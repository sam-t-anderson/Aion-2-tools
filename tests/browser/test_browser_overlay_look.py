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
        return [parseFloat(card.style.getPropertyValue('--ov-top-h')),
                rows.getBoundingClientRect().top - card.getBoundingClientRect().top - parseFloat(getComputedStyle(rows).marginTop),
                parseFloat(getComputedStyle(card, '::before').height)]; }""")
    assert abs(top[0] - top[1]) <= 1 and abs(top[2] - top[0]) <= 1, top                       # the panel ends at the gap above the rows
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
    them. The card mode reports the card's own outline, its corners rounded (0.2.370); the party window, square,
    reports null, the whole window."""
    page = app_page
    page.add_init_script("""window.__shapes = []; window.pywebview = { platform: "edgechromium",
        api: new Proxy({}, { get: (t, name) => (...args) => { if (name === "set_window_shape") window.__shapes.push(args[0]); return Promise.resolve(); } }) };""")
    open_overlay(page, app_url, fight(), overlay_bg_mode="top")
    page.wait_for_function("window.__shapes.length && window.__shapes[window.__shapes.length - 1] !== null")
    rects = page.evaluate("window.__shapes[window.__shapes.length - 1]")
    rows = page.evaluate("[...document.querySelectorAll('#ovcontent .ovrow')].map(r => { const b = r.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; })")
    top_h = page.evaluate("parseFloat(document.querySelector('.ovcard').style.getPropertyValue('--ov-top-h'))")
    assert rects[0][1] == 0 and abs(rects[0][3] - top_h) < 1                     # the header panel, from the card's top
    for left, top, right, bottom in rows:                                        # every row, its outline (and corner) exactly
        assert any(r[0] <= left and r[1] <= top and r[2] >= right and r[3] >= bottom for r in rects[1:])
    assert all(r[3] <= top_h + 1 or r[1] >= top_h - 4 for r in rects[1:])        # nothing inside the panel reported again (rows get 3 px of room)
    open_overlay(page, app_url, fight(), overlay_bg_mode="none")
    page.wait_for_function("window.__shapes.length && Array.isArray(window.__shapes[window.__shapes.length - 1]) && window.__shapes[window.__shapes.length - 1].length > 5")
    rects = page.evaluate("window.__shapes[window.__shapes.length - 1]")
    head = page.evaluate("(() => { const b = document.querySelector('.ovhd').getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; })()")
    assert any(r[0] <= head[0] and r[1] <= head[1] and r[2] >= head[2] and r[3] >= head[3] for r in rects)   # the toolbar on its own
    open_overlay(page, app_url, fight())                                      # the whole card: its own outline
    page.wait_for_function("(s => Array.isArray(s) && s.length === 1)(window.__shapes[window.__shapes.length - 1])")
    whole, dpr = page.evaluate("window.__shapes[window.__shapes.length - 1][0]"), page.evaluate("window.devicePixelRatio")
    card = page.evaluate("(() => { const b = document.querySelector('.ovcard').getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; })()")
    assert all(abs(whole[i] - card[i] * dpr) < 1 for i in range(4)) and whole[4] == round(12 * dpr), (whole, card)
    # the card changes size between renders (a resize drag sets its width): the outline follows it at once, even
    # with the meter's poll frozen by Lock, so no render comes to send it
    page.click("#ovlock")
    page.wait_for_timeout(200)                                                     # a poll already on its way lands
    page.evaluate("document.documentElement.style.setProperty('--ov-width', '300px')")
    page.wait_for_function("""dpr => { const s = window.__shapes[window.__shapes.length - 1], b = document.querySelector('.ovcard').getBoundingClientRect();
        return Array.isArray(s) && s.length === 1 && Math.abs(b.width - 300) < 1 && Math.abs(s[0][2] - b.right * dpr) < 1; }""",
                           arg=dpr, timeout=5000)
    page.goto(app_url + "overlay?view=party", wait_until="load")                # the party window: the whole window
    page.wait_for_function("window.__shapes.length && window.__shapes[window.__shapes.length - 1] === null")


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


