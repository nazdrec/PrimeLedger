"""Local HTTP server: JSON API for the interface plus static files.

Listens on 127.0.0.1 only.  Outbound traffic: warframe.market (public API, rate-limited), the
official DE drop tables page and -- when the user starts a reading -- the AI service they chose
in the settings (see providers/).
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import queue
import re
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

from . import (APP_NAME, HOMEPAGE, __version__, analysis, catalog as catalog_mod, config, continuity, demo, history, i18n,
               inventory, live, mastery, providers, recognize, sales, settings, shots, updates, vault)
from .cache import DiskCache
from .i18n import N_, tr
from .wfm import FetchError, WfmClient, valid_slug

log = logging.getLogger("primesets")

MAX_BODY = 64 * 1024
MAX_SCREENSHOT = 40 * 1024 * 1024
SCREENSHOT_EXT = shots.EXT
_NAME_RE = re.compile(r"[^\w._() -]+")


class AppState:
    def __init__(self, auto_exit: bool = True):
        self.cache = DiskCache(config.CACHE_DIR)
        self.wfm = WfmClient(self.cache)
        i18n.set_language(settings.language())
        self.catalog: Optional[Dict[str, Any]] = catalog_mod.load_cached(
            self.cache, None, settings.language(), settings.game_language())
        self.build = {"building": False, "stage": "", "done": 0, "total": 0, "error": None}
        self._build_lock = threading.Lock()
        self.clients: List["queue.Queue[Optional[dict]]"] = []
        self._clients_lock = threading.Lock()
        self.auto_exit = auto_exit
        self.started_at = time.time()
        self.ever_connected = False
        self.last_client_seen = time.time()
        self.bye_at: Optional[float] = None
        self.stop_event = threading.Event()
        self._inv_mtime = inventory.mtime()
        self._mastery_mtime = mastery.mtime()
        self.job: Optional[recognize.Job] = None
        self._job_lock = threading.Lock()
        self._restore_tried = False
        self._thumbs: Dict[Any, bytes] = {}
        self._joins: Dict[str, Any] = {"key": None, "result": None, "busy": None}
        self._joins_lock = threading.Lock()
        self.live = live.Live(self.push)
        self.update: Dict[str, Any] = {"state": "off"}

    # -- a newer version ----------------------------------------------------
    def check_update(self, force: bool = False) -> None:
        """Ask the page of the project whether a newer version is out -- in the background, and only
        while the user has not switched the question off."""
        if not settings.check_updates():
            self.update = {"state": "off"}
            return

        def ask() -> None:
            try:
                self.update = updates.check(self.cache, force)
            except Exception:            # a convenience: it must never get in the way
                log.exception("the check for a newer version failed")
                return
            if self.update.get("state") == "newer":
                log.info("a newer version is out: %s", self.update.get("latest"))
                self.push("update", {})

        threading.Thread(target=ask, name="update-check", daemon=True).start()

    # -- recognition --------------------------------------------------------
    def start_recognition(self) -> recognize.Job:
        self.live.stop()
        demo.switch(False)               # the user's own screenshots are being read: the example has done its job
        with self._job_lock:
            if self.job and self.job.state == "running":
                raise recognize.RecognizeError(tr("Распознавание уже идёт"), "busy")
            if not self.catalog:
                raise recognize.RecognizeError(tr("Справочник комплектов ещё не загружен"), "no_catalog")
            files = shots.originals()
            if not files:
                raise recognize.RecognizeError(tr("В папке нет скриншотов"), "no_files")
            job = recognize.Job(files, self.catalog)
            self.job = job
        threading.Thread(target=job.run, name="recognize", daemon=True).start()
        return job

    def restore_reading(self) -> None:
        """Once the catalog is there, bring back a reading that was finished before the last shutdown."""
        if self._restore_tried or not self.catalog:
            return
        with self._job_lock:
            if self._restore_tried:
                return
            self._restore_tried = True
            if self.job is None:
                self.job = recognize.restore_pending(self.catalog)
                if self.job:
                    log.info("restored a finished reading of %d screenshots", len(self.job.files))

    def joins_state(self) -> Dict[str, Any]:
        """Do the inventory screenshots in the inbox join up?  (continuity.py)

        The comparison takes a second or two, so it runs in the background: the answer is
        "checking" until it is ready, then the page is told to ask again.
        """
        files = shots.originals()
        key = []
        for f in files:
            try:
                st = f.stat()
            except OSError:
                continue
            key.append((f.name, st.st_mtime_ns, st.st_size))
        signature = tuple(key)
        with self._joins_lock:
            if self._joins["key"] == signature and self._joins["result"] is not None:
                return self._joins["result"]
            if not signature or not continuity.available():
                return {"available": continuity.available(), "state": "none", "pages": 0, "pairs": 0, "joined": 0,
                        "gaps": [], "unknown": [], "start": "unknown", "end": "unknown", "first": "", "last": ""}
            if self._joins["busy"] != signature:
                self._joins["busy"] = signature
                threading.Thread(target=self._check_joins, args=(signature, files), name="joins", daemon=True).start()
        return {"available": True, "state": "checking", "pages": 0, "pairs": 0, "joined": 0, "gaps": [], "unknown": [],
                "start": "unknown", "end": "unknown", "first": "", "last": ""}

    def _check_joins(self, signature: tuple, files: List[Any]) -> None:
        try:
            result = continuity.check(files)
        except Exception:  # a broken picture must not take the dialog down
            log.exception("join check failed")
            result = {"available": False, "state": "none", "pages": 0, "pairs": 0, "joined": 0, "gaps": [], "unknown": [],
                      "start": "unknown", "end": "unknown", "first": "", "last": ""}
        with self._joins_lock:
            if self._joins["busy"] != signature:
                return                       # the folder changed meanwhile: a newer check is on its way
            self._joins.update({"key": signature, "result": result, "busy": None})
        self.push("joins", {})

    def recognition_state(self, refresh: bool = False) -> Dict[str, Any]:
        self.restore_reading()
        job = self.job
        game = shots.game_new()
        snap = job.snapshot() if job else None
        # after the reading the job knows better: it has been told which screenshots are the inventory
        joins = snap["joins"] if snap and snap.get("joins") else self.joins_state()
        return {"provider": providers.current().status(force=refresh), "job": snap,
                "files": list_screenshots(), "joins": joins, "live": self.live.state(),
                "game": {"dir": game["dir"], "exists": game["exists"], "new": len(game["files"])}}

    # -- server-sent events -------------------------------------------------
    def add_client(self) -> "queue.Queue[Optional[dict]]":
        q: "queue.Queue[Optional[dict]]" = queue.Queue(maxsize=200)
        with self._clients_lock:
            self.clients.append(q)
            self.ever_connected = True
            self.bye_at = None
            self.last_client_seen = time.time()
        return q

    def remove_client(self, q) -> None:
        with self._clients_lock:
            if q in self.clients:
                self.clients.remove(q)
            self.last_client_seen = time.time()

    def client_count(self) -> int:
        with self._clients_lock:
            return len(self.clients)

    def push(self, event: str, data: Optional[dict] = None) -> None:
        with self._clients_lock:
            targets = list(self.clients)
        for q in targets:
            try:
                q.put_nowait({"event": event, "data": data or {}})
            except queue.Full:
                pass

    # -- catalog ------------------------------------------------------------
    def catalog_status(self) -> Dict[str, Any]:
        cat = self.catalog
        status = dict(self.build)
        status.update({
            "ready": cat is not None,
            "built_at": cat.get("built_at") if cat else None,
            "set_count": len(cat["sets"]) if cat else 0,
            "droptables": cat.get("droptables") if cat else None,
            "items_fetched_at": cat.get("items_fetched_at") if cat else None,
            "stale": bool(cat and time.time() - cat.get("built_at", 0) > config.TTL_CATALOG),
        })
        return status

    def ensure_catalog(self, force: bool = False) -> bool:
        """Start a background build when the catalog is missing, old, or a refresh is requested."""
        cat = self.catalog
        fresh = cat is not None and time.time() - cat.get("built_at", 0) <= config.TTL_CATALOG
        if fresh and not force:
            return False
        with self._build_lock:
            if self.build["building"]:
                return False
            self.build.update({"building": True, "stage": tr("Подготовка"), "done": 0, "total": 0, "error": None})
        threading.Thread(target=self._build, args=(force,), name="catalog-build", daemon=True).start()
        return True

    def _build(self, force: bool) -> None:
        last_push = [0.0]

        def progress(stage: str, done: int, total: int) -> None:
            self.build.update({"stage": stage, "done": done, "total": total})
            now = time.time()
            if now - last_push[0] > 0.4 or done == total:
                last_push[0] = now
                self.push("catalog", {"building": True, "stage": stage, "done": done, "total": total})

        lang, game = settings.language(), settings.game_language()
        try:
            cat = catalog_mod.build(self.wfm, self.cache, progress, force=force, lang=lang, game_lang=game)
            self.catalog = cat
            self.build.update({"building": False, "error": None})
            log.info("catalog built: %d sets (%s, game %s)", len(cat["sets"]), lang, game)
            self._reword_job()
        except Exception as exc:  # network trouble must never kill the app
            log.exception("catalog build failed")
            self.build.update({"building": False, "error": str(exc)})
        self.push("catalog", {"building": False, "error": self.build["error"]})
        if (lang, game) != (settings.language(), settings.game_language()):
            self.apply_language()            # the language was changed while the catalog was being built

    def apply_language(self) -> None:
        """The settings name another language: switch the texts and bring the catalog with names in it."""
        lang, game = settings.language(), settings.game_language()
        i18n.set_language(lang)
        cat = self.catalog
        if not cat or cat.get("lang") != lang or cat.get("game_lang") != game:
            self.catalog = catalog_mod.load_cached(self.cache, None, lang, game)
            self.ensure_catalog()
            self._restore_tried = False
        self._reword_job()

    def _reword_job(self) -> None:
        """A reading that waits for the user's decision follows the language (see recognize.Job.reword)."""
        job = self.job
        if not job or job.state != "review":
            return
        try:
            job.reword(self.catalog)
        except Exception:
            log.exception("could not reword the pending reading")
        self.push("joins", {})               # the dialog of the screenshots asks for the reading again

    # -- background watchers ------------------------------------------------
    def watch(self) -> None:
        """Notify the page when inventory.json changes on disk; stop the app when the window is gone."""
        while not self.stop_event.wait(1.0):
            m, mm = inventory.mtime(), mastery.mtime()
            if m != self._inv_mtime or mm != self._mastery_mtime:
                self._inv_mtime, self._mastery_mtime = m, mm
                self.push("inventory", {})
            if not self.auto_exit:
                continue
            now = time.time()
            if self.client_count() > 0:
                continue
            if self.job and self.job.state == "running":
                continue                     # never quit in the middle of reading screenshots
            idle = now - self.last_client_seen
            if self.ever_connected:
                if self.bye_at and now - self.bye_at > 4 and idle > 4:
                    log.info("window closed -> exit")
                    self.stop_event.set()
                elif idle > 12 * 3600:
                    # no "bye" came: the window may only be asleep in the background, so wait long
                    log.info("no window for 12 hours -> exit")
                    self.stop_event.set()
            elif now - self.started_at > 180:
                log.info("nobody connected -> exit")
                self.stop_event.set()


