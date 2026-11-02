"""The overlay's player panel, background modes and row effects (0.2.364). A click on a player's name (or Enter on
it) opens that player under the rows: totals, DPS, contribution, combat time, hits and the special-hit shares as
tiles, their top skills with an icon and a bar each, and the buffs on them with their uptime, which the page asks
``/api/meter/player`` for. The close button or a second click puts the panel away, and the click never expands
the row's skill breakdown. With the background set to *none* the card is clear and the rows keep a pill of their
own; set to *top* the card's panel ends where the rows begin, measured after each render. A row effect marks the
top row or your own row (your own wins when both are yours) and holds still with reduced motion and in
performance mode."""
from urllib.parse import parse_qs, urlparse

PARTY = [("Seraphel", "sorcerer", 23400), ("Nyxara", "ranger", 15600), ("Velmira", "cleric", 6700)]
BUFFS = {"0": [{"skill_id": 18300000, "skill": "Mantra of Flame", "seconds": 75.0, "uptime_pct": 100.0, "applications": 1, "self": True},
               {"skill_id": 17200000, "skill": "Protection", "seconds": 60.0, "uptime_pct": 80.0, "applications": 6, "self": False}]}


def fight(local_name="Nyxara"):
    """A running boss fight of three players, each with their shares and two skills; ``local_name`` is you."""
    rows = []
    for i, (name, cls, dps) in enumerate(PARTY):
        rows.append({"id": str(i), "key": str(i), "name": name, "class": cls, "dps": dps, "damage": dps * 75, "hps": 0, "healing": 0,
                     "dtps": 0, "hits": 120 - 20 * i, "share": [0.51, 0.34, 0.15][i], "crit": 0.333, "back": 0.5, "front": 0.5,
                     "parry": 0.05, "double": 0.1, "perfect": 0.2, "multi": 0, "incoming": {"damage": 4000, "hits": 9, "parries": 4},
                     "skills": [{"skill_id": 1010003, "skill": "Flame Bolt", "damage": dps * 45, "hits": 60, "share": 0.6,
                                 "crit": 0.4, "back": 0.5, "parry": 0.0},
                                {"skill_id": 1020002, "skill": "Frost Spear", "damage": dps * 30, "hits": 40, "share": 0.4,
                                 "crit": 0.25, "back": None, "parry": None}]})
    return {"running": True, "combine_pets": True, "snapshot": {
        "boss": "Atiel", "duration": 75.0, "recorded_duration": 75.0, "paused": False, "battle_over": False, "boss_alive": True,
        "identity_status": {"self_identified": True, "unnamed_actors": 0, "linked_pets": 0, "local_id": 1,
                            "local_name": local_name, "local_combat_power": 123456},
        "current_target": {"name": "Atiel", "mob_code": 2340601, "hp_pct": 0.47, "ttk": 66.0, "ttk_fraction": 0.53,
                           "damage": 3_420_000, "contributors": [{"name": name, "dps": dps} for name, _, dps in PARTY]},
        "players": rows}}


def open_overlay(page, app_url: str, meter: dict, **look) -> None:
    """The overlay at 340 px over the meter's answer ``meter`` with these overlay settings; called again on the
    same page it reloads the overlay with the new settings."""
    if not hasattr(page, "ov_look"):
        page.ov_look, page.ov_meter = {}, {}
        page.route("**/api/ui", lambda route: route.continue_() if route.request.method != "GET" else
                   route.fulfill(json={**route.fetch().json(), "overlay_width": 340, **page.ov_look}))
        page.route("**/api/meter?view=latest", lambda route: route.fulfill(json=page.ov_meter))
        page.route("**/api/meter/player?*", lambda route: route.fulfill(json={"player": {
            "key": key, "buffs": BUFFS.get(key, []), "active_seconds": 61, "duration": 75.0}}
            if (key := parse_qs(urlparse(route.request.url).query).get("key", [""])[0]) else {"player": None}))
    page.ov_look, page.ov_meter = look, meter
    page.goto("about:blank")
    page.goto(app_url + "overlay", wait_until="load")
    page.wait_for_function("!document.querySelector('#ovtarget').hidden && document.querySelectorAll('#ovcontent .ovrow').length === 3")
    page.wait_for_function("w => Math.abs(document.querySelector('.ovcard').getBoundingClientRect().width - w) < 1",
                           arg=look.get("overlay_width", 340))


