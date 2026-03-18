# 项目技术知识库 — 面试官参考手册

> 本文件供面试官（AI Agent）使用，包含本项目的关键实现细节、高频面试题及参考答案。
> 面试过程中用于生成精准追问和评估候选人回答质量。

---

## 模块一：Hybrid Search 混合检索

### 核心实现
- **双路并行召回**：Dense（向量语义）+ Sparse（BM25 关键词）同时执行
- **融合算法**：RRF（Reciprocal Rank Fusion）  
  公式：`Score = 1/(k + Rank_Dense) + 1/(k + Rank_Sparse)`，k 通常取 60
- **为什么用 RRF 而不是线性加权**：RRF 无需对不同路的分数值做归一化，对排名稳健，不依赖各路分数的绝对尺度
- **Dense Route**：计算 Query Embedding → Cosine Similarity → Top-N 语义候选
- **Sparse Route**：BM25 倒排索引 → Top-N 关键词候选

### 高频面试题

**Q: 为什么要做 Hybrid Search？BM25 和向量检索各有什么优劣？**  
A: BM25（稀疏检索）擅长精确关键词匹配，对专有名词（如 API 名称、产品型号）效果好；Dense Embedding（稠密检索）擅长语义理解，处理同义词、模糊表达时优势明显。两者互补：BM25 查准率高但泛化差，Dense 泛化好但关键词精确度弱。Hybrid Search 结合两者，用 RRF 融合，平衡 Precision 和 Recall。

**Q: RRF 公式里 k=60 是怎么来的？**  
A: k 是平滑因子，防止排名靠前的文档分数过度高估。k=60 是学术论文（Cormack et al. 2009）中的经验推荐值，实践中通常无需调整。调大 k 会使分数分布更均匀（减弱头部文档优势），调小 k 会使分数差异更大。

**Q: 你们的 BM25 索引存在哪里？IDF 怎么算的？**  
A: 当前 BM25/Sparse 检索落在 `fts.sqlite` 的 FTS5 虚表 `chunks_fts` 上，upsert 时按 `chunk_id + text` 写入，查询时通过 `MATCH + bm25(chunks_fts)` 返回候选与分数。工程上我们不再自己维护一套显式的 IDF 字典或 `bm25/` 目录索引文件，而是把分词匹配、倒排组织和 BM25 打分交给 SQLite FTS5；面试时更应该考察候选人是否理解“为什么这里选 FTS5 做本地稀疏检索、它和 Dense 路召回如何对齐”，而不是背旧版 pickle 结构。

---

## 模块二：Reranker 精排

### 核心实现
- **两段式架构**：粗排召回（低成本泛召回）→ 精排过滤（高成本精确排序）
- **支持三种后端**：
  1. `None`：直接返回 RRF Top-K
  2. `Cross-Encoder`：优先对 fusion 后 Top-N 候选构造 `(query, chunk_retrieval_text)` pairs 进行本地交叉编码打分；若 `chunk_retrieval_text` 缺失，则回退使用 `chunk_text`
  3. `LLM Rerank`：用 LLM 对候选集排序，输出 JSON ranked ids
- **Graceful Fallback**：精排失败/超时时自动回退到 RRF 排名，保证系统可用性

### 高频面试题

**Q: Cross-Encoder 和 Bi-Encoder 的区别？为什么 Cross-Encoder 不能做粗排召回？**  
A: Bi-Encoder（如 Dense Embedding 模型）将 Query 和 Document **分别**编码为向量，再算相似度。可以预先离线计算 Document 向量，查询时只需对比一次，效率高，适合大规模召回。Cross-Encoder 将 Query 和 Document **拼接**后一起输入模型，能捕捉 Query-Document 的交互特征，精度更高，但必须对每对 `(Query, Chunk)` 实时推理，复杂度 O(n)，不适合大规模召回，只适合对小候选集（10–30 条）精排。

**Q: 精排阶段你们用的什么模型？用 CPU 跑 Cross-Encoder 会有延迟问题吗？**  
A: 按当前 `DEV_SPEC`，Cross-Encoder 的主路径是：对 fusion 后 Top-N 候选优先构造 `(query, chunk_retrieval_text)` pairs 做本地交叉编码打分，若 `chunk_retrieval_text` 缺失再回退到 `chunk_text`。示例模型配置为 `BAAI/bge-reranker-v2-m3`；CPU 路径下应限制候选集规模、启用 lazy-load 与进程内缓存，并在超时或异常时回退到 RRF 结果。