# --------------------------------------------------------------------------- payloads
VAULT_TEXT = {
    "vaulted": (N_("Да"), ""),
    "available": (N_("Нет"), ""),
    "special": (N_("Нет"), N_("только особые реликвии")),
    "partial": (N_("Частично"), ""),
    "unknown": ("—", N_("нет данных")),
}


def market_url(slug: str) -> str:
    """The page of an item on warframe.market, in the language of the interface."""
    code = i18n.info()["wfm"]
    return f"{config.WFM_SITE}/{'' if code == 'en' else code + '/'}items/{slug}"


def _mastery_payload(st: Dict[str, Any], marks: Dict[str, Any]) -> Dict[str, Any]:
    if not mastery.masterable(st):
        return {"state": "na", "label": tr("не даёт ранг"), "source": "", "warn": False}
    state = mastery.state_of(marks, st["slug"])
    rec = marks["items"].get(st["slug"]) or {}
    return {"state": state, "label": tr(mastery.STATE_TEXT[state]), "source": rec.get("source", ""),
            # the warning the user asked for: a full set of something not mastered yet
            "warn": state == "none"}


def _set_payload(cat: Dict[str, Any], row: Dict[str, Any], marks: Dict[str, Any]) -> Dict[str, Any]:
    st = cat["sets"][row["slug"]]
    progress = {p["slug"]: p for p in row["parts"]}
    parts = []
    for p in st["parts"]:
        pr = progress[p["slug"]]
        parts.append({
            "slug": p["slug"],
            "label": p["label"],
            "name": p["name"],
            "en": p["en"],
            "thumb": p["thumb"],
            "quantity": p["quantity"],
            "owned": pr["owned"],
            "spare": pr["spare"],
            "missing": pr["missing_for_next"],
            "ducats": p.get("ducats"),
            "availability": p["availability"],
            "relics": [{"name": r["name"], "drops": r["drops"], "wfm_vaulted": r["wfm_vaulted"],
                        "rarity": r["rarity"]} for r in p["relics"]],
        })
    return {
        "slug": st["slug"],
        "title": st["title"],
        "title_en": st["title_en"],
        "name_en": st["en"],
        "thumb": st["thumb"],
        "category": st["category"],
        "ducats": st.get("ducats"),
        "complete": row["complete"],
        "owned_kinds": row["owned_kinds"],
        "total_kinds": row["total_kinds"],
        "missing_count": sum(m["count"] for m in row["missing"]),
        "missing_kinds": len(row["missing"]),
        "parts": parts,
        "mastery": _mastery_payload(st, marks),
        "vault": _vault_payload(st),
        "market_url": market_url(st["slug"]),
    }