def panel_rows(page, section: str) -> list[list[str]]:
    """Each row of the panel's section (*Top skills* or *Buff uptime*): the icon's initials, the name, the value."""
    return page.evaluate("""section => {
        const heads = [...document.querySelectorAll('#ovdetail .ovdsec')];
        const head = heads.find(h => h.textContent === section);
        if (!head) return null;
        return [...head.nextElementSibling.querySelectorAll('.ovdsk')].map(r => [
            r.querySelector('.ovdicon em').textContent, r.querySelector('.ovdskname').textContent, r.querySelector('.ovdskval').textContent]);
    }""", section)


def test_a_click_on_a_name_opens_that_players_panel_with_tiles_skills_and_buffs(app_page, app_url):
    page = app_page
    open_overlay(page, app_url, fight())
    assert page.locator("#ovdetail").is_hidden()
    assert page.locator('.ovname[data-detail="0"]').get_attribute("role") == "button"
    page.click('.ovname[data-detail="0"]')
    page.wait_for_function("!document.querySelector('#ovdetail').hidden && document.querySelectorAll('#ovdetail .ovdsec').length === 2"
                           " && document.querySelectorAll('#ovdetail .ovdlist')[1].querySelectorAll('.ovdsk').length === 2")
    row = page.locator('.ovrow[data-exk="0"]')
    assert "ovrow-detail" in row.get_attribute("class") and "ovrow-open" not in row.get_attribute("class")   # the panel, not the breakdown
    assert page.locator("#ovdetail .ovdname").inner_text() == "Seraphel"
    assert page.locator("#ovdetail .ovdhead .ovdsub").inner_text() == "Sorcerer"              # no combat power known for them
    assert page.locator("#ovdetail .ovdline").inner_text() == "Target: Atiel · 1m 15s in combat"
    tiles = page.eval_on_selector_all("#ovdetail .ovdtile", "ts => ts.map(t => [t.querySelector('span').textContent, t.querySelector('b').textContent])")
    assert [label for label, _ in tiles] == ["Total damage", "DPS", "Contribution", "Combat time", "Hits", "Parry", "Crit", "Front",
                                             "Back", "Perfect", "Double", "Parried in"]
    values = dict(tiles)
    assert (values["Combat time"], values["Hits"], values["Crit"], values["Parry"], values["Contribution"], values["Parried in"]) == (
        "1m 15s", "120", "33%", "5%", "51%", "4")
    assert (values["DPS"], values["Total damage"]) == ("23.40K/s", "1.75M")
    assert page.locator('#ovdetail .ovdtile[title^="Fight time; this player dealt damage in 1m 01s"]').count() == 1
    skills = panel_rows(page, "Top skills")
    assert [(initials, name) for initials, name, _ in skills] == [("FB", "Flame Bolt"), ("FS", "Frost Spear")]
    assert skills[0][2].endswith("· 60% · 60× · 40%") and skills[1][2].endswith("· 40% · 40× · 25%")
    widths = page.evaluate("[...document.querySelector('#ovdetail .ovdlist').querySelectorAll('.ovdskbar i')].map(b => b.style.width)")
    assert widths == ["100%", "67%"]                                                           # bars against the top skill
    assert panel_rows(page, "Buff uptime") == [["Mo", "Mantra of Flame", "100% · 1m 15s"], ["P", "Protection", "80% · 1m 00s"]]
    assert page.locator('#ovdetail .ovdsk[title*="applied 1×, by this player"]').count() == 1
    page.click("#ovdetail [data-close]")
    page.wait_for_function("document.querySelector('#ovdetail').hidden")
    assert "ovrow-detail" not in page.locator('.ovrow[data-exk="0"]').get_attribute("class")
    # Enter on a focused name opens it too; your own panel says so and carries your combat power
    page.focus('.ovname[data-detail="1"]')
    page.keyboard.press("Enter")
    page.wait_for_function("!document.querySelector('#ovdetail').hidden && document.querySelectorAll('#ovdetail .ovdlist').length === 2")
    assert page.locator("#ovdetail .ovdname").inner_text() == "Nyxara"
    assert page.locator("#ovdetail .ovdhead .ovdsub").inner_text() == "Ranger · CP 123.46K"
    assert page.locator("#ovdetail .ovdline").inner_text() == "Target: Atiel · 1m 15s in combat · you"
    page.wait_for_function("document.querySelectorAll('#ovdetail .ovdlist')[1].textContent === 'No buff records in this fight yet.'")
    page.click('.ovname[data-detail="1"]')                                                   # a second click closes it
    page.wait_for_function("document.querySelector('#ovdetail').hidden")


