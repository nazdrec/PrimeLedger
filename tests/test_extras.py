"""Offline tests of what version 1.2 added: the riven mods with the bottom of their market and the
relics with what refining them gives.  No network, no real lists, no reader of screenshots.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import time
import unittest
from types import SimpleNamespace

import test_core  # noqa: F401  (first: it points the app at throw-away folders)

from primesets import analysis, config, demo, providers, relics, rivens, scans, server, shots  # noqa: E402
from primesets.providers import ProviderError  # noqa: E402
from primesets.wfm import FetchError  # noqa: E402


def clean_lists():
    """No riven mods, no relics, no screenshots waiting, the example off."""
    import shutil
    demo.switch(False)
    for f in (rivens.RIVENS_FILE, relics.RELICS_FILE):
        if f.exists():
            f.unlink()
    for kind in scans.KINDS:
        shutil.rmtree(scans.inbox(kind), ignore_errors=True)


# --------------------------------------------------------------------------- made-up market data
def weapon(slug, ru, en, group="primary"):
    return {"slug": slug, "name": ru, "en": en, "group": group, "riven_type": "rifle", "thumb": ""}


WEAPONS = [weapon("soma", "Сома", "Soma"), weapon("reaper_prime", "Жнец Прайм", "Reaper Prime", "melee"),
           weapon("kamas", "Камы", "Kamas", "melee"), weapon("dual_kamas", "Парные Камы", "Dual Kamas", "melee"),
           weapon("bubonico", "Бубонико", "Bubonico"), weapon("pangolin_sword", "Меч Панголин", "Pangolin Sword", "melee"),
           weapon("plague_kripath", "Чумной Крипат", "Plague Kripath", "zaw")]


def relic_item(key, ru, vaulted=True):
    return {"slug": key.lower().replace(" ", "_") + "_relic", "en": f"{key} Relic", "name": ru, "tags": ["relic"],
            "vaulted": vaulted, "thumb": ""}


def part_item(en, ru):
    return {"slug": en.lower().replace(" ", "_"), "en": en, "name": ru, "tags": ["prime"], "thumb": ""}


def rewards(rare, uncommon, common):
    return ([{"item": rare, "rarity": "Rare", "chance": 2.0}]
            + [{"item": i, "rarity": "Uncommon", "chance": 11.0} for i in uncommon]
            + [{"item": i, "rarity": "Uncommon", "chance": 25.33} for i in common])


ITEMS = [relic_item("Lith A13", "Реликвия Лит A13", False), relic_item("Lith C11", "Реликвия Лит C11"),
         relic_item("Meso K9", "Реликвия Мезо K9", False), relic_item("Meso P8", "Реликвия Мезо P8"),
         relic_item("Neo N21", "Реликвия Нео N21"), relic_item("Axi A22", "Реликвия Акси A22", False),
         relic_item("Requiem IV", "Реликвия Реквием IV"), relic_item("Requiem Eterna", "Реликвия Реквием Этерна"),
         part_item("Gold Part", "Золотая часть"), part_item("Silver One", "Серебряная раз"), part_item("Silver Two", "Серебряная два"),
         part_item("Bronze One", "Бронзовая раз"), part_item("Bronze Two", "Бронзовая два"), part_item("Bronze Three", "Бронзовая три"),
         part_item("Dear Part", "Дорогая часть")]
USUAL = rewards("Gold Part", ["Silver One", "Silver Two"], ["Bronze One", "Bronze Two", "Bronze Three"])
DROPS = {
    "relics": {
        "Lith A13": USUAL,
        "Lith C11": rewards("Dear Part", ["Silver One", "2X Forma Blueprint"], ["Bronze One", "Bronze Two", "Forma Blueprint"]),
        "Meso K9": USUAL, "Neo N21": USUAL, "Axi A22": USUAL,
        "Requiem Iv": USUAL,                                   # as the drop tables write it
        "Requiem Eterna": [{"item": "Bronze One", "rarity": "Uncommon", "chance": 9.5}] * 8,
    },
    "active": ["Lith A13", "Meso K9"],
}
PRICES = {"gold_part": 100, "silver_one": 20, "silver_two": 10, "bronze_one": 5, "bronze_two": 3, "bronze_three": 2, "dear_part": 300}


def order(platinum, status="ingame"):
    return {"platinum": platinum, "status": status, "quantity": 1, "user": "S", "reputation": 1}


class FakeMarket:
    """What the app remembers of the market, and a count of what it was asked for."""

    def __init__(self, prices=None, offers=None, age=60.0):
        self.prices, self.offers, self.age = dict(prices or {}), dict(offers or {}), age
        self.asked = []

    def top_orders_cached(self, slug):
        return ({"sell": [order(self.prices[slug])], "buy": []}, time.time() - self.age) if slug in self.prices else None

    def top_orders(self, slug, force=False):
        self.asked.append(slug)
        if slug == "silver_two":
            raise FetchError("the market did not answer")
        self.prices.setdefault(slug, 7)
        self.age = 0.0
        return {"sell": [order(self.prices[slug])], "buy": []}, {"fetched_at": time.time(), "stale": False}

    def riven_offers_cached(self, slug):
        return (self.offers[slug], time.time() - self.age) if slug in self.offers else None

    def riven_offers(self, slug, force=False):
        self.asked.append(slug)
        if slug == "kamas":
            raise FetchError("the market did not answer")
        self.offers[slug] = {"offers": [{"platinum": 15, "status": "offline"}], "listed": 1}
        return self.offers[slug], {"fetched_at": time.time(), "stale": False}


# --------------------------------------------------------------------------- riven mods
class RivenCaptions(unittest.TestCase):
    def setUp(self):
        self.weapons = rivens.Weapons(WEAPONS)

    def test_the_name_of_a_mod_comes_back_whole(self):
        self.assertEqual(rivens.tidy("Crita- ignitox"), "Crita-ignitox")          # broken over two lines after the hyphen
        self.assertEqual(rivens.tidy("  Hexa -\nлациум "), "Hexa-лациум")
        self.assertEqual(rivens.tidy("Acri parasus"), "Acri-parasus")             # the edge of the card hid the hyphen
        self.assertEqual(rivens.tidy("Crita-igni tox"), "Crita-ignitox")
        self.assertEqual(rivens.tidy("Mantican"), "Mantican")
        self.assertEqual(rivens.tidy(""), "")

    def test_the_weapon_is_found_by_its_name_in_any_language(self):
        self.assertEqual(self.weapons.split("Сома Satidra"), ("soma", "Satidra", "ok"))
        self.assertEqual(self.weapons.split("Soma Satidra"), ("soma", "Satidra", "ok"))
        self.assertEqual(self.weapons.split("Жнец Прайм Crita-ignitox"), ("reaper_prime", "Crita-ignitox", "ok"))
        self.assertEqual(self.weapons.split("Меч Панголин Hexa- лациум"), ("pangolin_sword", "Hexa-лациум", "ok"))
        self.assertEqual(self.weapons.split("Чумной Крипат Acri parasus"), ("plague_kripath", "Acri-parasus", "ok"))

    def test_the_longest_name_wins(self):
        self.assertEqual(self.weapons.split("Парные Камы Visi-critatis")[0], "dual_kamas")
        self.assertEqual(self.weapons.split("Камы Visi-critatis")[0], "kamas")

    def test_a_slip_in_the_name_is_that_weapon_still_and_is_marked(self):
        self.assertEqual(self.weapons.split("Бубоника Toxican"), ("bubonico", "Toxican", "fuzzy"))

    def test_what_names_no_weapon_is_left_out(self):
        for caption in ("Завуалированный мод Разлома", "Зазубренные Лезвия", "Сома", ""):
            self.assertEqual(self.weapons.split(caption)[::2], (None, "unmatched"), caption)

    def test_names_of_the_game_language_are_known_too(self):
        both = rivens.Weapons([weapon("soma", "Soma", "Soma")], [weapon("soma", "Сома", "Soma")])
        self.assertEqual(both.split("Сома Satidra")[0], "soma")
        self.assertEqual(both.by_slug["soma"]["name"], "Soma")                    # shown in the language of the interface

    def test_one_mod_seen_on_two_screenshots_is_one_mod(self):
        rev = rivens.review([{"name": "Сома Satidra", "shot": "a.png"}, {"name": "Сома  Satidra", "shot": "b.png"},
                             {"name": "Сома Mantican", "shot": "b.png"}, {"name": "Нечто Странное", "shot": "b.png"},
                             {"name": "Нечто Странное", "shot": "c.png"}], self.weapons)
        self.assertEqual([(e["weapon"], e["name"], e["status"]) for e in rev["entries"]],
                         [("soma", "Satidra", "ok"), ("soma", "Mantican", "ok"), (None, "", "unmatched")])
        self.assertEqual((rev["matched"], rev["unmatched"], rev["entries"][0]["title"]), (2, 1, "Сома"))


class RivenList(unittest.TestCase):
    def setUp(self):
        clean_lists()

    def tearDown(self):
        clean_lists()

    def test_the_whole_list_or_an_addition(self):
        rivens.store([{"weapon": "soma", "name": "Satidra"}, {"weapon": "soma", "name": "satidra"}, {"weapon": "kamas", "name": "Visi"}],
                     ["Нечто Странное"])
        self.assertEqual(rivens.load()["items"], [{"weapon": "soma", "name": "Satidra"}, {"weapon": "kamas", "name": "Visi"}])
        rivens.store([{"weapon": "soma", "name": "Mantican"}, {"weapon": "kamas", "name": "Visi"}], ["Ещё"], mode="merge")
        self.assertEqual([it["name"] for it in rivens.load()["items"]], ["Satidra", "Visi", "Mantican"])
        self.assertEqual(rivens.load()["unknown"], ["Нечто Странное", "Ещё"])
        rivens.store([{"weapon": "soma", "name": "Mantican"}])
        self.assertEqual((rivens.load()["items"], rivens.load()["unknown"]), ([{"weapon": "soma", "name": "Mantican"}], []))

    def test_what_is_not_a_mod_is_not_kept(self):
        rivens.store([{"weapon": "", "name": "X"}, {"weapon": "../soma", "name": "X"}, {"weapon": "soma", "name": ""}, "junk",
                      {"weapon": "soma", "name": "Good"}])
        self.assertEqual(rivens.load()["items"], [{"weapon": "soma", "name": "Good"}])

    def test_a_mod_that_is_gone_is_taken_off(self):
        rivens.store([{"weapon": "soma", "name": "Satidra"}, {"weapon": "kamas", "name": "Visi"}], ["Нечто"])
        rivens.remove("soma", "SATIDRA")
        self.assertEqual(rivens.load()["items"], [{"weapon": "kamas", "name": "Visi"}])
        with self.assertRaises(ValueError):
            rivens.remove("soma", "Satidra")
        rivens.forget_unknown()
        self.assertEqual(rivens.load()["unknown"], [])

    def test_the_example_has_its_own_mods_and_cannot_be_changed(self):
        rivens.store([{"weapon": "soma", "name": "Mine"}])
        before = rivens.RIVENS_FILE.read_bytes()
        demo.switch(True)
        self.assertEqual(len(rivens.load()["items"]), len(demo.RIVENS))
        for change in (lambda: rivens.store([{"weapon": "soma", "name": "Other"}]), lambda: rivens.remove("soma", "Mine"),
                       rivens.forget_unknown):
            with self.assertRaises(ValueError):
                change()
        demo.switch(False)
        self.assertEqual(rivens.RIVENS_FILE.read_bytes(), before)


class RivenPrices(unittest.TestCase):
    def setUp(self):
        clean_lists()
        rivens.store([{"weapon": "soma", "name": "Satidra"}, {"weapon": "kamas", "name": "Visi"}, {"weapon": "soma", "name": "Mantican"}])

    def tearDown(self):
        clean_lists()

    def state(self, market):
        return SimpleNamespace(wfm=market, riven_weapons=lambda: rivens.Weapons(WEAPONS))

    def test_the_bottom_of_the_market(self):
        offers = [{"platinum": 40, "status": "ingame"}, {"platinum": 12, "status": "offline"}, {"platinum": 25, "status": "online"},
                  {"platinum": 0, "status": "ingame"}, {"platinum": None, "status": "ingame"}, {"platinum": True, "status": "ingame"}]
        self.assertEqual(analysis.riven_floor(offers),
                         {"floor": 12, "floor_live": 25, "offers": 3, "live": 2, "cheapest": [12, 25, 40]})
        self.assertEqual(analysis.riven_floor([]), {"floor": None, "floor_live": None, "offers": 0, "live": 0, "cheapest": []})

    def test_the_list_is_shown_with_what_is_remembered_and_asks_nothing(self):
        market = FakeMarket(offers={"soma": {"offers": [{"platinum": 30, "status": "offline"}, {"platinum": 50, "status": "ingame"}],
                                             "listed": 100}})
        got = server.rivens_payload(self.state(market))
        self.assertEqual(market.asked, [])
        rows = {(r["weapon"], r["name"]): r for r in got["rivens"]}
        soma = rows[("soma", "Satidra")]
        self.assertEqual((soma["title"], soma["asked"], soma["floor"], soma["floor_live"], soma["listed"]), ("Сома", True, 30, 50, 100))
        self.assertEqual(rows[("soma", "Mantican")]["floor"], 30)                 # one weapon, one price
        self.assertEqual((rows[("kamas", "Visi")]["asked"], rows[("kamas", "Visi")]["floor"]), (False, None))
        self.assertIn("weapon_url_name=soma", soma["market_url"])
        self.assertEqual((got["interval"], got["ttl"]), (config.WFM_CONTRACT_MIN_INTERVAL, config.TTL_RIVEN_OFFERS))

    def test_a_price_is_asked_for_one_weapon_of_the_list_only(self):
        market = FakeMarket()
        got = server.riven_price(self.state(market), "soma")
        self.assertEqual((market.asked, got["price_error"]), (["soma"], ""))
        self.assertEqual({r["floor"] for r in got["rivens"] if r["weapon"] == "soma"}, {15})
        self.assertTrue(server.riven_price(self.state(market), "kamas")["price_error"])     # the market is silent: said, not raised
        with self.assertRaises(KeyError):
            server.riven_price(self.state(market), "bubonico")                    # not a weapon of the list: nothing is asked
        self.assertEqual(market.asked, ["soma", "kamas"])

    def test_the_site_allows_ten_such_requests_a_minute(self):
        self.assertLessEqual(60 / config.WFM_CONTRACT_MIN_INTERVAL, 10)
        self.assertGreaterEqual(config.TTL_RIVEN_OFFERS, 30 * 60)

    def test_without_the_list_of_weapons_the_mods_are_still_shown(self):
        def silent():
            raise FetchError("the market did not answer")

        got = server.rivens_payload(SimpleNamespace(wfm=FakeMarket(), riven_weapons=silent))
        self.assertTrue(got["error"])
        self.assertEqual([r["title"] for r in got["rivens"]], ["soma", "kamas", "soma"])


# --------------------------------------------------------------------------- relics
class RelicCaptions(unittest.TestCase):
    def setUp(self):
        self.index = relics.Index(ITEMS, None, DROPS)

    def test_a_caption_names_the_relic_and_its_refinement(self):
        self.assertEqual(self.index.parse("Реликвия Лит A13"), ("Lith A13", "intact"))
        self.assertEqual(self.index.parse("Реликвия Лит A13 [Бесподобная]"), ("Lith A13", "flawless"))
        self.assertEqual(self.index.parse("Реликвия Мезо K9 [Необычная]"), ("Meso K9", "exceptional"))
        self.assertEqual(self.index.parse("Реликвия Нео N21 [Сияющая]"), ("Neo N21", "radiant"))
        self.assertEqual(self.index.parse("Реликвия Реквием IV [Сияющая]"), ("Requiem IV", "radiant"))
        self.assertEqual(self.index.parse("Axi A22 Relic [Radiant]"), ("Axi A22", "radiant"))
        self.assertEqual(self.index.parse("Лит A13"), ("Lith A13", "intact"))                 # the word "relic" is not needed

    def test_a_look_alike_letter_in_the_code_is_the_latin_one(self):
        self.assertEqual(self.index.parse("Реликвия Лит С11"), ("Lith C11", "intact"))        # a Cyrillic С
        self.assertEqual(self.index.parse("Реликвия Мезо Р8 [Сияющая]"), ("Meso P8", "radiant"))
        self.assertEqual(self.index.parse("Реликвия Акси А22"), ("Axi A22", "intact"))

    def test_an_unknown_word_in_brackets_is_what_the_reader_made_of_it(self):
        self.assertEqual(self.index.parse("Лит A13 [Strahlend]", "radiant"), ("Lith A13", "radiant"))
        self.assertEqual(self.index.parse("Лит A13 [Strahlend]"), ("Lith A13", None))         # nobody knows: not taken
        self.assertEqual(self.index.parse("Лит A13 [Сияющая]", "intact"), ("Lith A13", "radiant"))   # a known word wins
        self.assertEqual(self.index.parse("Лит A13", "radiant"), ("Lith A13", "radiant"))

    def test_what_is_not_a_relic_is_not_guessed(self):
        for caption in ("Реликвия Лит Z99", "Реликвия", "Форма", ""):
            self.assertIsNone(self.index.parse(caption)[0], caption)

    def test_what_a_relic_holds_and_whether_it_still_drops(self):
        a13 = self.index.relics["Lith A13"]
        self.assertEqual((a13["status"], a13["name"], a13["era"]), ("missions", "Реликвия Лит A13", "lith"))
        # the rare one first, then by name as the interface shows it
        self.assertEqual([(r["tier"], r["slug"]) for r in a13["rewards"]],
                         [("rare", "gold_part"), ("uncommon", "silver_two"), ("uncommon", "silver_one"),
                          ("common", "bronze_two"), ("common", "bronze_one"), ("common", "bronze_three")])
        c11 = self.index.relics["Lith C11"]
        self.assertEqual(c11["status"], "vaulted")
        self.assertEqual(sorted(r["item"] for r in c11["rewards"] if r["slug"] is None), ["2X Forma Blueprint", "Forma Blueprint"])
        self.assertEqual(self.index.relics["Axi A22"]["status"], "special")       # not in the missions, not vaulted on the market
        self.assertEqual(len(self.index.relics["Requiem IV"]["rewards"]), 6)      # "Requiem Iv" of the drop tables
        self.assertEqual(relics.Index(ITEMS).relics["Lith A13"]["status"], "unknown")   # no drop tables: nothing is claimed

    def test_the_same_tile_on_two_screenshots_is_one_line(self):
        rev = relics.review([
            {"name": "Реликвия Лит A13", "refinement": "intact", "count": 17, "shot": "a.png"},
            {"name": "Реликвия Лит A13", "refinement": "intact", "count": 16, "shot": "b.png"},        # a slip in one of them
            {"name": "Реликвия Лит A13 [Бесподобная]", "refinement": "flawless", "count": 1, "shot": "a.png"},
            {"name": "Реликвия Мезо K9", "refinement": "intact", "count": "x", "shot": "b.png"},
            {"name": "Реликвия Лит Z99", "refinement": "intact", "count": 2, "shot": "b.png"},
            {"name": "Реликвия Лит Z99", "refinement": "intact", "count": 2, "shot": "c.png"}], self.index)
        self.assertEqual([(e["relic"], e["refinement"], e["count"], e["status"]) for e in rev["entries"]],
                         [("Lith A13", "intact", 17, "count"), ("Lith A13", "flawless", 1, "ok"), ("Meso K9", "intact", 1, "ok"),
                          (None, "intact", 2, "unmatched")])
        self.assertEqual((rev["matched"], rev["unmatched"], rev["kinds"]), (3, 1, 2))
        self.assertEqual(relics.review([], self.index), {"entries": [], "matched": 0, "unmatched": 0, "kinds": 0})


class RelicList(unittest.TestCase):
    def setUp(self):
        clean_lists()

    def tearDown(self):
        clean_lists()

    def test_the_whole_list_or_an_addition(self):
        relics.store([{"relic": "Lith A13", "refinement": "intact", "count": 17}, {"relic": "Lith A13", "refinement": "flawless", "count": 1},
                      {"relic": "Meso K9", "refinement": "intact", "count": 2}])
        relics.store([{"relic": "Lith A13", "refinement": "intact", "count": 15}, {"relic": "Neo N21", "refinement": "radiant", "count": 3}],
                     ["Нечто"], mode="merge")
        self.assertEqual([(i["relic"], i["refinement"], i["count"]) for i in relics.load()["items"]],
                         [("Lith A13", "intact", 15), ("Lith A13", "flawless", 1), ("Meso K9", "intact", 2), ("Neo N21", "radiant", 3)])
        self.assertEqual(relics.load()["unknown"], ["Нечто"])
        relics.store([{"relic": "Axi A22", "refinement": "intact", "count": 1}])
        self.assertEqual([i["relic"] for i in relics.load()["items"]], ["Axi A22"])

    def test_what_is_not_a_line_of_the_list_is_not_kept(self):
        relics.store([{"relic": "Lith A13", "refinement": "shiny", "count": 1}, {"relic": "A13", "refinement": "intact", "count": 1},
                      {"relic": "Lith A13", "refinement": "intact", "count": 0}, {"relic": "Lith A13", "refinement": "intact", "count": "many"},
                      "junk", {"relic": "Meso K9", "refinement": "radiant", "count": 100000}])
        self.assertEqual(relics.load()["items"], [{"relic": "Meso K9", "refinement": "radiant", "count": relics.MAX_COUNT}])

    def test_a_count_is_put_right_by_hand(self):
        relics.store([{"relic": "Lith A13", "refinement": "intact", "count": 17}, {"relic": "Meso K9", "refinement": "intact", "count": 1}])
        relics.set_count("Lith A13", "intact", 16)
        relics.set_count("Meso K9", "intact", 0)                                  # the last one is gone: the line too
        self.assertEqual(relics.load()["items"], [{"relic": "Lith A13", "refinement": "intact", "count": 16}])
        for bad in (("Lith A13", "radiant", 1), ("Lith A13", "shiny", 1), ("Neo N21", "intact", 1), ("Lith A13", "intact", "x")):
            with self.assertRaises(ValueError):
                relics.set_count(*bad)

    def test_the_example_has_its_own_relics_and_cannot_be_changed(self):
        relics.store([{"relic": "Lith A13", "refinement": "intact", "count": 2}])
        before = relics.RELICS_FILE.read_bytes()
        demo.switch(True)
        self.assertEqual(len(relics.load()["items"]), len(demo.RELICS))
        for change in (lambda: relics.store([]), lambda: relics.set_count("Lith A13", "intact", 5), relics.forget_unknown):
            with self.assertRaises(ValueError):
                change()
        demo.switch(False)
        self.assertEqual(relics.RELICS_FILE.read_bytes(), before)


class RelicWorth(unittest.TestCase):
    REWARDS = [{"tier": "rare", "price": 100}, {"tier": "uncommon", "price": 20}, {"tier": "uncommon", "price": None},
               {"tier": "common", "price": 5}, {"tier": "common", "price": 3}, {"tier": "common", "price": 2}]

    def setUp(self):
        clean_lists()
        self.index = relics.Index(ITEMS, None, DROPS)

    def tearDown(self):
        clean_lists()

    def state(self, market):
        return SimpleNamespace(wfm=market, relic_index=lambda: self.index)

    def test_the_tier_of_a_reward_is_told_by_its_chance(self):
        self.assertEqual([analysis.relic_tier(c) for c in (25.33, 11.0, 2.0, 9.5, None, "x", True)],
                         ["common", "uncommon", "rare", "uncommon", "", "", ""])

    def test_the_chances_of_every_refinement_add_up_to_a_whole(self):
        for level, (common, uncommon, rare) in analysis.RELIC_CHANCES.items():
            self.assertAlmostEqual(3 * common + 2 * uncommon + rare, 100, delta=0.02, msg=level)
        self.assertEqual(analysis.RELIC_TRACES, {"intact": 100, "exceptional": 75, "flawless": 50, "radiant": 0})

    def test_one_opening_is_worth_its_rewards_by_their_chances(self):
        self.assertAlmostEqual(analysis.relic_value(self.REWARDS, "intact"), 0.02 * 100 + 0.11 * 20 + 0.2533 * 10)
        self.assertAlmostEqual(analysis.relic_value(self.REWARDS, "radiant"), 0.10 * 100 + 0.20 * 20 + 0.1667 * 10)
        self.assertIsNone(analysis.relic_value(self.REWARDS[:5], "intact"))       # not built the usual way
        self.assertIsNone(analysis.relic_value(self.REWARDS, "shiny"))

    def test_what_refining_gives(self):
        got = analysis.relic_gain(self.REWARDS, "intact", "vaulted")
        self.assertAlmostEqual(got["gain"], got["radiant"] - got["now"])
        self.assertEqual(got["traces"], 100)
        self.assertAlmostEqual(got["per_100"], got["gain"])
        self.assertAlmostEqual(got["score"], got["gain"] * analysis.RELIC_STATUS_WEIGHT["vaulted"])
        half = analysis.relic_gain(self.REWARDS, "flawless")
        self.assertEqual(half["traces"], 50)
        self.assertAlmostEqual(half["per_100"], half["gain"] * 2)                 # half the traces, counted for a hundred
        done = analysis.relic_gain(self.REWARDS, "radiant")
        self.assertEqual((done["gain"], done["traces"], done["score"]), (0.0, 0, 0.0))

    def test_a_relic_that_cannot_be_found_again_stands_higher(self):
        weights = analysis.RELIC_STATUS_WEIGHT
        self.assertGreater(weights["vaulted"], weights["special"])
        self.assertGreater(weights["special"], weights["missions"])
        self.assertEqual(weights["missions"], 1.0)

    def test_the_relics_are_ranked_by_what_refining_gives(self):
        relics.store([{"relic": "Lith A13", "refinement": "intact", "count": 17}, {"relic": "Lith A13", "refinement": "flawless", "count": 1},
                      {"relic": "Lith C11", "refinement": "intact", "count": 9}, {"relic": "Neo N21", "refinement": "radiant", "count": 3},
                      {"relic": "Axi A22", "refinement": "intact", "count": 2}, {"relic": "Requiem Eterna", "refinement": "intact", "count": 1},
                      {"relic": "Lith Z99", "refinement": "intact", "count": 1}])
        market = FakeMarket(PRICES)
        got = server.relics_payload(self.state(market))
        self.assertEqual((market.asked, got["need"]), ([], 0))
        rows = {(r["relic"], r["refinement"]): r for r in got["relics"]}
        order_ = [key for key, r in sorted(rows.items(), key=lambda kv: kv[1]["rank"] or 99) if r["rank"]]
        # the dear rare reward first; of two relics that hold the same, the one that no longer drops; the half refined one last
        self.assertEqual(order_, [("Lith C11", "intact"), ("Axi A22", "intact"), ("Lith A13", "intact"), ("Lith A13", "flawless")])
        self.assertEqual(rows[("Axi A22", "intact")]["value"]["gain"], rows[("Lith A13", "intact")]["value"]["gain"])
        self.assertIsNone(rows[("Neo N21", "radiant")]["rank"])                   # nothing left to refine
        self.assertEqual(rows[("Neo N21", "radiant")]["value"]["gain"], 0)
        self.assertIsNone(rows[("Requiem Eterna", "intact")]["value"])            # eight rewards: no usual chances
        self.assertEqual((rows[("Lith Z99", "intact")]["rewards"], rows[("Lith Z99", "intact")]["status"]), ([], "unknown"))
        c11 = rows[("Lith C11", "intact")]
        self.assertEqual([(r["slug"], r["price"], r["asked"]) for r in c11["rewards"] if r["slug"] is None], [(None, None, True)] * 2)
        self.assertEqual(got["chances"]["radiant"], {"common": 16.67, "uncommon": 20.0, "rare": 10.0})

    def test_a_relic_without_all_its_prices_waits_for_them(self):
        relics.store([{"relic": "Lith A13", "refinement": "intact", "count": 1}])
        market = FakeMarket({k: v for k, v in PRICES.items() if k != "gold_part"})
        got = server.relics_payload(self.state(market))
        row, = got["relics"]
        self.assertEqual((row["complete"], row["value"], row["rank"], row["need"], got["need"]), (False, None, None, 1, 1))
        old = server.relics_payload(self.state(FakeMarket(PRICES, age=config.TTL_RELIC_PRICES + 60)))
        self.assertEqual((old["relics"][0]["complete"], old["need"]), (True, 6))  # ranked by what is known, asked anew when told

    def test_prices_are_asked_only_where_they_are_missing_or_old(self):
        relics.store([{"relic": "Lith A13", "refinement": "intact", "count": 1}])
        market = FakeMarket({k: v for k, v in PRICES.items() if k not in ("gold_part", "silver_two")})
        got = server.relic_prices(self.state(market), "Lith A13")
        self.assertEqual(market.asked, ["gold_part", "silver_two"])
        self.assertEqual(len(got["price_errors"]), 1)                             # one of them the market did not give
        market = FakeMarket(PRICES, age=config.TTL_TOP_ORDERS + 60)
        server.relic_prices(self.state(market), "Lith A13")
        self.assertEqual(market.asked, [])                                        # fresh enough for a ranking
        market = FakeMarket(PRICES, age=config.TTL_TOP_ORDERS + 60)
        server.relic_prices(self.state(market), "Lith A13", force=True)
        # "anew": what is older than a few minutes is asked again (the fake has one clock for all prices,
        # so its first answer makes the rest fresh)
        self.assertEqual(market.asked, ["gold_part"])
        with self.assertRaises(KeyError):
            server.relic_prices(self.state(FakeMarket()), "Lith Z99")


# --------------------------------------------------------------------------- reading the screenshots
class Reader:
    """Stands in for the connection that reads screenshots: answers from a table by the name of the file."""
    id = "fake"

    def __init__(self, answers, ready=True):
        self.answers, self.ready, self.read_files = answers, ready, []

    def status(self, force=False):
        return {"ready": self.ready, "reason": "" if self.ready else "login"}

    def read(self, work_dir, tiles, task, holder=None):
        name = tiles[0].name.split(".")[0].split("__")[0]
        self.read_files.append(name)
        answer = self.answers[name]
        if isinstance(answer, Exception):
            raise answer
        return {"data": answer, "seconds": 0.1}


class Scans(unittest.TestCase):
    def setUp(self):
        clean_lists()
        self._current = providers.current

    def tearDown(self):
        providers.current = self._current
        clean_lists()

    def put_shots(self, kind, names):
        folder = scans.inbox(kind)
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            if shots.have_pillow():
                from PIL import Image
                Image.new("RGB", (64, 48), "black").save(folder / name)
            else:
                (folder / name).write_bytes(b"not a picture, copied as it is")
        return scans.files(kind)

    def run_job(self, kind, answers, context, ready=True):
        reader = Reader(answers, ready)
        providers.current = lambda: reader
        job = scans.ScanJob(kind, scans.files(kind), context)
        job.run()
        return job, reader

    def test_each_kind_has_a_request_and_an_inbox_of_its_own(self):
        for kind in scans.KINDS:
            for lang in ("ru", "en", "de"):
                task = scans.task(kind, lang, "ru")
                self.assertIn("{files}", task.prompt_files)
                self.assertNotIn("[WHAT]", task.prompt_files + task.prompt_attached)
                self.assertNotIn("LANGUAGE", task.prompt_attached)
                self.assertEqual(task.schema["properties"]["screen"]["enum"], [kind, "other"])
                self.assertFalse(task.schema["additionalProperties"])
                self.assertEqual(task.schema["required"], list(task.schema["properties"]))
            self.assertEqual(scans.inbox(kind).parent, config.SCREENSHOT_DIR)
            self.assertNotIn(scans.inbox(kind), shots.originals())
        # relics are shot on the sell screen of the inventory: the request describes its tiles, the count
        # next to the check mark, and asks for nothing that screen does not show
        self.assertEqual(list(scans.SCHEMAS["relics"]["properties"]), ["screen", "items", "notes"])
        for lang in ("ru", "de"):
            prompt = scans.task("relics", lang, "ru").prompt_attached
            self.assertTrue("ИНВЕНТАРЬ / ПРОДАТЬ" in prompt or "Inventory / Sell" in prompt, lang)
            self.assertTrue("галочкой в кружке" in prompt or "check mark in a circle" in prompt, lang)
            self.assertNotIn("collected", prompt)
        with self.assertRaises(ValueError):
            scans.inbox("inventory")

    def test_an_answer_is_brought_to_shape_whatever_it_is(self):
        got = scans.clean_answer("relics", {"screen": "relics", "collected": "many", "notes": None, "extra": 1, "items": [
            {"name": " Реликвия  Лит A13 ", "refinement": "flawless", "count": "3", "count_visible": True},
            {"name": "Реликвия Лит A6", "refinement": "shiny", "count": None},
            {"name": ""}, "junk", {"name": "Реликвия Мезо K9", "count": -4, "run": "rm -rf"}]})
        self.assertEqual(got, {"screen": "relics", "notes": "", "items": [
            {"name": "Реликвия Лит A13", "refinement": "flawless", "count": 3, "count_visible": True},
            {"name": "Реликвия Лит A6", "refinement": None, "count": 1, "count_visible": False},
            {"name": "Реликвия Мезо K9", "refinement": None, "count": 1, "count_visible": False}]})
        self.assertEqual(scans.clean_answer("rivens", {"screen": "relics", "items": [{"name": "Сома Satidra", "count": 5}]}),
                         {"screen": "other", "items": [{"name": "Сома Satidra"}], "notes": ""})
        self.assertEqual(scans.clean_answer("relics", {"screen": "relics", "items": [], "collected": 110}),
                         {"screen": "relics", "items": [], "notes": ""})        # a field nobody asked for is dropped
        for junk in (None, [], "text", {"something": 1}):
            with self.assertRaises(ProviderError):
                scans.clean_answer("rivens", junk)

    def test_riven_mods_are_read_and_saved(self):
        self.put_shots("rivens", ["a.png", "b.png", "c.png"])
        job, reader = self.run_job("rivens", {
            "a": {"screen": "rivens", "notes": "", "items": [{"name": "Сома Satidra"}, {"name": "Жнец Прайм Crita- ignitox"}]},
            "b": {"screen": "rivens", "notes": "не прочитана подпись справа", "items": [{"name": "Сома Satidra"}, {"name": "Нечто Странное"}]},
            "c": {"screen": "other", "notes": "", "items": [{"name": "Камы Visi"}]},
        }, lambda: rivens.Weapons(WEAPONS))
        self.assertEqual((job.state, sorted(reader.read_files)), ("review", ["a", "b", "c"]))
        snap = job.snapshot()
        self.assertEqual([(e["weapon"], e["name"]) for e in snap["review"]["entries"]],
                         [("soma", "Satidra"), ("reaper_prime", "Crita-ignitox"), (None, "")])
        self.assertEqual((snap["review"]["other_screens"], snap["notes"]), (["c.png"], ["b.png: не прочитана подпись справа"]))
        job.apply("replace", skip=[1])                                            # the user took a line out
        self.assertEqual((rivens.load()["items"], rivens.load()["unknown"]), ([{"weapon": "soma", "name": "Satidra"}], ["Нечто Странное"]))
        self.assertEqual((job.state, scans.files("rivens")), ("applied", []))     # the screenshots have moved to the archive
        with self.assertRaises(ProviderError):
            job.apply("replace")

    def test_relics_are_read_and_saved(self):
        relics.store([{"relic": "Neo N21", "refinement": "radiant", "count": 3}])
        self.put_shots("relics", ["a.png", "b.png"])
        index = relics.Index(ITEMS, None, DROPS)
        job, _ = self.run_job("relics", {
            "a": {"screen": "relics", "notes": "", "items": [
                {"name": "Реликвия Лит A13", "refinement": "intact", "count": 17, "count_visible": True},
                {"name": "Реликвия Лит A13 [Бесподобная]", "refinement": "flawless", "count": 1, "count_visible": False}]},
            "b": {"screen": "relics", "notes": "", "items": [
                {"name": "Реликвия Лит A13", "refinement": "intact", "count": 17, "count_visible": True},
                {"name": "Реликвия Мезо К9 [Сияющая]", "refinement": "radiant", "count": 2, "count_visible": True}]},
        }, lambda: index)
        rev = job.snapshot()["review"]
        self.assertEqual((rev["matched"], rev["kinds"], rev["other_screens"]), (3, 2, []))
        job.apply("merge")
        self.assertEqual([(i["relic"], i["refinement"], i["count"]) for i in relics.load()["items"]],
                         [("Lith A13", "intact", 17), ("Lith A13", "flawless", 1), ("Meso K9", "radiant", 2), ("Neo N21", "radiant", 3)])

    def test_a_reading_that_cannot_start_spends_nothing(self):
        self.put_shots("rivens", ["a.png"])
        job, reader = self.run_job("rivens", {}, lambda: rivens.Weapons(WEAPONS), ready=False)
        self.assertEqual((job.state, job.error_code, reader.read_files), ("error", "login", []))

        def silent():
            raise FetchError("the market did not answer")

        job, reader = self.run_job("rivens", {}, silent)
        self.assertEqual((job.state, job.error_code, reader.read_files), ("error", "network", []))   # no names to match against
        self.assertEqual(len(scans.files("rivens")), 1)                           # the screenshot waits where it was

    def test_one_bad_screenshot_does_not_stop_the_rest(self):
        self.put_shots("rivens", ["a.png", "b.png"])
        job, _ = self.run_job("rivens", {"a": ProviderError("the picture was refused", "refused"),
                                         "b": {"screen": "rivens", "notes": "", "items": [{"name": "Сома Satidra"}]}},
                              lambda: rivens.Weapons(WEAPONS))
        snap = job.snapshot()
        self.assertEqual((snap["state"], [f["state"] for f in snap["files"]], snap["review"]["matched"]), ("review", ["error", "done"], 1))
        self.put_shots("relics", ["a.png"])
        job, _ = self.run_job("relics", {"a": ProviderError("no such key", "bad_key")}, lambda: relics.Index(ITEMS, None, DROPS))
        self.assertEqual((job.state, job.error_code), ("error", "bad_key"))

    def test_screenshots_of_the_game_can_go_to_an_inbox_of_a_kind(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("PRIMESETS_GAME_SHOTS")
            os.environ["PRIMESETS_GAME_SHOTS"] = tmp
            try:
                shots.game_mark_seen(time.time() - 3600)
                (Path(tmp) / "Warframe0007.jpg").write_bytes(b"picture")
                inventory_inbox = shots.originals()                 # other tests may have left their own files there
                copied = shots.game_import(dest=scans.inbox("relics"))
                self.assertEqual([f.parent for f in copied], [scans.inbox("relics")])
                self.assertEqual((len(scans.files("relics")), shots.originals(), shots.game_new()["files"]),
                                 (1, inventory_inbox, []))          # nothing went to the inbox of the inventory
            finally:
                if old is None:
                    os.environ.pop("PRIMESETS_GAME_SHOTS", None)
                else:
                    os.environ["PRIMESETS_GAME_SHOTS"] = old


if __name__ == "__main__":
    unittest.main()
