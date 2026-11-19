"""Offline tests of the calculations: no network, no real inventory.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# keep the real inventory and screenshot inbox untouched: all writes go to throw-away folders
_TMP = tempfile.TemporaryDirectory()
os.environ["PRIMESETS_DATA"] = str(Path(_TMP.name) / "data")
os.environ["PRIMESETS_SCREENSHOTS"] = str(Path(_TMP.name) / "screenshots")
FAKE_CLAUDE = [sys.executable, str(Path(__file__).resolve().parent / "fake_claude.py")]

from primesets import (analysis, catalog, continuity, droptables, i18n, inventory, mastery, providers, recognize,  # noqa: E402
                       settings, shots, vault)
from primesets.providers import claude_cli  # noqa: E402
from primesets.matching import Matcher, normalize, split_blueprint  # noqa: E402
from primesets.wfm import RateLimiter  # noqa: E402


def part(slug, ru, en, qty=1, blueprint=False, availability="vaulted"):
    return {"slug": slug, "name": ru, "game": ru, "en": en, "label": ru, "quantity": qty, "thumb": "", "ducats": 15,
            "blueprint": blueprint, "relics": [], "availability": availability}


def make_catalog():
    sets = {
        "mirage_prime_set": {
            "slug": "mirage_prime_set", "name": "Мираж Прайм: Комплект", "en": "Mirage Prime Set",
            "title": "Мираж Прайм", "title_en": "Mirage Prime", "thumb": "", "category": "warframe",
            "parts": [
                part("mirage_prime_blueprint", "Мираж Прайм (Чертеж)", "Mirage Prime Blueprint", blueprint=True),
                part("mirage_prime_chassis_blueprint", "Мираж Прайм: Каркас (Чертеж)", "Mirage Prime Chassis Blueprint", blueprint=True),
                part("mirage_prime_neuroptics_blueprint", "Мираж Прайм: Нейрооптика (Чертеж)", "Mirage Prime Neuroptics Blueprint", blueprint=True),
                part("mirage_prime_systems_blueprint", "Мираж Прайм: Система (Чертеж)", "Mirage Prime Systems Blueprint", blueprint=True),
            ],
        },
        "akstiletto_prime_set": {
            "slug": "akstiletto_prime_set", "name": "Акстилетто Прайм: Комплект", "en": "Akstiletto Prime Set",
            "title": "Акстилетто Прайм", "title_en": "Akstiletto Prime", "thumb": "", "category": "secondary",
            "parts": [
                part("akstiletto_prime_blueprint", "Акстилетто Прайм (Чертеж)", "Akstiletto Prime Blueprint", blueprint=True),
                part("akstiletto_prime_barrel", "Акстилетто Прайм: Ствол", "Akstiletto Prime Barrel", qty=2),
                part("akstiletto_prime_receiver", "Акстилетто Прайм: Приёмник", "Akstiletto Prime Receiver", qty=2),
                part("akstiletto_prime_link", "Акстилетто Прайм: Связь", "Akstiletto Prime Link"),
            ],
        },
        "vasto_prime_set": {
            "slug": "vasto_prime_set", "name": "Васто Прайм: Комплект", "en": "Vasto Prime Set",
            "title": "Васто Прайм", "title_en": "Vasto Prime", "thumb": "", "category": "secondary",
            "parts": [
                part("vasto_prime_blueprint", "Васто Прайм (Чертеж)", "Vasto Prime Blueprint", blueprint=True),
                part("vasto_prime_barrel", "Васто Прайм: Ствол", "Vasto Prime Barrel"),
                part("vasto_prime_receiver", "Васто Прайм: Приёмник", "Vasto Prime Receiver"),
            ],
        },
        "akvasto_prime_set": {
            "slug": "akvasto_prime_set", "name": "Аквасто Прайм: Комплект", "en": "Akvasto Prime Set",
            "title": "Аквасто Прайм", "title_en": "Akvasto Prime", "thumb": "", "category": "secondary",
            "parts": [
                part("akvasto_prime_blueprint", "Аквасто Прайм (Чертеж)", "Akvasto Prime Blueprint", blueprint=True),
                part("akvasto_prime_link", "Аквасто Прайм: Связь", "Akvasto Prime Link"),
            ],
        },
        "kavasa_prime_kubrow_collar_set": {
            "slug": "kavasa_prime_kubrow_collar_set", "name": "Ошейник Кубрау: Каваса Прайм: Комплект",
            "en": "Kavasa Prime Kubrow Collar Set", "title": "Ошейник Кубрау: Каваса Прайм",
            "title_en": "Kavasa Prime Kubrow Collar", "thumb": "", "category": "other",
            "parts": [part("kavasa_prime_band", "Каваса Прайм: Лента", "Kavasa Prime Band")],
        },
    }
    index = {p["slug"]: slug for slug, st in sets.items() for p in st["parts"]}
    return {"version": catalog.CATALOG_VERSION, "sets": sets, "part_index": index}


# --------------------------------------------------------------------------- drawn sell screens (need Pillow)
ROW = 148               # row pitch of the drawn list at 1280x720 -- half of the real 296 px at 1440 lines
VIEW = (133, 654)       # the lines of the screen where the list scrolls: three rows and a half


def draw_list(rows, seed=7):
    """The whole list as one tall picture: rows of six tiles, every tile with content of its own."""
    import random
    from PIL import Image, ImageDraw
    rng = random.Random(seed)
    img = Image.new("L", (900, rows * ROW), 14)
    d = ImageDraw.Draw(img)
    for r in range(rows):
        for c in range(6):
            x, y = round(50 + c * 138.4), r * ROW
            d.rectangle((x, y, x + 126, y + 126), fill=24)
            for _ in range(7):                       # the "icon": a few bright shapes
                x0, y0 = x + rng.randint(8, 80), y + rng.randint(8, 60)
                d.rectangle((x0, y0, x0 + rng.randint(8, 40), y0 + rng.randint(6, 30)), fill=rng.randint(110, 250))
            for line in range(2):                    # the caption
                x0 = x + rng.randint(8, 30)
                d.rectangle((x0, y + 96 + line * 14, x0 + rng.randint(50, 90), y + 104 + line * 14), fill=200)
    return img


def draw_screen(strip, offset, glow=0):
    """The sell screen: a header, the list scrolled down by `offset` pixels, a side panel, a scrollbar."""
    import random
    from PIL import Image, ImageChops, ImageDraw
    img = Image.new("L", (1280, 720), 14)
    d = ImageDraw.Draw(img)
    d.rectangle((60, 30, 440, 58), fill=210)          # the title
    for i in range(17):                               # the row of category icons
        d.rectangle((62 + i * 26, 98, 80 + i * 26, 116), fill=150)
    d.rectangle((920, 280, 1200, 320), fill=180)      # the side panel
    d.rectangle((920, 600, 1200, 640), fill=120)
    img.paste(strip.crop((0, offset, 880, offset + VIEW[1] - VIEW[0])), (0, VIEW[0]))
    # the scrollbar: its thumb travels the height of the list window as the list goes from top to bottom
    travel = strip.size[1] - 21 - (VIEW[1] - VIEW[0])
    if travel > 0:
        top = VIEW[0] + round((VIEW[1] - VIEW[0] - 33) * min(offset, travel) / travel)
        d.rectangle((894, top, 897, top + 32), fill=220)
    if glow:                                          # the drifting background glow: different on every screenshot
        rng = random.Random(glow)
        haze = Image.new("L", (16, 9))
        haze.putdata([rng.randint(0, 28) for _ in range(16 * 9)])
        img = ImageChops.add(img, haze.resize(img.size, Image.BICUBIC))
    return img


def draw_foundry(seed=3):
    """Wide cards in two columns: not a grid of tiles."""
    import random
    from PIL import Image, ImageDraw
    rng = random.Random(seed)
    img = Image.new("L", (1280, 720), 14)
    d = ImageDraw.Draw(img)
    for r in range(3):
        for c in range(2):
            x, y = 60 + c * 420, 140 + r * 175
            d.rectangle((x, y, x + 400, y + 160), fill=40)
            for _ in range(12):
                x0, y0 = x + rng.randint(5, 330), y + rng.randint(5, 130)
                d.rectangle((x0, y0, x0 + rng.randint(20, 60), y0 + rng.randint(6, 20)), fill=rng.randint(110, 250))
    return img


@unittest.skipUnless(shots.have_pillow(), "the join check needs Pillow")
class Joins(unittest.TestCase):
    """continuity.py on drawn sell screens: three full rows of tiles and a fourth one cut by the edge."""
    ROWS = 16

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.strip = draw_list(cls.ROWS)
        cls.end = cls.ROWS * ROW - 21 - (VIEW[1] - VIEW[0])      # the list cannot scroll further than this

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        continuity.forget()
        self.n = 0

    def page(self, offset, crop=None, spoil=()):
        """A screenshot of the list scrolled to `offset`; `spoil` -- tile columns of the first row drawn over."""
        from PIL import ImageDraw
        self.n += 1
        img = draw_screen(self.strip, offset, glow=self.n)
        for col in spoil:
            x = round(50 + col * 138.4)
            d = ImageDraw.Draw(img)
            d.rectangle((x + 3, VIEW[0] + 3, x + 123, VIEW[0] + 70), outline=255, width=3)
            d.rectangle((x + 30, VIEW[0] + 20, x + 100, VIEW[0] + 50), fill=235)
        if crop:
            img = img.crop(crop)
        path = Path(self.tmp.name) / f"{self._testMethodName}-{self.n:02d}.png"
        img.save(path)
        return path

    def gaps(self, report):
        return [(g["after"][-6:-4], g["before"][-6:-4]) for g in report["gaps"]]

    def test_three_rows_a_step_join(self):
        files = [self.page(0), self.page(3 * ROW), self.page(6 * ROW)]
        rep = continuity.check(files)
        self.assertEqual((rep["state"], rep["pages"], rep["joined"], rep["gaps"]), ("ok", 3, 2, []))
        self.assertEqual(continuity.join(files[0], files[1]).shift, 3 * ROW)

    def test_a_skipped_row_is_a_gap(self):
        files = [self.page(0), self.page(3 * ROW), self.page(7 * ROW), self.page(10 * ROW)]
        rep = continuity.check(files)
        self.assertEqual((rep["state"], rep["joined"]), ("gaps", 2))
        self.assertEqual(self.gaps(rep), [("02", "03")])

    def test_a_retake_added_later_closes_the_gap(self):
        files = [self.page(0), self.page(3 * ROW), self.page(7 * ROW), self.page(10 * ROW)]
        files.append(self.page(6 * ROW))             # the missed row is the first one here
        rep = continuity.check(files)
        self.assertEqual((rep["state"], rep["gaps"]), ("ok", []))

    def test_a_retake_that_misses_the_place_does_not(self):
        files = [self.page(0), self.page(3 * ROW), self.page(7 * ROW), self.page(10 * ROW)]
        files.append(self.page(0))                   # shot again, but not where the row was skipped
        self.assertEqual(self.gaps(continuity.check(files)), [("02", "03")])

    def test_the_last_page_scrolls_less(self):
        self.assertLess(self.end - 12 * ROW, 3 * ROW)
        files = [self.page(o) for o in (6 * ROW, 9 * ROW, 12 * ROW, self.end)]
        rep = continuity.check(files)
        self.assertEqual((rep["state"], rep["joined"]), ("ok", 3))
        self.assertEqual(continuity.join(files[2], files[3]).shift, self.end - 12 * ROW)

    def test_the_same_screen_twice_and_scrolling_back(self):
        files = [self.page(3 * ROW), self.page(3 * ROW), self.page(0)]
        rep = continuity.check(files)
        self.assertEqual((rep["state"], rep["joined"]), ("ok", 2))
        self.assertEqual(continuity.join(files[1], files[2]).shift, -3 * ROW)

    def test_other_screens_are_left_out(self):
        foundry = Path(self.tmp.name) / "foundry.png"
        draw_foundry().save(foundry)
        self.assertFalse(continuity.is_grid(foundry))
        files = [self.page(0), foundry, self.page(3 * ROW)]
        rep = continuity.check(files)
        self.assertEqual((rep["state"], rep["pages"], rep["joined"]), ("ok", 2, 1))

    def test_nothing_joins_is_one_warning_not_many(self):
        files = [self.page(o) for o in (0, 4 * ROW, 8 * ROW, 12 * ROW)]      # four rows every time
        rep = continuity.check(files)
        self.assertEqual((rep["state"], rep["joined"], len(rep["gaps"])), ("unsure", 0, 3))

    def test_what_the_recognition_said_decides_which_screens_count(self):
        files = [self.page(0), self.page(3 * ROW), self.page(6 * ROW)]
        screens = {files[0].name: "inventory", files[1].name: "foundry", files[2].name: "inventory"}
        rep = continuity.check(files, screens)
        self.assertEqual((rep["pages"], self.gaps(rep)), (2, [("01", "03")]))

    def ends(self, report):
        return (report["start"], report["end"], report["first"][-6:-4], report["last"][-6:-4])

    def test_the_whole_list_from_top_to_bottom(self):
        files = [self.page(o) for o in (0, 3 * ROW, 6 * ROW, 9 * ROW, 12 * ROW, self.end)]
        rep = continuity.check(files)
        self.assertEqual((rep["state"], rep["joined"]), ("ok", 5))
        self.assertEqual(self.ends(rep), ("ok", "ok", "01", "06"))

    def test_stopped_before_the_end(self):
        # the last screenshot is an ordinary page: its cut fourth row is on no screenshot in full
        files = [self.page(o) for o in (0, 3 * ROW, 6 * ROW, 9 * ROW, 12 * ROW)]
        rep = continuity.check(files)
        self.assertEqual((rep["state"], self.ends(rep)), ("ok", ("ok", "missing", "01", "05")))

    def test_started_below_the_top(self):
        files = [self.page(o) for o in (3 * ROW, 6 * ROW, 9 * ROW, 12 * ROW, self.end)]
        rep = continuity.check(files)
        self.assertEqual((rep["state"], self.ends(rep)), ("ok", ("missing", "ok", "01", "05")))

    def test_the_ends_go_by_the_place_in_the_list_not_by_the_order_of_shooting(self):
        files = [self.page(o) for o in (12 * ROW, self.end, 9 * ROW, 6 * ROW, 3 * ROW, 0)]
        rep = continuity.check(files)
        self.assertEqual((rep["state"], self.ends(rep)), ("ok", ("ok", "ok", "06", "02")))

    def test_one_screenshot(self):
        rep = continuity.check([self.page(0)])
        self.assertEqual((rep["state"], rep["pages"], self.ends(rep)), ("none", 1, ("ok", "missing", "01", "01")))
        # a list of three rows fits on the screen: nothing is cut at the bottom (and there is no scrollbar to go by)
        short = draw_screen(draw_list(3), 0, glow=5)
        path = Path(self.tmp.name) / "short-01.png"
        short.save(path)
        rep = continuity.check([path])
        self.assertEqual(self.ends(rep), ("unknown", "ok", "01", "01"))

    def test_the_ends_are_told_together_with_a_gap(self):
        # one trip back to the game should be enough: a skipped row AND the missing end are both reported
        files = [self.page(o) for o in (0, 3 * ROW, 7 * ROW, 10 * ROW)]
        rep = continuity.check(files)
        self.assertEqual((rep["state"], self.gaps(rep), self.ends(rep)), ("gaps", [("02", "03")], ("ok", "missing", "01", "04")))

    def test_a_retake_of_the_wrong_place_is_not_a_new_gap(self):
        files = [self.page(o) for o in (0, 3 * ROW, 6 * ROW, 10 * ROW, 13 * ROW)]
        files.append(self.page(3 * ROW))             # shot again where nothing was missing
        rep = continuity.check(files)
        self.assertEqual(self.gaps(rep), [("03", "04")])

    def test_one_tile_drawn_differently_is_forgiven(self):
        # a tile under the cursor is highlighted: one column may differ, two may not
        a = self.page(0)
        self.assertTrue(continuity.join(a, self.page(3 * ROW, spoil=(2,))).joined)
        self.assertFalse(continuity.join(a, self.page(3 * ROW, spoil=(1, 4))).joined)

    def test_screenshots_cut_to_another_size(self):
        whole = self.page(0)
        cut = self.page(3 * ROW, crop=(0, 0, 1272, 714))
        self.assertTrue(continuity.join(whole, cut).joined)
        skipped = self.page(4 * ROW, crop=(0, 0, 1272, 714))
        link = continuity.join(whole, skipped)
        self.assertEqual((link.joined, link.why), (False, "size"), "not sure enough to call it a gap")
        rep = continuity.check([whole, skipped])
        self.assertEqual((rep["state"], rep["gaps"], len(rep["unknown"])), ("unknown", [], 1))


class Normalisation(unittest.TestCase):
    def test_case_yo_and_punctuation(self):
        self.assertEqual(normalize("ЧЕРТЁЖ:  Мираж Прайм — Система!"), "чертеж мираж прайм система")

    def test_blueprint_word_is_split_off(self):
        self.assertEqual(split_blueprint("Чертёж: Мираж Прайм: Система"), ("мираж прайм система", True))
        self.assertEqual(split_blueprint("Mirage Prime Systems Blueprint"), ("mirage prime systems", True))
        self.assertEqual(split_blueprint("Акстилетто Прайм: Ствол"), ("акстилетто прайм ствол", False))


class Matching(unittest.TestCase):
    def setUp(self):
        self.m = Matcher(make_catalog())

    def test_game_style_and_market_style_names(self):
        for name in ("Чертёж: Мираж Прайм: Система", "Мираж Прайм: Система (Чертеж)", "МИРАЖ ПРАЙМ: СИСТЕМА (ЧЕРТЁЖ)",
                     "Mirage Prime Systems Blueprint"):
            res = self.m.match(name)
            self.assertEqual((res.status, res.slug), ("exact", "mirage_prime_systems_blueprint"), name)

    def test_word_order_does_not_matter(self):
        self.assertEqual(self.m.match("Система: Мираж Прайм", True).slug, "mirage_prime_systems_blueprint")

    def test_main_blueprint(self):
        self.assertEqual(self.m.match("Чертёж: Мираж Прайм").slug, "mirage_prime_blueprint")

    def test_built_item_is_not_counted(self):
        res = self.m.match("Мираж Прайм: Система", blueprint=False)
        self.assertEqual(res.status, "built")
        self.assertFalse(res.ok)

    def test_unknown_blueprint_flag_is_flagged(self):
        res = self.m.match("Мираж Прайм: Система")
        self.assertTrue(res.ok)
        self.assertIn("чертёж", res.note)

    def test_small_reading_slip_is_fuzzy(self):
        res = self.m.match("Акстилето Прайм: Ствол", blueprint=False)
        self.assertEqual((res.status, res.slug), ("fuzzy", "akstiletto_prime_barrel"))

    def test_similar_names_are_not_confused(self):
        self.assertEqual(self.m.match("Васто Прайм: Ствол", False).slug, "vasto_prime_barrel")
        self.assertEqual(self.m.match("Аквасто Прайм: Связь", False).slug, "akvasto_prime_link")
        self.assertEqual(self.m.match("Чертёж: Аквасто Прайм").slug, "akvasto_prime_blueprint")
        self.assertEqual(self.m.match("Чертёж: Васто Прайм").slug, "vasto_prime_blueprint")

    def test_garbage_and_non_prime(self):
        self.assertEqual(self.m.match("Зюзя Прайм: Хвост").status, "unmatched")
        self.assertEqual(self.m.match("Чертёж: Форма").status, "not_prime")

    def test_whole_item_to_set(self):
        self.assertEqual(self.m.match_set("Акстилетто Прайм").slug, "akstiletto_prime_set")
        self.assertEqual(self.m.match_set("AKSTILETTO PRIME").slug, "akstiletto_prime_set")
        self.assertEqual(self.m.match_set("Чертёж: Мираж Прайм").slug, "mirage_prime_set")
        self.assertEqual(self.m.match_set("Васто Прайм").slug, "vasto_prime_set")
        self.assertEqual(self.m.match_set("Экскалибур").status, "not_prime")


class CompleteSets(unittest.TestCase):
    def setUp(self):
        self.cat = make_catalog()

    def test_part_needed_twice(self):
        st = self.cat["sets"]["akstiletto_prime_set"]
        have = {"akstiletto_prime_blueprint": 1, "akstiletto_prime_barrel": 1, "akstiletto_prime_receiver": 2,
                "akstiletto_prime_link": 1}
        prog = analysis.set_progress(st, have)
        self.assertEqual(prog["complete"], 0, "one barrel is not enough: the set needs two")
        self.assertEqual(prog["missing"], [{"slug": "akstiletto_prime_barrel", "count": 1}])
        have["akstiletto_prime_barrel"] = 2
        self.assertEqual(analysis.set_progress(st, have)["complete"], 1)

    def test_several_copies_and_next_copy(self):
        st = self.cat["sets"]["akstiletto_prime_set"]
        have = {"akstiletto_prime_blueprint": 3, "akstiletto_prime_barrel": 5, "akstiletto_prime_receiver": 4,
                "akstiletto_prime_link": 2}
        prog = analysis.set_progress(st, have)
        self.assertEqual(prog["complete"], 2)
        missing = {m["slug"]: m["count"] for m in prog["missing"]}
        self.assertEqual(missing, {"akstiletto_prime_barrel": 1, "akstiletto_prime_receiver": 2,
                                   "akstiletto_prime_link": 1})

    def test_split_and_order(self):
        items = {"mirage_prime_blueprint": 1, "mirage_prime_chassis_blueprint": 1,
                 "mirage_prime_neuroptics_blueprint": 1, "mirage_prime_systems_blueprint": 1,
                 "vasto_prime_barrel": 1, "akvasto_prime_link": 1}
        split = analysis.split_inventory(self.cat, items)
        self.assertEqual([r["slug"] for r in split["complete"]], ["mirage_prime_set"])
        # nearest first: Akvasto lacks one part, Vasto lacks two
        self.assertEqual([r["slug"] for r in split["partial"]], ["akvasto_prime_set", "vasto_prime_set"])


class Prices(unittest.TestCase):
    def test_ingame_seller_wins_over_cheaper_site_only_seller(self):
        top = {"sell": [{"platinum": 40, "status": "online"}, {"platinum": 45, "status": "ingame"},
                        {"platinum": 50, "status": "ingame"}],
               "buy": [{"platinum": 30, "status": "ingame"}, {"platinum": 35, "status": "online"}]}
        p = analysis.price_from_orders(top)
        self.assertEqual((p["value"], p["basis"], p["buy_max"]), (45, "ingame", 35))

    def test_fallback_and_empty(self):
        self.assertEqual(analysis.price_from_orders({"sell": [{"platinum": 40, "status": "online"}]})["basis"], "online")
        self.assertIsNone(analysis.price_from_orders({"sell": [], "buy": []})["value"])


class Ducats(unittest.TestCase):
    """The "Дукаты" tab: what a set brings at the ducat kiosk against what it costs."""

    def test_a_part_needed_twice_counts_twice(self):
        cat = make_catalog()
        self.assertEqual(analysis.ducat_value(cat["sets"]["akstiletto_prime_set"]), 15 * (1 + 2 + 2 + 1))
        self.assertEqual(analysis.ducat_value(cat["sets"]["mirage_prime_set"]), 60)

    def test_ducats_per_platinum(self):
        self.assertEqual(analysis.ducats_per_platinum(300, 20), 15)
        self.assertAlmostEqual(analysis.ducats_per_platinum(175, 14), 12.5)
        for ducats, price in ((300, None), (300, 0), (None, 20), (0, 20)):
            self.assertIsNone(analysis.ducats_per_platinum(ducats, price))

    def test_the_list_shows_remembered_prices_and_asks_the_market_nothing(self):
        from types import SimpleNamespace
        from primesets import server
        cat = make_catalog()
        for st in cat["sets"].values():
            st["vault"] = {"state": "vaulted", "vaulted_parts": len(st["parts"]), "total_parts": len(st["parts"])}
        remembered = {"mirage_prime_set": ({"sell": [{"platinum": 9, "status": "online"}, {"platinum": 12, "status": "ingame"}],
                                           "buy": []}, 1700000000.0)}
        state = SimpleNamespace(catalog=cat, wfm=SimpleNamespace(top_orders_cached=remembered.get))
        rows = {r["slug"]: r for r in server.ducat_sets(state)["sets"]}
        self.assertEqual(set(rows), set(cat["sets"]), "every set of the catalog, owned or not")
        mirage = rows["mirage_prime_set"]
        self.assertEqual((mirage["ducats"], mirage["price"]["value"], mirage["orders_at"]), (60, 12, 1700000000.0),
                         "the seller who is in the game sets the price, as everywhere else in the app")
        self.assertEqual([(p["label"], p["quantity"], p["ducats"]) for p in rows["akstiletto_prime_set"]["parts"]][1],
                         ("Акстилетто Прайм: Ствол", 2, 15))
        self.assertIsNone(rows["vasto_prime_set"]["price"])
        self.assertEqual(mirage["vault"]["label"], "Да")

    # -- the purchase calculator --
    def test_offers_are_only_the_sellers_who_are_in_the_game(self):
        top = {"sell": [{"platinum": 9, "status": "online", "user": "A", "quantity": 1},
                        {"platinum": 12, "status": "ingame", "user": "B", "quantity": 3, "reputation": 5},
                        {"platinum": 10, "status": "ingame", "user": "C"},
                        {"platinum": 0, "status": "ingame", "user": "D"},
                        {"platinum": 7, "status": "ingame", "user": ""}], "buy": []}
        self.assertEqual([(o["user"], o["platinum"], o["quantity"]) for o in analysis.offers_from_orders(top)],
                         [("C", 10, 1), ("B", 12, 3)])

    def test_the_plan_is_the_cheapest_way_to_the_target_not_just_the_best_rates(self):
        offers = [{"ducats": 300, "platinum": 20, "quantity": 1},     # 15 ducats per platinum
                  {"ducats": 350, "platinum": 30, "quantity": 2},     # 11.7
                  {"ducats": 60, "platinum": 8, "quantity": 5}]       # 7.5: a poor rate, but it closes a small gap cheaply
        plan = analysis.plan_ducats(offers, 350)
        self.assertEqual((plan["platinum"], plan["ducats"], plan["reached"]), (28, 360, True),
                         "300 + 60 for 28 beats 350 for 30 and 300 + 350 for 50")
        self.assertEqual(plan["picks"], [{"index": 0, "count": 1}, {"index": 2, "count": 1}])

    def test_the_plan_respects_how_many_sets_a_seller_has(self):
        offers = [{"ducats": 100, "platinum": 5, "quantity": 2}, {"ducats": 100, "platinum": 9, "quantity": 10}]
        plan = analysis.plan_ducats(offers, 500)
        self.assertEqual(plan["picks"], [{"index": 0, "count": 2}, {"index": 1, "count": 3}])
        self.assertEqual((plan["platinum"], plan["ducats"]), (37, 500))

    def test_fewer_purchases_win_a_tie(self):
        offers = [{"ducats": 100, "platinum": 10, "quantity": 2}, {"ducats": 200, "platinum": 20, "quantity": 1}]
        self.assertEqual(analysis.plan_ducats(offers, 200)["picks"], [{"index": 1, "count": 1}])

    def test_not_enough_on_offer(self):
        plan = analysis.plan_ducats([{"ducats": 100, "platinum": 10, "quantity": 2}], 500)
        self.assertEqual((plan["ducats"], plan["platinum"], plan["reached"]), (200, 20, False))
        self.assertFalse(analysis.plan_ducats([], 500)["reached"])

    def test_the_plan_matches_an_exhaustive_search(self):
        import itertools
        import random
        rng = random.Random(11)
        for _ in range(80):
            offers = [{"ducats": rng.choice([55, 60, 90, 115, 150, 160, 205, 260, 350]), "platinum": rng.randint(4, 40),
                       "quantity": rng.randint(1, 3)} for _ in range(rng.randint(2, 6))]
            target = rng.choice([100, 250, 400, 700])
            best = None
            for counts in itertools.product(*[range(o["quantity"] + 1) for o in offers]):
                if sum(c * o["ducats"] for c, o in zip(counts, offers)) >= target:
                    cost = sum(c * o["platinum"] for c, o in zip(counts, offers))
                    best = cost if best is None else min(best, cost)
            plan = analysis.plan_ducats(offers, target)
            bought = sum(p["count"] * offers[p["index"]]["ducats"] for p in plan["picks"])
            paid = sum(p["count"] * offers[p["index"]]["platinum"] for p in plan["picks"])
            self.assertEqual((plan["ducats"], plan["platinum"]), (bought, paid), "the totals describe the picks")
            self.assertTrue(all(p["count"] <= offers[p["index"]]["quantity"] for p in plan["picks"]))
            if best is None:
                self.assertFalse(plan["reached"])
            else:
                self.assertEqual((plan["platinum"], plan["reached"]), (best, True), (offers, target))

    def test_a_large_market_is_planned_as_well_as_by_trying_every_offer(self):
        # the planner looks only at the offers that can matter; a plain search over all of them must not do better
        import random
        rng = random.Random(5)
        for target in (300, 1000, 3000):
            offers = [{"ducats": rng.choice([55, 60, 75, 90, 110, 115, 150, 160, 175, 205, 220, 260, 275, 305, 350]),
                       "platinum": rng.randint(6, 80), "quantity": rng.randint(1, 6)} for _ in range(400)]
            best = {0: 0}
            for o in offers:
                for _ in range(min(o["quantity"], 20, -(-target // o["ducats"]))):
                    new = dict(best)
                    for ducats, cost in best.items():
                        reach, pay = min(target, ducats + o["ducats"]), cost + o["platinum"]
                        if pay < new.get(reach, 10 ** 9):
                            new[reach] = pay
                    best = new
            self.assertEqual(analysis.plan_ducats(offers, target)["platinum"], best[target], target)

    def test_the_shopping_list_names_the_seller_and_the_message_to_send(self):
        from types import SimpleNamespace
        from primesets import server
        cat = make_catalog()
        remembered = {
            "mirage_prime_set": ({"sell": [{"platinum": 6, "status": "ingame", "user": "Alice", "quantity": 2},
                                           {"platinum": 4, "status": "online", "user": "NotInGame"}], "buy": []}, 1700000000.0),
            "vasto_prime_set": ({"sell": [{"platinum": 10, "status": "ingame", "user": "Bob", "quantity": 1}], "buy": []},
                                1700000100.0)}
        state = SimpleNamespace(catalog=cat, wfm=SimpleNamespace(top_orders_cached=remembered.get))
        plan = server.ducat_plan(state, 100)
        self.assertEqual((plan["platinum"], plan["ducats"], plan["reached"], plan["priced"]), (12, 120, True, 2))
        self.assertEqual([(s["user"], s["title"], s["count"], s["cost"], s["gain"]) for s in plan["steps"]],
                         [("Alice", "Мираж Прайм", 2, 12, 120)])
        self.assertEqual(plan["steps"][0]["message"],
                         '/w Alice Hi! I want to buy: "Mirage Prime Set" x2 for 6 platinum each. (warframe.market)')
        self.assertEqual(plan["oldest_at"], 1700000000.0)
        # the seller does not answer: plan again without that offer
        plan = server.ducat_plan(state, 100, ["mirage_prime_set|Alice"])
        self.assertEqual([(s["user"], s["count"]) for s in plan["steps"]], [("Bob", 1)])
        self.assertEqual((plan["ducats"], plan["reached"]), (45, False))
        self.assertEqual(plan["steps"][0]["message"],
                         '/w Bob Hi! I want to buy: "Vasto Prime Set" for 10 platinum. (warframe.market)')


class History(unittest.TestCase):
    """What each update changed (history.py)."""

    def setUp(self):
        import shutil
        from primesets import history
        self.history = history
        self.cat = make_catalog()
        for f in (inventory.config.INVENTORY_FILE, history.HISTORY_FILE, history.VALUES_FILE):
            if f.exists():
                f.unlink()
        shutil.rmtree(inventory.config.BACKUP_DIR, ignore_errors=True)

    def parts(self, **counts):
        names = {"barrel": "Акстилетто Прайм: Ствол", "receiver": "Акстилетто Прайм: Приёмник",
                 "link": "Акстилетто Прайм: Связь", "blueprint": "Чертёж: Акстилетто Прайм", "vasto": "Васто Прайм: Ствол"}
        return [{"name": names[k], "count": n, "blueprint": k == "blueprint"} for k, n in counts.items()]

    def test_an_import_is_remembered_with_what_it_changed(self):
        inventory.import_entries(self.parts(barrel=2, receiver=1, vasto=3), self.cat, note="первый")
        inventory.import_entries(self.parts(barrel=2, receiver=2, link=1, blueprint=1), self.cat, note="второй")
        new, old = self.history.updates(self.cat, inventory.load())
        self.assertEqual((old["first"], old["note"], old["distinct"], old["total"], old["complete"]), (True, "первый", 3, 6, 0))
        self.assertEqual((new["first"], new["note"], new["mode"]), (False, "второй", "replace"))
        self.assertEqual([(r["item"], r["count"]) for r in new["added"]],
                         [("Акстилетто Прайм (Чертеж)", 1), ("Акстилетто Прайм: Связь", 1)])
        self.assertEqual([(r["item"], r["count"]) for r in new["removed"]], [("Васто Прайм: Ствол", 3)])
        self.assertEqual([(r["item"], r["old"], r["new"]) for r in new["changed"]], [("Акстилетто Прайм: Приёмник", 1, 2)])
        self.assertEqual(new["sets_up"], [{"slug": "akstiletto_prime_set", "title": "Акстилетто Прайм", "old": 0, "new": 1}])
        self.assertEqual((new["complete_before"], new["complete"], new["total_before"], new["total"]), (0, 1, 6, 6))

    def test_an_update_that_changes_nothing_is_not_an_update(self):
        inventory.import_entries(self.parts(barrel=2), self.cat)
        inventory.import_entries(self.parts(barrel=2), self.cat)
        self.assertEqual(len(self.history.updates(self.cat, inventory.load())), 1)

    def test_edits_by_hand_are_one_update(self):
        inventory.import_entries(self.parts(barrel=2, receiver=2, link=1, blueprint=1), self.cat)
        inventory.set_count("akstiletto_prime_link", 0, self.cat)
        inventory.set_count("akstiletto_prime_barrel", 5, self.cat)
        new, old = self.history.updates(self.cat, inventory.load())
        self.assertEqual((new["source"], [r["item"] for r in new["removed"]], [(r["old"], r["new"]) for r in new["changed"]]),
                         ("manual", ["Акстилетто Прайм: Связь"], [(2, 5)]))
        self.assertEqual(new["sets_down"], [{"slug": "akstiletto_prime_set", "title": "Акстилетто Прайм", "old": 1, "new": 0}])
        # ...and putting everything back leaves no trace of them
        inventory.set_count("akstiletto_prime_link", 1, self.cat)
        inventory.set_count("akstiletto_prime_barrel", 2, self.cat)
        self.assertEqual(len(self.history.updates(self.cat, inventory.load())), 1)

    def test_the_past_is_rebuilt_from_the_backup_copies(self):
        # two imports made before the history existed: only the backups and the inventory itself are left
        inventory.import_entries(self.parts(barrel=1), self.cat, note="раз")
        time.sleep(1.1)
        inventory.import_entries(self.parts(barrel=1, vasto=2), self.cat, note="два")
        time.sleep(1.1)
        inventory.import_entries(self.parts(vasto=2), self.cat, note="три")
        self.history.HISTORY_FILE.unlink()
        got = self.history.updates(self.cat, inventory.load())
        self.assertEqual([(u["note"], u["total"]) for u in got], [("три", 2), ("два", 3), ("раз", 1)])
        self.assertEqual([r["item"] for r in got[0]["removed"]], ["Акстилетто Прайм: Ствол"])
        self.assertTrue(got[-1]["first"])

    def test_a_change_made_past_the_app_is_noticed(self):
        import json
        inventory.import_entries(self.parts(barrel=1), self.cat)
        box = json.loads(inventory.config.INVENTORY_FILE.read_text(encoding="utf-8"))
        box["items"]["vasto_prime_barrel"] = 4
        inventory.config.INVENTORY_FILE.write_text(json.dumps(box), encoding="utf-8")
        got = self.history.updates(self.cat, inventory.load())
        self.assertEqual((len(got), [(r["item"], r["count"]) for r in got[0]["added"]]), (2, [("Васто Прайм: Ствол", 4)]))

    def test_the_value_of_a_day_is_the_last_one_reported(self):
        self.history.record_value(700.4, 20, 25, 20)
        rec = self.history.record_value(754, 23, 29, 23)
        self.assertEqual((rec["value"], rec["sets"], rec["copies"]), (754, 23, 29))
        days_ = self.history.values()
        self.assertEqual((len(days_), days_[0]["value"], days_[0]["date"]), (1, 754, time.strftime("%Y-%m-%d")))


def days(prices, start="2026-08-20", volume=10):
    from datetime import date, timedelta
    y, m, d = map(int, start.split("-"))
    first = date(y, m, d)
    return [{"date": (first + timedelta(days=i)).isoformat(), "median": p, "volume": volume}
            for i, p in enumerate(prices) if p is not None]


class Trend(unittest.TestCase):
    def test_falling(self):
        t = analysis.trend_from_days(days([100] * 30 + [80] * 30 + [70] * 30))
        self.assertEqual(t["direction"], "down")
        self.assertAlmostEqual(t["change"], -0.30, places=2)
        self.assertEqual((t["start_price"], t["end_price"], t["window_days"]), (100.0, 70.0, 14))

    def test_rising_and_flat(self):
        self.assertEqual(analysis.trend_from_days(days([50] * 45 + [60] * 45))["direction"], "up")
        self.assertEqual(analysis.trend_from_days(days([50] * 45 + [53] * 45))["direction"], "flat")

    def test_volume_weighting(self):
        rows = days([100] * 90)
        rows[-1]["median"], rows[-1]["volume"] = 1, 1          # one odd cheap deal must not move the result
        for r in rows[-14:-1]:
            r["volume"] = 100
        t = analysis.trend_from_days(rows)
        self.assertEqual(t["direction"], "flat")

    def test_too_little_data(self):
        self.assertEqual(analysis.trend_from_days([])["direction"], "unknown")
        self.assertEqual(analysis.trend_from_days(days([10, 11, 12]))["direction"], "unknown")

    def test_sparse_history_widens_the_windows(self):
        prices = [None] * 90
        for i in (0, 9, 18, 27, 62, 71, 80, 89):
            prices[i] = 100 if i < 45 else 60
        t = analysis.trend_from_days(days(prices))
        self.assertEqual(t["direction"], "down")
        # 14 days hold only two trading days on each side, 21 days hold three
        self.assertEqual(t["window_days"], 21)
        self.assertEqual((t["start_price"], t["end_price"]), (100.0, 60.0))


DROP_HTML = """<html><body><p><b>Last Update:</b>
22 October, 2026
<h3 id="missionRewards">Missions:</h3>
<table><tr><th colspan="2">Earth/Test (Survival)</th></tr><tr><th colspan="2">Rotation A</th></tr>
<tr><td>Lith A1 Relic</td><td>Rare (7.69%)</td></tr><tr><td>100 Endo</td><td>Common (50.00%)</td></tr></table>
<h3 id="relicRewards">Relics:</h3>
<table>
<tr><th colspan="2">Lith A1 Relic (Intact)</th></tr><tr><td>Akstiletto Prime Barrel</td><td>Uncommon (11.00%)</td></tr><tr><td>Forma Blueprint</td><td>Common (25.33%)</td></tr>
<tr class="blank-row"><td class="blank-row" colspan="2"></td></tr>
<tr><th colspan="2">Lith A1 Relic (Radiant)</th></tr><tr><td>Akstiletto Prime Barrel</td><td>Uncommon (20.00%)</td></tr>
<tr class="blank-row"><td class="blank-row" colspan="2"></td></tr>
<tr><th colspan="2">Axi V8 Relic (Intact)</th></tr><tr><td>Vasto Prime Barrel</td><td>Rare (2.00%)</td></tr>
PADDING
</table>
<h3 id="transientRewards">Dynamic Location Rewards:</h3>
<table><tr><td>Neo Z9 Relic (Radiant)</td><td>Rare (2.00%)</td></tr></table>
</body></html>"""


class DropTables(unittest.TestCase):
    def test_parse(self):
        # the real page holds hundreds of relics; pad the sample so the sanity check passes
        pad = "".join(f'<tr><th colspan="2">Meso P{i} Relic (Intact)</th></tr><tr><td>Forma Blueprint</td><td>Common (25.33%)</td></tr>'
                      for i in range(120))
        data = droptables.parse(DROP_HTML.replace("PADDING", pad))
        self.assertEqual(data["updated"], "22 October, 2026")
        self.assertEqual([r["item"] for r in data["relics"]["Lith A1"]], ["Akstiletto Prime Barrel", "Forma Blueprint"])
        self.assertEqual(data["relics"]["Lith A1"][0]["chance"], 11.0, "chances come from the Intact table only")
        self.assertEqual(data["active"], ["Lith A1"], "Axi V8 never drops; Neo Z9 is not in the relic table")

    def test_broken_page_is_rejected(self):
        with self.assertRaises(ValueError):
            droptables.parse("<html><h3 id=\"relicRewards\">Relics:</h3></html>")


class VaultState(unittest.TestCase):
    def test_states(self):
        def p(av):
            return {"availability": av}
        self.assertEqual(catalog._vault_state([p("vaulted"), p("vaulted")])["state"], "vaulted")
        self.assertEqual(catalog._vault_state([p("missions"), p("special")])["state"], "available")
        self.assertEqual(catalog._vault_state([p("special"), p("special")])["state"], "special")
        self.assertEqual(catalog._vault_state([p("missions"), p("vaulted")])["state"], "partial")
        self.assertEqual(catalog._vault_state([p("unknown")])["state"], "unknown")

    def test_relic_availability(self):
        self.assertEqual(catalog._availability([{"drops": False, "wfm_vaulted": True}]), "vaulted")
        self.assertEqual(catalog._availability([{"drops": False, "wfm_vaulted": True}, {"drops": True, "wfm_vaulted": True}]), "missions")
        self.assertEqual(catalog._availability([{"drops": False, "wfm_vaulted": False}]), "special")
        self.assertEqual(catalog._availability([]), "unknown")

    def test_labels(self):
        self.assertEqual(catalog.part_label("Мираж Прайм: Система (Чертеж)", "Мираж Прайм", "ru"), "Система (чертёж)")
        self.assertEqual(catalog.part_label("Мираж Прайм (Чертеж)", "Мираж Прайм", "ru"), "Чертёж")
        self.assertEqual(catalog.part_label("Орнамент: Типедо Прайм", "Типедо Прайм", "ru"), "Орнамент")
        self.assertEqual(catalog.part_label("Каваса Прайм: Лента", "Ошейник Кубрау: Каваса Прайм", "ru"), "Лента")


class ImportFlow(unittest.TestCase):
    def setUp(self):
        self.cat = make_catalog()
        for f in (inventory.config.INVENTORY_FILE, mastery.MASTERY_FILE):
            if f.exists():
                f.unlink()

    def test_overlapping_screenshots_count_once_and_conflicts_are_reported(self):
        rep = inventory.import_entries([
            {"name": "Акстилетто Прайм: Ствол", "count": 2, "blueprint": False, "shot": "a"},
            {"name": "Акстилетто Прайм: Ствол", "count": 2, "blueprint": False, "shot": "b"},
            {"name": "Акстилетто Прайм: Связь", "count": 1, "blueprint": False, "shot": "a"},
            {"name": "Акстилетто Прайм: Связь", "count": 3, "blueprint": False, "shot": "b"},
            {"name": "Мираж Прайм", "count": 1, "blueprint": False},
        ], self.cat)
        inv = inventory.load()
        self.assertEqual(inv["items"], {"akstiletto_prime_barrel": 2, "akstiletto_prime_link": 3})
        self.assertEqual([c["slug"] for c in rep["conflicts"]], ["akstiletto_prime_link"])
        self.assertEqual([s["status"] for s in rep["skipped"]], ["built"])

    def test_foundry_blueprint_without_number_keeps_known_count(self):
        inventory.import_entries([{"name": "Чертёж: Мираж Прайм", "count": 3, "blueprint": True}], self.cat)
        inventory.import_entries([{"name": "Мираж Прайм", "count": 1, "blueprint": True, "count_known": False}],
                                 self.cat, mode="merge")
        self.assertEqual(inventory.load()["items"]["mirage_prime_blueprint"], 3)
        inventory.import_entries([{"name": "Васто Прайм", "count": 1, "blueprint": True, "count_known": False}],
                                 self.cat, mode="merge")
        self.assertEqual(inventory.load()["items"]["vasto_prime_blueprint"], 1)

    def test_replace_that_shrinks_the_inventory_is_refused(self):
        names = [p["name"] for st in self.cat["sets"].values() for p in st["parts"]][:12]
        inventory.import_entries([{"name": n, "count": 1} for n in names], self.cat)
        before = inventory.load()["items"]
        self.assertEqual(len(before), 12)
        rep = inventory.import_entries([{"name": names[0], "count": 1}], self.cat)
        self.assertTrue(rep["refused"])
        self.assertEqual(inventory.load()["items"], before, "nothing may be lost on a refused import")
        rep = inventory.import_entries([{"name": names[0], "count": 1}], self.cat, force=True)
        self.assertEqual(len(inventory.load()["items"]), 1)

    def test_merge_keeps_the_rest(self):
        inventory.import_entries([{"name": "Васто Прайм: Ствол", "count": 2, "blueprint": False}], self.cat)
        inventory.import_entries([{"name": "Васто Прайм: Приёмник", "count": 1, "blueprint": False}], self.cat, mode="merge")
        self.assertEqual(inventory.load()["items"], {"vasto_prime_barrel": 2, "vasto_prime_receiver": 1})

    def test_mastery_marks(self):
        rep = mastery.import_marks([
            {"name": "Мираж Прайм", "mastered": True},
            {"name": "Акстилетто Прайм", "mastered": False, "owned": True},
            {"name": "Васто Прайм", "mastered": False},
            {"name": "Ошейник Кубрау: Каваса Прайм", "mastered": False},
            {"name": "Неведомый Прайм", "mastered": True},
        ], self.cat)
        data = mastery.load()
        self.assertEqual({k: v["state"] for k, v in data["items"].items()},
                         {"mirage_prime_set": "mastered", "akstiletto_prime_set": "owned", "vasto_prime_set": "none"})
        self.assertEqual(len(rep["applied"]), 3)
        # mastery cannot be lost: a contradicting screenshot is reported, not applied
        rep = mastery.import_marks([{"name": "Мираж Прайм", "mastered": False}], self.cat)
        self.assertEqual(mastery.state_of(mastery.load(), "mirage_prime_set"), "mastered")
        self.assertEqual(rep["review"][0]["kind"], "mastery-downgrade")
        # one screenshot shows «Освоено», another does not: the explicit label wins, and the user is told
        rep = mastery.import_marks([{"name": "Васто Прайм", "mastered": True}, {"name": "Васто Прайм", "mastered": False}], self.cat)
        self.assertEqual(mastery.state_of(mastery.load(), "vasto_prime_set"), "mastered")
        self.assertEqual([r["kind"] for r in rep["review"]], ["mastery-conflict"])
        # marks from screenshots can be dropped as a whole; manual ones stay
        mastery.set_state("akvasto_prime_set", "mastered", self.cat)
        self.assertEqual(mastery.forget_source("screenshots"), 3)
        self.assertEqual(list(mastery.load()["items"]), ["akvasto_prime_set"])

    def test_dismissed_unknown_name_is_not_reported_again(self):
        entries = [{"name": "Аскарида Прайм", "count": 75, "blueprint": False},
                   {"name": "Васто Прайм: Ствол", "count": 1, "blueprint": False}]
        rep = inventory.import_entries(entries, self.cat)
        self.assertEqual([r["kind"] for r in rep["review"]], ["unmatched"])
        inventory.dismiss_review(0)
        rep = inventory.import_entries(entries, self.cat)
        self.assertEqual(rep["review"], [])
        self.assertEqual(inventory.load()["items"], {"vasto_prime_barrel": 1})
        inventory.IGNORED_FILE.unlink()

    def test_foundry_number_never_beats_the_inventory(self):
        # while an item is being built the foundry counts one blueprint too many
        rep = inventory.import_entries([
            {"name": "Чертёж: Васто Прайм", "count": 3, "blueprint": True, "shot": "inv"},
            {"name": "ВАСТО ПРАЙМ", "count": 4, "blueprint": True, "count_known": False, "shot": "foundry"},
            {"name": "АКВАСТО ПРАЙМ", "count": 2, "blueprint": True, "count_known": False, "shot": "foundry"}], self.cat)
        self.assertEqual(inventory.load()["items"], {"vasto_prime_blueprint": 3, "akvasto_prime_blueprint": 2})
        self.assertEqual(rep["conflicts"], [])

    def test_manual_edit(self):
        inventory.set_count("vasto_prime_barrel", 4, self.cat)
        self.assertEqual(inventory.load()["items"], {"vasto_prime_barrel": 4})
        inventory.set_count("vasto_prime_barrel", 0, self.cat)
        self.assertEqual(inventory.load()["items"], {})
        with self.assertRaises(ValueError):
            inventory.set_count("not_a_part", 1, self.cat)


class Tiling(unittest.TestCase):
    def test_spans_cover_everything_with_overlap(self):
        self.assertEqual(shots.spans(1440), [(0, 1440)])
        self.assertEqual(shots.spans(2560), [(0, 1500), (1060, 2560)])
        for total in (1920, 2560, 3440, 3840, 5120):
            sp = shots.spans(total)
            self.assertEqual((sp[0][0], sp[-1][1]), (0, total))
            self.assertTrue(all(b - a <= shots.MAX_SIDE for a, b in sp))
            self.assertTrue(all(prev[1] - nxt[0] >= shots.MIN_OVERLAP for prev, nxt in zip(sp, sp[1:])), sp)


class Recognition(unittest.TestCase):
    """The whole in-app path with a stand-in for the Claude Code CLI (tests/fake_claude.py)."""

    def setUp(self):
        self.cat = make_catalog()
        for f in (inventory.config.INVENTORY_FILE, mastery.MASTERY_FILE):
            if f.exists():
                f.unlink()
        self.inbox = shots.config.SCREENSHOT_DIR
        if self.inbox.exists():
            import shutil
            shutil.rmtree(self.inbox)
        self.inbox.mkdir(parents=True)
        os.environ["PRIMESETS_CLAUDE_CMD"] = __import__("json").dumps(FAKE_CLAUDE)
        os.environ["FAKE_RECOGNIZE_MODE"] = "ok"
        providers.get("claude_cli").forget_status()
        self.data_file = Path(_TMP.name) / "fake_data.json"
        os.environ["FAKE_RECOGNIZE_DATA"] = str(self.data_file)
        os.environ["ANTHROPIC_API_KEY"] = "must-not-reach-the-child"

    def tearDown(self):
        for key in ("PRIMESETS_CLAUDE_CMD", "FAKE_RECOGNIZE_MODE", "FAKE_RECOGNIZE_DATA", "ANTHROPIC_API_KEY"):
            os.environ.pop(key, None)

    @staticmethod
    def tiny_png() -> bytes:
        """A valid 2x2 PNG built by hand, so the tests need no imaging library."""
        import struct
        import zlib

        def chunk(tag, data):
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        rows = b"".join(b"\x00" + b"\x10\x20\x30" * 2 for _ in range(2))
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))

    def shot(self, name):
        path = self.inbox / name
        path.write_bytes(self.tiny_png())
        return path

    def test_broken_picture_is_reported_not_fatal(self):
        self.shot("good.png")
        (self.inbox / "broken.png").write_bytes(b"this is not a picture")
        self.answers({"*": {"screen": "inventory", "notes": "", "items": [self.tile("Васто Прайм: Ствол")]}})
        snap = self.run_job().snapshot()
        self.assertEqual(snap["state"], "review")
        states = {f["name"]: f["state"] for f in snap["files"]}
        if shots.have_pillow():
            self.assertEqual(states, {"broken.png": "error", "good.png": "done"})

    def answers(self, mapping):
        import json
        self.data_file.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")

    def run_job(self):
        job = recognize.Job(shots.originals(), self.cat)
        job.run()
        return job

    def test_status(self):
        self.assertEqual(claude_cli.find(), FAKE_CLAUDE)
        claude = providers.get("claude_cli")
        st = claude.status(force=True)
        self.assertTrue(st["available"] and st["logged_in"] and st["ready"])
        os.environ["FAKE_RECOGNIZE_MODE"] = "not_logged_in"
        st = claude.status(force=True)
        self.assertEqual((st["logged_in"], st["ready"], st["reason"]), (False, False, "login"))

    @staticmethod
    def tile(name, count=None, bp=False, rank=None):
        """An inventory tile as the model reports it."""
        return {"name": name, "rank": rank, "count": count or 1, "count_visible": count is not None,
                "blueprint_word": bp, "mastered_label": None, "owned_label": None}

    @staticmethod
    def card(name, left=None, mastered=None, owned=None):
        """A foundry card as the model reports it."""
        return {"name": name, "rank": None, "count": left or 1, "count_visible": left is not None,
                "blueprint_word": False, "mastered_label": mastered, "owned_label": owned}

    def test_full_run_review_and_apply(self):
        self.shot("inv_1.png")
        self.shot("kuznitsa_1.png")
        self.answers({
            "inv_1": {"screen": "inventory", "notes": "", "items": [
                self.tile("Акстилетто Прайм: Ствол", 2),
                self.tile("Акстилетто Прайм: Приёмник", 2),
                self.tile("Акстилетто Прайм: Связь"),
                self.tile("Чертёж: Акстилетто Прайм", bp=True),
                self.tile("Чертёж: Мираж Прайм: Система", 3, bp=True),
                self.tile("Мираж Прайм: Каркас"),                 # a built component: not for sale
                self.tile("Васто Прайм", rank=30),                # a built weapon at the top rank
                self.tile("Чистильщик Прайм", rank=30),           # a sentinel weapon: not a set at all
                self.tile("Зюзя Прайм: Хвост")]},
            "kuznitsa_1": {"screen": "foundry", "notes": "нижний ряд не читается", "items": [
                self.card("АКСТИЛЕТТО ПРАЙМ", left=1, mastered=False, owned=False),
                self.card("МИРАЖ ПРАЙМ", left=2, mastered=True, owned=True),
                # the label on a component card says nothing about the warframe itself
                self.card("МИРАЖ ПРАЙМ: СИСТЕМА", left=3, mastered=False, owned=True)]},
        })
        job = self.run_job()
        snap = job.snapshot()
        self.assertEqual(snap["state"], "review", snap)
        self.assertEqual([f["state"] for f in snap["files"]], ["done", "done"])
        self.assertEqual(snap["notes"], ["kuznitsa_1.png: нижний ряд не читается"])
        rep = snap["reports"]["replace"]
        self.assertEqual(rep["distinct_parts"], 6)
        self.assertEqual([r["kind"] for r in rep["review"]], ["unmatched"])
        self.assertEqual([x["name"] for x in rep["skipped"]], ["Мираж Прайм: Каркас"])
        self.assertEqual(snap["suggested"], "replace", "an empty inventory plus an inventory screen: full snapshot")
        self.assertEqual(inventory.load()["items"], {}, "nothing is written before the user confirms")
        self.assertTrue(recognize.PENDING_FILE.exists(), "a finished reading is kept on disk")

        # the app is closed and started again: the reading is still there
        again = recognize.restore_pending(self.cat)
        self.assertEqual(again.snapshot()["reports"]["replace"]["distinct_parts"], 6)

        result = again.apply("replace")
        inv = inventory.load()
        self.assertEqual(inv["items"], {"akstiletto_prime_barrel": 2, "akstiletto_prime_receiver": 2,
                                        "akstiletto_prime_link": 1, "akstiletto_prime_blueprint": 1,
                                        "mirage_prime_blueprint": 2, "mirage_prime_systems_blueprint": 3})
        marks = {k: v["state"] for k, v in mastery.load()["items"].items()}
        self.assertEqual(marks, {"akstiletto_prime_set": "none", "mirage_prime_set": "mastered",
                                 "vasto_prime_set": "mastered"})
        self.assertEqual(shots.originals(), [], "processed screenshots leave the inbox")
        self.assertEqual(len(list(Path(result["archived_to"]).iterdir())), 2, "...but are kept in _done")
        self.assertTrue(list((inventory.config.DATA_DIR / "imports").glob("recognized-*.json")))
        self.assertFalse(recognize.PENDING_FILE.exists())
        self.assertIsNone(recognize.restore_pending(self.cat))
        self.assertEqual(analysis.split_inventory(self.cat, inv["items"])["complete"][0]["slug"], "akstiletto_prime_set")

    def test_foundry_count_is_the_blueprints_left_line(self):
        combined = recognize.combine([{"shot": "k.png", "screen": "foundry", "notes": "", "items": [
            self.card("МИРАЖ ПРАЙМ: КАРКАС", left=4, owned=True),
            self.card("МИРАЖ ПРАЙМ: НЕЙРООПТИКА")]}], self.cat)
        # the number is kept, but only as "at least": the inventory has the last word on counts
        self.assertEqual([(p["name"], p["count"], p["blueprint"], p["count_known"]) for p in combined["parts"]],
                         [("МИРАЖ ПРАЙМ: КАРКАС", 4, True, False), ("МИРАЖ ПРАЙМ: НЕЙРООПТИКА", 1, True, False)])
        self.assertEqual(combined["mastery"], [], "component cards give no mastery marks")

    def test_hidden_label_is_unknown_not_absent(self):
        self.shot("kuznitsa.png")
        self.answers({"*": {"screen": "foundry", "notes": "", "items": [
            self.card("МИРАЖ ПРАЙМ", left=1, mastered=True, owned=True),      # proves the screen shows labels
            self.card("ВАСТО ПРАЙМ", left=1, mastered=None, owned=None),       # covered by the character
            self.card("АКВАСТО ПРАЙМ", left=1, mastered=None, owned=True),     # one label seen, the rest covered
            self.card("АКСТИЛЕТТО ПРАЙМ", left=1, mastered=False, owned=False)]}})
        job = self.run_job()
        job.apply("merge")
        marks = {k: v["state"] for k, v in mastery.load()["items"].items()}
        self.assertEqual(marks, {"mirage_prime_set": "mastered", "akvasto_prime_set": "owned",
                                 "akstiletto_prime_set": "none"})

    def test_not_mastered_needs_proof_that_the_screen_shows_labels(self):
        self.shot("kuznitsa.png")
        self.answers({"*": {"screen": "foundry", "notes": "", "items": [
            self.card("ВАСТО ПРАЙМ", left=1, mastered=False, owned=False),
            self.card("МИРАЖ ПРАЙМ", left=1, mastered=False, owned=True)]}})
        job = self.run_job()
        snap = job.snapshot()
        self.assertEqual(snap["dropped_negative_marks"], 2)
        job.apply("merge")
        marks = {k: v["state"] for k, v in mastery.load()["items"].items()}
        self.assertEqual(marks, {"mirage_prime_set": "owned"},
                         "no label seen anywhere: a missing one proves nothing, a visible one still counts")

    def test_rank_in_the_inventory(self):
        combined = recognize.combine([{"shot": "a.png", "screen": "inventory", "notes": "", "items": [
            self.tile("Васто Прайм", rank=30),
            self.tile("Мираж Прайм [12]"),                        # the rank left inside the caption
            self.tile("Чертёж: Васто Прайм", 2, bp=True)]}], self.cat)
        self.assertEqual([(m["name"], m["mastered"], m["owned"]) for m in combined["mastery"]],
                         [("Васто Прайм", True, True), ("Мираж Прайм", None, True)])
        self.assertEqual([p["name"] for p in combined["parts"]], ["Чертёж: Васто Прайм"])
        rep = mastery.import_marks(combined["mastery"], self.cat)
        self.assertEqual({x["slug"]: x["state"] for x in rep["applied"]},
                         {"vasto_prime_set": "mastered", "mirage_prime_set": "owned"})
        # a later screenshot with a low rank (the weapon was reset by forma) does not undo mastery
        rep = mastery.import_marks([{"name": "Васто Прайм", "mastered": None, "owned": True}], self.cat)
        self.assertEqual(mastery.state_of(mastery.load(), "vasto_prime_set"), "mastered")
        self.assertEqual(rep["review"], [])

    def test_count_without_a_number(self):
        combined = recognize.combine([
            {"shot": "a", "screen": "inventory", "notes": "", "items": [self.tile("Васто Прайм: Ствол")]},
            {"shot": "b", "screen": "other", "notes": "", "items": [self.tile("Васто Прайм: Приёмник")]},
        ], self.cat)
        known = {p["name"]: p["count_known"] for p in combined["parts"]}
        self.assertEqual(known, {"Васто Прайм: Ствол": True, "Васто Прайм: Приёмник": False})

    def test_a_tile_cut_at_the_top_hides_its_count(self):
        # the last page of the list: its first row has captions but no count badges
        cut = {**self.tile("Чертёж: Мираж Прайм: Система", bp=True), "cut_top": True}
        whole = self.tile("Чертёж: Мираж Прайм: Система", 3, bp=True)
        both = recognize.combine([
            {"shot": "p1.png", "screen": "inventory", "notes": "", "items": [whole]},
            {"shot": "p2.png", "screen": "inventory", "notes": "", "items": [cut]}], self.cat)
        self.assertEqual([(p["count"], p["count_known"]) for p in both["parts"]], [(3, True), (1, False)])
        rep = inventory.import_entries(both["parts"], self.cat, dry_run=True)
        self.assertEqual((rep["conflicts"], rep["review"]), ([], []), "the whole tile on the previous page decides")
        self.assertEqual(rep["total_parts"], 3)
        # no other screenshot shows the number: say so instead of silently writing "1"
        alone = recognize.combine([{"shot": "p2.png", "screen": "inventory", "notes": "", "items": [cut]}], self.cat)
        rep = inventory.import_entries(alone["parts"], self.cat, dry_run=True)
        self.assertEqual([(r["kind"], r["slug"], r["shot"]) for r in rep["review"]],
                         [("check", "mirage_prime_systems_blueprint", "p2.png")])

    @unittest.skipUnless(shots.have_pillow(), "the join check needs Pillow")
    def test_a_skipped_row_is_reported_and_the_whole_list_mode_is_not_offered(self):
        strip = draw_list(12)
        for name, offset in (("inv_a.png", 0), ("inv_b.png", 3 * ROW), ("inv_c.png", 7 * ROW)):
            draw_screen(strip, offset, glow=offset + 1).save(self.inbox / name)
        inventory.import_entries([{"name": "Васто Прайм: Ствол", "count": 2, "blueprint": False},
                                  {"name": "Акстилетто Прайм: Связь", "count": 1, "blueprint": False}], self.cat)
        self.answers({
            "inv_a": {"screen": "inventory", "notes": "", "items": [
                self.tile("Акстилетто Прайм: Ствол", 2), self.tile("Акстилетто Прайм: Приёмник")]},
            "inv_b": {"screen": "inventory", "notes": "", "items": [
                self.tile("Акстилетто Прайм: Связь"), self.tile("Чертёж: Акстилетто Прайм", bp=True)]},
            "inv_c": {"screen": "inventory", "notes": "", "items": [
                self.tile("Чертёж: Мираж Прайм: Система", 3, bp=True)]},
        })
        snap = self.run_job().snapshot()
        joins = snap["joins"]
        self.assertEqual((joins["state"], joins["pages"], joins["joined"]), ("gaps", 3, 1))
        self.assertEqual(joins["gaps"], [{"after": "inv_b.png", "before": "inv_c.png",
                                          "after_item": "Чертёж: Акстилетто Прайм",
                                          "before_item": "Чертёж: Мираж Прайм: Система"}])
        self.assertEqual(snap["suggested"], "merge", "a skipped row would make the whole-list mode drop its parts")
        self.assertEqual((joins["start"], joins["end"], joins["first"], joins["last"]), ("ok", "missing", "inv_a.png", "inv_c.png"))
        self.assertEqual((joins["first_item"], joins["last_item"]), ("Акстилетто Прайм: Ствол", "Чертёж: Мираж Прайм: Система"))
        self.assertEqual(snap["reports"]["replace"]["removed_list"], [{"item": "Васто Прайм: Ствол", "count": 2}])
        self.assertEqual(snap["reports"]["merge"]["removed_list"], [])
        # the verdict survives a restart together with the reading
        again = recognize.restore_pending(self.cat)
        self.assertEqual(again.snapshot()["joins"]["gaps"], joins["gaps"])
        self.assertEqual(again.snapshot()["suggested"], "merge")
        again.apply("merge")
        record = sorted((inventory.config.DATA_DIR / "imports").glob("recognized-*.json"))[-1]
        self.assertEqual(__import__("json").loads(record.read_text(encoding="utf-8"))["joins"]["state"], "gaps")
        self.assertEqual(inventory.load()["items"]["vasto_prime_barrel"], 2, "merge keeps what was not on the screenshots")

    @unittest.skipUnless(shots.have_pillow(), "the join check needs Pillow")
    def test_joined_screens_leave_the_whole_list_mode(self):
        rows = 12
        end = rows * ROW - 21 - (VIEW[1] - VIEW[0])
        strip = draw_list(rows)
        for name, offset in (("inv_a.png", 0), ("inv_b.png", 3 * ROW), ("inv_c.png", 6 * ROW), ("inv_d.png", end)):
            draw_screen(strip, offset, glow=offset + 1).save(self.inbox / name)
        inventory.import_entries([{"name": "Акстилетто Прайм: Связь", "count": 1, "blueprint": False}], self.cat)
        self.answers({"*": {"screen": "inventory", "notes": "", "items": [self.tile("Акстилетто Прайм: Связь", 2)]}})
        snap = self.run_job().snapshot()
        joins = snap["joins"]
        self.assertEqual((joins["state"], joins["start"], joins["end"]), ("ok", "ok", "ok"))
        self.assertEqual(snap["suggested"], "replace")

    @unittest.skipUnless(shots.have_pillow(), "the join check needs Pillow")
    def test_a_list_not_shot_to_its_end_does_not_get_the_whole_list_mode(self):
        strip = draw_list(12)
        for name, offset in (("inv_a.png", 0), ("inv_b.png", 3 * ROW)):
            draw_screen(strip, offset, glow=offset + 1).save(self.inbox / name)
        inventory.import_entries([{"name": "Акстилетто Прайм: Связь", "count": 1, "blueprint": False}], self.cat)
        self.answers({"*": {"screen": "inventory", "notes": "", "items": [self.tile("Акстилетто Прайм: Связь", 2)]}})
        snap = self.run_job().snapshot()
        joins = snap["joins"]
        self.assertEqual((joins["state"], joins["start"], joins["end"], joins["last"]), ("ok", "ok", "missing", "inv_b.png"))
        self.assertEqual(snap["suggested"], "merge", "the rows below the last screenshot were never read")

    def test_not_logged_in(self):
        self.shot("inv_1.png")
        self.shot("inv_2.png")
        os.environ["FAKE_RECOGNIZE_MODE"] = "not_logged_in"
        snap = self.run_job().snapshot()
        self.assertEqual((snap["state"], snap["error_code"]), ("error", "login"))
        self.assertEqual(len(shots.originals()), 2, "screenshots stay for the next try")

    def test_unreadable_answer(self):
        self.shot("inv_1.png")
        os.environ["FAKE_RECOGNIZE_MODE"] = "garbage"
        snap = self.run_job().snapshot()
        self.assertEqual((snap["state"], snap["error_code"]), ("error", "nothing"))

    def test_cancel(self):
        for i in range(4):
            self.shot(f"inv_{i}.png")
        os.environ["FAKE_RECOGNIZE_MODE"] = "slow"
        job = recognize.Job(shots.originals(), self.cat)
        thread = threading.Thread(target=job.run)
        thread.start()
        time.sleep(0.8)
        job.cancel()
        thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(job.snapshot()["state"], "cancelled")
        self.assertEqual(len(shots.originals()), 4)


class Limiter(unittest.TestCase):
    def test_parallel_callers_are_spaced_out(self):
        limiter = RateLimiter(0.12)
        starts = []

        def call():
            with limiter:
                starts.append(time.perf_counter())
                time.sleep(0.01)

        threads = [threading.Thread(target=call) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        starts.sort()
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        self.assertTrue(all(g >= 0.12 for g in gaps), gaps)


if __name__ == "__main__":
    unittest.main()
