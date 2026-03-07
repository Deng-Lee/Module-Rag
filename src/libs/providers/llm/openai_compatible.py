from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from ...interfaces.llm import LLMResult
from ....observability.obs import api as obs


@dataclass
class OpenAICompatibleLLM:
    """OpenAI-compatible chat completions client.

    Works with OpenAI / DeepSeek / Qwen (OpenAI-compatible endpoints).
    """

    base_url: str
    api_key: str
    model: str
    timeout_s: float = 60.0
    extra_headers: dict[str, str] | None = None

    def generate(self, mode: str, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResult:
        url = self._join(self.base_url, "/chat/completions")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.extra_headers:
            headers.update(self.extra_headers)

        payload = {
            "model": self.model,
            "messages": messages,
        }
        payload.update(kwargs or {})

        with httpx.Client(timeout=self.timeout_s) as client:
            try:
                res = client.post(url, headers=headers, json=payload)
                res.raise_for_status()
                data = res.json()
            except httpx.HTTPStatusError as e:
                resp = e.response
                status = getattr(resp, "status_code", None)
                text = getattr(resp, "text", "")
                try:
                    obs.event("llm.http_error", {"url": url, "status": status, "response_snippet": (text[:1000] if isinstance(text, str) else repr(text))})
                except Exception:
                    logging.exception("failed to emit llm observability event")
                logging.error("LLM HTTP error %s %s: %s", status, url, text[:1000])
                raise
            except httpx.RequestError as e:
                try:
                    obs.event("llm.request_error", {"url": url, "error": str(e)})
                except Exception:
                    logging.exception("failed to emit llm observability event")
                logging.exception("LLM request failed for %s", url)
                raise

        text = _extract_text(data)
        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        return LLMResult(
            text=text,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            meta={"provider": "openai_compatible", "mode": mode},
        )

    @staticmethod
    def _join(base: str, path: str) -> str:
        base = base.rstrip("/")
        return f"{base}{path}"


def _extract_text(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if isinstance(first, dict):
        msg = first.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
        if isinstance(first.get("text"), str):
            return first["text"]
    return ""
