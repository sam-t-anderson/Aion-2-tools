"""The overlay's "New" button starts a fresh encounter split without alt-tabbing
to the app. It must stay wired to the existing /api/meter split action (the same
one the Live Meter page's "Split now" uses), be grouped with the framed header
controls, and clear the live graph so the next fight starts clean. The live view
behind both then shows only the combat after the split."""
import pathlib

from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession, Record

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
HTML = (STATIC / "overlay.html").read_text(encoding="utf-8")
JS = (STATIC / "overlay.js").read_text(encoding="utf-8")
CSS = (STATIC / "overlay.css").read_text(encoding="utf-8")


def test_button_present_in_header():
    assert 'id="ovsplit"' in HTML


def test_button_posts_the_split_action():
    assert "#ovsplit" in JS
    assert 'action:"split"' in JS or '"action":"split"' in JS
    # Starting a new fight clears the live graph history.
    assert "graphHist=[]" in JS


def test_button_is_styled_with_the_other_header_controls():
    # Grouped into the framed button selectors (also fixes the older unstyled Copy).
    assert "#ovsplit" in CSS and "#ovcopy" in CSS


def test_new_clears_the_overlays_meter_until_the_next_fight_begins():
    # 0.2.329: New empties this overlay's meter at once (the app keeps every fight) and keeps it empty
    # until the live encounter's id changes, which the next fight's first hit does.
    assert "let clearedFight=null;" in JS
    assert 'clearedFight=String((lastSnap&&lastSnap.snapshot&&lastSnap.snapshot.selected_segment)??"");' in JS
    assert 'if(clearedFight!==null&&String(snap.selected_segment??"")!==clearedFight)clearedFight=null;' in JS
    assert "const players = cleared?[]:(snap.players || []);" in JS
    assert '"New fight · waiting for combat"' in JS and '"New fight — waiting for the first hit."' in JS
    for panel in ("const showT=showTarget&&!over&&!cleared&&", "const showD=showDummy&&!over&&!cleared&&", "const showC=showContribution&&!over&&!cleared&&"):
        assert panel in JS                       # the target, dummy and contribution panels clear with the rows
    assert "shownRates.clear();playerHist.clear();" in JS


def _session():
    """One player in one run, with the gap that splits fights at its default."""
    s = CombatSession()
    for epoch in (0, 1):
        s.identities[epoch] = {"names": {101: "Me"}, "spawns": {}, "jobs": {}, "local_id": 101,
                               "owners": {}, "roster": {}, "observed_players": {101}}
    s.runs = {1: {"instance_id": None, "start_observed": True}}
    s.run = 1
    return s


def _hit(s, t, damage, epoch=0):
    """The player hits the same enemy at ``t`` ms, recorded under the session's current split."""
    event = DamageEvent(actor_id=101, target_id=9001, skill_code=15210000, damage=damage, timestamp_ms=t)
    s.records.append(Record(epoch, event, frozenset(), 101, s.manual_split, 1, len(s.records) + 1))


def test_the_first_hit_after_new_does_not_bring_the_fight_before_back():
    # Reported: New emptied the overlay, but the first hit after it brought the previous fight's
    # damage back. The live view re-joined the new fight to the one before it (the same run, a few
    # seconds apart): the re-join meant for a zone change in the middle of a fight.
    s = _session()
    _hit(s, 1000, 600)
    _hit(s, 2000, 400)
    before = s.snapshot(scope="self")
    assert before["players"][0]["damage"] == 1000
    s.split_now()                                           # New
    _hit(s, 5000, 250)                                      # three seconds later
    live = s.snapshot(scope="self")
    assert live["players"][0]["damage"] == 250
    assert live["selected_segment"] != before["selected_segment"]       # the overlay shows it from here
    assert live["segments"][0]["id"] == before["selected_segment"]      # the fight before New is kept


def test_new_pressed_twice_keeps_every_earlier_fight_out():
    s = _session()
    _hit(s, 1000, 1000)
    s.split_now()
    _hit(s, 3000, 200)
    s.split_now()                                           # New again, before the next hit
    assert s.snapshot(scope="self")["players"][0]["damage"] == 200
    _hit(s, 5000, 50)
    assert s.snapshot(scope="self")["players"][0]["damage"] == 50


def test_a_zone_change_after_new_still_joins_the_fight_across_it():
    # The re-join itself stays: a mechanic's zone change in the middle of the fight after New (a new
    # epoch, the same split) does not reset the live view.
    s = _session()
    _hit(s, 1000, 1000)
    s.split_now()
    _hit(s, 5000, 300)
    _hit(s, 9000, 700, epoch=1)
    assert s.snapshot(scope="self")["players"][0]["damage"] == 1000


def test_the_boss_splits_the_session_makes_itself_are_unchanged():
    # Only the player's split stops the re-join: the session's own (a wipe, a reset, the next boss
    # after a kill) bump the same counter, and the live view treats them as it did.
    s = _session()
    _hit(s, 1000, 1000)
    s.manual_split += 1
    _hit(s, 5000, 300)
    assert s.snapshot(scope="self")["players"][0]["damage"] == 1300

