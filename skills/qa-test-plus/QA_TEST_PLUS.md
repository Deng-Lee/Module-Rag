# QA Test Plus 测试计划

> 目标：面向当前项目的真实数据链路，建立一套独立于 `QA_TEST.md` 的 REAL-only QA 自动化用例池。  
> 正式口径：真实文档 + 真实 provider + 隔离 settings/data 目录 + dashboard API / 前端契约一致性。  
> 非目标：Streamlit AppTest、完整浏览器 E2E、OFFLINE 回归。

## 说明

- 文档样本统一来自 `tests/fixtures/sample_documents/`
- 正式执行只认非沙箱 / 本机 Terminal
- 用例池可以大于当前自动化覆盖范围
- `自动化状态` 用来区分阶段性落地范围：
  - `v1已实现`：当前 `qa-test-plus` 脚本已覆盖
  - 后续若新增 `v2` 用例，可继续沿用同样的标记方式

## A. 环境与预检

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| A-01 | REAL 预检通过 | provider preflight | 生成隔离 settings，加载 `local.production_like` 并执行 `preflight_real(settings, strategy)` | 返回 `PASS`；检查项中 `embedder/llm/judge/evaluator/reranker` 均带具体 `provider_id/model/host`，且状态不是 `FAIL/BLOCKED` | v1已实现 |
| A-02 | 缺失 API Key 的提示 | provider preflight | 生成临时 settings，把 `providers.llm.params.api_key` 置空后执行 `preflight_real(...)` | 返回 `FAIL`；失败信息明确指向 `llm::openai_compatible::<model>`，原因为 `missing_api_key`，且其它 provider 检查项保持可读 | v1已实现 |
| A-03 | endpoint host 无法解析 | provider preflight | 生成临时 settings，把 `providers.llm.params.base_url` 改成 `http://qa-plus.invalid/v1` 后执行 `preflight_real(...)` | 返回 `BLOCKED(env:network)`；失败信息中包含目标 host `qa-plus.invalid`、失败阶段和 provider/model | v1已实现 |
| A-04 | strategy 文件不存在 | settings + strategy loader | 调用 query runner，传入 `strategy_config_id=local.missing_strategy` | 返回清晰的 `strategy config not found` 配置错误；错误能定位到 strategy loader，且不写入业务数据 | v1已实现 |
| A-05 | settings 隔离目录生成正确 | settings writer | 生成 `config/settings.qa.plus.<run_id>.main.yaml`，加载后检查 `data/cache/logs/sqlite` 路径 | `data_dir/cache_dir/logs_dir/sqlite_dir` 均落在 `qa_plus_runs/<run_id>/main`，路径值可直接回填到结果里 | v1已实现 |
| A-06 | model_endpoints 覆盖生效 | settings + provider merge | 加载 `local.production_like`，执行 `merged_provider_specs(settings, strategy)` | `llm/embedder` 最终参数中带入真实 `base_url/api_key`；结果里能看到合并后的参数，且 `endpoint_key` 不再残留 | v1已实现 |

## B. CLI 摄取

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| B-01 | 摄取 `simple.pdf` | CLI ingest | 执行 `scripts/dev_ingest.sh tests/fixtures/sample_documents/simple.pdf local.production_like new_version` | 返回 `status=ok`；结果里包含 `doc_id/version_id/trace_id`，且 `chunks_written > 0` | v1已实现 |
| B-02 | 摄取 `with_images.pdf` | CLI ingest | 执行 `scripts/dev_ingest.sh tests/fixtures/sample_documents/with_images.pdf local.production_like new_version` | 返回 `status=ok`；结果里包含 `doc_id/version_id/trace_id`，且 `assets_written > 0`；trace 中可见 `asset_normalize/section_assets/transform_post/upsert` 等图片相关阶段；SQLite 中能查到该文档关联的 `asset_id`；若策略启用了视觉 enricher，则还应能查到 `caption_text` 或 `vision_snippets` 一类 caption 证据 | v1已实现 |
| B-03 | 摄取 `complex_technical_doc.pdf` | CLI ingest | 执行 `scripts/dev_ingest.sh tests/fixtures/sample_documents/complex_technical_doc.pdf local.production_like new_version` | 返回 `status=ok`；结果里有 `doc_id/version_id/trace_id`，且写入多个 chunk | v1已实现 |
| B-04 | 摄取 `chinese_technical_doc.pdf` | CLI ingest | 执行 `scripts/dev_ingest.sh tests/fixtures/sample_documents/chinese_technical_doc.pdf local.production_like new_version` | 返回 `status=ok`；结果里有 `doc_id/version_id/trace_id`，中文 PDF 文本正常入库 | v1已实现 |
| B-05 | 摄取 `chinese_long_doc.pdf` | CLI ingest | 执行 `scripts/dev_ingest.sh tests/fixtures/sample_documents/chinese_long_doc.pdf local.production_like new_version` | 返回 `status=ok`；结果里有 `doc_id/version_id/trace_id`，长文档处理不崩溃 | v1已实现 |
| B-06 | 摄取 `blogger_intro.pdf` | CLI ingest | 执行 `scripts/dev_ingest.sh tests/fixtures/sample_documents/blogger_intro.pdf local.production_like new_version` | 返回 `status=ok`；结果中有 `doc_id/trace_id`，且文档能在后续 `/api/documents` 与 `/api/traces` 中被读到 | v1已实现 |
| B-07 | 摄取 `sample.txt` 返回清晰类型错误 | CLI ingest | 调用 ingest runner，传入 `tests/fixtures/sample_documents/sample.txt` | 返回 `status=error`；错误包含 `unsupported file type`，且不会产生 `doc_id` 或业务落库记录 | v1已实现 |
| B-08 | 重复摄取同一文件幂等 | CLI ingest | 连续两次对 `simple.pdf` 执行 ingest，第二次使用 `policy=skip` | 第二次返回 `status=skipped`；结果里保留原 `doc_id`，且不产生重复活动版本 | v1已实现 |
| B-09 | 隔离运行摄取不污染主库 | CLI ingest | 在 `qa_plus_runs/<run_id>/ingest-isolated` 下写入临时 markdown，并用独立 settings 执行 ingest | 隔离库中可见新文档的 `doc_id/trace_id`；主库 `/api/documents` 中不可见该 `doc_id` | v1已实现 |
| B-10 | 摄取失败时 trace 落库 | CLI ingest | 用临时 strategy 把 embedder `base_url` 改成 `http://127.0.0.1:9/v1`，再 ingest 临时 markdown | 返回 `status=error`；trace 中存在失败事件，且能回填 `stage/provider_model/raw_error` | v1已实现 |
| B-11 | 摄取不存在路径返回清晰错误 | CLI ingest | 调用 ingest runner，传入不存在的 `tests/fixtures/sample_documents/__missing_document__.pdf` | 返回 `status=error`、`reason=file_not_found`；结果里保留具体 `file_path`，且不写入业务数据 | v1已实现 |
| B-12 | ingest `--verbose` 输出详情 | CLI ingest 脚本 | 执行 `scripts/dev_ingest.sh tests/fixtures/sample_documents/simple.pdf local.production_like skip --verbose` | 输出中包含 `VERBOSE DETAILS` 区块；区块内至少包含 `file_path/strategy_config_id/policy/trace_id/status/structured/providers/aggregates/spans`，且 `structured` 中保留 `doc_id/version_id` 或 `status=skipped` 等关键字段 | v1已实现 |

