from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from ...interfaces.vector_store.retriever import RankedCandidate


@dataclass
class OpenAICompatibleLLMReranker:
    """LLM-based reranker via OpenAI-compatible chat completions.

    Expects `RankedCandidate.metadata["chunk_text"]` to be populated.
    """

    base_url: str
    api_key: str
    model: str
    timeout_s: float = 60.0
    max_candidates: int = 20
    max_chunk_chars: int = 600

    def rerank(self, query: str, candidates: list[RankedCandidate]) -> list[RankedCandidate]:
        if not candidates:
            return []

        top = list(candidates[: max(0, int(self.max_candidates))])
        payload_items: list[dict[str, Any]] = []
        for c in top:
            text = ""
            if isinstance(c.metadata, dict):
                t = c.metadata.get("chunk_text")
                if isinstance(t, str):
                    text = t
            text = _truncate(text, int(self.max_chunk_chars))
            payload_items.append({"chunk_id": c.chunk_id, "text": text})

        # If no text is available, keep original order.
        if not any(it.get("text") for it in payload_items):
            return candidates

        scores = self._score(query, payload_items)
        if not scores:
            return candidates

        def key_fn(rc: RankedCandidate) -> tuple[float, int]:
            # Stable: keep original rank for tie-break.
            return (float(scores.get(rc.chunk_id, -1.0)), -int(getattr(rc, "rank", 0) or 0))

        reranked = sorted(list(candidates), key=key_fn, reverse=True)
        return reranked

    def _score(self, query: str, items: list[dict[str, Any]]) -> dict[str, float]:
        url = self._join(self.base_url, "/chat/completions")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        system = (
            "You are a reranker for RAG retrieval. "
            "Given a query and passages, output strict JSON as an array of "
            "{chunk_id: string, score: float between 0 and 1} with higher score meaning more relevant. "
            "Do not include any other text."
        )
        user = json.dumps({"query": (query or "").strip(), "passages": items}, ensure_ascii=False)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
        }

        with httpx.Client(timeout=self.timeout_s) as client:
            res = client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()

        text = _extract_text(data)
        if not text:
            return {}

        try:
            arr = json.loads(_extract_json(text))
            if not isinstance(arr, list):
                return {}
            out: dict[str, float] = {}
            for item in arr:
                if not isinstance(item, dict):
                    continue
                cid = item.get("chunk_id")
                score = item.get("score")
                if isinstance(cid, str) and cid:
                    try:
                        out[cid] = float(score)
                    except Exception:
                        continue
            return out
        except Exception:
            return {}

    @staticmethod
    def _join(base: str, path: str) -> str:
        base = base.rstrip("/")
        return f"{base}{path}"


def _truncate(text: str, max_chars: int) -> str:
    s = (text or "").strip()
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    return s[:max_chars].rstrip() + "…"


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


def _extract_json(text: str) -> str:
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        return text[start : end + 1]
    # fallback: attempt object list extraction
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        return m.group(0)
    return text