def _vault_payload(st: Dict[str, Any]) -> Dict[str, Any]:
    label, note = VAULT_TEXT.get(st["vault"]["state"], ("—", ""))
    label, note = (tr(label) if label != "—" else label), (tr(note) if note else "")
    if st["vault"]["state"] == "partial":
        note = tr("в хранилище {0} из {1} частей", st["vault"]["vaulted_parts"], st["vault"]["total_parts"])
    return {"state": st["vault"]["state"], "label": label, "note": note}


def ducat_sets(state: AppState) -> Dict[str, Any]:
    """Every set of the catalog with what it gives in ducats -- for "which set is the cheapest way to ducats".

    Prices here come from the cache only, however old: asking the market about 160 sets is the
    user's decision (the page then goes through /api/market?lite=1 one set at a time).
    """
    cat = state.catalog
    out: List[Dict[str, Any]] = []
    if cat:
        have = inventory.load()["items"]
        for st in cat["sets"].values():
            row: Dict[str, Any] = {
                "slug": st["slug"],
                "title": st["title"],
                "title_en": st["title_en"],
                "thumb": st["thumb"],
                "category": st["category"],
                "ducats": analysis.ducat_value(st),
                "parts": [{"slug": p["slug"], "label": p["label"], "name": p["name"], "quantity": p["quantity"],
                           "ducats": p.get("ducats")} for p in st["parts"]],
                "owned": analysis.set_progress(st, have)["complete"],
                "vault": _vault_payload(st),
                "market_url": market_url(st["slug"]),
                "price": None,
                "orders_at": None,
            }
            hit = state.wfm.top_orders_cached(st["slug"])
            if hit:
                row["price"] = analysis.price_from_orders(hit[0])
                row["orders_at"] = hit[1]
            out.append(row)
    return {"sets": out, "ttl_orders": config.TTL_TOP_ORDERS, "min_interval": config.WFM_MIN_INTERVAL}


def whisper(user: str, item_en: str, platinum: Any, count: int = 1, deal: str = "buy") -> str:
    """The message for a seller (deal="buy") or for a buyer (deal="sell"): the user pastes it into the
    game chat by hand.

    warframe.market's API rules ask an application to give this message in the same format as the
    site and to include the application's name.  So the site's own line is kept exactly as it is,
    and what the application adds comes after it: its name and, when several are traded, how many.
    """
    verb = "sell" if deal == "sell" else "buy"
    line = f'/w {user} Hi! I want to {verb}: "{item_en}" for {platinum} platinum. (warframe.market)'
    own = f"x{count}, via {APP_NAME}" if count > 1 else f"via {APP_NAME}"
    return f"{line} ({own})"


def _complete_rows(state: AppState) -> List[Dict[str, Any]]:
    """The sets the inventory holds in full, each with what the market said about it last (no request is made)."""
    cat = state.catalog
    if not cat:
        return []
    marks = mastery.load()
    out = []
    for row in analysis.split_inventory(cat, inventory.load()["items"])["complete"]:
        st = cat["sets"][row["slug"]]
        hit = state.wfm.top_orders_cached(st["slug"])
        price = analysis.price_from_orders(hit[0]) if hit else None
        out.append({"slug": st["slug"], "title": st["title"], "name_en": st["en"], "thumb": st["thumb"],
                    "copies": row["complete"], "price": price["value"] if price else None,
                    "basis": price["basis"] if price else None, "orders_at": hit[1] if hit else None,
                    "buyers": analysis.buyers_from_orders(hit[0]) if hit else [],
                    "unmastered": mastery.masterable(st) and mastery.state_of(marks, st["slug"]) == "none"})
    return out


def sell_now(state: AppState) -> Dict[str, Any]:
    """Who buys the user's complete sets right now: buyers who are in the game, the most generous first.

    Built from the orders the app already holds (the prices of the complete sets); no request is made.
    """
    rows = _complete_rows(state)
    out = []
    for r in rows:
        if not r["buyers"]:
            continue
        out.append({**{k: r[k] for k in ("slug", "title", "name_en", "thumb", "copies", "unmastered", "orders_at")},
                    "sell_min": r["price"],
                    "buyers": [{**b, "message": whisper(b["user"], r["name_en"], b["platinum"], deal="sell")}
                               for b in r["buyers"][:3]]})
    out.sort(key=lambda r: (-r["buyers"][0]["platinum"], r["title"]))
    known = [r["orders_at"] for r in rows if r["orders_at"]]
    return {"sets": out, "complete": len(rows), "priced": len(known), "oldest_at": min(known, default=None),
            "ttl_orders": config.TTL_TOP_ORDERS}


def sales_plan(state: AppState, target: int, keep_unmastered: bool = True,
               exclude: Optional[List[str]] = None) -> Dict[str, Any]:
    """Which complete sets to sell for `target` platinum: what is bought often first (analysis.plan_sales).

    Prices and the week's deals are the ones the app already holds; no request is made here.
    keep_unmastered -- leave out the sets that are not mastered yet (they are better built first).
    """
    skip = set(exclude or [])
    items, held, unpriced = [], [], []
    for r in _complete_rows(state):
        if r["slug"] in skip:
            continue
        if keep_unmastered and r["unmastered"]:
            held.append(r["title"])
            continue
        if r["price"] is None:
            unpriced.append(r["title"])
            continue
        stats = state.wfm.statistics_cached(r["slug"])
        deals = analysis.recent_deals(stats[0].get("days") or []) if stats else None
        items.append({**r, "platinum": r["price"], "deals": deals, "speed": analysis.sale_speed(deals)})
    plan = analysis.plan_sales(items, target)
    steps = []
    for pick in plan["picks"]:
        it, n = items[pick["index"]], pick["count"]
        best = it["buyers"][0] if it["buyers"] else None
        steps.append({"slug": it["slug"], "title": it["title"], "name_en": it["name_en"], "thumb": it["thumb"],
                      "count": n, "copies": it["copies"], "platinum": it["platinum"], "sum": it["platinum"] * n,
                      "deals": it["deals"], "speed": it["speed"], "basis": it["basis"], "orders_at": it["orders_at"],
                      "buyer": {"user": best["user"], "platinum": best["platinum"]} if best else None})
    order = {"fast": 0, "normal": 1, "slow": 2}
    steps.sort(key=lambda s: (order[s["speed"]], -s["platinum"], s["title"]))
    return {"target": target, "platinum": plan["platinum"], "reached": plan["reached"], "steps": steps,
            "available": len(items), "held": held, "unpriced": unpriced,
            "oldest_at": min((s["orders_at"] for s in steps if s["orders_at"]), default=None),
            "ttl_orders": config.TTL_TOP_ORDERS}


