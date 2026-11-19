"""warframe.market client: polite (rate-limited, one request at a time) and cached.

Only public, read-only endpoints are used; no account, no token, no orders are
ever placed.  The site's Terms of Service (section 11, "API") allow no more than
3 requests per second -- see config.WFM_MIN_INTERVAL.
"""
from __future__ import annotations

import gzip
import json
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import config
from .cache import DiskCache


class FetchError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, url: str = ""):
        super().__init__(message)
        self.status = status
        self.url = url


class RateLimiter:
    """Serialises requests and keeps a minimum interval between their starts."""

    def __init__(self, min_interval: float):
        self.min_interval = float(min_interval)
        self._serial = threading.Lock()
        self._next_start = 0.0

    def __enter__(self):
        self._serial.acquire()
        # perf_counter, not monotonic: on Windows the latter ticks every ~16 ms and
        # sleep() may return early, which would let a request through too soon
        while True:
            delay = self._next_start - time.perf_counter()
            if delay <= 0:
                break
            time.sleep(delay)
        self._next_start = time.perf_counter() + self.min_interval
        return self

    def __exit__(self, *exc):
        # the interval is counted from the end of the request too, so a slow
        # response never lets two requests land inside the same window
        self._next_start = max(self._next_start, time.perf_counter() + self.min_interval / 2)
        self._serial.release()
        return False


def http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 30.0) -> bytes:
    req_headers = {
        "User-Agent": config.USER_AGENT,
        "Accept-Encoding": "gzip",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                body = gzip.decompress(body)
            return body
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        err = FetchError(f"HTTP {exc.code} for {url}", status=exc.code, url=url)
        err.retry_after = retry_after  # type: ignore[attr-defined]
        raise err from None
    except (urllib.error.URLError, TimeoutError, OSError, EOFError) as exc:
        raise FetchError(f"network error for {url}: {exc}", status=None, url=url) from None


class Fetcher:
    """Rate-limited GET with retries and request accounting."""

    def __init__(self, min_interval: float, name: str):
        self.name = name
        self.limiter = RateLimiter(min_interval)
        self.requests_made = 0
        self.errors = 0
        self.last_error: Optional[str] = None
        self.last_request_at: Optional[float] = None
        self._stat_lock = threading.Lock()

    def get(self, url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 30.0, retries: int = 3) -> bytes:
        attempt = 0
        while True:
            attempt += 1
            with self.limiter:
                with self._stat_lock:
                    self.requests_made += 1
                    self.last_request_at = time.time()
                try:
                    return http_get(url, headers=headers, timeout=timeout)
                except FetchError as exc:
                    with self._stat_lock:
                        self.errors += 1
                        self.last_error = str(exc)
                    status = exc.status
                    retriable = status is None or status == 429 or 500 <= status < 600
                    if not retriable or attempt > retries:
                        raise
                    wait = min(30.0, 1.5 * (2 ** (attempt - 1)))
                    if status == 429:
                        ra = getattr(exc, "retry_after", None)
                        try:
                            wait = min(60.0, max(wait, float(ra))) if ra else max(wait, 5.0)
                        except ValueError:
                            wait = max(wait, 5.0)
                    # sleep while still holding the limiter: nobody else may hammer the site meanwhile
                    time.sleep(wait)


_THUMB_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,200}\.(png|webp|jpg|jpeg)$")
_SLUG_RE = re.compile(r"^[a-z0-9_]{1,80}$")


def valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug or ""))


