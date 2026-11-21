"""The journal of sales: what the user sold, when and for how much.

A sale is entered by the user ("Продал"): the parts of the set leave the inventory and a line is
added here.  The app cannot see a trade -- nothing is read from the game or from the market -- it
only remembers what it was told.  A line can be taken back: the parts return to the inventory.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import config, inventory
from .i18n import tr

SALES_FILE = config.DATA_DIR / "sales.json"
KEEP = 3000
MAX_PLATINUM = 100000
MAX_COPIES = 99

_lock = threading.RLock()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load() -> List[Dict[str, Any]]:
    """Every sale, the oldest first."""
    try:
        data = json.loads(SALES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in data if isinstance(r, dict) and r.get("id") and isinstance(r.get("parts"), dict)] \
        if isinstance(data, list) else []


def _write(records: List[Dict[str, Any]]) -> None:
    SALES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SALES_FILE.with_name(SALES_FILE.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(records[-KEEP:], ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, SALES_FILE)


def add(catalog: Dict[str, Any], slug: str, platinum: Any, count: Any = 1, buyer: str = "") -> Dict[str, Any]:
    """The user sold `count` copies of a set for `platinum` each: take its parts out and write the line."""
    st = catalog["sets"].get(slug)
    if st is None:
        raise ValueError(tr("Такого комплекта в справочнике нет"))
    try:
        price, copies = int(platinum), int(count)
    except (TypeError, ValueError):
        raise ValueError(tr("Цена и количество должны быть числами")) from None
    if not 0 <= price <= MAX_PLATINUM:
        raise ValueError(tr("Цена должна быть от 0 до 100 000 платины"))
    if not 1 <= copies <= MAX_COPIES:
        raise ValueError(tr("Количество должно быть от 1 до 99"))
    parts = {p["slug"]: int(p["quantity"]) * copies for p in st["parts"]}
    with _lock:
        note = tr("{0} ×{1} за {2} пл", st["title"], copies, price * copies)
        inventory.change({s: -n for s, n in parts.items()}, catalog, kind="sale", note=note)
        record = {"id": uuid.uuid4().hex[:12], "at": _now(), "slug": slug, "name_en": st["en"], "platinum": price,
                  "count": copies, "parts": parts, "buyer": str(buyer or "").strip()[:60]}
        records = load()
        records.append(record)
        _write(records)
        return record


def undo(catalog: Dict[str, Any], sale_id: str) -> Dict[str, Any]:
    """The line was entered by mistake: give the parts back and drop it."""
    with _lock:
        records = load()
        record = next((r for r in records if r["id"] == sale_id), None)
        if record is None:
            raise ValueError(tr("Такой продажи в журнале нет"))
        # a part that has left the catalog meanwhile cannot be given back; the rest is
        back = {s: int(n) for s, n in record["parts"].items() if s in catalog["part_index"] and int(n) > 0}
        st = catalog["sets"].get(record.get("slug"))
        title = st["title"] if st else str(record.get("name_en") or "")
        if back:
            inventory.change(back, catalog, kind="sale", note=tr("отмена продажи: {0}", title))
        _write([r for r in records if r["id"] != sale_id])
        return record


def totals(records: List[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    """What the journal adds up to: in all and over the last 30 days."""
    now = now or datetime.now().astimezone()
    edge = now - timedelta(days=30)
    platinum = month = sets = 0
    for r in records:
        amount = int(r.get("platinum") or 0) * int(r.get("count") or 1)
        platinum += amount
        sets += int(r.get("count") or 1)
        try:
            if datetime.fromisoformat(str(r.get("at"))) >= edge:
                month += amount
        except (TypeError, ValueError):
            pass
    return {"platinum": platinum, "month": month, "sales": len(records), "sets": sets}


def payload(catalog: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The journal for the page, the newest first, with the titles in the language of the interface."""
    records = load()
    rows = []
    for r in reversed(records):
        st = catalog["sets"].get(r.get("slug")) if catalog else None
        count, price = int(r.get("count") or 1), int(r.get("platinum") or 0)
        rows.append({"id": r["id"], "at": r.get("at"), "slug": r.get("slug"),
                     "title": st["title"] if st else str(r.get("name_en") or r.get("slug") or ""),
                     "thumb": st["thumb"] if st else "", "platinum": price, "count": count, "sum": price * count,
                     "buyer": r.get("buyer") or ""})
    return {"sales": rows[:400], "totals": totals(records)}
