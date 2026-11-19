"""Official Digital Extremes drop tables -> which relic holds which prime part,
and which relics still drop in missions.

Source: https://www.warframe.com/droptables -- a public page DE generates from
its own data for players.  It is downloaded at most once a day.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from . import config
from .cache import DiskCache
from .wfm import Fetcher, FetchError

_SECTION_RE = re.compile(r'<h3 id="([^"]+)">')
_UPDATED_RE = re.compile(r"Last Update:</b>\s*([^<]+)<")
_RELIC_ROW_RE = re.compile(r'<th colspan="2">([^<]+)</th>|<td>([^<]*)</td><td>([^<]*)</td>')
_RELIC_HEAD_RE = re.compile(r"^(\w+ \w+) Relic \((\w+)\)$")
_RELIC_CELL_RE = re.compile(r"<td>(?:\d+X )?(\w+ \w+) Relic(?: \(\w+\))?</td>")
_RARITY_RE = re.compile(r"^\s*([A-Za-z ]+?)\s*\(([\d.]+)%\)\s*$")

RELIC_SECTION = "relicRewards"


def parse(html: str) -> Dict[str, Any]:
    """Parse the drop tables page.

    Returns {"updated": str, "relics": {relic: [{"item", "rarity", "chance"}]}, "active": [relic, ...]}
    where `active` lists relics that appear as a reward anywhere outside the relic
    table itself (missions, bounties, keys, enemy drops...).
    """
    marks = [(m.start(), m.group(1)) for m in _SECTION_RE.finditer(html)]
    if not marks:
        raise ValueError("drop tables: no sections found")
    sections: Dict[str, str] = {}
    for idx, (pos, sid) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(html)
        sections[sid] = html[pos:end]
    if RELIC_SECTION not in sections:
        raise ValueError("drop tables: relic section not found")

    relics: Dict[str, List[dict]] = {}
    current = None
    for m in _RELIC_ROW_RE.finditer(sections[RELIC_SECTION]):
        if m.group(1) is not None:
            head = _RELIC_HEAD_RE.match(m.group(1).strip())
            # contents are the same for every refinement; chances are read from Intact
            current = head.group(1) if head and head.group(2) == "Intact" else None
            if current is not None:
                relics.setdefault(current, [])
        elif current is not None:
            item = m.group(2).strip()
            rarity = _RARITY_RE.match(m.group(3) or "")
            relics[current].append({
                "item": item,
                "rarity": rarity.group(1).strip() if rarity else "",
                "chance": float(rarity.group(2)) if rarity else None,
            })

    active = set()
    for sid, text in sections.items():
        if sid == RELIC_SECTION:
            continue
        for m in _RELIC_CELL_RE.finditer(text):
            active.add(m.group(1))

    if len(relics) < 100 or not active:
        raise ValueError(f"drop tables: unexpected structure (relics={len(relics)}, active={len(active)})")

    updated = _UPDATED_RE.search(html)
    return {
        "updated": updated.group(1).strip() if updated else "",
        "relics": relics,
        "active": sorted(active & set(relics)),
    }


def load(cache: DiskCache, fetcher: Fetcher, force: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (parsed tables, meta). Falls back to the previous copy if the download fails."""
    key = "de_droptables"
    if not force:
        hit = cache.get(key, config.TTL_DROPTABLES)
        if hit is not None:
            return hit[0], {"fetched_at": hit[1], "stale": False, "error": None}
    try:
        raw = fetcher.get(config.DROPTABLES_URL, headers={"Accept": "text/html"}, timeout=90, retries=2)
        data = parse(raw.decode("utf-8", "replace"))
    except (FetchError, ValueError) as exc:
        old = cache.get(key, None)
        if old is not None:
            return old[0], {"fetched_at": old[1], "stale": True, "error": str(exc)}
        raise FetchError(f"drop tables unavailable: {exc}") from None
    fetched_at = cache.put(key, data)
    return data, {"fetched_at": fetched_at, "stale": False, "error": None}