---

## 模块三：Ingestion Pipeline 数据摄取流水线

### 九阶段流程
```
dedup → loader → asset_normalize → transform_pre → sectioner → chunker → transform_post → embedding → upsert
```

1. **Dedup**：先基于文件哈希与版本记录判断是否已处理，解决重复摄入与幂等入口问题。
2. **Loader**：按文件类型选择 loader；PDF 场景优先走 PyMuPDF，失败时退到 `pypdf` 或原始文本提取，同时抽取资产引用。
3. **Asset Normalize**：把图片等资产统一落到本地资产存储，建立 `ref_id → asset_id` 映射，避免后续链路直接依赖源文件路径。
4. **Transform Pre**：对 Markdown/文本做前置规范化，保证后续 section/chunk 切分输入稳定。
5. **Sectioner**：先按文档结构切成 section，并为每个 section 分配稳定 `section_id`，保留结构边界。
6. **Chunker**：在 section 内做递归字符切分，生成 `chunk_index / section_path / asset_ids` 等元数据，并基于 `section_id + canonical_text_fingerprint` 生成稳定 `chunk_id`。
7. **Transform Post**：通过通用 `Enricher` 机制补充检索增强信息，把 `chunk_retrieval_text`、`enrich_keys` 等写入 metadata，但**不直接改写** `chunk.text`。
8. **Embedding**：按策略执行 dense / sparse / hybrid 编码；Dense 侧支持缓存，Sparse 侧直接产出供 FTS5 upsert 的文本。
9. **Upsert**：把结果分别写入 `app.sqlite`、`fts.sqlite`、`chroma_lite.sqlite` 与本地 md/assets 目录，形成可查询、可回溯、可删除的多存储状态。

### 幂等性设计
- **chunk_id 生成**：chunker 先对 `chunk.text` 做 canonical 规范化，再计算文本指纹，并与 `section_id` 组合生成稳定 `chunk_id`；这样同一 section 下内容不变时可重复得到相同 ID，而内容变更或 section 边界变化时才会产生新的 chunk。
- **为什么不用 UUID**：UUID 只能保证唯一，不能保证重复摄入时的可重算性；当前实现需要依赖稳定 `chunk_id` 做 upsert、覆盖写入和差量处理，因此必须使用确定性哈希。
- **文件级去重**：在真正进入 loader/chunker 前，会先把文件 SHA256 落到 `app.sqlite` 的 `doc_versions.file_sha256` 上；如果发现同内容版本已存在，就可以直接跳过重复摄入，减少后续解析、切分和 embedding 成本。

### 高频面试题

**Q: 当前系统如何保证切分质量？为什么不用一个独立的 LLM `ChunkRefiner` 来做 Chunking 优化？**  
A: 当前系统把“切分质量”和“检索增强”拆成了两个更可控的层次：
   - **先保结构完整**：`sectioner` 先按 Markdown/页面结构切出 section，避免跨标题、跨页把不相关内容混在一起。
   - **再做递归 chunking**：`chunker` 在 section 内按分隔符递归切分，并保留 `chunk_overlap`、`section_path`、`asset_ids` 等上下文，使 chunk 本身已经是较稳定的语义单元。
   - **最后补检索信号**：如果还需要额外的检索增强，不是让 LLM 直接“重写 chunk”，而是在 `transform_post` 中由 `Enricher` 生成 retrieval-only 信息，写入 metadata 与 `chunk_retrieval_text`。
   - **这样设计的原因**：相比一个黑盒式 `ChunkRefiner`，当前方案更确定、更便宜、更容易 trace 和复现，也更适合做幂等 upsert 与回归测试。

**Q: 当前系统的 metadata enrichment 存在哪里？对检索有什么用？**  
A: 真实实现里，“metadata enrichment” 依然存在，只是不再被硬编码成 `Title/Summary/Tags` 三元组：
   - **存在哪里**：`transform_post` 会把 `Enricher` 的输出合并进 chunk metadata，同时生成 `chunk_retrieval_text` 与 `enrich_keys`；对于视觉增强类结果，还会把 sidecar 数据写入 `asset_enrichments` / `chunk_enrichments` 表。
   - **对检索有什么用**：`chunk_retrieval_text` 会作为召回用文本，把原始 chunk 内容和增强信息拼成更适合检索的视图；而 metadata 中的字段则更适合做结果解释、调试、展示，以及后续基于 `filters` 的扩展过滤能力。
   - **为什么不用固定三元组**：不同 provider 输出的信息粒度不同，当前设计选择“保留通用 enrichment 接口 + retrieval view 组装”，而不是强迫所有增强器都产出同一套 `Title/Summary/Tags` 字段。

