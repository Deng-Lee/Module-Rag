from __future__ import annotations

import pytest

from src.ingestion import DEFAULT_STAGE_ORDER, IngestionPipeline, StageSpec


def test_ingestion_pipeline_stage_order_and_spans() -> None:
    stages = []
    for name in DEFAULT_STAGE_ORDER:
        stages.append(StageSpec(name=name, fn=lambda data, ctx, n=name: f"{data}:{n}"))

    pipeline = IngestionPipeline(stages)
    result = pipeline.run("start", strategy_config_id="local.default")

    assert result.status == "ok"
    assert result.trace is not None
    span_names = [s.name for s in result.trace.spans]
    assert span_names == [f"stage.{name}" for name in DEFAULT_STAGE_ORDER]


def test_ingestion_pipeline_error() -> None:
    def bad_stage(data, ctx):
        raise ValueError("boom")

    stages = [StageSpec(name="dedup", fn=bad_stage)]
    pipeline = IngestionPipeline(stages)
    result = pipeline.run("start", strategy_config_id="local.default")

    assert result.status == "error"
    assert result.error is not None
    assert result.error.stage == "dedup"


def test_ingestion_pipeline_progress_callback() -> None:
    events: list[tuple[str, float, str]] = []

    def on_progress(stage, percent, message, payload=None):
        events.append((stage, percent, message))

    stages = [StageSpec(name="dedup", fn=lambda data, ctx: data)]
    pipeline = IngestionPipeline(stages)
    pipeline.run("start", strategy_config_id="local.default", on_progress=on_progress)

    assert events[0][2] == "start"
    assert events[-1][2] == "end"
