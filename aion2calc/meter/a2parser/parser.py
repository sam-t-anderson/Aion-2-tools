"""Partial AION 2 packet decoder for the core 0x04/0x38 damage record.

This is deliberately isolated: the upstream parser also handles identity,
rosters, summons, heals, HP, embedded records and evolving packet variants.
"""

from __future__ import annotations

import time
import json
import unicodedata
from collections import deque
from importlib.resources import files

from .framing import FrameKind, decompress_bundle, read_varint, walk, walk_inner
from .models import DamageEvent, HealEvent, SpecialDamage
from .lookup import has_skill, normalize_skill, decode_spec_flags, job_from_roster

try:
    DOT_SKILLS = set(json.loads(files(__package__).joinpath("data", "dot_skill_ids.json").read_text(encoding="utf-8")))
except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError):
    DOT_SKILLS = set()


def _var(data: bytes, offset: int) -> tuple[int, int] | None:
    result = read_varint(data, offset)
    if result.length <= 0 or result.value < 0:
        return None
    return result.value, offset + result.length


def _varint_ending_at(data: bytes, end: int, minimum_start: int,
                      minimum: int, maximum: int) -> int | None:
    """Read a complete varint ending at `end`, preferring a true boundary."""
    fallback = None
    for width in range(1, 4):
        start = end - width
        if start < minimum_start:
            break
        parsed = _var(data, start)
        if parsed is None or parsed[1] != end or not minimum <= parsed[0] <= maximum:
            continue
        continued = start > 0 and bool(data[start - 1] & 0x80)
        if not continued:
            return parsed[0]
        if fallback is None:
            fallback = parsed[0]
    return fallback


def _hit_tail(data: bytes, offset: int, layout: int, switch: int, value: int):
    def parse_as(candidate_layout: int):
        pos, field = offset, 0
        if candidate_layout == 4:
            parsed = _var(data, pos)
            if parsed is None or not 1 <= parsed[0] <= 25:
                return None
            field, pos = parsed
        count = damage = 0
        if switch & 0x20:
            parsed = _var(data, pos)
            if parsed is None or not 1 <= parsed[0] <= 25:
                return None
            count, pos = parsed
            for _ in range(count):
                hit = _var(data, pos)
                if hit is None:
                    return None
                damage += hit[0]
                pos = hit[1]
            if damage >= value:
                return None
        rest = data[pos:]
        clean_end = (not rest or rest.startswith(b"\x04\x38") or
                     (len(rest) >= 2 and rest[1] == 0 and 1 <= rest[0] <= 7))
        return (pos, field, count, damage) if clean_end else None

    return parse_as(layout) or (parse_as(6) if layout == 4 else None)


def _should_use_repeated_hit_damage(switch: int, encoded_damage: int,
                                    multi_count: int, first_hit: int | None,
                                    all_match: bool) -> bool:
    if switch != 54 or multi_count <= 0 or not all_match or first_hit is None:
        return False
    main_component = encoded_damage - multi_count * first_hit
    return main_component <= first_hit and encoded_damage // 10 == first_hit


def _damage_frames(data: bytes, *, inner: bool, depth: int = 0):
    if depth > 8:
        return
    framing = walk_inner(data) if inner else walk(data)
    for frame in framing.frames:
        if frame.kind is FrameKind.PACKET:
            yield frame.bytes(data)
        else:
            expanded = decompress_bundle(frame.payload(data))
            if expanded is not None:
                yield from _damage_frames(expanded, inner=True, depth=depth + 1)


def _compact_skill_context(frame: bytes) -> tuple[int, int] | None:
    length = read_varint(frame, 0)
    if length.length <= 0 or length.length >= len(frame):
        return None
    body = frame[length.length:]
    marker = next((i for i in range(max(0, len(body) - 4))
                   if body[i] == 0x08 and body[i + 1] in (0x3B, 0x3D)
                   and body[i + 2:i + 5] == b"\x38\0\0"), None)
    if marker is None:
        return None
    opcode = body.find(b"\x38", marker + 5)
    if opcode < 0:
        return None
    actor = _var(body, opcode + 1)
    if actor is None or actor[0] < 100:
        return None
    uid_at = actor[1] + 1
    if uid_at >= len(body):
        return None
    skill_at = uid_at + 1
    if skill_at + 3 > len(body):
        return None
    candidates = []
    if skill_at + 4 <= len(body):
        candidates.append(int.from_bytes(body[skill_at:skill_at + 4], "little"))
    candidates.append(int.from_bytes(body[skill_at:skill_at + 3], "little"))
    for candidate in candidates:
        if 1 <= candidate <= 299_999_999 and (has_skill(candidate) or 30_000_000 <= candidate <= 30_999_999):
            return actor[0], normalize_skill(candidate)
    return None


