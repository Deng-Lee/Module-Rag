from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from ...interfaces.evaluator.judge import JudgeScore


@dataclass
class OpenAICompatibleJudge:
    """LLM-based judge using OpenAI-compatible chat completions."""

    provider_id: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = "gpt-4o-mini"
    timeout_s: float = 60.0
    temperature: float = 0.0
    extra_headers: dict[str, str] | None = None

    def score_faithfulness(self, answer: str, context: str) -> JudgeScore:
        system = (
            "You are a strict evaluator. Score faithfulness of the answer given the context. "
            "Return JSON: {\"score\": float between 0 and 1, \"reason\": string}."
        )
        user = f"Context:\n{context}\n\nAnswer:\n{answer}\n\nScore faithfulness.".strip()
        return self._score(system, user)

    def score_answer_relevancy(self, answer: str, query: str) -> JudgeScore:
        system = (
            "You are a strict evaluator. Score answer relevancy to the query. "
            "Return JSON: {\"score\": float between 0 and 1, \"reason\": string}."
        )
        user = f"Query:\n{query}\n\nAnswer:\n{answer}\n\nScore relevancy.".strip()
        return self._score(system, user)

    def _score(self, system: str, user: str) -> JudgeScore:
        url = self._join(self.base_url, "/chat/completions")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.extra_headers:
            headers.update(self.extra_headers)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
        }

        with httpx.Client(timeout=self.timeout_s) as client:
            res = client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()

        content = _extract_text(data)
        return _parse_score(content)

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


def _parse_score(text: str) -> JudgeScore:
    if not text:
        return JudgeScore(score=0.0, reason="empty_response")
    try:
        obj = json.loads(_extract_json(text))
        score = float(obj.get("score"))
        reason = obj.get("reason")
        return JudgeScore(score=score, reason=reason)
    except Exception:
        pass
    match = re.search(r"([01](?:\.\d+)?)", text)
    if match:
        try:
            return JudgeScore(score=float(match.group(1)), reason="parsed_float")
        except Exception:
            pass
    return JudgeScore(score=0.0, reason="parse_failed")


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text