def test_the_background_can_be_the_whole_card_the_top_portion_or_none(app_page, app_url):
    page = app_page
    clear = "rgba(0, 0, 0, 0)"
    styles = "() => { const s = sel => getComputedStyle(document.querySelector(sel)); return [s('.ovcard').backgroundColor, s('.ovrow').backgroundColor, s('.ovhd').textShadow]; }"
    open_overlay(page, app_url, fight(), overlay_bg_mode="none")
    assert page.evaluate("[...document.querySelector('#ov').classList].filter(c => c.startsWith('ov-bg-'))") == ["ov-bg-none"]
    card, row, shadow = page.evaluate(styles)
    assert card == clear and row != clear and shadow != "none"                              # rows keep their pill, text its shadow
    assert page.evaluate("getComputedStyle(document.querySelector('#ovbg')).display") == "none"
    open_overlay(page, app_url, fight(), overlay_bg_mode="top")
    assert page.evaluate("[...document.querySelector('#ov').classList].filter(c => c.startsWith('ov-bg-'))") == ["ov-bg-top"]
    page.wait_for_function("parseFloat(document.querySelector('.ovcard').style.getPropertyValue('--ov-top-h')) > 40")
    top = page.evaluate("""() => { const card = document.querySelector('.ovcard'), rows = document.querySelector('#ovcontent');
        return [parseFloat(card.style.getPropertyValue('--ov-top-h')), rows.getBoundingClientRect().top - card.getBoundingClientRect().top,
                parseFloat(getComputedStyle(card, '::before').height)]; }""")
    assert abs(top[0] - top[1]) <= 1 and abs(top[2] - top[0]) <= 1, top                       # the panel ends where the rows begin
    card, row, _ = page.evaluate(styles)
    assert card == clear and row != clear
    open_overlay(page, app_url, fight())
    assert page.evaluate("[...document.querySelector('#ov').classList].filter(c => c.startsWith('ov-bg-'))") == []
    card, _, _ = page.evaluate(styles)
    assert card != clear and page.evaluate("document.querySelector('.ovcard').style.getPropertyValue('--ov-top-h')") == ""


def test_a_row_effect_marks_the_top_row_or_your_own_and_holds_still_when_motion_is_reduced(app_page, app_url):
    page = app_page
    cosmetics = "() => [...document.querySelectorAll('#ovcontent .ovrow')].map(r => [...r.classList].filter(c => c.startsWith('ov-cos-')).join(' '))"
    moving = """() => { const gold = document.querySelector('.ov-cos-gold'), name = document.querySelector('.ov-cos-rainbow .ovnametext');
        return [getComputedStyle(gold, '::after').animationName, getComputedStyle(gold.querySelector('.ovname'), '::before').content,
                getComputedStyle(name).animationName]; }"""
    open_overlay(page, app_url, fight("Nyxara"), overlay_top_cosmetic="gold", overlay_me_cosmetic="rainbow")
    assert page.evaluate(cosmetics) == ["ov-cos-gold", "ov-cos-rainbow", ""]                 # the top row's, yours, nobody else's
    frame, diamond, rainbow = page.evaluate(moving)
    assert frame != "none" and diamond == '"◆"' and rainbow != "none"
    page.emulate_media(reduced_motion="reduce")
    frame, _, rainbow = page.evaluate(moving)
    assert frame == "none" and rainbow == "none"
    page.emulate_media(reduced_motion="no-preference")
    open_overlay(page, app_url, fight("Seraphel"), overlay_top_cosmetic="gold", overlay_me_cosmetic="rainbow", performance_mode=True)
    assert page.evaluate(cosmetics) == ["ov-cos-rainbow", "", ""]                            # your own effect wins the top row
    assert page.evaluate("getComputedStyle(document.querySelector('.ov-cos-rainbow .ovnametext')).animationName") == "none"
    open_overlay(page, app_url, fight("Seraphel"))
    assert page.evaluate(cosmetics) == ["", "", ""]


