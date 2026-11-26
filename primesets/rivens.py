"""The user's riven mods: data/rivens.json, filled from screenshots of the mod list.

A riven mod is known here by the weapon it is for and by its own name ("Mantican", "Crita-ignitox").
The caption of a mod card reads "<weapon> <name of the mod>"; the weapon is found among the names
warframe.market gives for the weapons riven mods exist for -- in the language of the game client,
of the interface and in English.

The app never touches the game: the list comes from pictures the user made and can be corrected
by hand.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import config, demo
from .i18n import tr
from .matching import normalize

RIVENS_FILE = config.DATA_DIR / "rivens.json"
VERSION = 1
MAX_RIVENS = 400                 # far above what an account holds
FUZZY_WEAPON = 0.86              # a weapon's name read with a slip is still that weapon

_lock = threading.RLock()
_HYPHEN = re.compile(r"\s*[-‐‑–—]\s*")


def tidy(name: str) -> str:
    """The name of a riven mod as one word.  A caption broken over two lines after the hyphen
    ("Crita-" / "ignitox") comes back whole; and where the card's edge hid the hyphen ("Acri" /
    "parasus"), it is put back: the name of a riven mod has no spaces in it."""
    name = _HYPHEN.sub("-", " ".join(str(name or "").split())).strip("- ")
    if " " in name:
        name = name.replace(" ", "" if "-" in name else "-", 1).replace(" ", "")
    return name[:60]


class Weapons:
    """The weapons riven mods exist for, findable by any of their names."""

    def __init__(self, own: List[dict], game: Optional[List[dict]] = None):
        self.by_slug: Dict[str, dict] = {w["slug"]: w for w in own}
        self.keys: Dict[str, str] = {}
        for listing in (game or [], own):
            for w in listing:
                if w["slug"] not in self.by_slug:
                    continue
                for name in (w.get("name"), w.get("en")):
                    key = normalize(name or "")
                    if key:
                        self.keys.setdefault(key, w["slug"])

    def split(self, caption: str) -> Tuple[Optional[str], str, str]:
        """(weapon, name of the mod, status) out of the caption of a mod card.

        status: ok -- the weapon was found by its name; fuzzy -- by a name read with a slip, worth a
        look; unmatched -- no such weapon (a veiled mod, an ordinary mod, a misreading).
        """
        words = str(caption or "").split()
        for cut in range(len(words) - 1, 0, -1):          # the longest name first: "Dual Kamas" before "Kamas"
            slug = self.keys.get(normalize(" ".join(words[:cut])))
            if slug:
                return slug, tidy(" ".join(words[cut:])), "ok"
        for cut in range(len(words) - 1, 0, -1):
            key = normalize(" ".join(words[:cut]))
            if len(key) < 5:
                continue
            close = difflib.get_close_matches(key, self.keys, n=2, cutoff=FUZZY_WEAPON)
            if close and (len(close) == 1 or self.keys[close[0]] == self.keys[close[1]]):
                return self.keys[close[0]], tidy(" ".join(words[cut:])), "fuzzy"
        return None, tidy(caption), "unmatched"


# --------------------------------------------------------------------------- the list on the disk
def empty() -> Dict[str, Any]:
    return {"version": VERSION, "updated_at": None, "items": [], "unknown": []}


def _clean_items(raw: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for it in raw if isinstance(raw, list) else []:
        if not isinstance(it, dict):
            continue
        weapon, name = str(it.get("weapon") or ""), tidy(it.get("name") or "")
        key = (weapon, name.casefold())
        if not re.fullmatch(r"[a-z0-9_]{1,80}", weapon) or not name or key in seen:
            continue
        seen.add(key)
        out.append({"weapon": weapon, "name": name})
    return out[:MAX_RIVENS]


def load() -> Dict[str, Any]:
    if demo.on():
        return {"version": VERSION, "updated_at": demo.since(), "unknown": [],
                "items": [{"weapon": w, "name": n} for w, n in demo.RIVENS]}
    try:
        data = json.loads(RIVENS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty()
    if not isinstance(data, dict):
        return empty()
    unknown = [str(u)[:120] for u in data.get("unknown") if isinstance(u, str)] if isinstance(data.get("unknown"), list) else []
    return {"version": VERSION, "updated_at": data.get("updated_at") if isinstance(data.get("updated_at"), str) else None,
            "items": _clean_items(data.get("items")), "unknown": unknown[:60]}


def _write(data: Dict[str, Any]) -> Dict[str, Any]:
    if demo.on():
        raise ValueError(tr("Сейчас показан пример инвентаря. Уберите пример, чтобы вносить изменения."))
    data = {"version": VERSION, "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "items": _clean_items(data.get("items")), "unknown": list(data.get("unknown") or [])[:60]}
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = RIVENS_FILE.with_name(RIVENS_FILE.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, RIVENS_FILE)
    return data


def store(items: Iterable[Dict[str, str]], unknown: Iterable[str] = (), mode: str = "replace") -> Dict[str, Any]:
    """Write what a reading found.  replace -- this is the whole list; merge -- add it to what is kept."""
    with _lock:
        fresh = _clean_items(list(items))
        if mode == "merge":
            kept = load()
            fresh = _clean_items(kept["items"] + fresh)
            unknown = list(kept["unknown"]) + [u for u in unknown if u not in kept["unknown"]]
        return _write({"items": fresh, "unknown": [str(u)[:120] for u in unknown]})


def remove(weapon: str, name: str) -> Dict[str, Any]:
    """The mod is gone (sold, dissolved): take it off the list."""
    with _lock:
        data = load()
        key = (str(weapon), tidy(name).casefold())
        left = [it for it in data["items"] if (it["weapon"], it["name"].casefold()) != key]
        if len(left) == len(data["items"]):
            raise ValueError(tr("Такого мода в списке нет"))
        return _write({"items": left, "unknown": data["unknown"]})


def forget_unknown() -> Dict[str, Any]:
    """The captions no weapon was found for have been looked at."""
    with _lock:
        data = load()
        return _write({"items": data["items"], "unknown": []})


# --------------------------------------------------------------------------- what a reading means
def review(captions: List[Dict[str, str]], weapons: Weapons) -> Dict[str, Any]:
    """The captions read from the screenshots, each matched to its weapon.

    captions: [{"name": the caption, "shot": the screenshot it stands on}, ...].  One mod seen on two
    screenshots (a list scrolled by less than a screen) is one mod.
    """
    entries: List[Dict[str, Any]] = []
    seen: Dict[Tuple[str, str], int] = {}
    for cap in captions:
        text = " ".join(str(cap.get("name") or "").split())
        if not text:
            continue
        slug, name, status = weapons.split(text)
        key = (slug or "", (name if slug else text).casefold())
        if key in seen:
            continue
        seen[key] = len(entries)
        weapon = weapons.by_slug.get(slug) if slug else None
        entries.append({"caption": text, "weapon": slug, "title": weapon["name"] if weapon else "",
                        "name": name if slug else "", "status": status, "shot": str(cap.get("shot") or "")})
    return {"entries": entries, "matched": sum(1 for e in entries if e["weapon"]),
            "unmatched": sum(1 for e in entries if not e["weapon"])}