def parse_damage_packet(frame: bytes, timestamp_ms: int | None = None,
                        known_entities: set[int] | None = None,
                        compact_context: tuple[int, int] | None = None,
                        known_players: set[int] | None = None) -> list[DamageEvent | HealEvent]:
    """Decode recognized damage records from one complete framed packet."""
    if timestamp_ms is None:
        timestamp_ms = time.time_ns() // 1_000_000
    length = read_varint(frame, 0)
    if length.length <= 0:
        return []
    offset = length.length
    if frame[offset : offset + 2] != b"\x04\x38":
        return []
    offset += 2
    out: list[DamageEvent | HealEvent] = []
    while offset < len(frame):
        if frame[offset : offset + 2] == b"\x01\x00":
            offset += 2
        elif out:
            break
        target = _var(frame, offset)
        if target is None:
            break
        target_id, offset = target
        if target_id < 100 and (target_id <= 0 or known_entities is None or target_id not in known_entities):
            break
        switch = _var(frame, offset)
        if switch is None:
            break
        switch_value, offset = switch
        layout = switch_value & 0x0F
        if layout not in (4, 5, 6, 7):
            break
        unused = _var(frame, offset)
        if unused is None:
            break
        _, offset = unused
        actor = _var(frame, offset)
        if actor is None:
            break
        actor_id, offset = actor
        if actor_id < 100 and (actor_id <= 0 or known_entities is None or actor_id not in known_entities):
            break
        if offset + 4 > len(frame):
            break
        skill = int.from_bytes(frame[offset : offset + 4], "little")
        offset += 4
        if 3_000_000 <= skill <= 3_099_999:
            skill = skill * 10 + 1
        raw_skill = skill
        # NPC attacks use this lower skill-id range. Accept it only when
        # directed at a verified player by a different entity; these
        # records were previously rejected, leaving Defense empty.
        incoming_npc = (known_players is not None and target_id in known_players
                        and actor_id != target_id)
        if not 1 <= skill <= 299_999_999 or (1_000_000 <= skill <= 9_999_999 and not incoming_npc):
            break
        if offset < len(frame):
            offset += 1  # UID
        dtype = _var(frame, offset)
        if dtype is None:
            break
        damage_type, offset = dtype
        skip = {4: 8, 5: 12, 6: 10, 7: 14}[layout]
        specials: set[SpecialDamage] = set()
        if layout in (5, 6, 7) and offset < len(frame):
            mods = frame[offset]
            for mask, flag in ((2, SpecialDamage.PARRY), (4, SpecialDamage.PERFECT),
                               (8, SpecialDamage.DOUBLE), (32, SpecialDamage.SMITE),
                               (64, SpecialDamage.POWER_SHARD)):
                if mods & mask:
                    specials.add(flag)
            if offset + 2 < len(frame):
                if frame[offset + 2] == 1:
                    specials.add(SpecialDamage.BACK)
                elif frame[offset + 2] == 2:
                    specials.add(SpecialDamage.FRONTAL)
        if damage_type == 3:
            specials.add(SpecialDamage.CRITICAL)
        offset += skip
        first = _var(frame, offset)
        if first is None:
            break
        first_value, after_first = first
        second = _var(frame, after_first)
        if second is None:
            break
        second_value, after_second = second
        damage = first_value
        if first_value == 0:
            third = _var(frame, after_second)
            if third:
                first_value, second_value = second_value, third[0]
                after_first, after_second = after_second, third[1]
        offset = after_second
        first_is_damage = (1_000 <= first_value <= 99_999_999 and 0 <= second_value <= 25
                           and first_value <= 5_000_000 and layout == 6 and damage_type == 3)
        power_scalar = first_value if not first_is_damage and 1_000 <= first_value <= 200_000 else 0
        if not first_is_damage:
            damage = second_value
        else:
            damage = first_value
            offset = after_first
        if not 0 <= damage <= 99_999_999:
            break
        multi_count = multi_damage = 0
        strict_tail = _hit_tail(frame, offset, layout, switch_value, damage) if layout in (4, 6) and skill != 99_745_942 else None
        hit_count = 0
        if strict_tail is not None:
            offset, hit_count, multi_count, multi_damage = strict_tail
        if strict_tail is None and switch_value & 0x30 == 0x30 and offset < len(frame):
            field = _var(frame, offset)
            if field:
                offset = field[1]
        hit_count = 0
        pre_hit_offset = offset
        marker = offset + 1 < len(frame) and frame[offset + 1] == 0 and 1 <= frame[offset] <= 7
        if strict_tail is None and offset < len(frame) and not marker:
            peek = _var(frame, offset)
            if peek and 0 <= peek[0] <= 25:
                hit_count, offset = peek
            elif peek:
                marker_after = (peek[1] + 1 < len(frame) and frame[peek[1] + 1] == 0
                                and 1 <= frame[peek[1]] <= 7)
                actual = _var(frame, peek[1]) if not marker_after else None
                if actual and 0 <= actual[0] <= 25:
                    hit_count, offset = actual
                else:
                    offset = pre_hit_offset
        first_multi_hit_value = None
        all_multi_hits_match = True
        if strict_tail is None and hit_count:
            hits_read = 0
            for _ in range(min(hit_count, 25)):
                marker_next = (offset + 1 < len(frame) and frame[offset + 1] == 0
                               and 1 <= frame[offset] <= 7)
                next_packet = frame[offset:offset + 2] == b"\x04\x38"
                if marker_next or next_packet:
                    break
                nxt = _var(frame, offset)
                if not nxt:
                    break
                hit = nxt[0]
                if hit > max(damage, 500_000) or hit < 50:
                    multi_damage = 0
                    first_multi_hit_value = None
                    all_multi_hits_match = True
                    break
                if first_multi_hit_value is None:
                    first_multi_hit_value = hit
                elif first_multi_hit_value != hit:
                    all_multi_hits_match = False
                multi_damage += hit
                hits_read += 1
                offset = nxt[1]
            multi_count = hits_read
        if (strict_tail is None and switch_value == 54 and hit_count > multi_count
                and multi_count == 1 and first_multi_hit_value is not None
                and all_multi_hits_match):
            multi_count = hit_count
            multi_damage = first_multi_hit_value * hit_count
        if (strict_tail is None and _should_use_repeated_hit_damage(
                switch_value, second_value, multi_count, first_multi_hit_value,
                all_multi_hits_match)):
            damage = first_multi_hit_value
        if strict_tail is not None:
            offset, hit_count, multi_count, multi_damage = strict_tail
        if multi_count > 0 and multi_damage > 0 and damage > multi_damage:
            damage -= multi_damage
        compact_resolved = (compact_context is not None and skill == 99_745_942
                            and actor_id == compact_context[0] and hit_count > 1
                            and multi_damage > 0 and second_value > multi_damage)
        if compact_resolved:
            damage = second_value - multi_damage
            skill = compact_context[1]
        normalized_skill = skill if compact_resolved else normalize_skill(skill)
        heal_amount = 0
        if offset + 1 < len(frame) and frame[offset:offset + 2] == b"\x03\x00":
            heal = _var(frame, offset + 2)
            if heal and 0 < heal[0] < 10_000_000:
                heal_amount = heal[0]
        if actor_id != target_id:
            out.append(DamageEvent(actor_id, target_id, normalized_skill, damage, timestamp_ms,
                                   damage_type, frozenset(specials), False,
                                   multi_count, multi_damage,
                                   decode_spec_flags(compact_context[1] if compact_resolved else raw_skill),
                                   power_scalar))
            if heal_amount:
                out.append(HealEvent(actor_id, normalized_skill, heal_amount, timestamp_ms))
        elif damage > 1 and known_players is not None and actor_id in known_players:
            out.append(HealEvent(actor_id, normalized_skill, damage, timestamp_ms))
    return out


