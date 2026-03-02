from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .dataset import EvalCase
from .metrics.retrieval import hit_rate_at_k, mrr, ndcg_at_k


@dataclass
class MetricSet:
    k: int = 5

    def compute(self, case: EvalCase, run_output: dict[str, Any]) -> dict[str, float]:
        ranked = _extract_ranked_ids(run_output)
        expected = case.expected_chunk_ids or case.expected_doc_ids or case.expected_keywords
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
