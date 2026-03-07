from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...interfaces.vector_store.retriever import RankedCandidate


@dataclass
class CrossEncoderReranker:
    """Cross-Encoder reranker with lazy model loading + process cache."""

    model_name: str
    device: str = "cpu"
    revision: str | None = None
    max_candidates: int = 30
    batch_size: int = 8
    max_length: int = 512
    score_activation: str = "sigmoid"  # sigmoid|raw

    def rerank(self, query: str, candidates: list[RankedCandidate]) -> list[RankedCandidate]:
        if not candidates:
            return []

        limit = int(self.max_candidates)
        if limit <= 0:
            return candidates

        head = list(candidates[:limit])
        tail = list(candidates[limit:])

        pair_inputs: list[tuple[str, str]] = []
        pair_ids: list[str] = []
        for rc in head:
            text = _candidate_text(rc)
            if not text:
                continue
            pair_inputs.append(((query or "").strip(), text))
            pair_ids.append(rc.chunk_id)

        # If no rerank text exists, keep original order.
        if not pair_inputs:
            return candidates

        scores = self._predict_pairs(pair_inputs)
        if len(scores) != len(pair_inputs):
            raise ValueError("cross_encoder score count mismatch")

        score_by_id = {cid: float(score) for cid, score in zip(pair_ids, scores)}

        def key_fn(rc: RankedCandidate) -> tuple[float, int]:
            # Stable tie-break by original rank.
            return (float(score_by_id.get(rc.chunk_id, -1e30)), -int(getattr(rc, "rank", 0) or 0))

        reranked_head = sorted(head, key=key_fn, reverse=True)
        return reranked_head + tail

    def _predict_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        model = self._load_model_cached(self.model_name, self.device, self.revision)
        kwargs = {"batch_size": int(self.batch_size), "show_progress_bar": False}
        max_len = int(self.max_length)
        if max_len > 0:
            kwargs["max_length"] = max_len
        try:
            raw = model.predict(pairs, **kwargs)
        except TypeError:
            # Some sentence-transformers versions do not accept max_length in predict().
            kwargs.pop("max_length", None)
            raw = model.predict(pairs, **kwargs)

        vals = _to_float_list(raw)
        act = (self.score_activation or "sigmoid").strip().lower()
        if act == "raw":
            return vals
        if act != "sigmoid":
            raise ValueError(f"unsupported score_activation: {self.score_activation}")
        return [_sigmoid(v) for v in vals]

    @staticmethod
    @lru_cache(maxsize=8)
    def _load_model_cached(model_name: str, device: str, revision: str | None) -> Any:
        if not (model_name or "").strip():
            raise ValueError("model_name is required for cross_encoder reranker")
        try:
            from sentence_transformers import CrossEncoder
        except Exception as e:  # pragma: no cover - exercised via integration/runtime.
            raise RuntimeError(
                "cross_encoder dependency missing; install optional extras for sentence-transformers/torch"
            ) from e

        kwargs: dict[str, Any] = {}
        dev = (device or "").strip().lower()
        if dev and dev != "auto":
            kwargs["device"] = dev
        if revision:
            kwargs["revision"] = revision
        try:
            return CrossEncoder(model_name, **kwargs)
        except TypeError:
            kwargs.pop("revision", None)
            return CrossEncoder(model_name, **kwargs)


def _candidate_text(rc: RankedCandidate) -> str:
    if not isinstance(rc.metadata, dict):
        return ""
    v = rc.metadata.get("rerank_text")
    if isinstance(v, str) and v.strip():
        return v.strip()
    v = rc.metadata.get("chunk_text")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return ""


def _to_float_list(raw: Any) -> list[float]:
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if isinstance(raw, (int, float)):
        return [float(raw)]
    if not isinstance(raw, list):
        return []
    out: list[float] = []
    for x in raw:
        try:
            out.append(float(x))
        except Exception:
            out.append(0.0)
    return out


def _sigmoid(x: float) -> float:
    # Clamp to keep math.exp stable.
    z = max(-60.0, min(60.0, float(x)))
    return 1.0 / (1.0 + math.exp(-z))
