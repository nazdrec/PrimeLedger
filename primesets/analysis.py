"""Pure calculations: complete sets from an inventory, price and 3-month trend from market data."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from . import config
from .i18n import tr


# --------------------------------------------------------------------------- sets
def set_progress(st: Dict[str, Any], items: Dict[str, int]) -> Dict[str, Any]:
    """How many full copies of the set the inventory holds, and what is missing for one more."""
    parts = []
    complete: Optional[int] = None
    owned_kinds = 0
    for p in st["parts"]:
        owned = int(items.get(p["slug"], 0))
        need = int(p["quantity"])
        full = owned // need
        complete = full if complete is None else min(complete, full)
        if owned:
            owned_kinds += 1
        parts.append({"slug": p["slug"], "owned": owned, "quantity": need})
    complete = complete or 0
    missing = []
    spare = []
    for p in parts:
        lack = p["quantity"] * (complete + 1) - p["owned"]
        p["missing_for_next"] = max(0, lack)
        p["spare"] = p["owned"] - p["quantity"] * complete
        if lack > 0:
            missing.append({"slug": p["slug"], "count": lack})
        if p["spare"] > 0:
            spare.append({"slug": p["slug"], "count": p["spare"]})
    return {
        "complete": complete,
        "owned_kinds": owned_kinds,
        "total_kinds": len(parts),
        "parts": parts,
        "missing": missing,
        "spare": spare,
    }


def split_inventory(catalog: Dict[str, Any], items: Dict[str, int]) -> Dict[str, List[dict]]:
    """Return {"complete": [...], "partial": [...]} -- sets with at least one full copy,
    and sets where some parts are owned but a full copy is not assembled yet."""
    complete, partial = [], []
    for slug, st in catalog["sets"].items():
        prog = set_progress(st, items)
        if prog["owned_kinds"] == 0:
            continue
        row = {"slug": slug, **prog}
        (complete if prog["complete"] > 0 else partial).append(row)
    complete.sort(key=lambda r: catalog["sets"][r["slug"]]["title"].lower())
    partial.sort(key=lambda r: (sum(m["count"] for m in r["missing"]),
                                catalog["sets"][r["slug"]]["title"].lower()))
    return {"complete": complete, "partial": partial}


# --------------------------------------------------------------------------- ducats
def ducat_value(st: Dict[str, Any]) -> int:
    """What a whole set brings at the ducat kiosk: every part at its ducat price, counted as many
    times as the set needs it (a set is traded whole, its parts are handed in one by one)."""
    return sum(int(p.get("ducats") or 0) * int(p["quantity"]) for p in st["parts"])


def ducats_per_platinum(ducats: Optional[float], price: Optional[float]) -> Optional[float]:
    """How many ducats one platinum buys when the set costs `price`; None when either is unknown."""
    if not ducats or not price or price <= 0:
        return None
    return ducats / price


def offers_from_orders(top: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Sell orders of players who are in the game right now, the cheapest first.

    Only they can be traded with at once -- that is what a shopping list needs.
    """
    out = []
    for o in top.get("sell") or []:
        price, user = o.get("platinum"), str(o.get("user") or "").strip()
        if o.get("status") != "ingame" or not user or not isinstance(price, (int, float)) or price <= 0:
            continue
        qty = o.get("quantity")
        out.append({"user": user, "platinum": int(price) if float(price).is_integer() else price,
                    "quantity": int(qty) if isinstance(qty, (int, float)) and qty >= 1 else 1,
                    "reputation": o.get("reputation")})
    out.sort(key=lambda r: (r["platinum"], -r["quantity"], r["user"].lower()))
    return out


