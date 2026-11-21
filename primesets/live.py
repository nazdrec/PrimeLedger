"""Shooting the inventory with a second pair of eyes.

While the user is in the game pressing F6 on every page of the list, the app watches the folder
where the game itself saves those screenshots, takes each new one into its inbox and checks at
once whether it continues the previous one (continuity.py).  A short sound says "it does"; a low
triple one says "a row was skipped: go one page back and shoot again".  The mistake then costs
a second instead of a second trip into the game after the reading.

Only files the game has already written are read.  The app does not look at the screen, presses
no keys and has no contact with the game.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import continuity, shots

log = logging.getLogger("primesets")

IDLE_STOP = 30 * 60             # nothing was shot for this long: the shooting is over
RECENT = 10 * 60                # screenshots made this shortly before the start still belong to the shooting
POLL = 1.0
# what is played: (frequency in Hz or 0 for a pause, milliseconds)
PATTERNS = {
    "ok": [(1175, 70)],
    "other": [(784, 60)],                                             # taken, but it is not the tile grid
    "gap": [(330, 220), (0, 70), (330, 220), (0, 70), (330, 320)],
    "end": [(880, 110), (0, 40), (1320, 190)],
}


def play(kind: str) -> None:
    """The sound of a signal, from the program itself (the window may be asleep behind the game)."""
    try:
        import winsound
    except ImportError:                  # not Windows: silently
        return

    def run() -> None:
        for freq, ms in PATTERNS.get(kind, []):
            if not freq:
                time.sleep(ms / 1000)
                continue
            try:
                winsound.Beep(freq, ms)
            except RuntimeError:         # no sound device
                return

    threading.Thread(target=run, name="beep", daemon=True).start()


class Live:
    def __init__(self, notify: Callable[[str, Dict[str, Any]], None], beep: Optional[Callable[[str], None]] = None):
        self.on = False
        self.sound = True
        self.started = 0.0
        self.taken = 0                   # screenshots taken in since the start
        self.signal = ""                 # the last signal: ok | gap | end | other
        self.last = ""                   # the file it was about
        self.gap: Optional[Dict[str, Any]] = None       # the newest unclosed break: {"after", "before"}
        self.report: Optional[Dict[str, Any]] = None
        self._sizes: Dict[str, int] = {}
        self._trouble: Optional[int] = None
        self._ended = False
        self._active = 0.0
        self._notify = notify
        self._beep = beep or play
        self._lock = threading.Lock()

    # -- switching ----------------------------------------------------------
    def start(self, sound: bool = True, thread: bool = True) -> None:
        with self._lock:
            if self.on:
                self.sound = bool(sound)
                return
            now = time.time()
            self.on, self.sound, self.started, self._active = True, bool(sound), now, now
            self.taken, self.signal, self.last, self.gap, self.report = 0, "", "", None, None
            self._sizes, self._trouble, self._ended = {}, None, False
        # what was shot long before the start is not part of this shooting
        shots.game_mark_seen(now - RECENT)
        if thread:
            threading.Thread(target=self._run, name="live-shooting", daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            self.on = False

    def _run(self) -> None:
        while self.on:
            try:
                self.step()
            except Exception:            # a broken file must not end the shooting
                log.exception("live shooting: a look at the game's folder failed")
            time.sleep(POLL)

    def state(self) -> Dict[str, Any]:
        return {"on": self.on, "sound": self.sound, "taken": self.taken, "signal": self.signal, "last": self.last,
                "gap": self.gap, "started": self.started, "available": continuity.available()}

    # -- one look at the game's folder --------------------------------------
    @staticmethod
    def _count(report: Dict[str, Any]) -> int:
        return len(report.get("gaps") or [])

    def step(self, now: Optional[float] = None) -> Optional[str]:
        """Take in what the game has finished writing and say whether the list still joins up.
        Returns the signal given ("ok", "gap", "end", "other") or None when there was nothing new."""
        if not self.on:
            return None
        now = now or time.time()
        ready: List[Any] = []
        sizes: Dict[str, int] = {}
        for f in shots.game_new()["files"]:
            try:
                size = f.stat().st_size
            except OSError:
                continue
            sizes[str(f)] = size
            if size > 0 and self._sizes.get(str(f)) == size:
                ready.append(f)          # the same size at two looks in a row: the game has finished the file
        self._sizes = sizes
        if not ready:
            if now - self._active > IDLE_STOP:
                self.stop()
                self._notify("live", self.state())
            return None
        self._active = now
        if self._trouble is None:        # the breaks that were in the inbox before this shooting are not its fault
            self._trouble = self._count(continuity.check(shots.originals())) if continuity.available() else 0
        copied = shots.game_import(only=ready)
        if not copied:
            return None
        signal = "ok"
        if continuity.available():
            report = continuity.check(shots.originals())
            trouble = self._count(report)
            if not any(continuity.is_grid(f) for f in copied):
                signal = "other"
            elif trouble > self._trouble:
                signal = "gap"
            elif report.get("end") == "ok" and report.get("state") == "ok" and not self._ended:
                signal, self._ended = "end", True
            self._trouble = trouble
            self.report = report
            self.gap = dict(report["gaps"][-1]) if report.get("gaps") else None
        self.taken += len(copied)
        self.signal, self.last = signal, copied[-1].name
        if self.sound:
            self._beep(signal)
        self._notify("joins", {})        # the dialog of the screenshots asks for the list and the check again
        self._notify("live", self.state())
        return signal
