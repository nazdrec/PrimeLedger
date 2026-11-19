"""Screenshots the user put into the app folder: listing, tiling, archiving.

Why tiles: the model sees a picture no wider than ~1568 px, larger ones are scaled
down and small inventory captions get harder to read.  Tiles keep the original
scale and overlap, so an item cut by the edge of one tile is whole on the next.
Originals are never modified.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .i18n import tr

EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
TILE_DIR = config.SCREENSHOT_DIR / "_tiles"
DONE_DIR = config.SCREENSHOT_DIR / "_done"
MAX_SIDE = 1500          # keeps a tile below the model's downscaling threshold
MIN_OVERLAP = 320        # wider than one inventory cell even at 4K


def have_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def originals() -> List[Path]:
    if not config.SCREENSHOT_DIR.is_dir():
        return []
    return sorted(f for f in config.SCREENSHOT_DIR.iterdir() if f.is_file() and f.suffix.lower() in EXT)


def find(name: str) -> Optional[Path]:
    """A screenshot by its file name -- only from the inbox folder itself, never a path."""
    for f in originals():
        if f.name == name:
            return f
    return None


def spans(total: int, max_side: int = MAX_SIDE, min_overlap: int = MIN_OVERLAP) -> List[Tuple[int, int]]:
    """Split [0, total) into the fewest equal windows of at most max_side with at least min_overlap overlap."""
    if total <= max_side:
        return [(0, total)]
    n = 2
    while True:
        size = min(max_side, total)
        step = (total - size) / (n - 1)
        if size - step >= min_overlap:
            return [(round(i * step), round(i * step) + size) for i in range(n)]
        n += 1


def image_size(path: Path) -> Optional[Tuple[int, int]]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.width, im.height
    except Exception:
        return None


def make_tiles(src: Path, out_dir: Path, max_side: int = MAX_SIDE) -> List[Path]:
    """Write the pieces of one screenshot into out_dir and return them in reading order.

    A screenshot that already fits, or any screenshot when Pillow is missing, is copied as is.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
    except ImportError:
        dst = out_dir / src.name
        shutil.copy2(src, dst)
        return [dst]
    try:
        opened = Image.open(src)
    except Exception:
        raise ValueError(tr("файл не открывается как картинка")) from None
    with opened as im:
        im = im.convert("RGB")
        # The game's interface grows with the screen height.  Above 1440 lines (4K) the captions
        # are larger than needed: bring the picture down to 1440 lines, which is known to read
        # well, instead of cutting it into many pieces.
        if im.height > max_side:
            ratio = 1440 / im.height
            im = im.resize((round(im.width * ratio), 1440), Image.LANCZOS)
        # the overlap must stay wider than one inventory cell
        overlap = max(MIN_OVERLAP, round(im.height * 0.22))
        xs, ys = spans(im.width, max_side, overlap), spans(im.height, max_side, overlap)
        if len(xs) == 1 and len(ys) == 1:
            dst = out_dir / (src.stem + ".png")
            im.save(dst, optimize=True)
            return [dst]
        tiles = []
        for r, (y0, y1) in enumerate(ys, 1):
            for c, (x0, x1) in enumerate(xs, 1):
                dst = out_dir / f"{src.stem}__r{r}c{c}.png"
                im.crop((x0, y0, x1, y1)).save(dst, optimize=True)
                tiles.append(dst)
        return tiles


def thumbnail(src: Path, width: int = 320) -> Optional[bytes]:
    """A small JPEG preview for the interface; None when Pillow is missing or the file is not a picture."""
    try:
        from PIL import Image
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((width, width))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
            return buf.getvalue()
    except Exception:
        return None


def archive(files: Optional[List[Path]] = None, label: str = "") -> Optional[Path]:
    """Move screenshots out of the inbox into _done/<time>[-label]. Nothing is ever deleted."""
    files = list(files) if files is not None else originals()
    if TILE_DIR.exists():
        shutil.rmtree(TILE_DIR, ignore_errors=True)
    files = [f for f in files if f.is_file()]
    if not files:
        return None
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S") + (f"-{label}" if label else "")
    target = DONE_DIR / stamp
    n = 1
    while target.exists():
        n += 1
        target = DONE_DIR / f"{stamp}-{n}"
    target.mkdir(parents=True)
    for f in files:
        shutil.move(str(f), str(target / f.name))
    return target


# --------------------------------------------------------------------------- the game's own screenshots
# Warframe saves a screenshot to <Pictures>\Warframe\WarframeNNNN.jpg when the player presses F6.
# Picking those files up spares the user any pasting: press F6 on each page in the game,
# then one click here.  The files are only read and copied; the folder itself is left alone.
STATE_FILE = config.DATA_DIR / "state.json"
FIRST_LOOK_BACK = 12 * 3600          # the first time, offer only what was shot during the last hours


def _pictures_dir() -> Path:
    """The user's Pictures folder, wherever Windows keeps it (it may be redirected, e.g. to OneDrive)."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

        folder_id = GUID(0x33E28130, 0x4E1E, 0x4676, (ctypes.c_ubyte * 8)(0x83, 0x5A, 0x98, 0x39, 0x5C, 0x3B, 0xC3, 0xBB))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(out)) == 0:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except Exception:
        pass
    return Path(os.environ.get("USERPROFILE") or Path.home()) / "Pictures"


def _state() -> Dict[str, Any]:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(data: Dict[str, Any]) -> None:
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass


def game_dir() -> Path:
    override = os.environ.get("PRIMESETS_GAME_SHOTS")
    if override:
        return Path(override)
    from . import settings
    custom = settings.extra("game_screenshots_dir")
    if isinstance(custom, str) and custom:
        return Path(custom)
    return _pictures_dir() / "Warframe"


def game_new() -> Dict[str, Any]:
    """Screenshots in the game's folder that were made after the last pick-up."""
    folder = game_dir()
    since = float(_state().get("game_shots_seen") or (time.time() - FIRST_LOOK_BACK))
    files = []
    if folder.is_dir():
        for f in folder.iterdir():
            try:
                if f.is_file() and f.suffix.lower() in EXT and f.stat().st_mtime > since:
                    files.append(f)
            except OSError:
                continue
    files.sort(key=lambda f: (f.stat().st_mtime, f.name))
    return {"dir": str(folder), "exists": folder.is_dir(), "files": files, "since": since}


def game_import() -> List[Path]:
    """Copy the new game screenshots into the inbox (in the order they were taken) and remember where we stopped."""
    info = game_new()
    config.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    copied: List[Path] = []
    newest = info["since"]
    for src in info["files"]:
        stamp = datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
        dst = config.SCREENSHOT_DIR / f"game-{stamp}-{src.stem}{src.suffix.lower()}"
        if not dst.exists():
            shutil.copy2(src, dst)
        copied.append(dst)
        newest = max(newest, src.stat().st_mtime)
    if copied:
        state = _state()
        state["game_shots_seen"] = newest
        _save_state(state)
    return copied


def game_mark_seen() -> None:
    """Forget what is in the game's folder right now: only screenshots made later will be offered."""
    state = _state()
    state["game_shots_seen"] = time.time()
    _save_state(state)