def parse_dot_packet(frame: bytes, timestamp_ms: int | None = None) -> DamageEvent | HealEvent | None:
    """Decode supported damage-over-time and healing effect records."""
    if timestamp_ms is None:
        timestamp_ms = time.time_ns() // 1_000_000
    length = read_varint(frame, 0)
    if length.length <= 0:
        return None
    offset = length.length
    if frame[offset : offset + 2] != b"\x05\x38":
        return None
    offset += 2
    target = _var(frame, offset)
    if target is None:
        return None
    target_id, offset = target
    if offset >= len(frame):
        return None
    effect_type = frame[offset]
    offset += 1
    is_damage = effect_type in (0x02, 0x0A)
    is_heal = effect_type in (0x01, 0x09, 0x0B)
    if not is_damage and not is_heal:
        return None
    actor = _var(frame, offset)
    if actor is None:
        return None
    actor_id, offset = actor
    if is_damage and actor_id == target_id:
        return None
    unknown = _var(frame, offset)
    if unknown is None:
        return None
    _, offset = unknown
    if offset + 4 > len(frame):
        return None
    skill_id = int.from_bytes(frame[offset : offset + 4], "little") // 100
    offset += 4
    amount = _var(frame, offset)
    if amount is None or not 0 < amount[0] <= 99_999_999:
        return None
    if is_heal:
        return HealEvent(actor_id, skill_id, amount[0], timestamp_ms, effect_type == 0x0B, target_id)
    if skill_id not in DOT_SKILLS:
        return None
    return DamageEvent(actor_id, target_id, skill_id, amount[0], timestamp_ms, is_dot=True)


def scan_identity(frame: bytes) -> list[tuple[int, str, bool, str | None]]:
    """Find the upstream masked self/player identity records in packet bytes."""
    updates = []
    i = 0
    while i + 8 < len(frame):
        if frame[i + 1] != 0x36 or frame[i] not in (0x33, 0x44, 0x45):
            i += 1
            continue
        is_self = frame[i] == 0x33
        entity = _var(frame, i + 2)
        if entity is None or not 1 <= entity[0] <= 9_999_999:
            i += 1
            continue
        entity_id, after_id = entity
        mask_at = after_id + 4
        if mask_at + 1 >= len(frame) or frame[mask_at] & 1 == 0:
            i += 1
            continue
        name_len = frame[mask_at + 1]
        name_start, name_end = mask_at + 2, mask_at + 2 + name_len
        if not 1 <= name_len <= 48 or name_end > len(frame):
            i += 1
            continue
        try:
            name = frame[name_start:name_end].decode("utf-8")
        except UnicodeDecodeError:
            i += 1
            continue
        if not (1 <= len(name) <= 12 and name.isalnum() and any(c.isalpha() for c in name)):
            i += 1
            continue
        job = None
        if is_self and name_end + 6 <= len(frame):
            roster_value = int.from_bytes(frame[name_end + 2:name_end + 6], "little")
            from .lookup import job_from_roster
            job = job_from_roster(roster_value)
        updates.append((entity_id, name, is_self, job))
        i = name_end
    return updates


