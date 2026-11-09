"""An older log's heals over time are rebuilt into what each tick took when it is read (0.2.404).

A heal over time holds an HP pool, reported in ``05 38`` records. A meter before 0.2.399 recorded the pool as a heal
when it was cast and then, at each tick, a heal of what was left of it, so a Light of Regeneration counted about ten
times what it healed. A pool of N ticks loses ``pool // N`` a tick, on its tick clock (2 s, Spirit's Benediction 1 s),
so its records step down by whole ticks; ``healing.heals_over_time`` splits each (source, target, skill id) chain
back into its pools and makes each record the heal of what the ticks since the pool's last record took, as a meter
of 0.2.399 or later records it (docs/methodology.md, "Heals over time in older logs, rebuilt when read").
Synthetic records only."""
import pytest

from aion2calc.combat import a2log
from aion2calc.combat.healing import heals_over_time, meter_version, pool_shape, records_pools
from aion2calc.combat.healing_share import _pool
from aion2calc.combat.unnamed import relabel

CLERIC, CHANTER, TARGET = "p:2102:1", "p:2102:2", "p:2102:3"
LOR, RECUPERATION, RECUPERATION_STACKS, POTION, BENEDICTION = 17090120, 18120000, 18120010, 2011101, 16190000


def heal(t, source, target, skill, name, amount):
    return {"kind": "heal", "t": t, "source": source, "target": target, "skill_id": skill, "skill": name,
            "amount": float(amount)}


def _pool_records(t0, source, target, skill, name, pool, ticks, interval=2.0, applied=True, taken=0, last=None):
    """A pool's records as an old meter saved them: the whole pool when cast (``applied``), then what was left
    after each tick, from ``taken`` ticks in (a pool cast before the fight) to ``last`` ticks."""
    tick = pool // ticks
    out = [heal(t0, source, target, skill, name, pool)] if applied else []
    for k in range(max(1, taken), (last or ticks) + 1):
        out.append(heal(t0 + k * interval, source, target, skill, name, pool - k * tick))
    return out


def _doc(events, version="0.2.398", duration=60.0):
    return {"format": "a2log", "version": 1,
            "meta": {"title": "Run", "capture_quality": {"decoder": "a2tools-python-v1", "app_version": version}},
            "players": [{"id": CLERIC, "name": "Testcleric", "class": "cleric"},
                        {"id": CHANTER, "name": "Testchanter", "class": "chanter"},
                        {"id": TARGET, "name": "Testtemplar", "class": "templar"}],
            "segments": [{"duration": duration, "encounter_type": "expedition", "hits": [], "events": events,
                          "entities": []}]}


def _heals(segment, skill=None):
    return [(e["t"], e["amount"]) for e in segment["events"] if e["kind"] == "heal"
            and (skill is None or e["skill_id"] == skill)]


def test_which_records_are_pools():
    assert pool_shape(17090120) == (15, 2.0, False) and pool_shape(17090000) == (15, 2.0, False)
    assert pool_shape(18120000) == (4, 2.0, True)          # its own heal and "+5 % HP restored" share the id
    assert pool_shape(18120030) == (6, 2.0, False)         # "+4s healing duration": six ticks
    assert pool_shape(18120010) == (4, 2.0, False)
    assert pool_shape(17290000) is None and pool_shape(17290040) == (5, 2.0, False)     # Absolution's option 4
    assert pool_shape(12350000) is None and pool_shape(12350230) == (5, 2.0, False)     # Warding Strike's option 3
    assert pool_shape(16190000) == (10, 1.0, True)         # Spirit's Benediction, every 1 s
    assert pool_shape(2011101) == (5, 2.0, False) and pool_shape(2011102) == (5, 2.0, False)
    assert pool_shape(17100000) is None and pool_shape(17160000) is None and pool_shape(None) is None


