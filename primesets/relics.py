"""The user's void relics: data/relics.json, filled from screenshots of the relic list (the sell
screen of the inventory, the "Relics" category).

What a relic holds comes from the official drop tables of Digital Extremes (droptables.py), how
it is named in each language and whether it is vaulted -- from the item list of warframe.market.
A line of the list is a relic at one refinement with its count: "Lith A13", flawless, x1.

The app never touches the game: the list comes from pictures the user made and can be corrected
by hand.
"""
from __future__ import annotations

import json
import os
import re
import threading
from collections import Counter
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import analysis, config, demo
from .i18n import tr
from .matching import normalize

RELICS_FILE = config.DATA_DIR / "relics.json"
VERSION = 1
MAX_COUNT = 9999
REFINEMENTS = analysis.REFINEMENTS

# the word in square brackets at the end of a caption, in the clients whose wording is known for certain
REFINEMENT_WORDS = {
    "необычная": "exceptional", "бесподобная": "flawless", "сияющая": "radiant", "нетронутая": "intact",
    "exceptional": "exceptional", "flawless": "flawless", "radiant": "radiant", "intact": "intact",
}
_BRACKET = re.compile(r"\s*[\[(（【]\s*([^\[\]()（）【】]+?)\s*[\])）】]\s*$")
_RELIC_EN = re.compile(r"^(\w+ \w+) Relic$")
_CODE = re.compile(r"^[a-zа-я]{1,2}\d{1,2}$")
# Cyrillic letters that look like Latin ones: a relic's code ("A13") is Latin, but next to Russian
# words it is easily written with the look-alike
_LOOKALIKE = str.maketrans("авекмнорстух", "abekmhopctyx")

_lock = threading.RLock()


def _tokens(text: str) -> List[str]:
    out = []
    for tok in normalize(text).split():
        out.append(tok.translate(_LOOKALIKE) if _CODE.match(tok) else tok)
    return out


class Index:
    """Every void relic: its names, what it holds and whether it can still be found."""

    def __init__(self, own: List[dict], game: Optional[List[dict]] = None, drops: Optional[Dict[str, Any]] = None):
        self.relics: Dict[str, Dict[str, Any]] = {}
        self._names: List[Tuple[List[str], str]] = []          # (tokens of a name, relic) in every known language
        by_en = {str(it.get("en") or "").lower(): it for it in own}
        # the drop tables write "Requiem Iv" where the market writes "Requiem IV": the case is not compared
        tables = {str(k).lower(): v for k, v in ((drops or {}).get("relics") or {}).items()}
        active = {str(k).lower() for k in (drops or {}).get("active") or []}
        for it in own:
            key = self._key(it)
            if not key:
                continue
            rewards = []
            for rw in tables.get(key.lower()) or []:
                base = by_en.get(str(rw.get("item") or "").lower())
                rewards.append({
                    "item": rw.get("item") or "",
                    "tier": analysis.relic_tier(rw.get("chance")),
                    "slug": base["slug"] if base else None,          # None: not traded (Forma, kuva...)
                    "name": base["name"] if base else (rw.get("item") or ""),
                    "thumb": base.get("thumb", "") if base else "",
                })
            order = {t: n for n, t in enumerate(reversed(analysis.RELIC_TIERS))}
            rewards.sort(key=lambda r: (order.get(r["tier"], 9), r["name"]))
            vaulted = it.get("vaulted")
            status = "unknown"
            if drops:
                status = ("missions" if key.lower() in active else "special" if vaulted is False
                          else "vaulted" if vaulted is True else "unknown")
            self.relics[key] = {"key": key, "slug": it["slug"], "name": it.get("name") or it["en"], "en": it["en"],
                                "era": key.split()[0].lower(), "thumb": it.get("thumb") or "", "status": status,
                                "rewards": rewards}
        # The word every name of a language shares ("Реликвия", "Relic", "Relikt") tells nothing: a caption
        # is matched without it, so the order of the words and a missing "Relic" do not matter.
        self._common: set = set()
        for listing, field in ((game or [], "name"), (own, "name"), (own, "en")):
            names = [(_tokens(it.get(field) or ""), self._key(it)) for it in listing]
            names = [(toks, key) for toks, key in names if toks and key in self.relics]
            seen = Counter(tok for toks, _ in names for tok in set(toks))
            self._common |= {tok for tok, n in seen.items() if n > len(names) * 0.6}
            self._names.extend(names)
        self.keys: Dict[frozenset, str] = {}
        for toks, key in self._names:
            own_words = frozenset(t for t in toks if t not in self._common)
            if own_words:
                self.keys.setdefault(own_words, key)

    @staticmethod
    def _key(item: dict) -> Optional[str]:
        if "relic" not in (item.get("tags") or []):
            return None
        m = _RELIC_EN.match(str(item.get("en") or ""))
        return m.group(1) if m else None

    def parse(self, caption: str, refinement: Any = None) -> Tuple[Optional[str], Optional[str]]:
        """(relic, refinement) out of a caption like "Реликвия Лит A13 [Бесподобная]".

        refinement -- what the reader of the screenshot made of the bracketed word; it is used only
        when the word itself is not one of those known for certain.  None for what cannot be told.
        """
        text = " ".join(str(caption or "").split())
        word = ""
        m = _BRACKET.search(text)
        if m:
            word, text = normalize(m.group(1)), text[:m.start()]
        level = REFINEMENT_WORDS.get(word)
        if level is None:
            level = refinement if refinement in REFINEMENTS else ("intact" if not word else None)
        words = frozenset(t for t in _tokens(text) if t not in self._common)
        key = self.keys.get(words)
        if key is None and words:
            # a caption with something extra in it: the relic whose own words are all there, if it is the only one
            inside = [(len(k), relic) for k, relic in self.keys.items() if k <= words]
            best = max((n for n, _ in inside), default=0)
            found = {relic for n, relic in inside if n == best}
            key = found.pop() if len(found) == 1 and best >= 2 else None
        return key, level


