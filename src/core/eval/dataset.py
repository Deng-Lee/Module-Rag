from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterator

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    query: str
    tags: list[str]
    expected_doc_ids: list[str] = field(default_factory=list)
    expected_tags: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)
    expected_answer: str | None = None
    expected_citations: list[str] = field(default_factory=list)
    expected_chunk_ids: list[str] = field(default_factory=list)
    doc_scope: dict[str, Any] | None = None
    notes: str | None = None


@dataclass
class Dataset:
    dataset_id: str
    version: str | None
    cases: list[EvalCase]
    description: str | None = None

    def iter_cases(self) -> Iterator[EvalCase]:
        return iter(self.cases)


def load_dataset(path: str | Path) -> Dataset:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        raw = yaml.safe_load(text)
    else:  # fallback: allow JSON-formatted YAML files
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("pyyaml_missing_and_json_parse_failed") from exc
    if not isinstance(raw, dict):
        raise ValueError("dataset_root_must_be_mapping")

    dataset_id = str(raw.get("dataset_id") or "").strip()
    if not dataset_id:
        raise ValueError("missing_dataset_id")

    version = raw.get("version")
    if version is not None:
        version = str(version)

    description = raw.get("description")
    if description is not None:
        description = str(description)

    cases_raw = raw.get("cases")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ValueError("missing_cases")

    cases: list[EvalCase] = []
    for idx, item in enumerate(cases_raw):
        if not isinstance(item, dict):
            raise ValueError(f"case_{idx}_must_be_mapping")
        cases.append(_parse_case(item, idx))

    return Dataset(dataset_id=dataset_id, version=version, cases=cases, description=description)


def _parse_case(item: dict[str, Any], idx: int) -> EvalCase:
    case_id = str(item.get("case_id") or "").strip()
    if not case_id:
        raise ValueError(f"case_{idx}_missing_case_id")

    query = str(item.get("query") or "").strip()
    if not query:
        raise ValueError(f"case_{case_id}_missing_query")

    tags = item.get("tags")
    if not isinstance(tags, list) or not tags:
        raise ValueError(f"case_{case_id}_missing_tags")
    tags = [str(t) for t in tags if t is not None]

    expected_doc_ids: list[str] = _as_list(
        item.get("expected_doc_ids") or item.get("expected_doc_id")
    )
    expected_tags: list[str] = _as_list(item.get("expected_tags") or item.get("expected_tag"))
    expected_keywords: list[str] = _as_list(
        item.get("expected_keywords")
        or item.get("expected_keyword")
        or item.get("expected_terms")
    )

    expected = item.get("expected")
    if isinstance(expected, dict):
        if not expected_doc_ids:
            expected_doc_ids = _as_list(expected.get("doc_ids") or expected.get("doc_id"))
        if not expected_tags:
            expected_tags = _as_list(expected.get("tags") or expected.get("tag"))
        if not expected_keywords:
            expected_keywords = _as_list(
                expected.get("keywords") or expected.get("keyword") or expected.get("terms")
            )

    if not (expected_doc_ids or expected_tags or expected_keywords):
        raise ValueError(f"case_{case_id}_missing_expected_source")

    return EvalCase(
        case_id=case_id,
        query=query,
        tags=tags,
        expected_doc_ids=expected_doc_ids,
        expected_tags=expected_tags,
        expected_keywords=expected_keywords,
        expected_answer=_opt_str(item.get("expected_answer")),
        expected_citations=_as_list(item.get("expected_citations")),
        expected_chunk_ids=_as_list(item.get("expected_chunk_ids")),
        doc_scope=_opt_dict(item.get("doc_scope")),
        notes=_opt_str(item.get("notes")),
    )


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return None