def test_a_light_of_regeneration_heals_what_its_ticks_took():
    """The 31 October recording's 5,946: 396 a tick for 15 ticks, 6 left. Recorded as the pool and what was left
    of it, it counted 47,616; rebuilt, the application is no heal and each tick heals 396."""
    events = _pool_records(10.0, CLERIC, TARGET, LOR, "Light of Regeneration", 5946, 15)
    assert sum(e["amount"] for e in events) == 47_616
    segment = _doc(events)["segments"][0]
    count = heals_over_time(segment)
    assert _heals(segment) == [(10.0 + 2 * k, 396.0) for k in range(1, 16)]
    assert count == {"records": 16, "amount": 47_616.0, "rebuilt": 5940.0, "skills": {"Light of Regeneration": 16}}


def test_a_pool_cast_before_the_fight_counts_its_first_recorded_tick():
    events = _pool_records(-4.0, CLERIC, TARGET, LOR, "Light of Regeneration", 5946, 15, applied=False, taken=3)
    segment = _doc(events)["segments"][0]
    heals_over_time(segment)
    assert _heals(segment) == [(-4.0 + 2 * k, 396.0) for k in range(3, 16)]


def test_light_of_regenerations_second_pool_and_a_potions_two_are_told_apart():
    """The "+20 %" option applies a second pool beside the first and each tick takes from one of them; a Life
    Potion's two pools tick side by side. Each record goes to the pool it continues by whole ticks."""
    first, second = 6310, 7577                              # ticks 420 and 505
    events = [heal(20.0, CLERIC, TARGET, LOR, "Light of Regeneration", first),
              heal(20.0, CLERIC, TARGET, LOR, "Light of Regeneration", second),
              heal(22.0, CLERIC, TARGET, LOR, "Light of Regeneration", first - 420),
              heal(24.0, CLERIC, TARGET, LOR, "Light of Regeneration", first - 840),
              heal(26.0, CLERIC, TARGET, LOR, "Light of Regeneration", second - 505),     # HP under half: the second
              heal(28.0, CLERIC, TARGET, LOR, "Light of Regeneration", first - 1260),
              heal(30.0, CLERIC, TARGET, LOR, "Light of Regeneration", first - 1680)]
    potion = []
    for k in range(0, 6):                                   # 2,095 = 5 x 419 and 1,602 = 5 x 320 + 2
        potion += [heal(40.0 + 2 * k, TARGET, TARGET, POTION, "Life Potion", 2095 - 419 * k)] if k < 5 else []
        potion += [heal(40.0 + 2 * k, TARGET, TARGET, POTION, "Life Potion", 1602 - 320 * k)]
    segment = _doc(events + potion)["segments"][0]
    heals_over_time(segment)
    assert _heals(segment, LOR) == [(22.0, 420.0), (24.0, 420.0), (26.0, 505.0), (28.0, 420.0), (30.0, 420.0)]
    assert sum(a for _, a in _heals(segment, POTION)) == 4 * 419 + 5 * 320


def test_recuperations_instant_heals_stay_and_its_stacked_pools_are_rebuilt():
    """Its heal and "+5 % HP restored" carry 18120000; with "Heal over Time can stack up to 2 times" two pools of
    one caster run on one target."""
    events = [heal(5.0, CHANTER, TARGET, RECUPERATION, "Recuperation", 2770),            # the heal
              heal(5.0, CHANTER, TARGET, RECUPERATION, "Recuperation", 3652),            # +5 % HP restored
              *_pool_records(5.0, CHANTER, TARGET, RECUPERATION_STACKS, "Recuperation", 2901, 4),
              *_pool_records(5.5, CHANTER, TARGET, RECUPERATION_STACKS, "Recuperation", 2885, 4)]
    segment = _doc(events)["segments"][0]
    heals_over_time(segment)
    assert _heals(segment, RECUPERATION) == [(5.0, 2770.0), (5.0, 3652.0)]
    assert sorted(_heals(segment, RECUPERATION_STACKS)) == sorted(
        [(5.0 + 2 * k, 725.0) for k in range(1, 5)] + [(5.5 + 2 * k, 721.0) for k in range(1, 5)])


def test_spirits_benediction_ticks_every_second():
    events = _pool_records(3.0, TARGET, TARGET, BENEDICTION, "Enhance: Spirit's Benediction", 4007, 10, interval=1.0)
    segment = _doc(events)["segments"][0]
    heals_over_time(segment)
    assert _heals(segment) == [(3.0 + k, 400.0) for k in range(1, 11)]