def scan_self_profile(frame: bytes) -> tuple[int, int, str, int] | None:
    """Read server, class and level from a valid masked local-player record."""
    i = 0
    while i + 8 < len(frame):
        if frame[i:i + 2] != b"\x33\x36":
            i += 1
            continue
        entity = _var(frame, i + 2)
        if entity is None or not 1 <= entity[0] <= 9_999_999:
            i += 1
            continue
        actor_id, after_id = entity
        mask_at = after_id + 4
        if mask_at + 1 >= len(frame) or frame[mask_at] & 1 == 0:
            i += 1
            continue
        name_len = frame[mask_at + 1]
        name_start = mask_at + 2
        name_end = name_start + name_len
        if not 1 <= name_len <= 48 or name_end + 11 > len(frame):
            i += 1
            continue
        try:
            name = frame[name_start:name_end].decode("utf-8")
        except UnicodeDecodeError:
            i += 1
            continue
        if not (1 <= len(name) <= 12 and name.isalnum() and any(c.isalpha() for c in name)):
            i += 1
            continue
        server_id = int.from_bytes(frame[name_end:name_end + 2], "little")
        roster_class = int.from_bytes(frame[name_end + 2:name_end + 6], "little")
        job = job_from_roster(roster_class)
        level = int.from_bytes(frame[name_end + 7:name_end + 11], "little")
        if 1_000 <= server_id < 3_000 and job and 1 <= level <= 99:
            return actor_id, server_id, job, level
        i = name_end
    return None


def scan_character_list(frame: bytes, character_name: str) -> tuple[int, str] | None:
    """Resolve the configured local character from a login character list."""
    wanted = character_name.strip()
    if not wanted:
        return None
    i = 0
    while i + 5 < len(frame):
        entity_id = int.from_bytes(frame[i:i + 4], "little")
        if not 100 <= entity_id <= 9_999_999:
            i += 1
            continue
        name_len = frame[i + 4]
        if not 1 <= name_len <= 48 or i + 5 + name_len > len(frame):
            i += 1
            continue
        try:
            name = frame[i + 5:i + 5 + name_len].decode("utf-8")
        except UnicodeDecodeError:
            i += 1
            continue
        valid_name = (1 <= len(name) <= 12 and name.isalnum()
                      and any(char.isalpha() for char in name))
        if valid_name and name == wanted:
            return entity_id, name
        i += 1
    return None


def scan_actor_name_bindings(frame: bytes) -> list[tuple[int, str]]:
    """Read actor-id/name pairs carried near 0x36 anchors in packet variants."""
    found: list[tuple[int, str]] = []
    seen: set[int] = set()
    anchor: tuple[int, int] | None = None
    i = 0
    while i < len(frame):
        if frame[i] == 0x36:
            if i > 0 and frame[i - 1] in (0x40, 0x41, 0x44, 0x45):
                anchor = None
                i += 1
                continue
            actor = _var(frame, i + 1)
            anchor = (actor[0], actor[1]) if actor and actor[0] >= 100 else None
            i += 1
            continue
        if frame[i] == 0x07 and anchor is not None:
            actor_id, end_of_id = anchor
            distance = i - end_of_id
            if 0 <= distance <= 64 and actor_id not in seen and i + 1 < len(frame):
                name_len = frame[i + 1]
                end = i + 2 + name_len
                if 1 <= name_len <= 36 and end <= len(frame):
                    try:
                        raw_name = frame[i + 2:end].decode("utf-8")
                    except UnicodeDecodeError:
                        raw_name = ""
                    name = raw_name.split("\0", 1)[0].strip()
                    cleaned = []
                    for char in name:
                        if (not char.isalnum() or char == "\ufffd"
                                or unicodedata.category(char).startswith("C")):
                            break
                        cleaned.append(char)
                    value = "".join(cleaned)
                    cjk = any(0x3400 <= ord(char) <= 0x4DBF
                              or 0x4E00 <= ord(char) <= 0x9FFF
                              or 0xAC00 <= ord(char) <= 0xD7AF
                              or 0x20000 <= ord(char) <= 0x2A6DF for char in value)
                    if (value and any(char.isalpha() for char in value)
                            and (len(value) >= 2 or cjk)):
                        found.append((actor_id, value))
                        seen.add(actor_id)
                        i = end
                        continue
        i += 1
    return found


