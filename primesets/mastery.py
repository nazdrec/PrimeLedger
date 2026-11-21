"""Which prime items the account has already mastered.

Digital Extremes has no public API for account data, so this is a local list:
marks read from the user's own screenshots (the foundry and the profile show
"Освоено") or set by hand in the interface.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from . import config, demo
from .i18n import N_, tr
from .matching import Matcher

MASTERY_FILE = config.DATA_DIR / "mastery.json"
VERSION = 1
# mastered -- levelled to the maximum rank at least once (the game shows "Освоено")
# owned    -- a built copy sits in the arsenal; whether it is mastered is not known for sure
#             (a weapon reset by forma shows a low rank but stays mastered)
# none     -- neither: the game showed the blueprint without «Освоено» and without «В наличии»
STATES = ("mastered", "owned", "none")
STATE_TEXT = {"mastered": N_("освоено"), "owned": N_("есть в арсенале"), "none": N_("не освоено"),
              "unknown": N_("не отмечено")}

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def masterable(st: Dict[str, Any]) -> bool:
    """Everything except cosmetics-like sets (the kubrow collar) gives mastery."""
    return st.get("category") != "other"


def load() -> Dict[str, Any]:
    data: Dict[str, Any] = {"version": VERSION, "updated_at": None, "items": {}}
    if demo.on():                       # the marks of the made-up inventory; the real file is not touched
        data["updated_at"] = demo.since()
        data["items"] = {slug: {"state": state, "source": "demo", "at": demo.since() or ""}
                         for slug, state in demo.MASTERY.items()}
        return data
    with _lock:
        try:
            raw = json.loads(MASTERY_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return data
    if isinstance(raw, dict):
        data["updated_at"] = raw.get("updated_at")
        items = raw.get("items")
        if isinstance(items, dict):
            for slug, rec in items.items():
                if isinstance(rec, dict) and rec.get("state") in STATES:
                    data["items"][slug] = {"state": rec["state"], "source": rec.get("source") or "",
                                           "at": rec.get("at") or ""}
    return data


def _save(data: Dict[str, Any]) -> Dict[str, Any]:
    if demo.on():
        raise ValueError(tr("Сейчас показан пример инвентаря. Уберите пример, чтобы вносить изменения."))
    data = dict(data)
    data["version"] = VERSION
    data["updated_at"] = _now_iso()
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MASTERY_FILE.with_name(MASTERY_FILE.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, MASTERY_FILE)
    return data


def mtime() -> float:
    try:
        return MASTERY_FILE.stat().st_mtime
    except OSError:
        return 0.0


def state_of(data: Dict[str, Any], slug: str) -> str:
    rec = data["items"].get(slug)
    return rec["state"] if rec else "unknown"


def set_state(slug: str, state: Optional[str], catalog: Dict[str, Any], source: str = "manual") -> Dict[str, Any]:
    """Manual mark from the interface. state=None forgets the mark."""
    if slug not in catalog["sets"]:
        raise ValueError(f"unknown set: {slug}")
    if state is not None and state not in STATES:
        raise ValueError(f"bad state: {state}")
    with _lock:
        data = load()
        if state is None:
            data["items"].pop(slug, None)
        else:
            data["items"][slug] = {"state": state, "source": source, "at": _now_iso()}
        return _save(data)


def import_marks(marks: Iterable[Dict[str, Any]], catalog: Dict[str, Any], source: str = "screenshots",
                 dry_run: bool = False) -> Dict[str, Any]:
    """Apply marks read from screenshots.

    marks: [{"name": "Акцельтра Прайм", "mastered": True | False | None, "owned": True | False | None, "shot": str}]
        mastered True  -- the game says so: the label «Освоено», or the built item stands at rank 30;
        mastered False -- a foundry card was fully visible and carried no «Освоено»;
        mastered None  -- no evidence either way (a hidden label, a built item below rank 30);
        owned True     -- a built copy exists (label «В наличии», or the item itself in the inventory).
    All marks about one item are weighed together: any proof of mastery wins; "not mastered" needs an
    explicit clean reading; a built copy alone gives «есть в арсенале».  A mark already stored as
    «освоено» is never lowered -- mastery cannot be lost in the game.
    Names that are not prime sets (sentinel weapons, built parts) are ignored without noise.
    """
    matcher = Matcher(catalog)
    review: List[dict] = []
    skipped: List[dict] = []
    seen: Dict[str, Dict[str, Any]] = {}
    for raw in marks:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        mastered = raw.get("mastered") if isinstance(raw.get("mastered"), bool) else None
        owned = raw.get("owned") if isinstance(raw.get("owned"), bool) else None
        if not name or (mastered is None and not owned):
            continue
        shot = str(raw.get("shot") or "")
        m = matcher.match_set(name)
        if not m.ok:
            skipped.append({"name": name, "status": m.status, "note": m.note, "shot": shot})
            continue
        st = catalog["sets"][m.slug]
        if not masterable(st):
            skipped.append({"name": name, "status": "not_masterable", "note": "", "shot": shot})
            continue
        agg = seen.setdefault(m.slug, {"yes": False, "no": False, "owned": False, "shots": [], "fuzzy": None})
        agg["yes"] = agg["yes"] or mastered is True
        agg["no"] = agg["no"] or mastered is False
        agg["owned"] = agg["owned"] or owned is True
        if shot and shot not in agg["shots"]:
            agg["shots"].append(shot)
        if m.status == "fuzzy" and not m.confident:
            agg["fuzzy"] = {"name": name, "note": m.note}

    applied: List[dict] = []
    with _lock:
        data = load()
        for slug, agg in seen.items():
            st = catalog["sets"][slug]
            shots_text = ", ".join(agg["shots"][:3])
            if agg["yes"]:
                state = "mastered"
                if agg["no"]:
                    review.append({"kind": "mastery-conflict", "name": st["title"], "slug": slug, "shot": shots_text,
                                   "note": tr("на одном скриншоте есть «Освоено», на другом нет — записано «освоено»")})
            elif agg["owned"]:
                state = "owned"
            elif agg["no"]:
                state = "none"
            else:
                continue
            old = state_of(data, slug)
            if old == "mastered" and state != "mastered":
                if agg["no"]:
                    review.append({"kind": "mastery-downgrade", "name": st["title"], "slug": slug, "shot": shots_text,
                                   "note": tr("раньше было отмечено «освоено», на скриншоте — «{0}»; оставлено «освоено», "
                                              "проверьте", tr(STATE_TEXT[state]))})
                continue
            if agg["fuzzy"]:
                review.append({"kind": "mastery-check", "name": agg["fuzzy"]["name"], "slug": slug,
                               "item": st["title"], "note": agg["fuzzy"]["note"], "shot": shots_text})
            data["items"][slug] = {"state": state, "source": source, "at": _now_iso()}
            applied.append({"slug": slug, "item": st["title"], "state": state, "was": old})
        if not dry_run and applied:
            _save(data)
    return {"applied": applied, "skipped": skipped, "review": review,
            "changed": [a for a in applied if a["was"] != a["state"]]}


def forget_source(source: str = "screenshots") -> int:
    """Drop every mark that came from the given source (manual marks stay). Used before a re-reading
    that is known to be more careful than the previous one."""
    with _lock:
        data = load()
        gone = [slug for slug, rec in data["items"].items() if rec.get("source") == source]
        for slug in gone:
            del data["items"][slug]
        if gone:
            _save(data)
        return len(gone)
