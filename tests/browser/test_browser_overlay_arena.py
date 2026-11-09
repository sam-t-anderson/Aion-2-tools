"""The overlay's arena mode (0.2.395), as a player sees it. In an arena match the meter's reading carries the match
(`arena`): the overlay draws the opponent's card (name, server, the Opponent tag, HP, combat power, arena rating, the
score) and the three metrics in the layout picked in its Options, Compact by default; a team match puts your three first
and the party in the chip's metric, or all three with "All 3 for party". The player cards window (?view=players) lists
the match's players, allies then enemies, as a list or a grid. Arena mode off draws the meter as ever."""
import json

def fighter(key, name, cls, side, dps, dtps, hps, **more):
    return {"key": key, "id": key[2:], "name": name, "class": cls, "side": side, "self": more.pop("self", False), "dps": dps,
            "dtps": dtps, "hps": hps, "hp_pct": more.pop("hp", 1.0), "dead": more.pop("dead", False), "deaths": 0, **more}


def row(i, name, cls, dps, hps, dtps):
    return {"id": str(i), "key": str(i), "name": name, "class": cls, "dps": dps, "damage": dps * 60, "hps": hps,
            "healing": hps * 60, "dtps": dtps, "hits": 50, "share": 0.5, "skills": []}


def solo():
    me = fighter("a:1", "Testme", "templar", "ally", 12_400, 10_600, 4_100, self=True, server_name="Zikel", rating=1_530,
                 combat_power=46_870)
    foe = fighter("a:2", "Testfoe", "gladiator", "enemy", 10_600, 12_400, 1_200, server_name="Siel", faction="elyos", level=45,
                  rating=1_842, combat_power=48_210, cp_source="official", hp=0.63)
    snap = {"boss": "Testfoe", "duration": 60.0, "recorded_duration": 60.0, "paused": False, "battle_over": False,
            "players": [row(1, "Testme", "templar", 12_400, 4_100, 10_600)],
            "identity_status": {"self_identified": True, "unnamed_actors": 0, "linked_pets": 0, "local_id": 1, "local_name": "Testme"},
            "arena": {"kind": "solitude", "label": "Arena of Solitude", "zone": "Impetusium Arena", "map": 61,
                      "fighters": [foe, me], "opponent": "a:2", "target": "a:2", "you": "a:1", "match": 7, "round": 2,
                      "won": 1, "lost": 0, "result": None}}
    return {"running": True, "combine_pets": True, "snapshot": snap}


def team():
    names = [("Ally", "sorcerer", 23_400, 400, 11_100), ("Testme", "cleric", 6_700, 9_600, 8_200)]
    rows = [row(i + 1, *n) for i, n in enumerate(names)]
    fighters = [fighter(f"a:{i + 1}", n[0], n[1], "ally", n[2], n[4], n[3], self=n[0] == "Testme") for i, n in enumerate(names)]
    fighters += [fighter("a:9", "Foe", "assassin", "enemy", 21_600, 9_800, 0, hp=0.41, share_of_your_damage_taken=0.38),
                 fighter("a:8", "Fallen", "gladiator", "enemy", 16_100, 15_200, 600, hp=0.0, dead=True)]
    snap = {"boss": "Foe", "duration": 90.0, "recorded_duration": 90.0, "paused": False, "battle_over": False, "players": rows,
            "identity_status": {"self_identified": True, "unnamed_actors": 0, "linked_pets": 0, "local_id": 2, "local_name": "Testme"},
            "arena": {"kind": "cooperation", "label": "Arena of Cooperation", "zone": "Fire Temple Arena", "map": 60,
                      "fighters": fighters, "opponent": None, "target": "a:9", "you": "a:2"}}
    return {"running": True, "combine_pets": True, "snapshot": snap}


def open_overlay(page, app_url, meter, view="", **look):
    """The overlay over the meter answer ``meter`` with these settings; the saved settings the overlay posts are kept."""
    if not hasattr(page, "arena_look"):
        page.arena_look, page.arena_meter, page.arena_posts = {}, {}, []

        def ui(route):
            if route.request.method == "POST":           # kept here: the app's saved settings serve every test
                body = json.loads(route.request.post_data or "{}")
                page.arena_posts.append(body)
                page.arena_look.update(body)
                return route.fulfill(json=dict(page.arena_look))
            return route.fulfill(json={**route.fetch().json(), "overlay_width": 340, **page.arena_look})
        page.route("**/api/ui", ui)
        page.route("**/api/meter?view=latest", lambda route: route.fulfill(json=page.arena_meter))
    page.arena_look, page.arena_meter = dict(look), meter
    page.goto("about:blank")
    page.goto(app_url + "overlay" + (f"?view={view}" if view else ""), wait_until="load")