def _nickname(data: bytes) -> str | None:
    """Return a conservative valid player name from a protocol string field."""
    try:
        raw = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    value = raw.split("\0", 1)[0].strip()
    cleaned = []
    for char in value:
        if not char.isalnum() or unicodedata.category(char).startswith("C"):
            if not cleaned:
                return None
            break
        cleaned.append(char)
    value = "".join(cleaned)
    cjk = any(0x3400 <= ord(char) <= 0x4DBF or 0x4E00 <= ord(char) <= 0x9FFF
              or 0xAC00 <= ord(char) <= 0xD7AF or 0x20000 <= ord(char) <= 0x2A6DF
              for char in value)
    return value if any(char.isalpha() for char in value) and (len(value) >= 2 or cjk) else None


def scan_legacy_nicknames(packet: bytes) -> list[tuple[int, str]]:
    """Decode older name/loot anchors still emitted beside modern identity packets.

    These packet variants are important when the meter attaches after a zone
    has loaded: a player may damage a target before a new ``45 36`` identity
    record appears.  The patterns match upstream's E2/E0, 0F1D37, 4C and loot
    attribution readers and return only conservative UTF-8 player names.
    """
    found: dict[int, str] = {}

    def add(actor_id: int | None, start: int, length: int) -> None:
        if actor_id is None or not 100 <= actor_id <= 9_999_999 or not 2 <= length <= 36:
            return
        name = _nickname(packet[start:start + length])
        if name:
            old = found.get(actor_id)
            if old is None or len(name) > len(old):
                found[actor_id] = name

    i = 0
    while i + 2 < len(packet):
        # E2/E0 07 <length><name>, with the actor varint immediately before it.
        if packet[i] in (0xE0, 0xE2) and packet[i + 1] == 0x07:
            size = packet[i + 2]
            if i + 3 + size <= len(packet):
                add(_varint_ending_at(packet, i, max(0, i - 3), 100, 9_999_999), i + 3, size)
                i += 3 + size
                continue
        # 0F 1D 37 <actor varint> ... 00 00 <length><name>.
        if packet[i:i + 3] == b"\x0f\x1d\x37":
            actor = _var(packet, i + 3)
            if actor and 100 <= actor[0] <= 9_999_999:
                pos, stop = actor[1], min(len(packet) - 2, actor[1] + 500)
                while pos < stop:
                    if packet[pos:pos + 3] in (b"\x06\0\x36", b"\x0e\0\x36"):
                        break
                    if packet[pos:pos + 2] == b"\0\0" and pos + 3 < len(packet):
                        size = packet[pos + 2]
                        if pos + 3 + size <= len(packet):
                            add(actor[0], pos + 3, size)
                            break
                    pos += 1
        # 04/00 4C <actor varint> ... <name> ... 06/0E 00 36.
        if packet[i] in (0x00, 0x04) and packet[i + 1] == 0x4C:
            actor = _var(packet, i + 2)
            if actor and 100 <= actor[0] <= 9_999_999:
                pos, stop = actor[1], min(len(packet) - 2, actor[1] + 128)
                while pos < stop:
                    if packet[pos:pos + 3] in (b"\x06\0\x36", b"\x0e\0\x36"):
                        for size in range(36, 1, -1):
                            at = pos - size - 1
                            if at > actor[1] and packet[at] == size:
                                add(actor[0], at + 1, size)
                                break
                        break
                    pos += 1
        # Loot attribution: <actor varint> F0..FF 03/A3 <length><name>.
        if 0xF0 <= packet[i] <= 0xFF and packet[i + 1] in (0x03, 0xA3) and i + 3 < len(packet):
            size = packet[i + 2]
            if i + 3 + size <= len(packet):
                add(_varint_ending_at(packet, i, max(0, i - 3), 100, 99_999), i + 3, size)
                i += 3 + size
                continue
        i += 1
    return list(found.items())


