"""Do the inventory screenshots join up, or was a row of tiles skipped while scrolling?

The sell screen shows three full rows of tiles and a fourth one cut by the lower edge of the list.
Scroll by exactly three rows and that cut row is the first row of the next screenshot.  Scroll by
four and the cut row -- visible without its captions -- is on neither screenshot in full: its parts
silently fall out of a "this is my whole list" import.  It happened to the user on 2026-11-18
(six parts lost between two F6 screenshots), hence this check.

How it works, for every two neighbouring screenshots of the tile grid:

  1. coarse: on small edge images, find the vertical shifts at which the lower part of the earlier
     screenshot looks like the upper part of the later one (candidates only -- part icons repeat a
     lot, "systems" looks the same for every warframe);
  2. fine: at each candidate, compare the overlap in the screenshots' own pixels, tile column by
     tile column, in small blocks, forgiving one pixel of misalignment (the list is often caught
     a moment before it settles).  The rows are the same only if (almost) every column agrees.
     On the user's real list two different rows differ clearly in at least four of the six
     columns, the same row in none.

No shift passes -> the list does not continue there.  A screenshot added later (a retake of the
missed place) closes the gap when it overlaps both sides.

The two ends of the list are checked as well:

  * the bottom: on an ordinary page the lowest row is cut by the edge about halfway, and those tiles
    are on no screenshot in full; on the last page the list is pushed against its end and the
    lowest row is whole.  A cut row at the bottom of the lowest screenshot = the list goes on;
  * the top: nothing in the tiles tells the first page from any other, but the scrollbar does --
    its thumb stands at the very top.

Only pictures the user made are compared; nothing is read from the game.  Needs Pillow: without it
the check reports itself unavailable and the app works as before.
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

WORK_H = 360                    # coarse scale: the reference height is brought to this many lines
GRID_Y = (0.185, 0.905)         # the scrolling list between the filter row and the bottom bar (of the height)
GRID_X_MAX = 0.72               # the tile grid ends before this share of the width (then the scrollbar)
MIN_OVERLAP = 20                # coarse lines two screenshots must share to be compared at all
STRIPES = 12
COARSE_MAX = 0.42               # a shift is worth a closer look below this mismatch (0 = identical, ~0.5 = unrelated)
CANDIDATES = 4
BLOCK = 8                       # fine block in pixels of a 1440-line screenshot
BLOCK_DIFF = 24                 # a block differs when this much edge strength has no counterpart on the other picture
CELL_SHARE = 0.01               # a tile column differs when this share of its blocks do (and at least CELL_BLOCKS)
CELL_BLOCKS = 4                 # ...which is about the size of a count badge
CELL_CONTENT = 4                # ...and holds anything at all when its edge level is above this
ALLOW_CELLS = 1                 # one column may differ: a tile under the cursor is drawn highlighted
SIZE_TOLERANCE = 0.85           # screenshots are comparable when the smaller is at least this share of the larger
ROW_WHOLE = 0.70                # the lowest row is whole when this share of a row is visible (a cut one shows about half,
                                # the last row of the list 0.86 -- measured on the user's screenshots)
THUMB_AT_TOP = 6                # the scrollbar thumb is at the top within this many pixels (of a 1440-line screenshot)...
THUMB_OFF_TOP = 10              # ...and clearly below it from here on
THUMB_AT_BOTTOM = 3             # a thumb this close to the bottom says "the end", whatever the rows look like


class Join(NamedTuple):
    joined: bool                # the two screenshots show one continuous stretch of the list
    why: str                    # "" | "gap" | "size" | "nogrid"
    shift: int = 0              # scroll between them in screenshot pixels (negative: the second one is higher up)
    cells: int = 0              # tile columns compared
    differ: int = 0             # ...of them clearly different at the best shift found


class _Page:
    """The list band of one screenshot: a small edge image for finding the overlap, and the
    full-size one -- made only when a candidate overlap has to be checked."""
    __slots__ = ("coarse", "lattice", "size", "scale", "unit", "bar", "_band", "_fine", "_guard")

    def __init__(self, band: Any, coarse: Any, lattice: Optional[Tuple[float, float, int]],
                 size: Tuple[int, int], scale: float, unit: float, bar: Any = None):
        self.bar = bar                  # the narrow strip right of the tiles where the scrollbar is (grey, own pixels)
        self.coarse = coarse            # edge image of the band, coarse scale
        self.lattice = lattice          # coarse x where the first column begins, column pitch, columns
        self.size = size
        self.scale = scale              # coarse pixels per screenshot pixel
        self.unit = unit                # screenshot pixels per pixel of a 1440-line screenshot
        self._band = band
        self._fine = None
        self._guard = threading.Lock()

    @property
    def fine(self) -> Any:
        """Edge image of the band in the screenshot's own pixels (the tile grid part of the width)."""
        with self._guard:
            if self._fine is None:
                self._fine = _edges(self._band, 2.0 * self.unit, 2)
                self._band = None
            return self._fine


