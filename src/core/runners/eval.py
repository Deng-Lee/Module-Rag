from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import json

from ..eval import CompositeEvaluator, GenerationMetricSet, MetricSet, load_dataset
from ..response import ResponseIR
from ..strategy import Settings, load_settings, merge_provider_overrides
from .query import QueryRunner
from ...ingestion.stages.storage.sqlite import SqliteStore
from ...libs.factories.common import NoopProvider
from ...libs.factories.evaluator import make_evaluator
from ...libs.factories.judge import make_judge
from ...libs.providers import register_builtin_providers
from ...libs.registry import ProviderRegistry


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
    settings: Settings | None = None

    def run(
        self,
        dataset_id: str,
        *,
        strategy_config_id: str,
        top_k: int = 5,
        judge_strategy_id: str | None = None,
    ) -> EvalRunResult:
        settings = self.settings or load_settings(self.settings_path)
        dataset_path = _resolve_dataset_path(dataset_id, settings)
        dataset = load_dataset(dataset_path)

        sqlite = SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite")

        registry = ProviderRegistry()
        register_builtin_providers(registry)

        # Apply model_endpoints to provider params (and strip endpoint_key) before instantiation.
        merged_providers = merge_provider_overrides(
            {},
            settings.raw.get("providers"),
            settings.raw.get("model_endpoints"),
        )
        cfg = dict(settings.raw)
        cfg["providers"] = merged_providers

        evaluator = None
        try:
            evaluator = make_evaluator(cfg, registry)
        except Exception:
            evaluator = None

        judge = None
        try:
            j = make_judge(cfg, registry)
            if not isinstance(j, NoopProvider):
                judge = j
        except Exception:
            judge = None

        if evaluator is None:
            metric_sets: dict[str, Any] = {"retrieval": MetricSet(k=top_k)}
            if judge is not None:
                metric_sets["generation"] = GenerationMetricSet()
            evaluator = CompositeEvaluator(metric_sets=metric_sets, judge=judge)

        cases_out: list[EvalCaseRun] = []
        aggregates: dict[str, list[float]] = {}

        runner = QueryRunner(settings_path=self.settings_path, settings=settings)
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
        run_result = EvalRunResult(
            run_id=str(uuid.uuid4()),
            dataset_id=dataset.dataset_id,
            strategy_config_id=strategy_config_id,
            metrics=metrics,
            cases=cases_out,
        )
        _persist_eval_run(sqlite, run_result)
        return run_result


def _resolve_dataset_path(dataset_id: str, settings: Any) -> Path:
    p = Path(dataset_id)
    if p.exists():
        return p
    repo_root = Path(__file__).resolve().parents[3]
    datasets_dir = settings.raw.get("eval", {}).get("datasets_dir")
    if datasets_dir:
        base = Path(datasets_dir)
        if not base.is_absolute():
            base = (repo_root / base).resolve()
    else:
        base = repo_root / "tests" / "datasets"

    candidate = base / f"{dataset_id}.yaml"
    if candidate.exists():
        return candidate
    candidate_json = base / f"{dataset_id}.json"
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


def _persist_eval_run(sqlite: SqliteStore, result: EvalRunResult) -> None:
    sqlite.upsert_eval_run(
        run_id=result.run_id,
        dataset_id=result.dataset_id,
        strategy_config_id=result.strategy_config_id,
        metrics_json=json.dumps(result.metrics, ensure_ascii=False),
    )
    for case in result.cases:
        sqlite.upsert_eval_case_result(
            run_id=result.run_id,
            case_id=case.case_id,
            trace_id=case.trace_id,
            metrics_json=json.dumps(case.metrics, ensure_ascii=False),
            artifacts_json=json.dumps(case.artifacts, ensure_ascii=False),
        )