## C. CLI 查询与 Trace

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| C-01 | 基础检索命中 | CLI query | 执行 `scripts/dev_query.sh "Transformer 注意力机制是什么" local.production_like 5` | 返回非空 `sources` 和有效 `trace_id`；Top-K 至少包含 `chinese_long_doc.pdf` 或 `chinese_technical_doc.pdf` 的 chunk，且每条结果都带 `chunk_id/doc_id/score/section_path`，文本片段包含 `Transformer`、`注意力机制` 或 `Self-Attention` 相关内容 | v1已实现 |
| C-02 | 查询 trace 可读取 | CLI query + trace | 承接 C-01，对返回的 `trace_id` 调用 `GET /api/trace/{trace_id}` | `trace_id` 可读；trace 详情中能还原查询对应的 providers、events 和 replay 关键信息 | v1已实现 |
| C-03 | Dense/Sparse 证据存在 | CLI query + trace | 执行查询 `"Transformer 注意力机制是什么"`，再检查该 query trace | trace 中同时存在 dense 和 sparse 检索事件；事件预览里包含候选 `chunk_id` 和对应分数 | v1已实现 |
| C-04 | 生成阶段事件存在 | CLI query + trace | 执行查询 `"Transformer 注意力机制是什么"`，再检查 generate span | trace 中存在 `generate.used` 或 `warn.generate_fallback`；返回内容与 Top-K 检索片段主题一致 | v1已实现 |
| C-05 | 中文查询命中中文文档 | CLI query | 执行 `scripts/dev_query.sh "什么是混合检索和 BM25" local.production_like 3` | Top-K 至少包含 `chinese_technical_doc.pdf` 或 `chinese_long_doc.pdf` 的 chunk；结果条目带 `score/section_path/doc_id`，文本片段包含 `混合检索`、`BM25`、`RRF` 等关键词 | v1已实现 |
| C-06 | 空查询处理清晰 | CLI query | 执行 `scripts/dev_query.sh "" local.production_like 5`，或直接调用 query runner 并传入空字符串/全空白字符串 | 返回 `trace_id`；`sources` 为空；`content_md` 明确提示 `（空查询）请提供一个问题。`，而不是误走正常召回或生成链路 | v1已实现 |
| C-07 | 长查询处理稳定 | CLI query | 执行超长查询：`"Transformer 模型中的自注意力机制如何工作，包括 Multi-Head Attention 和 RoPE 位置编码的原理，以及 KV Cache 优化策略。同时请解释 RAG 系统中混合检索的工作流程，包括 Dense Retrieval、BM25 Sparse Retrieval 和 RRF 融合算法的具体实现方式。还有 Cross-Encoder Reranker 和 LLM Reranker 的对比分析，以及在生产环境中如何选择合适的向量数据库（如 ChromaDB、FAISS、Milvus）来存储和检索 Embedding 向量。请详细说明每个组件的优缺点和适用场景。"` | 查询不崩溃；若返回结果，则每条结果仍包含 `chunk_id/doc_id/score/section_path` 等字段，且 Top-K 应主要来自技术类长文档；若失败，返回清晰错误提示 | v1已实现 |
| C-08 | 无关查询低相关或空结果 | CLI query | 执行 `scripts/dev_query.sh "zzqvxxp cosmic-hypergraph ordinance 99173" local.production_like 3` | 返回空结果，或其 Top-K 分数明显低于 C-01 的高相关查询；若有结果，也应保留 `score/doc_id/section_path` 便于复核 | v1已实现 |
| C-09 | 查询失败时错误链路完整 | CLI query | 用临时 strategy 把 embedder `base_url` 改成 `http://127.0.0.1:9/v1`，执行查询 `"hello world"` | 失败信息完整记录 `stage/location/provider_model/raw_error/fallback`；不会伪造成功的 `sources` 列表 | v1已实现 |
| C-10 | query `top_k` 参数生效 | CLI query 脚本 | 执行 `scripts/dev_query.sh "Transformer 注意力机制是什么" local.production_like 2 --verbose` | `--verbose` 输出中的 `top_k=2`，`source_count` 不大于 2；若返回 2 条结果，每条都带 `chunk_id/doc_id/score/source/section_path` | v1已实现 |
| C-11 | query `--verbose` 输出检索详情 | CLI query 脚本 | 执行 `scripts/dev_query.sh "Transformer 注意力机制是什么" local.production_like 5 --verbose` | 输出中包含 `VERBOSE DETAILS` 区块；区块内至少包含 `query/strategy_config_id/top_k/trace_id/source_count/sources/providers/aggregates/spans`，且 `sources` 中每条结果都带 `chunk_id/doc_id/score/source/section_path` | v1已实现 |

