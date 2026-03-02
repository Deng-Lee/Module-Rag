# MODULE-RAG

Pluggable RAG document assistant exposed as an MCP server. This repo includes ingestion, retrieval, evaluation, observability, and a dashboard API.

## Quickstart (Local)

1. Bootstrap directories
   - `scripts/bootstrap_local.sh`
2. Ingest a document
   - `scripts/dev_ingest.sh /path/to/doc.md`
3. Query
   - `scripts/dev_query.sh "your question"`
4. Run evaluation
   - `scripts/dev_eval.sh rag_eval_small`
5. Start dashboard API
   - `scripts/dev_dashboard.sh`

## MCP Server (stdio)

Run the MCP server (stdio transport):

`PYTHONPATH=. .venv/bin/python -m src.mcp_server.entry`

Supported tools (core):
`library.ingest`, `library.query`, `library.query_assets`, `library.get_document`,
`library.list_documents`, `library.delete_document`, `library.ping`.

## Dashboard API

The dashboard is API-only (FastAPI). Start it via:

`scripts/dev_dashboard.sh`

Default URL:
`http://127.0.0.1:7860`

## Evaluation

Minimal dataset is in `tests/datasets/rag_eval_small.yaml`.
Run evaluation:
`scripts/dev_eval.sh rag_eval_small`

## Tests

Unit:
`PYTHONPATH=. .venv/bin/pytest -q tests/unit`

Integration:
`PYTHONPATH=. .venv/bin/pytest -q -m integration`

E2E:
`PYTHONPATH=. .venv/bin/pytest -q -m e2e`

## Troubleshooting

Trace ID lookup:
1. Dashboard: `GET /api/traces` then `GET /api/trace/{trace_id}`
2. JSONL logs: `logs/traces.jsonl` (one trace per line, search by `trace_id`)
3. SQLite traces: `data/sqlite/traces.sqlite` (if enabled)

Common issues:
- `pytest: command not found`
  - Use `.venv/bin/pytest` or install dev deps.
- Missing dataset
  - Ensure `config/settings.yaml` contains `eval.datasets_dir: tests/datasets`.
- Assets not found in `query_assets`
  - Ensure Markdown uses absolute image paths or that the image is under the same folder as the Markdown file.

## Spec

See `DEV_SPEC.md` for full architecture, contracts, and milestone plan.
