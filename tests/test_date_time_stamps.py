"""Every date the app and the website show carries the time of day: 2026-10-23 15:04:05.

The community logs, Saved Logs, My uploads, Your characters, the review, Saved Results, the news,
the timers and the Pages logs and leaderboard used to show a date alone (``toLocaleDateString``,
an ISO day) or the computer's own clock style (``toLocaleString``, 12-hour in en-US). Each script
now carries the same one-line ``whenAt`` stamp: the local date with a 24-hour ``HH:MM:SS`` clock."""
import os
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
SITE = ROOT / "site"
DATED = [STATIC / name for name in ("app.js", "combat-review.js", "community.js", "build-workspace.js", "crafting.js", "identity.js",
                                    "log-ownership.js", "logs-view.js", "saved-logs.js", "news.js", "timers.js", "maps.js")] \
    + [SITE / "logs.js", SITE / "leaderboard.js"]
WHEN = re.compile(r"const whenAt = \(x\) => \{.*?\};")
NODE_ENV = {**os.environ, "TZ": "UTC"}


def _node(probe: str) -> str:
    return subprocess.run(["node", "-e", probe], capture_output=True, text=True, check=True, env=NODE_ENV).stdout.strip()


def _stamp(path: pathlib.Path) -> str:
    match = WHEN.search(path.read_text(encoding="utf-8"))
    assert match, f"{path.name} shows dates but has no whenAt stamp"
    return match.group(0)


def test_every_script_that_shows_a_date_carries_the_same_stamp():
    stamps = {_stamp(path) for path in DATED}
    assert len(stamps) == 1, "one formatter, copied verbatim (each page script is self-contained)"


@pytest.mark.parametrize("path", DATED, ids=lambda p: p.name)
def test_the_stamp_is_the_local_date_with_a_24_hour_clock(path):
    probe = _stamp(path) + ('\nconsole.log([whenAt(1700000000000), whenAt("2024-01-02T03:04:05Z"), whenAt(Date.UTC(2026, 9, 23, 15, 4, 5)),'
                            ' whenAt(null), whenAt(undefined), whenAt(""), whenAt(NaN), whenAt("not a date")].join("|"))')
    assert _node(probe) == "2023-11-14 22:13:20|2024-01-02 03:04:05|2026-10-23 15:04:05|—|—|—|—|—"


def test_no_date_only_or_computer_style_render_remains():
    scripts = [p for p in STATIC.glob("*.js") if p.name not in ("html2canvas.min.js", "server-names.js")] + list(SITE.glob("*.js"))
    computer_style = re.compile(r"new Date\([^()]*(?:\([^()]*\)[^()]*)*\)\s*\.toLocale(?:Date|Time)?String\(")
    for path in scripts:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            where = f"{path.name}:{number}"
            assert "toLocaleDateString(" not in line and "toLocaleTimeString(" not in line, where
            assert not computer_style.search(line), where
            if "toISOString().slice(0,10)" in line or "toISOString().slice(0, 10)" in line:
                assert "preparedDay" in line, f"{where}: a day key is fine, a shown date is not"


@pytest.mark.parametrize("path, needle", [
    (STATIC / "logs-view.js", "const day = (ts) => whenAt(ts * 1000);"),           # Community Combat Logs: the Date column
    (SITE / "logs.js", "const day = (ts) => whenAt(ts * 1000);"),                 # the website's logs page
    (STATIC / "saved-logs.js", "const day = (ts) => whenAt(ts * 1000);"),         # Saved Logs
    (STATIC / "community.js", "<td>${whenAt(x.created_at*1000)}</td>"),           # All matching public attempts: Recorded
    (STATIC / "community.js", "<td>${whenAt(l.created_at*1000)}</td>"),           # the community table's Recorded column
    (STATIC / "combat-review.js", "whenAt((u.created_at || 0)*1000)"),            # Also recorded by …
    (STATIC / "combat-review.js", "const stamp=x=>x?whenAt(x*1000):\"Not recorded\";"),
    (STATIC / "identity.js", "const when=t=>t?whenAt(t*1000):'';"),               # Your characters
    (STATIC / "log-ownership.js", "const day=t=>t?whenAt(t*1000):'';"),           # My uploads holds and appeals
    (SITE / "leaderboard.js", 'const day=t=>t?whenAt(t*1000):"—";'),              # the leaderboard's Date column
    (STATIC / "app.js", "whenAt(r.created*1000)"),                                # Saved Results
    (STATIC / "app.js", "whenAt(s.db.last_sync.at * 1000)"),                      # Settings: the game database
    (STATIC / "app.js", "clockAt(segment.start)"),                                # the Live Meter's segment list
    (STATIC / "timers.js", "const local=t=>whenAt(t);"),
    (STATIC / "timers.js", "${localIn(next,zone)}"),                              # the event zone's own stamp
    (STATIC / "news.js", "const date=x=>{const s=whenAt(x);return s==='—'?'Date unavailable':s;};"),
    (STATIC / "crafting.js", "esc(whenAt(catalog.retrieved_at))"),
    (STATIC / "maps.js", "Catalog built ${esc(whenAt(data.generated_at))}."),
    (STATIC / "build-workspace.js", "esc(whenAt(x.updated_at))"),
])
def test_the_lists_and_pages_use_the_stamp(path, needle):
    assert needle in path.read_text(encoding="utf-8")


def test_the_live_meter_clock_is_the_time_of_day_alone():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    clock = re.search(r"const clockAt = \(x\) => \{.*?\};", app).group(0)
    probe = _stamp(STATIC / "app.js") + "\n" + clock + '\nconsole.log([clockAt(1700000000000), clockAt(null)].join("|"))'
    assert _node(probe) == "22:13:20|—"


def test_the_timers_zone_stamp_reads_the_same_in_the_event_zone():
    timers = (STATIC / "timers.js").read_text(encoding="utf-8")
    local_in = re.search(r"const localIn=\(t,zone\)=>\{.*?\}\};", timers).group(0)
    probe = ("const whenAt=x=>'local';const local=t=>whenAt(t);" + local_in +
             "\nconsole.log([localIn(1700000000000,'Asia/Seoul'), localIn(Date.UTC(2024,0,2,0,0,0),'UTC'), localIn(1700000000000,'Not/AZone')].join('|'))")
    assert _node(probe) == "2023-11-15 07:13:20|2024-01-02 00:00:00|local"      # h23: midnight is 00, never 24