## D. CLI 评估

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| D-01 | 运行 `rag_eval_small` | CLI eval | 执行 `scripts/dev_eval.sh rag_eval_small local.production_like 5` | 返回 `run_id`；`eval_runs` 中写入 metrics，且每个 case 都有对应 `trace_id` 可回查 | v1已实现 |
| D-02 | 评估历史可读 | CLI eval + dashboard API | 承接 D-01，对返回的 `run_id` 调用 `GET /api/eval/runs?limit=50&offset=0` | 列表中可见该 `run_id`、`dataset_id`、`strategy_config_id` 和 metrics 字段 | v1已实现 |
| D-03 | 评估趋势可读 | CLI eval + dashboard API | 承接 D-01，调用 `GET /api/eval/trends?metric=hit_rate@k&window=30` | 返回至少一个趋势点；每个点包含 `run_id/dataset_id/strategy_config_id/value` | v1已实现 |
| D-04 | 评估失败诊断 | CLI eval | 用临时 settings 把 evaluator `base_url` 改成 `http://127.0.0.1:9/v1`，执行 `rag_eval_small` | case artifacts 中明确记录失败阶段、模型、错误信息和基础上下文，而不是只给空指标 | v1已实现 |
| D-05 | 使用 golden set 自定义数据集评估 | CLI eval | 生成隔离 settings，先摄取 `DEV_SPEC.md`，再执行 `scripts/dev_eval.sh tests/fixtures/golden_test_set.json local.production_like 5 --verbose` | 正确读取 `tests/fixtures/golden_test_set.json` 并返回 `run_id`；结果中 `dataset_id=golden_test_set`，且 `metrics` 非空，可用于回看 golden queries 的整体表现 | v1已实现 |
| D-06 | 评估失败仍保留 case 级 artifacts | CLI eval | 承接 D-04，查询 `eval_case_results` 中该 `run_id` 的记录 | `artifacts_json` 中保留失败诊断字段；至少包含 `stage/model/error` 等关键信息 | v1已实现 |
| D-07 | Cross-Encoder 策略评估链路可执行 | CLI eval | 执行 `scripts/dev_eval.sh rag_eval_small local.production_like_cross_encoder 5`，再读取首个 case 的 trace | case trace 的 providers snapshot 中可见 `reranker.provider_id=cross_encoder`；评估结果仍保留 `run_id/case_id/trace_id` 关联关系 | v1已实现 |
| D-08 | eval `--verbose` 输出详情 | CLI eval 脚本 | 执行 `scripts/dev_eval.sh rag_eval_small local.production_like 3 --verbose` | 输出中包含 `VERBOSE DETAILS` 区块；区块内至少包含 `dataset_id/strategy_config_id/top_k/run_id/metrics/cases`，且 `cases` 中每条记录都带 `case_id/trace_id` | v1已实现 |
| D-09 | 使用 `composite` evaluator 进行 CLI 评估 | CLI eval 脚本 | 生成隔离 settings，将 `providers.evaluator.provider_id` 设为 `composite`、`providers.judge.provider_id` 设为 `noop`，再执行 `scripts/dev_eval.sh production_like_eval_smoke local.production_like 3 --verbose` | 返回 `run_id`；`metrics` 至少包含 `retrieval.hit_rate@3/retrieval.mrr/retrieval.ndcg@3`；不要求出现 `ragas.*` 指标；`cases` 中每条记录都带 `case_id/trace_id` | v1已实现 |
| D-10 | 使用 `ragas` evaluator 进行 CLI 评估 | CLI eval 脚本 | 生成隔离 settings，将 `providers.evaluator.provider_id` 设为 `ragas`，再执行 `scripts/dev_eval.sh production_like_eval_smoke local.production_like 3 --verbose` | 返回 `run_id`；`metrics` 至少包含 `ragas.faithfulness/ragas.answer_relevancy`；`cases` 中每条记录都带 `case_id/trace_id`，且可用于回查具体 trace | v1已实现 |

## E. Dashboard 一致性

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| E-01 | Overview 文档/分块统计一致 | dashboard API | 承接 B 阶段结果，调用 `GET /api/overview` | `assets.docs/chunks` 与 CLI 摄取结果一致或不少于当前活动文档数；返回体中同时带有可读的 provider 概览 | v1已实现 |
| E-02 | Overview provider 信息可读 | dashboard API | 调用 `GET /api/overview` | `providers` 非空；至少能看到当前链路中的关键 provider 信息，而不是空壳结构 | v1已实现 |
| E-03 | Browser 文档列表一致 | dashboard API | 调用 `GET /api/documents?limit=100&offset=0` | 活动文档列表包含 B 阶段摄取成功的 `doc_id`；每条文档记录至少带 `doc_id/version_id/status` | v1已实现 |
| E-04 | Chunk 详情一致 | dashboard API | 对查询返回的 `sample_chunk_id` 调用 `GET /api/chunk/{chunk_id}` | 返回正确的 `chunk_id`、文本和资产信息；结果里能看到 `doc_id/section_path/chunk_text/asset_ids` | v1已实现 |
| E-05 | Ingestion Trace 列表可见 | dashboard API | 调用 `GET /api/traces?trace_type=ingestion&limit=200&offset=0` | 列表包含 B 阶段产生的 ingestion trace；每条结果至少带 `trace_id/trace_type/status/strategy_config_id` | v1已实现 |
| E-06 | Query Trace 列表可见 | dashboard API | 调用 `GET /api/traces?trace_type=query&limit=200&offset=0` | 列表包含 C 阶段产生的 query trace；对应 `trace_id` 的详情可继续读到 retrieval/rerank/generate 相关信息 | v1已实现 |
| E-07 | Eval 历史可见 | dashboard API | 承接 D 阶段结果，调用 `GET /api/eval/runs` 与 `GET /api/eval/trends` | `run_id` 可见；runs 列表带 metrics，trends 返回的点位含 `run_id/value` | v1已实现 |
| E-08 | include_deleted 一致性 | dashboard API | 删除 `simple.pdf` 对应 `doc_id` 后，分别调用 `/api/documents` 和 `/api/documents?include_deleted=true` | 活动列表隐藏该文档；`include_deleted=true` 时该文档可见，且 `status=deleted` | v1已实现 |
| E-09 | 文档分页参数生效 | dashboard API | 分别调用 `GET /api/documents?limit=2&offset=0` 与 `GET /api/documents?limit=2&offset=2` | 两页结果不同；返回结果中可直接比较 `doc_id/version_id/status` | v1已实现 |
| E-10 | trace 筛选参数生效 | dashboard API | 调用 `GET /api/traces?trace_type=query&status=ok&strategy_config_id=local.production_like&limit=100&offset=0` | 返回结果均满足 `trace_type/status/strategy_config_id` 筛选条件，且每条 trace 都带这些字段 | v1已实现 |

