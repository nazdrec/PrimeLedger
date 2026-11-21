"""What the user chose in the settings dialog: data/settings.json.

Nothing secret is kept here -- API keys and the proxy address live in vault.py, encrypted.
Keys the dialog does not know (hand-made additions such as "claude_path") are left in the
file as they are.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional

from . import config, i18n

SETTINGS_FILE = config.DATA_DIR / "settings.json"
PROVIDERS = ("claude_cli", "codex_cli", "anthropic_api", "openai_api", "deepseek_api", "gemini_api")
DEFAULT_PROVIDER = "claude_cli"
DEFAULT_PARALLEL = 3

DEFAULTS: Dict[str, Any] = {
    "language": "",            # "" -- the language of Windows, if the app speaks it
    "game_language": "",       # "" -- the same as the interface
    "provider": DEFAULT_PROVIDER,
    "models": {},              # provider -> model ("" or absent: the provider's own default)
    "base_urls": {},           # provider -> another address of its API (a compatible gateway)
    "use_proxy": [],           # providers that go through the proxy kept in the vault
    "parallel": DEFAULT_PARALLEL,
    "check_updates": True,     # ask the page of the project once at the start whether a newer version is out
    "welcomed": False,         # the first-start guide has been shown
}

_lock = threading.RLock()
_cache: Dict[str, Any] = {"mtime": None, "data": None}


def _read_file() -> Dict[str, Any]:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _clean(raw: Dict[str, Any]) -> Dict[str, Any]:
    """The file's content with every known key brought to a valid value."""
    data = dict(raw)
    data["language"] = raw.get("language") if i18n.valid(raw.get("language")) else ""
    data["game_language"] = raw.get("game_language") if i18n.valid(raw.get("game_language")) else ""
    data["provider"] = raw.get("provider") if raw.get("provider") in PROVIDERS else DEFAULT_PROVIDER
    models = raw.get("models") if isinstance(raw.get("models"), dict) else {}
    # settings written by hand for the first version of the app
    if "claude_cli" not in models and isinstance(raw.get("recognize_model"), str) and raw["recognize_model"]:
        models = {**models, "claude_cli": raw["recognize_model"]}
    data["models"] = {k: str(v)[:100] for k, v in models.items() if k in PROVIDERS and isinstance(v, str) and v.strip()}
    urls = raw.get("base_urls") if isinstance(raw.get("base_urls"), dict) else {}
    data["base_urls"] = {k: str(v)[:300] for k, v in urls.items() if k in PROVIDERS and isinstance(v, str) and v.strip()}
    proxied = raw.get("use_proxy") if isinstance(raw.get("use_proxy"), list) else []
    data["use_proxy"] = [p for p in PROVIDERS if p in proxied]
    try:
        parallel = int(raw.get("parallel") or raw.get("recognize_parallel") or DEFAULT_PARALLEL)
    except (TypeError, ValueError):
        parallel = DEFAULT_PARALLEL
    data["parallel"] = max(1, min(4, parallel))
    data["check_updates"] = raw.get("check_updates") is not False
    data["welcomed"] = raw.get("welcomed") is True
    return data


def load() -> Dict[str, Any]:
    with _lock:
        try:
            mtime: Optional[float] = SETTINGS_FILE.stat().st_mtime
        except OSError:
            mtime = None
        if _cache["data"] is None or _cache["mtime"] != mtime:
            _cache.update({"mtime": mtime, "data": _clean(_read_file())})
        return dict(_cache["data"])


def save(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge the given keys into the file.  Values are validated; unknown keys of the patch are ignored."""
    with _lock:
        data = _read_file()
        for key in ("language", "game_language", "provider", "parallel"):
            if key in patch:
                data[key] = patch[key]
        for key in ("check_updates", "welcomed"):
            if key in patch:
                data[key] = bool(patch[key])
        for key in ("models", "base_urls"):
            if isinstance(patch.get(key), dict):
                merged = dict(data.get(key) if isinstance(data.get(key), dict) else {})
                for pid, value in patch[key].items():
                    if pid not in PROVIDERS:
                        continue
                    if isinstance(value, str) and value.strip():
                        merged[pid] = value.strip()
                    else:
                        merged.pop(pid, None)
                data[key] = merged
        if isinstance(patch.get("use_proxy"), dict):
            current = set(data.get("use_proxy") if isinstance(data.get("use_proxy"), list) else [])
            for pid, on in patch["use_proxy"].items():
                if pid in PROVIDERS:
                    (current.add if on else current.discard)(pid)
            data["use_proxy"] = [p for p in PROVIDERS if p in current]
        data = _clean(data)
        for legacy in ("recognize_model", "recognize_parallel"):
            data.pop(legacy, None)
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, SETTINGS_FILE)
        _cache.update({"mtime": None, "data": None})
        return load()


def language() -> str:
    """The language of the interface."""
    return load()["language"] or i18n.system_language()


def game_language() -> str:
    """The language of the game client the screenshots come from."""
    return load()["game_language"] or language()


def provider() -> str:
    return load()["provider"]


def model(pid: str) -> str:
    return load()["models"].get(pid, "")


def base_url(pid: str) -> str:
    return load()["base_urls"].get(pid, "")


def proxied(pid: str) -> bool:
    return pid in load()["use_proxy"]


def parallel() -> int:
    return load()["parallel"]


def check_updates() -> bool:
    return bool(load()["check_updates"])


def welcomed() -> bool:
    return bool(load()["welcomed"])


def extra(key: str) -> Any:
    """A hand-made key of the file (claude_path, codex_path, game_screenshots_dir)."""
    return load().get(key)


def languages() -> List[Dict[str, str]]:
    return [{"code": code, "name": info["name"]} for code, info in i18n.LANGS.items()]
