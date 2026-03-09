from __future__ import annotations

from pathlib import Path

import pytest

from src.core.eval.dataset import load_dataset


def test_load_dataset_ok() -> None:
    dataset = load_dataset("tests/datasets/rag_eval_small.yaml")
    assert dataset.dataset_id == "rag_eval_small"
    assert len(list(dataset.iter_cases())) == 4
    first = next(dataset.iter_cases())
    assert first.query
    assert first.tags
    assert "canonical" in {k.lower() for k in first.expected_keywords}


def test_load_dataset_missing_expected_source(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
{
  "dataset_id": "bad",
  "cases": [
    {"case_id": "c1", "query": "q", "tags": ["t"]}
  ]
}
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing_expected_source"):
        load_dataset(path)


def test_load_dataset_missing_query(tmp_path: Path) -> None:
    path = tmp_path / "bad_query.yaml"
    path.write_text(
        """
{
  "dataset_id": "bad",
  "cases": [
    {"case_id": "c1", "tags": ["t"], "expected": {"keywords": ["k"]}}
  ]
}
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing_query"):
        load_dataset(path)
