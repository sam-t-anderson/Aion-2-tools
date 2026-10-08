"""Export a bounded crafting snapshot from its publisher's public recipe graph."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

SOURCE = "https://gamers4.life/aion-2/database/crafting-graph.json"
PAGE = "https://gamers4.life/aion-2/database/en/crafting-calculator/"
MAX = 3 * 1024 * 1024
ID = re.compile(r"[1-9][0-9]{0,18}")


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError("Duplicate source key; review the changed recipe graph.")
        result[key] = value
    return result


def export(raw: bytes) -> dict:
    if len(raw) > MAX:
        raise ValueError("Recipe graph exceeds 3 MiB; review the changed source.")
    data = json.loads(raw, object_pairs_hook=_pairs)
    if not isinstance(data, dict) or set(data) != {"items", "recipes", "byProduct", "byCombo", "craftable"}:
        raise ValueError("Unexpected recipe graph schema.")
    items, recipes = {}, {}
    if not isinstance(data["items"], dict) or not isinstance(data["recipes"], dict) or len(data["recipes"]) > 10000:
        raise ValueError("Invalid recipe graph counts.")
    for key, item in data["items"].items():
        if not ID.fullmatch(key) or not isinstance(item, dict) or not isinstance(item.get("n"), str) or len(item["n"]) > 300:
            raise ValueError("Invalid item identity.")
        if item.get("g") not in {11, 21, 31, 41, 51}:
            raise ValueError("Unknown source item grade; review the changed graph.")
        image = item.get("ic", "")
        icon = ""
        if isinstance(image, str) and re.fullmatch(r"/assets/Game/[A-Za-z0-9_./-]+", image) and ".." not in image:
            icon = "https://gamers4.life/aion-2/database/icons" + image.split(".", 1)[0] + ".webp"
        items[key] = {"name": item["n"], "grade": item.get("g"), "icon": icon}
    for key, row in data["recipes"].items():
        if not ID.fullmatch(key) or not isinstance(row, dict) or set(row) != {"p", "qr", "mg", "ml", "gold", "in", "out", "outq", "cp", "combo"}:
            raise ValueError("Unexpected recipe fields.")
        if row["p"] not in {"blacksmithing", "tailoring", "jewelcrafting", "alchemy", "cooking"} or row["qr"] not in {"light", "dark"}:
            raise ValueError("Unknown profession or faction; review the source.")
        if row["out"] not in items or row["combo"] is not None and row["combo"] not in items:
            raise ValueError("Recipe output lacks an item record.")
        for field in ("ml", "gold", "outq", "cp"):
            if type(row[field]) is not int or not 0 <= row[field] <= (10000 if field == "cp" else 10**9):
                raise ValueError("Invalid recipe numeric field.")
        if row["cp"] and not row["combo"]:
            raise ValueError("Nonzero combo rate without a combo output.")
        if not row["outq"] or not isinstance(row["in"], list) or len(row["in"]) > 100:
            raise ValueError("Invalid recipe quantities.")
        inputs = []
        for entry in row["in"]:
            if not isinstance(entry, list) or len(entry) != 3 or entry[0] not in items or type(entry[1]) is not int or not 0 < entry[1] <= 10**9 or entry[2] is not None and entry[2] not in data["recipes"]:
                raise ValueError("Invalid material or intermediate recipe reference.")
            inputs.append({"item": entry[0], "quantity": entry[1], "recipe": entry[2]})
        recipes[key] = {"profession": row["p"], "faction": row["qr"], "mastery_group": row["mg"], "mastery_level": row["ml"],
                        "fee": row["gold"], "inputs": inputs, "output": row["out"], "quantity": row["outq"],
                        "combo": row["combo"], "combo_chance": row["cp"] / 10000,
                        "success_chance": None, "modifiers": None}
    return {"version": 1, "source": SOURCE, "source_page": PAGE,
            "retrieved_at": datetime.now(timezone.utc).isoformat(), "source_sha256": hashlib.sha256(raw).hexdigest(),
            "game_build": None, "region": None,
            "note": "Publisher-provided game-data snapshot; game build and region are not independently confirmed. Combo chance uses the source's 10,000-point rate scale. General craft success, failure rewards, combo quantity/replacement semantics and modifier rules are not supplied. Calculations are conditional planning assumptions, not live-game guarantees.",
            "items": items, "recipes": recipes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Previously downloaded public recipe graph; otherwise fetch the fixed source")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "aion2calc/app/static/crafting-catalog.json")
    args = parser.parse_args()
    if args.source:
        raw = args.source.read_bytes()
    else:
        with urlopen(Request(SOURCE, headers={"User-Agent": "aion2calc-catalog"}), timeout=30) as response:
            raw = response.read(MAX + 1)
    data = export(raw)
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Exported {len(data['recipes'])} recipes / {len(data['items'])} item references; build applicability unverified.")


if __name__ == "__main__":
    main()
