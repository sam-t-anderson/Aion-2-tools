"""The Brawler, the client's Fighter (0.2.390): out in Korea and Taiwan, and in the global client without its skills'
names or values. The meter, the logs, the character import and the class colours know it; the Korean training-dummy
reference is bundled; the calculator does not model it until its skills have values (docs/methodology.md,
"The Brawler")."""
import json
from pathlib import Path

import pytest

from aion2calc.combat import a2log, adapters, analyze
from aion2calc.meter.a2parser.lookup import class_key_of, job_from_roster, job_from_skill, skill_name
from aion2calc.meter.session import CombatSession
from aion2calc.sources import official

ROOT = Path(__file__).resolve().parents[1]
ASCENDING_RAMPAGE, CHAIN_FIST_RAMPAGE, FLURRY = 19150000, 19430000, 19010000


def test_the_game_names_it_the_fighter_and_every_part_keys_it_brawler():
    assert job_from_skill(ASCENDING_RAMPAGE) == job_from_skill(FLURRY) == "Fighter"
    # the official Taiwanese pcData: 45-48 are the Brawler's light/dark, male/female; 37-44 are no class
    assert [job_from_roster(code) for code in (36, 44, 45, 48, 49)] == ["Chanter", None, "Fighter", "Fighter", None]
    assert class_key_of("Fighter") == "brawler" and class_key_of("Elementalist") == "spiritmaster"
    assert class_key_of("Chanter") == "chanter" and class_key_of(None) is None and class_key_of("") is None
    assert CombatSession._actor(7, "Someone", "Fighter")["class"] == "brawler"
    assert official.CLASS_KEYS["Fighter"] == "brawler" and official.search_class(46) == "brawler"
    assert [a2log.class_key(c) for c in ("Fighter", "fighter", "brawler", "Elementalist", "bard")] == \
        ["brawler", "brawler", "brawler", "spiritmaster", None]


def test_a_recorded_brawler_keeps_its_class_through_the_log():
    """The meter wrote the game's own job name, and a log dropped "Fighter" as no class."""
    from aion2calc.meter import Meter, replay_source
    meter = Meter()
    for event in replay_source(ROOT / "aion2calc" / "meter" / "demo_session.jsonl"):
        meter.add(event)
    doc = meter.to_a2log(title="Demo")
    doc["players"][0]["class"] = "Fighter"
    assert a2log.validate(doc)["players"][0]["class"] == "brawler"


def test_importing_a_brawler_says_the_class_is_not_modelled():
    from aion2calc.sources.character import from_profile
    with pytest.raises(ValueError, match="is a Brawler"):
        from_profile({"profile": {"className": "Fighter", "characterName": "Tester"}})


def test_the_korean_reference_is_bundled_and_a_brawler_log_compares_with_it():
    ref = json.loads((ROOT / "aion2calc" / "data" / "kr" / "a2dil" / "brawler.json").read_text(encoding="utf-8"))
    assert ref["class"] == "brawler" and ref["records"] == 10
    shares = {v["code"]: v["mean_share"] for v in ref["skills"].values() if v["code"]}
    assert shares[ASCENDING_RAMPAGE] > 0.1 and shares[CHAIN_FIST_RAMPAGE] > 0.1      # the Rampage variants lead
    assert sum(v["mean_share"] for v in ref["skills"].values()) == pytest.approx(1.0, abs=0.01)
    # a log with no class named is a Brawler's by its skills' prefix, and is named in English by the meter's catalog
    enc = adapters.normalize({"meta": {"duration": 10.0},
                              "hits": [{"t": i, "skill_id": ASCENDING_RAMPAGE if i % 2 else CHAIN_FIST_RAMPAGE,
                                        "skill": "승천타[폭주]", "damage": 1000.0} for i in range(10)]})
    assert enc["meta"]["class"] == "brawler"
    assert {h["skill"] for h in enc["hits"]} == {skill_name(ASCENDING_RAMPAGE), skill_name(CHAIN_FIST_RAMPAGE)}
    rows = {r["skill"]: r for r in analyze.vs_top(enc)["rows"]}
    top = rows[skill_name(ASCENDING_RAMPAGE)]
    assert top["share"] == pytest.approx(0.5) and top["top_share"] == pytest.approx(shares[ASCENDING_RAMPAGE])


def test_a_refresh_skips_the_brawler_until_metabot_has_it(monkeypatch, tmp_path):
    from aion2calc.scrape import a2dil, metabot, refresh
    from aion2calc.scrape.http import NotFound

    def missing(cls, fresh=False):
        raise NotFound(f"404 for {cls}")
    monkeypatch.setattr(metabot, "class_data", missing)
    monkeypatch.setattr(a2dil, "class_summary", lambda cls: {"class": cls, "records": 0, "skills": {}, "raw": []})
    monkeypatch.setattr(refresh, "DATA", tmp_path)
    refresh.refresh(only="brawler")
    assert not (tmp_path / "global" / "classes" / "brawler.json").exists()
    assert json.loads((tmp_path / "kr" / "a2dil" / "brawler.json").read_text(encoding="utf-8"))["class"] == "brawler"
    with pytest.raises(NotFound):                    # a released class missing from metabot is still an error
        refresh.refresh(only="gladiator", skip_kr=True)


def test_the_brawler_has_a_class_colour_the_settings_keep(tmp_path, monkeypatch):
    from aion2calc.app.settings_backup import clean_class_colors
    assert clean_class_colors({"colors": {"brawler": "#7F9A3A"}}) == {"colors": {"brawler": "#7f9a3a"}}
    static = ROOT / "aion2calc" / "app" / "static"
    assert 'brawler:"#7f9a3a"' in (static / "overlay.js").read_text(encoding="utf-8")
    assert 'brawler:"#00c98d"' in (static / "featured.js").read_text(encoding="utf-8")
