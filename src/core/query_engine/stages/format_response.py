from __future__ import annotations

from dataclasses import dataclass

from ...response import ResponseIR, SourceRef
from ....libs.interfaces.vector_store import RankedCandidate
from ..models import QueryIR, QueryRuntime


@dataclass
class FormatResponseStage:
    """Build an extractive markdown answer (no LLM)."""

    max_chars_per_chunk: int = 320

    def run(self, *, q: QueryIR, candidates: list[RankedCandidate], runtime: QueryRuntime, trace_id: str) -> ResponseIR:
        if not q.query_norm.strip():
            return ResponseIR(trace_id=trace_id, content_md="（空查询）请提供一个问题。", sources=[])

        if not candidates:
            return ResponseIR(trace_id=trace_id, content_md="未召回到相关内容（当前为 extractive 模式）。", sources=[])

        chunk_ids = [c.chunk_id for c in candidates]
        rows = runtime.sqlite.fetch_chunks(chunk_ids)
        by_id = {r.chunk_id: r for r in rows}

        sources: list[SourceRef] = []
        lines: list[str] = []
        lines.append("以下为**召回片段（extraction）**，用于定位原文：\n")

        for idx, cand in enumerate(candidates, start=1):
            row = by_id.get(cand.chunk_id)
            excerpt = ""
            if row is not None:
                excerpt = row.chunk_text.strip().replace("\n", " ")
                if len(excerpt) > self.max_chars_per_chunk:
                    excerpt = excerpt[: self.max_chars_per_chunk].rstrip() + "…"

            sources.append(
                SourceRef(
                    chunk_id=cand.chunk_id,
                    score=float(cand.score),
                    source=cand.source,
                    rank=int(getattr(cand, "rank", idx) or idx),
                    doc_id=row.doc_id if row else None,
                    version_id=row.version_id if row else None,
                    section_path=row.section_path if row else None,
                    chunk_index=row.chunk_index if row else None,
                )
            )

            title = row.section_path if (row and row.section_path) else "(unknown section)"
            lines.append(
                f"{idx}. `{title}` (score={cand.score:.4f}, chunk_id={cand.chunk_id})"
            )
            if excerpt:
                lines.append(f"   - {excerpt}")

        content_md = "\n".join(lines).strip() + "\n"
        return ResponseIR(trace_id=trace_id, content_md=content_md, sources=sources)
