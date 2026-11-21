"""What every way of reading a screenshot has in common.

A provider gets the pieces of ONE screenshot and a task (prompts + the answer schema) and
returns the model's answer as a dict.  Two kinds:
  * "subscription" -- a command-line program the user is signed in to with their own account
    (Claude Code, Codex); the app starts it and never sees the credentials;
  * "api" -- a web API called with the user's own key (kept in vault.py).
Whatever a picture says is data: the answer is parsed as JSON and checked, never executed.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import settings, shots, vault
from ..i18n import tr

CALL_TIMEOUT = 300


class ProviderError(Exception):
    """A problem the user can act on; `code` tells the interface what to offer.

    login | no_cli | no_key | no_sdk   -- the connection is not set up
    bad_key | quota | rate | network | timeout | refused | model | bad_output | error
    """

    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


FATAL = ("login", "no_cli", "no_key", "no_sdk", "bad_key", "quota", "model")   # no point in trying the next screenshot


@dataclass
class Task:
    """One screenshot to read: the same request in two wordings."""
    system_files: str        # for a program that opens the pictures itself
    system_attached: str     # for a model that gets the pictures inside the request
    prompt_files: str        # {files} -- the list of file names
    prompt_attached: str
    schema: Dict[str, Any]
    grid_hint: str = ""      # [cols] -- how many tiles a row of this screenshot holds, when that is known

    def files_text(self, tiles: List[Path]) -> str:
        return self.prompt_files.format(files="\n".join(f"  {t.name}" for t in tiles))

    def with_grid(self, cols: int) -> "Task":
        """The same request for a screenshot on which the app has found the tile grid."""
        if not self.grid_hint:
            return self
        hint = self.grid_hint.replace("[cols]", str(int(cols)))
        return replace(self, prompt_files=self.prompt_files + hint, prompt_attached=self.prompt_attached + hint)


class Provider:
    id = ""
    kind = "api"                 # "api" | "subscription"
    default_model = ""
    models: List[str] = []       # what the dialog offers before the live list is asked for
    default_base_url = ""

    # -- settings ------------------------------------------------------------
    def model(self) -> str:
        return settings.model(self.id) or self.default_model

    def base_url(self) -> str:
        return (settings.base_url(self.id) or self.default_base_url).rstrip("/")

    def proxy(self) -> Optional[str]:
        return vault.proxy_for(self.id)

    # -- to be provided ------------------------------------------------------
    def status(self, force: bool = False) -> Dict[str, Any]:
        raise NotImplementedError

    def read(self, work_dir: Path, tiles: List[Path], task: Task, holder: Optional[list] = None) -> Dict[str, Any]:
        """-> {"data": the model's answer, "seconds": float}"""
        raise NotImplementedError

    def check(self) -> Dict[str, Any]:
        """The "Проверить" button: is the connection usable right now?  -> {"ok", "message", "models"}"""
        raise NotImplementedError

    def login(self) -> None:
        raise ProviderError(tr("Для этого подключения вход не нужен"), "error")

    # -- shared pieces ---------------------------------------------------------
    def _base_status(self) -> Dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "ready": False, "reason": "", "error": "",
                "model": self.model(), "default_model": self.default_model, "models": list(self.models),
                "pillow": shots.have_pillow(), "use_proxy": settings.proxied(self.id)}


class ApiProvider(Provider):
    kind = "api"

    def key(self) -> str:
        return vault.get(self.id)

    def status(self, force: bool = False) -> Dict[str, Any]:
        st = self._base_status()
        st.update({"has_key": bool(self.key()), "key_hint": vault.hint(self.id), "key_source": vault.source(self.id),
                   "base_url": settings.base_url(self.id), "default_base_url": self.default_base_url})
        if not st["has_key"]:
            st["reason"] = "no_key"
        else:
            st["ready"] = True
        return st

    def _need_key(self) -> str:
        key = self.key()
        if not key:
            raise ProviderError(tr("Не задан API-ключ: введите его в настройках"), "no_key")
        return key


# --------------------------------------------------------------------------- helpers for the API providers
def scrub(text: str, *secrets: str) -> str:
    """The text without the given secrets: some services quote the key back in an error message."""
    for secret in secrets:
        secret = (secret or "").strip()
        if len(secret) >= 6:
            text = text.replace(secret, "***")
    return text


def image_part(path: Path) -> tuple:
    """(media type, base64 text) of a picture file."""
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    if mime == "image/jpg":
        mime = "image/jpeg"
    return mime, base64.standard_b64encode(path.read_bytes()).decode("ascii")


def parse_json_answer(text: str) -> Dict[str, Any]:
    """The JSON object a model answered with; tolerant of a ```json fence around it."""
    text = (text or "").strip()
    if not text:
        raise ProviderError(tr("Модель вернула пустой ответ"), "bad_output")
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        try:
            data = json.loads(match.group(0)) if match else None
        except ValueError:
            data = None
    if not isinstance(data, dict):
        raise ProviderError(tr("В ответе нет данных в нужном формате: {0}", text[:300]), "bad_output")
    return data


def schema_text(schema: Dict[str, Any]) -> str:
    """The answer format in words, for a model whose API cannot enforce a schema."""
    return ("Answer with ONE JSON object and nothing else. It must follow this JSON Schema exactly "
            "(every listed field is required, no extra fields):\n" + json.dumps(schema, ensure_ascii=False))
