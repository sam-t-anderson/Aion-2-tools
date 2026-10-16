"""The RTSS in-game overlay backend: the shared-memory slot logic (claim a free slot after slot 0,
reuse our own, write the extended text on v2.7+, bump the frame counter, release cleanly) runs
against an RTSS-shaped block on any platform; the text renderer never emits user text that RTSS
would read as a tag; the pusher reports a missing RTSS instead of raising."""
import struct

import pytest

from aion2calc.app import rtss


def _view(version=0x0002000F, slots=8):
    return rtss.MemoryView(rtss.fake_block(version=version, slots=slots))


def _owner(view, header, index):
    return rtss._cstr(view.read(header.entry_offset(index) + rtss.OSD_TEXT_BYTES, rtss.OSD_OWNER_BYTES))


def test_claims_the_first_free_slot_after_slot_zero_and_reuses_it():
    view = _view()
    header = rtss.Header(view)
    # Slot 1 belongs to another program; slot 0 is the primary client's and must never be touched.
    view.write(header.entry_offset(1) + rtss.OSD_TEXT_BYTES, rtss._cbytes("MSIAfterburner", rtss.OSD_OWNER_BYTES))
    info = rtss.write_text(view, "one")
    assert info["slot"] == 2 and info["extended"] is True
    assert _owner(view, header, 2) == rtss.OWNER and _owner(view, header, 1) == "MSIAfterburner" and _owner(view, header, 0) == ""
    assert rtss._cstr(view.read(header.entry_offset(2) + 512, rtss.OSD_EX_BYTES)) == "one"
    assert rtss.Header(view).osd_frame == 1
    assert rtss.write_text(view, "two")["slot"] == 2                 # our slot is reused, not a new one
    assert rtss._cstr(view.read(header.entry_offset(2) + 512, rtss.OSD_EX_BYTES)) == "two"
    assert rtss.Header(view).osd_frame == 2


def test_old_shared_memory_uses_the_short_text_field():
    view = _view(version=0x00020005)
    header = rtss.Header(view)
    assert header.extended_text is False
    info = rtss.write_text(view, "x" * 400)
    assert info["extended"] is False
    text = rtss._cstr(view.read(header.entry_offset(info["slot"]), rtss.OSD_TEXT_BYTES))
    assert len(text) == 255                                            # truncated to the 256-byte field


def test_release_clears_only_our_slot_and_bumps_the_frame():
    view = _view()
    header = rtss.Header(view)
    view.write(header.entry_offset(1) + rtss.OSD_TEXT_BYTES, rtss._cbytes("Other", rtss.OSD_OWNER_BYTES))
    rtss.write_text(view, "ours")
    assert rtss.release(view) is True
    assert _owner(view, header, 2) == "" and _owner(view, header, 1) == "Other"
    assert rtss.Header(view).osd_frame == 2
    assert rtss.release(view) is False                                 # nothing of ours left


def test_bad_signature_or_full_array_are_reported():
    block = rtss.fake_block()
    block[0:4] = struct.pack("<I", 0xDEAD)
    with pytest.raises(rtss.NotRunning):
        rtss.Header(rtss.MemoryView(block))
    view = _view(slots=3)
    header = rtss.Header(view)
    for index in (1, 2):
        view.write(header.entry_offset(index) + rtss.OSD_TEXT_BYTES, rtss._cbytes("Taken", rtss.OSD_OWNER_BYTES))
    with pytest.raises(rtss.RTSSError):
        rtss.write_text(view, "no room")


def test_render_rows_shares_and_tag_safety():
    status = {"running": True, "snapshot": {"boss": "Atiel <Phase 2>", "duration": 75, "players": [
        {"name": "Seraphel", "class": "sorcerer", "dps": 23400, "damage": 1_400_000},
        {"name": "<Nyxara>", "class": "ranger", "dps": 15600, "damage": 933_300},
        {"name": "Drakthar", "class": "gladiator", "dps": 13900, "damage": 831_900}]}}
    plain = rtss.render(status, rows=2)
    lines = plain.split("\n")
    assert lines[0].startswith("Atiel Phase 2  1:15") and lines[0].endswith("DPS")
    assert len(lines) == 3 and lines[1].startswith("Seraphel") and "23.4K/s" in lines[1] and "44%" in lines[1]
    assert "<" not in plain and ">" not in plain                         # user text can never open an RTSS tag
    colored = rtss.render(status, rows=3, style="colored")
    assert "<C=3A86C8>Seraphel" in colored and "<C=B9962A>Nyxara" in colored and colored.count("<C>") == 4
    assert "waiting for combat" in rtss.render({"running": True, "snapshot": {"players": []}})
    assert rtss.render({"running": False, "snapshot": {}}).startswith("Meter stopped")
    assert len(rtss.render({"snapshot": {"players": [{"name": "x" * 50, "dps": 1, "damage": 1}] * 100}}, rows=100)) < rtss.OSD_EX_BYTES


def test_pusher_reports_missing_rtss_and_pushes_into_a_fake_block():
    def missing():
        raise rtss.NotRunning("RTSS is not running")
    settings = {"rtss_enabled": True, "rtss_rows": 3, "rtss_metric": "dps", "rtss_style": "plain"}
    pusher = rtss.Pusher(lambda: {"running": True, "snapshot": {"players": []}}, lambda: settings, view_factory=missing)
    assert pusher.push_once() is False
    assert pusher.state["connected"] is False and "not running" in pusher.state["error"]
    block = rtss.fake_block()
    pusher = rtss.Pusher(lambda: {"running": True, "snapshot": {"boss": "B", "players": [{"name": "A", "dps": 5, "damage": 5}]}},
                         lambda: settings, view_factory=lambda: rtss.MemoryView(block))
    assert pusher.push_once() is True
    assert pusher.state["connected"] and pusher.state["slot"] == 1 and pusher.state["version"] == "2.15" and pusher.state["updates"] == 1
    assert pusher.push_once() is True and pusher.state["updates"] == 1      # unchanged text: no rewrite
    pusher.stop()
    assert rtss.release(rtss.MemoryView(block)) is False                   # stop() already cleared our slot
    assert pusher.state["enabled"] is False and pusher.state["connected"] is False


def test_open_view_refuses_off_windows(monkeypatch):
    monkeypatch.setattr(rtss.sys, "platform", "linux")
    assert rtss.supported() is False
    with pytest.raises(rtss.RTSSError):
        rtss.open_view()
