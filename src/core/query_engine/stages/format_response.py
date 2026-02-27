from __future__ import annotations

from dataclasses import dataclass

from ...response import ResponseIR, SourceRef
from ..models import QueryIR
from .context_build import ContextBundle


@dataclass
class FormatResponseStage:
    """Build an extractive markdown answer (no LLM)."""

    def run(self, *, q: QueryIR, bundle: ContextBundle, trace_id: str) -> ResponseIR:
        if not q.query_norm.strip():
            return ResponseIR(trace_id=trace_id, content_md="（空查询）请提供一个问题。", sources=[])

        if not bundle.chunks:
            return ResponseIR(trace_id=trace_id, content_md="未召回到相关内容（当前为 extractive 模式）。", sources=[])

        sources: list[SourceRef] = []
        lines: list[str] = []
        lines.append("以下为**召回片段（extraction）**，用于定位原文：\n")

        for idx, c in enumerate(bundle.chunks, start=1):
            sources.append(
                SourceRef(
                    chunk_id=c.chunk_id,
                    score=float(c.score),
                    source=c.source,
                    rank=int(c.rank or idx),
                    citation_id=c.citation_id,
                    asset_ids=list(c.asset_ids),
                    doc_id=c.doc_id,
                    version_id=c.version_id,
                    section_path=c.section_path,
                    chunk_index=c.chunk_index,
                )
            )

            title = c.section_path or "(unknown section)"
            lines.append(f"{idx}. `{title}` {c.citation_id} (score={c.score:.4f}, chunk_id={c.chunk_id})")
            if c.excerpt:
                lines.append(f"   - {c.excerpt}")

            if c.asset_ids:
                # Return asset anchors without inlining base64; client can pull later.
                lines.append(f"   - asset_ids: {', '.join(c.asset_ids)}")

        if bundle.citations_md:
            lines.append("\n---\n\n**Citations**\n")
            lines.append(bundle.citations_md.rstrip("\n"))

        content_md = "\n".join(lines).strip() + "\n"
        return ResponseIR(trace_id=trace_id, content_md=content_md, sources=sources)
