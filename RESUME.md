**画廊敏感知识检索与导购问答系统** | 2026.02 - 2026.03 | LLM Application Engineer

**背景**：服务于画廊的艺术家信息、作品信息、展览/对谈文档与价格资料管理（4 类敏感资产）。接入前仅能按名称精确检索，销售向买家介绍作品时难以快速关联“同风格作品、参展记录、同艺术家其他作品”。

**目标**：基于 Agent + RAG 构建可扩展的知识系统，打通离线摄取、Hybrid Search、问答生成和证据回溯链路；在保证敏感信息可控的前提下，支持多客户端通过 MCP 协议统一调用并持续演进策略。

**过程**：
- 设计可插拔 Ingestion Pipeline，固化 `IngestionPipeline.run()` 单入口与冻结拓扑。  
- 实现 Hybrid Search，组合 Dense/FTS5-BM25 召回、RRF 融合与可选 Rerank 回退。  
- 封装 MCP Tool 契约，交付 `ingest/query/query_assets/get_document/list/delete`。  
- 构建多模态资产链路，完成 `ref_id -> asset_id` 归一化、去重与按需拉取。  
- 落地 Trace-First + 评估体系，覆盖 HitRate@K/MRR/nDCG 与回放诊断。  
- 推行工程化(TDD)与 Skill 驱动全流程，沉淀 QA/亮点提炼/简历生成能力。  

**结果**：
- 完成 `DEV_SPEC` B~I 阶段 **80** 项里程碑任务，形成端到端可交付闭环。  
- 离线基准（`local.test`）下，摄取 **5** 份文档：`p50=50.93ms`、`p95=132.42ms`、吞吐 `893.81 docs/min`。  
- 同基准下查询 **80** 次：`p50=6.33ms`、`p95=7.33ms`、`QPS=155.48`、平均返回 `5` 条来源。  
- 索引规模落库为 `documents=5 / versions=6 / chunks=22 / assets=6`，重复摄取命中 `new_version` 策略。  
- 在 `retrieval_small` 回归集上，`hybrid_rrf` 的 `Hit@5=1.0 / MRR@5=0.6111 / nDCG@5=0.7103`，相对 `sparse_only` 分别提升 `+1.0 / +0.6111 / +0.7103`。  

**技术栈**：Hybrid Search, Rerank, MCP 协议, 可插拔架构, 多模态, 可观测性, 评估体系, 工程化(TDD), Agent 扩展, Skill 驱动全流程, Python, SQLite, FTS5, Chroma