def test_the_counter_lines_share_one_row_as_icons_when_the_overlay_is_narrow(app_page, app_url):
    """The Odyle, Shugo and Nightmare lines share one row: their full text where the card is wide enough for all
    three, an icon with the count each where it is not (0.2.369, the see-through modes; the whole card too since
    0.2.370, at its top, where it stacked them at the bottom before)."""
    page = app_page
    lines = "['#ovodyle', '#ovshugo', '#ovnightmare'].map(s => document.querySelector(s).getBoundingClientRect())"
    open_overlay(page, app_url, counted(), overlay_bg_mode="top")          # 340 px: the full lines do not fit
    page.wait_for_function("document.querySelector('#ov').classList.contains('ov-lines-icons')")
    boxes = page.evaluate(lines)
    assert max(b["top"] for b in boxes) - min(b["top"] for b in boxes) < 2             # one row
    # the regular count, then the bonus in brackets, as the game's windows (and NotMeter) write it (0.2.370)
    assert page.locator("#ovodyle .ovoltext").is_hidden() and page.locator("#ovodyle .ovolshort").inner_text() == "1,200(+300)"
    assert page.locator("#ovnightmare .ovolshort").inner_text() == "9(+2)" and page.locator("#ovshugo .ovolshort").inner_text() == "12(+4)"
    assert page.locator("#ovodyle").get_attribute("title").startswith("Your Odyle Energy")   # the words live in the title
    top_h = page.evaluate("parseFloat(document.querySelector('.ovcard').style.getPropertyValue('--ov-top-h'))")
    assert all(b["bottom"] <= top_h + 1 for b in boxes)                                   # inside the top panel
    open_overlay(page, app_url, counted(), overlay_bg_mode="none", overlay_width=760)   # wide: the full lines, one row
    page.wait_for_function("document.querySelector('#ov').classList.contains('ov-lines-row') && !document.querySelector('#ov').classList.contains('ov-lines-icons')")
    boxes = page.evaluate(lines)
    assert max(b["top"] for b in boxes) - min(b["top"] for b in boxes) < 2
    assert page.locator("#ovodyle .ovoltext").inner_text() == "Odyle Energy 1,500 (1,200 + 300 bonus)"
    open_overlay(page, app_url, counted())                                   # the whole card: the same row, at its top
    page.wait_for_function("document.querySelector('#ov').classList.contains('ov-lines-icons')")
    boxes = page.evaluate(lines)
    assert max(b["top"] for b in boxes) - min(b["top"] for b in boxes) < 2
    target = page.locator("#ovtarget").bounding_box()
    assert all(b["bottom"] <= target["y"] + 1 for b in boxes)                         # above the target card



