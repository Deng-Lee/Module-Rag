# 项目亮点（基于 DEV_SPEC 与当前实现）

## 亮点 1：固定拓扑 + 多 Provider 切换的可插拔架构
**技术要点：**
1. 离线摄取统一通过 `IngestionPipeline.run()` 进入，避免 CLI、Dashboard、测试脚本各自拼装流程，保证执行语义一致。
2. 摄取拓扑固定为 `Loader → Transformer(pre) → Sectioner → Chunker → Transformer(post) → Embedding → Upsert`，阶段顺序不分叉，阶段实现通过 provider 配置切换。
3. 入库前对原始字节流做边写盘边 `sha256` 计算，并基于 SQLite 做 `skip / new_version` 去重和版本决策，减少重复解析与重复索引。
4. 系统通过 `openai_compatible` 适配层统一接入 Qwen、DeepSeek 等模型服务，将 `endpoint_key / model / timeout` 等差异收敛到配置层，主 LLM、reranker、judge、evaluator 都可独立切换。
5. 通过 `local.production_like`、`local.production_like_cross_encoder`、`local.production_like_deepseek` 等真实策略，将 Qwen、DeepSeek、Cross-Encoder 组合成可对比、可回归的生产链路。
6. 流水线阶段统一产出 `on_progress`、阶段事件、耗时和统计，失败时保留可诊断中间状态，方便回放和问题复现。

**简历话术方向：**
1. 设计固定拓扑 + Provider 可插拔的 Modular RAG 架构，将摄取、检索、重排、评估能力统一配置化，支持 Qwen / DeepSeek / Cross-Encoder 等策略切换而不改主流程。
2. 落地文件级哈希去重和版本控制机制，降低重复解析成本，并为数据回放、幂等处理和多策略实验提供稳定锚点。

## 亮点 2：Hybrid Search + Retrieval View 的可演进检索链路
**技术要点：**
1. 在线查询链路采用 `Dense Retrieval + BM25 Sparse Retrieval + RRF Fusion`，而不是单一路径向量检索，兼顾语义匹配和关键词命中。
2. 在 `transform_post` 阶段构建 `chunk_retrieval_text`，将 chunk 正文、标题原文、结构信息和可选增强片段拼成 retrieval view，统一作为 dense / sparse 编码输入。
3. 检索、融合、重排职责分层，召回与排序能力可独立替换；即使某一阶段失败，仍可按 `rerank → fusion → dense/sparse` 回退。
4. 查询结果保留 `doc_id / chunk_id / score / section_path` 等结构化证据，支持后续 dashboard 展示、评估和错误诊断。

**简历话术方向：**
1. 实现 Dense、BM25 与 RRF 融合的 Hybrid Search 链路，并引入 retrieval view 机制，提升复杂查询和长文档场景下的召回稳定性。
2. 将召回、融合、重排拆成独立阶段，形成可插拔、可回退、可评估的检索架构。

## 亮点 3：双路径精排能力落地到生产策略
**技术要点：**
1. 系统同时支持基于 OpenAI-compatible 接口的 `LLM Reranker` 和本地 `Cross-Encoder Reranker`，通过 strategy 配置切换而非修改主代码。
2. Cross-Encoder 路径支持 lazy load、进程内缓存、`max_candidates / batch_size / max_length / score_activation` 等参数控制，适合做本地精排和低外部依赖场景。
3. LLM Reranker 和 Cross-Encoder 都接入统一的 `RerankStage`，并在 trace 中记录 `rerank_profile_id`、`effective_rank_source`、`rerank_failed`、`rerank_latency_ms`。
4. 当 reranker 初始化失败或调用异常时，系统不会静默吞错，而是显式记录 `warn.rerank_fallback` 并回退到 fusion 结果，保证线上查询可用性。

**简历话术方向：**
1. 落地 LLM Reranker 与 Cross-Encoder 两条精排方案，支持 Qwen、DeepSeek 和本地 Cross-Encoder 的统一策略切换与效果对比。
2. 为精排链路补齐 profile version、fallback 和 latency 观测，提升策略试验的可解释性和生产可控性。

## 亮点 4：多模态内容处理与资产引用链路
**技术要点：**
1. 系统在 Loader 之后引入独立的资产归一化阶段，不在解析器内部直接处理图片，而是统一提取图片资产、生成稳定 `asset_id` 并将文档引用改写为 `asset://`。
2. 文档 chunk 除正文外还能挂载 `asset_ids`、锚点、页面/章节等结构信息，使图片和文本能在同一条检索与溯源链路中被消费。
3. 系统为 OCR、Caption、vision snippets 等增强能力预留了 post-transform 扩展位，既能支持图文检索，也不会污染原始事实层。
4. MCP 侧提供 `library_query_assets`，可按查询返回相关图片资产；Dashboard 和 QA 用例也会校验图文文档的资产写入、caption 证据和多模态查询结果。

**简历话术方向：**
1. 设计独立的多模态资产处理链路，将图片提取、去重、引用改写和检索证据统一收口到 `asset_id` 机制中。
2. 将多模态增强能力做成可插拔扩展位，支持图文检索、caption 挂载与资产回查，同时保持核心解析和检索链路稳定。

## 亮点 5：MCP Tool 化能力完整，适合 Agent 直接调用
**技术要点：**
1. 系统将知识库能力统一封装为 MCP tools，包括 `library_ingest`、`library_query`、`library_query_assets`、`library_list_documents`、`library_get_document`、`library_delete_document`、`library_summarize_document`。
2. `library_summarize_document` 不是简单返回原文，而是基于 `doc_id/version_id` 读取 `md_norm.md`，做抽取式摘要，补齐“文档详情读取”和“摘要提取”两类不同能力。
3. MCP 接口采用清晰的 JSON schema 和结构化返回，便于 Copilot / Agent 在 stdio JSON-RPC 场景下稳定消费。
4. 查询类工具返回 `trace_id`、`sources`、`chunk_id`、`score` 等结构化证据，保证上层 Agent 能解释结果来源，而不是拿到黑盒答案。