**Q: 图片检索是怎么实现的？用户怎么通过文字找到图片？**  
A: 视觉增强结果会进入 metadata 与 `chunk_retrieval_text`，从而参与检索召回；查询结果先返回关联 `asset_id`，需要图片时再通过 `library_query_assets` 按资产 ID 读取文件并返回 Base64 数据。

---

## 模块四：可插拔架构

### 核心设计
- 6 大组件均有抽象 Base 类：`BaseLoader` / `BaseSplitter` / `BaseTransform` / `BaseEmbedding` / `BaseVectorStore` / `BaseReranker`
- **工厂模式**：各组件通过 Factory 函数根据 YAML 配置实例化，调用方不直接 new 具体实现类
- **配置驱动**：修改 `config/settings.yaml` 即可切换后端，零代码修改

### 新增 Provider 流程（面试经典追问）
1. 新建 `src/libs/{component}/your_provider.py`，继承对应 Base 类，实现接口方法
2. 在对应 Factory 函数中注册新 provider 名称和类映射
3. 在 `config/settings.yaml` 中配置 `provider: your_provider`
4. 只需增量修改，不需要改已有代码

### 当前支持
- LLM：Azure OpenAI / OpenAI / Ollama / DeepSeek
- Embedding：OpenAI / Azure / Ollama
- Vector Store：Chroma（接口预留 Qdrant/Pinecone 替换）
- Reranker：Cross-Encoder / LLM Rerank / None

---

## 模块五：MCP 协议集成

### 核心规范
- **协议**：MCP（Model Context Protocol），基于 JSON-RPC 2.0
- **传输层**：Stdio Transport（Client 以子进程方式启动 Server，双方通过 stdin/stdout 通信）
- **为什么用 Stdio**：零网络依赖，无需端口/鉴权，天然适合私有知识库；stdout 只输出合法 MCP 消息，日志走 stderr

### 暴露的 Tools
| 工具名 | 功能 | 关键参数 |
|--------|------|---------|
| `library_query` | 主检索入口，执行 Hybrid Search + 可选 Rerank，返回回答与引用 | `query`, `top_k?`, `filters?`, `strategy_config_id?` |
| `library_query_assets` | 按资产 ID 读取图片/附件内容，返回 Base64 数据 | `asset_ids`, `variant?`, `max_bytes?` |
| `library_get_document` | 获取某个文档版本的规范化 Markdown 内容 | `doc_id`, `version_id`, `max_chars?` |
| `library_list_documents` | 列出文档版本，支持分页与删除状态过滤 | `limit?`, `offset?`, `include_deleted?`, `doc_id?` |
| `library_delete_document` | 删除整份文档或指定版本（当前 MCP 仅开放 soft delete） | `doc_id`, `version_id?`, `mode?`, `reason?`, `dry_run?` |
| `library_ingest` | 摄入本地文档，创建或续接文档版本生命周期 | `file_path`, `policy?`, `strategy_config_id?` |
| `library_ping` | 健康检查与连通性验证 | 无 |

### Citation 设计
每个检索结果携带结构化引用：来源文件名、页码、chunk 内容摘要，方便 Client 展示"回答依据"，增强用户对 AI 输出的信任。

### 高频面试题

**Q: MCP 和普通 REST API 有什么区别？**  
A: MCP 是专为 AI Agent 设计的上下文协议，定义了标准的 `tools`/`resources`/`prompts` 接口，任何合规的 MCP Client（Copilot、Claude Desktop 等）都能即插即用，无需定制集成。REST API 需要客户端专门适配，MCP 通过协议标准化消除了这一成本。

**Q: Stdio Transport 有什么局限性？什么情况下需要换 HTTP Transport？**  
A: Stdio 适合本地单进程场景。局限：不支持远程调用（Client 和 Server 必须在同一机器），不支持多 Client 并发连接。如需远程访问、多用户并发或负载均衡，需切换到 HTTP+SSE Transport。

---

## 模块六：文档生命周期管理

