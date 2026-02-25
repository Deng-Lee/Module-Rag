from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....libs.interfaces.splitter import ChunkIR
from ....libs.interfaces.vector_store import VectorItem


@dataclass
class DenseEncoded:
    items: list[VectorItem]


@dataclass
class SparseDoc:
    chunk_id: str
    text: str
    metadata: dict[str, Any]


@dataclass
class SparseEncoded:
    docs: list[SparseDoc]


@dataclass
class EncodedChunks:
    chunks: list[ChunkIR]
    dense: DenseEncoded | None = None
    sparse: SparseEncoded | None = None
