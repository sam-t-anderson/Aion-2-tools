"""Settings → Overlay beyond its plain switches: the hotkeys (a row per action, keys pressed into it, saved
together and refused when two actions share keys), the Hidden Cube radar (its notes name each learn step's
key, its buttons ask the radar, its line says how it is doing), the in-game RTSS line, the streaming link,
the number colours' reset, the look presets and the class colour palettes. Each test puts back what it
saved, since the tests share one running app."""
import json
import re

from aion2calc.app import hotkeys

from apphelpers import open_settings, posted, put_back


def hotkey(page, action):
    return page.locator(f'.hotkey-input[data-action="{action}"]')


def test_every_hotkey_action_has_its_row_and_the_radars_steps_start_on_ctrl_1_to_4(app_page, app_url):
    open_settings(app_page, app_url, "overlay")
    rows = app_page.eval_on_selector_all("#hotkey-rows .hotkey-input",
                                         "fields => fields.map(f => [f.dataset.action, f.previousElementSibling.textContent, f.value])")
    assert [(action, label) for action, label, _ in rows] == list(hotkeys.ACTIONS.items())
    keys = {action: key for action, _, key in rows}
    assert {action: keys[action] for action in hotkeys.RADAR_DEFAULTS} == hotkeys.RADAR_DEFAULTS
    assert not [action for action, key in keys.items() if key and action not in hotkeys.RADAR_DEFAULTS]   # none by default


def test_hotkeys_are_pressed_in_saved_together_and_refused_when_two_actions_share_keys(app_page, app_url):
    page = app_page
    open_settings(page, app_url, "overlay")
    hotkey(page, "toggle_meter").click()
    page.keyboard.press("Control+Shift+M")
    page.keyboard.press("Shift")                                                 # a modifier alone is not a hotkey
    assert hotkey(page, "toggle_meter").input_value() == "Ctrl+Shift+M"
    hotkey(page, "clear_meter").click()
    page.keyboard.press("Control+Shift+M")
    sent = []
    page.on("request", lambda r: sent.append(r) if r.method == "POST" and r.url.endswith("/api/ui") else None)
    page.click("#hotkeys-save")
    assert page.locator("#hotkeys-msg").inner_text() == "Ctrl+Shift+M is bound to two actions; give each action its own keys."
    assert not sent
    page.locator('.hotkey-clear[data-action="clear_meter"]').click()
    page.locator('.hotkey-clear[data-action="radar_learn_cube"]').click()        # a learn step can be left without keys
    hotkey(page, "open_app").click()
    page.keyboard.press("F8")
    try:
        assert posted(page, lambda: page.click("#hotkeys-save")) == {"hotkeys": {
            "toggle_meter": "Ctrl+Shift+M", "open_app": "F8", "radar_learn_background": "Ctrl+1", "radar_learn_cube": "",
            "radar_learn_cube_behind": "Ctrl+3", "radar_learn_other": "Ctrl+4"}}
        page.wait_for_function("document.querySelector('#hotkeys-msg').textContent === 'Saved'")
        open_settings(page, app_url, "overlay")
        assert [hotkey(page, a).input_value() for a in ("toggle_meter", "open_app", "clear_meter", "radar_learn_cube",
                                                         "radar_learn_cube_behind")] == ["Ctrl+Shift+M", "F8", "", "", "Ctrl+3"]
    finally:
        put_back(page, {"hotkeys": {}})


def radar_notes(page) -> list[str]:
    """Each learn step as the radar's notes put it: the three numbered steps, then the "not a cube" one."""
    row = page.locator(".setrow", has=page.locator("#radar-enabled"))
    return row.locator("ol > li").all_inner_texts() + [row.locator("ol + p").inner_text()]


def test_the_radar_notes_name_each_learn_step_by_the_key_that_takes_it(app_page, app_url):
    page = app_page
    open_settings(page, app_url, "overlay")
    steps = radar_notes(page)
    assert [step.split(" ", 1)[0] for step in steps] == ["Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4"]
    assert steps[0].startswith("Ctrl+1 where no cube or feather can be heard")
    assert steps[3].startswith("Ctrl+4 while a sound the radar takes for a cube plays")
    row = page.locator(".setrow", has=page.locator("#radar-enabled")).inner_text()
    for words in ("turn 3D audio on", "stereo cannot tell ahead from behind", "nothing is recorded or uploaded",
                  "The radar is its own small overlay window"):
        assert words in row, words
    try:
        put_back(page, {"hotkeys": {"radar_learn_background": "", "radar_learn_cube": "F7"}})
        open_settings(page, app_url, "overlay")
        steps = radar_notes(page)
        assert steps[0].startswith("Button 1 where no cube")                     # no keys: its button does it
        assert steps[1].startswith("F7 facing a Hidden Cube") and steps[2].startswith("Ctrl+3 ")
    finally:
        put_back(page, {"hotkeys": {}})