## F. MCP Stdio

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| F-01 | `tools/list` 返回关键工具 | MCP stdio | 启动 `python -m src.mcp_server.entry`，发送 `{"method":"tools/list"}` | 返回 `library_ingest/query/query_assets/list_documents/get_document/summarize_document/delete_document/ping` 等关键工具；每个工具项含名称和参数 schema | v1已实现 |
| F-02 | `library_ingest` 可写入隔离库 | MCP stdio | 通过 `tools/call` 调用 `library_ingest`，参数为 `tests/fixtures/sample_documents/simple.pdf` | 返回 `status=ok|skipped`；结构化结果中包含 `doc_id/version_id`，且该 PDF 文档写入隔离库 | v1已实现 |
| F-03 | `library_query` 可返回结果 | MCP stdio | 承接 F-02，调用 `library_query(query="Sample Document PDF loader", top_k=3)` | 返回 `sources` 数组；每条 source 至少带 `chunk_id/doc_id/score/section_path`，Top-1 应落在 `simple.pdf` 对应文档上 | v1已实现 |
| F-04 | `library_get_document` 返回文档详情 | MCP stdio | 承接 F-02，调用 `library_get_document(doc_id=<F-02 doc_id>, version_id=<F-02 version_id>, max_chars=4000)` | 返回文档 markdown 内容和结构化字段；`structured` 中包含 `doc_id/version_id/warnings`，返回文本中可见 `Sample Document`、`A Simple Test PDF` 等正文片段 | v1已实现 |
| F-05 | `library_summarize_document` 返回摘要 | MCP stdio | 承接 F-02，调用 `library_summarize_document(doc_id=<F-02 doc_id>, version_id=<F-02 version_id>, max_chars=240, max_segments=3)` | 返回抽取式摘要文本和结构化字段；`structured` 中包含 `doc_id/version_id/warnings/summary_char_count`，摘要文本非空且能反映文档正文主题 | v1已实现 |
| F-06 | `library_list_documents` 可读到文档 | MCP stdio | 承接 F-02，调用 `library_list_documents(include_deleted=true)` | 返回列表中包含 F-02 的 `doc_id`；每条文档记录至少带 `doc_id/version_id/status` | v1已实现 |
| F-07 | `library_delete_document` 生效 | MCP stdio | 承接 F-02，调用 `library_delete_document(doc_id=<F-02 doc_id>)` 后再执行 `library_query(query="Sample Document PDF loader", top_k=3)` | 删除返回 `ok|noop`；后续查询结果不再命中被删 `doc_id` | v1已实现 |
| F-08 | `library_query_assets` 返回资产 | MCP stdio | 承接 F-10，从多模态 query 结果提取 `asset_ids`，再调用 `library_query_assets(asset_ids=[...])` | 返回资产详情，且 `asset_count > 0`；每个资产项至少带 `asset_id/mime/size_bytes` | v1已实现 |
| F-09 | 无效参数时 JSON-RPC 错误可读 | MCP stdio | 调用 `library_query_assets`，故意传空参数 `{}` | 返回 `error.code=-32602`；错误信息能指出缺失的是 `asset_ids` 参数 | v1已实现 |
| F-10 | 查询返回图片相关多模态证据 | MCP stdio | 先通过 `tools/call` 调用 `library_ingest(file_path="tests/fixtures/sample_documents/with_images.pdf")`，再调用 `library_query(query="Document with Images embedded image below", top_k=3)`；若结果里出现 `asset_ids`，继续调用 `library_query_assets(asset_ids=[...])` | query 返回的 `sources` 中至少一条命中 `with_images.pdf` 对应文档，且带非空 `asset_ids`；随后 `library_query_assets` 返回对应图片资产，形成“文本答案 + 图片证据”的闭环 | v1已实现 |
| F-11 | Server 长会话查询稳定 | MCP stdio | 在同一个 MCP stdio session 中连续执行 5 次 `library_query`：`"Sample Document PDF loader"`、`"A Simple Test PDF"`、`"Section 1 Introduction"`、`"Document with Images"`、`"embedded image below"` | 5 次查询均正常返回 `sources`；记录每次耗时，`max_latency_ms` 不应出现异常飙升，整体无超时、无会话中断 | v1已实现 |
| F-12 | 引用透明性检查 | MCP stdio | 承接 F-03，检查 `library_query(query="Sample Document PDF loader")` 返回的 `sources` 字段 | 每条检索结果至少包含 `doc_id/chunk_id/score/section_path`；检索片段中应包含 `simple.pdf` 对应的 `doc_id`，且 Top-1 的这些字段非空，支持基于 MCP 返回结果直接追溯到具体 chunk | v1已实现 |