def test_a_one_against_one_match_shows_the_opponents_card_and_the_compact_table(app_page, app_url):
    page = app_page
    open_overlay(page, app_url, solo())
    page.wait_for_selector("#ovcontent .arn-table")
    card = page.locator("#ovtarget")
    assert card.locator(".ovtname").inner_text() == "Testfoe" and card.locator(".arn-tag").inner_text().lower() == "opponent"
    assert "Siel · Elyos" in card.locator(".arn-who").inner_text() and card.locator(".ovhp").inner_text() == "63.0%"
    line = card.locator(".ovtline").first.inner_text()
    assert "48.2K" in line and "Gladiator" in line and "Lv 45" in line and "Rating 1,842" in line
    assert "Round 2" in card.locator(".ovtline").nth(1).inner_text() and "1–0" in card.locator(".ovtline").nth(1).inner_text()
    rows = page.locator("#ovcontent .arn-table")
    assert rows.count() == 2
    assert rows.nth(0).locator(".ovnametext").inner_text() == "Testme" and "ovrow-self" in rows.nth(0).get_attribute("class")
    assert rows.nth(0).locator(".arn-cell").all_inner_texts() == ["12.4K", "10.6K", "4.1K"]
    assert "Arena of Solitude" in page.locator("#ovclock").inner_text() and "1–0" in page.locator("#ovclock").inner_text()
    # the layout picker in the Options: Stacked draws a section for each metric, saved as a setting
    page.click("#ovsettings")
    assert page.locator("#ovarenalayout").input_value() == "compact" and page.locator("#ovarena").is_checked()
    page.select_option("#ovarenalayout", "stacked")
    page.wait_for_function("document.querySelectorAll('#ovcontent .arn-sec').length === 3")
    assert {"overlay_arena_layout": "stacked"} in page.arena_posts
    assert [t.lower() for t in page.locator("#ovcontent .arn-sec").all_inner_texts()] == ["dps", "d.taken", "hps"]
    assert page.locator("#ovcontent .arn-row").count() == 6
    page.select_option("#ovarenalayout", "versus")
    page.wait_for_selector("#ovcontent .arn-tug")
    assert page.locator("#ovcontent .arn-tug").count() == 3 and page.locator("#ovtarget .arn-vs .arn-side").count() == 2
    # arena mode off: the meter's own rows and no card
    page.uncheck("#ovarena")
    page.wait_for_function("document.querySelectorAll('#ovcontent .ovrow:not(.arn-row):not(.arn-table)').length === 1")
    assert {"overlay_arena_mode": False} in page.arena_posts and page.locator("#ovtarget .arn-tag").count() == 0


def test_a_team_match_shows_your_three_then_the_party_and_all_three_on_request(app_page, app_url):
    page = app_page
    open_overlay(page, app_url, team(), overlay_arena_layout="stacked")
    page.wait_for_selector("#ovcontent .arn-row")
    assert page.locator("#ovtarget .ovtname").inner_text() == "Foe" and page.locator("#ovtarget .arn-tag").inner_text().lower() == "target"
    assert "38%" in page.locator("#ovtarget").inner_text()
    labels = page.locator("#ovcontent .arn-sec").all_inner_texts()
    assert labels[0].lower().startswith("you") and "".join(labels[1].lower().split()) == "party·dps"
    mine = page.locator("#ovcontent .arn-row").all_inner_texts()[:3]
    assert [m.split("\n")[0] for m in mine] == ["DPS", "D.Taken", "HPS"]
    party = page.locator("#ovcontent .arn-row .ovnametext").all_inner_texts()[3:]
    assert party == ["Ally", "Testme"]                                         # by the chip's metric, DPS
    page.click("#ovsettings")
    page.check("#ovarenaall3")
    page.wait_for_selector("#ovcontent .arn-tri")
    assert {"overlay_arena_all3": True} in page.arena_posts
    assert page.locator("#ovcontent .arn-tri").first.locator("b").all_inner_texts() == ["23.4K", "11.1K", "400"]


def test_the_player_cards_window_lists_the_match_as_a_list_or_a_grid(app_page, app_url):
    page = app_page
    open_overlay(page, app_url, team(), view="players")
    page.wait_for_selector("#ovcontent .arn-card")
    assert page.locator("#ovtarget .arn-badge").inner_text().lower() == "arena of cooperation · 2v2"
    cards = page.locator("#ovcontent .arn-card")
    assert cards.count() == 4 and [cards.nth(i).locator(".nm").inner_text() for i in range(4)] == ["Ally", "Testme", "Foe", "Fallen"]
    assert "dead" in cards.nth(3).get_attribute("class") and "foe" in cards.nth(2).get_attribute("class")
    assert cards.nth(1).locator(".arn-you").count() == 1
    for hidden in ("#ovsettings", "#ovsplit", "#ovcopy", "#ovcapture", "#plan-tab"):
        assert page.locator(hidden).is_hidden()
    assert page.locator("#ovhide").is_visible() and page.locator("#ovlock").is_visible()
    open_overlay(page, app_url, team(), view="players", overlay_players_style="grid")
    page.wait_for_selector("#ovcontent .arn-grid .arn-mini")
    assert page.locator("#ovcontent .arn-mini").count() == 4
    open_overlay(page, app_url, {"running": True, "snapshot": {"players": []}}, view="players")
    page.wait_for_function("(document.querySelector('#ovcontent') || {}).textContent.includes('Waiting for an arena or battlefield match')")
