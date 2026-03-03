from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import httpx


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    if size <= 0:
        yield items
        return
    for i in range(0, len(items), size):
        yield items[i : i + size]


@dataclass
class AzureOpenAIEmbedder:
    """Azure OpenAI embeddings client."""

    base_url: str
    api_key: str
    deployment_name: str
    api_version: str = "2024-02-15-preview"
    timeout_s: float = 60.0
    batch_size: int = 128
    extra_headers: dict[str, str] | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = self._endpoint()
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        if self.extra_headers:
            headers.update(self.extra_headers)

        out: list[list[float]] = []
        with httpx.Client(timeout=self.timeout_s) as client:
            for batch in _chunks(texts, self.batch_size):
                payload: dict[str, Any] = {"input": batch}
                res = client.post(url, headers=headers, json=payload)
                res.raise_for_status()
                data = res.json()
                out.extend(_extract_embeddings(data))
        if len(out) != len(texts):
            raise ValueError("embedding_count_mismatch")
        return out

    def _endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        return f"{base}/openai/deployments/{self.deployment_name}/embeddings?api-version={self.api_version}"


def _extract_embeddings(data: Any) -> list[list[float]]:
    if not isinstance(data, dict):
        return []
    items = data.get("data")
    if not isinstance(items, list):
        return []
    items_sorted = sorted(items, key=lambda x: x.get("index", 0))
    embeddings: list[list[float]] = []
    for item in items_sorted:
        emb = item.get("embedding")
        if isinstance(emb, list):
            embeddings.append([float(v) for v in emb])
        else:
            embeddings.append([])
    return embeddings