## G. Profile 切换与对比

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| G-01 | 固定 REAL profile 对比 | compare runner | 执行 `python skills/qa-test-plus/scripts/compare_profiles.py --strategies local.default local.production_like local.production_like_cross_encoder` | 产出 profile 差异摘要和结果文件；每个 profile 至少给出 ingest/query/eval/dashboard 的结果摘要 | v1已实现 |
| G-02 | 比较 ingest 结果一致性 | compare runner | 承接 G-01，对 `local.default`、`local.production_like`、`local.production_like_cross_encoder` 分别 ingest `simple.pdf` 与 `complex_technical_doc.pdf` | 三个 profile 的 `ingest_success_count` 应一致，且每个文件的 `chunks_written/dense_written/sparse_written` 应一致；结果中还应给出 `embedder_provider_id/embedder_model`，若出现差异则说明 strategy 泄漏影响了 ingest 配置 | v1已实现 |
| G-03 | 比较 query Top 命中差异 | compare runner | 承接 G-01，对同一查询 `"Transformer 注意力机制是什么"` 对比各 profile 的 query 结果 | 结果中应能逐个 profile 比较 `query_top_doc_id/query_top_chunk_id/query_top_section_path/query_top_score/query_top_source`；这些字段必须完整可读，便于判断 Top-1 是否仍落在中文 Transformer 文档及其具体段落上 | v1已实现 |
| G-04 | 比较 eval 指标差异 | compare runner | 承接 G-01，对同一 dataset `rag_eval_small` 对比各 profile 的 eval 结果 | 这条比较的是整组评估数据集上的聚合指标差异，而不是单条 query 的 Top-K；输出 `metric_deltas`，差异值可直接对应到具体指标名 | v1已实现 |
| G-05 | 比较 rerank/fallback 差异 | compare runner | 先执行 `PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/compare_profiles.py --strategies local.default local.production_like local.production_like_cross_encoder`，比较 `local.default`、`local.production_like`、`local.production_like_cross_encoder` 在同一条查询 `"Transformer 注意力机制是什么"` 下的 rerank 行为矩阵；这个 compare 负责对比 `noop / LLM reranker / Cross-Encoder reranker` 的正常行为。若要主动制造 `reranker` 失败并验证 fallback，不是在 `compare_profiles.py` 中完成，而是执行 `PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/run_real_suite.py`，由其中的 `I-04` 在运行时生成临时策略文件 `data/qa_plus_runs/<run_id>/strategies/broken-reranker.yaml`，把 `providers.reranker.params.base_url` 改成 `http://127.0.0.1:9/v1` 后再发起 query | `compare_profiles.py` 的结果中应逐个 profile 给出 `reranker_provider_id/rerank_applied/rerank_failed/effective_rank_source/rerank_latency_ms`；至少一个带 reranker 的 profile 应显示真实 `rerank` 生效，baseline profile 应明确保持 `baseline/noop` 口径。主动失败注入部分则应在 `I-04` 中观察到 `warn.rerank_fallback`、`effective_rank_source=fusion`，从而把“正常 rerank”和“rerank 失败后 fallback”两类行为分开验证 | v1已实现 |

## H. 数据生命周期

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| H-01 | 重复摄取幂等 | CLI ingest | 对 `simple.pdf` 再执行一次 ingest，`policy=skip` | 返回 `status=skipped`；结果里保留 `doc_id/trace_id` 便于追溯 | v1已实现 |
| H-02 | 删除后查询不再命中 | admin + query | 对 `simple.pdf` 的 `doc_id` 执行 `admin.delete_document(mode=soft)`，再查询 `"Sample Document PDF loader"` | query 结果不再命中被删 `doc_id`；若仍有返回，也不能把该 `doc_id` 排进 Top-K | v1已实现 |
| H-03 | 删除后 dashboard 同步变化 | admin + dashboard API | 承接 H-02，调用 `GET /api/documents` 与 `GET /api/overview` | Browser/Overview 不再把该文档视为活动文档；相关计数同步更新 | v1已实现 |
| H-04 | 软删除后 `include_deleted` 可见 | admin + dashboard API | 承接 H-02，调用 `GET /api/documents?include_deleted=true` | deleted 文档在 `include_deleted` 列表中可见，且记录里明确显示 `status=deleted` | v1已实现 |
| H-05 | 重新摄取已删除文档恢复可查 | ingest + query + dashboard | 软删除后重新 ingest `simple.pdf`，再查询 `"Sample Document PDF loader"` 并检查 `/api/documents` | 文档重新出现在活动列表中；查询 Top-K 重新包含该 `doc_id`，且结果条目带 `score/section_path` | v1已实现 |

