---
name: qa-test-plus
description: Run REAL-only QA regression for MODULE-RAG using isolated settings, real sample documents, CLI/MCP/eval flows, dashboard consistency checks, and fixed profile compare.
---

# QA Test Plus

Use this skill when the user wants to run or maintain the project-specific QA workflow for MODULE-RAG using real providers and real fixture documents.

This skill is for:
- REAL-only regression
- isolated per-run data directories
- CLI ingestion/query/eval checks
- MCP stdio checks
- dashboard API and frontend-contract consistency checks
- fixed strategy/profile compare
- structured progress backfill with failure diagnostics

This skill is not for:
- Streamlit `AppTest`
- full browser E2E
- OFFLINE baseline
- arbitrary profile matrix generation

## Inputs

- [QA_TEST_PLUS.md](QA_TEST_PLUS.md)
- [QA_TEST_PLUS_PROGRESS.md](QA_TEST_PLUS_PROGRESS.md)
- [tests/fixtures/sample_documents](/Users/lee/Documents/AI/MODULE-RAG/tests/fixtures/sample_documents)
- existing strategies under `config/strategies/`

Read these references only when needed:
- case grouping: [references/case-numbering.md](references/case-numbering.md)
- dashboard checks: [references/dashboard-light-checks.md](references/dashboard-light-checks.md)
- compare rules: [references/profile-compare.md](references/profile-compare.md)
- progress display: [references/progress-format.md](references/progress-format.md)

## Rules

- Run formal regression only in non-sandbox / local terminal.
- Always generate isolated settings and write into `data/qa_plus_runs/<run_id>/...`.
- Do not point the workflow at shared `data/`, `logs/`, or `cache/`.
- Use real docs from `tests/fixtures/sample_documents/`.
- Treat dashboard as `FastAPI API + frontend contract consistency`, not Streamlit UI.
- Default failure policy is `test + diagnose + bounded fix attempt`.
- Do not auto-fix quota issues, remote provider outages, or large product defects.

## Main commands

Run the full REAL suite:

```bash
PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/run_real_suite.py
```

Run a single strategy:

```bash
PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/run_real_suite.py --strategy-config-id local.production_like
```

Run profile compare:

```bash
PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/compare_profiles.py
```

Backfill progress from a saved JSON result:

```bash
PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/write_progress.py --result-json <path>
```

## Workflow

1. Read [QA_TEST_PLUS.md](QA_TEST_PLUS.md) for the target cases.
2. Generate an isolated settings file for the run.
3. Run the REAL flow:
   - preflight
   - ingest
   - query
   - eval
   - dashboard consistency
   - MCP
   - profile compare
   - lifecycle
   - fault diagnostics
4. If a case fails:
   - capture `stage`, `location`, `provider/model`, `raw_error`, `fallback`
   - attempt only bounded infra/test fixes
   - retry the same case up to 3 times
5. Persist JSON results and append a run block to [QA_TEST_PLUS_PROGRESS.md](QA_TEST_PLUS_PROGRESS.md).

## Required output fields

Each case result must include:
- `case_id`
- `strategy_config_id`
- `entry`
- `status`
- `evidence`
- `failure.stage`
- `failure.location`
- `failure.provider_model`
- `failure.raw_error`
- `failure.fallback`

If the failure is caused by env/provider issues, mark it `BLOCKED(env/provider)`.
