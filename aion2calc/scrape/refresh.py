"""Regenerate the normalized JSON data shipped in ``aion2calc/data``.

    python -m aion2calc refresh            # everything
    python -m aion2calc refresh --only sorcerer
"""
from __future__ import annotations

import json
from pathlib import Path

from . import a2dil, gamers4life, metabot

DATA = Path(__file__).resolve().parent.parent / "data"

# Items whose global stats we keep (popular L45 gear + best-in-slot candidates).
ITEM_SLUGS = [
    "spiritforged-spellbook", "rupture-tome", "ludras-grimoire", "splendent-wise-dragon-lord-spellbook",
    "splendent-ebony-dragon-lord-spellbook", "abyssal-spellbook", "aulamus-spellbook",
    "spiritforged-guard", "bakarma-guard",
    "vakron-helm", "vakron-pauldrons", "vakron-breastplate", "vakron-greaves", "vakron-gloves",
    "vakron-boots", "vakron-cloak",
    "bakarma-helm", "bakarma-pauldrons", "bakarma-breastplate", "bakarma-greaves", "bakarma-gloves",
    "bakarma-boots", "bakarma-cloak",
    "divine-canyon-helm", "divine-canyon-breastplate",
    "aulamus-necklace", "aulamus-earrings", "aulamus-ring",
    "liberator-necklace", "liberator-earrings", "liberator-ring",
    "ascension-bracelet", "liberator-bracelet", "abyssal-bracelet",
    "noble-belt", "revelation-amulet", "fierce-battle-amulet-rare", "clash-rune",
    ]


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def refresh(only: str | None = None, skip_kr: bool = False, items_only: bool = False) -> None:
    classes = [] if items_only else ([only] if only else metabot.CLASSES)
    for cls in classes:
        print(f"[metabot] {cls}")
        _dump(DATA / "global" / "classes" / f"{cls}.json", metabot.class_data(cls))
        if not skip_kr:
            print(f"[gamers4.life] {cls} hit profiles")
            kr_cls = "elementalist" if cls == "spiritmaster" else cls
            profiles = {}
            for sid in gamers4life.class_skill_ids(kr_cls):
                det = gamers4life.skill_detail(sid)
                profiles[sid] = {"name": det.get("name"), "hits": gamers4life.hit_profile(det)}
            _dump(DATA / "kr" / "hit_profiles" / f"{cls}.json", profiles)
            print(f"[a2dil] {cls}")
            summ = a2dil.class_summary(kr_cls if kr_cls in a2dil.KR_CLASS else cls)
            summ.pop("raw", None)
            _dump(DATA / "kr" / "a2dil" / f"{cls}.json", summ)
    if not only:
        print("[metabot] items")
        items = {}
        for slug in ITEM_SLUGS:
            try:
                items[slug] = metabot.item(slug)
            except Exception as err:  # renamed / missing pages are skipped
                print(f"  skip {slug}: {err}")
        _dump(DATA / "global" / "items.json", items)
        print("[metabot] titles")
        _dump(DATA / "global" / "titles.json", metabot.titles())
        print("[metabot] arcana skill pools")
        _dump(DATA / "global" / "arcana_skill_pools.json", metabot.arcana_skill_pools())
