"""A storage rollover is a memory-management flush that also resets the live view, so
its triggers (distinct players / segments retained) must measure real combat volume.

A Krao expedition reset the live meter repeatedly: in-instance phase teleports bump the
engine's zone-reset signal, which advances the identity epoch, and the rollover counters
were keyed on (epoch, actor) / (epoch, …). The same small party then looked like dozens
of distinct players and hundreds of segments as the epoch churned, tripping the 48-player
rollover again and again. These guard that epoch churn alone no longer inflates them."""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


def _hit(actor, target, t, dmg=500):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def test_phase_teleport_epoch_churn_does_not_inflate_the_rollover_counters():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    # A stable three-person party inside one instance; actor ids never change (a phase
    # teleport keeps them), only the zone-reset signal flips each phase.
    local, mates = 4062, (4063, 4064)
    engine.map_id = engine.dungeon_id = 600001
    engine.local_player_id = local
    engine.names = {local: "Me", mates[0]: "MateA", mates[1]: "MateB"}
    engine.known_players = {local, *mates}
    engine.roster = {name: {} for name in engine.names.values()}

    t = 10_000
    for phase in range(80):                     # 80 phase teleports in one sustained fight
        engine.last_zone_reset_ms = 1_000 + phase   # each phase flips the zone-reset signal
        # Keep hits inside gap_seconds of each other so no real time-gap segment forms.
        s.observe(engine, [_hit(local, 9001, t), _hit(mates[0], 9001, t + 500)], timestamp_ms=t + 500)
        t += 3_000

    assert s.epoch >= 80, s.epoch                 # the epoch really did churn

    players = s._storage_players.get("party", s.storage_players)
    groups = s._storage_groups.get("party", s.storage_groups)
    # Three party actors, one ongoing segment — nowhere near the 48 / 100 rollover thresholds,
    # even though the epoch advanced 80 times.
    assert len(players) <= 4, (len(players), players)
    assert groups <= 2, groups
