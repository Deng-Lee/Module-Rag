from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.vector_store import Candidate, RankedCandidate
from ..models import QueryParams, QueryRuntime


@dataclass
class FusionStage:
    """Fuse multi-source candidates into a single ranked list.

    D-5 scope: default RRF fusion; if fusion is not configured, degrade to
    a stable passthrough that prefers dense ordering.
    """

    def run(
        self,
        *,
        runtime: QueryRuntime,
        params: QueryParams,
        candidates_by_source: dict[str, list[Candidate]],
    ) -> list[RankedCandidate]:
        fused: list[RankedCandidate]
        if runtime.fusion is not None:
            fused = runtime.fusion.fuse(candidates_by_source)
        else:
            fused = _passthrough(candidates_by_source)

        if params.top_k > 0:
            return fused[: params.top_k]
        return fused


def _passthrough(candidates_by_source: dict[str, list[Candidate]]) -> list[RankedCandidate]:
    dense = list(candidates_by_source.get("dense") or [])
    sparse = list(candidates_by_source.get("sparse") or [])

    # Keep stable order; prefer dense on duplicates.
    seen: set[str] = set()
    out: list[RankedCandidate] = []

    def add(src: str, cands: list[Candidate]) -> None:
        for c in cands:
            if not c.chunk_id or c.chunk_id in seen:
                continue
            seen.add(c.chunk_id)
            out.append(
                RankedCandidate(
                    chunk_id=c.chunk_id,
                    score=float(c.score),
                    rank=0,
                    source=src,
                    metadata={"passthrough": True},
                )
            )

    add("dense", dense)
    add("sparse", sparse)

    for i, r in enumerate(out, start=1):
        r.rank = i
    return out

