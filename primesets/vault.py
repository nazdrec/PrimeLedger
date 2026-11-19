"""API keys and the proxy address, kept encrypted.

Windows encrypts each value with the account of the user who is signed in (DPAPI), so the file
data/secrets.json is useless on another computer and under another Windows account.  The
values never travel to the page: the interface learns only that something is saved and how
it ends ("...a1b2").  Nothing here is written to the log.

A key can also come from the usual environment variable (ANTHROPIC_API_KEY and the like):
it is then used as it is and never copied into the file.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import urllib.parse
from typing import Dict, Optional

from . import APP_NAME, config

SECRETS_FILE = config.DATA_DIR / "secrets.json"
PROXY = "proxy"
ENV_KEYS: Dict[str, tuple] = {
    "anthropic_api": ("ANTHROPIC_API_KEY",),
    "openai_api": ("OPENAI_API_KEY",),
    "deepseek_api": ("DEEPSEEK_API_KEY",),
    "gemini_api": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}
_ENTROPY = b"PrimeSets.vault.v1"         # a fixed mark of this file format: never changes with the name of the app
_lock = threading.RLock()


def available() -> bool:
    return os.name == "nt"


# --------------------------------------------------------------------------- DPAPI
_blob_type = None


def _blob_class():
    global _blob_type
    if _blob_type is None:
        import ctypes
        from ctypes import wintypes

        class DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        _blob_type = DataBlob
    return _blob_type


def _blob(data: bytes):
    """A DATA_BLOB over a copy of the bytes; the buffer is returned too, to keep it alive."""
    import ctypes

    buf = ctypes.create_string_buffer(data, len(data))
    return _blob_class()(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _crypt(data: bytes, protect: bool) -> bytes:
    import ctypes

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    blob_in, _keep_in = _blob(data)
    entropy, _keep_entropy = _blob(_ENTROPY)
    out = _blob_class()()
    flags = 0x01                      # CRYPTPROTECT_UI_FORBIDDEN: never show a window
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(blob_in), APP_NAME, ctypes.byref(entropy), None, None, flags,
                                      ctypes.byref(out))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, ctypes.byref(entropy), None, None, flags,
                                        ctypes.byref(out))
    if not ok:
        raise OSError("DPAPI refused the data")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


# --------------------------------------------------------------------------- the file
def _load() -> Dict[str, str]:
    try:
        data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        return {str(k): str(v) for k, v in items.items()} if isinstance(items, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(items: Dict[str, str]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SECRETS_FILE.with_name(SECRETS_FILE.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"version": 1, "note": "encrypted for one Windows account; of no use elsewhere",
                               "items": items}, indent=1), encoding="utf-8")
    os.replace(tmp, SECRETS_FILE)


def put(name: str, value: str) -> None:
    """Store a value; an empty one removes the entry."""
    value = (value or "").strip()
    with _lock:
        items = _load()
        if not value:
            items.pop(name, None)
        else:
            if not available():
                raise OSError("no protected storage on this system")
            items[name] = base64.b64encode(_crypt(value.encode("utf-8"), True)).decode("ascii")
        _save(items)


def saved(name: str) -> str:
    """The stored value, or "" when there is none or it cannot be read under this account."""
    with _lock:
        raw = _load().get(name)
    if not raw or not available():
        return ""
    try:
        return _crypt(base64.b64decode(raw), False).decode("utf-8")
    except (OSError, ValueError):
        return ""


def from_env(name: str) -> str:
    for var in ENV_KEYS.get(name, ()):
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    return ""


def get(name: str) -> str:
    """The key of a provider: the saved one first, then the environment."""
    return saved(name) or from_env(name)


def source(name: str) -> str:
    """Where the key comes from: "saved", "env" or ""."""
    if saved(name):
        return "saved"
    return "env" if from_env(name) else ""


def hint(name: str) -> str:
    """The tail of a key, enough to tell two keys apart and nothing more."""
    value = get(name)
    if not value:
        return ""
    return "…" + value[-4:] if len(value) >= 12 else "…"


# --------------------------------------------------------------------------- proxy
def check_proxy(url: str) -> str:
    """A proxy address brought to the form the programs understand; ValueError when it is not one.

    Only http(s) proxies: neither the Python library nor the command-line programs the app starts
    work through a SOCKS proxy given this way.
    """
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError("scheme")
    if not parts.hostname:
        raise ValueError("host")
    try:
        parts.port
    except ValueError:
        raise ValueError("port") from None
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def proxy() -> str:
    return saved(PROXY)


def proxy_hint() -> str:
    """The proxy without the name and password that may be part of it."""
    url = proxy()
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
        return f"{parts.scheme}://{host}" + (f":{parts.port}" if parts.port else "") + (" (+ login)" if parts.username else "")
    except ValueError:
        return "…"


def proxy_for(pid: str) -> Optional[str]:
    """The proxy a provider must use, or None for a direct connection."""
    from . import settings
    return (proxy() or None) if settings.proxied(pid) else None
