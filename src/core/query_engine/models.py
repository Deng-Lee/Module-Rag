from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...libs.interfaces.embedding import Embedder
from ...libs.interfaces.llm import LLM
from ...libs.interfaces.reranker import Reranker
from ...libs.interfaces.vector_store import Candidate, Fusion, Retriever, VectorIndex
from ...ingestion.stages.storage.sqlite import SqliteStore


@dataclass(frozen=True)
class QueryParams:
    top_k: int = 5
    filters: dict[str, Any] | None = None
    text_norm_profile_id: str = "default"


@dataclass(frozen=True)
class QueryIR:
    query_raw: str
    query_norm: str
    query_hash: str

    rewrite_used: bool = False
    query_rewritten: str | None = None


@dataclass
class QueryState:
    query: QueryIR
    candidates: list[Candidate] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class QueryRuntime:
    embedder: Embedder
    vector_index: VectorIndex
    retriever: Retriever
    sqlite: SqliteStore
    sparse_retriever: Retriever | None = None
    fusion: Fusion | None = None
    reranker: Reranker | None = None
    llm: LLM | None = None
