"""The user's prime parts: a plain JSON file inside the app folder.

It is written either by the import tool (names read from the user's own
screenshots) or by manual edits in the interface.  Nothing here talks to the game.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from . import config, demo, history
from .i18n import tr
from .matching import Match, Matcher, normalize

INVENTORY_VERSION = 1
IGNORED_FILE = config.DATA_DIR / "ignored_names.json"
_lock = threading.RLock()


def ignored_names() -> set:
    """Names from the screen that are not prime parts and that the user asked not to hear about again
    (the game has items with «Прайм» in the name that belong to no set)."""
    try:
        data = json.loads(IGNORED_FILE.read_text(encoding="utf-8"))
        return {str(n) for n in data} if isinstance(data, list) else set()
    except (OSError, ValueError):
        return set()


def ignore_name(name: str) -> None:
    key = normalize(name)
    if not key:
        return
    with _lock:
        names = ignored_names()
        names.add(key)
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = IGNORED_FILE.with_name(IGNORED_FILE.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(sorted(names), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, IGNORED_FILE)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def empty() -> Dict[str, Any]:
    return {"version": INVENTORY_VERSION, "updated_at": None, "source": None, "note": "", "items": {}, "review": []}


def load() -> Dict[str, Any]:
    if demo.on():                       # the made-up list the user asked to look at; the real file is not touched
        inv = empty()
        inv.update({"items": dict(demo.ITEMS), "source": "demo", "updated_at": demo.since()})
        return inv
    with _lock:
        try:
            raw = config.INVENTORY_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError):
            return empty()
    inv = empty()
    if isinstance(data, dict):
        inv.update({k: data[k] for k in ("updated_at", "source", "note") if k in data})
        items = data.get("items")
        if isinstance(items, dict):
            for slug, count in items.items():
                try:
                    n = int(count)
                except (TypeError, ValueError):
                    continue
                if isinstance(slug, str) and n > 0:
                    inv["items"][slug] = n
        review = data.get("review")
        if isinstance(review, list):
            inv["review"] = [_review_entry(r) for r in review if isinstance(r, dict)]
    return inv


def _review_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Notes written by the first version of the app called the catalog name "ru"."""
    entry = dict(entry)
    if "ru" in entry:
        entry.setdefault("item", entry.pop("ru"))
    if isinstance(entry.get("suggestions"), list):
        entry["suggestions"] = [{"slug": s.get("slug"), "item": s.get("item") or s.get("ru") or ""}
                                for s in entry["suggestions"] if isinstance(s, dict)]
    return entry


def _backup() -> None:
    src = config.INVENTORY_FILE
    if not src.exists():
        return
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = config.BACKUP_DIR / f"inventory-{stamp}.json"
    n = 1
    while dst.exists():
        n += 1
        dst = config.BACKUP_DIR / f"inventory-{stamp}-{n}.json"
    shutil.copy2(src, dst)
    old = sorted(config.BACKUP_DIR.glob("inventory-*.json"))
    for extra in old[:-30]:
        try:
            extra.unlink()
        except OSError:
            pass


