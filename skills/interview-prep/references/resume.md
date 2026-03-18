画廊多模态知识检索与 Agent 协同系统
项目简介
面向画廊艺术家资料、作品信息、展览与对谈文档、价格等敏感知识资产，设计并实现一套基于 RAG + MCP 的多模态知识检索系统，支持文档摄取、混合检索、重排、性能评估、可视化追踪和 Agent 调用能力。全链路可插拔、可追踪、可回放的设计，极大简化了策略更换、参数调整、模型能力比对流程，提升复杂语义查询、相似作品发现和敏感知识回查效率
设计固定拓扑 + Provider 可插拔的 Modular RAG 架构，可替换、可追踪、不侵入主流程。将 Loader、Chunker、Embedder、Reranker、Evaluator策略选型全部配置化，结合Factory映射和固定拓扑，实现策略一键装配
Sectioner + Chunker 的两层构建策略有效地将chunk漂移局限在局部，有利于提高content_hash利用率，如果需要排查导致chunk漂移的原因，可以根据漂移类型更快速地定位问题
实现 Dense Retrieval + BM25 + RRF 的 Hybrid Search 链路，并引入 retrieval view，支持按作品风格、展览经历、艺术家关联关系做跨文档召回，落地 LLM Reranker 与 Cross-Encoder 双路径精排，补齐相关可观测字段，支持精排效果与回退行为对比。比对后发现，纯BM25检索延迟最低，但精度不够理想；混合检索+ Corss-Encoder 重排的方案延迟相对较高，但在精度上表现最佳
构建多模态资产处理链路，摄取侧将图片规范化、落盘、挂载到chunk上，图片资产经过处理之后，允许为图片资产挂载扩展产物(OCR、Caption等)，由此形成扩展产物— 图片资产 — chunk_id的连接链路
多渠道信息增强，将元数据注入到chunk的metadata中；可选对每个chunk使用llm生成summary或关键词并注入到metadata中；多模态增强结果以独立字段存储。以上增强信息可供检索过滤、重排或展示使用
使用约束强度分级 + 执行阶段分层的双层过滤策略，将整个策略执行分成Pre阶段硬过滤、Post阶段硬过滤、软偏好三层，硬约束负责缩小候选空间，软偏好负责调解排序权重
将能力封装为 MCP tools，提供 ingest / query / query_assets / get_document / get_document_summary 等接口，支撑上层 Agent 直接调用
搭建 Trace 体系，以trace_id贯穿全链路进行数据追踪；搭建Dashboard，统一展示文档、Query Trace、Ingestion Trace、Eval Trends
建立了覆盖 100+ REAL case 的自动化 QA 回归体系，通过 qa-test skill 驱动真实数据测试，skill触发灵敏，从真实数据回归、故障注入到结果回填全程全自动无需人工介入
结果
系统上线后，复杂查询Top-5命中率为91%，销售顾问从“按关键词翻多份资料”缩短到“单次查询返回艺术家、相似作品、相关展览与价格线索”，单次信息查找耗时由 5分钟降至 1 分钟内，整套系统支撑 3000+ 文档/作品资料 的语义检索与追踪
技术栈
RAG，MCP，Hybrid Search，Cross-Encoder，LLM Reranker，Ragas，Skills