def test_a_pool_seen_once_heals_nothing_but_an_instant_heal_under_its_id_stays():
    events = [heal(50.0, CLERIC, TARGET, LOR, "Light of Regeneration", 6000),           # cast as the fight ended
              heal(51.0, CLERIC, TARGET, 17100000, "Healing Light", 1400),              # not a heal over time
              heal(52.0, CHANTER, TARGET, RECUPERATION, "Recuperation", 2500)]          # Recuperation's own heal
    segment = _doc(events)["segments"][0]
    count = heals_over_time(segment)
    assert _heals(segment) == [(51.0, 1400.0), (52.0, 2500.0)]
    assert count["records"] == 2 and count["amount"] == 8500.0 and count["rebuilt"] == 2500.0


def test_only_an_older_meters_logs_are_rebuilt_and_only_once():
    events = _pool_records(10.0, CLERIC, TARGET, LOR, "Light of Regeneration", 5946, 15)
    assert meter_version(_doc(events, "0.2.385")) == (0, 2, 385)
    assert records_pools(_doc(events, "0.2.398")) and not records_pools(_doc(events, "0.2.399"))
    assert not records_pools(_doc(events, "0.2.404"))
    unnamed = _doc(events, None)
    assert not records_pools(unnamed)                                   # names no meter version
    other = _doc(events)
    other["meta"]["capture_quality"]["decoder"] = "another-meter"
    assert not records_pools(other)
    # a log of 0.2.399 or later holds ticks already: read as it is
    new = relabel(_doc([heal(12.0 + 2 * k, CLERIC, TARGET, LOR, "Light of Regeneration", 396) for k in range(15)],
                       "0.2.399"))
    assert sum(a for _, a in _heals(new["segments"][0])) == 15 * 396 and "heals_over_time" not in new["segments"][0]
    # an older one is rebuilt when read, keeps the count through the validator, and is not rebuilt again
    doc = relabel(_doc(events))
    segment = doc["segments"][0]
    assert sum(a for _, a in _heals(segment)) == 5940.0 and segment["heals_over_time"]["records"] == 16
    clean = a2log.validate(doc)
    assert clean["segments"][0]["heals_over_time"] == segment["heals_over_time"]
    again = relabel(clean)
    assert sum(a for _, a in _heals(again["segments"][0])) == 5940.0


def test_reading_an_older_log_recomputes_what_it_says_of_its_heals():
    """Its encounter insights (effective healing) and death recaps are recomputed from the rebuilt heals, and the
    healing share pools them."""
    doc = a2log.validate(_doc(_pool_records(10.0, CLERIC, TARGET, LOR, "Light of Regeneration", 5946, 15)))
    assert "heals_over_time" not in doc["segments"][0]                 # validating does not rebuild: reading does
    shares = _pool(doc, CLERIC)
    assert shares["total"] == pytest.approx(5940.0) and shares["skills"] == {"Light of Regeneration": 5940.0}
    before = doc["encounter_insights"]
    after = relabel(doc)["encounter_insights"]
    assert after is not before and after["segments"][0]["segment"] == before["segments"][0]["segment"]


def test_the_apps_review_of_a_saved_log_rebuilds_it_too():
    """The app's review reads a saved log through ``unnamed.rebuild_heals`` (``/api/sessions?file=``, and each part of
    a recording reviewed together), which rebuilds only an older meter's log and recomputes its summaries."""
    from aion2calc.combat.unnamed import rebuild_heals
    older = a2log.validate(_doc(_pool_records(10.0, CLERIC, TARGET, LOR, "Light of Regeneration", 5946, 15)))
    insights = older["encounter_insights"]
    assert rebuild_heals(older) is True
    assert sum(a for _, a in _heals(older["segments"][0])) == 5940.0 and older["encounter_insights"] is not insights
    assert rebuild_heals(older) is False                                 # rebuilt once
    newer = _doc([heal(12.0, CLERIC, TARGET, LOR, "Light of Regeneration", 396)], "0.2.399")
    assert rebuild_heals(newer) is False and _heals(newer["segments"][0]) == [(12.0, 396.0)]
