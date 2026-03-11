# Profile Compare Rules

Default compare scope is fixed and small.

Preferred default strategies:
- `local.default`
- `local.production_like`

Optional extra strategies may be passed explicitly, but they are not part of the default formal matrix.

Per-profile smoke checks:
- preflight
- ingest at least 2 docs
- one query
- one eval run
- one dashboard consistency pass

Required compare output:
- strategy id
- status
- ingest success count
- query top source/doc/chunk/section/score
- query trace id
- eval run id
- eval metrics
- reranker provider id
- rerank applied / fallback signal
- effective rank source
- rerank latency

Diff summary must state:
- which strategy failed first
- whether the difference came from retrieval, rerank, generate, or evaluator
- metric deltas for shared metrics