class WfmClient:
    def __init__(self, cache: DiskCache):
        self.cache = cache
        self.api = Fetcher(config.WFM_MIN_INTERVAL, "warframe.market API")
        self.assets = Fetcher(config.ASSET_MIN_INTERVAL, "warframe.market assets")
        self._key_locks: Dict[str, threading.Lock] = {}
        self._key_locks_guard = threading.Lock()

    # -- plumbing -----------------------------------------------------------
    def _lock_for(self, key: str) -> threading.Lock:
        with self._key_locks_guard:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = self._key_locks[key] = threading.Lock()
            return lock

    def _json(self, path: str, language: str = "en") -> Any:
        headers = {
            "Accept": "application/json",
            "Language": language,
            "Platform": config.PLATFORM,
        }
        raw = self.api.get(config.WFM_API + path, headers=headers)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise FetchError(f"bad JSON from {path}: {exc}") from None

    def _cached(self, key: str, ttl: float, loader: Callable[[], Any], force: bool = False,
                allow_stale: bool = True) -> Tuple[Any, Dict[str, Any]]:
        """Return (data, meta). meta: fetched_at, cached (bool), stale (bool), error (str|None)."""
        with self._lock_for(key):
            if not force:
                hit = self.cache.get(key, ttl)
                if hit is not None:
                    return hit[0], {"fetched_at": hit[1], "cached": True, "stale": False, "error": None}
            try:
                data = loader()
            except FetchError as exc:
                old = self.cache.get(key, None) if allow_stale else None
                if old is not None:
                    return old[0], {"fetched_at": old[1], "cached": True, "stale": True, "error": str(exc)}
                raise
            fetched_at = self.cache.put(key, data)
            return data, {"fetched_at": fetched_at, "cached": False, "stale": False, "error": None}

    # -- endpoints ----------------------------------------------------------
    def items(self, language: str = "en", force: bool = False) -> Tuple[List[dict], Dict[str, Any]]:
        """All tradable items: slug, tags, relic `vaulted` flags, the English name and the name in
        `language` (a code of warframe.market: ru, de, fr, pl, zh-hans...)."""
        if not re.fullmatch(r"[a-z]{2}(-[a-z]{2,4})?", language or ""):
            raise FetchError(f"bad language {language!r}")

        def load():
            box = self._json("/v2/items", language)
            data = box.get("data")
            if not isinstance(data, list) or len(data) < 500:
                raise FetchError("unexpected /v2/items payload")
            slim = []
            for it in data:
                i18n = it.get("i18n") or {}
                en = i18n.get("en") or {}
                own = i18n.get(language) or {}
                slim.append({
                    "id": it.get("id"),
                    "slug": it.get("slug"),
                    "tags": it.get("tags") or [],
                    "ducats": it.get("ducats"),
                    "vaulted": it.get("vaulted"),
                    "en": en.get("name") or "",
                    "name": own.get("name") or en.get("name") or "",
                    "thumb": en.get("thumb") or own.get("thumb") or "",
                })
            return slim
        return self._cached(f"wfm_items_{language}", config.TTL_ITEMS, load, force)

    def item_set(self, slug: str, force: bool = False) -> Tuple[List[dict], Dict[str, Any]]:
        """Composition of a set: every member with its quantityInSet."""
        if not valid_slug(slug):
            raise FetchError(f"bad slug {slug!r}")

        def load():
            box = self._json(f"/v2/item/{slug}/set")
            items = ((box.get("data") or {}).get("items")) or []
            if not items:
                raise FetchError(f"empty set payload for {slug}")
            out = []
            for it in items:
                out.append({
                    "id": it.get("id"),
                    "slug": it.get("slug"),
                    "set_root": bool(it.get("setRoot")),
                    "quantity": int(it.get("quantityInSet") or 1),
                    "tags": it.get("tags") or [],
                    "ducats": it.get("ducats"),
                    "tradable": it.get("tradable", True),
                })
            return out
        return self._cached(f"wfm_set_{slug}", config.TTL_SET, load, force)

    def top_orders(self, slug: str, force: bool = False) -> Tuple[dict, Dict[str, Any]]:
        """Cheapest sell and highest buy orders of players who are online right now."""
        if not valid_slug(slug):
            raise FetchError(f"bad slug {slug!r}")

        def slim(order: dict) -> dict:
            user = order.get("user") or {}
            return {
                "platinum": order.get("platinum"),
                "quantity": order.get("quantity"),
                "status": user.get("status"),
                "platform": user.get("platform"),
                "user": user.get("ingameName"),
                "reputation": user.get("reputation"),
            }

        def load():
            box = self._json(f"/v2/orders/item/{slug}/top")
            data = box.get("data") or {}
            return {
                "sell": [slim(o) for o in (data.get("sell") or []) if o.get("visible", True)],
                "buy": [slim(o) for o in (data.get("buy") or []) if o.get("visible", True)],
            }
        return self._cached(f"wfm_top_{slug}", config.TTL_TOP_ORDERS, load, force)

    def top_orders_cached(self, slug: str) -> Optional[Tuple[dict, float]]:
        """What the last top_orders() of this item returned and when -- however old, without any request.

        For lists of many items (every set of the catalog): show what is known at once,
        and let the user decide when to spend 160 requests on fresh prices.
        """
        if not valid_slug(slug):
            return None
        return self.cache.get(f"wfm_top_{slug}", None)

    def statistics(self, slug: str, force: bool = False) -> Tuple[dict, Dict[str, Any]]:
        """Closed-deal statistics: one row per day for the last 90 days."""
        if not valid_slug(slug):
            raise FetchError(f"bad slug {slug!r}")

        def load():
            headers = {"Accept": "application/json", "Platform": config.PLATFORM, "Language": "en"}
            try:
                raw = self.api.get(f"{config.WFM_API}/v1/items/{slug}/statistics", headers=headers)
            except FetchError as exc:
                if exc.status == 404:
                    return {"days": []}
                raise
            try:
                payload = json.loads(raw.decode("utf-8")).get("payload") or {}
            except ValueError as exc:
                raise FetchError(f"bad JSON from statistics/{slug}: {exc}") from None
            closed = (payload.get("statistics_closed") or {}).get("90days") or []
            days = []
            for row in closed:
                # sets/parts have no ranks; mods would add `mod_rank`, which we do not use
                days.append({
                    "date": (row.get("datetime") or "")[:10],
                    "volume": row.get("volume") or 0,
                    "median": row.get("median"),
                    "avg": row.get("avg_price"),
                    "wavg": row.get("wa_price"),
                    "min": row.get("min_price"),
                    "max": row.get("max_price"),
                })
            days = [d for d in days if d["date"]]
            days.sort(key=lambda d: d["date"])
            return {"days": days}
        return self._cached(f"wfm_stats_{slug}", config.TTL_STATISTICS, load, force)

    def thumbnail(self, rel_path: str) -> Optional[Tuple[bytes, str]]:
        """Item picture from the site's static assets, cached forever. Returns (bytes, mime)."""
        if not _THUMB_RE.match(rel_path or "") or ".." in rel_path:
            return None
        suffix = "." + rel_path.rsplit(".", 1)[-1].lower()
        mime = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}[suffix]
        key = "thumb_" + rel_path
        with self._lock_for(key):
            hit = self.cache.get_bytes(key, suffix)
            if hit:
                return hit, mime
            try:
                data = self.assets.get(config.WFM_ASSETS + rel_path, headers={"Accept": "image/*"}, timeout=20, retries=1)
            except FetchError:
                return None
            if not data or len(data) > 2_000_000:
                return None
            self.cache.put_bytes(key, suffix, data)
            return data, mime

    def counters(self) -> dict:
        return {
            "api_requests": self.api.requests_made,
            "api_errors": self.api.errors,
            "api_last_error": self.api.last_error,
            "asset_requests": self.assets.requests_made,
        }