_lock = threading.Lock()
_pages: "OrderedDict[Tuple, _Page]" = OrderedDict()        # a few recent pages: neighbours are compared in order
_joins: Dict[Tuple, Join] = {}
_grids: Dict[Tuple, Tuple[bool, Tuple[int, int]]] = {}
_marks: Dict[Tuple, Optional[Tuple[float, float]]] = {}    # where the scrollbar thumb stands on a screenshot
_PAGE_CACHE = 12
WORKERS = max(1, min(4, (os.cpu_count() or 2) - 1))
_RESULT_CACHE = 800


def available() -> bool:
    try:
        from PIL import Image, ImageChops, ImageFilter  # noqa: F401
        return True
    except ImportError:
        return False


def forget() -> None:
    """Drop everything remembered about earlier screenshots."""
    with _lock:
        _pages.clear()
        _joins.clear()
        _grids.clear()
        _marks.clear()


def _key(path: Path) -> Optional[Tuple[str, int, int]]:
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path), st.st_mtime_ns, st.st_size)


# --------------------------------------------------------------------------- one screenshot
def _edges(img: Any, blur: float, gain: int) -> Any:
    """Outlines only: the game's background is a slowly drifting glow that shines through the tiles
    and differs from screenshot to screenshot; icons, digits and captions are sharp."""
    from PIL import ImageChops, ImageFilter
    soft = img.filter(ImageFilter.GaussianBlur(blur))
    return ImageChops.difference(img, soft).point(lambda v: min(255, v * gain))


def _grow(img: Any, radius: int) -> Any:
    """Every pixel takes the largest value within `radius` around it (edges wrap, which is harmless here)."""
    from PIL import ImageChops
    out = img
    for d in range(1, radius + 1):
        out = ImageChops.lighter(out, ImageChops.lighter(ImageChops.offset(img, d, 0), ImageChops.offset(img, -d, 0)))
    wide = out
    for d in range(1, radius + 1):
        out = ImageChops.lighter(out, ImageChops.lighter(ImageChops.offset(wide, 0, d), ImageChops.offset(wide, 0, -d)))
    return out


