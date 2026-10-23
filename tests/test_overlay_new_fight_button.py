"""The overlay's "New" button starts a fresh encounter split without alt-tabbing
to the app. It must stay wired to the existing /api/meter split action (the same
one the Live Meter page's "Split now" uses), be grouped with the framed header
controls, and clear the live graph so the next fight starts clean."""
import pathlib

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
