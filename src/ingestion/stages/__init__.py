"""Ingestion stages (1 stage = 1 file)."""

from ..pipeline import DEFAULT_STAGE_ORDER, StageSpec
from .receive.dedup import DedupDecision, DedupStage
from .receive.loader import LoaderStage, detect_file_type
from .chunking.sectioner import SectionerStage
from .chunking.chunker import ChunkerStage
from .embedding import DenseEncoded, EncodedChunks, EncodingStrategy, EmbeddingStage, SparseDoc, SparseEncoded
from .transform.asset_normalize import FsAssetNormalizer
from .transform.transform_pre import DefaultTransformPre, TransformPreStage
from .transform.transform_post import NoopEnricher, TransformPostStage
from .transform.retrieval_view import RetrievalViewConfig, build_chunk_retrieval_text
from .storage.fs import FsStore
from .storage.assets import AssetStore
from .storage.sqlite import SqliteStore

__all__ = [
    "StageSpec",
    "DEFAULT_STAGE_ORDER",
    "DedupStage",
    "DedupDecision",
    "FsStore",
    "AssetStore",
    "SqliteStore",
    "LoaderStage",
    "detect_file_type",
    "SectionerStage",
    "ChunkerStage",
    "EncodingStrategy",
    "EmbeddingStage",
    "EncodedChunks",
    "DenseEncoded",
    "SparseEncoded",
    "SparseDoc",
    "FsAssetNormalizer",
    "DefaultTransformPre",
    "TransformPreStage",
    "RetrievalViewConfig",
    "build_chunk_retrieval_text",
    "TransformPostStage",
    "NoopEnricher",
]