# --------------------------------------------------------------------------- the list on the disk
def empty() -> Dict[str, Any]:
    return {"version": VERSION, "updated_at": None, "items": [], "unknown": []}


def _clean_items(raw: Any) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[str, str], int] = {}
    for it in raw if isinstance(raw, list) else []:
        if not isinstance(it, dict):
            continue
        relic, level = str(it.get("relic") or ""), it.get("refinement")
        try:
            count = int(it.get("count") or 0)
        except (TypeError, ValueError):
            continue
        if not re.fullmatch(r"\w+ \w+", relic) or level not in REFINEMENTS or count <= 0:
            continue
        merged[(relic, level)] = min(MAX_COUNT, count)
    order = {level: n for n, level in enumerate(REFINEMENTS)}
    return [{"relic": relic, "refinement": level, "count": count}
            for (relic, level), count in sorted(merged.items(), key=lambda kv: (kv[0][0], order[kv[0][1]]))]


def load() -> Dict[str, Any]:
    if demo.on():
        return {"version": VERSION, "updated_at": demo.since(), "unknown": [],
                "items": [{"relic": r, "refinement": level, "count": n} for r, level, n in demo.RELICS]}
    try:
        data = json.loads(RELICS_FILE.read_text(encoding="utf-8"))
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
    tmp = RELICS_FILE.with_name(RELICS_FILE.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, RELICS_FILE)
    return data


def store(items: Iterable[Dict[str, Any]], unknown: Iterable[str] = (), mode: str = "replace") -> Dict[str, Any]:
    """Write what a reading found.  replace -- this is the whole list; merge -- the lines read are
    brought up to date and the rest of the list is kept."""
    with _lock:
        fresh = list(items)
        if mode == "merge":
            kept = load()
            fresh = kept["items"] + fresh                    # a later line of the same relic wins
            unknown = list(kept["unknown"]) + [u for u in unknown if u not in kept["unknown"]]
        return _write({"items": fresh, "unknown": [str(u)[:120] for u in unknown]})


def set_count(relic: str, refinement: str, count: Any) -> Dict[str, Any]:
    """A correction by hand: how many of this relic at this refinement there are (0 takes the line off)."""
    with _lock:
        if refinement not in REFINEMENTS:
            raise ValueError(tr("Такой строки в списке реликвий нет"))
        try:
            count = max(0, min(MAX_COUNT, int(count)))
        except (TypeError, ValueError):
            raise ValueError(tr("Количество должно быть числом")) from None
        data = load()
        left = [it for it in data["items"] if (it["relic"], it["refinement"]) != (relic, refinement)]
        if len(left) == len(data["items"]):
            raise ValueError(tr("Такой строки в списке реликвий нет"))
        if count:
            left.append({"relic": relic, "refinement": refinement, "count": count})
        return _write({"items": left, "unknown": data["unknown"]})


def forget_unknown() -> Dict[str, Any]:
    """The captions no relic was found for have been looked at."""
    with _lock:
        data = load()
        return _write({"items": data["items"], "unknown": []})


# --------------------------------------------------------------------------- what a reading means
def review(captions: List[Dict[str, Any]], index: Index) -> Dict[str, Any]:
    """The tiles read from the screenshots, each matched to its relic.

    captions: [{"name", "refinement", "count", "shot"}, ...].  The same tile seen on two screenshots
    (a list scrolled by less than a screen) is one line; if the two readings disagree about the count,
    the line is marked for a look and the larger number is kept.
    """
    entries: List[Dict[str, Any]] = []
    seen: Dict[Tuple[str, str], int] = {}
    for cap in captions:
        text = " ".join(str(cap.get("name") or "").split())
        if not text:
            continue
        key, level = index.parse(text, cap.get("refinement"))
        try:
            count = max(1, min(MAX_COUNT, int(cap.get("count") or 1)))
        except (TypeError, ValueError):
            count = 1
        if key is None or level is None:
            if ("", text.casefold()) not in seen:
                seen[("", text.casefold())] = len(entries)
                entries.append({"caption": text, "relic": None, "title": "", "refinement": level, "count": count,
                                "status": "unmatched", "shot": str(cap.get("shot") or "")})
            continue
        if (key, level) in seen:
            entry = entries[seen[(key, level)]]
            if entry["count"] != count:
                entry["count"], entry["status"] = max(entry["count"], count), "count"
            continue
        seen[(key, level)] = len(entries)
        entries.append({"caption": text, "relic": key, "title": index.relics[key]["name"], "refinement": level,
                        "count": count, "status": "ok", "shot": str(cap.get("shot") or "")})
    kinds = len({e["relic"] for e in entries if e["relic"]})
    return {"entries": entries, "matched": sum(1 for e in entries if e["relic"]),
            "unmatched": sum(1 for e in entries if not e["relic"]), "kinds": kinds}
