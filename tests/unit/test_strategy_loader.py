from __future__ import annotations

import pytest

from src.core.strategy import StrategyLoader
from src.core.strategy.models import StrategyConfig


def test_strategy_loader_minimal() -> None:
    loader = StrategyLoader()
    sc = loader.load("local.default")

    assert sc.strategy_id == "local.default"
    assert sc.strategy_config_id.startswith("scfg_")

    provider_id, params = sc.resolve_provider("embedder")
    assert provider_id == "embedder.fake"
    assert params["dim"] == 8

    factory_cfg = sc.to_factory_cfg()
    assert "providers" in factory_cfg
    assert "embedder" in factory_cfg["providers"]


def test_strategy_config_missing_kind() -> None:
    loader = StrategyLoader()
    sc = loader.load("local.default")
    with pytest.raises(KeyError):
        sc.resolve_provider("missing")


def test_strategy_config_invalid_provider() -> None:
    raw = {"providers": {"embedder": {"params": {"dim": 8}}}}
    sc = StrategyConfig.from_dict("test.invalid", raw)
    with pytest.raises(ValueError):
        sc.resolve_provider("embedder")