def test_the_meter_is_laid_out_like_notmeter_in_every_background_mode(app_page, app_url):
    """The meter's compact layout after NotMeter's (0.2.370): a target card on top with the portrait, name, HP and
    bars inside it, the rows as pills with the rate in full digits, the share to a tenth and your combat power,
    and under them the fight clock with the party's total, the ping, and a toolbar of icons led by the metric chip;
    the pet grouping and the opacity slider wait behind the Options button. Top portion only and None lay it out
    first; the whole card takes the same layout with the card behind all of it, and the party window keeps the
    older look."""
    page = app_page
    open_overlay(page, app_url, fight(), overlay_bg_mode="top", overlay_dps_interpolate=False, overlay_show_enemy_hp=True)
    assert page.evaluate("document.querySelector('#ov').classList.contains('ov-nm')")
    rows = page.locator("#ovcontent .ovrow")
    page.wait_for_function("document.querySelector('#ovcontent .ovrate').textContent === '23,400'")
    assert [rows.nth(i).locator(".ovpct").inner_text() for i in range(3)] == ["51.2%", "34.1%", "14.7%"]
    assert rows.nth(0).locator(".sub").is_hidden()                                       # the total stays in the tooltip
    assert "ovrow-self" in rows.nth(1).get_attribute("class") and "ovrow-self" not in rows.nth(0).get_attribute("class")
    assert rows.nth(1).locator(".ovcp").inner_text() == "123.5K" and rows.nth(0).locator(".ovcp").count() == 0
    # the target card holds its bars; the whole card's separate bars stay out of the way
    assert page.locator("#ovtarget .ovtname").inner_text() == "Atiel" and page.locator("#ovtarget .ovhp").inner_text() == "47.0%"
    assert page.locator("#ovtarget .ovtbar-hp b").get_attribute("style") == "width:47.0%" and page.locator("#ovhpbar").is_hidden()
    assert page.locator("#ovtarget .ovtlabel").count() == 0
    # the clock under the rows, then the ping and the toolbar on a line of their own
    clock = page.locator("#ovclock")
    assert clock.locator(".ovclktime").inner_text() == "01:15" and clock.locator(".ovclkbar.on").count() == 1
    assert clock.locator(".ovclkparty").inner_text() == "Party DPS 45.70K"
    last_row = rows.nth(2).bounding_box()
    bar, ping = page.locator(".ovhd").bounding_box(), page.locator("#ovping").bounding_box()
    assert clock.bounding_box()["y"] >= last_row["y"] + last_row["height"] and bar["y"] > clock.bounding_box()["y"]
    assert abs(ping["y"] - bar["y"]) < 4 and ping["x"] < bar["x"]                         # the ping left, the toolbar right
    assert page.locator("#ovping").inner_text() == "—ms"                                  # no samples in this fight
    # the metric chip leads the toolbar and moves to the next metric on a click
    assert page.evaluate("document.querySelector('#ovmetrics').parentElement.classList.contains('ovhd')")
    visible = "[...document.querySelectorAll('#ovmetrics button')].filter(b => b.offsetWidth > 0).map(b => b.textContent)"
    assert page.evaluate(visible) == ["DPS"] and page.locator("#ovstatus").is_hidden()
    page.click("#ovmetrics button.on")
    page.wait_for_function(f"JSON.stringify({visible}) === JSON.stringify(['HPS'])")
    page.click("#ovmetrics button.on")
    page.click("#ovmetrics button.on")
    page.wait_for_function(f"JSON.stringify({visible}) === JSON.stringify(['DPS'])")
    # the options fold away behind the toolbar's Options button
    assert page.locator(".ovoptions").is_hidden() and page.locator("#ovop").is_hidden()
    page.click("#ovsettings")
    assert page.locator(".ovoptions").is_visible() and page.locator("#ovop").is_visible()
    assert page.locator("#ovsettings").get_attribute("aria-expanded") == "true"
    page.click("#ovsettings")
    assert page.locator("#ovop").is_hidden()
    # None: the same layout, the counters and the target card floating like the rest
    open_overlay(page, app_url, counted(), overlay_bg_mode="none", overlay_dps_interpolate=False)
    assert page.evaluate("document.querySelector('#ov').classList.contains('ov-nm')") and page.locator("#ovclock").is_visible()
    lines, target = page.locator("#ovlines").bounding_box(), page.locator("#ovtarget").bounding_box()
    assert lines["width"] < target["width"] and lines["y"] < target["y"]                   # the counters chip, above the card
    # the whole card: the same layout, the card behind all of it
    open_overlay(page, app_url, fight(), overlay_dps_interpolate=False)
    classes = page.evaluate("[...document.querySelector('#ov').classList]")
    assert "ov-nm" in classes and "ov-whole" in classes
    assert page.evaluate("getComputedStyle(document.querySelector('.ovcard')).backgroundColor") != "rgba(0, 0, 0, 0)"
    page.wait_for_function("document.querySelector('#ovcontent .ovrate').textContent === '23,400'")
    assert page.locator("#ovcontent .ovpct").count() == 3 and page.locator("#ovclock").is_visible() and page.locator("#ovsettings").is_visible()
    assert page.evaluate("document.querySelector('#ovmetrics').parentElement.classList.contains('ovhd')")
    assert page.locator("#ovtarget .ovtlabel").count() == 0 and page.locator("#ovtarget .ovtport").count() == 1
    card = page.locator(".ovcard").bounding_box()
    for piece in ("#ovtarget", "#ovcontent", "#ovclock", "#ovping", ".ovhd"):                # every piece inside it
        box = page.locator(piece).bounding_box()
        assert card["x"] < box["x"] and box["x"] + box["width"] < card["x"] + card["width"], piece
        assert card["y"] < box["y"] and box["y"] + box["height"] < card["y"] + card["height"], piece
    # the plan view has no metric: its chip leaves the toolbar
    page.click("#plan-tab")
    page.wait_for_function("document.querySelector('#ovmetrics').hidden")
    assert page.locator("#ovmetrics").is_hidden() and page.locator("#meter-tab").is_visible()
    # the party window keeps the older look
    page.goto(app_url + "overlay?view=party", wait_until="load")
    page.wait_for_function("document.querySelector('#ovcontent .ovpstat')")
    assert not page.evaluate("document.querySelector('#ov').classList.contains('ov-nm')")