RADAR = {"supported": True, "setting": True, "enabled": True, "listening": True, "heard": False, "device": "Speakers",
         "channels": 2, "ready": True, "learning": None, "last_learn": None, "error": None,
         "model": {"cubes": 2, "ahead": 1, "behind": 1, "backgrounds": 1, "others": 0, "front_back": "learned", "notes": True},
         "samples": [{"id": "s1", "kind": "cube", "facing": "ahead", "level_db": 0, "notes": True, "at": "2026-10-20T20:00:00"},
                     {"id": "s2", "kind": "background", "at": "2026-10-20T19:59:00"}]}


def test_the_radar_buttons_ask_the_radar_and_its_line_says_how_it_is(app_page, app_url):
    page = app_page
    state, sent = json.loads(json.dumps(RADAR)), []

    def radar(route):
        if route.request.method == "POST":
            sent.append(json.loads(route.request.post_data))
        route.fulfill(json=state)
    page.route("**/api/radar", radar)
    open_settings(page, app_url, "overlay")
    says = lambda text: page.wait_for_function("t => document.querySelector('#radar-status').textContent === t", arg=text)
    says("Learned 2 cube samples (1 facing it, 1 behind you), 1 background sample, with the jingle's notes. "
         "It tells ahead from behind. Listening to Speakers: no cube heard.")
    assert page.locator("#radar-samples li").all_inner_texts() == [
        "Cube, facing it · the loudest · with its notes · 2026-10-20 20:00:00 Forget", "Background · 2026-10-20 19:59:00 Forget"]
    state.update(error="no sound output device", listening=False)                     # why it does not listen
    says("Learned 2 cube samples (1 facing it, 1 behind you), 1 background sample, with the jingle's notes. "
         "It tells ahead from behind. Not listening: no sound output device.")
    state.update(error=None, listening=True, heard=True, direction="ahead", proximity=0.6, match=0.83)
    says("Learned 2 cube samples (1 facing it, 1 behind you), 1 background sample, with the jingle's notes. "
         "It tells ahead from behind. Hearing a cube ahead, close (match 83 %).")
    state.update(learning={"phase": "countdown", "kind": "cube", "seconds": 4.2})
    says("Learning the cube's sound in 5 s: switch to the game.")
    assert page.locator("#radar-cancel").is_visible()
    for button in ("#radar-learn-bg", "#radar-learn-cube", "#radar-learn-behind", "#radar-learn-other", "#radar-cancel"):
        page.click(button)
    page.locator('#radar-samples [data-id="s1"]').click()
    page.once("dialog", lambda d: d.dismiss())
    page.click("#radar-clear")                                                       # asked first: kept
    page.once("dialog", lambda d: d.accept())
    page.click("#radar-clear")
    for _ in range(30):                                                              # the last answer on its way
        if len(sent) == 7:
            break
        page.wait_for_timeout(100)
    assert sent == [{"action": "learn", "kind": "background"}, {"action": "learn", "kind": "cube"},
                    {"action": "learn", "kind": "cube", "facing": "behind"}, {"action": "learn", "kind": "other"},
                    {"action": "cancel"}, {"action": "forget", "sample": "s1"}, {"action": "clear"}]
    state.clear()
    state.update(supported=False)
    says("The radar listens to Windows' sound output; it runs on Windows only.")


def answering(answer):
    """A route handler that answers with this JSON (Playwright passes the request to a second parameter)."""
    return lambda route: route.fulfill(json=answer)


def test_the_in_game_rtss_line_says_what_rtss_is_doing(app_page, app_url):
    page = app_page
    open_settings(page, app_url, "overlay")                                          # this computer: not Windows
    page.wait_for_function("document.querySelector('#rtss-status').textContent === 'RTSS output is available on Windows only.'")
    assert "Nothing is injected into or loaded by the game" in page.locator(".setrow", has=page.locator("#rtss-enabled")).inner_text()
    for answer, line in (({"supported": True, "enabled": False}, "Off."),
                         ({"supported": True, "enabled": True, "connected": True, "slot": 2, "version": "2.20", "updates": 17},
                          "Drawing in RTSS OSD slot 2 (shared memory v2.20, 17 updates)."),
                         ({"supported": True, "enabled": True, "connected": False, "error": "RTSS is not running"}, "RTSS is not running"),
                         ({"supported": True, "enabled": True, "connected": False}, "Waiting for RTSS…")):
        page.unroute("**/api/rtss")
        page.route("**/api/rtss", answering(answer))
        open_settings(page, app_url, "overlay")
        page.wait_for_function("t => document.querySelector('#rtss-status').textContent === t", arg=line)


