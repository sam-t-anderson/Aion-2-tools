"""Export community-measured crafting success/combo rates from metabot.gg.

The gamers4.life recipe graph (export_crafting_catalog.py) carries the combo *trigger*
rate but no craft *success* rate, and NCSoft publishes no official table. metabot.gg's
crafting calculator lists, per product, the base success chance at the recipe's own
proficiency (community-measured). This tool extracts that product table and writes a
small, source-attributed ``crafting-success.json`` keyed by product name, which the
crafting workshop matches to its recipes to show an actual success rate where available.

These are community-measured figures, not developer-confirmed; the output note says so.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html as _html
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

SOURCE = "https://metabot.gg/en/aion-2/crafting"
MAX = 8 * 1024 * 1024
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
# Product row: Name [\tFaction?] \t<mastery> \t<combo '—' or 'NN%'> \t<base '—' or 'NN.N%'>
_ROW = re.compile(
    r"\t([A-Z][A-Za-z'`()&.\- ]{2,48}?)\t(?:(?:Elyos|Asmodian)\t)?(\d{1,3})\t(—|\d{1,3}%)\t(—|\d{1,3}(?:\.\d)?%)\t")


def download(url: str, limit: int = MAX) -> bytes:
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={"User-Agent": UA, "Accept": "text/html"}), timeout=40) as response:
                raw = response.read(limit + 1)
            break
        except Exception:  # noqa: BLE001 - retried with backoff, then re-raised
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    if len(raw) > limit:
        raise ValueError("Crafting source exceeds its collection limit")
    return raw


def parse(raw: bytes) -> dict[str, dict]:
    """Product name (lower-case) -> {name, mastery, combo_chance, base_success}."""
    page = raw.decode("utf-8", "replace").replace('\\"', '"').replace("\\n", "\n")
    text = _html.unescape(re.sub(r"<[^>]+>", "\t", page))
    text = re.sub(r"[ \t]*\t[ \t]*", "\t", text)
    out: dict[str, dict] = {}
    for name, mastery, combo, base in _ROW.findall(text):
        name = name.strip()
        if name in ("Elyos", "Asmodian") or base == "—":
            continue
        succ = float(base.rstrip("%"))
        if not 0 < succ <= 100:
            continue
        out.setdefault(name.lower(), {
            "name": name, "mastery": int(mastery),
            "combo_chance": 0.0 if combo == "—" else int(combo.rstrip("%")) / 100,
            "base_success": succ})
    return out


def export(raw: bytes) -> dict:
    recipes = parse(raw)
    if len(recipes) < 80:
        raise ValueError(f"Only {len(recipes)} products parsed; the source layout may have changed — keep the prior snapshot.")
    return {
        "version": 1, "source": SOURCE,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "note": ("Community-measured crafting success and combo rates from metabot.gg, keyed by product "
                 "name; base_success is the measured chance at the recipe's own proficiency (+0). NCSoft "
                 "publishes no official success table, so these are community figures, not developer-confirmed, "
                 "and some players report crafting level has little visible effect. Success rises with "
                 "proficiency toward a per-tier cap and standard gear never reaches 100%."),
        "recipes": dict(sorted(recipes.items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Previously downloaded crafting page; otherwise fetch the fixed source")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "aion2calc/app/static/crafting-success.json")
    args = parser.parse_args()
    raw = args.source.read_bytes() if args.source else download(SOURCE)
    data = export(raw)
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Exported community success/combo rates for {len(data['recipes'])} products (community-measured, not official).")


if __name__ == "__main__":
    main()
