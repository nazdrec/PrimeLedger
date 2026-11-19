"""Claude through the Anthropic API, with the user's own key (official `anthropic` library).

One request per screenshot: the tiles go in as images, the answer is constrained to the JSON
schema (structured outputs).  The key is read from the vault (or the usual ANTHROPIC_API_KEY
variable) and never logged.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import vault
from ..i18n import tr
from .base import ApiProvider, ProviderError, Task, image_part, parse_json_answer, scrub

MAX_TOKENS = 16000
EFFORT = "low"                   # reading a grid of captions: the same effort the Claude Code path was checked with
# Models whose safety classifiers may decline a request: for them the API can re-run the request on
# another model inside the same call (opt-in, beta).
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")


def sdk():
    try:
        import anthropic
        return anthropic
    except ImportError:
        return None


class AnthropicApi(ApiProvider):
    id = "anthropic_api"
    default_model = "claude-opus-5-5"
    models = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
    default_base_url = "https://api.anthropic.com"

    def status(self, force: bool = False) -> Dict[str, Any]:
        st = super().status(force)
        if sdk() is None:
            st.update({"ready": False, "reason": "no_sdk"})
        return st

    def _client(self):
        anthropic = sdk()
        if anthropic is None:
            raise ProviderError(tr("Для Claude API нужна библиотека anthropic: выполните «pip install anthropic» "
                                   "или пользуйтесь готовым exe."), "no_sdk")
        self._need_key()
        options: Dict[str, Any] = {"timeout": 180.0, "max_retries": 2}
        saved = vault.saved(self.id)
        if saved:
            options["api_key"] = saved          # otherwise the library reads ANTHROPIC_API_KEY itself
        if self.base_url() != self.default_base_url:
            options["base_url"] = self.base_url()
        proxy = self.proxy()
        if proxy:
            options["http_client"] = anthropic.DefaultHttpxClient(proxy=proxy)
        return anthropic, anthropic.Anthropic(**options)

    def _fail(self, anthropic, exc: Exception) -> ProviderError:
        """An exception of the library as a problem the user can act on (most specific first)."""
        detail = scrub(str(getattr(exc, "message", "") or exc)[:400], self.key())
        if isinstance(exc, anthropic.AuthenticationError):
            return ProviderError(tr("Сервис не принял API-ключ: проверьте его в настройках. {0}", detail), "bad_key")
        if isinstance(exc, anthropic.PermissionDeniedError):
            return ProviderError(tr("Сервис отказал в доступе (403): проверьте ключ и права на модель. {0}", detail), "bad_key")
        if isinstance(exc, anthropic.NotFoundError):
            return ProviderError(tr("Сервис не знает такую модель или адрес: проверьте модель в настройках. {0}", detail), "model")
        if isinstance(exc, anthropic.RateLimitError):
            return ProviderError(tr("Сервис просит подождать: слишком много запросов. {0}", detail), "rate")
        if isinstance(exc, anthropic.BadRequestError):
            if "credit balance" in detail.lower() or "billing" in detail.lower():
                return ProviderError(tr("На счёте сервиса закончились средства или квота: {0}", detail), "quota")
            return ProviderError(tr("Сервис отклонил запрос ({0}): {1}", 400, detail), "error")
        if isinstance(exc, anthropic.APITimeoutError):
            return ProviderError(tr("Сервис не ответил за отведённое время"), "timeout")
        if isinstance(exc, anthropic.APIConnectionError):
            return ProviderError(tr("Нет связи с сервисом: {0}. Проверьте интернет; если сервис недоступен напрямую, "
                                    "включите для него прокси в настройках.", detail), "network")
        if isinstance(exc, anthropic.APIStatusError):
            status = getattr(exc, "status_code", 0)
            if status >= 500:
                return ProviderError(tr("Сервис временно не отвечает ({0}). Попробуйте позже. {1}", status, detail), "network")
            return ProviderError(tr("Сервис отклонил запрос ({0}): {1}", status, detail), "error")
        return ProviderError(detail or exc.__class__.__name__, "error")

    def check(self) -> Dict[str, Any]:
        """Ask for the list of models: free of charge, proves the key and the connection."""
        try:
            anthropic, client = self._client()
        except ProviderError as exc:
            return {"ok": False, "message": str(exc), "models": []}
        try:
            ids = [m.id for m in client.models.list()]
        except anthropic.APIError as exc:
            return {"ok": False, "message": str(self._fail(anthropic, exc)), "models": []}
        ids = [i for i in ids if i.startswith("claude-")]
        return {"ok": True, "message": tr("Ключ принят, моделей доступно: {0}.", len(ids)), "models": ids}

    def read(self, work_dir: Path, tiles: List[Path], task: Task, holder: Optional[list] = None) -> Dict[str, Any]:
        anthropic, client = self._client()
        content: List[Dict[str, Any]] = []
        for tile in tiles:
            mime, data = image_part(tile)
            content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
        content.append({"type": "text", "text": task.prompt_attached})
        model = self.model()
        request: Dict[str, Any] = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "system": task.system_attached,
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": task.schema}},
            "messages": [{"role": "user", "content": content}],
        }
        # Three wordings of the same request, from the fullest down: a model or an API gateway that
        # does not know an optional part answers 400, and the next wording leaves that part out.
        attempts = []
        if model in FALLBACK_MODELS:
            attempts.append(lambda: client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **request))
        attempts.append(lambda: client.messages.create(**request))
        plain = dict(request, output_config={"format": request["output_config"]["format"]})
        attempts.append(lambda: client.messages.create(**plain))
        started = time.time()
        response = None
        for n, attempt in enumerate(attempts):
            try:
                response = attempt()
                break
            except anthropic.BadRequestError as exc:
                if n == len(attempts) - 1:
                    raise self._fail(anthropic, exc) from None
            except anthropic.APIError as exc:
                raise self._fail(anthropic, exc) from None
        if response.stop_reason == "refusal":
            raise ProviderError(tr("Модель отказалась читать этот скриншот"), "refused")
        if response.stop_reason == "max_tokens":
            raise ProviderError(tr("Ответ модели оборвался: он не поместился в отведённый объём"), "bad_output")
        text = next((block.text for block in response.content if block.type == "text"), "")
        return {"data": parse_json_answer(text), "seconds": round(time.time() - started, 1)}