### 生命周期相关 MCP Tools
- `library_ingest`：负责把本地 `pdf/md` 文档纳入系统生命周期，完成从“原始文件”到“可检索文档版本”的创建。
  - **功能**：校验 `file_path / policy / strategy_config_id`，执行 dedup → chunk → embed → upsert 全链路。
  - **实现方案**：MCP 层先通过 `normalize_ingest_input` 规范参数，再调用 `IngestRunner.run(...)`；其中 `policy` 控制遇到重复文件时是跳过、创建新版本还是继续。
  - **主要函数**：`src/mcp_server/mcp/tools/ingest.py` 中的 `normalize_ingest_input`、`make_tool`，以及 `src/core/runners/ingest.py` 中的 `IngestRunner.run`。

- `library_list_documents`：负责列出当前已进入生命周期管理的文档版本，属于管理侧“盘点/分页浏览”入口。
  - **功能**：支持 `limit / offset / include_deleted / doc_id`，返回文档版本列表，而不是旧设计里的 collection 视图。
  - **实现方案**：MCP 层完成分页参数校验后，直接读取 `app.sqlite`，通过 `SqliteStore.list_doc_versions(...)` 返回结构化版本列表。
  - **主要函数**：`src/mcp_server/mcp/tools/list_documents.py` 中的 `make_tool`，以及 `src/ingestion/stages/storage/sqlite.py` 中的 `list_doc_versions`。

- `library_get_document`：负责读取某个文档版本的规范化内容，属于生命周期中的“查看事实层内容”入口。
  - **功能**：按 `doc_id + version_id` 读取对应版本的 `md_norm.md`，支持 `max_chars` 截断，便于管理端查看当前版本实际入库内容。
  - **实现方案**：先通过 `_resolve_md_norm_path(...)` 定位到规范化 Markdown 文件，再通过 `_read_text_limited(...)` 控制读取长度；如果目标版本不存在，则直接返回参数错误。
  - **主要函数**：`src/mcp_server/mcp/tools/get_document.py` 中的 `_resolve_md_norm_path`、`_read_text_limited`、`make_tool`。

- `library_delete_document`：负责把文档或某个文档版本从生命周期中移除，是管理侧删除入口。
  - **功能**：支持按 `doc_id` 删除整份文档，或按 `doc_id + version_id` 删除指定版本；支持 `mode` 与 `dry_run`，但当前 MCP 仅开放 `soft delete`。
  - **实现方案**：MCP 层先校验 `doc_id / version_id / mode / dry_run`，再调用 `AdminRunner.delete_document(...)`。`soft delete` 通过 `SqliteStore.mark_deleted(...)` 修改 `doc_versions.status`；底层代码仍具备 hard delete 分支，可协调 `app.sqlite`、`fts.sqlite`、`chroma_lite.sqlite` 与本地文件系统删除，但 MCP 默认不开放。
  - **主要函数**：`src/mcp_server/mcp/tools/delete_document.py` 中的 `make_tool`，`src/core/runners/admin.py` 中的 `AdminRunner.delete_document`，以及 `src/ingestion/stages/storage/sqlite.py` 中的 `mark_deleted`、`preview_delete` 等删除辅助函数。

### 设计要点
- 系统里没有单独命名为 `DocumentManager` 的实体，文档生命周期管理是通过一组 MCP admin tools + runner/store 协作完成的。
- 生命周期主线是：`ingest` 创建版本 → `list/get` 查看版本状态与内容 → `delete` 标记删除或物理删除版本。
- 删除之所以不是“只改一张表”，是因为文档版本同时影响主数据库、稀疏索引、向量索引以及本地 md/raw/assets 文件；即使当前 MCP 只开放 soft delete，底层实现仍然按跨存储一致性设计。

### 高频面试题

**Q: 为什么文档删除不能只删数据库里的一条记录？当前系统是怎么处理生命周期一致性的？**  
A: 因为一个文档版本在系统里同时对应多层状态：`app.sqlite` 里有版本与 chunk 元数据，`fts.sqlite` 里有 sparse 检索文本，`chroma_lite.sqlite` 里有向量表示，本地文件系统里还有原始文件、规范化 Markdown 和资产文件。如果只删其中一层，就会出现“列表里看不到但还能被召回”或“索引删了但原始文件还在”的不一致。当前 MCP 层默认走 soft delete，只把 `doc_versions.status` 标成 deleted，降低误删风险；底层 `AdminRunner.delete_document(...)` 则保留 hard delete 协调逻辑，用于需要彻底清理多存储状态的场景。

