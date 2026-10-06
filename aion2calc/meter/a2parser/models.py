"""Core protocol and combat models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SpecialDamage(str, Enum):
    BACK = "back"
    CRITICAL = "critical"
    PARRY = "parry"
    PERFECT = "perfect"
    DOUBLE = "double"
    FRONTAL = "frontal"
    SMITE = "smite"
    POWER_SHARD = "powershard"


@dataclass(frozen=True, slots=True)
class DamageEvent:
    actor_id: int
    target_id: int
    skill_code: int
    damage: int
    timestamp_ms: int
    damage_type: int = 0
    specials: frozenset[SpecialDamage] = frozenset()
    is_dot: bool = False
    multi_hit_count: int = 0
    multi_hit_damage: int = 0
    spec_flags: tuple[bool, bool, bool, bool, bool] = (False, False, False, False, False)
    power_scalar: int = 0

    @property
    def total_damage(self) -> int:
        return self.damage + self.multi_hit_damage


@dataclass(frozen=True, slots=True)
class HealEvent:
    actor_id: int
    skill_code: int
    amount: int
    timestamp_ms: int
    is_hot: bool = False
    target_id: int | None = None


@dataclass(slots=True)
class SkillStats:
    skill_code: int
    damage: int = 0
    hits: int = 0
    min_damage: int = 2**31 - 1
    max_damage: int = 0
    crits: int = 0
    backs: int = 0
    parries: int = 0
    perfects: int = 0
    doubles: int = 0
    frontal: int = 0
    multi_hit_count: int = 0
    multi_hit_damage: int = 0
    spec_flags: list[bool] = field(default_factory=lambda: [False] * 5)

    def add(self, event: DamageEvent) -> None:
        amount = event.total_damage
        self.damage += amount
        self.hits += 1
        self.min_damage = min(self.min_damage, amount)
        self.max_damage = max(self.max_damage, amount)
        self.crits += SpecialDamage.CRITICAL in event.specials
        self.backs += SpecialDamage.BACK in event.specials
        self.parries += SpecialDamage.PARRY in event.specials
        self.perfects += SpecialDamage.PERFECT in event.specials
        self.doubles += SpecialDamage.DOUBLE in event.specials
        self.frontal += SpecialDamage.FRONTAL in event.specials
        self.multi_hit_count += event.multi_hit_count
        self.multi_hit_damage += event.multi_hit_damage
        for index, enabled in enumerate(event.spec_flags):
            self.spec_flags[index] |= enabled


@dataclass(slots=True)
class ActorStats:
    actor_id: int
    nickname: str = ""
    job: str = ""
    damage: int = 0
    healing: int = 0
    regeneration: int = 0
    level: int = 0
    gear_score: int = 0
    combat_power: int = 0
    server_id: int = 0
    skills: dict[tuple[int, bool], SkillStats] = field(default_factory=dict)

    def add(self, event: DamageEvent) -> None:
        self.damage += event.total_damage
        key = (event.skill_code, event.is_dot)
        self.skills.setdefault(key, SkillStats(event.skill_code)).add(event)


@dataclass(slots=True)
class TargetStats:
    target_id: int
    damage: int = 0
    first_hit_ms: int = 0
    last_hit_ms: int = 0
    actors: dict[int, ActorStats] = field(default_factory=dict)
    mob_code: int = 0
    max_hp: int = 0
    current_hp: int = -1
    damage_by_second: dict[int, int] = field(default_factory=dict)
    actor_damage_by_second: dict[int, dict[int, int]] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        return max(0, self.last_hit_ms - self.first_hit_ms)


class TargetMode(str, Enum):
    MOST_DAMAGE = "mostDamage"
    MOST_RECENT = "mostRecent"
    LAST_HIT_BY_ME = "lastHitByMe"
    ALL_TARGETS = "allTargets"