def test_the_compact_layouts_window_outline_carries_each_pieces_corner(app_page, app_url):
    """In the compact layout every piece paints its own rounded background, so the shape sent to the Windows host
    is each piece's exact outline with its corner radius as a fifth number (device px): the window's corners are
    round where the pieces' are (0.2.370)."""
    page = app_page
    page.add_init_script("""window.__shapes = []; window.pywebview = { platform: "edgechromium",
        api: new Proxy({}, { get: (t, name) => (...args) => { if (name === "set_window_shape") window.__shapes.push(args[0]); return Promise.resolve(); } }) };""")
    open_overlay(page, app_url, fight(), overlay_bg_mode="none")
    page.wait_for_function("window.__shapes.length && Array.isArray(window.__shapes[window.__shapes.length - 1]) && window.__shapes[window.__shapes.length - 1].length > 5")
    rects = page.evaluate("window.__shapes[window.__shapes.length - 1]")
    dpr = page.evaluate("window.devicePixelRatio")
    rows = page.evaluate("[...document.querySelectorAll('#ovcontent .ovrow')].map(r => { const b = r.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; })")
    for row in rows:                                                                     # each row's own outline, corner 7 px
        match = [r for r in rects if all(abs(r[i] - row[i] * dpr) < 1 for i in range(4))]
        assert match and match[0][4] == round(7 * dpr), (row, rects)
    bar = page.evaluate("(() => { const b = document.querySelector('.ovhd').getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; })()")
    assert any(all(abs(r[i] - bar[i] * dpr) < 1 for i in range(4)) and len(r) == 5 for r in rects)   # the toolbar too


def test_a_narrow_card_with_large_text_keeps_the_names_and_the_controls_in_reach(app_page, app_url):
    """At the narrowest width (260 px) with the largest text the rows' combat power and then their share give way,
    and the target's HP numbers, so the names keep their room beside the rate; the toolbar and the fight clock
    wrap inside the card rather than run past it (0.2.370). At the default size all of it shows."""
    page = app_page
    meter = fight()
    meter["snapshot"]["current_target"].update(effective_max_hp=300_000_000, effective_current_hp=141_000_000, effective_hp_samples=12)
    look = dict(overlay_dps_interpolate=False, overlay_show_enemy_hp=True)
    shown = "sel => [...document.querySelectorAll(sel)].filter(e => e.offsetWidth > 0).length"
    open_overlay(page, app_url, meter, **look)                                      # 340 px, 100 %: everything
    assert page.evaluate(shown, ".ovpct") == 3 and page.evaluate(shown, ".ovcp") == 1 and page.evaluate(shown, ".ovhpnum") == 1
    open_overlay(page, app_url, meter, overlay_width=260, overlay_font_scale=160, **look)
    assert page.evaluate(shown, ".ovpct") == 0 and page.evaluate(shown, ".ovcp") == 0 and page.evaluate(shown, ".ovhpnum") == 0
    assert page.locator("#ovtarget .ovhp").inner_text() == "47.0%"                  # the HP share stays
    names = page.evaluate("[...document.querySelectorAll('#ovcontent .ovnametext')].map(n => n.getBoundingClientRect().width)")
    size = page.evaluate("parseFloat(getComputedStyle(document.querySelector('#ovcontent .ovnametext')).fontSize)")
    assert min(names) >= 2.5 * size, (names, size)                                   # a few letters of each name at least
    card = page.locator(".ovcard").bounding_box()
    for piece in ("#ovtarget .ovhp", "#ovclock", ".ovhd", "#ovcapture", "#ovhide"):    # nothing past the card's right edge
        box = page.locator(piece).bounding_box()
        assert box["x"] + box["width"] <= card["x"] + card["width"] + 0.5, piece
