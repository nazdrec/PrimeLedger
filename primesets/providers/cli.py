"""Starting a command-line program of the user's (Claude Code, Codex) without a window.

The child gets the user's own environment minus anything that would change which account it
uses, plus the proxy when the settings say this program goes through one.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..i18n import tr
from .base import ProviderError

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010
PROXY_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")


def child_env(drop_prefixes: Iterable[str], keep: Iterable[str] = (), proxy: Optional[str] = None) -> Dict[str, str]:
    """The user's environment without the variables whose names start with one of drop_prefixes."""
    keep = {k.upper() for k in keep}
    prefixes = tuple(p.upper() for p in drop_prefixes)
    env = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if upper in keep or not upper.startswith(prefixes):
            env[key] = value
    if proxy:
        for var in PROXY_VARS:
            env[var] = proxy
    return env


def run(cmd: List[str], env: Dict[str, str], cwd: Optional[Path] = None, timeout: float = 30,
        stdin_text: Optional[str] = None, holder: Optional[list] = None, who: str = ""):
    """-> (exit code, stdout, stderr).  holder collects the running process so a cancel can kill it."""
    flags = CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(cwd) if cwd else None, env=env,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
    except OSError as exc:
        raise ProviderError(tr("Не удалось запустить {0}: {1}", who or cmd[0], exc), "no_cli") from None
    if holder is not None:
        holder.append(proc)
    try:
        out, err = proc.communicate(stdin_text.encode("utf-8") if stdin_text is not None else None, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise ProviderError(tr("{0} не ответил за отведённое время", who or cmd[0]), "timeout") from None
    finally:
        if holder is not None and proc in holder:
            holder.remove(proc)
    return proc.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def open_console(cmd: List[str], env: Dict[str, str]) -> None:
    """A console window where the user does something themself (signs in); it stays until a key is pressed."""
    flags = CREATE_NEW_CONSOLE if os.name == "nt" else 0
    subprocess.Popen(["cmd.exe", "/c"] + cmd + ["&", "pause"], env=env, creationflags=flags)


def override(var: str) -> Optional[List[str]]:
    """A command given through an environment variable (the tests use it): a JSON list or a plain path."""
    value = os.environ.get(var)
    if not value:
        return None
    try:
        cmd = json.loads(value)
        if isinstance(cmd, list) and cmd:
            return [str(c) for c in cmd]
    except ValueError:
        pass
    return [value]


def last_json(text: str) -> Optional[dict]:
    """The last line of the output that is a JSON object (or the whole output if it is one)."""
    for line in reversed([ln.strip() for ln in text.splitlines() if ln.strip()]):
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    return obj
            except ValueError:
                continue
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except ValueError:
        return None