def test_a_poll_that_only_moves_the_numbers_keeps_the_rows_and_their_effect(app_page, app_url):
    """0.2.368: every poll of a live fight used to rebuild the rows, which restarted a row's animated effect each
    time; the rows stay when only the numbers changed, and the numbers are written into them."""
    page = app_page
    open_overlay(page, app_url, fight("Nyxara"), overlay_top_cosmetic="gold", overlay_me_cosmetic="rainbow", performance_mode=True)
    page.evaluate("[...document.querySelectorAll('#ovcontent .ovrow')].forEach((r, i) => (r.dataset.kept = String(i)))")
    moved = fight("Nyxara")
    for i, p in enumerate(moved["snapshot"]["players"]):
        p["dps"] += 1000 * (i + 1)
        p["damage"] = p["dps"] * 80
    moved["snapshot"]["duration"] = moved["snapshot"]["recorded_duration"] = 80.0
    page.ov_meter = moved
    page.wait_for_function("document.querySelector('#ovcontent .ovrate').getAttribute('data-target') === '24400'")
    assert page.evaluate("[...document.querySelectorAll('#ovcontent .ovrow')].map(r => r.dataset.kept)") == ["0", "1", "2"]
    assert page.evaluate("[...document.querySelectorAll('#ovcontent .ovrow')].map(r => [...r.classList].filter(c => c.startsWith('ov-cos-')).join(' '))") == ["ov-cos-gold", "ov-cos-rainbow", ""]
    assert page.evaluate("document.querySelector('#ovcontent .ovrow .ovbar .sub').textContent").startswith("1.95M")
    # a new player in the list is a structural change: the rows are drawn again
    joined = fight("Nyxara")
    joined["snapshot"]["players"].append({**joined["snapshot"]["players"][0], "id": "9", "key": "9", "name": "Lysithea", "class": "templar", "dps": 100, "damage": 7500})
    page.ov_meter = joined
    page.wait_for_function("document.querySelectorAll('#ovcontent .ovrow').length === 4")
    assert page.evaluate("document.querySelector('#ovcontent .ovrow').dataset.kept") is None


def test_a_click_anywhere_on_a_row_opens_the_players_panel(app_page, app_url):
    """The row's bar used to toggle the older per-skill breakdown inside the row (0.2.364: only the name opened the
    panel); the panel is the breakdown now, in every background mode."""
    page = app_page
    open_overlay(page, app_url, fight(), overlay_bg_mode="top")
    page.locator("#ovcontent .ovrow").nth(1).locator(".ovbar").click()
    page.wait_for_function("!document.querySelector('#ovdetail').hidden")
    assert page.locator("#ovdetail .ovdname").inner_text() == "Nyxara"
    assert page.locator("#ovcontent .ovrow.ovrow-open").count() == 0            # no in-row breakdown opened
    page.locator("#ovcontent .ovrow").nth(1).locator(".ovbar").click()           # the same row again closes it
    page.wait_for_function("document.querySelector('#ovdetail').hidden")


def test_the_transparent_modes_tell_the_host_which_rectangles_the_page_draws(app_page, app_url):
    """In the native window the host paints an opaque card-coloured surface, so the page's clear card alone
    showed no change (0.2.364 to 0.2.367). In the *top* and *none* modes the page now reports the rectangles it
    draws (the header panel, each row, the pieces under the rows, in device px) and the host clips its window to
    them; the card mode reports null, the whole window."""
    page = app_page
    page.add_init_script("""window.__shapes = []; window.pywebview = { platform: "edgechromium",
        api: new Proxy({}, { get: (t, name) => (...args) => { if (name === "set_window_shape") window.__shapes.push(args[0]); return Promise.resolve(); } }) };""")
    open_overlay(page, app_url, fight(), overlay_bg_mode="top")
    page.wait_for_function("window.__shapes.length && window.__shapes[window.__shapes.length - 1] !== null")
    rects = page.evaluate("window.__shapes[window.__shapes.length - 1]")
    rows = page.evaluate("[...document.querySelectorAll('#ovcontent .ovrow')].map(r => { const b = r.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; })")
    top_h = page.evaluate("parseFloat(document.querySelector('.ovcard').style.getPropertyValue('--ov-top-h'))")
    assert rects[0][1] == 0 and abs(rects[0][3] - top_h) < 1                     # the header panel, from the card's top
    for left, top, right, bottom in rows:                                        # every row, with a little room around it
        assert any(l <= left and t <= top and r >= right and b >= bottom for l, t, r, b in rects[1:])
    assert all(r[3] <= top_h + 1 or r[1] >= top_h - 4 for r in rects[1:])        # nothing inside the panel reported again (rows get 3 px of room)
    open_overlay(page, app_url, fight(), overlay_bg_mode="none")
    page.wait_for_function("window.__shapes.length && Array.isArray(window.__shapes[window.__shapes.length - 1]) && window.__shapes[window.__shapes.length - 1].length > 5")
    rects = page.evaluate("window.__shapes[window.__shapes.length - 1]")
    head = page.evaluate("(() => { const b = document.querySelector('.ovhd').getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; })()")
    assert any(l <= head[0] and t <= head[1] and r >= head[2] and b >= head[3] for l, t, r, b in rects)   # the header on its own
    open_overlay(page, app_url, fight())
    page.wait_for_function("window.__shapes[window.__shapes.length - 1] === null")


