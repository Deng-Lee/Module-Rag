from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import httpx
import logging

from ....observability.obs import api as obs


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    if size <= 0:
        yield items
        return
    for i in range(0, len(items), size):
        yield items[i : i + size]


@dataclass
class OpenAICompatibleEmbedder:
    """OpenAI-compatible embeddings client (OpenAI / DeepSeek / Qwen)."""

    base_url: str
    api_key: str
    model: str
    timeout_s: float = 60.0
    # Some providers enforce small embedding batch sizes (e.g., qwen <= 10).
    # Use 10 as a safe default; can be overridden via provider params.
    batch_size: int = 10
    dimensions: int | None = None
    extra_headers: dict[str, str] | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        url = self._join(self.base_url, "/embeddings")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.extra_headers:
            headers.update(self.extra_headers)

        out: list[list[float]] = []
        with httpx.Client(timeout=self.timeout_s) as client:
            for batch in _chunks(texts, self.batch_size):
                payload: dict[str, Any] = {"model": self.model, "input": batch}
                if self.dimensions is not None:
                    payload["dimensions"] = self.dimensions
                try:
                    res = client.post(url, headers=headers, json=payload)
                    res.raise_for_status()
                    data = res.json()
                    out.extend(_extract_embeddings(data))
                except httpx.HTTPStatusError as e:
                    resp = e.response
                    status = getattr(resp, "status_code", None)
                    text = getattr(resp, "text", "")
                    # Emit observability event with trimmed response body
                    try:
                        obs.event("embedder.http_error", {"url": url, "status": status, "response_snippet": (text[:1000] if isinstance(text, str) else repr(text))})
                    except Exception:
                        logging.exception("failed to emit embedder observability event")
                    logging.error("Embedding HTTP error %s %s: %s", status, url, text[:1000])
                    raise
                except httpx.RequestError as e:
                    # Network / timeout / DNS errors
                    try:
                        obs.event("embedder.request_error", {"url": url, "error": str(e)})
                    except Exception:
                        logging.exception("failed to emit embedder observability event")
                    logging.exception("Embedding request failed for %s", url)
                    raise

        if len(out) != len(texts):
            raise ValueError("embedding_count_mismatch")
        return out

    @staticmethod
    def _join(base: str, path: str) -> str:
        base = base.rstrip("/")
        return f"{base}{path}"


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
