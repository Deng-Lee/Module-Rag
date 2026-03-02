from __future__ import annotations

import math
from typing import Iterable


def hit_rate_at_k(results: Iterable[str], expected: Iterable[str], k: int) -> float:
    expected_set = _as_set(expected)
    if not expected_set or k <= 0:
        return 0.0
    hits = 0
    for rid in _head(results, k):
        if rid in expected_set:
            hits += 1
            break
    return 1.0 if hits > 0 else 0.0


def mrr(results: Iterable[str], expected: Iterable[str]) -> float:
    expected_set = _as_set(expected)
    if not expected_set:
        return 0.0
    for idx, rid in enumerate(results, start=1):
        if rid in expected_set:
            return 1.0 / float(idx)
    return 0.0


def ndcg_at_k(results: Iterable[str], expected: Iterable[str], k: int) -> float:
    expected_set = _as_set(expected)
    if not expected_set or k <= 0:
        return 0.0
    gains = 0.0
    for idx, rid in enumerate(_head(results, k), start=1):
        if rid in expected_set:
            gains += 1.0 / math.log2(idx + 1)
    ideal = _ideal_dcg(min(k, len(expected_set)))
    return gains / ideal if ideal > 0 else 0.0


def _ideal_dcg(count: int) -> float:
    total = 0.0
    for idx in range(1, count + 1):
        total += 1.0 / math.log2(idx + 1)
    return total


def _as_set(items: Iterable[str]) -> set[str]:
    return {str(i) for i in items if i is not None}


def _head(items: Iterable[str], k: int) -> list[str]:
    out: list[str] = []
    for rid in items:
        out.append(str(rid))
        if len(out) >= k:
            break
    return out
