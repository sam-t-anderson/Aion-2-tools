"""Collect ID-based image references and stage upstream catalog changes for review.

No downloaded code is executed. Gameplay catalogs are audited, never promoted here.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aion2calc.scrape import metabot
from aion2calc.scrape.http import NotFound
from aion2calc.scrape.catalog import REPOSITORY, stage

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc/app/static"


RETRIES = 5


def _transient(error):
    """A dropped connection, a timeout, a rate limit or a server error: worth asking again. A refusal (403) or
    any other 4xx is not."""
    if isinstance(error, HTTPError):
        return error.code == 429 or 500 <= error.code < 600
    return isinstance(error, (URLError, TimeoutError, ConnectionError, OSError))


def download(url, limit, *, github=False):
    headers = {"User-Agent": "aion2calc-asset-refresh"}
    token = os.environ.get("GH_TOKEN")
    if github and token:
        headers["Authorization"] = "Bearer " + token
    for attempt in range(RETRIES):
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as response:
                raw = response.read(limit + 1)
            break
        except Exception as error:  # noqa: BLE001 - re-raised below unless transient
            # DBAion2 dropped the runner's TLS handshake on 19 November 2026 (SSL: UNEXPECTED_EOF)
            if attempt + 1 >= RETRIES or not _transient(error):
                raise
            time.sleep(2 ** (attempt + 1))  # 2, 4, 8, 16 s
    if len(raw) > limit:
        raise ValueError("Source exceeds its collection limit")
    return raw


def previous_npc_rows(portraits_path):
    """The NPC rows the published portraits were matched from (id, name, icon name), so the portrait step can
    rebuild them unchanged while DBAion2's NPC table cannot be read."""
    if not portraits_path.exists():
        raise ValueError("No previous NPC portraits to keep while DBAion2's NPC table is unavailable")
    rows = []
    for key, row in json.loads(portraits_path.read_bytes()).items():
        icon = re.fullmatch(r"https://dbaion2\.ru/icons/([A-Za-z0-9_]{1,120})\.webp", str(row.get("icon", "")))
        if re.fullmatch(r"[0-9]{1,19}", key) and icon:
            rows.append({"id": int(key), "name": row.get("name", ""), "icon": icon[1]})
    return rows


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in ("retrieved_at", "checked_at", "item_details_retrieved_at")}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def run(name, *args):
    subprocess.run([sys.executable, str(ROOT / "tools" / name), *map(str, args)],
                   check=True, cwd=ROOT)


class SourceUnavailable(RuntimeError):
    """The class pages could not be read at all (refused or unreachable), as opposed to read and invalid."""


def class_skill_refs(class_files):
    """Each class page's skill IDs and icon references, validated against their IDs."""
    refs = {}
    for file in class_files:
        try:
            data = metabot.class_data(file.stem, fresh=True)
        except (NotFound, RuntimeError, OSError) as exc:
            raise SourceUnavailable(str(exc)) from exc
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
    return refs


DBAION2_SKILLS = "https://dbaion2.ru/data-en/skills.json"
DBAION2_ICON = "https://dbaion2.ru/icons/{}.webp"


def dbaion2_skill_icons(raw):
    """``{skill id: DBAion2 icon URL}`` from DBAion2's English skill table (the game's skill ids, the same ones
    metabot.gg files its icons under, and the game's own icon names), or ``ValueError`` for a shape not reviewed."""
    rows = json.loads(raw)
    if not isinstance(rows, list) or not 10 <= len(rows) <= 5000:
        raise ValueError("DBAion2 skill table layout changed")
    icons = {}
    for row in rows:
        key, icon = (row.get("id"), row.get("icon")) if isinstance(row, dict) else (None, None)
        if type(key) is not int or not 0 < key < 2**63:
            raise ValueError("Invalid DBAion2 skill ID")
        if icon is None:
            continue
        if not isinstance(icon, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,80}", icon):
            raise ValueError("Invalid DBAion2 skill icon name")
        icons[key] = DBAION2_ICON.format(icon)
    return icons


