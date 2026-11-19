"""Gemini through the Google AI API (Interactions API), with the user's own key.

One request per screenshot: the tiles go in as inline images, the answer is constrained to the
JSON schema (response_format).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..i18n import tr
from . import http
from .base import ApiProvider, ProviderError, Task, image_part, parse_json_answer

MAX_TOKENS = 16000
API_REVISION = "2026-05-20"


class GeminiApi(ApiProvider):
    id = "gemini_api"
    default_model = "gemini-4-hydrogen"
    models = ["gemini-4-hydrogen", "gemini-4-argon", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"

    def _headers(self) -> Dict[str, str]:
        return {"x-goog-api-key": self._need_key(), "Api-Revision": API_REVISION}

    def check(self) -> Dict[str, Any]:
        try:
            body, _ = http.call("GET", self.base_url() + "/models?pageSize=200", self._headers(), proxy=self.proxy(),
                                timeout=40, retries=1)
        except ProviderError as exc:
            return {"ok": False, "message": str(exc), "models": []}
        ids = []
        for m in body.get("models") or []:
            name = str(m.get("name") or "") if isinstance(m, dict) else ""
            name = name.split("/", 1)[1] if name.startswith("models/") else name
            if name.startswith("gemini-") and not any(w in name for w in ("embedding", "image", "tts", "audio", "live")):
                ids.append(name)
        ids.sort(reverse=True)
        return {"ok": True, "message": tr("Ключ принят, моделей доступно: {0}.", len(ids)), "models": ids}

    def read(self, work_dir: Path, tiles: List[Path], task: Task, holder: Optional[list] = None) -> Dict[str, Any]:
        headers = self._headers()
        parts: List[Dict[str, Any]] = [{"type": "text", "text": task.prompt_attached}]
        for tile in tiles:
            mime, data = image_part(tile)
            parts.append({"type": "image", "data": data, "mime_type": mime})
        payload: Dict[str, Any] = {
            "model": self.model(),
            "system_instruction": task.system_attached,
            "input": parts,
            "response_format": {"type": "text", "mime_type": "application/json", "schema": task.schema},
            "generation_config": {"thinking_level": "low", "max_output_tokens": MAX_TOKENS},
            "store": False,
        }
        url = self.base_url() + "/interactions"
        try:
            body, seconds = http.call("POST", url, headers, payload, proxy=self.proxy())
        except ProviderError as exc:
            # a model without this thinking level rejects the parameter: ask again without it
            if exc.code != "error" or "thinking" not in str(exc).lower():
                raise
            payload["generation_config"].pop("thinking_level")
            body, seconds = http.call("POST", url, headers, payload, proxy=self.proxy())
        status = body.get("status")
        if status in ("failed", "cancelled"):
            err = body.get("error") if isinstance(body.get("error"), dict) else {}
            raise ProviderError(str(err.get("message") or tr("Сервис не выполнил запрос"))[:400], "error")
        texts: List[str] = []
        for step in body.get("steps") or body.get("outputs") or []:
            if not isinstance(step, dict):
                continue
            if step.get("type") in ("model_output", None) and isinstance(step.get("content"), list):
                texts += [str(p.get("text") or "") for p in step["content"] if isinstance(p, dict) and p.get("type") == "text"]
            elif step.get("type") == "text":
                texts.append(str(step.get("text") or ""))
        text = "".join(texts) or str(body.get("output_text") or "")
        if not text.strip() and status == "incomplete":
            raise ProviderError(tr("Ответ модели оборвался: он не поместился в отведённый объём"), "bad_output")
        return {"data": parse_json_answer(text), "seconds": seconds}