def scan_party_roster(data: bytes) -> tuple[dict[str, dict], bool, int] | None:
    """Decode a complete or partial upstream 0x02/0x97 party roster."""
    i = 0
    while i + 24 < len(data):
        if data[i:i + 2] != b"\x02\x97":
            i += 1
            continue
        pos = i + 2 + 4  # opcode and party key
        if pos >= len(data):
            return None
        party_name_len = data[pos]
        pos += 1
        if not 1 <= party_name_len <= 40 or pos + party_name_len + 16 > len(data):
            i += 1
            continue
        try:
            data[pos:pos + party_name_len].decode("utf-8")
        except UnicodeDecodeError:
            i += 1
            continue
        pos += party_name_len
        party_size = data[pos]
        pos += 1
        if not 1 <= party_size <= 12:
            i += 1
            continue
        dungeon_id = int.from_bytes(data[pos:pos + 4], "little")
        pos += 17  # dungeon id, 2 pad, leader dbid, 3 pad
        count = _var(data, pos)
        if count is None or not 1 <= count[0] <= 12:
            i += 1
            continue
        pos = count[1]
        members: dict[str, dict] = {}
        complete = False
        for member_index in range(count[0]):
            if pos + 20 > len(data):
                break
            slot = data[pos + 1]
            dbid = int.from_bytes(data[pos + 2:pos + 10], "little")
            server_id = (dbid >> 48) & 0xFFFF
            name_len = data[pos + 10]
            if name_len == 0:
                complete = True
                break
            if name_len > 40 or pos + 11 + name_len + 12 > len(data):
                break
            name_start = pos + 11
            try:
                nickname = data[name_start:name_start + name_len].decode("utf-8")
            except UnicodeDecodeError:
                break
            fields = name_start + name_len
            roster_class = int.from_bytes(data[fields:fields + 4], "little")
            level = int.from_bytes(data[fields + 4:fields + 8], "little")
            gear_score = int.from_bytes(data[fields + 8:fields + 12], "little")
            if not 1 <= level <= 200 or gear_score > 1_000_000:
                break
            anchor = next((j for j in range(fields + 12, min(fields + 22, len(data) - 1))
                           if int.from_bytes(data[j:j + 2], "little") == server_id), None)
            if anchor is None:
                break
            power_at = anchor + 5
            if power_at + 8 > len(data):
                break
            combat_power = int.from_bytes(data[power_at:power_at + 8], "little")
            if combat_power > 100_000_000:
                break
            members[nickname] = {
                "slot": slot, "dbid": dbid, "serverId": server_id,
                "job": job_from_roster(roster_class), "level": level,
                "gearScore": gear_score, "combatPower": combat_power,
            }
            if member_index + 1 == count[0]:
                complete = True
                break
            # Reacquire next slot header because the tail length varies.
            expected = (slot + 1) & 0xFF
            next_pos = None
            for j in range(power_at + 8, min(power_at + 40, len(data) - 12)):
                if data[j + 1] != expected:
                    continue
                next_server = int.from_bytes(data[j + 8:j + 10], "little")
                next_len = data[j + 10]
                if 0 < next_server <= 9_999 and 0 < next_len <= 40 and j + 11 + next_len <= len(data):
                    try:
                        data[j + 11:j + 11 + next_len].decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    next_pos = j
                    break
            if next_pos is None:
                break
            pos = next_pos
        if members:
            return members, complete, dungeon_id
        i += 1
    return None


def scan_summon_links(data: bytes, names: dict[int, str], known_summons: set[int] | None = None) -> tuple[set[int], dict[int, int]]:
    """Read common summon-spawn parent keys and 04/8D owner links."""
    summon_ids: set[int] = set()
    links: dict[int, int] = {}
    i = 0
    while i + 8 < len(data):
        if data[i + 1] != 0x36 or data[i] not in (0x40, 0x41):
            i += 1
            continue
        entity = _var(data, i + 2)
        if entity is None or not 100 <= entity[0] <= 9_999_999:
            i += 1
            continue
        entity_id, after_id = entity
        real_id = ((entity_id & 0x3FFF) | 0x4000) if entity_id > 1_000_000 else entity_id
        mask = int.from_bytes(data[after_id:after_id + 4].ljust(4, b"\0"), "little")
        kind = data[after_id] if after_id < len(data) else 0
        is_summon = kind in (0x5F, 0x1F, 0x1D, 0x5D)
        if is_summon:
            summon_ids.add(real_id)
        # Inline owner name is carried under a one-bit gate in one of two
        # observed mask widths. Keep only a whole valid name field.
        owner_name = None
        cursor = after_id + 5
        for width in (4, 2):
            gate = after_id + width
            if gate + 1 >= len(data) or data[gate] & 1 == 0:
                continue
            name_len = data[gate + 1]
            end = gate + 2 + name_len
            if not 1 <= name_len <= 48 or end > len(data):
                continue
            try:
                candidate = data[gate + 2:end].decode("utf-8")
            except UnicodeDecodeError:
                continue
            if 1 <= len(candidate) <= 12 and candidate.isalnum() and any(c.isalpha() for c in candidate):
                owner_name, cursor = candidate, end
                break
        if kind in (0x5F, 0x1F, 0x1D, 0x5D, 0x1C) and owner_name:
            candidates = [owner_id for owner_id, name in names.items()
                          if name == owner_name and owner_id != real_id]
            if len(candidates) == 1:
                links[real_id] = candidates[0]
        if kind == 0x5F and mask & 0x10:
            search_end = min(len(data) - 12, cursor + 512)
            for at in range(max(cursor, after_id + 4), search_end):
                if at == 0 or data[at - 1] != 0x06:
                    continue
                owner_id = int.from_bytes(data[at:at + 4], "little")
                legion_id = int.from_bytes(data[at + 4:at + 8], "little")
                zero = int.from_bytes(data[at + 8:at + 10], "little")
                server_id = int.from_bytes(data[at + 10:at + 12], "little")
                nlen = data[at + 12]
                if (100 <= owner_id <= 9_999_999 and owner_id != real_id
                        and legion_id < 2**32 and zero == 0 and 0 < server_id < 10_000
                        and nlen <= 40 and at + 13 + nlen <= len(data)):
                    try:
                        data[at + 13:at + 13 + nlen].decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    links[real_id] = owner_id
                    break
        if kind in (0x5F, 0x1F, 0x1D, 0x5D):
            owner_anchor = b"\x80\x75\xd5\x2a\xbb\x03\0\0"
            end = min(len(data) - len(owner_anchor), after_id + 120)
            for at in range(after_id, max(after_id, end) + 1):
                if data[at:at + len(owner_anchor)] != owner_anchor:
                    continue
                owner = _var(data, at + len(owner_anchor))
                if owner and 1 <= owner[0] <= 9_999_999 and owner[0] != real_id:
                    links[real_id] = owner[0]
                    break
        i = after_id + 4
    # Ownership packet: <len> 04 8D <summon varint> <4 bytes> <owner varint>.
    i = 0
    while i + 4 < len(data):
        if data[i:i + 2] != b"\x04\x8d":
            i += 1
            continue
        summon = _var(data, i + 2)
        if summon is None:
            i += 2
            continue
        summon_id, pos = summon
        pos += 4
        owner = _var(data, pos)
        if (owner and 100 <= owner[0] <= 9_999_999
                and (summon_id in summon_ids or (known_summons and summon_id in known_summons))
                and owner[0] != summon_id):
            links[summon_id] = owner[0]
        i += 2
    # Embedded ownership records carry `<owner varint><server u16><len><name>`
    # after the fixed field. Recover the owner from the complete varint boundary
    # and accept current server ids instead of a short hard-coded server list.
    i = 0
    while i + 2 < len(data):
        marker = data.find(b"\x04\x8d", i)
        if marker < 0:
            break
        i = marker + 2
        summon = _var(data, i)
        if summon is None or not 100 <= summon[0] <= 9_999_999:
            continue
        summon_id, pos = summon
        after_fixed = pos + 4
        if after_fixed >= len(data) or data[after_fixed] == 0:
            continue
        scan_end = min(len(data) - 2, after_fixed + 128)
        for server_at in range(after_fixed + 1, scan_end):
            server_id = int.from_bytes(data[server_at:server_at + 2], "little")
            if not 1_000 <= server_id <= 2_999:
                continue
            owner_id = _varint_ending_at(data, server_at, after_fixed, 100, 99_999)
            if owner_id is None or owner_id == summon_id:
                continue
            length_at = server_at + 2
            if length_at >= len(data):
                continue
            name_len = data[length_at]
            name_end = length_at + 1 + name_len
            if not 1 <= name_len <= 48 or name_end > len(data):
                continue
            try:
                owner_name = data[length_at + 1:name_end].decode("utf-8")
            except UnicodeDecodeError:
                continue
            valid_name = (1 <= len(owner_name) <= 12 and owner_name.isalnum()
                          and any(char.isalpha() for char in owner_name))
            if not valid_name:
                continue
            names.setdefault(owner_id, owner_name)
            if summon_id in summon_ids or (known_summons and summon_id in known_summons):
                links[summon_id] = owner_id
            i = name_end
            break
    return summon_ids, links