def previous_skill_refs(manifest_path):
    """The skill icon references the published snapshot holds, in the form ``class_skill_refs`` returns."""
    if not manifest_path.exists():
        raise ValueError("No previous asset snapshot to keep while the skill icon source is unavailable")
    references = json.loads(manifest_path.read_bytes()).get("references", {})
    refs = {}
    for name, row in references.items():
        if not name.startswith("metabot:skill:"):
            continue
        key = int(row["id"])
        if row.get("url") == f"https://metabot.gg/web/aion2/skills/{key}.webp":
            refs[key] = {"id": key, "url": row["url"]}
    return refs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--observed-build", default="",
                        help="Optional collection context, not a verified source-to-build mapping")
    args = parser.parse_args()
    if args.observed_build and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,99}", args.observed_build):
        raise ValueError("Invalid build observation label")
    generated = [STATIC / n for n in ("build-catalog.json", "crafting-catalog.json", "crafting-success.json", "game-assets.json")]
    previous = {p: p.read_bytes() for p in generated if p.exists()}
    class_files = sorted((ROOT / "aion2calc/data/global/classes").glob("*.json"))
    # DBAion2 (dbaion2.ru, already the source of the NPC portraits and item names) is the second source for
    # skill icons: its table names the game's icon for each skill id. Without it the refresh still runs.
    try:
        backup = dbaion2_skill_icons(download(DBAION2_SKILLS, 16 * 1024 * 1024))
    except Exception as exc:  # noqa: BLE001 - only the second source; metabot.gg remains the first
        backup = {}
        print(f"::warning::DBAion2 skill table unavailable ({exc}); no second source for skill icons")
    try:
        refs = class_skill_refs(class_files)
    except SourceUnavailable as exc:
        # metabot.gg has refused this runner (HTTP 403 since 12 November 2026). The skill list comes from the
        # snapshot and DBAion2's table, and an icon metabot.gg will not serve is taken from DBAion2. A class
        # page that answers with a changed layout still fails the run.
        refs = previous_skill_refs(STATIC / "game-assets.json")
        refs.update({key: {"id": key, "url": f"https://metabot.gg/web/aion2/skills/{key}.webp"}
                     for key in backup if key not in refs})
        print(f"::warning::metabot.gg class pages unavailable ({exc}); {len(refs)} skill icons from the "
              + ("snapshot and DBAion2's skill table" if backup else "snapshot"))
    mirrors = {row["url"]: backup[key] for key, row in refs.items() if key in backup}
    with tempfile.TemporaryDirectory(prefix="aion2-assets-") as temp:
        temp = Path(temp)
        additional = temp / "skills.json"
        additional.write_text(json.dumps(list(refs.values())), encoding="utf-8")
        mirror_file = temp / "mirrors.json"
        mirror_file.write_text(json.dumps(mirrors), encoding="utf-8")
        run("export_build_catalog.py")
        run("export_crafting_catalog.py")
        try:
            run("export_crafting_success.py")
        except Exception as exc:  # noqa: BLE001 - community success rates are optional; keep the prior snapshot
            print(f"Crafting success refresh skipped (keeping prior snapshot): {exc}")
        refresh = ["--refresh-existing"] if args.refresh_existing else []
        run("export_game_assets.py", "--additional", additional, "--mirrors", mirror_file, *refresh)
        npc_source = temp / "npcs.json"
        try:
            npc_source.write_bytes(download("https://dbaion2.ru/data-en/npcs.json", 8 * 1024 * 1024))
            kept = []
        except Exception as exc:  # noqa: BLE001 - keep the published portraits rather than drop them all
            rows = previous_npc_rows(ROOT / "aion2calc/meter/a2parser/data/i18n/npc-portraits/en.json")
            npc_source.write_text(json.dumps(rows), encoding="utf-8")
            record = temp / "npc-source.json"
            old = previous.get(STATIC / "game-assets.json")
            record.write_text(json.dumps(json.loads(old).get("npc_portrait_source") if old else None), encoding="utf-8")
            kept = ["--from-snapshot", record]
            print(f"::warning::DBAion2 NPC table unavailable ({exc}); keeping the {len(rows)} published portraits")
        run("export_npc_portraits.py", npc_source, *refresh, *kept)
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
    manifest["asset_sha256"] = {url: hashlib.sha256((STATIC / path).read_bytes()).hexdigest()
                                for url, path in sorted(manifest["assets"].items())}
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