def save(inv: Dict[str, Any], source: Optional[str] = None, backup: bool = True) -> Dict[str, Any]:
    if demo.on():
        raise ValueError(tr("Сейчас показан пример инвентаря. Уберите пример, чтобы вносить изменения."))
    with _lock:
        if backup:
            _backup()
        inv = dict(inv)
        inv["version"] = INVENTORY_VERSION
        inv["updated_at"] = _now_iso()
        if source:
            inv["source"] = source
        inv["items"] = {k: int(v) for k, v in sorted(inv.get("items", {}).items()) if int(v) > 0}
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = config.INVENTORY_FILE.with_name(config.INVENTORY_FILE.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(inv, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, config.INVENTORY_FILE)
        return inv


def mtime() -> float:
    try:
        return config.INVENTORY_FILE.stat().st_mtime
    except OSError:
        return 0.0


def _not_the_example() -> None:
    """Nothing is written -- not even into the history -- while the made-up inventory is on show."""
    if demo.on():
        raise ValueError(tr("Сейчас показан пример инвентаря. Уберите пример, чтобы вносить изменения."))


def set_count(slug: str, count: int, catalog: Dict[str, Any]) -> Dict[str, Any]:
    """Manual edit from the interface: set the number of a part (0 removes it)."""
    _not_the_example()
    if slug not in catalog["part_index"]:
        raise ValueError(f"unknown part: {slug}")
    count = max(0, min(9999, int(count)))
    with _lock:
        inv = load()
        _remember(lambda: history.sync(inv))
        if count:
            inv["items"][slug] = count
        else:
            inv["items"].pop(slug, None)
        # keep the original source label, but remember that the list was touched by hand
        source = inv.get("source") or "manual"
        if source == "screenshots":
            source = "screenshots+manual"
        saved = save(inv, source=source, backup=False)
        _remember(lambda: history.snapshot(saved["items"], source="manual"))
        return saved


def change(delta: Dict[str, int], catalog: Dict[str, Any], kind: str = "manual", note: str = "") -> Dict[str, Any]:
    """Add (a positive number) or take away (a negative one) several parts at once: a sale the user
    entered, or its undoing.  All or nothing: if one part cannot be taken in full, nothing is written."""
    _not_the_example()
    with _lock:
        inv = load()
        wanted = {}
        for slug, n in delta.items():
            if slug not in catalog["part_index"]:
                raise ValueError(f"unknown part: {slug}")
            left = inv["items"].get(slug, 0) + int(n)
            if left < 0:
                raise ValueError(tr("В инвентаре не хватает частей этого комплекта"))
            wanted[slug] = min(9999, left)
        _remember(lambda: history.sync(inv))
        for slug, left in wanted.items():
            if left:
                inv["items"][slug] = left
            else:
                inv["items"].pop(slug, None)
        source = inv.get("source") or "manual"
        if source == "screenshots":
            source = "screenshots+manual"
        saved = save(inv, source=source, backup=False)
        _remember(lambda: history.snapshot(saved["items"], source=kind, note=note))
        return saved


def _remember(action) -> None:
    """The history of updates is a convenience: a failure to write it must never fail the update itself."""
    try:
        action()
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("primesets").exception("could not write the update history")


def dismiss_review(index: int) -> Dict[str, Any]:
    _not_the_example()
    with _lock:
        inv = load()
        if 0 <= index < len(inv["review"]):
            gone = inv["review"].pop(index)
            if gone.get("kind") == "unmatched":
                ignore_name(str(gone.get("name") or ""))      # "Понятно": do not report this name again
        return save(inv, backup=False)


def add_review(notes: List[Dict[str, Any]], replace: bool = False) -> Dict[str, Any]:
    """Store notes that need the user's eye (shown as a banner in the interface)."""
    _not_the_example()
    with _lock:
        inv = load()
        inv["review"] = list(notes) if replace else inv["review"] + list(notes)
        return save(inv, backup=False)


def import_entries(entries: Iterable[Dict[str, Any]], catalog: Dict[str, Any], mode: str = "replace",
                   source: str = "screenshots", note: str = "", dry_run: bool = False,
                   extra_review: Optional[List[Dict[str, Any]]] = None, force: bool = False) -> Dict[str, Any]:
    """Match recognised names to catalog parts and store the result.

    entries: [{"name": str, "count": int, "blueprint": bool|None, "count_known": bool, "shot": str}]
             count_known=False means "at least one": the screen showed the item without a number
             (a blueprint card in the foundry), so an already known larger count is kept.
             count_hidden=True (with count_known=False): the place of the number was cut off; if no
             other screenshot shows the number, the part is listed for a second look.
    mode:    "replace" -- the entries are a full snapshot of the prime parts;
             "merge"   -- only the listed parts are updated, the rest is kept.
    The same part seen on several (overlapping) screenshots is counted once.
    A "replace" that would drop more than half of a sizeable inventory is refused unless force=True.
    """
    if mode not in ("replace", "merge"):
        raise ValueError("mode must be 'replace' or 'merge'")
    if not dry_run:
        _not_the_example()
    matcher = Matcher(catalog)
    part_names = {p["slug"]: p["name"] for st in catalog["sets"].values() for p in st["parts"]}

    ignored = ignored_names()
    exact: Dict[str, int] = {}          # counts read from the screen
    at_least: Dict[str, int] = {}       # "there is at least this many"
    seen: Dict[str, List[dict]] = {}
    hidden: Dict[str, dict] = {}        # parts whose number was cut off on the screenshot
    matched: List[dict] = []
    review: List[dict] = []
    skipped: List[dict] = []
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict) or raw.get("skip") is True:      # skip: the user set the line aside in the review
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        try:
            count = int(raw.get("count") if raw.get("count") is not None else 1)
        except (TypeError, ValueError):
            count = 1
        known = raw.get("count_known") is not False
        bp = raw.get("blueprint")
        bp = bp if isinstance(bp, bool) else None
        shot = str(raw.get("shot") or "")
        told = raw.get("slug")          # the user named the part in the review: no guessing needed
        m = Match("exact", slug=told, score=1.0) if isinstance(told, str) and told in part_names else matcher.match(name, bp)
        row = {"name": name, "count": count, "shot": shot, "status": m.status, "note": m.note, "count_known": known,
               "entry": index}
        pos = raw.get("pos")            # the tile of the screenshot the line was read from: [row, column]
        if isinstance(pos, (list, tuple)) and len(pos) == 2 and all(isinstance(v, int) for v in pos):
            row["pos"] = [pos[0], pos[1]]
        where = {"shot": shot, "entry": index, "pos": row.get("pos")}
        if m.ok and count > 0:
            row.update({"slug": m.slug, "item": part_names[m.slug]})
            matched.append(row)
            if known:
                seen.setdefault(m.slug, []).append(row)
                exact[m.slug] = max(exact.get(m.slug, 0), count)
            else:
                at_least[m.slug] = max(at_least.get(m.slug, 0), count)
                if raw.get("count_hidden") is True:
                    hidden.setdefault(m.slug, row)
            if m.note:                 # a confident match carries no note and needs no second look
                review.append({"kind": "check", "name": name, "count": count, "slug": m.slug,
                               "item": part_names[m.slug], "note": m.note, **where})
        elif m.status == "unmatched" and normalize(name) in ignored:
            row["status"] = "ignored"
            skipped.append(row)
        elif m.status == "unmatched":
            sugg = [{"slug": s, "item": part_names[s]} for s in m.suggestions[:3]]
            review.append({"kind": "unmatched", "name": name, "count": count, "note": m.note,
                           "suggestions": sugg, **where})
            skipped.append(row)
        else:
            row["slug"] = m.slug
            skipped.append(row)

    # the same tile read from two overlapping screenshots must not be listed twice
    unique, keys = [], set()
    for note_row in review:
        key = (note_row["kind"], note_row["name"].strip().lower(), note_row.get("count"), note_row.get("slug"))
        if key not in keys:
            keys.add(key)
            unique.append(note_row)
    review = unique

    conflicts = []
    for slug, rows in seen.items():
        distinct = sorted({r["count"] for r in rows})
        if len(distinct) > 1:
            conflicts.append({"slug": slug, "item": part_names[slug], "counts": distinct, "used": exact[slug]})
            review.append({"kind": "conflict", "name": part_names[slug], "count": exact[slug], "slug": slug,
                           "item": part_names[slug],
                           "note": tr("на разных скриншотах разное количество: {0} — взято {1}",
                                      ", ".join(map(str, distinct)), exact[slug])})

    for slug, row in hidden.items():
        if slug not in exact:
            review.append({"kind": "check", "name": row["name"], "count": at_least[slug], "slug": slug,
                           "item": part_names[slug], "shot": row["shot"], "entry": row["entry"], "pos": row.get("pos"),
                           "note": tr("верх плитки срезан краем списка, число не видно — проверьте количество")})

    with _lock:
        inv = load()
        before = dict(inv["items"])
        counts = dict(exact)
        for slug, low in at_least.items():
            if slug not in counts:
                counts[slug] = max(low, before.get(slug, 0))
        after = dict(counts) if mode == "replace" else {**before, **counts}

        refused = ""
        if mode == "replace" and not force and len(before) >= 10 and len(after) < len(before) / 2:
            refused = tr("в новом снимке {0} разных частей вместо {1}: похоже, скриншоты покрывают не весь список. "
                         "Если это часть инвентаря, используйте режим merge; если инвентарь действительно так "
                         "уменьшился — повторите с --force.", len(after), len(before))
        changes = {
            "added": sorted(s for s in after if s not in before),
            "removed": sorted(s for s in before if s not in after),
            "changed": sorted(s for s in after if s in before and before[s] != after[s]),
        }
        written = False
        if not dry_run and not refused:
            _remember(lambda: history.sync(inv))       # the state this import starts from
            inv["items"] = after
            inv["review"] = review + list(extra_review or [])
            inv["note"] = note
            inv = save(inv, source=source, backup=True)
            written = True
            _remember(lambda: history.snapshot(after, source=source, note=note, mode=mode))

    return {
        "mode": mode,
        "dry_run": dry_run,
        "written": written,
        "refused": refused,
        "entries": len(matched) + len(skipped),
        "matched": matched,
        "skipped": skipped,
        "review": review,
        "conflicts": conflicts,
        "distinct_parts": len(counts),
        "total_parts": sum(counts.values()),
        "inventory_distinct": len(after),
        "inventory_total": sum(after.values()),
        "changes": changes,
    }