---

## 模块七：可观测性与追踪系统

### Trace 体系
- **双链路**：
  - **Ingestion Trace**：按真实 pipeline stage 记录 `dedup → loader → asset_normalize → transform_pre → sectioner → chunker → transform_post → embedding → upsert`。
  - **Query Trace**：按在线查询阶段记录 `query_norm → retrieve_dense → retrieve_sparse → fusion → rerank → context_build → generate → format_response`。
- **存储**：trace envelope 默认可落到 `logs/traces.jsonl`，也支持写入 `data/sqlite/traces.sqlite`，便于后续列表查询、按 `trace_id` 回放和 Dashboard/API 消费。
- **TraceContext**：显式上下文模式，负责管理 `trace_id / trace_type / strategy_config_id`、span 栈、trace 级事件、`providers_snapshot` 和 `replay_keys`；各阶段通过 `obs.with_stage(...)` 生成 `stage.start / stage.end / stage.error` 事件，查询链路还会额外记录候选预览、融合结果和 `ranked_chunk_ids` 等回放信息。

### Dashboard 6个页面
1. **系统总览**：当前组件配置 + Collection 统计
2. **数据浏览器**：文档/Chunk/图片详情查看
3. **Ingestion 管理**：文件上传、实时进度、文档删除
4. **Ingestion 追踪**：阶段耗时瀑布图
5. **Query 追踪**：Dense/Sparse 召回对比、Rerank 前后排名变化
6. **评估面板**：Ragas 指标、历史趋势

### 动态渲染设计
Dashboard 基于 Trace 中的 `method`/`provider` 字段**动态渲染**，更换可插拔组件后 Dashboard 自动适配，无需修改代码。

---

## 模块八：评估体系

### 指标体系
- **Hit Rate@K**：Top-K 结果中至少有一条命中 Golden Answer 的比例
- **MRR（Mean Reciprocal Rank）**：第一条命中结果的排名倒数均值，衡量头部排序质量
- **Ragas 指标集**：Faithfulness（回答是否基于检索内容）、Answer Relevancy（回答与问题相关性）、Context Precision（检索结果精准度）
- **可插拔**：CompositeEvaluator 支持多评估器并行执行，Ragas / 自定义指标均可挂载

### Golden Test Set
当前项目中的 golden set / eval dataset 主要保存在 `tests/datasets/rag_eval_small.yaml` 与 `tests/datasets/retrieval_small.yaml`，由集成测试和 `EvalRunner` 共同读取，用于回归比较检索与回答质量。

设计原则：
- **小而稳定**：数据集规模不追求大，而是优先覆盖关键能力点，保证每次策略调整后都能快速回归。
- **问题与预期显式配对**：每条 case 都有稳定的 `case_id`、查询文本，以及 `expected keywords` 或 `expected_terms` 这类可检查预期，便于做自动化评分。
- **检索与生成分层**：`retrieval_small.yaml` 更偏向“构造最小语料 + 验证召回是否命中”，`rag_eval_small.yaml` 更偏向“给定真实查询 case，验证最终检索/回答结果是否满足预期关键词”。
- **围绕核心机制选题**：当前样本集中覆盖了 embedding cache、SQLite FTS5 / BM25、RRF fusion 等核心实现点，目的是让回归数据直接对齐系统真实设计，而不是做泛化问答题库。

保存与读取方式：
- `tests/datasets/retrieval_small.yaml`：保存最小检索语料 `docs` 与查询 `queries`，主要用于集成测试先摄入样本文档，再验证检索链路。
- `tests/datasets/rag_eval_small.yaml`：保存 `dataset_id / version / cases`，每个 case 带 `case_id`、`query`、`tags` 和 `expected.keywords`，供 `EvalRunner` 按 dataset_id 加载并逐条执行评估。
- `EvalRunner` 会根据 `dataset_id` 解析到 `tests/datasets/<dataset_id>.yaml`（或 `.json`），逐条运行查询，并把结果持久化到 `app.sqlite` 的 `eval_runs` 与 `eval_case_results`。

---

## 模块九：工程化实践

