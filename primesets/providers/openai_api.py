"""ChatGPT models through the OpenAI API (Responses API), with the user's own key.

One request per screenshot: the tiles go in as images, the answer is constrained to the JSON
schema (Structured Outputs, strict).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..i18n import tr
from . import http
from .base import ApiProvider, ProviderError, Task, image_part, parse_json_answer

MAX_TOKENS = 16000
NOT_FOR_READING = ("image", "audio", "realtime", "tts", "transcribe", "search", "embedding", "instruct", "moderation",
                   "codex")


class OpenAiApi(ApiProvider):
    id = "openai_api"
    default_model = "gpt-6.2-astra"
    models = ["gpt-6.2-astra", "gpt-6-astra", "gpt-5.6-terra", "gpt-5.5", "gpt-5.4-mini"]
    default_base_url = "https://api.openai.com/v1"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": "Bearer " + self._need_key()}

    def check(self) -> Dict[str, Any]:
        """Ask for the list of models: free of charge, proves the key and the connection."""
        try:
            body, _ = http.call("GET", self.base_url() + "/models", self._headers(), proxy=self.proxy(), timeout=40, retries=1)
        except ProviderError as exc:
            return {"ok": False, "message": str(exc), "models": []}
        ids = sorted({str(m.get("id")) for m in body.get("data") or [] if isinstance(m, dict) and m.get("id")}, reverse=True)
        fit = [i for i in ids if i.startswith("gpt-") and not any(word in i for word in NOT_FOR_READING)]
        return {"ok": True, "message": tr("Ключ принят, моделей доступно: {0}.", len(fit or ids)), "models": fit or ids}

    def read(self, work_dir: Path, tiles: List[Path], task: Task, holder: Optional[list] = None) -> Dict[str, Any]:
        headers = self._headers()
        content: List[Dict[str, Any]] = [{"type": "input_text", "text": task.prompt_attached}]
        for tile in tiles:
            mime, data = image_part(tile)
            content.append({"type": "input_image", "image_url": f"data:{mime};base64,{data}", "detail": "high"})
        payload: Dict[str, Any] = {
            "model": self.model(),
            "instructions": task.system_attached,
            "input": [{"role": "user", "content": content}],
            "text": {"format": {"type": "json_schema", "name": "warframe_screenshot", "schema": task.schema, "strict": True}},
            "reasoning": {"effort": "low"},
            "max_output_tokens": MAX_TOKENS,
            "store": False,
        }
        url = self.base_url() + "/responses"
        try:
            body, seconds = http.call("POST", url, headers, payload, proxy=self.proxy())
        except ProviderError as exc:
            # a model without adjustable reasoning rejects the parameter: ask again without it
            if exc.code != "error" or "reasoning" not in str(exc).lower():
                raise
            payload.pop("reasoning")
            body, seconds = http.call("POST", url, headers, payload, proxy=self.proxy())
        if isinstance(body.get("error"), dict):
            raise ProviderError(str(body["error"].get("message") or body["error"])[:400], "error")
        if body.get("status") == "incomplete":
            reason = (body.get("incomplete_details") or {}).get("reason") or ""
            if reason == "content_filter":
                raise ProviderError(tr("Модель отказалась читать этот скриншот"), "refused")
            raise ProviderError(tr("Ответ модели оборвался: он не поместился в отведённый объём"), "bad_output")
        texts: List[str] = []
        for item in body.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "refusal":
                    raise ProviderError(tr("Модель отказалась читать этот скриншот"), "refused")
                if part.get("type") == "output_text":
                    texts.append(str(part.get("text") or ""))
        return {"data": parse_json_answer("".join(texts)), "seconds": seconds}