def baro(state: AppState) -> Dict[str, Any]:
    """The parts that make up no full set, each with its ducats and the price the market named last:
    what is better handed in at the ducat kiosk and what is better sold.  No request is made here --
    the page asks for the prices set by set (/api/parts-market?scope=spare) when the user says so."""
    cat = state.catalog
    out: List[Dict[str, Any]] = []
    if cat:
        index = {p["slug"]: (st, p) for st in cat["sets"].values() for p in st["parts"]}
        for spare in analysis.spare_parts(cat, inventory.load()["items"]):
            st, p = index[spare["slug"]]
            hit = state.wfm.top_orders_cached(p["slug"])
            price = analysis.price_from_orders(hit[0]) if hit else None
            out.append({"slug": p["slug"], "label": p["label"], "name": p["name"], "thumb": p["thumb"],
                        "set": st["slug"], "set_title": st["title"], "count": spare["count"], "near": spare["near"],
                        "ducats": int(p.get("ducats") or 0),
                        "price": price["value"] if price else None, "basis": price["basis"] if price else None,
                        "asked": hit is not None, "orders_at": hit[1] if hit else None})
    out.sort(key=lambda r: (r["set_title"].lower(), r["label"]))
    return {"parts": out, "ttl_orders": config.TTL_TOP_ORDERS, "min_interval": config.WFM_MIN_INTERVAL}


def collection(state: AppState) -> Dict[str, Any]:
    """Every set of the catalog with what the user has of it and whether it is mastered."""
    cat = state.catalog
    out: List[Dict[str, Any]] = []
    if cat:
        have = inventory.load()["items"]
        marks = mastery.load()
        for st in cat["sets"].values():
            prog = analysis.set_progress(st, have)
            out.append({"slug": st["slug"], "title": st["title"], "title_en": st["title_en"], "thumb": st["thumb"],
                        "category": st["category"], "complete": prog["complete"],
                        "have": sum(min(p["owned"], p["quantity"]) for p in prog["parts"]),
                        "need": sum(p["quantity"] for p in prog["parts"]),
                        "mastery": _mastery_payload(st, marks), "vault": _vault_payload(st),
                        "market_url": market_url(st["slug"])})
        out.sort(key=lambda r: r["title"].lower())
    return {"sets": out}


