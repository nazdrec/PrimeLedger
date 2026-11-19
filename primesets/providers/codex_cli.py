"""Codex, under the user's own ChatGPT sign-in.

The app starts `codex exec` (non-interactive mode): the tiles of one screenshot are attached
to the request, the answer must follow the JSON schema, the sandbox is read-only, nothing is
saved as a session and the user's own Codex configuration (rules, MCP servers) is left out.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import settings
from ..i18n import tr
from . import cli
from .base import CALL_TIMEOUT, Provider, ProviderError, Task, parse_json_answer

DEFAULT_EFFORT = "low"


def find() -> Optional[List[str]]:
    """Command prefix that starts Codex, or None: an override, PATH, then the copy of the Codex app."""
    cmd = cli.override("PRIMESETS_CODEX_CMD")
    if cmd:
        return cmd
    custom = settings.extra("codex_path")
    if isinstance(custom, str) and Path(custom).is_file():
        return [custom]
    on_path = shutil.which("codex")
    if on_path:
        return [on_path]
    base = os.environ.get("LOCALAPPDATA")
    if base:
        found = [p for p in Path(base).glob("OpenAI/Codex/bin/*/codex.exe") if p.is_file()]
        if found:
            return [str(max(found, key=lambda p: p.stat().st_mtime))]
    return None


def _network_trouble(text: str) -> bool:
    low = text.lower()
    return any(mark in low for mark in ("403 forbidden", "failed to refresh token", "reconnecting", "error sending request",
                                        "connection", "timed out", "dns error", "stream disconnected"))


class CodexCli(Provider):
    id = "codex_cli"
    kind = "subscription"
    default_model = ""           # whatever Codex itself uses by default for this account
    models: List[str] = []

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {"at": 0.0, "value": None}

    def env(self) -> Dict[str, str]:
        """OPENAI_API_KEY and friends are dropped: the ChatGPT sign-in is used, never a key that happens to be set."""
        return cli.child_env(("OPENAI", "CODEX", "PRIMESETS"), keep=("CODEX_HOME",), proxy=self.proxy())

    def forget_status(self) -> None:
        with self._lock:
            self._cache["value"] = None

    def status(self, force: bool = False) -> Dict[str, Any]:
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
                    code, out, err = cli.run(cmd + ["login", "status"], self.env(), timeout=25, who="Codex")
                    text = (out + "\n" + err).strip()
                    low = text.lower()
                    value["logged_in"] = code == 0 and "logged in" in low and "not logged in" not in low
                    if value["logged_in"]:
                        value["method"] = "chatgpt" if "chatgpt" in low else "api key" if "api key" in low else None
                    elif "not logged in" in low or code != 0:
                        value["reason"] = "login"
                    else:
                        value["error"], value["reason"] = text[:300] or tr("Codex не вернул состояние входа"), "error"
                except (OSError, ProviderError) as exc:
                    value["error"], value["reason"] = str(exc), "error"
            value["ready"] = bool(value["available"] and value["logged_in"])
            self._cache.update({"at": time.time(), "value": value})
            return dict(value)

    def check(self) -> Dict[str, Any]:
        st = self.status(force=True)
        if st["ready"]:
            return {"ok": True, "message": tr("Codex найден, вход выполнен. Связь с сервисом проверяется при первом распознавании."),
                    "models": []}
        if st["reason"] == "no_cli":
            return {"ok": False, "message": tr("Codex не найден на этом компьютере"), "models": []}
        if st["reason"] == "login":
            return {"ok": False, "message": tr("Codex найден, но вход не выполнен."), "models": []}
        return {"ok": False, "message": st["error"] or tr("Не удалось проверить Codex"), "models": []}

    def login(self) -> None:
        """A console window where the user signs in themself (browser).  The app never sees credentials."""
        cmd = find()
        if not cmd:
            raise ProviderError(tr("Codex не найден на этом компьютере"), "no_cli")
        cli.open_console(cmd + ["login"], self.env())
        self.forget_status()

    def read(self, work_dir: Path, tiles: List[Path], task: Task, holder: Optional[list] = None) -> Dict[str, Any]:
        cmd = find()
        if not cmd:
            raise ProviderError(tr("Codex не найден на этом компьютере"), "no_cli")
        schema_file = work_dir / "answer.schema.json"
        answer_file = work_dir / "answer.json"
        schema_file.write_text(json.dumps(task.schema, ensure_ascii=True), encoding="utf-8")
        try:
            answer_file.unlink()
        except OSError:
            pass
        argv = cmd + ["exec"]
        for tile in tiles:                      # never last: the option takes several values
            argv += ["--image", str(tile)]
        argv += [
            "--skip-git-repo-check",            # the work folder is a temporary one, not a repository
            "--ephemeral",                      # no session is saved
            "--ignore-user-config",             # no MCP servers or other additions of the user's own setup
            "--ignore-rules",
            "--sandbox", "read-only",
            "--color", "never",
            "--cd", str(work_dir),
            "-c", f'model_reasoning_effort="{settings.extra("recognize_effort") or DEFAULT_EFFORT}"',
            "--output-schema", str(schema_file),
            "--output-last-message", str(answer_file),
        ]
        if self.model():
            argv += ["--model", self.model()]
        argv += ["-"]                           # the request itself comes through stdin
        started = time.time()
        code, out, err = cli.run(argv, self.env(), cwd=work_dir, timeout=CALL_TIMEOUT,
                                 stdin_text=task.system_attached + "\n\n" + task.prompt_attached, holder=holder, who="Codex")
        try:
            text = answer_file.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if code != 0 or not text.strip():
            tail = (err or out).strip()
            low = tail.lower()
            if "not logged in" in low or "login required" in low or "401 unauthorized" in low:
                self.forget_status()
                raise ProviderError(tr("Нужен вход в Codex"), "login")
            if _network_trouble(tail):
                raise ProviderError(tr("Codex не смог связаться со своим сервисом. Если он недоступен напрямую, включите "
                                       "для Codex прокси в настройках. Подробности: {0}", tail[-300:]), "network")
            raise ProviderError(tr("Codex завершился с ошибкой: {0}", tail[-400:] or f"exit {code}"), "error")
        return {"data": parse_json_answer(text), "seconds": round(time.time() - started, 1)}
