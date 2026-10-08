"""Collect ID-based image references and stage upstream catalog changes for review.

No downloaded code is executed. Gameplay catalogs are audited, never promoted here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from aion2calc.scrape import metabot
from aion2calc.scrape.catalog import REPOSITORY, stage

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc/app/static"


def download(url, limit, *, github=False):
    headers = {"User-Agent": "aion2calc-asset-refresh"}
    token = os.environ.get("GH_TOKEN")
    if github and token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Source exceeds its collection limit")
    return raw


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in ("retrieved_at", "checked_at")}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def run(name, *args):
    subprocess.run([sys.executable, str(ROOT / "tools" / name), *map(str, args)],
                   check=True, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--observed-build", default="",
                        help="Optional collection context, not a verified source-to-build mapping")
    args = parser.parse_args()
    if args.observed_build and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,99}", args.observed_build):
        raise ValueError("Invalid build observation label")
    generated = [STATIC / n for n in ("build-catalog.json", "crafting-catalog.json", "game-assets.json")]
    previous = {p: p.read_bytes() for p in generated if p.exists()}
    class_files = sorted((ROOT / "aion2calc/data/global/classes").glob("*.json"))
    refs = {}
    for file in class_files:
        data = metabot.class_data(file.stem, fresh=True)
        skills = data.get("skills")
        if not isinstance(skills, list) or not 10 <= len(skills) <= 500:
            raise ValueError("Class source layout changed; retain the previous snapshot")
        for skill in skills:
            key = skill.get("id")
            if type(key) is not int or not 0 < key < 2**63:
                raise ValueError("Invalid source skill ID")
            value = str(skill.get("icon") or "")
            if value.startswith("/api/image?"):
                value = parse_qs(urlparse(value).query).get("src", [""])[0]
            if not value:
                continue
            expected = f"https://metabot.gg/web/aion2/skills/{key}.webp"
            if value != expected:
                raise ValueError("Skill image reference disagrees with its source ID")
            refs[key] = {"id": key, "url": value}
    with tempfile.TemporaryDirectory(prefix="aion2-assets-") as temp:
        temp = Path(temp)
        additional = temp / "skills.json"
        additional.write_text(json.dumps(list(refs.values())), encoding="utf-8")
        run("export_build_catalog.py")
        run("export_crafting_catalog.py")
        refresh = ["--refresh-existing"] if args.refresh_existing else []
        run("export_game_assets.py", "--additional", additional, *refresh)
        npc_source = temp / "npcs.json"
        npc_source.write_bytes(download("https://dbaion2.ru/data-en/npcs.json", 8 * 1024 * 1024))
        run("export_npc_portraits.py", npc_source, *refresh)
        if json.loads((STATIC / "game-assets.json").read_bytes()).get("missing"):
            raise ValueError("One or more source images failed; retain the prior published snapshot")
        commits = json.loads(download(f"https://api.github.com/repos/{REPOSITORY}/commits?per_page=1",
                                      256 * 1024, github=True))
        revision = commits[0]["sha"]
        audit = stage(revision, temp / "catalog")
        # This audit makes unknown IDs and classification changes reviewable. It
        # does not overwrite parser tables or silently assign new boss roles.
        audit_path = ROOT / "docs/generated/asset-catalog-audit.json"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        old_audit = json.loads(audit_path.read_bytes()) if audit_path.exists() else None
        if old_audit is None or stable(old_audit) != stable(audit):
            audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = STATIC / "game-assets.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["collection_context"] = {
        "observed_build": args.observed_build or None,
        "source_build_mapping_verified": False,
        "note": "Published source IDs; collection time/context does not establish game-build applicability.",
    }
    manifest["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # Avoid a new pull request every day for timestamps alone. Source/content
    # changes, new IDs and changed image bytes remain visible in git diff.
    for path, old in previous.items():
        if stable(json.loads(old)) == stable(json.loads(path.read_bytes())):
            path.write_bytes(old)
    print("Collected source-ID image mappings; upstream gameplay changes remain in the audit.")


if __name__ == "__main__":
    main()
