"""DeepSeek through its API (Chat Completions format), with the user's own key.

The API accepts pictures (model deepseek-flash) but cannot enforce a JSON schema: it has a
"JSON object" mode only.  So the schema is given in words, and the answer is checked by the
caller like any other.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..i18n import tr
from . import http
from .base import ApiProvider, ProviderError, Task, image_part, parse_json_answer, schema_text

MAX_TOKENS = 16000


class DeepSeekApi(ApiProvider):
    id = "deepseek_api"
    default_model = "deepseek-flash"
    models = ["deepseek-flash"]
    default_base_url = "https://api.deepseek.com"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": "Bearer " + self._need_key()}

    def check(self) -> Dict[str, Any]:
        try:
            body, _ = http.call("GET", self.base_url() + "/models", self._headers(), proxy=self.proxy(), timeout=40, retries=1)
        except ProviderError as exc:
            return {"ok": False, "message": str(exc), "models": []}
        ids = [str(m.get("id")) for m in body.get("data") or [] if isinstance(m, dict) and m.get("id")]
        return {"ok": True, "message": tr("Ключ принят, моделей доступно: {0}.", len(ids)), "models": ids}

    def read(self, work_dir: Path, tiles: List[Path], task: Task, holder: Optional[list] = None) -> Dict[str, Any]:
        headers = self._headers()
        content: List[Dict[str, Any]] = [{"type": "text", "text": task.prompt_attached}]
        for tile in tiles:
            mime, data = image_part(tile)
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}", "detail": "high"}})
        payload = {
            "model": self.model(),
            "messages": [
                {"role": "system", "content": task.system_attached + "\n\n" + schema_text(task.schema)},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "reasoning_effort": "low",
            "max_tokens": MAX_TOKENS,
            "stream": False,
        }
        url = self.base_url() + "/chat/completions"
        total = 0.0
        for attempt in (1, 2):
            body, seconds = http.call("POST", url, headers, payload, proxy=self.proxy())
            total += seconds
            choice = (body.get("choices") or [{}])[0] if isinstance(body.get("choices"), list) else {}
            finish = choice.get("finish_reason")
            text = str((choice.get("message") or {}).get("content") or "")
            if finish == "content_filter":
                raise ProviderError(tr("Модель отказалась читать этот скриншот"), "refused")
            if finish == "length":
                raise ProviderError(tr("Ответ модели оборвался: он не поместился в отведённый объём"), "bad_output")
            if text.strip():
                return {"data": parse_json_answer(text), "seconds": round(total, 1)}
            # documented quirk of the JSON mode: an answer that is not JSON comes back as spaces -- ask once more
        raise ProviderError(tr("Модель вернула пустой ответ"), "bad_output")
