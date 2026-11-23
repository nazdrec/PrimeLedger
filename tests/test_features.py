"""Offline tests of what version 1.1 added: the journal of sales, selling help, spare parts, the
example inventory, the notice of a newer version, the tiles of a screenshot and the live check of
the shooting -- and of what 1.1.1 added: the sellers of a missing part and "Купил".  No network, no
real inventory.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import test_core  # noqa: F401  (first: it points the app at throw-away folders)
from test_core import ROW, VIEW, draw_foundry, draw_list, draw_screen, make_catalog

from primesets import (analysis, continuity, demo, history, inventory, live, mastery, recognize, sales, server,  # noqa: E402
                       settings, shots, updates)
from primesets.cache import DiskCache  # noqa: E402
from primesets.wfm import FetchError  # noqa: E402

FULL_AKSTILETTO = {"akstiletto_prime_blueprint": 1, "akstiletto_prime_barrel": 2, "akstiletto_prime_receiver": 2,
                   "akstiletto_prime_link": 1}


def clean_data():
    """An empty data folder: no inventory, no history, no sales."""
    import shutil
    demo.switch(False)
    for f in (inventory.config.INVENTORY_FILE, history.HISTORY_FILE, history.VALUES_FILE, sales.SALES_FILE,
              mastery.MASTERY_FILE, shots.STATE_FILE, settings.SETTINGS_FILE):
        if f.exists():
            f.unlink()
    settings._cache.update({"mtime": None, "data": None})
    shutil.rmtree(inventory.config.BACKUP_DIR, ignore_errors=True)


def put(items):
    inventory.save({**inventory.empty(), "items": dict(items)}, source="screenshots", backup=False)


def order(user, platinum, status="ingame", quantity=1):
    return {"user": user, "platinum": platinum, "status": status, "quantity": quantity, "reputation": 5}


class FakeMarket:
    """What the app remembers of the market, without any request."""

    def __init__(self, orders=None, stats=None):
        self.orders, self.stats = orders or {}, stats or {}

    def top_orders_cached(self, slug):
        return (self.orders[slug], 1700000000.0) if slug in self.orders else None

    def statistics_cached(self, slug):
        return ({"days": self.stats[slug]}, 1700000000.0) if slug in self.stats else None


def week(volume):
    """Statistics with `volume` deals on each of the last three days."""
    today = date.today()
    return [{"date": (today - timedelta(days=n)).isoformat(), "volume": volume, "median": 10} for n in (1, 2, 3)]


# --------------------------------------------------------------------------- a newer version
class NewerVersion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = DiskCache(Path(self.tmp.name))
        self.asked = []

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self, tag):
        def get(url, headers=None, timeout=30.0):
            self.asked.append(url)
            if tag is None:
                raise FetchError("no network")
            return json.dumps({"tag_name": tag, "body": "ignored"}).encode()
        return get

    def test_versions_are_compared_as_numbers(self):
        self.assertTrue(updates.newer("v1.10.0", "1.9.3"))
        self.assertTrue(updates.newer("1.1", "1.0.1"))
        self.assertFalse(updates.newer("1.0.1", "1.0.1"))
        self.assertFalse(updates.newer("v1.0", "1.0.0"))
        self.assertFalse(updates.newer("1.0.0", "1.0.1"))
        for junk in ("", None, "latest", "1.0.1-beta", "v", "1..2"):
            self.assertFalse(updates.newer(junk, "1.0.0"), junk)

    def test_the_question_goes_to_the_page_of_the_project_and_nowhere_else(self):
        self.assertEqual(updates.api_url("https://github.com/someone/PrimeLedger"),
                         "https://api.github.com/repos/someone/PrimeLedger/releases/latest")
        self.assertEqual(updates.page_url("https://github.com/someone/PrimeLedger"),
                         "https://github.com/someone/PrimeLedger/releases/latest")
        for other in ("", "http://github.com/a/b", "https://example.com/a/b", "https://github.com/a", "https://github.com/a/b/c"):
            self.assertIsNone(updates.api_url(other), other)

    def test_a_newer_release_is_reported_and_asked_about_once(self):
        got = updates.check(self.cache, fetch=self.fetch("v9.9.9"), current="1.0.1")
        self.assertEqual((got["state"], got["latest"], got["current"]), ("newer", "9.9.9", "1.0.1"))
        self.assertTrue(got["url"].endswith("/releases/latest"))
        again = updates.check(self.cache, fetch=self.fetch(None), current="1.0.1")      # remembered: no second question
        self.assertEqual((again["state"], again["latest"]), ("newer", "9.9.9"))
        self.assertEqual(len(self.asked), 1)

    def test_the_same_version_and_a_silent_network_say_nothing(self):
        self.assertEqual(updates.check(self.cache, fetch=self.fetch("v1.0.1"), current="1.0.1")["state"], "current")
        self.assertEqual(updates.check(self.cache, force=True, fetch=self.fetch(None), current="1.0.1")["state"], "unknown")
        self.assertEqual(updates.check(self.cache, force=True, fetch=self.fetch("nightly"), current="1.0.1")["state"], "unknown")

    def test_the_question_can_be_switched_off(self):
        clean_data()
        self.assertTrue(settings.check_updates())
        settings.save({"check_updates": False})
        self.assertFalse(settings.check_updates())
        state = SimpleNamespace(update={"state": "newer"}, cache=self.cache)
        server.AppState.check_update(state)
        self.assertEqual(state.update, {"state": "off"})
        clean_data()


# --------------------------------------------------------------------------- the journal of sales
class Sales(unittest.TestCase):
    def setUp(self):
        clean_data()
        self.cat = make_catalog()
        put({**FULL_AKSTILETTO, "akstiletto_prime_barrel": 5, "vasto_prime_barrel": 1})

    def tearDown(self):
        clean_data()

    def test_a_sale_takes_the_parts_of_the_set_and_is_written_down(self):
        rec = sales.add(self.cat, "akstiletto_prime_set", 40)
        self.assertEqual((rec["platinum"], rec["count"], rec["name_en"]), (40, 1, "Akstiletto Prime Set"))
        self.assertEqual(inventory.load()["items"], {"akstiletto_prime_barrel": 3, "vasto_prime_barrel": 1})
        box = sales.payload(self.cat)
        self.assertEqual([(s["title"], s["sum"]) for s in box["sales"]], [("Акстилетто Прайм", 40)])
        self.assertEqual((box["totals"]["platinum"], box["totals"]["month"], box["totals"]["sales"]), (40, 40, 1))
        self.assertEqual(inventory.load()["source"], "screenshots+manual")

    def test_a_sale_of_what_is_not_there_changes_nothing(self):
        for slug, count in (("akstiletto_prime_set", 2), ("vasto_prime_set", 1)):
            with self.assertRaises(ValueError):
                sales.add(self.cat, slug, 10, count)
        for bad in ({"slug": "no_such_set", "platinum": 5}, {"slug": "akstiletto_prime_set", "platinum": -1},
                    {"slug": "akstiletto_prime_set", "platinum": "many"}, {"slug": "akstiletto_prime_set", "platinum": 5, "count": 0}):
            with self.assertRaises(ValueError):
                sales.add(self.cat, **bad)
        self.assertEqual(inventory.load()["items"]["akstiletto_prime_barrel"], 5)
        self.assertEqual(sales.load(), [])

    def test_a_sale_entered_by_mistake_is_taken_back(self):
        rec = sales.add(self.cat, "akstiletto_prime_set", 40)
        sales.undo(self.cat, rec["id"])
        self.assertEqual(inventory.load()["items"]["akstiletto_prime_barrel"], 5)
        self.assertEqual(inventory.load()["items"]["akstiletto_prime_link"], 1)
        self.assertEqual(sales.load(), [])
        with self.assertRaises(ValueError):
            sales.undo(self.cat, rec["id"])

    def test_sales_of_one_sitting_are_one_line_of_the_history(self):
        put({**FULL_AKSTILETTO, "vasto_prime_blueprint": 1, "vasto_prime_barrel": 1, "vasto_prime_receiver": 1})
        history.sync(inventory.load())
        sales.add(self.cat, "akstiletto_prime_set", 40)
        sales.add(self.cat, "vasto_prime_set", 15)
        new = history.updates(self.cat, inventory.load())[0]
        self.assertEqual(new["source"], "sale")
        self.assertIn("Акстилетто Прайм", new["note"])
        self.assertIn("Васто Прайм", new["note"])
        self.assertEqual(sorted(x["title"] for x in new["sets_down"]), ["Акстилетто Прайм", "Васто Прайм"])
        self.assertEqual(len(history.updates(self.cat, inventory.load())), 2)

    def test_the_last_thirty_days_are_counted_apart(self):
        now = datetime(2026, 11, 21, 12, 0).astimezone()
        old = (now - timedelta(days=45)).isoformat()
        records = [{"id": "a", "at": old, "platinum": 100, "count": 1, "parts": {}},
                   {"id": "b", "at": now.isoformat(), "platinum": 20, "count": 3, "parts": {}}]
        self.assertEqual(sales.totals(records, now), {"platinum": 160, "month": 60, "sales": 2, "sets": 4})


# --------------------------------------------------------------------------- who buys now, and what to sell
class Selling(unittest.TestCase):
    def setUp(self):
        clean_data()
        self.cat = make_catalog()
        put({**FULL_AKSTILETTO, "vasto_prime_blueprint": 2, "vasto_prime_barrel": 2, "vasto_prime_receiver": 2,
             "akvasto_prime_blueprint": 1, "akvasto_prime_link": 1})

    def tearDown(self):
        clean_data()

    def state(self, orders=None, stats=None):
        return SimpleNamespace(catalog=self.cat, wfm=FakeMarket(orders, stats))

    def test_only_buyers_who_are_in_the_game_count_the_most_generous_first(self):
        top = {"buy": [order("Low", 20), order("Away", 90, "online"), order("High", 35, quantity=2), order("", 99),
                       order("Free", 0)], "sell": []}
        self.assertEqual([(b["user"], b["platinum"], b["quantity"]) for b in analysis.buyers_from_orders(top)],
                         [("High", 35, 2), ("Low", 20, 1)])
        self.assertEqual(analysis.buyers_from_orders({}), [])

    def test_the_message_for_a_buyer_is_the_line_of_the_site_with_the_name_of_the_application(self):
        self.assertEqual(server.whisper("Dana", "Vasto Prime Set", 30, deal="sell"),
                         '/w Dana Hi! I want to sell: "Vasto Prime Set" for 30 platinum. (warframe.market) (via PrimeLedger)')

    def test_the_list_of_buyers_is_built_from_what_is_already_known(self):
        state = self.state({
            "akstiletto_prime_set": {"sell": [order("S", 50)], "buy": [order("B1", 44), order("B2", 40, "online")]},
            "vasto_prime_set": {"sell": [order("S", 30)], "buy": []},
            "mirage_prime_set": {"sell": [], "buy": [order("Stranger", 200)]}})     # not owned: of no interest
        got = server.sell_now(state)
        self.assertEqual((got["complete"], got["priced"]), (3, 2))
        self.assertEqual([(s["title"], s["sell_min"], s["copies"]) for s in got["sets"]], [("Акстилетто Прайм", 50, 1)])
        buyer = got["sets"][0]["buyers"][0]
        self.assertEqual((buyer["user"], buyer["platinum"]), ("B1", 44))
        self.assertEqual(buyer["message"],
                         '/w B1 Hi! I want to sell: "Akstiletto Prime Set" for 44 platinum. (warframe.market) (via PrimeLedger)')

    def test_deals_of_the_last_week_only(self):
        today = date(2026, 11, 21)
        days = [{"date": "2026-11-20", "volume": 4}, {"date": "2026-11-14", "volume": 3}, {"date": "2026-11-13", "volume": 50},
                {"date": "bad", "volume": 9}, {"date": "2026-11-19", "volume": None}]
        self.assertEqual(analysis.recent_deals(days, today), 7)
        self.assertEqual(analysis.recent_deals([], today), 0)
        self.assertEqual([analysis.sale_speed(n) for n in (None, 0, 2, 3, 13, 14, 500)],
                         ["slow", "slow", "slow", "normal", "normal", "fast", "fast"])

    def test_what_sells_fast_goes_first_and_nothing_extra_is_sold(self):
        items = [{"platinum": 60, "copies": 1, "deals": 30}, {"platinum": 30, "copies": 1, "deals": 20},
                 {"platinum": 50, "copies": 1, "deals": 5}, {"platinum": 300, "copies": 1, "deals": 0}]
        plan = analysis.plan_sales(items, 100)
        self.assertEqual((plan["picks"], plan["platinum"], plan["reached"]),
                         ([{"index": 0, "count": 1}, {"index": 2, "count": 1}], 110, True))
        # the slow dear one is taken only when the rest is not enough
        plan = analysis.plan_sales(items, 150)
        self.assertEqual(([p["index"] for p in plan["picks"]], plan["platinum"]), ([3], 300))
        plan = analysis.plan_sales(items, 140)
        self.assertEqual(([p["index"] for p in plan["picks"]], plan["platinum"]), ([0, 1, 2], 140))

    def test_copies_are_counted_and_an_unreachable_target_takes_everything(self):
        items = [{"platinum": 10, "copies": 3, "deals": 20}, {"platinum": 0, "copies": 5, "deals": 20}, {"platinum": 7}]
        plan = analysis.plan_sales(items, 25)
        self.assertEqual((plan["picks"], plan["platinum"], plan["reached"]), ([{"index": 0, "count": 3}], 30, True))
        plan = analysis.plan_sales(items, 500)
        self.assertEqual((plan["picks"], plan["platinum"], plan["reached"]),
                         ([{"index": 0, "count": 3}, {"index": 2, "count": 1}], 37, False))
        self.assertEqual(analysis.plan_sales([], 10), {"picks": [], "platinum": 0, "reached": False})
        self.assertEqual(analysis.plan_sales(items, 0), {"picks": [], "platinum": 0, "reached": True})

    def test_the_plan_leaves_out_what_is_not_mastered_and_what_has_no_price(self):
        mastery.set_state("akvasto_prime_set", "none", self.cat)
        state = self.state({"akstiletto_prime_set": {"sell": [order("S", 50)], "buy": [order("B", 45)]},
                            "akvasto_prime_set": {"sell": [order("S", 500)], "buy": []}},
                           {"akstiletto_prime_set": week(10)})
        plan = server.sales_plan(state, 40)
        self.assertEqual([(s["title"], s["count"], s["sum"], s["speed"], s["deals"]) for s in plan["steps"]],
                         [("Акстилетто Прайм", 1, 50, "fast", 30)])
        self.assertEqual(plan["steps"][0]["buyer"], {"user": "B", "platinum": 45})
        self.assertEqual((plan["reached"], plan["held"], plan["unpriced"]), (True, ["Аквасто Прайм"], ["Васто Прайм"]))
        # the user may decide otherwise, and may set a set aside
        plan = server.sales_plan(state, 600, keep_unmastered=False)
        self.assertEqual(sorted(s["title"] for s in plan["steps"]), ["Аквасто Прайм", "Акстилетто Прайм"])
        self.assertFalse(plan["reached"])
        plan = server.sales_plan(state, 40, exclude=["akstiletto_prime_set"])
        self.assertEqual((plan["steps"], plan["reached"]), ([], False))


# --------------------------------------------------------------------------- spare parts and the collection
class SpareParts(unittest.TestCase):
    def setUp(self):
        clean_data()
        self.cat = make_catalog()

    def tearDown(self):
        clean_data()

    def test_what_is_left_beyond_full_sets_is_spare(self):
        items = {**FULL_AKSTILETTO, "akstiletto_prime_barrel": 5, "vasto_prime_barrel": 2, "mirage_prime_blueprint": 1,
                 "mirage_prime_chassis_blueprint": 1, "mirage_prime_neuroptics_blueprint": 1}
        got = {(s["slug"], s["count"], s["near"]) for s in analysis.spare_parts(self.cat, items)}
        self.assertEqual(got, {("akstiletto_prime_barrel", 3, False), ("vasto_prime_barrel", 2, False),
                               ("mirage_prime_blueprint", 1, True), ("mirage_prime_chassis_blueprint", 1, True),
                               ("mirage_prime_neuroptics_blueprint", 1, True)})
        self.assertEqual(analysis.spare_parts(self.cat, FULL_AKSTILETTO), [])

    def test_spare_parts_come_with_ducats_and_the_remembered_price(self):
        put({**FULL_AKSTILETTO, "akstiletto_prime_barrel": 3, "vasto_prime_barrel": 2})
        state = SimpleNamespace(catalog=self.cat, wfm=FakeMarket({"vasto_prime_barrel": {"sell": [order("S", 4)], "buy": []}}))
        rows = {r["slug"]: r for r in server.baro(state)["parts"]}
        self.assertEqual(sorted(rows), ["akstiletto_prime_barrel", "vasto_prime_barrel"])
        self.assertEqual((rows["vasto_prime_barrel"]["count"], rows["vasto_prime_barrel"]["ducats"],
                          rows["vasto_prime_barrel"]["price"], rows["vasto_prime_barrel"]["asked"]), (2, 15, 4, True))
        self.assertEqual((rows["akstiletto_prime_barrel"]["count"], rows["akstiletto_prime_barrel"]["price"],
                          rows["akstiletto_prime_barrel"]["asked"]), (1, None, False))

    def test_prices_are_asked_for_the_spare_parts_only(self):
        put({**FULL_AKSTILETTO, "akstiletto_prime_barrel": 3})
        asked = []

        def top_orders(slug, force=False):
            asked.append(slug)
            return {"sell": [order("S", 6)], "buy": []}, {"fetched_at": 1.0, "stale": False}

        state = SimpleNamespace(catalog=self.cat, wfm=SimpleNamespace(top_orders=top_orders))
        got = server.parts_market(state, "akstiletto_prime_set", False, "spare")
        self.assertEqual(asked, ["akstiletto_prime_barrel"])
        self.assertEqual((got["parts"], got["total"]), ([{"slug": "akstiletto_prime_barrel", "units": 1, "price": 6, "basis": "ingame"}], 6))

    def test_the_collection_shows_every_set_of_the_catalog(self):
        put({**FULL_AKSTILETTO, "vasto_prime_barrel": 1})
        mastery.set_state("mirage_prime_set", "mastered", self.cat)
        for st in self.cat["sets"].values():
            st["vault"] = {"state": "vaulted", "vaulted_parts": len(st["parts"]), "total_parts": len(st["parts"])}
        rows = {r["slug"]: r for r in server.collection(SimpleNamespace(catalog=self.cat))["sets"]}
        self.assertEqual(len(rows), 5)
        self.assertEqual((rows["akstiletto_prime_set"]["complete"], rows["akstiletto_prime_set"]["have"],
                          rows["akstiletto_prime_set"]["need"]), (1, 6, 6))
        self.assertEqual((rows["vasto_prime_set"]["complete"], rows["vasto_prime_set"]["have"], rows["vasto_prime_set"]["need"]), (0, 1, 3))
        self.assertEqual(rows["mirage_prime_set"]["mastery"]["state"], "mastered")
        self.assertEqual(rows["kavasa_prime_kubrow_collar_set"]["mastery"]["state"], "na")


# --------------------------------------------------------------------------- who sells a missing part (version 1.1.1)
class SellersOfMissingParts(unittest.TestCase):
    def setUp(self):
        clean_data()
        self.cat = make_catalog()
        put({"akstiletto_prime_blueprint": 1, "akstiletto_prime_barrel": 2, "akstiletto_prime_link": 1})   # both receivers are missing

    def tearDown(self):
        clean_data()

    def state(self, orders):
        asked = []

        def top_orders(slug, force=False):
            asked.append((slug, force))
            if slug not in orders:
                raise FetchError("the market did not answer")
            return orders[slug], {"fetched_at": 1700000000.0 + len(asked), "stale": False}

        return SimpleNamespace(catalog=self.cat, wfm=SimpleNamespace(top_orders=top_orders)), asked

    def test_a_missing_part_comes_with_its_three_cheapest_sellers_who_are_in_the_game(self):
        state, asked = self.state({"akstiletto_prime_receiver": {
            "sell": [order("Dear", 30), order("Away", 5, "online"), order("Cheap", 12, quantity=3), order("Mid", 15),
                     order("Fourth", 20)],
            "buy": [order("Buyer", 99)]}})
        got = server.parts_market(state, "akstiletto_prime_set", False, "missing")
        self.assertEqual(asked, [("akstiletto_prime_receiver", False)])      # the one request the price needs anyway
        row, = got["parts"]
        self.assertEqual((row["slug"], row["units"], row["price"], row["basis"], row["orders_at"]),
                         ("akstiletto_prime_receiver", 2, 12, "ingame", 1700000001.0))
        self.assertEqual([(s["user"], s["platinum"], s["quantity"], s["count"]) for s in row["sellers"]],
                         [("Cheap", 12, 3, 2), ("Mid", 15, 1, 1), ("Fourth", 20, 1, 1)])
        # the line of the site word for word, then the name of the application; two are asked of the one who has them
        self.assertEqual([s["message"] for s in row["sellers"]], [
            '/w Cheap Hi! I want to buy: "Akstiletto Prime Receiver" for 12 platinum. (warframe.market) (x2, via PrimeLedger)',
            '/w Mid Hi! I want to buy: "Akstiletto Prime Receiver" for 15 platinum. (warframe.market) (via PrimeLedger)',
            '/w Fourth Hi! I want to buy: "Akstiletto Prime Receiver" for 20 platinum. (warframe.market) (via PrimeLedger)'])
        self.assertEqual((got["total"], got["oldest_at"], got["ttl_orders"]), (24, 1700000001.0, server.config.TTL_TOP_ORDERS))

    def test_a_seller_who_is_not_in_the_game_is_not_written_to(self):
        state, _ = self.state({"akstiletto_prime_receiver": {"sell": [order("Away", 9, "online"), order("Site", 7, "online")],
                                                             "buy": []}})
        row, = server.parts_market(state, "akstiletto_prime_set", False, "missing")["parts"]
        self.assertEqual((row["sellers"], row["price"], row["basis"]), ([], 7, "online"))

    def test_a_part_the_market_did_not_answer_about_has_no_sellers(self):
        state, asked = self.state({})
        got = server.parts_market(state, "akstiletto_prime_set", True, "missing")
        self.assertEqual(asked, [("akstiletto_prime_receiver", True)])
        row, = got["parts"]
        self.assertEqual((row["sellers"], row["orders_at"], row["price"]), ([], None, None))
        self.assertEqual((got["total"], got["oldest_at"], len(got["errors"])), (None, None, 1))

    def test_the_other_lists_of_parts_carry_no_sellers(self):
        state, asked = self.state({slug: {"sell": [order("S", 6)], "buy": []} for slug in FULL_AKSTILETTO})
        got = server.parts_market(state, "akstiletto_prime_set", False, "all")
        self.assertEqual(len(asked), 4)
        self.assertTrue(all(set(row) == {"slug", "units", "price", "basis"} for row in got["parts"]))
        self.assertEqual(got["oldest_at"], 1700000001.0)

    def test_the_scope_of_a_request_for_parts(self):
        self.assertEqual([server.part_scope(v) for v in ("missing", "spare", "all", "", "anything")],
                         ["missing", "spare", "all", "all", "all"])


# --------------------------------------------------------------------------- "Купил": a part the user bought (version 1.1.1)
class BoughtParts(unittest.TestCase):
    def setUp(self):
        clean_data()
        self.cat = make_catalog()
        put({"akstiletto_prime_blueprint": 1, "akstiletto_prime_barrel": 2, "akstiletto_prime_link": 1, "vasto_prime_barrel": 1})
        history.sync(inventory.load())
        self.state = SimpleNamespace(catalog=self.cat)

    def tearDown(self):
        clean_data()

    def test_a_bought_part_goes_into_the_inventory_and_into_the_history(self):
        server.bought(self.state, "akstiletto_prime_receiver", 2, 12, "  Cheap \n")
        self.assertEqual(inventory.load()["items"]["akstiletto_prime_receiver"], 2)
        self.assertEqual(inventory.load()["source"], "screenshots+manual")
        new = history.updates(self.cat, inventory.load())[0]
        self.assertEqual((new["source"], new["note"]), ("purchase", "Акстилетто Прайм: Приёмник ×2 за 24 пл (Cheap)"))
        self.assertEqual([x["title"] for x in new["sets_up"]], ["Акстилетто Прайм"])

    def test_a_purchase_entered_by_mistake_is_taken_back_and_leaves_no_trace(self):
        before = dict(inventory.load()["items"])
        server.bought(self.state, "akstiletto_prime_receiver", 1, 12, "Cheap")
        self.assertEqual(len(history.updates(self.cat, inventory.load())), 2)
        server.bought(self.state, "akstiletto_prime_receiver", 1, undo=True)
        self.assertEqual(inventory.load()["items"], before)
        self.assertEqual(len(history.updates(self.cat, inventory.load())), 1)      # the purchase and its undoing cancel out

    def test_purchases_of_one_sitting_are_one_line_of_the_history(self):
        server.bought(self.state, "akstiletto_prime_receiver", 2, 12, "Cheap")
        server.bought(self.state, "vasto_prime_receiver", 1)                       # the price may be unknown
        updates = history.updates(self.cat, inventory.load())
        self.assertEqual(len(updates), 2)
        self.assertEqual((updates[0]["source"], updates[0]["note"]),
                         ("purchase", "Акстилетто Прайм: Приёмник ×2 за 24 пл (Cheap); Васто Прайм: Приёмник ×1"))

    def test_what_cannot_be_a_purchase_changes_nothing(self):
        before = dict(inventory.load()["items"])
        for bad in ({"slug": "no_such_part"}, {"slug": "akstiletto_prime_set"}, {"slug": "akstiletto_prime_receiver", "count": 0},
                    {"slug": "akstiletto_prime_receiver", "count": 100}, {"slug": "akstiletto_prime_receiver", "count": "two"},
                    {"slug": "akstiletto_prime_receiver", "count": 1, "undo": True}):      # there is nothing to take back
            with self.assertRaises(ValueError):
                server.bought(self.state, **bad)
        self.assertEqual(inventory.load()["items"], before)
        self.assertEqual(len(history.updates(self.cat, inventory.load())), 1)


# --------------------------------------------------------------------------- the example inventory
class Example(unittest.TestCase):
    def setUp(self):
        clean_data()
        self.cat = make_catalog()

    def tearDown(self):
        clean_data()

    def test_the_example_is_shown_without_touching_the_real_files(self):
        put({"vasto_prime_barrel": 4})
        before = inventory.config.INVENTORY_FILE.read_bytes()
        demo.switch(True)
        self.assertEqual(inventory.load()["items"], demo.ITEMS)
        self.assertEqual(inventory.load()["source"], "demo")
        self.assertEqual(mastery.load()["items"]["wukong_prime_set"]["state"], "none")
        for change in (lambda: inventory.set_count("vasto_prime_barrel", 9, self.cat),
                       lambda: sales.add(self.cat, "vasto_prime_set", 5),
                       lambda: server.bought(SimpleNamespace(catalog=self.cat), "vasto_prime_barrel", 1, 5, "Seller"),
                       lambda: mastery.set_state("vasto_prime_set", "mastered", self.cat),
                       lambda: inventory.import_entries([{"name": "Васто Прайм: Ствол", "count": 1}], self.cat)):
            with self.assertRaises(ValueError):
                change()
        self.assertEqual(inventory.config.INVENTORY_FILE.read_bytes(), before)
        self.assertFalse(history.HISTORY_FILE.exists())
        self.assertFalse(mastery.MASTERY_FILE.exists())
        demo.switch(False)
        self.assertEqual(inventory.load()["items"], {"vasto_prime_barrel": 4})

    def test_every_part_of_the_example_is_a_plain_market_name(self):
        for slug, count in demo.ITEMS.items():
            self.assertRegex(slug, r"^[a-z0-9_]+_prime_[a-z0-9_]+$")
            self.assertGreater(count, 0)
        self.assertTrue(all(slug.endswith("_prime_set") for slug in demo.MASTERY))


# --------------------------------------------------------------------------- the tiles of a screenshot
@unittest.skipUnless(shots.have_pillow(), "needs Pillow")
class Tiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.strip = draw_list(12)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def shot(self, offset, name):
        path = Path(self.tmp.name) / name
        draw_screen(self.strip, offset, glow=3).save(path)
        return path

    def test_the_tiles_are_found_where_they_were_drawn(self):
        found = continuity.grid(self.shot(0, "top.png"))
        self.assertEqual((len(found["cols"]), len(found["rows"])), (6, 4))
        for c, (x0, x1) in enumerate(found["cols"]):
            self.assertAlmostEqual(x0, 50 + c * 138.4, delta=9)
            self.assertAlmostEqual(x1 - x0, 126, delta=9)
        for r, (y0, y1) in enumerate(found["rows"][:3]):
            self.assertAlmostEqual(y0, VIEW[0] + r * ROW, delta=9)
            self.assertAlmostEqual(y1 - y0, 126, delta=9)
        self.assertLess(found["rows"][3][1] - found["rows"][3][0], 100)        # the fourth row is cut by the edge

    def test_a_list_scrolled_off_the_grid_still_gives_its_rows_from_the_top(self):
        found = continuity.grid(self.shot(ROW * 3 + 60, "middle.png"))
        self.assertEqual(len(found["cols"]), 6)
        tops = [y0 for y0, _ in found["rows"]]
        self.assertAlmostEqual(tops[0], VIEW[0], delta=9)                      # a row cut by the upper edge is row 1
        self.assertAlmostEqual(tops[1], VIEW[0] + ROW - 60, delta=9)

    def test_a_tile_is_cut_out_as_a_small_picture_and_only_inside_the_grid(self):
        from PIL import Image
        import io
        path = self.shot(0, "tile.png")
        box = continuity.tile_box(path, 2, 3)
        self.assertAlmostEqual(box[0], 50 + 2 * 138.4, delta=18)
        self.assertAlmostEqual(box[1], VIEW[0] + ROW, delta=18)
        data = continuity.tile_picture(path, 2, 3)
        self.assertEqual(Image.open(io.BytesIO(data)).format, "JPEG")
        for row, col in ((0, 1), (1, 0), (9, 1), (1, 7)):
            self.assertIsNone(continuity.tile_box(path, row, col))
        foundry = Path(self.tmp.name) / "foundry.png"
        draw_foundry().save(foundry)
        self.assertIsNone(continuity.grid(foundry))
        self.assertIsNone(continuity.tile_picture(foundry, 1, 1))

    def test_places_named_by_the_model_are_kept_only_when_they_make_sense_together(self):
        def shot(*places):
            return {"items": [{"name": f"n{i}", "row": r, "col": c} for i, (r, c) in enumerate(places)]}
        good = shot((1, 1), (1, 2), (2, 1), (None, None))
        self.assertTrue(recognize.check_places(good, 4, 6))
        self.assertEqual(good["items"][2]["row"], 2)
        for bad in (shot((1, 1), (1, 1)), shot((5, 1), (1, 2)), shot((1, 7)), shot((None, 2), (3, None))):
            self.assertFalse(recognize.check_places(bad, 4, 6))
            self.assertTrue(all(it["row"] is None and it["col"] is None for it in bad["items"]))

    def test_the_request_names_the_width_of_the_grid_when_it_is_known(self):
        plain = recognize.task("ru", "ru")
        with_grid = plain.with_grid(6)
        self.assertNotIn("6 плиток", plain.prompt_attached)
        self.assertIn("6 плиток", with_grid.prompt_attached)
        self.assertIn("6 плиток", with_grid.files_text([Path("a.png")]))
        self.assertIn("a.png", with_grid.files_text([Path("a.png")]))
        self.assertIn("holds 6 tiles", recognize.task("en", "en").with_grid(6).prompt_attached)
        for lang in ("ru", "en", "de"):
            body = recognize.task(lang, lang).prompt_attached
            self.assertIn("row, col", body)


class ReviewFixes(unittest.TestCase):
    """A line of the reading corrected by the user before it is accepted."""

    def setUp(self):
        clean_data()
        self.cat = make_catalog()
        self.job = recognize.Job([], self.cat)
        self.job.cleanup()
        self.job._enter_review({"parts": [
            {"name": "Васто Прайм: Ствол", "count": 2, "blueprint": False, "count_known": True, "shot": "a.png", "pos": [1, 2]},
            {"name": "Васто Прайм: Приёмнк", "count": 1, "blueprint": False, "count_known": True, "shot": "a.png", "pos": [1, 3]},
            {"name": "Зорька Прайм: Ствол", "count": 1, "blueprint": False, "count_known": True, "shot": "a.png"}],
            "mastery": [], "notes": [], "dropped_negative_marks": 0, "screens": ["inventory"]})

    def tearDown(self):
        recognize.forget_pending()
        clean_data()

    def report(self):
        return self.job.snapshot()["reports"]["merge"]

    def test_the_reading_carries_the_tile_and_the_number_of_each_line(self):
        rep = self.report()
        first = next(m for m in rep["matched"] if m["name"] == "Васто Прайм: Ствол")
        self.assertEqual((first["entry"], first["pos"]), (0, [1, 2]))
        lost = next(r for r in rep["review"] if r["kind"] == "unmatched")
        self.assertEqual((lost["entry"], lost["pos"], lost["shot"]), (2, None, "a.png"))

    def test_a_number_a_part_and_a_line_can_be_corrected(self):
        self.job.fix(0, count=7)
        self.job.fix(2, slug="akvasto_prime_link")
        rep = self.report()
        counts = {m["item"]: m["count"] for m in rep["matched"]}
        self.assertEqual(counts["Васто Прайм: Ствол"], 7)
        self.assertEqual(counts["Аквасто Прайм: Связь"], 1)
        self.assertFalse([r for r in rep["review"] if r["kind"] == "unmatched"])
        self.job.fix(1, skip=True)
        self.assertNotIn("Васто Прайм: Приёмник", {m["item"] for m in self.report()["matched"]})
        self.job.fix(1, slug="vasto_prime_receiver")                     # named after all: the line is back
        self.assertIn("Васто Прайм: Приёмник", {m["item"] for m in self.report()["matched"]})
        self.job.apply("merge")
        self.assertEqual(inventory.load()["items"], {"akvasto_prime_link": 1, "vasto_prime_barrel": 7, "vasto_prime_receiver": 1})

    def test_a_correction_must_point_at_a_real_line_and_a_real_part(self):
        for bad in ({"entry": 9, "count": 1}, {"entry": -1, "skip": True}, {"entry": 0, "slug": "no_such_part"}):
            with self.assertRaises(recognize.RecognizeError):
                self.job.fix(**bad)


# --------------------------------------------------------------------------- shooting with a second pair of eyes
@unittest.skipUnless(shots.have_pillow(), "the join check needs Pillow")
class LiveShooting(unittest.TestCase):
    def setUp(self):
        import shutil
        clean_data()
        continuity.forget()
        self.tmp = tempfile.TemporaryDirectory()
        self.game = Path(self.tmp.name) / "Warframe"
        self.game.mkdir()
        os.environ["PRIMESETS_GAME_SHOTS"] = str(self.game)
        shutil.rmtree(inventory.config.SCREENSHOT_DIR, ignore_errors=True)
        self.strip = draw_list(16)
        self.end = 16 * ROW - 21 - (VIEW[1] - VIEW[0])
        self.n = 0
        self.sounds, self.events = [], []
        self.live = live.Live(lambda event, data: self.events.append(event), self.sounds.append)
        self.live.start(thread=False)

    def tearDown(self):
        import shutil
        self.live.stop()
        del os.environ["PRIMESETS_GAME_SHOTS"]
        shutil.rmtree(inventory.config.SCREENSHOT_DIR, ignore_errors=True)
        self.tmp.cleanup()
        clean_data()

    def press_f6(self, offset=None, picture=None):
        """The game writes a screenshot; the app looks twice (a file is taken when its size has settled)."""
        self.n += 1
        path = self.game / f"Warframe{self.n:04d}.png"
        (picture or draw_screen(self.strip, offset, glow=self.n)).save(path)
        stamp = time.time() + self.n          # later than the start, and in the order of shooting
        os.utime(path, (stamp, stamp))
        self.assertIsNone(self.live.step())
        return self.live.step()

    def test_pages_that_join_are_taken_in_with_a_short_sound(self):
        self.assertEqual(self.press_f6(0), "ok")
        self.assertEqual(self.press_f6(ROW * 3), "ok")
        self.assertEqual((self.live.taken, self.sounds, self.live.gap), (2, ["ok", "ok"], None))
        self.assertEqual(len(shots.originals()), 2)
        self.assertIn("joins", self.events)
        self.assertEqual(shots.game_new()["files"], [])                  # taken once, not offered again

    def test_a_skipped_row_is_told_at_once_and_a_retake_closes_it(self):
        self.press_f6(0)
        self.assertEqual(self.press_f6(ROW * 4), "gap")                  # four rows instead of three
        self.assertEqual(self.sounds[-1], "gap")
        self.assertIsNotNone(self.live.gap)
        self.assertEqual(self.press_f6(ROW * 2), "ok")                   # one page back: both sides meet
        self.assertIsNone(self.live.gap)
        self.assertEqual(self.press_f6(ROW * 7), "ok")

    def test_the_end_of_the_list_has_a_sound_of_its_own(self):
        self.press_f6(self.end - ROW * 3)
        self.assertEqual(self.press_f6(self.end), "end")
        self.assertEqual(self.sounds, ["ok", "end"])

    def test_another_screen_is_taken_in_without_alarm_and_silence_can_be_asked_for(self):
        self.press_f6(0)
        self.assertEqual(self.press_f6(picture=draw_foundry()), "other")
        self.live.sound = False
        self.assertEqual(self.press_f6(ROW * 3), "ok")
        self.assertEqual(self.sounds, ["ok", "other"])
        self.assertEqual(self.live.state()["taken"], 3)

    def test_a_file_still_being_written_waits_and_nothing_happens_when_off(self):
        path = self.game / "Warframe0001.png"
        draw_screen(self.strip, 0).save(path)
        stamp = time.time() + 1
        os.utime(path, (stamp, stamp))
        self.assertIsNone(self.live.step())
        with open(path, "ab") as f:                                      # the game is still writing
            f.write(b"\0" * 10)
        os.utime(path, (stamp, stamp))
        self.assertIsNone(self.live.step())
        self.assertEqual(shots.originals(), [])
        self.live.stop()
        self.assertIsNone(self.live.step())
        self.assertEqual(shots.originals(), [])

    def test_what_was_shot_long_before_the_start_is_left_alone(self):
        self.live.stop()
        old = self.game / "Warframe0900.png"
        draw_screen(self.strip, 0).save(old)
        stamp = time.time() - 3600
        os.utime(old, (stamp, stamp))
        fresh = live.Live(lambda event, data: None, self.sounds.append)
        fresh.start(thread=False)
        self.assertIsNone(fresh.step())
        self.assertIsNone(fresh.step())
        self.assertEqual(shots.originals(), [])


if __name__ == "__main__":
    unittest.main()
