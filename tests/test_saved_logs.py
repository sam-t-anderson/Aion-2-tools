"""Saved Logs are grouped by encounter category so it's easy to tell what each recorded fight is.

The server tags every recorded segment with a user-facing category (PvP / world boss / field boss
/ raid / nightmare / ascension / expedition / transcendence / daily / other) and, inside a mapped
dungeon, a boss role (final boss vs mini-boss) — using the catalog final-boss data and the
field-boss list. The A2SavedLogs client groups those into sections, like the website's Community
Combat Logs. This guards the classifier and the client/page wiring."""
import pathlib

from aion2calc.combat import sessions

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
SAVED_JS = (STATIC / "saved-logs.js").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (STATIC / "index.html").read_text(encoding="utf-8")


def _seg(encounter_type, boss=None, code=None, instance=None):
    entities = [{"is_boss": True, "name": boss, "mob_code": code}] if code is not None else []
    return {"encounter_type": encounter_type, "boss": boss, "instance_id": instance, "entities": entities}


def test_category_pvp():
    c = sessions._category(_seg("pvp_arena"), {})
    assert c["category"] == "pvp" and c["role"] is None


def test_category_raid_final_vs_mini():
    # Eternal Ludra raid (dungeon 600082): final boss 2301014, Isolation Specialist Rahu 2301006 is earlier.
    final = sessions._category(_seg("sanctuary", "Eternal Ludra", 2301014, 600082), {})
    assert final["category"] == "raid" and final["role"] == "final" and final["boss_code"] == 2301014
    mini = sessions._category(_seg("sanctuary", "Isolation Specialist Rahu", 2301006, 600082), {})
    assert mini["category"] == "raid" and mini["role"] == "mini"


def test_category_expedition_final_vs_mini():
    # Fire Temple (dungeon 600021): Kromede's Desire 2310371 is final; Silver Blade Rotan 2310310 is a mini-boss.
    final = sessions._category(_seg("expedition", "Kromede's Desire", 2310371, 600021), {})
    assert final["category"] == "expedition" and final["role"] == "final"
    mini = sessions._category(_seg("expedition", "Silver Blade Rotan", 2310310, 600021), {})
    assert mini["category"] == "expedition" and mini["role"] == "mini"


def test_category_dungeon_types_passthrough():
    for etype in ("nightmare", "ascension", "transcendence", "daily"):
        assert sessions._category(_seg(etype), {})["category"] == etype


def test_category_open_world_field_vs_world_boss():
    field = sessions._category(_seg("pve_open_world", "Kernon of the West"), {})
    assert field["category"] == "field_boss" and field["role"] == "field"
    world = sessions._category(_seg("pve_open_world", "Some Unlisted Open-World Boss"), {})
    assert world["category"] == "world_boss" and world["role"] == "world"


def test_category_unmapped_dungeon_has_no_guessed_role():
    # A dungeon with no curated final boss must not guess final/mini.
    c = sessions._category(_seg("expedition", "Mystery Boss", 999001, 999999), {})
    assert c["category"] == "expedition" and c["role"] is None


def test_category_unknown_is_other():
    assert sessions._category(_seg("unknown"), {})["category"] == "other"


def test_boss_code_prefers_named_boss_entity():
    seg = {"boss": "Final One", "entities": [{"is_boss": True, "name": "Add", "mob_code": 111},
                                             {"is_boss": True, "name": "Final One", "mob_code": 222}]}
    assert sessions._boss_code(seg) == 222


def test_row_contexts_carry_category_and_segment(tmp_path, monkeypatch):
    # _row enriches each session's per-segment contexts with category / role / boss / segment index.
    import json
    monkeypatch.setattr(sessions, "logs_dir", lambda: tmp_path)
    doc = {"format": "a2log", "version": 1, "meta": {"title": "Run"}, "players": [{"id": 1}],
           "segments": [
               {"boss": "Kromede's Desire", "duration": 42.0, "killed": True, "encounter_type": "expedition",
                "difficulty": "normal", "instance_id": 600021,
                "entities": [{"is_boss": True, "name": "Kromede's Desire", "mob_code": 2310371}]},
               {"boss": "Kernon of the West", "duration": 10.0, "killed": True, "encounter_type": "pve_open_world",
                "entities": [{"is_boss": True, "name": "Kernon of the West", "mob_code": 40}]}]}
    target = tmp_path / "session-test.a2log.json"
    target.write_text(json.dumps(doc), encoding="utf-8")
    row = sessions._row(target)
    ctx = row["contexts"]
    assert ctx[0]["category"] == "expedition" and ctx[0]["role"] == "final" and ctx[0]["segment"] == 0
    assert ctx[0]["boss"] == "Kromede's Desire" and ctx[0]["duration"] == 42.0
    assert ctx[1]["category"] == "field_boss" and ctx[1]["segment"] == 1
    # Existing fields preserved for the upload widget's filter.
    assert ctx[0]["encounter_type"] == "expedition" and ctx[0]["difficulty"] == "normal"


# ---- client / page wiring ----

def test_saved_logs_module_groups_by_category():
    assert "window.A2SavedLogs" in SAVED_JS and "function mount(root" in SAVED_JS
    for key in ("pvp", "world_boss", "field_boss", "raid", "nightmare", "ascension",
                "expedition", "transcendence", "daily"):
        assert f'"{key}"' in SAVED_JS, f"missing section {key}"
    assert "/api/sessions?paged=1" in SAVED_JS            # reads the saved recordings
    assert "data-seg" in SAVED_JS and "open(b.dataset.open" in SAVED_JS   # opens an encounter at its segment
    assert "Final boss" in SAVED_JS and "Mini-boss" in SAVED_JS           # role labels
    assert "A2BundledAssets" in SAVED_JS                  # boss portrait


def test_app_mounts_saved_logs_in_saved_panel():
    assert 'id="saved-browse"' in APP_JS
    assert "A2SavedLogs.mount($('#saved-browse')" in APP_JS
    assert "Recorded encounters by type" in APP_JS
    # opens the local recording at the chosen segment
    assert "'/combat-log/local/'+encodeURIComponent(file)" in APP_JS and "?segment='+segment" in APP_JS


def test_index_loads_saved_logs_script():
    assert 'src="/static/saved-logs.js"' in INDEX_HTML
