"""Is there a newer version of the program?

One question to the page of the project (GitHub) when the app starts -- and only while the user has
not switched it off in the settings.  Nothing is downloaded and nothing is installed: the app only
says that a newer version exists and where its page is.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional, Tuple

from . import HOMEPAGE, __version__, wfm

CACHE_KEY = "update_check"
TTL = 12 * 3600                 # at most two questions a day, however often the app is started
_REPO_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)/?$")
_VERSION_RE = re.compile(r"\s*v?(\d{1,4}(?:\.\d{1,4}){0,3})\s*")


def parse(text: Any) -> Optional[Tuple[int, ...]]:
    """"v1.2.3" -> (1, 2, 3); None for anything that is not a plain version number."""
    m = _VERSION_RE.fullmatch(str(text or ""))
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def newer(latest: Any, current: Any) -> bool:
    a, b = parse(latest), parse(current)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def api_url(homepage: str = HOMEPAGE) -> Optional[str]:
    """The address that names the latest release of a project kept on GitHub."""
    m = _REPO_RE.match(homepage or "")
    return f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/releases/latest" if m else None


def page_url(homepage: str = HOMEPAGE) -> str:
    """Where a person gets the new version: the page of the latest release."""
    return homepage.rstrip("/") + "/releases/latest" if homepage else ""


def check(cache: Any, force: bool = False, fetch: Optional[Callable[..., bytes]] = None,
          current: str = __version__) -> Dict[str, Any]:
    """{"state": "newer" | "current" | "unknown", "latest", "current", "url", "checked_at"}.

    "unknown" -- the question could not be asked or answered (no network, no page of the project);
    the app then simply says nothing.
    """
    out: Dict[str, Any] = {"state": "unknown", "latest": "", "current": current, "url": page_url(), "checked_at": None}
    url = api_url()
    if not url:
        return out
    hit = None if force else cache.get(CACHE_KEY, TTL)
    if hit is not None and isinstance(hit[0], dict) and parse(hit[0].get("latest")):
        latest, checked = str(hit[0]["latest"]), hit[1]
    else:
        try:
            raw = (fetch or wfm.http_get)(url, headers={"Accept": "application/vnd.github+json"}, timeout=10)
            tag = json.loads(raw.decode("utf-8")).get("tag_name")
        except (wfm.FetchError, ValueError, AttributeError):
            return out
        numbers = parse(tag)
        if not numbers:
            return out
        latest = ".".join(map(str, numbers))
        checked = cache.put(CACHE_KEY, {"latest": latest})
    out.update({"latest": latest, "checked_at": checked, "state": "newer" if newer(latest, current) else "current"})
    return out
