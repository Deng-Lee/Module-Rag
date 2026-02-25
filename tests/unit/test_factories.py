from __future__ import annotations

import pytest

from src.libs.factories import (
    LoaderGraph,
    make_embedding,
    make_evaluator,
    make_llm,
    make_loader_components,
    make_reranker,
    make_splitter,
    make_vector_store,
)
from src.libs.registry import ProviderNotFoundError, ProviderRegistry


class Dummy:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _reg(reg: ProviderRegistry, kind: str, provider_id: str) -> None:
    reg.register(kind, provider_id, Dummy)


def _cfg() -> dict:
    return {
        "providers": {
            "loader": {"provider_id": "loader.fake"},
            "sectioner": {"provider_id": "sectioner.fake"},
            "chunker": {"provider_id": "chunker.fake"},
            "embedder": {"provider_id": "embedder.fake"},
            "vector_index": {"provider_id": "vector.fake"},
            "retriever": {"provider_id": "retriever.fake"},
            "fusion": {"provider_id": "fusion.fake"},
            "llm": {"provider_id": "llm.fake"},
            "evaluator": {"provider_id": "evaluator.fake"},
        }
    }


def test_factories_create_instances() -> None:
    reg = ProviderRegistry()
    for kind, pid in [
        ("loader", "loader.fake"),
        ("sectioner", "sectioner.fake"),
        ("chunker", "chunker.fake"),
        ("embedder", "embedder.fake"),
        ("vector_index", "vector.fake"),
        ("retriever", "retriever.fake"),
        ("fusion", "fusion.fake"),
        ("llm", "llm.fake"),
        ("evaluator", "evaluator.fake"),
    ]:
        _reg(reg, kind, pid)

    cfg = _cfg()
    lg = make_loader_components(cfg, reg)
    assert isinstance(lg, LoaderGraph)
    sectioner, chunker = make_splitter(cfg, reg)
    embedder, sparse_encoder = make_embedding(cfg, reg)
    vector_index, sparse_index, retriever, fusion = make_vector_store(cfg, reg)
    llm = make_llm(cfg, reg)
    reranker = make_reranker(cfg, reg)  # optional -> noop
    evaluator = make_evaluator(cfg, reg)

    assert isinstance(lg.loader, Dummy)
    assert isinstance(sectioner, Dummy)
    assert isinstance(chunker, Dummy)
    assert isinstance(embedder, Dummy)
    assert isinstance(vector_index, Dummy)
    assert isinstance(retriever, Dummy)
    assert isinstance(fusion, Dummy)
    assert isinstance(llm, Dummy)
    assert isinstance(evaluator, Dummy)
    assert sparse_encoder is not None  # optional -> NoopProvider
    assert sparse_index is not None  # optional -> NoopProvider
    assert reranker is not None  # optional -> NoopProvider


def test_missing_provider_config_errors() -> None:
    reg = ProviderRegistry()
    cfg = {}
    with pytest.raises(ValueError):
        make_llm(cfg, reg)


def test_missing_provider_registration_errors() -> None:
    reg = ProviderRegistry()
    cfg = {"providers": {"llm": {"provider_id": "llm.missing"}}}
    with pytest.raises(ProviderNotFoundError):
        make_llm(cfg, reg)

