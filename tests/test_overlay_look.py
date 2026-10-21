"""The overlay's restyle is cosmetic: the markup, ids, settings hooks and behaviour stay.

Pins the pieces the new look depends on — the eight-class overlay palette (a user's own
class colour still wins), the boss-panel wrapping spans, the light number defaults the
settings page and the Default (gold) preset must agree on — and that nothing the
stylesheet used to expose for the layout settings went missing."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
CSS = (STATIC / "overlay.css").read_text(encoding="utf-8")
JS = (STATIC / "overlay.js").read_text(encoding="utf-8")
APP = (STATIC / "app.js").read_text(encoding="utf-8")
REVIEW = (STATIC / "combat-review.js").read_text(encoding="utf-8")
CLASSES = {"gladiator", "templar", "assassin", "ranger", "sorcerer", "spiritmaster", "cleric", "chanter"}


def _palette(src, name):
    m = re.search(name + r"\s*[:=]\s*\{([^}]*)\}", src)
    assert m, name
    return dict(re.findall(r"(\w+):\"(#[0-9a-f]{6})\"", m.group(1)))


def test_every_class_has_an_overlay_tint_and_the_review_palette_matches():
    overlay = _palette(JS, "OVERLAY_CLASS_COLORS")
    assert set(overlay) == CLASSES
    assert len(set(overlay.values())) == 8                      # all distinct
    assert _palette(REVIEW, r"\"Overlay \(cool\)\"") == overlay   # the app-wide palette is the same set


def test_a_users_own_class_colour_and_the_class_colour_switch_still_win():
    body = JS.split("function barColor(cls){", 1)[1].split("\n  }", 1)[0]
    assert "a2-combat-colors" in body                           # the shared preference store
    assert "pref.enabled===false" in body                       # "Use class colors" off -> shared fallback
    assert "A2CombatReview.color(key)" in body                  # chosen colour / unknown class -> shared rule
    # Every tinted element goes through it: bar, icon badge, swatch, coloured names, sparkline.
    assert JS.count("barColor(") >= 6
    assert "A2CombatReview.color(p.class)" not in JS


def test_the_boss_panel_keeps_its_readouts_in_order():
    row = JS.split("$(\"#ovtarget\").innerHTML=", 1)[1].split("\n", 1)[0]
    for piece in ("ovtlabel", "${portrait}", "ovtname", "${also}", "${hp}", "ovtline", "${ttk}", "class=\"sub\"", "${top"):
        assert piece in row
    assert row.index("ovtname") < row.index("${hp}") < row.index("ovtline") < row.index("${ttk}")
    assert ".ovtarget .ovtname" in CSS and ".ovtarget .ovtline" in CSS


def test_the_struck_enemies_count_sits_next_to_the_target_name():
    row = JS.split("$(\"#ovtarget\").innerHTML=", 1)[1].split("\n", 1)[0]
    who = row.split('<span class="ovtwho">', 1)[1]
    assert who.index("ovtname") < who.index("${also}") < who.index("</span>${hp}")
    also = JS.split("const also=", 1)[1].split(":'';", 1)[0]
    assert also.index("ovalsocount") < also.index("ovalsonames")
    # the name is only as wide as its text and the others' names take what is left, so the
    # count follows the name instead of the HP readout at the far edge
    assert re.search(r"\.ovtarget \.ovtwho \{ flex: 1 1 0;", CSS)
    assert re.search(r"\.ovtarget \.ovtname \{ flex: 0 1 auto;", CSS)
    assert re.search(r"\.ovtarget \.ovalsocount \{ flex: none;", CSS)
    assert re.search(r"\.ovtarget \.ovalsonames \{ flex: 1 1 0; min-width: 0;", CSS)


def test_number_colour_defaults_are_light_and_agree_everywhere():
    assert "--ov-rate-text, #ffffff" in CSS and "--ov-total-text, #9bb1c1" in CSS
    assert "rate:'#ffffff',total:'#9bb1c1'" in APP                 # the settings pickers' defaults
    assert "\"Default (gold)\":{overlay_text_colors:{rate:\"#ffffff\",total:\"#9bb1c1\"" in APP
    assert "Reset numbers to black" not in APP
    # Blank (unset) text colours fall through to the stylesheet, never to black.
    assert "'#000000'" not in JS.split("const syncColors", 1)[1].split("\n", 1)[0]


def test_layout_setting_hooks_survive_the_restyle():
    for selector in ("#ov.ov-bars-gradient", "#ov.ov-bars-rounded", "#ov.ov-stripes", "#ov.ov-compact", ".ovrow-me",
                     ".ovrank-1", ".ovclass", ".ovcicon", "#ov.ov-scroll-names", "#ov.ov-outline", "#ov.ov-cycle",
                     "#ov.ov-halo", "#ov.ov-retro", "#ov.ov-ac-blend", "#ov.ov-party", "#ov.ov-locked", "#ov.ov-resizable",
                     ".ovgraph", ".ovpspark", ".ovskills", ".ovhpbar", ".ovttkbar", ".ovdummy", ".ovevents", ".ovfps",
                     "#ovcapture", "#ovsplit", "#ovcopy", "#ovlock", "#ovhide", ".ovfoot", ".ovping", ".ovidentity",
                     ".ovcontribution", "--ov-width", "--ov-row-h", "--ov-font-scale", "--ov-hp-color", "--ov-ttk-color"):
        assert selector in CSS, selector


def test_rounded_bars_round_the_bar_not_the_open_skill_breakdown():
    # A 999px radius on the row turned an open row, which also holds the player's skill breakdown,
    # into a capsule that clipped the skill names and numbers at its sides: the row now rounds by
    # half the bar's height, and an open row keeps the plain row's bottom corners
    rule = re.search(r"#ov\.ov-bars-rounded \.ovrow, #ov\.ov-bars-rounded \.ovbar i \{ border-radius: ([^;]+); \}", CSS)
    assert rule and rule.group(1) == "calc(var(--ov-row-h, 22px) / 2)"
    assert "#ov.ov-bars-rounded .ovrow-open { border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; }" in CSS
    assert "expanded.has(key)?' ovrow-open':''" in JS                 # re-applied on every render
    assert 'row.classList.toggle("ovrow-open",!panel.hidden);' in JS   # and on the click that opens or closes it
