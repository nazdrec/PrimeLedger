"""Tiny disk cache: one JSON (or binary) file per key, with age-based expiry."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional, Tuple

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class DiskCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, key: str, suffix: str = ".json") -> Path:
        name = _SAFE.sub("_", key).strip("._") or "key"
        return self.root / (name[:150] + suffix)

    # -- JSON ---------------------------------------------------------------
    def get(self, key: str, ttl: Optional[float] = None) -> Optional[Tuple[Any, float]]:
        """Return (data, fetched_at) or None. With ttl, expired entries are ignored."""
        path = self._path(key)
        try:
            with self._lock:
                raw = path.read_text(encoding="utf-8")
            box = json.loads(raw)
            fetched_at = float(box["fetched_at"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if ttl is not None and time.time() - fetched_at > ttl:
            return None
        return box["data"], fetched_at

    def put(self, key: str, data: Any) -> float:
        now = time.time()
        self._write(self._path(key), json.dumps({"fetched_at": now, "data": data}, ensure_ascii=False).encode("utf-8"))
        return now

    def delete(self, key: str) -> None:
        try:
            with self._lock:
                self._path(key).unlink()
        except OSError:
            pass

    # -- binary (thumbnails) ------------------------------------------------
    def get_bytes(self, key: str, suffix: str) -> Optional[bytes]:
        try:
            with self._lock:
                return self._path(key, suffix).read_bytes()
        except OSError:
            return None

    def put_bytes(self, key: str, suffix: str, data: bytes) -> None:
        self._write(self._path(key, suffix), data)

    def _write(self, path: Path, payload: bytes) -> None:
        tmp = path.with_name(path.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(payload)
            os.replace(tmp, path)
