from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....libs.interfaces.llm import LLM, LLMResult
from ....observability.obs import api as obs
from ..models import QueryIR, QueryParams, QueryRuntime
from .context_build import ContextBundle


@dataclass(frozen=True)
class GenerationResult:
    answer_md: str
    used_llm: bool
    llm_meta: dict[str, Any] | None = None
    warning: str | None = None


@dataclass
class GenerateStage:
    """LLM generation with extractive fallback.

    D-8 scope:
    - If LLM is available, generate an answer using the context bundle.
    - If LLM is missing or fails, fall back to an extractive answer.
    """

    mode: str = "rag"
    max_context_chunks: int = 6

    def run(
        self,
        *,
        q: QueryIR,
        bundle: ContextBundle,
        runtime: QueryRuntime,
        params: QueryParams,
    ) -> GenerationResult:
        _ = params

        if not bundle.chunks:
            return GenerationResult(
                answer_md="未召回到相关内容，无法生成答案。",
                used_llm=False,
                warning="no_context",
            )

        llm = runtime.llm
        if llm is None:
            obs.event("generate.skipped", {"reason": "no_llm"})
            return GenerationResult(
                answer_md=_extractive_fallback(bundle),
                used_llm=False,
                warning="no_llm",
            )

        try:
            prompt = _build_prompt(q, bundle, max_chunks=self.max_context_chunks)
            res = llm.generate(
                self.mode,
                [
                    {"role": "system", "content": "You are a RAG document assistant. Answer concisely and cite sources like [1]."},
                    {"role": "user", "content": prompt},
                ],
            )
            obs.event(
                "generate.used",
                {
                    "mode": self.mode,
                    "tokens_in": res.tokens_in,
                    "tokens_out": res.tokens_out,
                    "has_meta": bool(res.meta),
                },
            )
            return GenerationResult(answer_md=res.text, used_llm=True, llm_meta=dict(res.meta))
        except Exception as e:
            obs.event("warn.generate_fallback", {"exc_type": type(e).__name__, "message": str(e)})
            return GenerationResult(
                answer_md=_extractive_fallback(bundle),
                used_llm=False,
                warning=f"llm_failed:{type(e).__name__}",
            )


def _build_prompt(q: QueryIR, bundle: ContextBundle, *, max_chunks: int) -> str:
    lines: list[str] = []
    lines.append(f"Question: {q.query_norm}".strip())
    lines.append("")
    lines.append("Context (cite with [n]):")
    lines.append("")

    for c in bundle.chunks[: max(0, max_chunks)]:
        excerpt = c.excerpt or c.chunk_text
        lines.append(f"{c.citation_id} {excerpt}")
    lines.append("")
    lines.append("Answer in Markdown. Use citations like [1] when relying on a context item.")
    return "\n".join(lines).strip() + "\n"


def _extractive_fallback(bundle: ContextBundle) -> str:
    lines: list[str] = []
    lines.append("（extractive fallback）基于召回片段给出答案线索：")
    for c in bundle.chunks[: min(6, len(bundle.chunks))]:
        if c.excerpt:
            lines.append(f"- {c.citation_id} {c.excerpt}")
    return "\n".join(lines).strip() + "\n"

