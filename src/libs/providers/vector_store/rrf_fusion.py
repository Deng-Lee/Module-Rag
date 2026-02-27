from __future__ import annotations

from dataclasses import dataclass

from ...interfaces.vector_store import Candidate, Fusion, RankedCandidate


@dataclass
class RrfFusion(Fusion):
    """Reciprocal Rank Fusion (RRF).

    RRF combines multiple ranked lists using:
      score(chunk) = sum_s 1 / (k + rank_s(chunk))

    Notes:
    - Uses rank within each source list; does not assume cross-source score comparability.
    - Higher score is better.
    """

    k: int = 60

    def fuse(self, candidates_by_source: dict[str, list[Candidate]]) -> list[RankedCandidate]:
        if self.k <= 0:
            raise ValueError("k must be positive")

        # chunk_id -> aggregated score and per-source ranks
        agg: dict[str, dict[str, object]] = {}

        for source, cands in (candidates_by_source or {}).items():
            if not cands:
                continue

            # assume input list is already sorted best-first
            for idx, c in enumerate(cands, start=1):
                if not c.chunk_id:
                    continue
                rec = agg.get(c.chunk_id)
                if rec is None:
                    rec = {"score": 0.0, "ranks": {}, "sources": set()}
                    agg[c.chunk_id] = rec

                score = float(rec["score"]) + 1.0 / (self.k + idx)
                rec["score"] = score
                rec["ranks"][source] = idx
                rec["sources"].add(source)

        ranked: list[RankedCandidate] = []
        for chunk_id, rec in agg.items():
            ranked.append(
                RankedCandidate(
                    chunk_id=chunk_id,
                    score=float(rec["score"]),
                    rank=0,
                    source="rrf",
                    metadata={
                        "sources": sorted(rec["sources"]),
                        "ranks": dict(rec["ranks"]),
                    },
                )
            )

        ranked.sort(key=lambda x: (-x.score, x.chunk_id))
        for i, r in enumerate(ranked, start=1):
            r.rank = i

        return ranked

