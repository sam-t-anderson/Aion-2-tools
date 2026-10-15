"""The WCL-style parse on the website leaderboard and in the combat review's player table.

Both read the log server's ``parse`` (percentile among every character's best on the same
encounter / category / game version / difficulty for the same class; 100 = class best) and
``parse_characters``, colour it in the usual tiers (gold 100, pink 99+, orange 95+, purple 75+,
blue 50+, green 25+, grey) and dim brackets with fewer than five characters.
"""
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEADERBOARD_JS = (ROOT / "site" / "leaderboard.js").read_text(encoding="utf-8")
LEADERBOARD_HTML = (ROOT / "site" / "leaderboard.html").read_text(encoding="utf-8")
REVIEW_JS = (ROOT / "aion2calc" / "app" / "static" / "combat-review.js").read_text(encoding="utf-8")
SITE_CSS = (ROOT / "site" / "site.css").read_text(encoding="utf-8")
REVIEW_CSS = (ROOT / "aion2calc" / "app" / "static" / "combat-review.css").read_text(encoding="utf-8")
TIER = re.compile(r"const parseTier=p=>[^;]+;")


def _tiers(script):
    expr = TIER.search(script).group(0)
    probe = expr + "console.log(JSON.stringify([100,99.5,99,98,95,94.9,75,60,50,30,25,10,0].map(parseTier)))"
    return subprocess.run(["node", "-e", probe], capture_output=True, text=True, check=True).stdout.strip()


def test_both_renderers_share_the_same_parse_tiers():
    expected = '["gold","pink","pink","orange","orange","purple","purple","blue","blue","green","green","grey","grey"]'
    assert _tiers(LEADERBOARD_JS) == expected
    assert _tiers(REVIEW_JS) == expected


def test_leaderboard_shows_parse_kill_time_date_and_can_sort_by_parse():
    assert "<th class=\"r\">Parse</th>" in LEADERBOARD_JS and "parseHTML(e)" in LEADERBOARD_JS
    assert "e.parse_characters" in LEADERBOARD_JS and "provisional" in LEADERBOARD_JS
    assert "Kill time" in LEADERBOARD_JS and "killTime(e.duration)" in LEADERBOARD_JS and "day(e.created_at)" in LEADERBOARD_JS
    assert 'sort:$("#sort").value' in LEADERBOARD_JS and '$("#sort").onchange=load' in LEADERBOARD_JS
    assert '<select id="sort"><option value="score">Metric</option><option value="parse">Parse</option></select>' in LEADERBOARD_HTML
    assert ".parse{" in SITE_CSS and ".q-gold{--q:#e5cc80}" in SITE_CSS


def test_review_player_table_shows_each_players_parse_above_ability_contribution():
    # The column joins the server's rankings (one entry per player id) into the player table that
    # sits above the "Ability contribution" breakdown, and only on reviews that have rankings.
    assert "const parseOf=id=>(ranks?.players||[]).find(x=>x.id===id)" in REVIEW_JS
    assert '...(parseColumn?["Parse"]:[])' in REVIEW_JS and "parseHTML(p)" in REVIEW_JS
    assert "const parseColumn=!!options.rankings" in REVIEW_JS
    assert REVIEW_JS.index("parseHTML(p)") < REVIEW_JS.index("Ability contribution")
    assert ".parse{" in REVIEW_CSS and ".q-gold{--q:#e5cc80}" in REVIEW_CSS
