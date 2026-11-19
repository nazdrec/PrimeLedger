"""Claude Code, under the user's own subscription login.

The app starts `claude -p` (non-interactive mode): each call gets one screenshot cut into
tiles, may use only the Read tool, is confined to the temporary folder that holds those tiles
and runs with all customisations switched off.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import settings
from ..i18n import tr
from . import cli
from .base import CALL_TIMEOUT, Provider, ProviderError, Task

DEFAULT_EFFORT = "low"


def _version_key(path: Path):
    nums = re.findall(r"\d+", path.parent.parent.name)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    return tuple(int(n) for n in nums[:4]), mtime


def find() -> Optional[List[str]]:
    """Command prefix that starts Claude Code, or None.

    Order: an explicit override, a standalone install on PATH, the usual native-install
    location, and finally the copy that ships inside the Claude desktop app (newest version).
    """
    cmd = cli.override("PRIMESETS_CLAUDE_CMD")
    if cmd:
        return cmd
    custom = settings.extra("claude_path")
    if isinstance(custom, str) and Path(custom).is_file():
        return [custom]
    on_path = shutil.which("claude")
    if on_path:
        return [on_path]
    local = Path.home() / ".local" / "bin" / "claude.exe"
    if local.is_file():
        return [str(local)]
    base = os.environ.get("LOCALAPPDATA")
    if base:
        found = list(Path(base).glob("Claude-Data/*/claude-code/*/*/claude.exe"))
        if found:
            return [str(max(found, key=_version_key))]
    return None


class ClaudeCli(Provider):
    id = "claude_cli"
    kind = "subscription"
    default_model = "sonnet"
    models = ["sonnet", "opus", "haiku"]

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {"at": 0.0, "value": None}

    def env(self) -> Dict[str, str]:
        """Dropping ANTHROPIC_* guarantees the subscription login is used (never an API key that
        happens to be set); dropping CLAUDE_* keeps a parent Claude session from leaking in."""
        return cli.child_env(("CLAUDE", "ANTHROPIC", "PRIMESETS"), keep=("CLAUDE_CONFIG_DIR",), proxy=self.proxy())

    def forget_status(self) -> None:
        with self._lock:
            self._cache["value"] = None

    def status(self, force: bool = False) -> Dict[str, Any]:
        """Is Claude Code present and signed in?  Cached for a short while: the check starts a process."""
        with self._lock:
            if not force and self._cache["value"] is not None and time.time() - self._cache["at"] < 45:
                value = dict(self._cache["value"])
                value.update({"model": self.model(), "use_proxy": settings.proxied(self.id)})
                return value
            value = self._base_status()
            value.update({"available": False, "logged_in": False, "path": None, "method": None})
            cmd = find()
            if not cmd:
                value["reason"] = "no_cli"
            else:
                value["available"] = True
                value["path"] = cmd[-1] if len(cmd) > 1 else cmd[0]
                try:
                    _code, out, err = cli.run(cmd + ["auth", "status"], self.env(), timeout=25, who="Claude Code")
                    info = cli.last_json(out) or {}
                    value["logged_in"] = bool(info.get("loggedIn"))
                    value["method"] = info.get("authMethod")
                    if not info:
                        value["error"] = (err or out).strip()[:300] or tr("Claude Code не вернул состояние входа")
                        value["reason"] = "error"
                    elif not value["logged_in"]:
                        value["reason"] = "login"
                except (OSError, ProviderError) as exc:
                    value["error"], value["reason"] = str(exc), "error"
            value["ready"] = bool(value["available"] and value["logged_in"])
            self._cache.update({"at": time.time(), "value": value})
            return dict(value)

    def check(self) -> Dict[str, Any]:
        st = self.status(force=True)
        if st["ready"]:
            return {"ok": True, "message": tr("Claude Code найден, вход выполнен."), "models": list(self.models)}
        if st["reason"] == "no_cli":
            return {"ok": False, "message": tr("Claude Code не найден на этом компьютере"), "models": []}
        if st["reason"] == "login":
            return {"ok": False, "message": tr("Claude Code найден, но вход не выполнен."), "models": []}
        return {"ok": False, "message": st["error"] or tr("Не удалось проверить Claude Code"), "models": []}

    def login(self) -> None:
        """Open a console window where the user signs in themself (browser OAuth).  The app never sees credentials."""
        cmd = find()
        if not cmd:
            raise ProviderError(tr("Claude Code не найден на этом компьютере"), "no_cli")
        cli.open_console(cmd + ["auth", "login"], self.env())
        self.forget_status()

    def read(self, work_dir: Path, tiles: List[Path], task: Task, holder: Optional[list] = None) -> Dict[str, Any]:
        cmd = find()
        if not cmd:
            raise ProviderError(tr("Claude Code не найден на этом компьютере"), "no_cli")
        argv = cmd + [
            "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(task.schema, ensure_ascii=True),
            "--system-prompt", task.system_files,
            "--tools", "Read",
            "--allowedTools", "Read",
            "--permission-prompts", "none",
            "--restricted",                 # file tools confined to work_dir, no command tools, user settings ignored
            "--safe-mode",                  # no CLAUDE.md, plugins, hooks or MCP servers
            "--strict-mcp-config",
            "--no-session-persistence",
            "--model", self.model(),
            "--effort", str(settings.extra("recognize_effort") or DEFAULT_EFFORT),
        ]
        _code, out, err = cli.run(argv, self.env(), cwd=work_dir, timeout=CALL_TIMEOUT,
                                  stdin_text=task.files_text(tiles), holder=holder, who="Claude Code")
        box = cli.last_json(out)
        if box is None:
            raise ProviderError(tr("Claude Code вернул непонятный ответ: {0}", (err or out).strip()[:300]), "bad_output")
        text = str(box.get("result") or "")
        if box.get("is_error"):
            if "not logged in" in text.lower() or "/login" in text.lower():
                self.forget_status()        # the remembered "signed in" is no longer true
                raise ProviderError(tr("Нужен вход в Claude Code"), "login")
            raise ProviderError(text.strip()[:400] or tr("Claude Code сообщил об ошибке"), "error")
        data = box.get("structured_output")
        if not isinstance(data, dict):
            match = re.search(r"\{.*\}", text, flags=re.S)
            try:
                data = json.loads(match.group(0)) if match else None
            except ValueError:
                data = None
        if not isinstance(data, dict):
            raise ProviderError(tr("В ответе нет данных в нужном формате: {0}", text.strip()[:300]), "bad_output")
        return {"data": data, "seconds": round((box.get("duration_ms") or 0) / 1000, 1)}