def _lattice(coarse: Any) -> Optional[Tuple[float, float, int]]:
    """Is this a grid of tiles?  Tiles stand in columns with empty gaps of equal spacing between them.

    Returns (x where the first column begins, column pitch, number of columns) or None.
    The foundry's wide cards, the profile and everything else give no such gaps.
    """
    from PIL import Image
    w, h = coarse.size
    if h < 8 or w < 60:
        return None
    profile = coarse.resize((w, 1), Image.BOX).tobytes()
    scan = profile[: round(w * 0.74)]
    level = sorted(scan)[len(scan) // 2]
    if level < 12:                                   # an almost empty picture
        return None
    limit = level * 0.3
    gaps: List[List[int]] = []
    start = None
    for x, v in enumerate(scan):
        if v <= limit:
            if start is None:
                start = x
        elif start is not None:
            if gaps and start - gaps[-1][1] <= 3:    # one gap seen in two pieces
                gaps[-1][1] = x
            else:
                gaps.append([start, x])
            start = None
    centres = [(a + b) / 2 for a, b in gaps if a > 0 and b - a >= 2]     # a > 0: the left margin is not a gap
    # the longest row of gaps one pitch apart; a gap's centre wanders a little with what the tiles show
    best: Tuple[int, float, float, float] = (0, 0.0, 0.0, 0.0)          # (gaps, -error, first centre, pitch)
    for i in range(len(centres)):
        for j in range(i + 1, len(centres)):
            for k in range(1, 6):                    # the two gaps are k columns apart
                pitch = (centres[j] - centres[i]) / k
                if not 0.06 * w <= pitch <= 0.30 * w:
                    continue
                hits: Dict[int, Tuple[float, float]] = {}
                for c in centres:
                    pos = (c - centres[i]) / pitch
                    n = round(pos)
                    err = abs(pos - n)
                    if err <= 0.12 and (n not in hits or err < hits[n][0]):
                        hits[n] = (err, c)
                run = [0]
                while run[-1] + 1 in hits:
                    run.append(run[-1] + 1)
                while run[0] - 1 in hits:
                    run.insert(0, run[0] - 1)
                error = sum(hits[n][0] for n in run) / len(run)
                span = hits[run[-1]][1] - hits[run[0]][1]
                cand = (len(run), -error, hits[run[0]][1], span / max(1, len(run) - 1))
                if cand[:2] > best[:2]:
                    best = cand
    count, _error, first, pitch = best
    if count < 4:                                    # fewer than five columns: not the inventory grid
        return None
    left = first - pitch
    while left - pitch >= -0.25 * pitch:             # a gap near the left edge may have been missed
        left -= pitch
    cols = 1
    while left + (cols + 1) * pitch <= w * GRID_X_MAX:           # the margin before the scrollbar is not a column
        cols += 1
    return (left, pitch, cols) if cols >= 5 else None


def _size(path: Path) -> Optional[Tuple[int, int]]:
    key = _key(path)
    with _lock:
        known = _grids.get(key) if key else None
    if known is not None and known[1] != (0, 0):
        return known[1]
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def _band_rows(height: int, ref_h: int) -> Tuple[int, int]:
    return round(ref_h * GRID_Y[0]), min(height, round(ref_h * GRID_Y[1]))


def _load(path: Path, ref_h: int) -> Optional[_Page]:
    """The list band of a screenshot; ref_h is the height of the screen it was cut from."""
    key = (_key(path), ref_h)
    if key[0] is None:
        return None
    with _lock:
        page = _pages.get(key)
        if page is not None:
            _pages.move_to_end(key)
            return page
    from PIL import Image
    try:
        with Image.open(path) as im:
            size = im.size
            grey = im.convert("L")
    except Exception:
        return None
    if size[1] < 200 or size[0] < 300 or ref_h < size[1]:
        return None
    scale = WORK_H / ref_h
    y0, y1 = _band_rows(size[1], ref_h)
    if (y1 - y0) * scale < MIN_OVERLAP * 2:
        return None
    band = grey.crop((0, y0, size[0], y1))
    cw, ch = max(1, round(size[0] * scale)), max(1, round((y1 - y0) * scale))
    coarse = _edges(band.resize((cw, ch), Image.BOX), 2.0, 4)
    lattice = _lattice(coarse)
    bar = None
    if lattice:
        right, step = (lattice[0] + lattice[2] * lattice[1]) / scale, lattice[1] / scale
        bx0, bx1 = round(right + 0.05 * step), min(size[0], round(right + 0.25 * step))
        if bx1 - bx0 >= 6:
            bar = band.crop((bx0, 0, bx1, y1 - y0))
    # the full-size picture is needed only where the tiles are
    band = band.crop((0, 0, min(size[0], round(size[0] * (GRID_X_MAX + 0.03))), y1 - y0))
    page = _Page(band, coarse, lattice, size, scale, ref_h / 1440, bar)
    with _lock:
        _pages[key] = page
        while len(_pages) > _PAGE_CACHE:
            _pages.popitem(last=False)
    return page


def _quick_grid(path: Path) -> Tuple[bool, Tuple[int, int]]:
    """The tile grid test alone, on a reduced decode (a JPEG is read at a quarter of its size)."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            size = im.size
            if size[1] < 200 or size[0] < 300:
                return (False, size)
            im.draft("L", (max(1, size[0] // 4), max(1, size[1] // 4)))
            grey = im.convert("L")
    except Exception:
        return (False, (0, 0))
    y0, y1 = _band_rows(size[1], size[1])
    ratio = grey.size[1] / size[1]
    band = grey.crop((0, round(y0 * ratio), grey.size[0], round(y1 * ratio)))
    scale = WORK_H / size[1]
    small = band.resize((max(1, round(size[0] * scale)), max(1, round((y1 - y0) * scale))), Image.BOX)
    return (_lattice(_edges(small, 2.0, 4)) is not None, size)


def is_grid(path: Path) -> bool:
    """Does the screenshot show the grid of inventory tiles?"""
    key = _key(path)
    if key is None:
        return False
    with _lock:
        known = _grids.get(key)
    if known is not None:
        return known[0]
    answer, size = _quick_grid(path)
    with _lock:
        if len(_grids) > _RESULT_CACHE:
            _grids.clear()
        _grids[key] = (answer, size)
    return answer


# --------------------------------------------------------------------------- where the tiles stand
ROW_PITCH = (1.00, 1.14)        # rows stand a little further apart than columns: 296 against 278 px at 1440 lines
TILE_SHARE = 0.92               # a tile is a square of this share of the column pitch; the rest is the gap
ROW_VISIBLE = 0.30              # a row cut by an edge of the list counts as a row when this much of it is seen


def grid(path: Path) -> Optional[Dict[str, Any]]:
    """Where the tiles stand on an inventory screenshot, in the screenshot's own pixels.

    Returns {"cols": [(x0, x1), ...], "rows": [(y0, y1), ...], "size": (w, h)} or None when the
    screenshot shows no tile grid.  The rows go from the top; a row cut by the upper or the lower
    edge of the list is among them when a fair part of it is visible -- as a person would count them.
    """
    size = _size(path)
    if not size:
        return None
    page = _load(path, size[1])
    if page is None or not page.lattice:
        return None
    from PIL import Image
    left, pitch, cols = page.lattice
    coarse = page.coarse
    w, h = coarse.size
    x0, x1 = max(0, round(left)), min(w, round(left + cols * pitch))
    if x1 - x0 < 8 or h < 16:
        return None
    profile = coarse.crop((x0, 0, x1, h)).resize((1, h), Image.BOX).tobytes()
    total = [0]
    for v in profile:
        total.append(total[-1] + v)

    def mean(a: float, b: float) -> Optional[float]:
        a, b = max(0, round(a)), min(h, round(b))
        return (total[b] - total[a]) / (b - a) if b > a else None

    tile = TILE_SHARE * pitch
    best: Tuple[float, float, float] = (-1.0, 0.0, 0.0)          # (contrast, row pitch, top of a row)
    steps = int((ROW_PITCH[1] - ROW_PITCH[0]) * pitch * 4) + 1
    for n in range(steps):
        row = ROW_PITCH[0] * pitch + n * 0.25
        gap = row - tile
        if gap < 1.5:
            continue
        phase = 0.0
        while phase < row:
            inside, between = [], []
            top = phase - row
            while top < h:
                a = mean(top, top + tile)
                b = mean(top - gap, top)
                if a is not None:
                    inside.append(a)
                if b is not None:
                    between.append(b)
                top += row
            if inside and between:
                contrast = sum(inside) / len(inside) - sum(between) / len(between)
                if contrast > best[0]:
                    best = (contrast, row, phase)
            phase += 0.5
    contrast, row, phase = best
    if contrast <= 0:
        return None
    band_top = _band_rows(size[1], size[1])[0]
    scale = page.scale
    rows = []
    top = phase - row
    while top < h:
        seen = (min(h, top + tile) - max(0.0, top)) / tile
        if seen >= ROW_VISIBLE:
            rows.append((band_top + round(max(0.0, top) / scale), band_top + round(min(h, top + tile) / scale)))
        top += row
    edge = (pitch - tile) / 2
    columns = [(round((left + c * pitch + edge) / scale), round((left + c * pitch + edge + tile) / scale)) for c in range(cols)]
    return {"cols": columns, "rows": rows, "size": size}


def tile_box(path: Path, row: int, col: int, margin: float = 0.06) -> Optional[Tuple[int, int, int, int]]:
    """The place of the tile in the given row and column (both from 1) with a little room around it."""
    found = grid(path)
    if not found or not (1 <= row <= len(found["rows"])) or not (1 <= col <= len(found["cols"])):
        return None
    (x0, x1), (y0, y1) = found["cols"][col - 1], found["rows"][row - 1]
    pad = round((x1 - x0) * margin)
    w, h = found["size"]
    return (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))


def tile_picture(path: Path, row: int, col: int, side: int = 240) -> Optional[bytes]:
    """A small JPEG of one tile, for showing next to the line that was read from it."""
    box = tile_box(path, row, col)
    if box is None:
        return None
    import io
    from PIL import Image
    try:
        with Image.open(path) as im:
            piece = im.convert("RGB").crop(box)
    except Exception:
        return None
    piece.thumbnail((side, side))
    out = io.BytesIO()
    piece.save(out, "JPEG", quality=85)
    return out.getvalue()


def _thumb(page: _Page) -> Optional[Tuple[float, float]]:
    """The scrollbar thumb: how far it stands from the top and from the bottom of the list band,
    in pixels of a 1440-line screenshot.  None when no thumb is seen.

    The thumb is the longest run of bright lines in the strip between the tiles and the side panel.
    A line counts when three neighbouring columns are bright at once: the mouse pointer, which
    likes to rest right there, is not that regular.
    """
    from PIL import ImageChops
    bar = page.bar
    if bar is None:
        return None
    w, h = bar.size
    best = (0, 0)                                    # (length, first line)
    for x in range(0, w - 2):
        col = bar.crop((x, 0, x + 1, h))
        for d in (1, 2):
            col = ImageChops.darker(col, bar.crop((x + d, 0, x + d + 1, h)))
        data = col.tobytes()
        ordered = sorted(data)
        dark, bright = ordered[h // 2], ordered[-1]
        if bright - dark < 50:
            continue
        limit = (dark + bright) / 2
        run = 0
        for y, v in enumerate(data):
            if v >= limit:
                run += 1
                if run > best[0]:
                    best = (run, y + 1 - run)
            else:
                run = 0
    length, top = best
    if not 0.012 * h <= length <= 0.6 * h:           # too short for a thumb, or a border running the whole height
        return None
    return (top / page.unit, (h - top - length) / page.unit)


def _mark(path: Path, height: int) -> Optional[Tuple[float, float]]:
    """_thumb() of a screenshot, remembered: the picture itself is not kept."""
    key = (_key(path), height)
    with _lock:
        if key in _marks:
            return _marks[key]
    page = _load(path, height)
    mark = _thumb(page) if page is not None and page.lattice else None
    with _lock:
        if len(_marks) > _RESULT_CACHE:
            _marks.clear()
        _marks[key] = mark
    return mark


def _last_row(page: _Page) -> Optional[float]:
    """How much of the lowest row of tiles is on the screenshot, as a share of a full row.

    About a half: the row is cut by the edge of the list -- the list goes on below.
    Close to one, or nothing at all below the last gap between rows: the list ends here.
    None: the rows could not be made out.
    """
    from PIL import Image
    if not page.lattice:
        return None
    left, pitch, cols = page.lattice
    w, h = page.coarse.size
    x0, x1 = max(0, round(left)), min(w, round(left + cols * pitch))
    if x1 - x0 < cols * 4:
        return None
    cells = page.coarse.crop((x0, 0, x1, h)).resize((cols, h), Image.BOX).tobytes()
    rows = [max(cells[y * cols:(y + 1) * cols]) for y in range(h)]      # one tile in a row is still a row
    level = sorted(rows)[h // 2]
    if level < 12:
        return None
    gaps: List[List[int]] = []
    start = None
    for y, v in enumerate(rows + [255]):
        if v <= level * 0.3:
            if start is None:
                start = y
        elif start is not None:
            if gaps and start - gaps[-1][1] <= 2:
                gaps[-1][1] = y
            else:
                gaps.append([start, y])
            start = None
    gaps = [g for g in gaps if g[1] - g[0] >= 6]     # a real gap between rows is about ten lines
    if not gaps:
        return None
    if gaps[-1][1] >= h:
        return 1.0                                   # the band ends in emptiness: nothing is cut
    centres = [(a + b) / 2 for a, b in gaps]
    steps = sorted(q - p for p, q in zip(centres, centres[1:]) if q - p >= 0.7 * pitch)
    row = steps[len(steps) // 2] if steps else pitch * 1.07         # tiles are square, rows a little further apart
    return (h - gaps[-1][1]) / row


# --------------------------------------------------------------------------- two screenshots
def _coarse_mismatch(a: Any, b: Any, s: int) -> float:
    """b scrolled s lines further than a: b[y] against a[y + s].  0 = the same picture, about 0.5 = unrelated.

    Counted in vertical stripes with the worst quarter dropped -- this stage only proposes shifts.
    """
    from PIL import Image, ImageChops
    w, h = a.size
    pa, pb = a.crop((0, s, w, h)), b.crop((0, 0, w, h - s))
    diff = ImageChops.difference(pa, pb).resize((STRIPES, 1), Image.BOX).tobytes()
    both = ImageChops.add(pa, pb, 2).resize((STRIPES, 1), Image.BOX).tobytes()
    rows = sorted(((d / (2 * n + 1e-6), d, n) for d, n in zip(diff, both)), key=lambda t: t[0])
    keep = rows[: STRIPES - STRIPES // 4]
    content = sum(t[2] for t in keep)
    if content < len(keep) * 4:                      # nothing but background in the overlap
        return 1.0
    return sum(t[1] for t in keep) / (2 * content)


def _candidates(a: Any, b: Any) -> List[Tuple[float, int]]:
    """The few shifts at which b best continues a, the best first.

    Every shift is tried on pictures of half the size (cheap), then the neighbourhood of the
    promising ones on the coarse pictures themselves.
    """
    h = a.size[1]
    last = h - MIN_OVERLAP
    half_a, half_b = a.reduce(2), b.reduce(2)
    rough = sorted((_coarse_mismatch(half_a, half_b, s), s) for s in range(0, max(1, half_a.size[1] - MIN_OVERLAP // 2)))
    spots: List[int] = []
    for _value, s in rough:
        if len(spots) >= CANDIDATES + 3:
            break
        if all(abs(s - other) > 4 for other in spots):
            spots.append(s)
    tried: Dict[int, float] = {}
    for spot in spots:
        for s in range(max(0, spot * 2 - 2), min(last, spot * 2 + 3)):
            if s not in tried:
                tried[s] = _coarse_mismatch(a, b, s)
    picks: List[Tuple[float, int]] = []
    for value, s in sorted((v, s) for s, v in tried.items()):
        if value > COARSE_MAX or len(picks) >= CANDIDATES:
            break
        if all(abs(s - other) > 8 for _v, other in picks):       # one entry per valley
            picks.append((value, s))
    return picks


def _verify(pa: _Page, pb: _Page, s: int, dx: int, exact_x: bool) -> Tuple[int, int, int, List[Tuple[int, int, int]]]:
    """Is the overlap at coarse shift s really the same rows?

    -> (columns compared, columns that differ, shift in screenshot pixels, per column (blocks, differing, level)).
    dx: b's tile columns stand dx pixels to the right of a's (screenshots cut to different sizes).
    """
    from PIL import Image, ImageChops
    a, b = pa.fine, pb.fine
    unit = pa.unit
    block = max(4, round(BLOCK * unit))
    h = min(a.size[1], b.size[1]) - abs(pa.size[1] - pb.size[1])
    left, pitch, cols = pa.lattice  # type: ignore[misc]
    gx0 = max(0, round(left / pa.scale))
    gx1 = min(a.size[0], round((left + cols * pitch) / pa.scale))
    reach = max(2, math.ceil(1.5 / pa.scale))        # the coarse shift is known to about a coarse line
    slack = 0 if exact_x else reach                 # cut to another size: the column offset is known as roughly
    gx0 = max(gx0, -(dx - slack), slack)
    gx1 = min(gx1, b.size[0] - dx - slack, a.size[0] - slack)
    centre = round(s / pa.scale)
    if gx1 - gx0 < block * 8:
        return (0, 0, centre, [])

    # 1. settle the shift to the pixel on a strip of the overlap
    span = min(round(220 * unit), h - (centre + reach) - reach)
    if span < block * 3:
        return (0, 0, centre, [])
    best = None
    for t in range(max(0, centre - reach), centre + reach + 1):
        for ox in range(-slack, slack + 1):
            ca = a.crop((gx0, t + reach, gx1, t + reach + span))
            cb = b.crop((gx0 + dx + ox, reach, gx1 + dx + ox, reach + span))
            total = sum(ImageChops.difference(ca, cb).resize((32, 6), Image.BOX).tobytes())
            if best is None or total < best[0]:
                best = (total, t, ox)
    _total, t, ox = best  # type: ignore[misc]

    # 2. what is on one picture and has nothing next to it on the other
    oh = h - t
    if oh < block * 3:
        return (0, 0, t, [])
    ca = a.crop((gx0, t, gx1, t + oh))
    cb = b.crop((gx0 + dx + ox, 0, gx1 + dx + ox, oh))
    near = 1 if unit <= 1.25 else 2
    alone = ImageChops.lighter(ImageChops.subtract(ca, _grow(cb, near)), ImageChops.subtract(cb, _grow(ca, near)))
    bw, bh = (gx1 - gx0) // block, oh // block
    if bw < 6 or bh < 2:
        return (0, 0, t, [])
    box = (0, 0, bw * block, bh * block)
    diff = alone.crop(box).resize((bw, bh), Image.BOX).tobytes()
    level = ImageChops.lighter(ca, cb).crop(box).resize((bw, bh), Image.BOX).tobytes()

    compared = differ = 0
    stats: List[Tuple[int, int, int]] = []
    for c in range(cols):
        c0 = max(0, round(((left + c * pitch) / pa.scale - gx0) / block))
        c1 = min(bw, round(((left + (c + 1) * pitch) / pa.scale - gx0) / block))
        if c1 - c0 < 3:
            continue
        bad = total = 0
        for r in range(bh):
            row = r * bw
            for x in range(c0, c1):
                total += level[row + x]
                if diff[row + x] >= BLOCK_DIFF:
                    bad += 1
        blocks = (c1 - c0) * bh
        stats.append((blocks, bad, round(total / blocks)))
        if total / blocks < CELL_CONTENT:
            continue                                 # an empty slot at the end of the list proves nothing
        compared += 1
        if bad >= max(CELL_BLOCKS, blocks * CELL_SHARE):
            differ += 1
    return (compared, differ, t, stats)


def _continues(pa: _Page, pb: _Page, exact_x: bool) -> Optional[Tuple[int, int, int]]:
    """Does pb show the list further down than pa, with an overlap?

    -> (shift in screenshot pixels, columns compared, differing columns); the last one is negated
    when no shift passed (the closest attempt is reported); None when there was nothing to compare.
    """
    w = min(pa.coarse.size[0], pb.coarse.size[0])
    h = min(pa.coarse.size[1], pb.coarse.size[1])
    left, pitch, cols = pa.lattice  # type: ignore[misc]

    def proposals(cdx: int) -> List[Tuple[float, int]]:
        x0 = max(0, round(left), -cdx)
        x1 = min(w, round(left + cols * pitch), pb.coarse.size[0] - cdx)
        if x1 - x0 < 40:
            return []
        return _candidates(pa.coarse.crop((x0, 0, x1, h)), pb.coarse.crop((x0 + cdx, 0, x1 + cdx, h)))

    if exact_x:
        cdx, picks = 0, proposals(0)
    else:
        # pieces of the same screen cut at different places: where do b's tile columns stand against a's?
        # The lattice says it only roughly, and "not moved at all" is the commonest answer.
        guess = round(pb.lattice[0] - pa.lattice[0])  # type: ignore[index]
        lo, hi = min(0, guess) - 3, max(0, guess) + 3
        if hi - lo > 40:
            return None
        cdx, picks = 0, []
        for off in range(lo, hi + 1):
            got = proposals(off)
            if got and (not picks or got[0][0] < picks[0][0]):
                cdx, picks = off, got
    dx = round(cdx / pa.scale)
    closest = None
    for _value, s in picks:
        compared, differ, shift, _stats = _verify(pa, pb, s, dx, exact_x)
        if compared >= 2 and differ <= ALLOW_CELLS and differ < compared:
            return (shift, compared, differ)
        if compared and (closest is None or differ < -closest[2]):
            closest = (shift, compared, -max(1, differ))
    return closest


def join(a: Path, b: Path) -> Join:
    """Do two screenshots show one stretch of the list (in either order)?"""
    ka, kb = _key(a), _key(b)
    if ka is None or kb is None:
        return Join(False, "nogrid")
    with _lock:
        known = _joins.get((ka, kb))
    if known is not None:
        return known
    result = _join(a, b)
    with _lock:
        if len(_joins) > _RESULT_CACHE:
            _joins.clear()
        _joins[(ka, kb)] = result
    return result


def _join(a: Path, b: Path) -> Join:
    sa, sb = _size(a), _size(b)
    if not sa or not sb:
        return Join(False, "nogrid")
    if min(sa[0], sb[0]) < max(sa[0], sb[0]) * SIZE_TOLERANCE or min(sa[1], sb[1]) < max(sa[1], sb[1]) * SIZE_TOLERANCE:
        return Join(False, "size")
    ref_h = max(sa[1], sb[1])
    pa, pb = _load(a, ref_h), _load(b, ref_h)
    if pa is None or pb is None or not pa.lattice or not pb.lattice:
        return Join(False, "nogrid")
    same = sa == sb
    down = _continues(pa, pb, same)
    if down and down[2] >= 0:
        return Join(True, "", down[0], down[1], down[2])
    up = _continues(pb, pa, same)                    # taken in the other order (scrolled back up)
    if up and up[2] >= 0:
        return Join(True, "", -up[0], up[1], up[2])
    seen = down or up
    why = "gap" if same else "size"                  # cut by hand to another size: not sure enough to call it a gap
    return Join(False, why, 0, seen[1] if seen else 0, -seen[2] if seen else 0)


# --------------------------------------------------------------------------- a batch
def _ends(seq: Sequence[Path], steps: List[Tuple[int, int, int]], report: Dict[str, Any]) -> None:
    """Fill in report["start"] / ["end"]: is the topmost screenshot the top of the list, the lowest one its bottom?"""
    sizes = {_size(f) for f in seq}
    if len(sizes) != 1 or None in sizes:
        return                                       # cut by hand to different sizes: the list band may sit elsewhere
    height = next(iter(sizes))[1]                    # type: ignore[index]
    near: Dict[int, List[Tuple[int, int]]] = {}
    for i, j, pixels in steps:
        near.setdefault(i, []).append((j, pixels))
        near.setdefault(j, []).append((i, -pixels))

    def stretch(origin: int) -> Dict[int, int]:
        """Where the screenshots joined to `origin` (directly or through others) stand, in pixels from it."""
        place = {origin: 0}
        todo = [origin]
        while todo:
            i = todo.pop()
            for j, pixels in near.get(i, ()):
                if j not in place:
                    place[j] = place[i] + pixels
                    todo.append(j)
        return place

    upper = lower = stretch(0)
    if len(upper) != len(seq):
        # A gap splits the screenshots into several stretches.  Within a stretch the joins give the
        # order to the pixel; which stretch is the highest and which the lowest, the scrollbar tells.
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            thumbs = list(pool.map(lambda f: _mark(f, height), seq))
        if any(t is None for t in thumbs):
            return
        upper = stretch(min(range(len(seq)), key=lambda i: thumbs[i][0]))      # type: ignore[index]
        lower = stretch(max(range(len(seq)), key=lambda i: thumbs[i][0]))      # type: ignore[index]
    top, bottom = min(upper, key=lambda i: upper[i]), max(lower, key=lambda i: lower[i])
    report["first"], report["last"] = seq[top].name, seq[bottom].name
    first, last = _load(seq[top], height), _load(seq[bottom], height)
    if first is not None and first.lattice:
        thumb = _thumb(first)
        if thumb is not None:
            report["start"] = "ok" if thumb[0] <= THUMB_AT_TOP else "missing" if thumb[0] >= THUMB_OFF_TOP else "unknown"
    if last is not None and last.lattice:
        share = _last_row(last)
        if share is not None and share >= ROW_WHOLE:
            report["end"] = "ok"
        elif share is not None:
            # the scrollbar must not contradict it: a thumb at the very bottom says the list has ended
            thumb = _thumb(last)
            report["end"] = "unknown" if thumb is not None and thumb[1] < THUMB_AT_BOTTOM else "missing"


def check(files: Sequence[Path], screens: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Look for skipped rows in a batch of screenshots given in the order they were taken.

    screens -- what the recognition said about each file ("inventory", "foundry", ...), when it is
    already known; without it a screenshot counts as inventory when the tile grid is found on it.

    Returns {"available", "state", "pages", "pairs", "joined", "gaps": [{"after", "before"}],
             "unknown": [{"after", "before", "why"}], "start", "end", "first", "last", "seconds"}.
    start / end -- "ok", "missing" or "unknown": does the topmost screenshot (first) show the top of
    the list and the lowest one (last) its bottom.
    state is one of
      none     fewer than two inventory screenshots: nothing to compare;
      ok       every screenshot continues the previous one;
      gaps     the listed neighbours do not join;
      unsure   no pair joined at all: either every step skipped a row or the screen looks unfamiliar;
      unknown  no gap found, but some pairs could not be compared.
    """
    started = time.perf_counter()
    report: Dict[str, Any] = {"available": available(), "state": "none", "pages": 0, "pairs": 0, "joined": 0,
                              "gaps": [], "unknown": [], "start": "unknown", "end": "unknown", "first": "", "last": "",
                              "seconds": 0.0}
    if not report["available"]:
        return report
    if screens is None:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            seq = [f for f, grid in zip(files, pool.map(is_grid, files)) if grid]
    else:
        seq = [f for f in files if screens.get(f.name) == "inventory"]
    report["pages"] = len(seq)
    report["pairs"] = max(0, len(seq) - 1)
    if not seq:
        report["seconds"] = round(time.perf_counter() - started, 2)
        return report

    steps: List[Tuple[int, int, int]] = []           # (i, j, pixels): seq[j] shows the list that much further down
    if len(seq) > 1:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            links = list(pool.map(lambda pair: join(*pair), zip(seq, seq[1:])))
        report["joined"] = sum(1 for link in links if link.joined)

        # runs of screenshots that continue each other; a later retake may connect two runs
        group = list(range(len(seq)))

        def find(i: int) -> int:
            while group[i] != i:
                group[i] = group[group[i]]
                i = group[i]
            return i

        for i, link in enumerate(links):
            if link.joined:
                group[find(i + 1)] = find(i)
                steps.append((i, i + 1, link.shift))
        breaks = [i for i, link in enumerate(links) if not link.joined]
        if breaks:
            # A short run is probably a retake of a missed place, added after the rest: see whether its
            # ends meet the ends of the other runs.  (Two long runs are not tried against each other.)
            bounds = [0] + [i + 1 for i in breaks] + [len(seq)]
            runs = [(a, b - 1) for a, b in zip(bounds, bounds[1:])]
            short = [r for r in runs if r[1] - r[0] < 3]
            wanted = {(min(i, j), max(i, j)) for r in short for q in runs if q != r for i in set(r) for j in set(q)}
            # ...and against the screenshots that stand next to it in the list, going by the scrollbar:
            # a retake of the wrong place then simply joins its neighbours instead of looking like a new gap
            sizes = {_size(f) for f in seq}
            if short and len(sizes) == 1 and None not in sizes:
                height = next(iter(sizes))[1]            # type: ignore[index]
                with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                    thumbs = list(pool.map(lambda f: _mark(f, height), seq))
                if all(t is not None for t in thumbs):
                    order = sorted(range(len(seq)), key=lambda i: thumbs[i][0])     # type: ignore[index]
                    rank = {i: n for n, i in enumerate(order)}
                    for r in short:
                        for i in set(r):
                            for n in range(max(0, rank[i] - 2), min(len(order), rank[i] + 3)):
                                j = order[n]
                                if j != i and find(j) != find(i):
                                    wanted.add((min(i, j), max(i, j)))
            pairs = sorted(wanted)
            if 0 < len(pairs) <= 32:
                with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                    for (i, j), link in zip(pairs, pool.map(lambda ij: join(seq[ij[0]], seq[ij[1]]), pairs)):
                        if link.joined:
                            group[find(j)] = find(i)
                            steps.append((i, j, link.shift))

        seams = set()
        for i in breaks:
            seam = frozenset((find(i), find(i + 1)))
            if len(seam) == 1 or seam in seams:
                continue                             # closed by another screenshot, or the same break seen twice
            seams.add(seam)
            item = {"after": seq[i].name, "before": seq[i + 1].name}
            if links[i].why == "gap":
                report["gaps"].append(item)
            else:
                report["unknown"].append({**item, "why": links[i].why})
        if report["gaps"]:
            report["state"] = "unsure" if report["joined"] == 0 and report["pairs"] >= 3 else "gaps"
        elif report["unknown"]:
            report["state"] = "unknown"
        else:
            report["state"] = "ok"

    _ends(seq, steps, report)                        # does what was shot reach both ends of the list?
    with _lock:
        _pages.clear()                               # the pictures are large; the answers are remembered separately
    report["seconds"] = round(time.perf_counter() - started, 2)
    return report