def scan_spawn_metadata(data: bytes, diagnostics: list | None = None) -> dict[int, dict[str, int]]:
    """Extract entity-to-NPC-code and spawn-time HP anchors from spawn bytes."""
    found: dict[int, dict[str, int]] = {}
    i = 0
    while i + 6 < len(data):
        if data[i + 1] != 0x36 or data[i] not in (0x40, 0x41):
            i += 1
            continue
        entity = _var(data, i + 2)
        if entity is None or not 100 <= entity[0] <= 9_999_999:
            i += 1
            continue
        entity_id, pos = entity
        if entity_id > 1_000_000:
            entity_id = (entity_id & 0x3FFF) | 0x4000
        info = found.setdefault(entity_id, {})
        end = min(len(data) - 2, pos + 60)
        for at in range(pos, end):
            if data[at] != 0 or data[at + 1] not in (0x40, 0x00) or data[at + 2] != 0x02:
                continue
            if at >= pos + 3:
                info["mobCode"] = data[at - 3] | (data[at - 2] << 8) | (data[at - 1] << 16)
            hp_end = min(len(data) - 1, at + 67)
            for hp_at in range(at + 3, hp_end):
                if data[hp_at] != 0x01:
                    continue
                current = _var(data, hp_at + 1)
                if current is None or current[0] <= 0:
                    continue
                maximum = _var(data, current[1])
                if maximum and maximum[0] >= current[0]:
                    info["currentHp"], info["maxHp"] = current[0], maximum[0]
                    break
            break
        if diagnostics is not None and len(diagnostics) < 128:
            diagnostics.append({"entity": entity_id, "opcode": data[i],
                                "mob_code": info.get("mobCode", 0),
                                "status": "type_decoded" if info.get("mobCode") else "type_marker_missing"})
        i = pos + 1
    return found


