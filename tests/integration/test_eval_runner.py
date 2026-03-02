from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.runners.eval import EvalRunner
from src.core.runners.ingest import IngestRunner


def _write_settings_yaml(p: Path, *, data_dir: Path) -> None:
    raw = "\n".join(
        [
            "paths:",
            f"  data_dir: {data_dir.as_posix()}",
            f"  raw_dir: {(data_dir / 'raw').as_posix()}",
            f"  md_dir: {(data_dir / 'md').as_posix()}",
            f"  assets_dir: {(data_dir / 'assets').as_posix()}",
            f"  chroma_dir: {(data_dir / 'chroma').as_posix()}",
            f"  sqlite_dir: {(data_dir / 'sqlite').as_posix()}",
            "  cache_dir: cache",
            "  logs_dir: logs",
            "",
            "defaults:",
            "  strategy_config_id: local.default",
            "",
        ]
    )
    p.write_text(raw, encoding="utf-8")


def _load_retrieval_docs(path: Path) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return list(raw.get("docs") or [])


@pytest.mark.integration
def test_eval_runner_smoke(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    settings_path = tmp_path / "settings.yaml"
    _write_settings_yaml(settings_path, data_dir=data_dir)

    ds_path = Path(__file__).resolve().parents[1] / "datasets" / "retrieval_small.yaml"
    docs = _load_retrieval_docs(ds_path)

    ingester = IngestRunner(settings_path=settings_path)
    for doc in docs:
        md_path = tmp_path / f"{doc['name']}.md"
        md_path.write_text(doc["md"], encoding="utf-8")
        resp = ingester.run(md_path, strategy_config_id="local.default", policy="new_version")
        assert resp.structured.get("status") in {"ok", "skipped"}

    evaluator = EvalRunner(settings_path=settings_path)
    result = evaluator.run("rag_eval_small", strategy_config_id="local.default", top_k=5)

    assert result.dataset_id == "rag_eval_small"
    assert result.cases
    assert "retrieval.hit_rate@5" in result.metrics
