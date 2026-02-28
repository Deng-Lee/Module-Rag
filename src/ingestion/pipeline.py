from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .errors import StageExecutionError
from .models import IngestResult, ProgressCallback, StageContext
from ..observability.obs import api as obs
from ..observability.trace.context import TraceContext


@dataclass
class StageSpec:
    name: str
    fn: Callable[[Any, StageContext], Any]


DEFAULT_STAGE_ORDER: list[str] = [
    "dedup",
    "loader",
    "asset_normalize",
    "transform_pre",
    "sectioner",
    "chunker",
    "transform_post",
    "embedding",
    "upsert",
]


class IngestionPipeline:
    def __init__(self, stages: Iterable[StageSpec]) -> None:
        self._stages = list(stages)

    def run(
        self,
        input_data: Any,
        strategy_config_id: str,
        on_progress: ProgressCallback | None = None,
    ) -> IngestResult:
        ctx = TraceContext.new(trace_type="ingestion", strategy_config_id=strategy_config_id)
        with TraceContext.activate(ctx):
            data = input_data
            total = len(self._stages) if self._stages else 1

            for idx, stage in enumerate(self._stages):
                try:
                    data = self._run_stage(
                        stage,
                        data,
                        strategy_config_id=strategy_config_id,
                        on_progress=on_progress,
                        index=idx,
                        total=total,
                    )
                except StageExecutionError as e:
                    envelope = ctx.finish()
                    return IngestResult(
                        trace_id=ctx.trace_id,
                        status="error",
                        error=e,
                        trace=envelope,
                    )

            envelope = ctx.finish()
            return IngestResult(
                trace_id=ctx.trace_id,
                status="ok",
                output=data,
                trace=envelope,
            )

    def _run_stage(
        self,
        stage: StageSpec,
        data: Any,
        *,
        strategy_config_id: str,
        on_progress: ProgressCallback | None,
        index: int,
        total: int,
    ) -> Any:
        stage_name = stage.name
        percent_start = _percent(index, total)
        percent_end = _percent(index + 1, total)

        if on_progress is not None:
            on_progress(stage_name, percent_start, "start", {"index": index, "total": total})

        obs.event("stage.start", {"stage": stage_name, "index": index, "total": total})

        try:
            with obs.span(f"stage.{stage_name}", {"stage": stage_name}):
                ctx = StageContext(
                    strategy_config_id=strategy_config_id,
                    trace_id=TraceContext.current().trace_id if TraceContext.current() else "",
                    stage=stage_name,
                )
                output = stage.fn(data, ctx)
        except Exception as e:
            obs.event("stage.error", {"stage": stage_name, "message": str(e)})
            raise StageExecutionError(stage_name, str(e)) from e
        finally:
            obs.event("stage.end", {"stage": stage_name})
            if on_progress is not None:
                on_progress(stage_name, percent_end, "end", {"index": index, "total": total})

        return output


def _percent(index: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((index / total) * 100.0, 2)