def plan_ducats(offers: List[Dict[str, Any]], target: int, max_copies: int = 20) -> Dict[str, Any]:
    """The cheapest way to at least `target` ducats out of the given offers.

    offers: [{"ducats": of one set, "platinum": for one set, "quantity": sets the seller has}, ...]
    Returns {"picks": [{"index": offer number, "count": sets to buy}], "ducats", "platinum", "reached"}.

    A set is bought whole, so "the best rate first" is not quite right at the end: the last purchase
    overshoots, and a small cheap set often closes the gap for less.  This is a knapsack; it is solved
    exactly over the offers that can matter -- the best rates up to several targets' worth plus the
    cheapest ones -- with platinum minimised first and the number of purchases (trades) second.
    """
    target = int(target)
    units: List[tuple] = []                      # one entry per set that can be bought: (rate, platinum, ducats, offer)
    for index, o in enumerate(offers):
        try:
            ducats, price = int(o["ducats"]), float(o["platinum"])
        except (KeyError, TypeError, ValueError):
            continue
        if ducats <= 0 or price <= 0 or target <= 0:
            continue
        copies = min(max(1, int(o.get("quantity") or 1)), max_copies, -(-target // ducats))
        units.extend((ducats / price, price, ducats, index) for _ in range(copies))
    if target <= 0 or not units:
        return {"picks": [], "ducats": 0, "platinum": 0, "reached": target <= 0}

    def answer(chosen: List[int]) -> Dict[str, Any]:
        counts: Dict[int, int] = {}
        for k in chosen:
            counts[units[k][3]] = counts.get(units[k][3], 0) + 1
        ducats = sum(units[k][2] for k in chosen)
        platinum = sum(units[k][1] for k in chosen)
        return {"picks": [{"index": i, "count": n} for i, n in sorted(counts.items())],
                "ducats": ducats, "platinum": int(platinum) if float(platinum).is_integer() else round(platinum, 2),
                "reached": ducats >= target}

    if sum(u[2] for u in units) <= target:
        return answer(list(range(len(units))))       # everything on offer is not more than what is needed

    # the offers that can matter: the best rates, a few targets' worth, and the cheapest ones (gap closers)
    by_rate = sorted(range(len(units)), key=lambda k: (-units[k][0], units[k][1], units[k][3]))
    pool, got = [], 0
    for k in by_rate:
        pool.append(k)
        got += units[k][2]
        if got >= 4 * target:
            break
    inside = set(pool)
    extra = 0
    for k in sorted(range(len(units)), key=lambda k: (units[k][1], -units[k][2], units[k][3])):
        if extra >= 60:
            break
        if k not in inside:
            pool.append(k)
            inside.add(k)
            extra += 1

    step = 0                                     # ducat prices are multiples of 5: count in such steps
    for k in pool:
        step = math.gcd(step, units[k][2])
    states = -(-target // step)
    pack = 4096                                  # platinum first, then the number of purchases
    inf = float("inf")
    best = [0.0] + [inf] * states                # best[s]: cost of reaching at least s steps of ducats
    took: List[bytearray] = []
    for k in pool:
        _rate, price, ducats, _index = units[k]
        width, cost = ducats // step, price * pack + 1
        row = bytearray(states + 1)
        for s in range(states, 0, -1):
            cand = best[s - width if s > width else 0] + cost
            if cand < best[s]:
                best[s] = cand
                row[s] = 1
        took.append(row)
    chosen, s = [], states
    for n in range(len(pool) - 1, -1, -1):
        if s > 0 and took[n][s]:
            chosen.append(pool[n])
            s = max(0, s - units[pool[n]][2] // step)
    return answer(chosen)


# --------------------------------------------------------------------------- selling
def buyers_from_orders(top: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Buy orders of players who are in the game right now, the most generous first.

    Only they can be traded with at once -- that is what "who buys my set now" needs.
    """
    out = []
    for o in top.get("buy") or []:
        price, user = o.get("platinum"), str(o.get("user") or "").strip()
        if o.get("status") != "ingame" or not user or not isinstance(price, (int, float)) or price <= 0:
            continue
        qty = o.get("quantity")
        out.append({"user": user, "platinum": int(price) if float(price).is_integer() else price,
                    "quantity": int(qty) if isinstance(qty, (int, float)) and qty >= 1 else 1,
                    "reputation": o.get("reputation")})
    out.sort(key=lambda r: (-r["platinum"], -r["quantity"], r["user"].lower()))
    return out


def recent_deals(days: List[Dict[str, Any]], today: Optional[date] = None, span: int = 7) -> int:
    """How many deals the statistics count over the last `span` days (the day before `today` and back:
    the site adds a day to its statistics only when the day is over)."""
    today = today or date.today()
    first = today - timedelta(days=span)
    total = 0
    for row in days or []:
        d = _parse_day(row.get("date", ""))
        vol = row.get("volume") or 0
        if d is not None and first <= d <= today and isinstance(vol, (int, float)) and vol > 0:
            total += int(vol)
    return total


FAST_DEALS = 14         # two deals a day and more: such a set finds a buyer quickly
SLOW_DEALS = 3          # fewer than three a week: it may wait for its buyer for days


def sale_speed(deals: Optional[int]) -> str:
    """"fast" | "normal" | "slow" by the deals closed over the last week; unknown counts as slow."""
    if deals is None or deals < SLOW_DEALS:
        return "slow"
    return "fast" if deals >= FAST_DEALS else "normal"


def plan_sales(items: List[Dict[str, Any]], target: float) -> Dict[str, Any]:
    """Which sets to sell to get at least `target` platinum.

    items: [{"platinum": the price of one copy, "copies": how many can be sold,
             "deals": deals closed over the last week or None}, ...]
    Returns {"picks": [{"index": item number, "count": copies to sell}], "platinum", "reached"}.

    What is bought often goes first, the dearer before the cheaper: a sale that happens today is worth
    more than a better price that waits for a week.  Then whatever turned out not to be needed is taken
    back, starting from the slowest and cheapest, so the list is no longer than the target asks for.
    """
    rank = {"fast": 2, "normal": 1, "slow": 0}
    units: List[tuple] = []                      # one entry per copy: (speed, price, item)
    for index, it in enumerate(items):
        try:
            price, copies = float(it["platinum"]), int(it.get("copies") or 1)
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0 or copies <= 0:
            continue
        speed = rank[sale_speed(it.get("deals"))]
        units.extend((speed, price, index) for _ in range(min(copies, 99)))

    def answer(chosen: List[tuple]) -> Dict[str, Any]:
        counts: Dict[int, int] = {}
        for _speed, _price, index in chosen:
            counts[index] = counts.get(index, 0) + 1
        total = sum(u[1] for u in chosen)
        return {"picks": [{"index": i, "count": n} for i, n in sorted(counts.items())],
                "platinum": int(total) if float(total).is_integer() else round(total, 2),
                "reached": total >= target}

    if target <= 0 or not units:
        return {"picks": [], "platinum": 0, "reached": target <= 0}
    units.sort(key=lambda u: (-u[0], -u[1], u[2]))
    chosen, total = [], 0.0
    for u in units:
        if total >= target:
            break
        chosen.append(u)
        total += u[1]
    for u in sorted(chosen, key=lambda u: (u[0], u[1], -u[2])):      # the least wanted first
        if total - u[1] >= target:
            chosen.remove(u)
            total -= u[1]
    return answer(chosen)


def spare_parts(catalog: Dict[str, Any], items: Dict[str, int]) -> List[Dict[str, Any]]:
    """Parts that make up no full set: what is left over after the complete copies, and the parts of
    sets that are not complete yet.  `near` marks the parts of a set that lacks a single part to
    the next full copy -- those are better kept until it is found."""
    out = []
    for slug, st in catalog["sets"].items():
        prog = set_progress(st, items)
        if not prog["spare"]:
            continue
        lacking = sum(m["count"] for m in prog["missing"])
        for spare in prog["spare"]:
            out.append({"slug": spare["slug"], "set": slug, "count": spare["count"], "near": lacking == 1})
    return out


# --------------------------------------------------------------------------- price
def price_from_orders(top: Dict[str, Any]) -> Dict[str, Any]:
    """Price = the cheapest sell order among players who are in the game right now.

    If nobody in the game sells the item, the cheapest order of a player who is
    online on the site is used instead and the basis says so.
    """
    def clean(orders):
        out = []
        for o in orders or []:
            p = o.get("platinum")
            if isinstance(p, (int, float)) and p > 0:
                out.append(o)
        return out

    sells = clean(top.get("sell"))
    buys = clean(top.get("buy"))
    ingame = [o for o in sells if o.get("status") == "ingame"]
    pool = ingame or sells
    result: Dict[str, Any] = {
        "value": None,
        "basis": None,              # ingame | online | None
        "sell_prices": sorted(o["platinum"] for o in sells),
        "sell_ingame": len(ingame),
        "sell_listed": len(sells),
        "buy_max": max((o["platinum"] for o in buys), default=None),
    }
    if pool:
        result["value"] = min(o["platinum"] for o in pool)
        result["basis"] = "ingame" if ingame else "online"
    return result


# --------------------------------------------------------------------------- trend
def _parse_day(s: str) -> Optional[date]:
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _window_price(points: List[dict]) -> Optional[float]:
    """Volume-weighted mean of daily medians."""
    total_v = sum(p["volume"] for p in points)
    if not points or total_v <= 0:
        return None
    return sum(p["price"] * p["volume"] for p in points) / total_v


def trend_from_days(days: List[Dict[str, Any]], window: int = config.TREND_WINDOW_DAYS,
                    threshold: float = config.TREND_THRESHOLD) -> Dict[str, Any]:
    """Compare the start and the end of the (up to) 90-day history of closed deals.

    For both ends the price is the volume-weighted average of daily median prices
    over `window` days.  If either end has fewer than 3 trading days the windows
    grow up to 30 days; with too little data the trend is reported as unknown.
    """
    points = []
    for row in days or []:
        d = _parse_day(row.get("date", ""))
        price = row.get("median")
        if price is None:
            price = row.get("wavg") if row.get("wavg") is not None else row.get("avg")
        vol = row.get("volume") or 0
        if d is None or not isinstance(price, (int, float)) or price <= 0 or vol <= 0:
            continue
        points.append({"date": d, "price": float(price), "volume": int(vol)})
    points.sort(key=lambda p: p["date"])

    series = [[p["date"].isoformat(), round(p["price"], 1), p["volume"]] for p in points]
    out: Dict[str, Any] = {
        "direction": "unknown",       # up | down | flat | unknown
        "change": None,               # fraction: -0.27 = minus 27 %
        "start_price": None,
        "end_price": None,
        "window_days": None,
        "period_days": 0,
        "from": None,
        "to": None,
        "trading_days": len(points),
        "volume": sum(p["volume"] for p in points),
        "recent_price": None,         # last 7 days of deals, for reference next to the live price
        "series": series,
        "reason": "",
    }
    if not points:
        out["reason"] = tr("нет сделок за 90 дней")
        return out

    first, last = points[0]["date"], points[-1]["date"]
    out["from"], out["to"] = first.isoformat(), last.isoformat()
    out["period_days"] = (last - first).days + 1
    week = [p for p in points if p["date"] > last - timedelta(days=7)]
    recent = _window_price(week)
    out["recent_price"] = round(recent, 1) if recent else None

    if out["period_days"] < 21 or len(points) < 6:
        out["reason"] = tr("слишком мало сделок, чтобы судить о тренде")
        return out

    for win in (window, 21, 30):
        win = min(win, out["period_days"] // 2)
        head = [p for p in points if p["date"] < first + timedelta(days=win)]
        tail = [p for p in points if p["date"] > last - timedelta(days=win)]
        if len(head) >= 3 and len(tail) >= 3:
            start, end = _window_price(head), _window_price(tail)
            if start and end:
                change = (end - start) / start
                out.update({
                    "start_price": round(start, 1),
                    "end_price": round(end, 1),
                    "window_days": win,
                    "change": round(change, 4),
                    "direction": "up" if change >= threshold else "down" if change <= -threshold else "flat",
                })
                return out
    out["reason"] = tr("слишком мало сделок, чтобы судить о тренде")
    return out


def market_summary(top: Dict[str, Any], stats: Dict[str, Any]) -> Dict[str, Any]:
    return {"price": price_from_orders(top), "trend": trend_from_days(stats.get("days") or [])}


# --------------------------------------------------------------------------- riven mods
def _plat(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def riven_floor(offers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The bottom of the market for the riven mods of one weapon, out of the offers at a fixed price.

    floor      -- the lowest price among all the offers.  Most sellers of riven mods are offline:
                  such an offer stands, but the deal has to wait for the seller;
    floor_live -- the lowest among the sellers who are in the game or on the site right now.
    """
    prices = sorted(o["platinum"] for o in offers if _plat(o.get("platinum")))
    live = sorted(o["platinum"] for o in offers if _plat(o.get("platinum")) and o.get("status") in ("ingame", "online"))
    return {"floor": prices[0] if prices else None, "floor_live": live[0] if live else None,
            "offers": len(prices), "live": len(live), "cheapest": prices[:5]}


# --------------------------------------------------------------------------- relics
REFINEMENTS = ("intact", "exceptional", "flawless", "radiant")
RELIC_TIERS = ("common", "uncommon", "rare")
# the chance of ONE reward of a tier, per cent: a relic holds three common rewards, two uncommon and one rare
RELIC_CHANCES = {
    "intact": (25.33, 11.0, 2.0),
    "exceptional": (23.33, 13.0, 4.0),
    "flawless": (20.0, 17.0, 6.0),
    "radiant": (16.67, 20.0, 10.0),
}
# void traces it takes to bring a relic of this refinement to radiant
RELIC_TRACES = {"intact": 100, "exceptional": 75, "flawless": 50, "radiant": 0}
# A relic that no longer drops cannot be replaced, so every copy of it should be opened at its best:
# among relics that gain the same from refinement the scarce one comes first.
RELIC_STATUS_WEIGHT = {"missions": 1.0, "special": 1.15, "vaulted": 1.3, "unknown": 1.0}
_STANDARD_RELIC = sorted(["common"] * 3 + ["uncommon"] * 2 + ["rare"])


def relic_tier(chance: Any) -> str:
    """The tier of a reward by its chance in an intact relic (25.33, 11 or 2 per cent); "" when unknown."""
    if not isinstance(chance, (int, float)) or isinstance(chance, bool):
        return ""
    return "common" if chance >= 20 else "uncommon" if chance >= 5 else "rare"


def relic_value(rewards: List[Dict[str, Any]], refinement: str) -> Optional[float]:
    """What one opening of a relic brings on average, in platinum: the price of every reward by its
    chance at this refinement.  A reward that is not traded (Forma) or has no price counts as nothing.

    rewards: [{"tier": common|uncommon|rare, "price": platinum or None}, ...] -- six of them;
    None for a relic that is not built the usual way (the chances above do not hold for it).
    """
    if refinement not in RELIC_CHANCES or sorted(r.get("tier") for r in rewards) != _STANDARD_RELIC:
        return None
    chance = dict(zip(RELIC_TIERS, RELIC_CHANCES[refinement]))
    return sum(chance[r["tier"]] / 100.0 * float(r.get("price") or 0) for r in rewards)


def relic_gain(rewards: List[Dict[str, Any]], refinement: str, status: str = "unknown") -> Optional[Dict[str, Any]]:
    """What refining a relic to radiant gives.

    now, radiant -- platinum of one opening as it is and once radiant;
    gain         -- the difference: what the refinement adds to every opening;
    traces       -- void traces the refinement costs;
    per_100      -- the gain for 100 traces (a relic that is half refined costs less and gains less);
    score        -- per_100 with the relic's own scarcity weighed in: what the relics are ranked by.
    """
    now, top = relic_value(rewards, refinement), relic_value(rewards, "radiant")
    if now is None or top is None:
        return None
    traces = RELIC_TRACES[refinement]
    gain = top - now
    per_100 = gain * 100.0 / traces if traces else 0.0
    return {"now": now, "radiant": top, "gain": gain, "traces": traces, "per_100": per_100,
            "score": per_100 * RELIC_STATUS_WEIGHT.get(status, 1.0)}