### 测试体系
- **分层金字塔**：Unit（单元）→ Integration（集成）→ E2E（端到端）
- **单元测试 mock 策略**：用 `unittest.mock.patch` mock LLM 客户端，返回预设响应，避免实际 API 调用；测试关注业务逻辑而非外部依赖
- **测试覆盖**：采用 Unit → Integration → E2E 金字塔，并补充 golden / trace schema / 稳定性契约 / 评估数据集回归，确保链路行为、观测结构与质量门禁同时可回归。
- **E2E 测试**：围绕真实 MCP stdio server、Dashboard smoke / real-data、资源拉取与 golden 回归做端到端验证；MCP 场景通过真实子进程启动 server，发送 JSON-RPC 消息完成闭环校验。

### 持久化存储架构
| 存储 | 文件 | 用途 |
|------|------|------|
| `app.sqlite` | `data/sqlite/app.sqlite` | 主数据、文档版本、chunk/asset 元数据、文件哈希去重记录、评估结果 |
| `fts.sqlite` | `data/sqlite/fts.sqlite` | 稀疏检索文本与 FTS5/BM25 查询 |
| `chroma_lite.sqlite` | `data/chroma/chroma_lite.sqlite` | Dense 向量数据与对应 metadata |
| `raw / md / assets` | `data/raw` / `data/md` / `data/assets` | 原始文件、规范化 Markdown、资产文件本体 |

**设计原则**：Local-First，零外部数据库依赖，`pip install` 即可运行。

---

## 模块十：画廊场景上线口径

### 业务对象分层
- **知识资产类型**：画廊场景下通常至少拆成四类：`艺术家资料`、`作品资料`、`展览/对谈文档`、`价格/销售敏感资料`。
- **为什么要先分层**：这四类数据的更新频率、查询方式、权限要求完全不同。如果不先分层，后面的 ingestion、filter、权限隔离和解释链路都会混在一起。
- **推荐补充字段**：
  - 艺术家资料：`artist_name`、`bio_period`、`nationality`、`style_tags`
  - 作品资料：`work_title`、`artist_name`、`year`、`medium`、`dimension`、`series`
  - 展览/对谈文档：`exhibition_name`、`venue`、`date_range`、`speaker`
  - 敏感资料：`price_band`、`currency`、`sales_status`、`access_level`
- **落到系统中的位置**：结构化字段优先进入 chunk metadata，供 pre-filter / citation / 管理侧使用；图片 OCR、caption、关键词等增强信息进入 `chunk_retrieval_text` 或 sidecar，用于 post-filter 与 rerank。

### 画廊查询是怎么接入系统的
- **推荐接入方式**：画廊前端不直接连 MCP stdio 进程，而是通过“画廊业务后端 → RAG 服务层”访问。
- **原因**：
  - 权限和登录态必须在业务侧接住；
  - 业务系统需要把用户角色转换成 query filters；
  - 查询和图片读取应拆成两步，避免一次请求返回大体积资源。
- **典型调用链路**：
  1. 销售或策展人在画廊 CRM/后台发起问题；
  2. 业务后端根据当前用户角色生成过滤条件和可见范围；
  3. 调用 `library_query` 获取 answer、citations、`asset_ids`、`trace_id`；
  4. 如果前端需要展示作品图，再调用 `library_query_assets` 拉取缩略图或原图；
  5. 如果用户点开来源，再调用 `library_get_document` 回看事实层内容。
- **核心原则**：`query` 只负责“检索 + 回答 + 引用”，图片/附件按 `asset_id` 按需拉取。

### 画廊场景里的过滤与排序
- **Hard Filter（前置硬过滤）**：
  - `doc_id / version_id`
  - `artist_name / exhibition_name`
  - 明确时间范围（如“2024 年展览”）
  - 权限字段 `access_level`
- **Post Filter（后置硬过滤）**：
  - `image_caption`
  - `ocr_text`
  - 由 Enricher 生成但底层索引不稳定支持的增强字段
- **Soft Preference（软偏好）**：
  - `prefer_recent`
  - `prefer_official`
  - `prefer_has_image`
  - “优先近两年展览”“优先带图作品”“优先官方策展文案”
- **面试回答重点**：画廊查询通常不是纯语义搜索，而是“结构约束 + 多模态增强 + 排序偏好”的组合问题。