## I. 故障注入与恢复

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| I-01 | 缺失 strategy 的报错链路 | query flow | 调用 query runner，传入 `strategy_config_id=local.missing_strategy` | 返回清晰配置错误；能定位到 strategy loader，且不会伪造成功 query 结果 | v1已实现 |
| I-02 | embedder 网络失败诊断 | ingest/query/eval | 用临时 strategy 把 embedder `base_url` 改成 `http://127.0.0.1:9/v1`，再执行 ingest/query | 错误可定位到 embedder 环节和模型；失败结果中保留 `stage/location/provider_model/raw_error` | v1已实现 |
| I-03 | llm 失败诊断 | query | 用临时 strategy 把 LLM `base_url` 改成 `http://127.0.0.1:9/v1`，执行查询 `"Transformer 注意力机制是什么"` | trace 中出现 `warn.generate_fallback`；虽然 query 仍可回退，但结果和 trace 都能证明走了 fallback，而不是静默成功 | v1已实现 |
| I-04 | reranker 失败诊断 | query | 执行 `PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/run_real_suite.py`；脚本会在 `run_real_suite.py` 中调用 `write_strategy_yaml(...)`，基于 `local.production_like` 生成临时策略 `data/qa_plus_runs/<run_id>/strategies/broken-reranker.yaml`，并把 `providers.reranker.params.base_url` 改成 `http://127.0.0.1:9/v1`，随后用该临时 strategy 对查询 `"Transformer 注意力机制是什么"` 发起 query | trace 中出现 `warn.rerank_fallback`；结果仍保留 `chunk_id/doc_id/score`，并可判断是否退回 fusion 排名；失败链路中应能定位到 `run_real_suite.py -> broken-reranker strategy -> rerank span` | v1已实现 |
| I-05 | dashboard API 读取空库 | dashboard API | 生成一套全新的空隔离 settings，直接调用 `/api/overview`、`/api/documents`、`/api/traces`、`/api/eval/runs`、`/api/eval/trends` | 返回可解释的空结构；`docs/chunks/documents/traces/eval_runs/trend_points` 计数均为 0 | v1已实现 |
| I-06 | 部分成功链路的回填格式正确 | progress writer | 构造一个包含 PASS/FAIL/BLOCKED 的示例 payload，调用 `write_progress._render_run_block(...)` | 渲染结果包含运行区块、结果表格、失败诊断和下一步建议；表格里能展示关键证据与失败链路 | v1已实现 |
| I-07 | settings 文件语法错误提示清晰 | 配置解析 | 生成一份临时 settings 文件，故意写入错误 YAML（如 `data_dir` 缺少冒号分隔），再调用 settings loader | 返回清晰的配置解析错误；错误信息能定位到 settings 文件语法，而不是伪装成 query/provider 失败 | v1已实现 |
| I-08 | strategy 缺少必填 provider 配置 | 配置解析 | 基于 `local.default` 生成临时 strategy，把 `providers.embedder` 改成缺少 `provider_id` 的非法结构，再执行 query | 返回明确的 provider 配置错误；错误信息中包含 `provider_id` 缺失，而不是静默回退 | v1已实现 |
| I-09 | traces.jsonl 被删除后的 Dashboard 空态 | dashboard API | 在独立隔离 settings 中先 ingest+query 生成 traces，再手动删除该 run 的 `logs/traces.jsonl`，随后调用 `/api/overview` 与 `/api/traces` | Dashboard 不崩溃；文档统计仍可读，但 traces 列表为空，`providers` 为空结构，表现为“无 trace 空态” | v1已实现 |
| I-10 | traces.jsonl 含损坏行时跳过坏行 | dashboard API | 在独立隔离 settings 中先生成至少 1 条有效 trace，再向 `logs/traces.jsonl` 追加非 JSON 文本和缺字段 JSON，随后调用 `/api/overview` 与 `/api/traces` | Dashboard 不崩溃；坏行被跳过，其余有效 trace 仍可展示；Overview 仍能读到有效 trace 的 provider 信息 | v1已实现 |
| I-11 | 调小 chunk_size 后分块数增多 | 摄取参数变更 | 在独立隔离 settings 中分别用默认 `chunk_size=800` 和临时 strategy `chunk_size=300` 摄取 `tests/fixtures/sample_documents/complex_technical_doc.pdf` | `chunk_size=300` 的 `chunks_written` 明显多于默认配置；结果中能直接对比两次写入的 chunk 数 | v1已实现 |
| I-12 | `chunk_overlap=0` 时相邻块重叠减少 | 摄取参数变更 | 在独立隔离 settings 中分别用默认 `chunk_overlap=120` 和临时 strategy `chunk_overlap=0` 摄取 `tests/fixtures/sample_documents/complex_technical_doc.pdf`，再读取前两个 chunk 文本做重叠比较 | `chunk_overlap=0` 时相邻 chunk 的尾首重叠文本显著减少；结果中能直接给出默认配置与 0 overlap 的观测重叠字符数 | v1已实现 |

## J. LLM 切换 — DeepSeek

> 这组 case 参考 `qa-tester` 的 K 模块，但只保留与当前项目真实架构匹配的部分。  
> 当前项目的正式 ingestion/query 主链路里，没有启用“LLM Chunk Refiner / Metadata Enricher”这类摄取期 LLM 变换，所以不新增 `qa-tester` K-03/K-04 那种 case。  
> DeepSeek 在本项目中作为“全文本链路” provider 使用：`llm/judge/evaluator/reranker(LLM)` 切到 DeepSeek，`embedder` 仍保持 Qwen，因为 DeepSeek 不提供 embedding。

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| J-01 | DeepSeek 全文本链路 strategy 可装配 | provider preflight | 使用 `local.production_like_deepseek.yaml` 生成隔离 settings，并执行 `preflight_real(settings, strategy)` | 返回 `PASS`；预检结果中 `llm` 和 `reranker` 均显示 `base_url=https://api.deepseek.com/v1`、`model=deepseek-chat`，且 `embedder` 仍保持 `qwen/text-embedding-v3` 侧配置 | v1已实现 |
| J-02 | DeepSeek LLM — CLI 查询 | CLI query | 在隔离 settings 中保留 `embedder=qwen`，使用 `local.production_like_deepseek`，先摄取 `tests/fixtures/sample_documents/complex_technical_doc.pdf`，再执行 `scripts/dev_query.sh "Retrieval-Augmented Generation modular architecture" local.production_like_deepseek 5 --verbose` | 查询成功；返回检索结果不为空；Verbose / trace providers 中可见 `llm.provider_id=openai_compatible`、`llm.model=deepseek-chat`、`llm.base_url=https://api.deepseek.com/v1`，且 Top-K 至少命中 `complex_technical_doc.pdf` 对应 `doc_id` | v1已实现 |
| J-03 | DeepSeek LLM — Dashboard Overview 反映配置 | CLI query + Dashboard API | 承接 J-02，启动同一套隔离 settings 的 Dashboard API，调用 `GET /api/overview` | `providers.llm` 中显示 DeepSeek 的 `provider/model/base_url`；Overview 与刚才 CLI 实际运行的 provider 配置一致 | v1已实现 |
| J-04 | DeepSeek 与 Qwen 全文本链路查询结果对比 | compare runner | 执行 `PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/compare_profiles.py --strategies local.production_like local.production_like_deepseek`，比较同一条查询 `"Transformer 注意力机制是什么"` | compare 输出中同时包含 `qwen` 与 `deepseek` 两个 strategy；至少能比较 `query_top_doc_id/query_top_chunk_id/query_top_section_path/llm_provider_id/llm_model/llm_base_url/reranker_provider_id/reranker_model/reranker_base_url`，若结果差异存在，可进一步定位是否来自 generate/rerank | v1已实现 |
| J-05 | DeepSeek API Key 无效时报错清晰 | query flow | 生成隔离 settings，将 `providers.llm.params.base_url=https://api.deepseek.com/v1` 且 `api_key` 改成无效值，再执行 DeepSeek query 链路 | query 不崩溃；trace 中出现 `warn.generate_fallback`，并能从 `/api/trace/{trace_id}` 的 `error_events` 中读到 DeepSeek LLM 相关报错；失败信息可定位到生成阶段 | v1已实现 |
| J-06 | Qwen Embedding + DeepSeek 全文本链路混合配置 | ingest + query | 在同一套隔离 settings 中保持 `embedder=qwen`，使用 `local.production_like_deepseek` 摄取 `simple.pdf` 后再执行查询 `"Sample Document PDF loader"` | ingest 正常完成；query 正常完成；trace `providers` 中 `embedder.model=text-embedding-v3` 且 `embedder.base_url` 指向 Qwen，`llm.model=deepseek-chat` 且 `llm.base_url` 指向 DeepSeek，`reranker.model=deepseek-chat` 且 `reranker.base_url` 也指向 DeepSeek，证明“向量检索仍走 Qwen、文本生成与精排都切到 DeepSeek”的混合配置可跑通 | v1已实现 |
| J-07 | Ragas / Judge 使用 DeepSeek | CLI eval | 生成隔离 settings，将 `judge` 切到 DeepSeek，将 `evaluator=ragas` 的 LLM 切到 DeepSeek、embedding 保持 Qwen，再执行 `scripts/dev_eval.sh rag_eval_small local.production_like_deepseek 3 --verbose` | eval 成功或返回可解释的 provider 级错误；若成功，`metrics` 正常落库；若失败，`eval_case_results` artifacts 中仍可见 DeepSeek judge/evaluator 与 Qwen embedding 的 provider/model/base_url 证据 | v1已实现 |

