"""Catalog of prime sets: members, quantities, localized names and vault status.

Built from two public sources:
  * warframe.market API  -- which items form a set and how many of each part it needs;
  * DE drop tables       -- which relics hold each part and whether they still drop.

Names come in three languages: of the interface (shown), English (the drop tables, messages to
sellers) and of the game client (what the screenshots say; often the same as the interface).
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

from . import config, droptables, i18n
from .cache import DiskCache
from .i18n import tr
from .wfm import FetchError, WfmClient

CATALOG_VERSION = 4

ProgressFn = Callable[[str, int, int], None]

# ": Комплект", " Set", ": Set", " - Set", ": Zestaw", " 一套" at the end of a set's name
_SET_SUFFIX = re.compile(r"(?:\s*[:\-–—]\s*|\s+)(?:комплект|set|zestaw|一套)\s*$", re.IGNORECASE)
_BLUEPRINT_RU = re.compile(r"\(\s*черт[её]ж\s*\)", re.IGNORECASE)
_PRIME_HEAD = re.compile(r"^.*?\b(?:прайм|prime)\b\s*[:\-–—]?\s*", re.IGNORECASE)

CATEGORY_ORDER = ["warframe", "primary", "secondary", "melee", "sentinel", "archwing", "other"]
# what the part that is the blueprint of the whole item is called in each language
BLUEPRINT_LABEL = {"ru": "Чертёж", "en": "Blueprint", "de": "Blaupause", "fr": "Schéma", "pl": "Schemat", "zh": "蓝图"}


def cache_key(lang: str, game_lang: str) -> str:
    return f"catalog_{lang}_{game_lang}"


def set_title(name: str) -> str:
    """'Мираж Прайм: Комплект' -> 'Мираж Прайм', 'Mirage Prime Set' -> 'Mirage Prime'."""
    return _SET_SUFFIX.sub("", name).strip() or name


def part_label(part_name: str, title: str, lang: str) -> str:
    """The short name of a part inside its set: 'Мираж Прайм: Система (Чертеж)' -> 'Система (чертёж)',
    'Mirage Prime Systems Blueprint' -> 'Systems Blueprint', 'Mirage Prime Blueprint' -> 'Blueprint'."""
    label = part_name
    idx = label.lower().find(title.lower())
    if title and idx >= 0:
        label = label[:idx] + label[idx + len(title):]
    else:
        # the set is named differently from its parts ("Ошейник Кубрау: Каваса Прайм" vs
        # "Каваса Прайм: Лента"): drop everything up to "Прайм:"
        label = _PRIME_HEAD.sub("", label, count=1)
    if lang == "ru":
        label = _BLUEPRINT_RU.sub("(чертёж)", label)
    label = re.sub(r"\s+", " ", label).strip(" :—–-")
    word = BLUEPRINT_LABEL.get(lang, BLUEPRINT_LABEL["en"])
    if label.strip("() ").casefold().replace("ё", "е") in ("", word.casefold().replace("ё", "е")):
        return word
    return label[0].upper() + label[1:]


def category_of(tags: List[str]) -> str:
    tags = set(tags or [])
    if "warframe" in tags:
        return "warframe"
    if "sentinel" in tags:
        return "sentinel"
    if "archwing" in tags:
        return "archwing"
    for cat in ("primary", "secondary", "melee"):
        if cat in tags:
            return cat
    return "other"


def _availability(relics: List[dict]) -> str:
    if not relics:
        return "unknown"
    if any(r["drops"] for r in relics):
        return "missions"
    if any(r["wfm_vaulted"] is False for r in relics):
        return "special"
    return "vaulted"


def _vault_state(parts: List[dict]) -> Dict[str, Any]:
    states = [p["availability"] for p in parts]
    known = [s for s in states if s != "unknown"]
    vaulted_parts = sum(1 for s in states if s == "vaulted")
    info = {"vaulted_parts": vaulted_parts, "total_parts": len(parts)}
    if not known:
        info["state"] = "unknown"
    elif all(s == "vaulted" for s in known):
        info["state"] = "vaulted"
    elif vaulted_parts:
        info["state"] = "partial"
    elif any(s == "missions" for s in known):
        info["state"] = "available"
    else:
        info["state"] = "special"
    return info


def build(wfm: WfmClient, cache: DiskCache, progress: Optional[ProgressFn] = None,
          force: bool = False, lang: str = "ru", game_lang: Optional[str] = None) -> Dict[str, Any]:
    """Download what is missing and assemble the catalog. Network errors propagate as FetchError
    unless an older copy of the same data is available on disk.

    lang -- the language of the interface, game_lang -- of the game client (codes of i18n.LANGS)."""
    game_lang = game_lang or lang
    def report(stage: str, done: int, total: int) -> None:
        if progress:
            progress(stage, done, total)

    report(tr("Список предметов warframe.market"), 0, 1)
    items, items_meta = wfm.items(i18n.LANGS[lang]["wfm"], force=force)
    by_id = {it["id"]: it for it in items}
    by_slug = {it["slug"]: it for it in items}
    game_names: Dict[str, str] = {}
    if game_lang != lang:
        try:
            game_names = {it["slug"]: it["name"] for it in wfm.items(i18n.LANGS[game_lang]["wfm"], force=force)[0]}
        except FetchError:
            pass                    # captions are then matched by the interface language and English only
    report(tr("Список предметов warframe.market"), 1, 1)

    report(tr("Таблицы дропа Digital Extremes"), 0, 1)
    drops: Optional[Dict[str, Any]] = None
    drops_meta: Dict[str, Any] = {"fetched_at": None, "stale": False, "error": None}
    try:
        drops, drops_meta = droptables.load(cache, wfm.assets, force=force)
    except FetchError as exc:
        drops_meta = {"fetched_at": None, "stale": True, "error": str(exc)}
    report(tr("Таблицы дропа Digital Extremes"), 1, 1)

    # relic name ("Axi A1") -> vaulted flag as shown on warframe.market
    wfm_relic_flag: Dict[str, Optional[bool]] = {}
    for it in items:
        if "relic" in it["tags"]:
            m = re.match(r"^(\w+ \w+) Relic$", it["en"])
            if m:
                wfm_relic_flag[m.group(1)] = it.get("vaulted")

    # part name (lower-case English) -> relics that contain it
    relics_of: Dict[str, List[dict]] = {}
    if drops:
        active = set(drops["active"])
        for relic, rewards in drops["relics"].items():
            for rw in rewards:
                relics_of.setdefault(rw["item"].lower(), []).append({
                    "name": relic,
                    "drops": relic in active,
                    "wfm_vaulted": wfm_relic_flag.get(relic),
                    "rarity": rw.get("rarity") or "",
                    "chance": rw.get("chance"),
                })
        for lst in relics_of.values():
            lst.sort(key=lambda r: (not r["drops"], r["name"]))

    set_items = sorted(
        (it for it in items if "prime" in it["tags"] and "set" in it["tags"]),
        key=lambda it: it["slug"],
    )
    sets: Dict[str, Any] = {}
    part_index: Dict[str, str] = {}
    failed: List[str] = []
    total = len(set_items)
    for n, root in enumerate(set_items, 1):
        report(tr("Состав комплектов"), n - 1, total)
        try:
            members, _ = wfm.item_set(root["slug"], force=False)
        except FetchError:
            failed.append(root["slug"])
            continue
        title = set_title(root["name"])
        title_en = set_title(root["en"])
        parts = []
        for mem in members:
            if mem["set_root"] or mem["slug"] == root["slug"]:
                continue
            base = by_slug.get(mem["slug"]) or by_id.get(mem["id"])
            if not base:
                continue
            relics = relics_of.get(base["en"].lower(), [])
            label = part_label(base["name"], title, lang)
            parts.append({
                "slug": base["slug"],
                "en": base["en"],
                "name": base["name"],
                "game": game_names.get(base["slug"]) or base["name"],
                "label": label,
                "main": label == BLUEPRINT_LABEL.get(lang, BLUEPRINT_LABEL["en"]),
                "quantity": max(1, int(mem.get("quantity") or 1)),
                "thumb": base["thumb"],
                "ducats": base.get("ducats"),
                "blueprint": "blueprint" in base["tags"] or base["en"].lower().endswith("blueprint"),
                "relics": relics,
                "availability": _availability(relics) if drops else "unknown",
            })
        if not parts:
            continue
        # main blueprint first, then the rest by name: reads naturally in the UI
        parts.sort(key=lambda p: (not p["main"], p["label"]))
        sets[root["slug"]] = {
            "slug": root["slug"],
            "id": root["id"],
            "name": root["name"],
            "en": root["en"],
            "title": title,
            "title_en": title_en,
            "title_game": set_title(game_names.get(root["slug"]) or root["name"]),
            "thumb": root["thumb"],
            "ducats": root.get("ducats"),
            "category": category_of(root["tags"]),
            "parts": parts,
            "vault": _vault_state(parts),
        }
        for p in parts:
            part_index[p["slug"]] = root["slug"]
    report(tr("Состав комплектов"), total, total)

    if not sets:
        raise FetchError("catalog: no prime sets could be loaded")

    catalog = {
        "version": CATALOG_VERSION,
        "lang": lang,
        "game_lang": game_lang,
        "built_at": time.time(),
        "items_fetched_at": items_meta.get("fetched_at"),
        "items_stale": bool(items_meta.get("stale")),
        "droptables": {
            "updated": (drops or {}).get("updated", ""),
            "fetched_at": drops_meta.get("fetched_at"),
            "stale": bool(drops_meta.get("stale")),
            "error": drops_meta.get("error"),
            "available": drops is not None,
            "relic_count": len((drops or {}).get("relics", {})),
            "active_count": len((drops or {}).get("active", [])),
        },
        "failed_sets": failed,
        "sets": sets,
        "part_index": part_index,
    }
    cache.put(cache_key(lang, game_lang), catalog)
    return catalog


def load_cached(cache: DiskCache, max_age: Optional[float] = config.TTL_CATALOG, lang: str = "ru",
                game_lang: Optional[str] = None) -> Optional[Dict[str, Any]]:
    hit = cache.get(cache_key(lang, game_lang or lang), max_age)
    if hit is None:
        return None
    data = hit[0]
    if not isinstance(data, dict) or data.get("version") != CATALOG_VERSION or not data.get("sets"):
        return None
    return data