**简历话术方向：**
1. 将 RAG 能力封装为 MCP Tool 契约，支持 Agent 直接调用 ingest、query、query_assets、document summary 等能力。
2. 设计结构化 MCP 返回格式与引用透明性字段，使上层应用既能获得答案，也能获得可追溯证据链。

## 亮点 6：Trace-First 可观测体系贯穿摄取、检索、评估
**技术要点：**
1. 查询和摄取都基于统一的 TraceEnvelope / Span / Event / Aggregates 模型记录执行过程，支持 `trace_id` 级别回放。
2. 检索链路中可看到 dense、sparse、fusion、rerank、generate 等阶段事件，便于区分“召回问题、重排问题还是生成问题”。
3. 错误不只记录日志文本，还结构化记录 `stage / location / provider_model / raw_error / fallback`，方便 QA 和 Dashboard 直接消费。
4. Trace 中保留 provider snapshot、关键 chunk 预览、评分与排序变化，使策略切换和故障注入结果可解释，而不是只能看成败。

**简历话术方向：**
1. 设计 Trace-First 观测体系，把摄取、检索、评估全过程结构化为 trace/span/event，显著提升问题定位和策略回放效率。
2. 将 provider、错误链路、fallback 和排序变化纳入统一观测模型，支撑生产诊断和实验对比。

## 亮点 7：Dashboard 与真实执行结果共用事实源
**技术要点：**
1. Dashboard API 直接读取真实 `documents / traces / eval_runs / chunk / assets` 数据，而不是使用前端 mock 数据，保证展示层与 CLI/MCP 执行结果一致。
2. Overview、Documents、Query Trace、Ingestion Trace、Eval Runs、Eval Trends 等页面都以 FastAPI API 为事实源，支持前端契约级验证。
3. Trace 接口不仅返回 envelope，还会额外高亮 error events，便于快速看到 `embedder.http_error`、`warn.rerank_fallback` 等关键问题。
4. Eval Trends 能从 `eval_runs.metrics_json` 聚合历史指标点，为策略切换提供可视化趋势视图，而不只是查看单次 run。

**简历话术方向：**
1. 搭建以真实 trace / eval / document 数据为事实源的 Dashboard，保证 CLI、MCP 与可视化层展示一致。
2. 通过 dashboard API 将错误事件、评估趋势和文档元数据结构化暴露，形成可观测与可运维的诊断面板。

## 亮点 8：面向真实数据链路的 QA 与评估闭环
**技术要点：**
1. 构建 `qa-test-plus` REAL-only 回归体系，使用 `tests/fixtures/sample_documents` 中的真实 PDF、图文和中文长文档，覆盖 ingest、query、eval、MCP、dashboard consistency、profile compare、故障注入和数据生命周期。
2. 以 skill 驱动整套测试流程，将测试计划、执行脚本、失败诊断、重试策略和结果展示统一收口到同一套 QA 工作流，而不是依赖零散脚本手工执行。
3. 接入 retrieval metrics 与 Ragas evaluator，同时支持 Qwen 和 DeepSeek 评估链路，能比较不同 strategy 下的检索质量、答案相关性和故障模式。
4. 用例结果逐条回填到进度文档，统一记录 `Status / ID / Title / Note`，并补充 `stage / location / provider_model / raw_error / fallback`，支持失败项增量重跑和历史结果追踪。
5. 通过 golden set、profile compare、rerank 行为矩阵、MCP 工具回归，把“功能能跑”升级成“结果合理、差异可解释、回归可持续”。

**简历话术方向：**
1. 建立由 skill 驱动的 QA 自动化体系，串起真实文档、真实 provider、CLI、MCP、Dashboard、评估与故障注入流程，并完成测试结果结构化回填。
2. 将 golden set、Ragas、strategy compare 和增量回填机制纳入同一套流程，提升模型/策略演进时的回归效率与可信度。

## 亮点 9：工程化实践与开发测试流程沉淀
**技术要点：**
1. 项目将日常开发入口标准化为 `dev_ingest.sh`、`dev_query.sh`、`dev_eval.sh` 三类 CLI，并补齐 `--verbose` 输出，保证开发、调试、回归使用同一套入口。
2. 对正式回归采用隔离 settings + 独立 `data/qa_plus_runs/<run_id>` 目录的执行方式，避免测试数据污染开发主库，同时保留每次运行的配置、结果和诊断产物。
3. 测试计划、执行脚本、结果回填和失败重跑规则都文档化到 skill 内，形成“先定义 case，再自动执行，再结构化回填，再按失败项增量重跑”的固定流程。
4. 在代码层面为关键路径补了单测、集成测试和端到端 smoke，例如 Cross-Encoder 真推理、MCP stdio、Dashboard API、Ragas adapter、trace 聚合字段等，确保改动不仅能运行，还能回归验证。
5. 对外部 provider 不稳定、超时、账户状态异常等问题，统一沉淀为 `stage / location / provider_model / raw_error / fallback` 的故障诊断格式，减少重复排查成本。

**简历话术方向：**
1. 将开发、调试、测试、结果回填和失败重跑流程标准化，形成以 CLI + skill + 隔离环境为核心的工程化研发流程。
2. 建立覆盖单测、集成测试、真实 provider 回归和增量补跑的测试体系，提升多模型、多策略迭代时的交付稳定性。
