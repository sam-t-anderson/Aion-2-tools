"""The native Saved Results page and the first result windows (0.2.434): the saved runs, their import and export,
and a saved build's Overview, Skills and Stigma windows as pages/history.js and pages/results.js show them, off
screen, over the app's own result view of the bundled sorcerer build (``views.build_view`` of
results/sorcerer_l45/build.json).
"""
import json
import os
import pathlib
import sys
import urllib.parse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPlainTextEdit, QPushButton, QToolButton  # noqa: E402

from aion2calc.app import history as store  # noqa: E402
from aion2calc.gui import history_page as h  # noqa: E402
from aion2calc.gui import result_windows as w  # noqa: E402
from aion2calc.gui import results as r  # noqa: E402
from aion2calc.gui.history_page import HistoryPage  # noqa: E402
from aion2calc.gui.news import when  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402
from test_native_pets import _png  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CREATED = 1793000000
ID, TEXT_ID, ADVICE_ID = "a" * 24, "b" * 24, "c" * 24


@pytest.fixture(scope="module")
def view():
    from aion2calc.app.views import build_view
    return build_view(json.loads((ROOT / "results" / "sorcerer_l45" / "build.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    """Each test's windows are closed and deleted while Qt's application exists (see test_native_interface.py)."""
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


def _doc(kind, result, title="sorcerer · PvE · optimize class", created=CREATED):
    return {"format": "a2result", "version": 1, "kind": kind, "title": title, "created": created, "result": result}


class FakeApp:
    """The app as the page asks it: the saved results (``docs`` by id), each checked as the app checks an import."""

    def __init__(self, docs, refuse=None):
        self.docs, self.refuse, self.calls, self.posts = dict(docs), refuse, [], []

    def get(self, path):
        self.calls.append(path)
        if path == "/api/history":
            return sorted(({"id": i, **{k: d[k] for k in ("kind", "title", "created")}} for i, d in self.docs.items()),
                          key=lambda row: row["created"], reverse=True)
        identifier = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)["id"][0]
        return json.loads(json.dumps(self.docs[identifier]))

    def get_bytes(self, path):
        self.calls.append(path)
        assert path.startswith("/api/icon?u=")
        return _png((200, 120, 40), 8)

    def post(self, path, body):
        self.posts.append((path, body))
        assert path == "/api/history"
        if self.refuse:
            raise OSError(self.refuse)
        checked = store.validate(body)                         # the app's own check of an imported result
        self.docs["d" * 24] = checked
        return {"id": "d" * 24}


def _page(api, **kwargs):
    page = HistoryPage(api, **kwargs)
    page.resize(1100, 1500)
    page.show()
    settle(lambda: page.rows or "/api/history" in api.calls and page.list.count())
    QCoreApplication.processEvents()
    return page


def _texts(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _button(widget, words):
    QCoreApplication.processEvents()
    return next((b for b in widget.findChildren(QPushButton) if b.text() == words and b.isVisibleTo(widget)), None)


def _counter(widget):
    """A window's counter as a screen reader reads it: its words, then its figure."""
    QCoreApplication.processEvents()
    return next(label.accessibleName() for label in widget.findChildren(QLabel, "counter") if label.isVisibleTo(widget))


def _opened(page, identifier):
    page.opened = None
    page.open(identifier)
    settle(lambda: page.opened is not None)
    QCoreApplication.processEvents()


def test_the_overviews_words(view):
    assert [r.n0(x) for x in (None, "x", 49658.18, 0.5, 1.5, -2.5)] == ["—", "—", "49,658", "1", "2", "-2"]
    assert (r.pct(0.0536862), r.pct(None), r.pct(0.25, 0), r.sp(0.0125), r.sp(-0.3)) == ("5.4%", "—", "25%", "+1.3%", "-30.0%")
    assert r.kpis(view) == [("boss DPS", "49,658"), ("dummy DPS", "47,760"), ("Typical top build", "44,920"),
                            ("Crit chance", "5.4%"), ("Cooldown red.", "6.5%"), ("Combat speed", "8.2%")]
    goal = r.objective(view)
    assert goal.startswith("<b>boss modeled DPS: 49,658</b><br>boss 100.0% · 180s · 49,658 DPS")
    assert "Damage objective subject to the saved HP" in goal
    assert r.overview_notes(view, when) == [goal] and r.model_note(view) == ""
    weights = r.weight_rows(view)
    assert weights[0] == ("Cooldown Reduction +3%", "+3.08%", pytest.approx(3.0765627961974427 * 25)) and len(weights) == 12
    assert r.weight_rows({"weights": [{"label": "Big", "pct": 9}, {"label": "Loss", "pct": -1}]}) == [
        ("Big", "+9.00%", 100.0), ("Loss", "-1.00%", 0.0)]
    shares = r.share_rows(view["shares"])
    assert shares[0] == ("Hellfire", "18.8%", 100.0) and len(shares) == 12 and shares[1][2] == pytest.approx(13.354767753 / 18.762211703 * 100)
    # the healing share: none without the key, the line asking for fights, then recorded and modelled
    assert r.healing(view) is None
    assert r.healing({"healing": None}) == {"lines": [
        "No recorded healing by this character yet. Fights recorded with the live meter on this computer fill this in; the "
        "model simulates heal amounts for Clerics and Chanters only."], "rows": []}
    recorded = r.healing({"healing": {"shares": {"Heal": 0.75, "Light": 0.25}, "hps": 1234.4, "fights": 1, "seconds": 120,
                                      "recordings": 2},
                          "modelled_healing": {"per_minute": 5, "hps": 2000, "multiplier": 1.5,
                                               "by_skill": [{"skill": "Heal", "share": 0.6}]}})
    assert recorded["lines"] == ["Modelled: 2,000 HPS in a boss fight (Heal 60.0%): each heal at this character's level times "
                                 "1.50 for its Attack, as often as recorded healers heal.",
                                 "Recorded: 1,234 HPS over 1 fight (2 min) in 2 recordings saved on this computer."]
    assert recorded["rows"] == [("Heal", "75.0%", 100.0), ("Light", "25.0%", pytest.approx(100 / 3))]
    # the other notes, as the web page writes them
    policy = r.scoring_policy({"scoring_policy": {"mode": "pvp", "note": "Equal & fair", "model": "m7"}, "score": 1234.6,
                               "preset_source": "community", "preset_checked_at": CREATED}, when)
    assert policy.startswith("Community PVP preset · 1,235 weighted modeled DPS<br><small>Equal weighting of sustained and burst")
    assert f"Last checked {when(CREATED * 1000)}" in policy and "Equal &amp; fair<br>Evaluator m7" in policy
    world = r.world_pvp({"score": 900, "dps": 1200.4, "alive_share": .5, "acting_share": .75, "effective_hp": 9000,
                         "control_s_per_min": 3.25, "controlled_self": .1, "attackers": 2, "controlled": .2, "damage_taken": .8,
                         "typical_build": {"score": 800}, "defensives": [1, 2], "note": "World note"})
    assert "<h4>World PvP</h4>" in world and "<td>900</td><td>800</td>" in world and "<td>3.3</td><td>—</td>" in world
    assert "2 attackers · 20.0% of their time under your crowd control" in world and "2 defensive effects counted." in world
    assert "<td>Skill</td><td>10</td><td>5</td><td>3</td><td>listed</td><td>Unknown</td>" in r.progression(
        {"resources": [{"resource": "skill", "observed_spent": 10, "available_assumption": 5, "assumed_unspent": 3,
                        "source": "listed", "verified_maximum": None}], "note": "p"})
    timing = r.action_timing({"windows": [{"name": "Dodge", "start_s": 1, "end_s": 2, "reserve_cooldown": True}],
                              "cases": {"boss": {"paused_s": 3, "duration_s": 180, "blocks": [[1, 2]],
                                                 "cooldown_checks": [{"skill": "Shield", "activation_starts_s": [1],
                                                                      "cooldown_s": 30, "shortest_reuse_gap_s": None}]}},
                              "note": "t"})
    assert "<li>Dodge · 1–2s · Rotation cooldown reservation requested · Unlinked assumption</li>" in timing
    assert "boss · 3s unavailable for new actions / 180s · clipped interval union: 1–2s" in timing
    assert "Shield · starts: 1s · Assumed effective cooldown 30s · No repeated activation · assumed spacing satisfied" in timing
    reserve = r.survival({"selected_node_hp": 1000, "minimum_node_hp": 900, "reference_node_hp": 800, "meets_node_floor": True,
                          "opponents": [{"name": "Boss", "window_s": 10.0, "required_hp": 5000, "headroom_hp": 100,
                                         "meets_assumed_pressure": True}], "binding_opponents": ["Boss"], "note": "s"})
    assert "Crystal-board flat HP: <b>1,000</b> · requested floor: 900 · previous contribution: 800. Reserve met." in reserve
    assert "User assumption · 10s window" in reserve and "100 · Meets assumed HP requirement" in reserve
    assert "Strictest incoming requirement: Boss" in reserve
    kept = r.skill_reserves({"met": False, "skills": [{"name": "Heal", "minimum": 5, "selected": 4}], "note": "k"})
    assert "<h3>Trained skill reserves · not met</h3>" in kept and "<td>Heal</td><td>5</td><td>4</td>" in kept
    assert r.comparison_text(view).startswith("Generate a separate PvE example") and "PvP example" in r.comparison_text({"scenario": "pvp"})


def test_the_skills_and_stigmas_words(view):
    blaze = view["skills"]["active"][0]
    assert r.skill_counter(view) == ("Skill points", "383 / 383")
    assert r.skill_level(blaze) == f"<b>Lv 20</b> <span style='color: {r.ACCENT};'>= SP 10 + Daevanion 4 + gear 6</span>"
    assert r.skill_level({**blaze, "gear": 0}).endswith("= SP 10 + Daevanion 4</span>")
    assert r.skill_slots(blaze) == "3 selection slot(s)\n3 recommended" and r.skill_slots({"specs": []}) == ""
    assert r.skill_slots({**blaze, "next_effect_level": 24}).endswith("\nNext effect at Lv 24")
    assert [r.effect_state(x) for x in blaze["specs"]] == ["Available", "Recommended", "Recommended", "Available", "Recommended"]
    assert r.effect_state({"chosen": False, "available": False}) == "Locked"
    copied = r.skills_copy(view).split("\n")
    assert copied[0] == ("Blaze: train to 10 (Lv 20) — specialties 2: +50% MP restored (effect Lv 8); 3: Delayed Damage "
                         "after 3s (effect Lv 8); 5: -3s [Wish of Concentration] cooldown on hit (effect Lv 16)")
    assert copied[-1].startswith("Bonus levels from gear rolls and arcana cards: Flame Scattershot +6 (Chalice, Compass), ")
    assert r.skills_grid(view)[0] == ("Skill points spent", "383 / 383")
    assert r.skills_grid(view)[-1][0].startswith("Bonus levels to chase")
    assert r.skills_grid({**view, "gear_skill_rolls": [{"name": "Blaze", "levels": 2}], "bonus_levels": []})[1:] == [
        ("Skill levels from gear", "Blaze +2")]
    assert r.stigma_counter(view) == ("Stigma points", "188 / 188")
    assert r.stigmas_copy(view) == "Cold Storm: Lv 13\nElement Enhancement: Lv 20\nFire Wall: Lv 20\nDelayed Explosion: Lv 8"
    assert r.stigmas_grid(view)[0] == ("Cold Storm", "Lv 13 · 2 effects")
    active, inactive = view["stigmas"][0]["specs"][0], view["stigmas"][0]["specs"][2]
    assert r.stigma_effect(active).startswith(f"<b style='color: {r.GOLD};'>1</b> Enhanced Frostbite")
    assert r.stigma_effect(inactive).startswith(f"<span style='color: {r.MUTED};'>")
    assert r.view_of(_doc("optimize-character", {"optimized": {"a": 1}})) == {"a": 1}
    assert r.view_of(_doc("optimize-class", view)) is not None and r.view_of({}) is None
    assert [key for key, _title, _mark in r.WINDOWS][:3] == ["overview", "skills", "stigma"] and len(r.WINDOWS) == 10


def test_the_saved_runs_and_a_build_opened(qapp, view):
    app, opened, copied = FakeApp({ID: _doc("optimize-class", view)}), [], []
    page = HistoryPage(app, open_web=opened.append)
    assert app.calls == []
    page.resize(1100, 1500)
    page.show()
    settle(lambda: page.rows)
    QCoreApplication.processEvents()
    texts = _texts(page)
    assert "sorcerer · PvE · optimize class" in texts and when(CREATED * 1000) in texts
    assert ["RUN", "RECORDED"] == [t for t in texts if t in ("RUN", "RECORDED")]
    _button(page, "Open").click()
    settle(lambda: page.windows is not None)
    QCoreApplication.processEvents()
    windows = page.windows
    windows.clipboard = copied.append
    assert r.saved_line(when(CREATED * 1000)) in _texts(page)
    assert windows.state["win"] == "overview" and windows.menu["overview"].objectName() == "sideItemOn"
    assert [b.text() for b in windows.menu.values()][7] == "♛   Titles && wings"           # "&" shown, not a shortcut
    texts = _texts(windows)
    for name, value in r.kpis(view):
        assert name.upper() in texts and value in texts
    assert view["loadout_name"] in texts and r.objective(view) in texts
    bars = [bar for bar in windows.findChildren(w.Bar) if bar.isVisibleTo(windows)]
    assert len(bars) == 24 and bars[12].words == "18.8%" and bars[0].share == pytest.approx(76.91, abs=0.01)
    assert "STAT PRIORITY (DPS PER UPGRADE)" in texts and "DAMAGE SHARE" in texts and "HEALING SHARE" not in texts
    comparison = next(b for b in windows.findChildren(QToolButton) if b.text() == "Contribute a community comparison")
    assert comparison.isVisibleTo(windows) and not comparison.isChecked()                # closed, as on the web page
    # Skills: the active skills, each with its picture, level, slots and effects; then passive; and the copy
    windows.choose("skills")
    QCoreApplication.processEvents()
    cards = [card for card in windows.findChildren(QFrame, "skill") if card.isVisibleTo(windows)]
    assert len(cards) == len(view["skills"]["active"])
    texts = _texts(windows)
    assert _counter(windows) == "Skill points 383 / 383" and r.skill_level(view["skills"]["active"][0]) in texts
    assert "3 selection slot(s)\n3 recommended" in texts and "+50% MP restored" in texts
    badges = [b for b in windows.findChildren(QLabel, "specOn") if b.isVisibleTo(windows)]
    assert len(badges) == sum(1 for s in view["skills"]["active"] for x in s["specs"] if x["chosen"])
    settle(lambda: any(icon.pixmap is not None for icon in windows.shown_icons))
    assert all(icon.path.startswith("/api/icon?u=https%3A%2F%2Fmetabot.gg%2Fweb%2Faion2%2Fskills%2F") for icon in windows.shown_icons)
    asked = [call for call in app.calls if call.startswith("/api/icon?u=")]
    assert len(asked) == len(set(asked))                                                 # each picture asked for once
    _button(windows, "Copy as text").click()
    assert copied == [r.skills_copy(view)]
    _button(windows, "Passive").click()
    QCoreApplication.processEvents()
    assert windows.state["skilltab"] == "passive"
    assert len([c for c in windows.findChildren(QFrame, "skill") if c.isVisibleTo(windows)]) == len(view["skills"]["passive"])
    # Stigma
    windows.choose("stigma")
    QCoreApplication.processEvents()
    assert len([c for c in windows.findChildren(QFrame, "stigma") if c.isVisibleTo(windows)]) == 4
    texts = _texts(windows)
    assert _counter(windows) == "Stigma points 188 / 188" and "Level 13" in texts
    assert r.stigma_effect(view["stigmas"][0]["specs"][0]) in texts
    _button(windows, "Copy as text").click()
    assert copied[-1] == r.stigmas_copy(view)
    # a window it does not know: the Overview without the comparison (results.js's default)
    windows.choose("nothing")
    QCoreApplication.processEvents()
    assert "STAT PRIORITY (DPS PER UPGRADE)" in _texts(windows)
    assert not [b for b in windows.findChildren(QToolButton) if b.text() == comparison.text() and b.isVisibleTo(windows)]
    # contributing a comparison is on the web page for now: its button opens it
    windows.choose("overview")
    QCoreApplication.processEvents()
    next(b for b in windows.findChildren(QToolButton) if b.text() == "Contribute a community comparison").click()
    assert w.COMPARISON_NOTE in _texts(windows)
    _button(windows, "Open the web Saved Results page").click()
    assert opened == ["history"]


def test_advice_its_text_and_the_export(qapp, view, tmp_path):
    saved = tmp_path / "saved.json"
    docs = {ID: _doc("optimize-class", view), TEXT_ID: _doc("advice-text", {"text": "Line one\n  Line two"}, "Text advice", CREATED + 1),
            ADVICE_ID: _doc("advice", {"character": {}}, "Advice", CREATED + 2)}
    page = _page(FakeApp(docs), save_as=lambda name: (setattr(page, "asked", name), str(saved))[1], open_web=lambda p: None)
    assert [row["id"] for row in page.rows] == [ADVICE_ID, TEXT_ID, ID]                 # newest first
    _opened(page, TEXT_ID)
    text = next(box for box in page.findChildren(QPlainTextEdit) if box.isVisibleTo(page))
    assert text.toPlainText() == "Line one\n  Line two" and text.isReadOnly() and page.windows is None
    _opened(page, ADVICE_ID)
    assert h.ADVICE_NOTE in _texts(page) and _button(page, "Open the web Saved Results page")
    page.export(ID)
    settle(lambda: saved.exists())
    assert page.asked == f"aion2calc-result-{ID}.json" and json.loads(saved.read_text(encoding="utf-8")) == json.loads(json.dumps(docs[ID]))
    assert page.message.text() == f"Result saved to {saved}."


def test_a_result_imported(qapp, view, tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_doc("optimize-class", view, "Imported build")), encoding="utf-8")
    app = FakeApp({})
    page = _page(app, choose_file=lambda: str(good))
    assert h.NO_RUNS in _texts(page)
    _button(page, "Choose a file…").click()
    settle(lambda: page.message.text() == "Result imported" and page.rows)
    assert app.posts[0][1]["title"] == "Imported build" and "Imported build" in _texts(page)
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    page.choose_file = lambda: str(broken)
    _button(page, "Choose a file…").click()
    assert page.message.text().startswith("Expecting property name")
    huge = tmp_path / "huge.json"
    with open(huge, "wb") as file:
        file.truncate(h.LIMIT + 1)
    page.choose_file = lambda: str(huge)
    _button(page, "Choose a file…").click()
    assert page.message.text() == "Result exceeds 20 MiB"
    refused = _page(FakeApp({}, refuse="Choose an exported Aion 2 Calc result JSON"), choose_file=lambda: str(good))
    _button(refused, "Choose a file…").click()
    settle(lambda: refused.message.text())
    assert refused.message.text() == "Choose an exported Aion 2 Calc result JSON"
    page.choose_file = lambda: ""
    _button(page, "Choose a file…").click()                                             # nothing chosen: nothing said
    assert page.message.text() == "Result exceeds 20 MiB"


def test_the_window_draws_saved_results_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("history"), HistoryPage) and not isinstance(window.page("history"), WebPage)
    assert isinstance(window.page("raid"), WebPage)                                        # not moved over yet
