"""PrimeLedger (prime sets for Warframe) -- starts the local app.

    PrimeLedger.exe / pythonw app.py  the usual start: the app window
    python app.py --no-window         the server only (for checks), its address is printed

The app does not interact with the game.  It reads the list of parts the user gave it
(screenshots they made themself, manual input) and public data of warframe.market and of the
Digital Extremes drop tables.
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from primesets import APP_NAME, __version__, config, i18n, settings  # noqa: E402
from primesets.i18n import tr  # noqa: E402
from primesets.server import AppState, make_server  # noqa: E402

log = logging.getLogger("primesets")


def setup_logging(verbose: bool) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(config.DATA_DIR / "app.log", maxBytes=512_000, backupCount=1,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None and verbose:
        root.addHandler(logging.StreamHandler())


def message_box(text: str) -> None:
    """A windowed program has no console: show fatal errors in a dialog."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)
    except Exception:
        if sys.stderr is not None:
            print(text, file=sys.stderr)


def running_instance(port: int) -> bool:
    try:
        # never through a proxy: this is the app's own server on this computer
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://{config.HOST}:{port}/api/ping", timeout=1.5) as resp:
            return json.loads(resp.read().decode("utf-8")).get("app") == config.APP_ID
    except (urllib.error.URLError, OSError, ValueError):
        return False


def find_browser() -> Optional[str]:
    """A Chromium browser that can show the page as a standalone window (--app mode)."""
    candidates = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for path in candidates:
        if path.is_file():
            return str(path)
    return shutil.which("msedge") or shutil.which("chrome")


def open_window(url: str) -> str:
    browser = find_browser()
    if browser:
        try:
            subprocess.Popen([browser, f"--app={url}", "--window-size=1360,900"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             close_fds=True)
            return "app-window"
        except OSError:
            log.exception("could not start %s", browser)
    webbrowser.open(url)
    return "browser-tab"


def main() -> int:
    ap = argparse.ArgumentParser(description=f"{APP_NAME}: prime sets for Warframe")
    ap.add_argument("--no-window", action="store_true", help="do not open the window and do not exit when it closes")
    ap.add_argument("--port", type=int, default=None, help=f"the local port (default {config.PORT})")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    setup_logging(args.verbose)
    i18n.set_language(settings.language())
    ports = [args.port] if args.port else [config.PORT + n for n in range(config.PORT_TRIES)]

    for port in ports:
        if running_instance(port):
            # already running: just bring up another window on the same server
            if not args.no_window:
                open_window(f"http://{config.HOST}:{port}/")
            return 0

    for folder in (config.CACHE_DIR, config.BACKUP_DIR, config.SCREENSHOT_DIR):
        folder.mkdir(parents=True, exist_ok=True)

    state = AppState(auto_exit=not args.no_window)
    httpd, error = None, None
    for port in ports:
        try:
            httpd = make_server(state, port)
            break
        except OSError as exc:              # the port is taken by another program: try the next one
            error = exc
    if httpd is None:
        text = tr("Не удалось занять порт {0} на этом компьютере: {1}\n\nВозможно, порты заняты другой программой. "
                  "Запустите с другим портом: --port 47700", ports[0], error)
        log.error(text)
        message_box(text)
        return 1

    url = f"http://{config.HOST}:{httpd.server_address[1]}/"
    log.info("%s %s listening on %s (data: %s)", APP_NAME, __version__, url, config.DATA_DIR)
    threading.Thread(target=httpd.serve_forever, name="http", daemon=True).start()
    threading.Thread(target=state.watch, name="watch", daemon=True).start()
    state.ensure_catalog()

    if args.no_window:
        if sys.stdout is not None:
            print(f"Server: {url}  (Ctrl+C to stop)", flush=True)
    else:
        mode = open_window(url)
        log.info("window: %s", mode)

    try:
        while not state.stop_event.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    state.stop_event.set()
    httpd.shutdown()
    httpd.server_close()
    log.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
