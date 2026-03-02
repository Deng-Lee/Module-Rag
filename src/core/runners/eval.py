from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..eval import CompositeEvaluator, GenerationMetricSet, MetricSet, load_dataset
from ..response import ResponseIR
from ..strategy import load_settings
from .query import QueryRunner
from ...ingestion.stages.storage.sqlite import SqliteStore
from ...libs.providers.evaluator.fake_judge import FakeJudge


@dataclass
class EvalCaseRun:
    case_id: str
    trace_id: str
    metrics: dict[str, float]
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalRunResult:
    run_id: str
    dataset_id: str
    strategy_config_id: str
    metrics: dict[str, float]
    cases: list[EvalCaseRun]


@dataclass
class EvalRunner:
    settings_path: str | Path = "config/settings.yaml"

    def run(
        self,
        dataset_id: str,
        *,
        strategy_config_id: str,
        top_k: int = 5,
        judge_strategy_id: str | None = None,
    ) -> EvalRunResult:
        dataset_path = _resolve_dataset_path(dataset_id)
        dataset = load_dataset(dataset_path)

        settings = load_settings(self.settings_path)
        sqlite = SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite")

        evaluator = CompositeEvaluator(
            metric_sets={"retrieval": MetricSet(k=top_k), "generation": GenerationMetricSet()},
            judge=FakeJudge(),
        )

        cases_out: list[EvalCaseRun] = []
        aggregates: dict[str, list[float]] = {}

        runner = QueryRunner(settings_path=self.settings_path)
        for case in dataset.iter_cases():
            resp = runner.run(case.query, strategy_config_id=strategy_config_id, top_k=top_k)
            run_output = _response_to_run_output(resp, sqlite, top_k=top_k)
            result = evaluator.evaluate_case(case, run_output)
            trace_id = resp.trace.trace_id if resp.trace is not None else resp.trace_id
            result.artifacts["trace_id"] = trace_id
            result.artifacts["strategy_config_id"] = strategy_config_id
            if judge_strategy_id:
                result.artifacts["judge_strategy_id"] = judge_strategy_id

            cases_out.append(
                EvalCaseRun(
                    case_id=case.case_id,
                    trace_id=trace_id,
                    metrics=result.metrics,
                    artifacts=result.artifacts,
                )
            )
            for k, v in result.metrics.items():
                aggregates.setdefault(k, []).append(float(v))

        metrics = {k: (sum(vals) / max(1, len(vals))) for k, vals in aggregates.items()}
        return EvalRunResult(
            run_id=str(uuid.uuid4()),
            dataset_id=dataset.dataset_id,
            strategy_config_id=strategy_config_id,
            metrics=metrics,
            cases=cases_out,
        )


def _resolve_dataset_path(dataset_id: str) -> Path:
    p = Path(dataset_id)
    if p.exists():
        return p
    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root / "tests" / "datasets" / f"{dataset_id}.yaml"
    if candidate.exists():
        return candidate
    candidate_json = repo_root / "tests" / "datasets" / f"{dataset_id}.json"
    if candidate_json.exists():
        return candidate_json
    raise FileNotFoundError(f"dataset not found: {dataset_id}")


def _response_to_run_output(resp: ResponseIR, sqlite: SqliteStore, *, top_k: int) -> dict[str, Any]:
    if resp.trace and "ranked_chunk_ids" in resp.trace.replay:
        ranked_chunk_ids = list(resp.trace.replay.get("ranked_chunk_ids") or [])
    else:
        ranked_chunk_ids = [s.chunk_id for s in resp.sources]
    ranked_chunk_ids = ranked_chunk_ids[: max(0, top_k)]

    retrieved = [
        {"chunk_id": s.chunk_id, "score": float(s.score), "source": s.source}
        for s in resp.sources[: max(0, top_k)]
    ]

    chunk_rows = sqlite.fetch_chunks(ranked_chunk_ids)
    text_by_id = {c.chunk_id: c.chunk_text for c in chunk_rows}
    retrieved_texts = [text_by_id.get(cid, "") for cid in ranked_chunk_ids]
    context = "\n\n".join([t for t in retrieved_texts if t])

    return {
        "ranked_chunk_ids": ranked_chunk_ids,
        "retrieved": retrieved,
        "retrieved_texts": retrieved_texts,
        "answer": resp.content_md,
        "context": context,
    }
