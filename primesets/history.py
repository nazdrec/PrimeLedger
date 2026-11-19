"""What each inventory update changed, and what the complete sets were worth day by day.

Two small files in the data folder:

  history.json        the list of parts after every update (an import or edits by hand), oldest
                      first; what changed between two neighbours is worked out when it is asked for
  value_history.json  the market value of the complete sets as the app showed it, one record a day

Nothing here talks to the game or to the market: it only remembers what the app already had.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import analysis, config

HISTORY_FILE = config.DATA_DIR / "history.json"
VALUES_FILE = config.DATA_DIR / "value_history.json"
KEEP_UPDATES = 200
KEEP_DAYS = 800
MANUAL_MERGE_SECONDS = 30 * 60          # edits by hand within half an hour are one update, not thirty

_lock = threading.RLock()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read(path: Path, default: Any) -> Any:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def _clean(items: Any) -> Dict[str, int]:
    out = {}
    for slug, count in (items or {}).items():
        try:
            if int(count) > 0:
                out[str(slug)] = int(count)
        except (TypeError, ValueError):
            continue
    return out


def _seconds_between(a: str, b: str) -> float:
    try:
        return abs((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds())
    except (TypeError, ValueError):
        return float("inf")


def _from_backups(current: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The first time: rebuild the past from the copies the app made before every import."""
    states = []
    folder = config.DATA_DIR / "backups"
    if folder.is_dir():
        for f in sorted(folder.glob("inventory-*.json")):
            box = _read(f, {})
            if isinstance(box.get("items"), dict) and box.get("updated_at"):
                states.append(box)
    if current and current.get("updated_at") and isinstance(current.get("items"), dict):
        states.append(current)
    states.sort(key=lambda s: str(s["updated_at"]))
    out: List[Dict[str, Any]] = []
    for s in states:
        items = _clean(s["items"])
        if not items or (out and out[-1]["items"] == items):
            continue
        out.append({"at": str(s["updated_at"]), "source": str(s.get("source") or ""), "note": str(s.get("note") or ""),
                    "mode": "", "items": items})
    return out


def _load(current: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    with _lock:
        if not HISTORY_FILE.exists():
            snaps = _from_backups(current)
            if snaps:
                _write(HISTORY_FILE, snaps)
            return snaps
        return [s for s in _read(HISTORY_FILE, []) if isinstance(s, dict) and isinstance(s.get("items"), dict)]


def sync(current: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Make sure the history ends with the inventory as it is now.

    It may have been changed past this module (a tool, an edit in the file itself); and the very
    first time the history is rebuilt from the backup copies, to which the present state belongs too.
    """
    with _lock:
        snaps = _load(current)
        items = _clean(current.get("items"))
        if items and (not snaps or snaps[-1]["items"] != items):
            snaps.append({"at": str(current.get("updated_at") or _now()), "source": str(current.get("source") or ""),
                          "note": str(current.get("note") or ""), "mode": "", "items": items})
            _write(HISTORY_FILE, snaps[-KEEP_UPDATES:])
        return snaps


def snapshot(items: Dict[str, int], source: str = "", note: str = "", mode: str = "") -> bool:
    """Remember the list of parts after an update.  Returns False when nothing changed."""
    items = _clean(items)
    with _lock:
        snaps = _load()
        if snaps and snaps[-1]["items"] == items:
            return False
        entry = {"at": _now(), "source": source, "note": note, "mode": mode, "items": items}
        manual = source == "manual"
        if (manual and len(snaps) >= 2 and snaps[-1].get("source") == "manual"
                and _seconds_between(snaps[-1]["at"], entry["at"]) <= MANUAL_MERGE_SECONDS):
            if snaps[-2]["items"] == items:
                snaps.pop()                      # the edits were undone: no update at all
            else:
                snaps[-1] = entry
        else:
            snaps.append(entry)
        _write(HISTORY_FILE, snaps[-KEEP_UPDATES:])
        return True


def _totals(catalog: Dict[str, Any], items: Dict[str, int]) -> Dict[str, Any]:
    complete = {r["slug"]: r["complete"] for r in analysis.split_inventory(catalog, items)["complete"]}
    return {"distinct": len(items), "total": sum(items.values()), "complete": len(complete),
            "copies": sum(complete.values()), "sets": complete}


def updates(catalog: Dict[str, Any], current: Optional[Dict[str, Any]] = None, limit: int = 40) -> List[Dict[str, Any]]:
    """What every update changed, the newest first: parts that came, went or changed their number,
    and the sets that became complete or stopped being so."""
    snaps = sync(current) if current is not None else _load()
    names = {p["slug"]: p["name"] for st in catalog["sets"].values() for p in st["parts"]}
    titles = {slug: st["title"] for slug, st in catalog["sets"].items()}
    out = []
    previous: Optional[Dict[str, Any]] = None
    previous_totals: Optional[Dict[str, Any]] = None
    for snap in snaps:
        items = snap["items"]
        totals = _totals(catalog, items)
        entry: Dict[str, Any] = {"at": snap["at"], "source": snap.get("source", ""), "note": snap.get("note", ""),
                                 "mode": snap.get("mode", ""), "first": previous is None,
                                 "distinct": totals["distinct"], "total": totals["total"],
                                 "complete": totals["complete"], "copies": totals["copies"],
                                 "added": [], "removed": [], "changed": [], "sets_up": [], "sets_down": []}
        if previous is not None and previous_totals is not None:
            before = previous["items"]
            entry.update({"distinct_before": previous_totals["distinct"], "total_before": previous_totals["total"],
                          "complete_before": previous_totals["complete"], "copies_before": previous_totals["copies"]})
            name = lambda slug: names.get(slug, slug)       # noqa: E731
            entry["added"] = sorted(({"slug": s, "item": name(s), "count": n} for s, n in items.items() if s not in before),
                                    key=lambda r: r["item"])
            entry["removed"] = sorted(({"slug": s, "item": name(s), "count": n} for s, n in before.items() if s not in items),
                                      key=lambda r: r["item"])
            entry["changed"] = sorted(({"slug": s, "item": name(s), "old": before[s], "new": n}
                                       for s, n in items.items() if s in before and before[s] != n), key=lambda r: r["item"])
            was, now = previous_totals["sets"], totals["sets"]
            for slug in sorted(set(was) | set(now), key=lambda s: titles.get(s, s)):
                old, new = was.get(slug, 0), now.get(slug, 0)
                if new != old:
                    entry["sets_up" if new > old else "sets_down"].append(
                        {"slug": slug, "title": titles.get(slug, slug), "old": old, "new": new})
        out.append(entry)
        previous, previous_totals = snap, totals
    out.reverse()
    return out[:limit]


# --------------------------------------------------------------------------- value by day
def record_value(value: float, sets: int, copies: int, priced: int) -> Dict[str, Any]:
    """Remember what the complete sets are worth today (the last figure of the day wins)."""
    with _lock:
        days = _read(VALUES_FILE, {})
        today = datetime.now().date().isoformat()
        days[today] = {"value": round(float(value)), "sets": int(sets), "copies": int(copies), "priced": int(priced),
                       "at": _now()}
        for old in sorted(days)[:-KEEP_DAYS]:
            del days[old]
        _write(VALUES_FILE, days)
        return days[today]


def values() -> List[Dict[str, Any]]:
    days = _read(VALUES_FILE, {})
    return [{"date": day, **rec} for day, rec in sorted(days.items()) if isinstance(rec, dict) and "value" in rec]
