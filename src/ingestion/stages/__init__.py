"""Ingestion stages (1 stage = 1 file)."""

from ..pipeline import DEFAULT_STAGE_ORDER, StageSpec
from .receive.dedup import DedupDecision, DedupStage
from .receive.loader import LoaderStage, detect_file_type
from .chunking.sectioner import SectionerStage
from .chunking.chunker import ChunkerStage
from .transform.asset_normalize import FsAssetNormalizer
from .transform.transform_pre import DefaultTransformPre, TransformPreStage
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
    "FsAssetNormalizer",
    "DefaultTransformPre",
    "TransformPreStage",
]
