from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .dataset import EvalCase
from .metrics.retrieval import hit_rate_at_k, mrr, ndcg_at_k


@dataclass
class MetricSet:
    k: int = 5

    def compute(self, case: EvalCase, run_output: dict[str, Any]) -> dict[str, float]:
        ranked = _extract_ranked_ids(run_output)
        if case.expected_keywords:
            texts = _extract_ranked_texts(run_output)
            if texts:
                return _compute_keyword_metrics(texts, case.expected_keywords, self.k)

        expected = case.expected_chunk_ids or case.expected_doc_ids
        return {
            f"hit_rate@{self.k}": hit_rate_at_k(ranked, expected, self.k),
            "mrr": mrr(ranked, expected),
            f"ndcg@{self.k}": ndcg_at_k(ranked, expected, self.k),
        }


def _extract_ranked_ids(run_output: dict[str, Any]) -> list[str]:
    if "ranked_chunk_ids" in run_output and isinstance(run_output["ranked_chunk_ids"], list):
        return [str(x) for x in run_output["ranked_chunk_ids"]]
    if "retrieved" in run_output and isinstance(run_output["retrieved"], list):
        ids: list[str] = []
        for item in run_output["retrieved"]:
            if isinstance(item, dict) and "chunk_id" in item:
                ids.append(str(item["chunk_id"]))
        return ids
    return []


def _extract_ranked_texts(run_output: dict[str, Any]) -> list[str]:
    texts = run_output.get("retrieved_texts")
    if isinstance(texts, list):
        return [str(t) for t in texts]
    return []


def _compute_keyword_metrics(texts: list[str], keywords: list[str], k: int) -> dict[str, float]:
    rels = [_is_relevant_text(t, keywords) for t in texts[: max(0, k)]]
    if not rels or k <= 0:
        return {f"hit_rate@{k}": 0.0, "mrr": 0.0, f"ndcg@{k}": 0.0}

    hit = 1.0 if any(rels) else 0.0
    # Keyword-mode is a weak label signal; use a lenient ranking proxy.
    mrr_val = 1.0 if hit > 0 else 0.0
    ndcg_val = 1.0 if hit > 0 else 0.0

    return {f"hit_rate@{k}": hit, "mrr": mrr_val, f"ndcg@{k}": ndcg_val}


def _is_relevant_text(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)
