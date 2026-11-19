"""JSON over HTTPS for the API providers that are called without a vendor library.

One place for the proxy, the retries and for turning HTTP failures into messages the user can
act on.  Keys travel only in request headers and are never logged or put into an error text.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from .. import APP_NAME
from ..i18n import tr
from .base import ProviderError, scrub

RETRY_STATUS = (408, 409, 429, 500, 502, 503, 504, 529)
MAX_WAIT = 30.0


def _opener(proxy: Optional[str]):
    if proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener()          # the system's own proxy settings, if any


def _message(body: Any, raw: str) -> str:
    """The provider's own explanation, wherever its error format keeps it."""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("code") or err.get("type") or "")[:400]
        if isinstance(err, str):
            return err[:400]
        if isinstance(body.get("message"), str):
            return body["message"][:400]
    return raw.strip()[:300]


def explain(status: int, detail: str) -> ProviderError:
    """An HTTP error as a problem the user can do something about."""
    low = detail.lower()
    if status == 401:
        return ProviderError(tr("Сервис не принял API-ключ: проверьте его в настройках. {0}", detail), "bad_key")
    if status == 403:
        if "country" in low or "region" in low or "territory" in low or "location" in low:
            return ProviderError(tr("Сервис недоступен из вашего региона: включите для него прокси в настройках. {0}", detail), "network")
        return ProviderError(tr("Сервис отказал в доступе (403): проверьте ключ и права на модель. {0}", detail), "bad_key")
    if status == 402 or "insufficient" in low or "billing" in low or "credit balance" in low:
        return ProviderError(tr("На счёте сервиса закончились средства или квота: {0}", detail), "quota")
    if status == 404:
        return ProviderError(tr("Сервис не знает такую модель или адрес: проверьте модель в настройках. {0}", detail), "model")
    if status == 429:
        return ProviderError(tr("Сервис просит подождать: слишком много запросов. {0}", detail), "rate")
    if status >= 500:
        return ProviderError(tr("Сервис временно не отвечает ({0}). Попробуйте позже. {1}", status, detail), "network")
    return ProviderError(tr("Сервис отклонил запрос ({0}): {1}", status, detail), "error")


def call(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]] = None,
         proxy: Optional[str] = None, timeout: float = 180.0, retries: int = 2) -> Tuple[Dict[str, Any], float]:
    """Send one request, return (JSON body, seconds).  Raises ProviderError."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    head = {"Accept": "application/json", "User-Agent": f"{APP_NAME} (python-urllib)"}
    if data is not None:
        head["Content-Type"] = "application/json"
    head.update(headers)
    opener = _opener(proxy)
    started = time.time()
    attempt = 0
    while True:
        attempt += 1
        req = urllib.request.Request(url, data=data, headers=head, method=method)
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            try:
                body = json.loads(raw)
            except ValueError:
                raise ProviderError(tr("Сервис ответил не в формате JSON: {0}", raw[:200]), "bad_output") from None
            if not isinstance(body, dict):
                raise ProviderError(tr("Сервис ответил не в формате JSON: {0}", raw[:200]), "bad_output")
            return body, round(time.time() - started, 1)
        except urllib.error.HTTPError as exc:
            raw = ""
            try:
                raw = exc.read().decode("utf-8", "replace")
            except Exception:
                pass
            try:
                body = json.loads(raw)
            except ValueError:
                body = None
            status = exc.code
            if status in RETRY_STATUS and attempt <= retries:
                wait = min(MAX_WAIT, 2.0 * attempt)
                try:
                    wait = min(MAX_WAIT, max(wait, float(exc.headers.get("Retry-After") or 0)))
                except (TypeError, ValueError):
                    pass
                time.sleep(wait)
                continue
            secrets = [v.split(" ", 1)[-1] for k, v in headers.items() if k.lower() in ("authorization", "x-goog-api-key", "x-api-key")]
            raise explain(status, scrub(_message(body, raw), *secrets)) from None
        except (socket.timeout, TimeoutError):
            raise ProviderError(tr("Сервис не ответил за отведённое время"), "timeout") from None
        except (urllib.error.URLError, OSError) as exc:
            if attempt <= retries:
                time.sleep(1.5 * attempt)
                continue
            reason = getattr(exc, "reason", exc)
            raise ProviderError(tr("Нет связи с сервисом: {0}. Проверьте интернет; если сервис недоступен напрямую, "
                                   "включите для него прокси в настройках.", str(reason)[:200]), "network") from None
