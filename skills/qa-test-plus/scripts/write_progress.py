from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _progress_path() -> Path:
    return _repo_root() / "skills" / "qa-test-plus" / "QA_TEST_PLUS_PROGRESS.md"


def _render_run_block(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    cases = payload.get("cases") or []
    lines = [
        f"### Run {payload.get('run_id')}",
        "",
        "**执行配置**",
        f"- 策略: `{payload.get('strategy_config_id')}`",
        f"- settings: `{payload.get('settings_path')}`",
        f"- 结果文件: `{payload.get('result_json')}`",
        "",
        "**执行总览**",
        f"- 自动化执行用例数: {len(cases)}",
        (
            f"- PASS={summary.get('PASS', 0)} | FAIL={summary.get('FAIL', 0)} | "
            f"BLOCKED={summary.get('BLOCKED', 0)} | TOTAL={summary.get('TOTAL', 0)}"
        ),
        "",
        "**用例结果**",
        "",
        "| Status | ID | Title | Note |",
        "|---|---|---|---|",
    ]
    for case in cases:
        row = (
            f"| {case.get('status')} | {case.get('case_id')} | "
            f"{case.get('title')} | {_render_note(case)} |"
        )
        lines.append(
            row
        )
    compare = payload.get("compare") or {}
    if compare:
        first_failure_text = (
            json.dumps(compare.get("first_failure"), ensure_ascii=False)
            if compare.get("first_failure")
            else "none"
        )
        metric_delta_text = json.dumps(compare.get("metric_deltas") or {}, ensure_ascii=False)
        lines.extend(
            [
                "",
                "**Profile 对比**",
                f"- 参与策略: {', '.join(compare.get('strategies') or [])}",
                f"- 首个失败策略: {first_failure_text}",
                f"- 指标差异: {metric_delta_text}",
            ]
        )
    failed_cases = [
        case
        for case in cases
        if str(case.get("status", "")).startswith("FAIL")
        or str(case.get("status", "")).startswith("BLOCKED")
    ]
    lines.extend(["", "**失败诊断**"])
    if failed_cases:
        for case in failed_cases:
            failure = case.get("failure") or {}
            lines.append(
                "- "
                f"{case.get('case_id')}: 阶段={failure.get('stage') or 'n/a'}, "
                f"位置={failure.get('location') or 'n/a'}, "
                f"模型={failure.get('provider_model') or 'n/a'}, "
                f"fallback={failure.get('fallback') or 'n/a'}"
            )
    else:
        lines.append("- 无")
    lines.extend(["", "**下一步**"])
    if failed_cases:
        lines.append("- 优先修复失败/阻塞用例对应的最早失败链路，再重跑同一 run。")
        lines.append("- 若失败来自环境或第三方 provider，单独记录为环境问题，不要混入产品缺陷。")
        lines.append("- 修复后保持回填格式不变，只追加新的 run 区块。")
    else:
        lines.append("- 当前 `v1` 自动化覆盖已通过，可继续扩展新的 REAL profile 或新的专项用例。")
    return "\n".join(lines) + "\n"


def _render_note(case: dict[str, Any]) -> str:
    entry = str(case.get("entry") or "").strip()
    evidence = case.get("evidence") or {}
    failure = case.get("failure") or {}
    parts: list[str] = []
    if entry:
        parts.append(f"entry={entry}")
    for key in (
        "file",
        "query",
        "trace_id",
        "run_id",
        "doc_id",
        "deleted_doc_id",
        "top_chunk_id",
        "top_doc_id",
        "metric_keys",
        "case_count",
    ):
        value = evidence.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value[:4])
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    for key in ("stage", "location", "provider_model", "raw_error", "fallback"):
        value = failure.get(key)
        if value:
            parts.append(f"{key}={value}")
    if not parts and evidence:
        for key, value in list(evidence.items())[:4]:
            parts.append(f"{key}={value}")
    return "; ".join(parts) or "-"


def _update_header(existing: str, payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = existing.splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith("- 最新运行:"):
            out.append(f"- 最新运行: {payload.get('run_id')}")
        elif line.startswith("- 最近一次执行统计:"):
            out.append(
                "- 最近一次执行统计: "
                f"PASS={summary.get('PASS', 0)} | "
                f"FAIL={summary.get('FAIL', 0)} | "
                f"BLOCKED={summary.get('BLOCKED', 0)} | "
                f"TOTAL={summary.get('TOTAL', 0)}"
            )
        else:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--result-json", required=True)
    args = p.parse_args()

    payload = json.loads(Path(args.result_json).read_text(encoding="utf-8"))
    progress_path = _progress_path()
    existing = (
        progress_path.read_text(encoding="utf-8")
        if progress_path.exists()
        else "# QA Test Plus 执行进度\n"
    )
    updated = _update_header(existing, payload)
    if "暂无运行记录。" in updated:
        updated = updated.replace("暂无运行记录。\n", "")
    updated = updated.rstrip() + "\n\n" + _render_run_block(payload)
    progress_path.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
