# Dashboard Light Checks

Formal dashboard acceptance for `qa-test-plus` is:
- dashboard API correctness
- frontend data-contract correctness
- consistency with CLI and MCP side effects

Use these endpoint families:
- `/api/overview`
- `/api/documents`
- `/api/chunk/{chunk_id}`
- `/api/traces`
- `/api/trace/{trace_id}`
- `/api/eval/runs`
- `/api/eval/trends`

Required consistency mappings:
- ingest -> overview docs/chunks increase
- ingest -> documents list contains active `doc_id`
- query -> traces list contains `trace_id`
- query -> trace detail contains retrieval/rerank/generate context
- eval -> eval runs contains `run_id`
- eval -> trends exposes at least one point for a populated metric
- delete -> active documents hide deleted doc while `include_deleted=true` still exposes it

Not covered:
- upload widget behavior
- modal/confirm dialogs
- browser routing interactions
- visual layout fidelity