### 敏感信息为什么必须单独隔离
- **画廊里的风险点**：价格、销售状态、买家沟通记录、未公开展览资料，都不应该和公开艺术家/作品介绍混在一个查询视图里。
- **当前系统设计口径**：`access_level` 属于 Hard Filter，且安全字段默认应走 `missing → exclude`。
- **真实上线时要补的能力**：
  - 用户身份 → 角色 → 查询过滤条件映射
  - 管理端对敏感文档的打标和版本控制
  - 删除/下线资料时的多存储一致性
- **如果不做**：销售可能会在面向客户的查询里命中内部价格文档，这是线上事故，不是“回答不准”那么简单。

### 上线流程（SOP 口径）
- **1. 环境准备**：准备预发布和生产环境，挂载 SQLite、资产目录、trace 日志目录，接通模型服务与配置。
- **2. 数据导入**：先导公共资料（艺术家、展览、作品），再导敏感资料，并验证 metadata、asset_ids、版本号是否正确。
- **3. Golden Set 验收**：构造画廊业务专用 case，至少覆盖艺术家查询、相似作品发现、展览关联、图片命中、敏感价格隔离。
- **4. 灰度上线**：先给内部策展/运营试用，再逐步开放给销售顾问。
- **5. 监控与回滚**：关注空结果率、错误引用率、图片拉取失败率、trace 异常与评估分数漂移；一旦策略变更导致效果下降，优先按 `strategy_config_id` 回滚。

### 为什么这个场景适合 Agent
- 画廊业务查询往往不是“单跳问答”，而是“找相关作品 → 展示出处 → 拉图验证 → 打开原文档继续追问”的链式操作。
- MCP tool 闭环正好适合这种模式：
  - `library_query`：给出回答与引用
  - `library_query_assets`：补图片/附件
  - `library_get_document`：回看原文
  - `library_list_documents/delete_document/ingest`：管理文档生命周期
- 因此在面试里，如果候选人说“这是一个画廊 Agent 场景”，真正该讲清楚的不是“用了 Agent”这句话，而是 **Agent 如何通过多步 tool 调用完成业务闭环**。

### 高频面试题

**Q: 如果把这套系统落到画廊内部，你最先做的不是模型调优，而是什么？为什么？**  
A: 先做知识资产分层和权限设计。因为画廊场景里数据天然分为公开资料和敏感资料，如果不先把文档类型、结构字段、权限边界定义清楚，后面的 ingestion、filter、rerank 再强也会把敏感价格或销售信息混进普通查询结果。模型效果问题可以后调，但权限事故是不能接受的。

**Q: 画廊系统为什么不应该直接连底层 RAG 进程，而要经过业务后端或网关？**  
A: 因为真实上线时不仅要“查得到”，还要处理鉴权、限流、审计、用户角色映射和接口稳定性。画廊业务后端负责把当前用户身份转换成 query filters，再调用 `library_query`；前端若需要图片，再单独调 `library_query_assets`。这样才能把知识服务和业务系统边界隔离开。

**Q: 如果用户问“给我推荐和这件作品风格相近、近两年参加过重要展览的作品”，你会怎么拆这个查询？**  
A: 这是一个典型的“结构约束 + 语义召回 + 排序偏好”组合。作品相似度主要靠 dense recall + rerank；“近两年展览”属于时间类过滤，可按表达强度决定是 Hard Filter 还是 Soft Preference；“重要展览”往往还需要结合 metadata 或业务定义标签来做排序加权，而不是只靠 embedding 自己猜。

---

## 常见"露馅"警示点

面试中如候选人无法解释以下细节，需在报告中标记：

| 简历描述 | 深挖问题 | 露馅信号 |
|---------|---------|---------|
| "混合检索命中率提升 XX%" | 怎么测的？用什么指标？ | 说不清 Hit Rate@K 定义或无测试数据 |
| "RRF 融合算法" | 公式是什么？k 值怎么设的？ | 无法说出公式，或说成线性加权 |
| "设计可插拔架构" | 新增 Provider 要改哪些文件？ | 不知道抽象接口在哪定义 |
| "幂等 Upsert" | chunk_id 怎么生成的？ | 说是 UUID，或说不清楚 |
| "MCP 协议实现" | Stdio Transport 是怎么工作的？ | 不知道 stdout/stderr 分工 |
| "TDD 开发，1200+ 测试" | 单元测试怎么 mock LLM？ | 不知道 mock 策略 |
| "多模态检索" | Caption 文本怎么参与检索？ | 说不清与正文的关系 |
| "跨存储协调删除" | 删一个文档要操作几个存储？ | 只说 Chroma 或说不知道 |