## N. 数据生命周期闭环

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| N-01 | 完整闭环：摄取→查询→软删除→查询 | 数据生命周期 | 在独立隔离 settings 中依次执行：摄取 `tests/fixtures/sample_documents/simple.pdf`，查询 `"Sample Document PDF loader"`，对该 `doc_id` 执行 `admin.delete_document(mode=soft)`，再重复同一查询 | 删除前查询命中该 `doc_id`；删除后同一查询不再命中该 `doc_id`；结果里保留 ingest/query/delete 的 trace_id 形成闭环证据 | v1已实现 |
| N-02 | 硬删除清理底层存储 | 数据生命周期 | 在独立隔离 settings 中摄取 `tests/fixtures/sample_documents/with_images.pdf`，记录 `doc_id/version_id/file_sha256` 后执行 `admin.delete_document(mode=hard)` | `chunks/doc_versions/asset_refs` 被清空；对应 `md_norm.md`、raw PDF、图片资产文件不再存在；结果里保留 `affected` 统计和剩余计数 | v1已实现 |
| N-03 | 删除一个文档不影响另一文档查询 | 数据生命周期 | 在同一套隔离 settings 中先后摄取 `simple.pdf` 和 `complex_technical_doc.pdf`，软删除 `simple.pdf`，再查询 `"Retrieval-Augmented Generation modular architecture"` | 查询仍命中 `complex_technical_doc.pdf` 对应 `doc_id`，不会因为删除 `simple.pdf` 破坏另一文档的检索 | v1已实现 |
| N-04 | 硬删除后重新摄取恢复可查 | 数据生命周期 | 在独立隔离 settings 中摄取 `simple.pdf`，执行 `admin.delete_document(mode=hard)`，然后重新摄取 `simple.pdf` 并查询 `"Sample Document PDF loader"` | 重新摄取后查询重新命中当前活动 `doc_id`；结果里能看到删除前后的 `doc_id` 与恢复后的 query trace | v1已实现 |

## O. 文档替换与多场景验证

| ID | 测试标题 | 执行入口 | 操作步骤 | 预期结果 | 自动化状态 |
|---|---|---|---|---|---|
| O-01 | 中文技术文档命中 | 样本文档验证 | 在独立隔离 settings 中摄取 `tests/fixtures/sample_documents/chinese_technical_doc.pdf`，执行查询 `"Modular RAG 设计理念"` | Top-1 命中该文档 `doc_id`；命中文本片段中至少出现 `Modular RAG`、`可独立替换`、`模块` 等关键词之一 | v1已实现 |
| O-02 | 中文表格文档命中 | 样本文档验证 | 在独立隔离 settings 中摄取 `tests/fixtures/sample_documents/chinese_table_chart_doc.pdf`，执行查询 `"BGE-large-zh Cross-Encoder"` | Top-1 命中该文档 `doc_id`；命中文本片段中至少出现 `BGE-large-zh`、`Cross-Encoder` 关键词之一 | v1已实现 |
| O-03 | 中文流程图文档命中 | 样本文档验证 | 在独立隔离 settings 中摄取 `tests/fixtures/sample_documents/chinese_table_chart_doc.pdf`，执行查询 `"RAG 数据摄取流程图"` | Top-1 命中该文档 `doc_id`；命中文本片段中至少出现 `流程图`、`RAG`、`数据摄取` 关键词之一 | v1已实现 |
| O-04 | 中文长文档前半章节命中 | 样本文档验证 | 在独立隔离 settings 中摄取 `tests/fixtures/sample_documents/chinese_long_doc.pdf`，执行查询 `"RoPE 位置编码"` | Top-1 命中该文档 `doc_id`；命中文本片段中至少出现 `RoPE`、`位置编码` 关键词之一 | v1已实现 |
| O-05 | 中文长文档后半章节命中 | 样本文档验证 | 在独立隔离 settings 中摄取 `tests/fixtures/sample_documents/chinese_long_doc.pdf`，执行查询 `"项目实战经验总结"` | Top-1 命中该文档 `doc_id`；命中文本片段中至少出现 `项目实战`、`经验总结` 关键词之一 | v1已实现 |
| O-06 | 英文技术文档命中 | 样本文档验证 | 在独立隔离 settings 中摄取 `tests/fixtures/sample_documents/complex_technical_doc.pdf`，执行查询 `"ChromaDB text-embedding-ada-002 vector storage"` | Top-1 命中该文档 `doc_id`；命中文本片段中至少出现 `ChromaDB`、`text-embedding-ada-002` 关键词之一 | v1已实现 |