def scan_hp_updates(data: bytes) -> tuple[dict[int, int], dict[int, int]]:
    """Return current HP and maximum HP learned from packet/feed records."""
    current: dict[int, int] = {}
    maximum: dict[int, int] = {}
    i = 0
    while i + 11 < len(data):
        if data[i] != 0x8D:
            i += 1
            continue
        entity = _var(data, i + 1)
        if entity is None or not 100 <= entity[0] <= 9_999_999:
            i += 1
            continue
        entity_id, pos = entity
        if (pos + 11 <= len(data) and data[pos:pos + 3] == b"\x02\x01\x00"
                and data[pos + 7:pos + 11] == b"\0\0\0\0"):
            value = int.from_bytes(data[pos + 3:pos + 7], "little")
            if value <= 100_000_000:
                current[entity_id] = value
            i = pos + 11
        else:
            i += 1
    # Max HP packet: <len> 1B 92 <entity> <current HP> <maximum HP>.
    for frame in _damage_frames(data, inner=False):
        length = read_varint(frame, 0)
        if length.length <= 0:
            continue
        pos = length.length
        if frame[pos:pos + 2] != b"\x1b\x92":
            continue
        actor = _var(frame, pos + 2)
        if actor is None or not 100 <= actor[0] <= 9_999_999:
            continue
        hp = _var(frame, actor[1])
        if hp is None:
            continue
        max_hp = _var(frame, hp[1])
        if max_hp and 0 < max_hp[0] <= 50_000_000:
            maximum[actor[0]] = max_hp[0]
    return current, maximum


def scan_deaths(data: bytes) -> set[int]:
    """Return entity ids with the upstream in-combat 0x41/0x42 0x36 death flag."""
    dead: set[int] = set()
    for frame in _damage_frames(data, inner=False):
        length = read_varint(frame, 0)
        if length.length <= 0:
            continue
        pos = length.length
        if pos + 2 > len(frame) or frame[pos] not in (0x41, 0x42) or frame[pos + 1] != 0x36:
            continue
        entity = _var(frame, pos + 2)
        if entity is None:
            continue
        skipped = _var(frame, entity[1])
        flag = _var(frame, skipped[1]) if skipped else None
        if flag and flag[0] == 3:
            dead.add(entity[0])
    return dead


def scan_zone_state(data: bytes) -> tuple[bool, int | None]:
    """Find self zone-transition and current map id packets."""
    zone_change = False
    map_id = None
    for frame in _damage_frames(data, inner=False):
        length = read_varint(frame, 0)
        if length.length <= 0:
            continue
        pos = length.length
        opcode = frame[pos:pos + 2]
        if opcode == b"\x23\x36":
            entity = _var(frame, pos + 2)
            if entity and entity[0] == 0:
                zone_change = True
        elif opcode == b"\x21\x36" and pos + 10 <= len(frame):
            map_id = int.from_bytes(frame[pos + 6:pos + 10], "little")
    return zone_change, map_id


def decode_stream(data: bytes, timestamp_ms: int | None = None,
                  known_entities: set[int] | None = None,
                  seen_embedded: set[bytes] | None = None,
                  seen_order: deque[bytes] | None = None,
                  known_players: set[int] | None = None):
    """Yield recognized damage, DOT and healing records from a captured stream."""
    seen = seen_embedded if seen_embedded is not None else set()
    order = seen_order if seen_order is not None else deque()

    def walk_packets(buffer: bytes, *, inner: bool, depth: int):
        if depth > 8:
            return
        frames = walk_inner(buffer) if inner else walk(buffer)
        pending_context = None
        for item in frames.frames:
            if item.kind is FrameKind.BUNDLE:
                expanded = decompress_bundle(item.payload(buffer))
                if expanded is not None:
                    yield from walk_packets(expanded, inner=True, depth=depth + 1)
                pending_context = None
                continue
            frame = item.bytes(buffer)
            if inner:
                found_context = _compact_skill_context(frame)
                if found_context is not None:
                    pending_context = found_context
            direct = parse_damage_packet(frame, timestamp_ms, known_entities, pending_context, known_players)
            yield from direct
            if pending_context and any(e.actor_id == pending_context[0] and e.skill_code == pending_context[1] for e in direct):
                pending_context = None
            effect = parse_dot_packet(frame, timestamp_ms) if not direct else None
            if effect is not None:
                yield effect
            if direct:
                continue
            pos = 0
            while pos + 1 < len(frame):
                idx = frame.find(b"\x04\x38", pos)
                if idx < 0:
                    break
                pos = idx + 1
                raw_key = frame[idx:min(idx + 64, len(frame))]
                if raw_key in seen:
                    continue
                recovered = parse_damage_packet(b"\xff\x01" + frame[idx:], timestamp_ms,
                                                known_entities, known_players=set())
                recovered_damage = [event for event in recovered if isinstance(event, DamageEvent)]
                if recovered_damage and all(
                    event.actor_id != event.target_id and 1 <= event.damage <= 99_999_999
                    and 1 <= event.skill_code <= 299_999_999 and 1 <= event.damage_type <= 3
                    and (has_skill(event.skill_code) or 30_000_000 <= event.skill_code <= 30_999_999)
                    for event in recovered_damage
                ):
                    if len(seen) >= 16_384 and order:
                        seen.discard(order.popleft())
                    seen.add(raw_key)
                    order.append(raw_key)
                    yield from recovered_damage
            if effect is not None:
                continue
    yield from walk_packets(data, inner=False, depth=0)
