from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ...interfaces.llm import LLMResult
from .openai_compatible import _extract_text


@dataclass
class AzureOpenAILLM:
    """Azure OpenAI chat completions client."""

    base_url: str
    api_key: str
    deployment_name: str
    api_version: str = "2024-02-15-preview"
    timeout_s: float = 60.0
    extra_headers: dict[str, str] | None = None

    def generate(self, mode: str, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResult:
        url = self._endpoint()
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        if self.extra_headers:
            headers.update(self.extra_headers)

        payload = {"messages": messages}
        payload.update(kwargs or {})

        with httpx.Client(timeout=self.timeout_s) as client:
            res = client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()

        text = _extract_text(data)
        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        return LLMResult(
            text=text,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            meta={"provider": "azure_openai", "mode": mode},
        )

    def _endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        return (
            f"{base}/openai/deployments/{self.deployment_name}/chat/completions"
            f"?api-version={self.api_version}"
        )
