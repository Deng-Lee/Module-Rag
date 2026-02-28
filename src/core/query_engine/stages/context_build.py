from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....libs.interfaces.vector_store import RankedCandidate
from ....observability.obs import api as obs
from ..models import QueryIR, QueryParams, QueryRuntime


@dataclass(frozen=True)
class ContextChunk:
    chunk_id: str
    rank: int
    score: float
    source: str

    doc_id: str | None
    version_id: str | None
    section_path: str | None
    chunk_index: int | None

    chunk_text: str
    excerpt: str
    citation_id: str
    asset_ids: list[str]


@dataclass(frozen=True)
class ContextBundle:
    chunks: list[ContextChunk]
    citations_md: str
    debug: dict[str, Any]


@dataclass
class ContextBuildStage:
    """Build a query-time context bundle by joining ranked candidates with SQLite.

    D-7 scope:
    - Join `chunk_id -> chunk_text/section_path/...` from SQLite.
    - Join `chunk_id -> asset_ids[]` from SQLite.
    - Build stable citation ids for UI and markdown footnotes.
    """

    excerpt_max_chars: int = 320

    def run(
        self,
        *,
        q: QueryIR,
        runtime: QueryRuntime,
        params: QueryParams,
        ranked: list[RankedCandidate],
    ) -> ContextBundle:
        _ = q
        include_deleted = False
        if params.filters and isinstance(params.filters, dict):
            include_deleted = bool(params.filters.get("include_deleted", False))
        if not ranked:
            return ContextBundle(chunks=[], citations_md="", debug={"count": 0})

        chunk_ids = [r.chunk_id for r in ranked]
        rows = runtime.sqlite.fetch_chunks(chunk_ids)
        by_id = {r.chunk_id: r for r in rows}
        assets_by_chunk = runtime.sqlite.fetch_chunk_assets(chunk_ids)
        statuses_by_version: dict[str, str] = {}
        if not include_deleted:
            version_ids = sorted({r.version_id for r in rows if r.version_id})
            statuses_by_version = runtime.sqlite.fetch_version_statuses(version_ids)

        out_chunks: list[ContextChunk] = []
        footnotes: list[str] = []
        dropped_deleted = 0

        for i, r in enumerate(ranked, start=1):
            row = by_id.get(r.chunk_id)
            if row is not None and not include_deleted:
                st = statuses_by_version.get(row.version_id, "")
                if st == "deleted":
                    dropped_deleted += 1
                    continue
            chunk_text = row.chunk_text if row else ""
            excerpt = _make_excerpt(chunk_text, self.excerpt_max_chars)
            citation_id = f"[{i}]"

            asset_ids = assets_by_chunk.get(r.chunk_id, [])

            out_chunks.append(
                ContextChunk(
                    chunk_id=r.chunk_id,
                    rank=int(r.rank or i),
                    score=float(r.score),
                    source=r.source,
                    doc_id=row.doc_id if row else None,
                    version_id=row.version_id if row else None,
                    section_path=row.section_path if row else None,
                    chunk_index=row.chunk_index if row else None,
                    chunk_text=chunk_text,
                    excerpt=excerpt,
                    citation_id=citation_id,
                    asset_ids=list(asset_ids),
                )
            )

            # Minimal, machine-readable footnote.
            if row is not None:
                footnotes.append(
                    f"{citation_id} doc_id={row.doc_id} version_id={row.version_id} section={row.section_path} chunk_index={row.chunk_index} chunk_id={row.chunk_id}"
                )
            else:
                footnotes.append(f"{citation_id} chunk_id={r.chunk_id} (missing in sqlite)")

        citations_md = "\n".join(footnotes).strip() + ("\n" if footnotes else "")

        obs.event(
            "context.built",
            {
                "count": len(out_chunks),
                "asset_refs": int(sum(len(c.asset_ids) for c in out_chunks)),
                "dropped_deleted": dropped_deleted,
            },
        )

        return ContextBundle(
            chunks=out_chunks,
            citations_md=citations_md,
            debug={
                "count": len(out_chunks),
                "missing_rows": max(0, len(ranked) - len(rows)),
                "dropped_deleted": dropped_deleted,
            },
        )


def _make_excerpt(text: str, max_chars: int) -> str:
    s = (text or "").strip()
    s = " ".join(s.split())
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    return s[:max_chars].rstrip() + "…"