## 当前阶段说明

- `qa-test-plus` 第一版已把 `A..J + N..O` 的 100 条 `v1` 用例全部接入真实执行链路。
- 正式执行仍然遵循同一口径：
  - 真实文档
  - 真实 provider
  - 隔离 settings / data 目录
  - dashboard API / 前端契约一致性
- 后续新增能力时，继续沿用当前回填格式，只追加新的用例或新的 run 区块。

---

## 附录：测试环境准备清单

### 配置文件与运行入口

| 文件/脚本 | 用途 | 说明 |
|---|---|---|
| `config/settings.yaml` | 默认本地 settings | 日常开发入口；`qa-test-plus` 正式运行不会直接复用它的落库目录 |
| `config/model_endpoints.local.yaml` | REAL provider endpoint 与 API Key | 统一维护 Qwen / DeepSeek 等 OpenAI-compatible endpoint 信息 |
| `config/strategies/local.default.yaml` | 基线策略 | 无 rerank 的稳定 baseline |
| `config/strategies/local.production_like.yaml` | 生产近似策略 | Qwen LLM + LLM reranker |
| `config/strategies/local.production_like_cross_encoder.yaml` | Cross-Encoder 策略 | 用于真实 rerank 对照 |
| `config/strategies/local.production_like_deepseek.yaml` | DeepSeek 全文本链路策略 | 保持 Qwen embedding，切换文本生成与 LLM reranker 到 DeepSeek |
| `skills/qa-test-plus/scripts/run_real_suite.py` | 主回归入口 | 执行 `A..J` 全量 REAL-only 用例 |
| `skills/qa-test-plus/scripts/compare_profiles.py` | 固定 profile compare | 对比 baseline / production-like / cross-encoder / DeepSeek |
| `skills/qa-test-plus/scripts/check_dashboard_consistency.py` | Dashboard 轻量校验 | 校验 CLI/API 结果与 Dashboard API 一致 |
| `skills/qa-test-plus/scripts/write_progress.py` | 结果回填 | 将 run 结果写入 `QA_TEST_PLUS_PROGRESS.md` |

### 文档样本

所有上传文档统一来自 `tests/fixtures/`，其中正式样本文档位于 `tests/fixtures/sample_documents/`。

| 文档 | 用途 |
|---|---|
| `simple.pdf` | 基础 ingest / query / MCP / 生命周期回归 |
| `with_images.pdf` | 图片资产、多模态证据、`query_assets` 回归 |
| `complex_technical_doc.pdf` | 英文技术查询、长段落、chunk 参数调优 |
| `chinese_technical_doc.pdf` | 中文技术查询与中文 PDF 解析 |
| `chinese_table_chart_doc.pdf` | 表格/流程图相关查询场景 |
| `chinese_long_doc.pdf` | 长文档、前后章节命中、长查询稳定性 |
| `blogger_intro.pdf` | 短文档、非技术类内容回归 |
| `sample.txt` | 负向用例，验证不支持的文件类型错误 |
| `test_vision_llm.jpg` | 图像相关底层测试资源 |

### 运行环境要求

| 项目 | 要求 | 说明 |
|---|---|---|
| 执行环境 | 非沙箱 / 本机 Terminal | `qa-test-plus` 正式口径只认 REAL 本机运行 |
| Python | `.venv` 虚拟环境 | 使用仓库当前虚拟环境执行脚本和测试 |
| 日志/数据 | 隔离 run 目录 | 自动写入 `data/qa_plus_runs/<run_id>/...` |
| 网络 | 可访问 provider endpoint | 至少保证 Qwen / DeepSeek endpoint DNS 与 HTTPS 可达 |
| 可选依赖 | `sentence-transformers` / `torch` | 仅在 Cross-Encoder 真实推理相关 case 中需要 |

### 凭据与 Provider

`qa-test-plus` 的 REAL 运行依赖 `config/model_endpoints.local.yaml` 中的本地凭据，不在测试计划里直接记录明文 Key。

| Provider | 用途 | 必要性 |
|---|---|---|
| `qwen` | embedding / 默认 llm / 默认 reranker / evaluator | 必需 |
| `deepseek` | LLM 切换、Judge/Evaluator DeepSeek case | J 段必需 |
| `openai` / `gemini` / `ollama` | 当前 `qa-test-plus` V1 非默认依赖 | 可选 |

### 正式执行命令

```bash
PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/run_real_suite.py
```

专项 compare：

```bash
PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/compare_profiles.py
```

只做 Dashboard 一致性校验时：

```bash
PYTHONPATH=. .venv/bin/python skills/qa-test-plus/scripts/check_dashboard_consistency.py \
  --settings-path <settings.yaml> \
  --evidence-json <evidence.json>
```

### 常用诊断命令

```bash
bash scripts/dev_ingest.sh tests/fixtures/sample_documents/simple.pdf local.production_like new_version --verbose
bash scripts/dev_query.sh "Transformer 注意力机制是什么" local.production_like 5 --verbose
bash scripts/dev_eval.sh rag_eval_small local.production_like 3 --verbose
```

### 结果产物位置

| 路径 | 内容 |
|---|---|
| `data/qa_plus_runs/<run_id>/results/suite_results.json` | 单次 suite 的结构化结果 |
| `data/qa_plus_runs/<run_id>/compare/compare_results.json` | profile compare 结果 |
| `config/settings.qa.plus.<run_id>.*.yaml` | 本次运行生成的隔离 settings |
| `skills/qa-test-plus/QA_TEST_PLUS_PROGRESS.md` | 人类可读回填进度 |
