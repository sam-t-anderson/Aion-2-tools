"""The log review's run-speed standings say why a scope is missing. A timed run that one scope cannot place
(the Server scope of a party with no verified home world) read "Not a timed run" beside its Region and World
ranks; only a run that is not speed-eligible says that now. A Server rank on the recording player's world says
so (log server 0.2.113 ranks a party drawn from several worlds there)."""
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "combat-review.js"


def test_a_missing_scope_of_a_timed_run_is_not_called_untimed():
    js = SCRIPT.read_text(encoding="utf-8")
    run = js[js.index("if(context==='run'){"):js.index("`Not a timed run — run speed")]
    assert "ranks.run_detail?.speed_eligible" in run                          # eligible runs never reach the text
    assert "the run has no Server cohort. Region and World still rank it." in run
    assert "x.basis==='recording_player'" in js and "On the recording player’s world" in js
    subprocess.run(["node", "--check", str(SCRIPT)], check=True)