def ducat_plan(state: AppState, target: int, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
    """A shopping list: the cheapest sets to buy for `target` ducats, seller by seller.

    Built from the remembered offers of players who were in the game when the prices were asked
    (no request is made here).  exclude -- "set slug|seller" pairs the user ruled out: a seller who
    does not answer, or a purchase already made.
    """
    cat = state.catalog
    skip = set(exclude or [])
    offers: List[Dict[str, Any]] = []
    priced = 0
    for st in (cat["sets"].values() if cat else []):
        hit = state.wfm.top_orders_cached(st["slug"])
        if not hit:
            continue
        priced += 1
        ducats = analysis.ducat_value(st)
        for o in analysis.offers_from_orders(hit[0]):
            key = f"{st['slug']}|{o['user']}"
            if key in skip:
                continue
            offers.append({"key": key, "slug": st["slug"], "title": st["title"], "name_en": st["en"],
                           "thumb": st["thumb"], "ducats": ducats, "platinum": o["platinum"],
                           "quantity": o["quantity"], "user": o["user"], "reputation": o["reputation"],
                           "orders_at": hit[1]})
    plan = analysis.plan_ducats(offers, target)
    steps = []
    for pick in plan["picks"]:
        o, n = offers[pick["index"]], pick["count"]
        steps.append({**o, "count": n, "cost": o["platinum"] * n, "gain": o["ducats"] * n,
                      "message": whisper(o["user"], o["name_en"], o["platinum"], n)})
    steps.sort(key=lambda s: (-s["ducats"] / s["platinum"], s["title"], s["user"].lower()))
    return {"target": target, "ducats": plan["ducats"], "platinum": plan["platinum"], "reached": plan["reached"],
            "steps": steps, "priced": priced, "sets": len(cat["sets"]) if cat else 0, "offers": len(offers),
            "oldest_at": min((s["orders_at"] for s in steps), default=None), "ttl_orders": config.TTL_TOP_ORDERS}


def overview(state: AppState) -> Dict[str, Any]:
    inv = inventory.load()
    cat = state.catalog
    data: Dict[str, Any] = {
        "app": {"version": __version__, "id": config.APP_ID, "screenshots_dir": str(config.SCREENSHOT_DIR),
                "root": str(config.ROOT), "language": i18n.current(), "frozen": config.FROZEN},
        "catalog": state.catalog_status(),
        "inventory": {
            "updated_at": inv["updated_at"],
            "source": inv["source"],
            "note": inv.get("note") or "",
            "distinct": len(inv["items"]),
            "total": sum(inv["items"].values()),
            "review": inv["review"],
            "unknown": [],
        },
        "complete": [],
        "partial": [],
        "limits": {"wfm_min_interval": config.WFM_MIN_INTERVAL, "ttl_orders": config.TTL_TOP_ORDERS,
                   "ttl_stats": config.TTL_STATISTICS, "trend_window": config.TREND_WINDOW_DAYS,
                   "trend_threshold": config.TREND_THRESHOLD},
        "requests": state.wfm.counters(),
        "update": state.update,
        "demo": demo.on(),
        "welcomed": settings.welcomed(),
    }
    if cat:
        marks = mastery.load()
        split = analysis.split_inventory(cat, inv["items"])
        data["complete"] = [_set_payload(cat, r, marks) for r in split["complete"]]
        data["partial"] = [_set_payload(cat, r, marks) for r in split["partial"]]
        data["inventory"]["unknown"] = sorted(s for s in inv["items"] if s not in cat["part_index"])
        data["mastery"] = {"updated_at": marks["updated_at"], "marked": len(marks["items"])}
    return data


def market(state: AppState, slug: str, force: bool, lite: bool = False) -> Dict[str, Any]:
    """Live price and the 90-day trend of a set. lite=True skips the statistics request."""
    cat = state.catalog
    if not cat or slug not in cat["sets"]:
        raise KeyError(slug)
    out: Dict[str, Any] = {"slug": slug, "price": None, "trend": None, "errors": [], "orders_at": None,
                           "stats_at": None, "stale": False}
    try:
        top, meta = state.wfm.top_orders(slug, force=force)
        out["price"] = analysis.price_from_orders(top)
        out["offers"] = analysis.offers_from_orders(top)
        out["orders_at"] = meta["fetched_at"]
        out["stale"] = out["stale"] or meta["stale"]
    except FetchError as exc:
        out["errors"].append(tr("заказы: {0}", exc))
    if lite:
        return out
    try:
        stats, meta = state.wfm.statistics(slug, force=force)
        out["trend"] = analysis.trend_from_days(stats.get("days") or [])
        out["stats_at"] = meta["fetched_at"]
        out["stale"] = out["stale"] or meta["stale"]
    except FetchError as exc:
        out["errors"].append(tr("статистика: {0}", exc))
    return out


PART_SCOPES = ("all", "missing", "spare")
SELLERS_SHOWN = 3       # a missing part is shown with this many of its cheapest sellers who are in the game


def part_scope(value: str) -> str:
    """The `scope` of a /api/parts-market request; anything unknown means every part."""
    return value if value in PART_SCOPES else "all"


def sellers_of_part(top: Dict[str, Any], item_en: str, units: int) -> List[Dict[str, Any]]:
    """The cheapest sellers of a part who are in the game right now, each with the message for them.

    units -- how many of the part the set still lacks: a seller who has that many is asked for all
    of them (the price in the message stays the price of one, as on the site).
    """
    out = []
    for offer in analysis.offers_from_orders(top)[:SELLERS_SHOWN]:
        count = max(1, min(units, offer["quantity"]))
        out.append({**offer, "count": count, "message": whisper(offer["user"], item_en, offer["platinum"], count)})
    return out


def parts_market(state: AppState, slug: str, force: bool, scope: str = "all") -> Dict[str, Any]:
    """Live prices of a set's parts.

    scope="all":     every part; `total` is the price of one set bought part by part.
    scope="missing": only the parts the inventory lacks for the next full copy;
                     `total` is what it costs to buy exactly those.  Each part also comes with its
                     cheapest sellers who are in the game (sellers_of_part) -- from the same answer
                     of the market that gave the price, so no further request is made for them.
    scope="spare":   only the parts left over beyond the full copies; `total` is what they sell for.
    """
    cat = state.catalog
    if not cat or slug not in cat["sets"]:
        raise KeyError(slug)
    st = cat["sets"][slug]
    progress = analysis.set_progress(st, inventory.load()["items"])
    lacking = {m["slug"]: m["count"] for m in progress["missing"]}
    spare = {m["slug"]: m["count"] for m in progress["spare"]}
    parts = []
    total: Optional[float] = 0
    errors = []
    asked_at: List[float] = []
    for p in st["parts"]:
        if (scope == "missing" and p["slug"] not in lacking) or (scope == "spare" and p["slug"] not in spare):
            continue
        units = lacking[p["slug"]] if scope == "missing" else spare[p["slug"]] if scope == "spare" else p["quantity"]
        row: Dict[str, Any] = {"slug": p["slug"], "units": units, "price": None, "basis": None}
        if scope == "missing":
            row.update(sellers=[], orders_at=None)
        try:
            top, meta = state.wfm.top_orders(p["slug"], force=force)
            price = analysis.price_from_orders(top)
            row["price"], row["basis"] = price["value"], price["basis"]
            when = meta.get("fetched_at")
            if isinstance(when, (int, float)):
                asked_at.append(when)
            if scope == "missing":
                row.update(sellers=sellers_of_part(top, p["en"], units), orders_at=when)
        except FetchError as exc:
            errors.append(f"{p['slug']}: {exc}")
        if row["price"] is None:
            total = None
        elif total is not None:
            total += row["price"] * units
        parts.append(row)
    return {"slug": slug, "scope": scope, "parts": parts, "total": total, "errors": errors,
            "oldest_at": min(asked_at, default=None), "ttl_orders": config.TTL_TOP_ORDERS}


MAX_BOUGHT = 99


def bought(state: AppState, slug: str, count: Any = 1, platinum: Any = None, seller: str = "",
           undo: bool = False) -> Dict[str, Any]:
    """The user bought a part ("Купил" next to a seller): add it to the inventory.  undo=True takes
    it back out -- the button was pressed by mistake.

    The app cannot see a trade: it only writes down what it was told.  The update goes into the
    history as a purchase, with what was bought, for how much and from whom.
    """
    cat = state.catalog
    owner = cat["part_index"].get(slug) if cat else None
    if not owner:
        raise ValueError(f"unknown part: {slug}")
    try:
        n = int(count)
    except (TypeError, ValueError):
        raise ValueError(tr("Количество должно быть от 1 до 99")) from None
    if not 1 <= n <= MAX_BOUGHT:
        raise ValueError(tr("Количество должно быть от 1 до 99"))
    part = next(p for p in cat["sets"][owner]["parts"] if p["slug"] == slug)
    if undo:
        note = tr("отмена покупки: {0}", part["name"] + (f" ×{n}" if n > 1 else ""))
        return inventory.change({slug: -n}, cat, kind="purchase", note=note)
    priced = isinstance(platinum, (int, float)) and not isinstance(platinum, bool) and 0 < platinum <= sales.MAX_PLATINUM
    note = tr("{0} ×{1} за {2} пл", part["name"], n, int(platinum) * n) if priced else f"{part['name']} ×{n}"
    who = " ".join(str(seller or "").split())[:60]
    if who:
        note += f" ({who})"
    return inventory.change({slug: n}, cat, kind="purchase", note=note)


def all_parts(state: AppState) -> List[Dict[str, Any]]:
    cat = state.catalog
    if not cat:
        return []
    out = []
    for st in cat["sets"].values():
        for p in st["parts"]:
            out.append({"slug": p["slug"], "name": p["name"], "en": p["en"], "label": p["label"],
                        "set": st["title"], "set_slug": st["slug"], "quantity": p["quantity"]})
    out.sort(key=lambda r: (r["set"].lower(), r["label"]))
    return out


def settings_payload(force: bool = False) -> Dict[str, Any]:
    """Everything the settings dialog shows.  No key and no proxy password ever goes to the page."""
    conf = settings.load()
    everyone = providers.everyone()
    states: List[Optional[Dict[str, Any]]] = [None] * len(everyone)

    def ask(i: int) -> None:
        try:
            states[i] = everyone[i].status(force)
        except Exception as exc:  # one broken check must not empty the dialog
            log.exception("status of %s failed", everyone[i].id)
            states[i] = {"id": everyone[i].id, "kind": everyone[i].kind, "ready": False, "reason": "error",
                         "error": str(exc), "model": "", "models": []}

    # the two command-line checks start a process each: side by side they take half the time
    threads = [threading.Thread(target=ask, args=(i,), daemon=True) for i in range(len(everyone))]
    for th in threads:
        th.start()
    for th in threads:
        th.join(40)
    return {
        "language": settings.language(), "language_set": conf["language"],
        "game_language": conf["game_language"],
        "languages": settings.languages(),
        "provider": conf["provider"],
        "providers": [st for st in states if st],
        "parallel": conf["parallel"],
        "check_updates": conf["check_updates"],
        "proxy": {"set": bool(vault.proxy()), "hint": vault.proxy_hint()},
        "vault": vault.available(),
        "data_dir": str(config.DATA_DIR), "version": __version__, "frozen": config.FROZEN, "portable": config.PORTABLE,
        "homepage": HOMEPAGE,
    }


def _allowed_api_address(url: str) -> bool:
    """Another address for an API: https only -- the key travels there -- or a server on this computer."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return True
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")


def change_settings(state: AppState, payload: Dict[str, Any]) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    for key in ("language", "game_language"):
        if key in payload:
            value = payload[key]
            if value not in ("", None) and not i18n.valid(value):
                raise ValueError(tr("Такого языка в приложении нет"))
            patch[key] = value or ""
    if "provider" in payload:
        if payload["provider"] not in settings.PROVIDERS:
            raise ValueError(tr("Неизвестное подключение"))
        patch["provider"] = payload["provider"]
    if "parallel" in payload:
        patch["parallel"] = payload["parallel"]
    for key in ("check_updates", "welcomed"):
        if key in payload:
            patch[key] = bool(payload[key])
    for key in ("models", "use_proxy"):
        if isinstance(payload.get(key), dict):
            patch[key] = payload[key]
    if isinstance(payload.get("base_urls"), dict):
        for pid, url in payload["base_urls"].items():
            if isinstance(url, str) and url.strip() and not _allowed_api_address(url.strip()):
                raise ValueError(tr("Адрес API должен начинаться с https://"))
        patch["base_urls"] = payload["base_urls"]
    before = (settings.language(), settings.game_language())
    settings.save(patch)
    after = (settings.language(), settings.game_language())
    if after != before:
        state.apply_language()
    if "check_updates" in patch:
        state.check_update()             # switched on: ask now; switched off: forget the answer
    out = settings_payload()
    out["reload"] = after[0] != before[0]          # the page reloads itself to show the other language
    return out


def licenses_text() -> str:
    """The license of the program and -- in the packed exe -- of the libraries packed with it."""
    folder = config.BUNDLE_DIR / "licenses"
    own = folder / "LICENSE.txt" if (folder / "LICENSE.txt").is_file() else config.SOURCE_ROOT / "LICENSE"
    parts = []
    try:
        parts.append(own.read_text(encoding="utf-8"))
    except OSError:
        parts.append("MIT License")
    try:
        parts.append((folder / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8"))
    except OSError:
        pass
    return ("\n\n" + "=" * 78 + "\n\n").join(parts)


def list_screenshots() -> List[Dict[str, Any]]:
    out = []
    for f in shots.originals():
        try:
            st = f.stat()
        except OSError:
            continue
        out.append({"name": f.name, "size": st.st_size, "mtime": st.st_mtime})
    return out


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{__version__}"
    protocol_version = "HTTP/1.1"
    state: AppState = None  # type: ignore[assignment]

    def log_message(self, fmt, *args):  # quiet: requests go to the log file at debug level only
        log.debug("%s %s", self.address_string(), fmt % args)

    # -- helpers ------------------------------------------------------------
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _send(self, status: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        headers = {"Cache-Control": "no-store"}
        headers.update(extra or {})
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj: Any, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    def _body(self, limit: int = MAX_BODY) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length < 0 or length > limit:
            raise ValueError("body too large")
        return self.rfile.read(length) if length else b""

    # -- routing ------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        if not self._host_ok():
            return self._error(403, "bad host")
        url = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(url.query)
        path = url.path
        st = self.state
        try:
            if path == "/api/ping":
                return self._json({"app": config.APP_ID, "version": __version__})
            if path == "/api/overview":
                st.ensure_catalog()
                return self._json(overview(st))
            if path == "/api/market":
                slug = (q.get("slug") or [""])[0]
                if not valid_slug(slug):
                    return self._error(400, "bad slug")
                return self._json(market(st, slug, (q.get("force") or ["0"])[0] == "1",
                                         lite=(q.get("lite") or ["0"])[0] == "1"))
            if path == "/api/parts-market":
                slug = (q.get("slug") or [""])[0]
                if not valid_slug(slug):
                    return self._error(400, "bad slug")
                scope = part_scope((q.get("scope") or [""])[0])
                return self._json(parts_market(st, slug, (q.get("force") or ["0"])[0] == "1", scope))
            if path == "/api/parts":
                return self._json({"parts": all_parts(st)})
            if path == "/api/ducats":
                st.ensure_catalog()
                return self._json(ducat_sets(st))
            if path == "/api/sell-now":
                return self._json(sell_now(st))
            if path == "/api/sales":
                return self._json(sales.payload(st.catalog))
            if path == "/api/baro":
                st.ensure_catalog()
                return self._json(baro(st))
            if path == "/api/collection":
                st.ensure_catalog()
                return self._json(collection(st))
            if path == "/api/tile":
                return self._tile((q.get("name") or [""])[0], (q.get("row") or [""])[0], (q.get("col") or [""])[0])
            if path == "/api/history":
                if demo.on():            # the example has no past, and the user's own is not mixed into it
                    return self._json({"updates": [], "values": [], "sales": {"sales": [], "totals": sales.totals([])}})
                changes = history.updates(st.catalog, inventory.load()) if st.catalog else []
                return self._json({"updates": changes, "values": history.values(), "sales": sales.payload(st.catalog)})
            if path == "/api/screenshots":
                return self._json({"files": list_screenshots(), "dir": str(config.SCREENSHOT_DIR)})
            if path == "/api/settings":
                return self._json(settings_payload((q.get("refresh") or ["0"])[0] == "1"))
            if path == "/licenses":
                return self._send(200, licenses_text().encode("utf-8"), "text/plain; charset=utf-8")
            if path == "/i18n.js":
                return self._send(200, i18n.page_script().encode("utf-8"), "application/javascript; charset=utf-8")
            if path == "/api/recognize":
                return self._json(st.recognition_state((q.get("refresh") or ["0"])[0] == "1"))
            if path == "/api/screenshot-thumb":
                return self._thumb((q.get("name") or [""])[0], large=(q.get("large") or ["0"])[0] == "1")
            if path == "/api/events":
                return self._events()
            if path == "/img":
                return self._image((q.get("p") or [""])[0])
            return self._static(path)
        except KeyError:
            return self._error(404, "not found")
        except (BrokenPipeError, ConnectionError):
            return None
        except Exception as exc:
            log.exception("GET %s failed", path)
            return self._error(500, str(exc))

    def do_HEAD(self):  # noqa: N802
        return self.do_GET()

    def do_POST(self):  # noqa: N802
        if not self._host_ok():
            return self._error(403, "bad host")
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        st = self.state
        try:
            if path == "/api/bye":           # sent by the page when its window closes
                self._body()
                st.bye_at = time.time()
                return self._json({"ok": True})
            if self.headers.get("X-Requested-With") != "primesets":
                return self._error(403, "missing header")
            if path == "/api/screenshot":
                return self._upload(urllib.parse.parse_qs(url.query))
            raw = self._body()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(payload, dict):
                return self._error(400, "bad payload")
            if path == "/api/inventory/set":
                if not st.catalog:
                    return self._error(409, tr("Справочник комплектов ещё не загружен"))
                slug = str(payload.get("slug") or "")
                inventory.set_count(slug, int(payload.get("count") or 0), st.catalog)
                st._inv_mtime = inventory.mtime()
                return self._json(overview(st))
            if path == "/api/inventory/bought":
                if not st.catalog:
                    return self._error(409, tr("Справочник комплектов ещё не загружен"))
                bought(st, str(payload.get("slug") or ""), payload.get("count") or 1, payload.get("platinum"),
                       str(payload.get("seller") or ""), undo=payload.get("undo") is True)
                st._inv_mtime = inventory.mtime()
                return self._json(overview(st))
            if path == "/api/inventory/dismiss-review":
                inventory.dismiss_review(int(payload.get("index", -1)))
                st._inv_mtime = inventory.mtime()
                return self._json(overview(st))
            if path == "/api/mastery/set":
                if not st.catalog:
                    return self._error(409, tr("Справочник комплектов ещё не загружен"))
                state_value = payload.get("state")
                mastery.set_state(str(payload.get("slug") or ""),
                                  state_value if state_value in mastery.STATES else None, st.catalog)
                st._mastery_mtime = mastery.mtime()
                return self._json(overview(st))
            if path == "/api/catalog/refresh":
                started = st.ensure_catalog(force=True)
                return self._json({"started": started, "catalog": st.catalog_status()})
            if path == "/api/history/value":
                # the page reports what the complete sets add up to once all their prices are in
                value, sets = float(payload.get("value") or 0), int(payload.get("sets") or 0)
                if not (0 <= value < 10 ** 8) or not (0 <= sets < 10 ** 4):
                    return self._error(400, "bad value")
                if demo.on():            # what the made-up inventory is worth is nobody's history
                    return self._json({"ok": True, "today": None, "values": []})
                rec = history.record_value(value, sets, int(payload.get("copies") or 0), int(payload.get("priced") or 0))
                return self._json({"ok": True, "today": rec, "values": history.values()})
            if path in ("/api/sales/add", "/api/sales/undo"):
                if not st.catalog:
                    return self._error(409, tr("Справочник комплектов ещё не загружен"))
                if path == "/api/sales/add":
                    sales.add(st.catalog, str(payload.get("slug") or ""), payload.get("platinum"),
                              payload.get("count") or 1, str(payload.get("buyer") or ""))
                else:
                    sales.undo(st.catalog, str(payload.get("id") or ""))
                st._inv_mtime = inventory.mtime()
                return self._json({"overview": overview(st), "sales": sales.payload(st.catalog)})
            if path == "/api/sales/plan":
                if not st.catalog:
                    return self._error(409, tr("Справочник комплектов ещё не загружен"))
                target = int(payload.get("target") or 0)
                if not 1 <= target <= 1000000:
                    return self._error(400, tr("Укажите, сколько платины нужно: от 1 до 1 000 000"))
                raw = payload.get("exclude")
                exclude = [str(x)[:200] for x in raw][:2000] if isinstance(raw, list) else []
                return self._json(sales_plan(st, target, payload.get("keep_unmastered") is not False, exclude))
            if path == "/api/demo":
                wanted = bool(payload.get("on"))
                if wanted and not demo.on() and inventory.load()["items"]:
                    return self._error(409, tr("Пример показывается, только пока своего инвентаря нет"))
                demo.switch(wanted)
                return self._json(overview(st))
            if path == "/api/live":
                if payload.get("on"):
                    if st.job and st.job.state == "running":
                        return self._error(409, tr("Дождитесь конца распознавания"))
                    if st.job and st.job.state != "running":
                        st.job.discard()             # new screenshots are coming: the old reading no longer fits
                        st.job = None
                    st.live.start(sound=payload.get("sound") is not False)
                else:
                    st.live.stop()
                return self._json(st.recognition_state())
            if path == "/api/ducats/plan":
                if not st.catalog:
                    return self._error(409, tr("Справочник комплектов ещё не загружен"))
                target = int(payload.get("target") or 0)
                if not 5 <= target <= 50000:
                    return self._error(400, tr("Укажите число дукатов от 5 до 50 000"))
                raw = payload.get("exclude")
                exclude = [str(x)[:200] for x in raw][:2000] if isinstance(raw, list) else []
                return self._json(ducat_plan(st, target, exclude))
            if path.startswith("/api/recognize/") or path in ("/api/screenshots/remove", "/api/screenshots/from-game"):
                return self._recognize(path, payload)
            if path == "/api/settings" or path.startswith("/api/settings/"):
                return self._settings(path, payload)
            if path == "/api/open-folder":
                which = payload.get("which")
                target = {"screenshots": config.SCREENSHOT_DIR, "app": config.ROOT, "data": config.DATA_DIR}.get(which)
                if which == "game":
                    target = shots.game_dir()
                if target is None:
                    return self._error(400, "bad folder")
                target.mkdir(parents=True, exist_ok=True)
                if hasattr(os, "startfile"):
                    os.startfile(str(target))  # noqa: S606 - opens Explorer on a fixed app folder
                return self._json({"ok": True, "path": str(target)})
            return self._error(404, "not found")
        except ValueError as exc:
            return self._error(400, str(exc))
        except (BrokenPipeError, ConnectionError):
            return None
        except Exception as exc:
            log.exception("POST %s failed", path)
            return self._error(500, str(exc))

    # -- handlers -----------------------------------------------------------
    def _settings(self, path: str, payload: Dict[str, Any]) -> None:
        """The settings dialog: language, the connection for reading screenshots, keys, proxy."""
        st = self.state
        pid = str(payload.get("provider") or "")
        try:
            if path == "/api/settings":
                return self._json(change_settings(st, payload))
            if path == "/api/settings/proxy":
                try:
                    url = vault.check_proxy(str(payload.get("url") or ""))
                except ValueError:
                    return self._error(400, tr("Адрес прокси должен выглядеть как http://адрес:порт (SOCKS не подходит)"))
                vault.put(vault.PROXY, url)
                return self._json(settings_payload())
            if pid not in settings.PROVIDERS:
                return self._error(400, tr("Неизвестное подключение"))
            provider = providers.get(pid)
            if path == "/api/settings/key":
                if provider.kind != "api":
                    return self._error(400, tr("Этому подключению ключ не нужен"))
                key = str(payload.get("key") or "").strip()
                if key and (len(key) < 8 or len(key) > 400 or any(ch.isspace() for ch in key)):
                    return self._error(400, tr("Это не похоже на API-ключ: проверьте, что скопировали его целиком"))
                vault.put(pid, key)
                return self._json(settings_payload())
            if path == "/api/settings/check":
                return self._json(provider.check())
            if path == "/api/settings/login":
                provider.login()
                return self._json({"ok": True})
        except recognize.RecognizeError as exc:
            return self._json({"error": str(exc), "code": exc.code}, 409)
        except OSError as exc:
            log.error("settings: %s failed (%s)", path, exc.__class__.__name__)
            return self._error(500, tr("Не удалось сохранить: {0}", exc))
        return self._error(404, "not found")

    def _recognize(self, path: str, payload: Dict[str, Any]) -> None:
        st = self.state
        try:
            if path == "/api/recognize/start":
                st.start_recognition()
            elif path == "/api/recognize/cancel":
                if st.job:
                    st.job.cancel()
            elif path == "/api/recognize/dismiss":
                if st.job and st.job.state != "running":
                    st.job.discard()
                    st.job = None
            elif path == "/api/recognize/login":
                providers.current().login()
            elif path == "/api/recognize/apply":
                if not st.job:
                    raise recognize.RecognizeError(tr("Нет результата распознавания"), "state")
                mode = "merge" if payload.get("mode") == "merge" else "replace"
                demo.switch(False)
                result = st.job.apply(mode, force=bool(payload.get("force")))
                st.job = None
                st._inv_mtime, st._mastery_mtime = inventory.mtime(), mastery.mtime()
                return self._json({"ok": True, "result": result, "overview": overview(st),
                                   "recognize": st.recognition_state()})
            elif path == "/api/recognize/fix":
                if not st.job:
                    raise recognize.RecognizeError(tr("Нет результата распознавания"), "state")
                count = payload.get("count")
                st.job.fix(int(payload.get("entry", -1)), count=int(count) if count is not None else None,
                           slug=str(payload["slug"]) if payload.get("slug") else None, skip=bool(payload.get("skip")))
            elif path == "/api/screenshots/from-game":
                if st.job and st.job.state == "running":
                    raise recognize.RecognizeError(tr("Дождитесь конца распознавания"), "busy")
                if payload.get("skip"):
                    shots.game_mark_seen()
                else:
                    shots.game_import()
                if st.job and st.job.state != "running":
                    st.job.discard()
                    st.job = None
            elif path == "/api/screenshots/remove":
                if st.job and st.job.state == "running":
                    raise recognize.RecognizeError(tr("Дождитесь конца распознавания"), "busy")
                if payload.get("all"):
                    shots.archive(label="removed")
                else:
                    target = shots.find(str(payload.get("name") or ""))
                    if target:
                        shots.archive([target], label="removed")
                if st.job and st.job.state != "running":
                    st.job.discard()
                    st.job = None            # the reviewed batch no longer matches the folder
            else:
                return self._error(404, "not found")
        except recognize.RecognizeError as exc:
            return self._json({"error": str(exc), "code": exc.code}, 409)
        return self._json(st.recognition_state(refresh=path == "/api/recognize/login"))

    def _thumb(self, name: str, large: bool = False) -> None:
        target = shots.find(name)
        if not target:
            return self._error(404, "no such screenshot")
        try:
            key = (target.name, target.stat().st_mtime_ns, large)
        except OSError:
            return self._error(404, "no such screenshot")
        cache = self.state._thumbs
        data = cache.get(key)
        if data is None:
            # large: big enough to read the captions when the user looks for the place of a gap
            data = shots.thumbnail(target, 1600) if large else shots.thumbnail(target)
            if data and not large:
                if len(cache) > 400:
                    cache.clear()
                cache[key] = data
        if data:
            return self._send(200, data, "image/jpeg", {"Cache-Control": "private, max-age=300"})
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), ctype, {"Cache-Control": "private, max-age=300"})

    def _tile(self, name: str, row: str, col: str) -> None:
        """One tile of an inventory screenshot: the picture a line of the reading came from."""
        target = shots.find(name)
        try:
            place = (int(row), int(col))
            key = (target.name, target.stat().st_mtime_ns, "tile") + place if target else None
        except (ValueError, OSError):
            key = None
        if key is None:
            return self._error(404, "no such tile")
        cache = self.state._thumbs
        data = cache.get(key)
        if data is None:
            data = continuity.tile_picture(target, *place)
            if data:
                if len(cache) > 400:
                    cache.clear()
                cache[key] = data
        if not data:
            return self._error(404, "no such tile")
        self._send(200, data, "image/jpeg", {"Cache-Control": "private, max-age=300"})

    def _upload(self, q: Dict[str, List[str]]) -> None:
        name = os.path.basename((q.get("name") or ["screenshot.png"])[0])
        name = _NAME_RE.sub("_", name).strip(" .") or "screenshot.png"
        ext = os.path.splitext(name)[1].lower()
        if ext not in SCREENSHOT_EXT:
            return self._error(400, tr("Подходят только картинки: png, jpg, webp, bmp"))
        data = self._body(MAX_SCREENSHOT)
        if not data:
            return self._error(400, tr("Пустой файл"))
        config.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        target = config.SCREENSHOT_DIR / name
        stem, n = os.path.splitext(name)[0], 1
        while target.exists():
            n += 1
            target = config.SCREENSHOT_DIR / f"{stem} ({n}){ext}"
        target.write_bytes(data)
        return self._json({"ok": True, "name": target.name, "files": list_screenshots()})

    def _image(self, rel: str) -> None:
        got = self.state.wfm.thumbnail(rel)
        if not got:
            return self._error(404, "no image")
        data, mime = got
        self._send(200, data, mime, {"Cache-Control": "public, max-age=2592000, immutable"})

    def _static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        rel = path.lstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", rel):
            return self._error(404, "not found")
        target = config.WEB_DIR / rel
        if not target.is_file():
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        body = target.read_bytes()
        if rel == "index.html":                 # the page's own texts, in the language of the settings
            body = i18n.render_html(body.decode("utf-8")).encode("utf-8")
        self._send(200, body, ctype, {"Cache-Control": "no-cache"})

    def _events(self) -> None:
        st = self.state
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        q = st.add_client()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while not st.stop_event.is_set():
                try:
                    msg = q.get(timeout=2.0)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                if msg is None:
                    break
                chunk = f"event: {msg['event']}\ndata: {json.dumps(msg['data'], ensure_ascii=False)}\n\n"
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        finally:
            st.remove_client(q)
            self.close_connection = True


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def make_server(state: AppState, port: int) -> Server:
    handler = type("BoundHandler", (Handler,), {"state": state})
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("image/svg+xml", ".svg")
    return Server((config.HOST, port), handler)