def test_the_streaming_link_is_the_apps_overlay_and_copies_in_a_click(app_page, app_url):
    page = app_page
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    open_settings(page, app_url, "overlay")
    link = page.locator("#ov-stream-url").input_value()
    assert link == app_url + "overlay"
    page.click("#ov-stream-copy")
    page.wait_for_function("document.querySelector('#ov-stream-msg').textContent === 'Copied — paste into an OBS Browser Source.'")
    assert page.evaluate("navigator.clipboard.readText()") == link
    row = page.locator(".setrow", has=page.locator("#ov-stream-url")).inner_text()
    assert "Browser Source" in row and "whole screen" in row and "will not show the overlay" in row


def test_reset_number_colours_puts_back_the_light_defaults(app_page, app_url):
    page = app_page
    open_settings(page, app_url, "overlay")
    colour = lambda element: page.locator(f"#ov-{element}-color").input_value()
    choose = lambda element, value: page.locator(f"#ov-{element}-color").evaluate(
        "(e, v) => { e.value = v; e.dispatchEvent(new Event('change', {bubbles: true})); }", value)
    assert (colour("rate"), colour("total")) == ("#ffffff", "#9bb1c1")                  # nothing chosen yet
    try:
        posted(page, lambda: choose("rate", "#000000"))
        dark = posted(page, lambda: choose("total", "#101010"))
        assert (dark["overlay_text_colors"]["rate"], dark["overlay_text_colors"]["total"]) == ("#000000", "#101010")
        reset = posted(page, lambda: page.click("#ov-color-reset"))["overlay_text_colors"]
        assert (reset["rate"], reset["total"]) == ("#ffffff", "#9bb1c1")
        assert {k: v for k, v in reset.items() if k not in ("rate", "total")} == \
               {k: v for k, v in dark["overlay_text_colors"].items() if k not in ("rate", "total")}   # the rest as chosen
    finally:
        put_back(page, {"overlay_text_colors": {}})


def test_each_look_preset_says_what_it_is_and_applying_one_saves_its_look(app_page, app_url):
    page = app_page
    open_settings(page, app_url, "overlay")
    presets = page.eval_on_selector_all('#ov-preset optgroup[label="Starter presets"] option', "os => os.map(o => o.value)")
    assert presets[0] == "b::Default (gold)" and {"b::Crimson", "b::Emerald", "b::Azure", "b::Amethyst", "b::Rose"} <= set(presets)
    said = {}
    for preset in presets:
        page.select_option("#ov-preset", preset)
        said[preset] = page.locator("#ov-preset-msg").inner_text()
    assert all(said.values()) and len(set(said.values())) == len(presets), said        # each its own description
    assert said["b::Default (gold)"].startswith("The classic look")
    before, look = page.evaluate("() => api('/api/ui')"), {}
    page.select_option("#ov-preset", "b::Default (gold)")
    try:
        look = posted(page, lambda: page.click("#ov-preset-apply"))
        assert look["overlay_text_colors"]["rate"] == "#ffffff" and look["overlay_text_colors"]["total"] == "#9bb1c1"
        page.wait_for_function("document.querySelector('#ov-preset-msg') && document.querySelector('#ov-preset-msg').textContent === ''")
        assert page.locator("#ov-rate-color").input_value() == "#ffffff"
        assert page.get_by_text("Preset applied").count() == 1
    finally:
        put_back(page, {key: before.get(key, {} if isinstance(value, dict) else value) for key, value in look.items()})


def test_a_class_colour_palette_sets_all_eight_classes_and_default_puts_them_back(app_page, app_url):
    page = app_page
    open_settings(page, app_url, "appearance")
    box = page.locator("#class-colors")
    palettes = box.locator("[data-palette] option").all_inner_texts()
    assert palettes[:3] == ["Choose a palette…", "Default (class colours)", "Colourblind-friendly"]
    colours = lambda: dict(box.locator("[data-color]").evaluate_all("es => es.map(e => [e.dataset.color, e.value])"))
    defaults = colours()
    assert len(defaults) == 8 and all(re.fullmatch(r"#[0-9a-f]{6}", v) for v in defaults.values())
    try:
        box.locator("[data-palette]").select_option("Colourblind-friendly")
        saved = posted(page, lambda: box.locator("[data-apply-palette]").click())["combat_colors"]
        assert saved == {"enabled": True, "colors": colours()} and colours()["sorcerer"] == "#56b4e9"
        box.locator("[data-palette]").select_option("Default (class colours)")
        assert posted(page, lambda: box.locator("[data-apply-palette]").click())["combat_colors"]["colors"] == defaults
    finally:
        put_back(page, {"combat_colors": {}})