def test_the_window_shape_is_sent_once_the_native_bridge_is_up(app_page, app_url):
    """The first render usually comes before pywebview injects its bridge: until 0.2.369 the page then remembered
    the see-through shape as sent and never sent it again, so the native window kept its whole card in the *top*
    and *none* modes however the setting read. Once the bridge is up the shape is measured and sent afresh."""
    page = app_page
    open_overlay(page, app_url, fight(), overlay_bg_mode="top")                  # no bridge: nothing can be sent yet
    page.wait_for_function("document.querySelector('.ovcard').style.getPropertyValue('--ov-top-h') !== ''")
    page.evaluate("""() => { window.__shapes = []; window.pywebview = { platform: "edgechromium",
        api: new Proxy({}, { get: (t, name) => (...args) => { if (name === "set_window_shape") window.__shapes.push(args[0]); return Promise.resolve(); } }) };
        window.dispatchEvent(new Event("pywebviewready")); }""")
    page.wait_for_function("window.__shapes.length && Array.isArray(window.__shapes[window.__shapes.length - 1])")
    rects = page.evaluate("window.__shapes[window.__shapes.length - 1]")
    assert len(rects) > 3 and rects[0][1] == 0                                   # the panel from the top, then the rows


COUNTERS = {"odyle": {"regular": 1200, "bonus": 300}, "shugo_keys": {"regular": 12, "bonus": 4},
            "nightmare_tickets": {"regular": 9, "bonus": 2}}


def counted():
    """The fight with the three counters the game sends in its snapshot."""
    meter = fight()
    return {**meter, "snapshot": {**meter["snapshot"], **COUNTERS}}


def test_the_counter_lines_share_one_row_as_icons_when_the_see_through_overlay_is_narrow(app_page, app_url):
    """In the see-through modes the Odyle, Shugo and Nightmare lines share one row: their full text where the card
    is wide enough for all three, an icon with the count each where it is not (0.2.369); the card mode stacks
    them at the bottom as before."""
    page = app_page
    lines = "['#ovodyle', '#ovshugo', '#ovnightmare'].map(s => document.querySelector(s).getBoundingClientRect())"
    open_overlay(page, app_url, counted(), overlay_bg_mode="top")          # 340 px: the full lines do not fit
    page.wait_for_function("document.querySelector('#ov').classList.contains('ov-lines-icons')")
    boxes = page.evaluate(lines)
    assert max(b["top"] for b in boxes) - min(b["top"] for b in boxes) < 2             # one row
    assert page.locator("#ovodyle .ovoltext").is_hidden() and page.locator("#ovodyle .ovolshort").inner_text() == "1,500"
    assert page.locator("#ovnightmare .ovolshort").inner_text() == "11"
    assert page.locator("#ovodyle").get_attribute("title").startswith("Your Odyle Energy")   # the words live in the title
    top_h = page.evaluate("parseFloat(document.querySelector('.ovcard').style.getPropertyValue('--ov-top-h'))")
    assert all(b["bottom"] <= top_h + 1 for b in boxes)                                   # inside the top panel
    open_overlay(page, app_url, counted(), overlay_bg_mode="none", overlay_width=760)   # wide: the full lines, one row
    page.wait_for_function("document.querySelector('#ov').classList.contains('ov-lines-row') && !document.querySelector('#ov').classList.contains('ov-lines-icons')")
    boxes = page.evaluate(lines)
    assert max(b["top"] for b in boxes) - min(b["top"] for b in boxes) < 2
    assert page.locator("#ovodyle .ovoltext").inner_text() == "Odyle Energy 1,500 (1,200 + 300 bonus)"
    open_overlay(page, app_url, counted())                                   # the card: stacked, full text
    page.wait_for_function("!document.querySelector('#ovodyle').hidden")
    assert page.evaluate("[...document.querySelector('#ov').classList].filter(c => c.startsWith('ov-lines'))") == []
    boxes = page.evaluate(lines)
    assert boxes[0]["top"] < boxes[1]["top"] < boxes[2]["top"]

