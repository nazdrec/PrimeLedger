"""Paths and constants.

Two kinds of files are kept apart:
  * the program's own files (the page in web/) -- BUNDLE_DIR;
  * the user's files (inventory, settings, cache, screenshots) -- ROOT.
Run from the source they are the same folder.  The packed exe carries its own files inside
and keeps the user's files in %LOCALAPPDATA%\\<name of the app> -- or next to itself when a "data"
folder (or a file portable.txt) is found there, so the app can be carried on a stick.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME, HOMEPAGE, __version__

FROZEN = bool(getattr(sys, "frozen", False))
SOURCE_ROOT = Path(__file__).resolve().parent.parent
if FROZEN:
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
    EXE_DIR = Path(sys.executable).resolve().parent
    PORTABLE = (EXE_DIR / "data").is_dir() or (EXE_DIR / "portable.txt").is_file()
    ROOT = EXE_DIR if PORTABLE else Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / APP_NAME
else:
    BUNDLE_DIR = EXE_DIR = ROOT = SOURCE_ROOT
    PORTABLE = True
# PRIMESETS_DATA points the app at another folder for the inventory and mastery marks
# (used by the tests and for trying things out without touching the real list).
DATA_DIR = Path(os.environ["PRIMESETS_DATA"]).resolve() if os.environ.get("PRIMESETS_DATA") else ROOT / "data"
CACHE_DIR = ROOT / "data" / "cache"      # public market data only: always shared
BACKUP_DIR = DATA_DIR / "backups"
# PRIMESETS_SCREENSHOTS does the same for the screenshot inbox.
SCREENSHOT_DIR = (Path(os.environ["PRIMESETS_SCREENSHOTS"]).resolve() if os.environ.get("PRIMESETS_SCREENSHOTS")
                  else ROOT / "screenshots")
WEB_DIR = BUNDLE_DIR / "web"
INVENTORY_FILE = DATA_DIR / "inventory.json"

# --- warframe.market -------------------------------------------------------
WFM_API = "https://api.warframe.market"
WFM_SITE = "https://warframe.market"
WFM_ASSETS = "https://warframe.market/static/assets/"
# Terms of Service, section 11 "API": no more than 3 requests per second.
# We stay well below: one request at a time, at most 2 per second.
WFM_MIN_INTERVAL = 0.5
# Riven mods are sold on the site as "contracts" (auctions), and the same section gives them a limit
# of their own: no more than 10 requests per minute.  One request in 8 seconds stays below it.
WFM_CONTRACT_MIN_INTERVAL = 8.0
ASSET_MIN_INTERVAL = 0.25
PLATFORM = "pc"

# --- Digital Extremes ------------------------------------------------------
# Official, public drop tables page (redirects to DE's CDN).
DROPTABLES_URL = "https://www.warframe.com/droptables"

# No personal data in the User-Agent: the name of the program only.
USER_AGENT = (f"{APP_NAME}/{__version__} (open-source desktop app; " + (f"+{HOMEPAGE}; " if HOMEPAGE else "")
              + "python-urllib)")

# --- cache lifetimes, seconds ---------------------------------------------
TTL_ITEMS = 24 * 3600          # item list with names and relic flags
TTL_SET = 7 * 24 * 3600        # set composition changes only with new primes
TTL_DROPTABLES = 24 * 3600     # DE updates the page with game updates
TTL_TOP_ORDERS = 10 * 60       # live sell/buy orders
TTL_STATISTICS = 6 * 3600      # daily closed-deal statistics
TTL_CATALOG = 24 * 3600        # derived catalog (sets + vault status)
TTL_RIVEN_WEAPONS = 24 * 3600  # the weapons a riven mod can be for, with their names
TTL_RIVEN_OFFERS = 60 * 60     # the cheapest riven mods offered for a weapon: asked sparingly (see above)
TTL_RELIC_PRICES = 6 * 3600    # prices of what a relic holds: fresh enough to rank the relics by

# --- local server ----------------------------------------------------------
HOST = "127.0.0.1"
PORT = 47615
PORT_TRIES = 8                 # 47615..47622: the next one is tried when a port is taken
APP_ID = "warframe-prime-sets"

# --- analysis --------------------------------------------------------------
TREND_WINDOW_DAYS = 14         # first vs last N days of the 90-day history
TREND_THRESHOLD = 0.10         # |change| below 10 % counts as "stable"
