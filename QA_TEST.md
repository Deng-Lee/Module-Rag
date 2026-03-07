# QA 专项测试计划（对齐目录结构）

版本：1.0  
更新时间：2026-03-03  
覆盖范围：系统功能验证、Dashboard API、CLI 脚本、Provider 切换、数据生命周期、容错降级、端到端验收

约束：

- 本计划不绑定任何特定 MCP Client；后续由 Skills 驱动自动执行与回填进度。
- 所有用例都声明 `Profiles`：
  - `OFFLINE`：不依赖外部网络/真实模型，可在本机稳定回归（推荐 `strategy_config_id=local.test`）。
  - `REAL`：依赖真实模型/真实后端，验证真实效果（推荐 `strategy_config_id=local.default`，需要可用网络与密钥配置）。
- 结果记录与判定规则：若用例要求 `OFFLINE/REAL` 两种 profile，则必须两者都通过才算 `Overall=PASS`。

---

## 目录

- [A. Dashboard - Overview（系统总览）](#a-dashboard---overview系统总览)
- [B. Dashboard - Data Browser（数据浏览）](#b-dashboard---data-browser数据浏览)
- [C. Dashboard - Ingestion Manager（摄取管理）](#c-dashboard---ingestion-manager摄取管理)
- [D. Dashboard - Ingestion Traces（摄取追踪）](#d-dashboard---ingestion-traces摄取追踪)
- [E. Dashboard - Query Traces（查询追踪）](#e-dashboard---query-traces查询追踪)
- [F. Dashboard - Evaluation Panel（评估面板）](#f-dashboard---evaluation-panel评估面板)
- [G. CLI - 数据摄取（ingest）](#g-cli---数据摄取ingest)
- [H. CLI - 查询（query）](#h-cli---查询query)
- [I. CLI - 评估（evaluate）](#i-cli---评估evaluate)
- [J. MCP Server - 协议交互（stdio）](#j-mcp-server---协议交互stdio)
- [K. Provider 切换 - DeepSeek LLM](#k-provider-切换---deepseek-llm)
- [L. Provider 切换 - Reranker 模式](#l-provider-切换---reranker-模式)
- [M. 配置变更与容错](#m-配置变更与容错)
- [N. 数据生命周期闭环](#n-数据生命周期闭环)
- [O. 文档替换与多场景验证](#o-文档替换与多场景验证)
- [P. Trace 与回放稳定性](#p-trace-与回放稳定性)
- [Q. 稳定性契约（canonical / chunk_id / asset_id）](#q-稳定性契约canonical--chunk_id--asset_id)
- [R. MCP Tool 黑盒闭环](#r-mcp-tool-黑盒闭环)
- [S. 评估数据集与质量门禁](#s-评估数据集与质量门禁)
- [T. Golden / 回归基线](#t-golden--回归基线)

---

## 测试数据（固定 fixtures）

文档目录：

`/Users/lee/Documents/AI/MODULE-RAG/tests/fixtures/docs`

核心文件：

- `simple.pdf`：纯文本 PDF
- `complex_technical_doc.pdf`：多页结构化 PDF
- `blogger_intro.pdf`：中文 PDF
- `with_images.pdf`：含图片 PDF
- `sample.md`：Markdown（含 heading + 关键词）
- `sample.txt`：不支持格式（负向）
- `test_vision_llm.jpg`：OCR/Caption 输入图片（可选）

---

## 状态、系统状态与执行规则（Skills 可复用）

### 用例状态字段（建议写回本文件，便于“计划+进度”合一）

- `状态`：`TODO | RUNNING | PASS | FAIL | BLOCKED | SKIP`
- `PASS` 判定：
- 需要同时覆盖 `OFFLINE/REAL` 的用例：两者都 `PASS` 才算 `Overall=PASS`
- 只覆盖单一 profile 的用例：该 profile `PASS` 即算 `Overall=PASS`
- `BLOCKED`：由于当前系统状态不满足前置条件、或运行环境缺依赖（如无外网/无密钥）导致无法执行

### 系统状态（System State）约定：用来决定“该不该跑这一阶段”

系统状态通过 `GET /api/overview`（或其等价的 TestClient 调用）判断，核心关注：

- `docs/chunks/assets` 是否为 0（是否空库）
- 最近 `traces` 是否存在（是否已有可追踪样本）
- 是否已完成至少一次 ingest（是否具备检索前置）

推荐把系统状态粗分为四档（不需要额外落库，只是测试调度的“口径”）：

- `S0_EMPTY`：无文档（docs=0）
- `S1_INGESTED_MIN`：至少 1 个文档且 chunks>0（可跑基础 query）
- `S2_INGESTED_MULTI`：>=2 个文档，且包含 pdf+md（可跑混合召回、对比、替换）
- `S3_DELETED`：存在 deleted 版本（可跑删除/过滤闭环）

执行调度规则（给 Skills 用）：

- 若用例前置要求 `S1+`，但当前为 `S0_EMPTY`：
- 优先执行该用例声明的 `Setup`（通常是 ingest fixtures）把系统推进到目标状态
- 若不允许修改数据（比如当前只验证 dashboard 空库展示），则将该用例标记为 `BLOCKED (state)`，不应硬跑 query/retrieval

---

## 公共执行入口（启动方式/命令模板，Skills 可复用）

基础准备（一次性）：

1. 目录初始化：`bash scripts/bootstrap_local.sh`
2. 虚拟环境：默认使用 `.venv/bin/python`（脚本已内置）；若你用系统 python，需保证依赖齐全
3. 配置入口：
- 默认读取 `config/settings.yaml`
- 如需切换 settings 文件：`MODULE_RAG_SETTINGS_PATH=/abs/path/to/settings.yaml`

CLI（便于本地快速定位）：

- `bash scripts/dev_ingest.sh <file_path> <strategy_config_id> <policy>`
- `bash scripts/dev_query.sh "<query>" <strategy_config_id> <top_k>`
- `bash scripts/dev_eval.sh <dataset_id> <strategy_config_id> <top_k>`

Dashboard API（API-only，无 UI；建议用 TestClient 调用，不占端口）：

- `from src.observability.dashboard.app import create_app`
- `TestClient(create_app()).get("/api/overview")`

Dashboard UI（如后续实现 Vite+React 前端时）：

- 后端（API）：`bash scripts/dev_dashboard.sh 127.0.0.1 7860`
- 前端（占位，具体路径以实际落地为准）：`pnpm -C web/dashboard dev --port 5173`
- 浏览器访问：`http://127.0.0.1:5173`

MCP（stdio）工具名（当前实现）：

- `library_ping`
- `library_ingest`
- `library_query`
- `library_query_assets`
- `library_get_document`
- `library_list_documents`
- `library_delete_document`

---

## A. Dashboard - Overview（系统总览）

启动方式（UI/API 两种验证口径）：

- API-only（当前实现）：直接用 TestClient 或启动 `scripts/dev_dashboard.sh`
- UI（待实现）：若存在 Dashboard 前端，则在浏览器校验页面渲染与交互；自动化建议使用 Playwright（后续单独补）

### A-01 Overview 接口可用

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 用 TestClient 调用 `GET /api/overview`。

预期：

1. HTTP 200。
2. 返回字段包含 `assets`、`health`、`providers`。

记录：

1. 响应 JSON（至少保存 keys 与核心计数）。

### A-02 Providers 配置快照可解释

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `GET /api/overview`。

预期：

1. `providers` 至少包含当前策略中关键组件的 provider_id（如 embedder/vector_index/retriever/fusion 等）。
2. 当切换 strategy（`local.test` vs `local.default`）时，providers 快照发生对应变化。

### A-03 资产计数与落库一致

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`
2. ingest `tests/fixtures/docs/with_images.pdf`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 对 `sample.md`、`with_images.pdf` 执行 ingest（对应 profile 的 strategy）。
2. 调用 `GET /api/overview`。

预期：

1. `assets.docs` >= 2。
2. `assets.chunks` 与 ingest 的 chunks_written 总量同量级（允许不同 doc 重复 ingest 导致增量）。
3. `assets.assets` >= 1（来自 `with_images.pdf`）。

### A-04 健康指标能反映最近调用

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 执行一次 ingest 与一次 query（任意文档/查询）。
2. 调用 `GET /api/overview`。

预期：

1. `health.recent_traces` > 0。
2. `health.error_rate` 与最近 trace 的 status 分布一致。

### A-05 空库/空 trace 兼容

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 指向一个全新 data_dir（空 sqlite/chroma/logs）。
2. 调用 `GET /api/overview`。

预期：

1. HTTP 200。
2. docs/chunks/assets 计数为 0 或缺省值，但不报错。

### A-UI-01（待实现）Overview 页面可渲染（非 API）

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

启动：

1. 启动后端：`bash scripts/dev_dashboard.sh 127.0.0.1 7860`
2. 启动前端：`pnpm -C web/dashboard dev --port 5173`（占位，路径以最终落地为准）
3. 浏览器打开：`http://127.0.0.1:5173`

步骤：

1. 进入 “System Overview/总览” 页面（路由以最终实现为准）。

预期：

1. 页面无报错白屏。
2. 能看到组件配置区（providers snapshot）与资产计数区（docs/chunks/assets）。

### A-UI-02（待实现）Providers 卡片详情可展开

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 在 Overview 页面点击任意 provider 卡片（如 embedder/vector_store）。

预期：

1. 展开区域展示关键字段（provider_id、model、endpoint_key、关键 params），且与 `/api/overview.providers` 一致。

### A-UI-03（待实现）健康指标随操作刷新

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 执行一次 ingest 与一次 query。
2. 刷新 Overview 页面或触发页面自动刷新。

预期：

1. “最近 traces/最近调用耗时”等健康指标发生可解释变化（与 `/api/overview.health` 对齐）。

---

## B. Dashboard - Data Browser（数据浏览）

启动方式（UI/API 两种验证口径）：

- API-only（当前实现）：直接用 TestClient 或启动 `scripts/dev_dashboard.sh`
- UI（待实现）：若存在 Dashboard 前端，则在浏览器校验文档列表、筛选、chunk 详情渲染；自动化建议使用 Playwright（后续单独补）

### B-01 文档列表接口可用

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 先 ingest 任意 1 个文档。
2. 调用 `GET /api/documents?limit=50&offset=0`。

预期：

1. HTTP 200。
2. `items` 为数组，包含 `doc_id/version_id/status` 等字段。

### B-02 分页与过滤（doc_id）

Profiles：OFFLINE/REAL

前置系统状态：至少 `S2_INGESTED_MULTI`

Setup（若当前 < S2）：

1. ingest `tests/fixtures/docs/sample.md`
2. ingest `tests/fixtures/docs/simple.pdf`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. ingest 至少 2 个不同文档。
2. 调用 `GET /api/documents?limit=1&offset=0` 与 `offset=1`。
3. 取其中一个 doc_id，再调用 `GET /api/documents?doc_id=<id>`。

预期：

1. limit/offset 生效，items 数量符合分页。
2. doc_id 过滤后只返回该 doc_id 的版本。

### B-03 include_deleted 行为

Profiles：OFFLINE/REAL

前置系统状态：至少 `S3_DELETED`

Setup（若当前 < S3）：

1. ingest `tests/fixtures/docs/sample.md`
2. soft delete 该文档版本

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. ingest 任意文档，记下 doc_id/version_id。
2. soft delete 该 version（走 `/api/delete` 或 MCP tool）。
3. 调用 `GET /api/documents?include_deleted=false` 与 `include_deleted=true`。

预期：

1. `include_deleted=false` 不包含 deleted 版本。
2. `include_deleted=true` 包含 deleted 版本且 status=deleted。

### B-04 Chunk 详情接口可用

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 执行一次 query，得到任意 `chunk_id`。
2. 调用 `GET /api/chunk/<chunk_id>`。

预期：

1. HTTP 200。
2. 返回包含 `chunk_text`、`section_path`、`doc_id/version_id`。
3. 若该 chunk 关联图片，返回 `asset_ids` 非空。

### B-05 Chunk 不存在的错误路径

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `GET /api/chunk/chk_not_exists`。

预期：

1. HTTP 200（当前实现）或 404（未来可改）；但必须返回结构化 `error:not_found`。

### B-UI-01（待实现）文档列表页面渲染 + 分页

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=ED(UI not implemented)，Overall=BLOCKED

步骤：

1. 打开 “Data Browser/数据浏览” 页面（路由以最终实现为准）。
2. 切换分页（下一页/上一页）。

预期：

1. 列表可见且不为空。
2. 分页切换后 items 发生变化或提示“已到末尾”，行为与 `/api/documents?limit/offset` 一致。

### B-UI-02（待实现）doc_id 过滤与 include_deleted 开关

Profiles：OFFLINE/REAL

前置系统状态：至少 `S3_DELETED`

Setup（若当前 < S3）：

1. ingest `tests/fixtures/docs/sample.md`
2. soft delete 该版本

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 在列表中选中某个 doc_id 做过滤（或输入框筛选）。
2. 关闭 include_deleted，确认 deleted 版本隐藏。
3. 打开 include_deleted，确认 deleted 版本可见且标识为 deleted。

预期：

1. UI 筛选结果与 `/api/documents` 的参数行为一致。

### B-UI-03（待实现）Chunk 详情页可打开并展示引用信息

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`
2. 执行一次 query 以获得 chunk_id

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 在 UI 中打开一个 chunk 详情（从 query 结果或 doc 详情跳转）。

预期：

1. 展示 `chunk_text`、引用信息（doc_id/version_id/section_path/page_range 等）。
2. 若存在 `asset_ids`，展示为可点击的资源锚点（资源拉取能力后续验证）。

---

## C. Dashboard - Ingestion Manager（摄取管理）

启动方式（UI/API 两种验证口径）：

- API-only（当前实现）：直接调用 `POST /api/ingest` 或用 CLI `scripts/dev_ingest.sh`
- UI（待实现）：若存在 Dashboard 前端，则校验文件选择、提交、结果 toast/trace_id 展示；自动化建议使用 Playwright（后续单独补）

### C-01 ingest API 基线可用

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `POST /api/ingest`，payload：
2. `file_path=.../sample.md`，`policy=default`，`strategy_config_id=default`。

预期：

1. 返回 `status=ok`。
2. 返回 `trace_id` 且结构化结果包含 `doc_id/version_id`。

### C-02 ingest API 负向：缺 file_path

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `POST /api/ingest`，payload 为空或缺 `file_path`。

预期：

1. 返回 `status=error`，reason 可解释。

### C-03 ingest API 负向：路径不存在

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `POST /api/ingest`，file_path 指向不存在文件。

预期：

1. 返回 error，且不产生脏写入。

### C-04 ingest API 支持 pdf/md，两类路径至少一类可跑通

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. ingest `simple.pdf`。
2. ingest `sample.md`。

预期：

1. 两类格式均可被识别。
2. 若 profile=REAL 外部依赖不可用，必须以结构化错误返回并可在 trace 中定位。

### C-UI-01（待实现）摄取管理页面：提交一次 ingest 并展示结果

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 打开 “Ingestion Manager/摄取管理” 页面。
2. 选择/填写 `tests/fixtures/docs/sample.md`（文件选择器或路径输入）。
3. 触发 ingest。

预期：

1. UI 显示 ingest 成功或失败（可解释错误）。
2. 成功时展示 `doc_id/version_id/trace_id`，并提供跳转到 trace 详情入口。

### C-UI-02（待实现）负向提示：缺 file_path 不应触发请求

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 打开 Ingestion Manager 页面。
2. 不选择文件直接点击 ingest。

预期：

1. UI 在前端侧拦截并提示必填字段（或后端返回 error 后 UI 明确展示）。

### C-UI-03（待实现）多次 ingest 的历史记录/最近任务展示

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`
2. ingest `tests/fixtures/docs/simple.pdf`

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 在 UI 查看最近 ingest 任务列表。

预期：

1. 列表数量与 `/api/traces?trace_type=ingestion` 同量级。
2. 每条任务可点击进入详情。

---

## D. Dashboard - Ingestion Traces（摄取追踪）

启动方式（UI/API 两种验证口径）：

- API-only（当前实现）：直接调用 `GET /api/traces` / `GET /api/trace/<id>`
- UI（待实现）：若存在 Dashboard 前端，则校验 traces 列表、筛选、trace 详情展开；自动化建议使用 Playwright（后续单独补）

### D-01 traces 列表可分页

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`（且存在 ingest trace）

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 执行多次 ingest。
2. 调用 `GET /api/traces?trace_type=ingestion&limit=10&offset=0`。

预期：

1. items 为数组。
2. 可通过 limit/offset 翻页。

### D-02 单条 trace 可回放（字段完整）

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`（且存在 ingest trace）

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 从 `/api/traces` 取一个 trace_id。
2. 调用 `GET /api/trace/<trace_id>`。

预期：

1. 返回包含 `trace_id/trace_type/status/start_ts/end_ts/strategy_config_id/providers`。
2. spans 中包含稳定 stage 名（dedup/loader/chunker/embedding/upsert 等）。

### D-03 失败 trace 的错误分级清晰

Profiles：OFFLINE/REAL

前置系统状态：至少存在 1 条 ingest trace（成功/失败均可）

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 制造一次 ingest 失败（例如 ingest `sample.txt`）。
2. 获取 trace detail。

预期：

1. trace.status=error。
2. events 或 aggregates 中有可定位错误原因（unsupported file type 等）。

### D-UI-01（待实现）摄取追踪页面：列表 + 翻页 + 搜索

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`（且存在 ingest trace）

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 打开 “Ingestion Traces/摄取追踪” 页面。
2. 翻页或按 trace_id/doc_id 过滤（以最终 UI 为准）。

预期：

1. 列表展示与 `/api/traces?trace_type=ingestion` 一致。

### D-UI-02（待实现）Trace 详情：stage 列表与耗时展示

Profiles：OFFLINE/REAL

前置系统状态：至少存在 1 条 ingest trace

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 点击某条 trace 进入详情。

预期：

1. 可看到关键 stage（dedup/loader/sectioner/chunker/transform_post/embedding/upsert）。
2. 每个 stage 显示开始结束时间或耗时，并能定位错误 stage。

---

## E. Dashboard - Query Traces（查询追踪）

启动方式（UI/API 两种验证口径）：

- API-only（当前实现）：直接调用 `GET /api/traces` / `GET /api/trace/<id>`
- UI（待实现）：若存在 Dashboard 前端，则校验 query traces 列表、检索证据展示；自动化建议使用 Playwright（后续单独补）

### E-01 query traces 可筛选

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`（且存在 query trace）

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`
2. query 任意关键词（例如 `FTS5`）

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 执行多次 query。
2. 调用 `GET /api/traces?trace_type=query&limit=10&offset=0`。

预期：

1. items 非空。
2. 可按 status/strategy_config_id 过滤（若实现支持）。

### E-02 query trace 包含检索与排序证据

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 执行一次 query（例如 `FTS5` 或 `Table of Contents`）。
2. 拉取 trace detail。

预期：

1. trace 中存在 retrieval 候选事件或等价字段（dense/sparse/fusion）。
2. 若 rerank 未启用，rerank_used 为 false 或缺省。

### E-03 空召回也必须可诊断

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 或 `S1+` 均可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. query 一个明显不存在的词（例如随机 UUID）。
2. 获取 trace detail。

预期：

1. 返回 sources 为空。
2. trace 仍完整，且标注“无命中”而非 silent fail。

### E-UI-01（待实现）查询追踪页面：列表 + 详情 + 检索证据展示

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`（且存在 query trace）

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`
2. query `FTS5`

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 打开 “Query Traces/查询追踪” 页面。
2. 进入某条 trace 详情。

预期：

1. 能看到 query_norm、retrieval、fusion、(optional) rerank 的证据与指标。
2. 能从 sources 跳转到 chunk 详情或文档位置（若实现了跳转）。

### E-UI-02（待实现）空召回场景：UI 明确提示“无命中”

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 或 `S1+` 均可

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 在 UI 中执行一个明显不存在的 query。

预期：

1. UI 明确显示 “无命中/无 sources”，并能查看 trace 详情定位原因（而非空白页）。

---

## F. Dashboard - Evaluation Panel（评估面板）

说明：当前 Dashboard 评估相关 API 有 stub，真实评估以 `scripts/dev_eval.sh` 为主；本专项验证“入口/持久化/趋势查询”三件事。

启动方式（UI/API 两种验证口径）：

- API-only（当前实现）：直接调用 `POST /api/eval/run` / `GET /api/eval/*`
- UI（待实现）：若存在 Dashboard 前端，则校验“运行评估/历史运行/趋势图”交互；自动化建议使用 Playwright（后续单独补）

### F-01 eval/run API stub 可用

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `POST /api/eval/run`，传入任意 payload。

预期：

1. 返回 `status`，且 payload 被回显或被记录。

### F-02 eval/runs 能读取历史

Profiles：OFFLINE/REAL

前置系统状态：至少存在一次 eval 运行记录（或明确为空）

Setup（建议）：

1. 执行一次 `bash scripts/dev_eval.sh rag_eval_small <strategy> 5`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 先执行一次 `bash scripts/dev_eval.sh rag_eval_small <strategy> 5`。
2. 调用 `GET /api/eval/runs?limit=50&offset=0`。

预期：

1. runs 列表中出现本次 run_id（若实现落库）。
2. 若未落库，需在返回中明确为空而非报错。

### F-03 eval/trends 返回结构稳定

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `GET /api/eval/trends?metric=hit_rate@k&window=30`。

预期：

1. 返回 `metric/window/points[]` 字段，即使 points 为空也不报错。

### F-UI-01（待实现）评估面板：能启动一次评估并看到运行记录

Profiles：OFFLINE/REAL

前置系统状态：建议至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 打开 “Evaluation Panel/评估面板” 页面。
2. 选择 dataset_id（如 `rag_eval_small`）与 strategy（local.test/local.default）。
3. 点击 Run。

预期：

1. UI 展示 run_id 与运行状态（running/success/error）。
2. 运行完成后可在历史列表中查看该 run 的指标详情。

### F-UI-02（待实现）趋势图：切换 metric 与窗口不报错

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可（points 为空也应可渲染）

状态：OFFLINE=BLOCKED(UI not implemented)，REAL=BLOCKED(UI not implemented)，Overall=BLOCKED

步骤：

1. 在趋势图区域切换 `hit_rate@k/mrr/ndcg@k` 等指标（以最终实现为准）。
2. 切换时间窗口（7/30/90 days）。

预期：

1. UI 不报错，空数据时显示“无数据”占位。

---

## G. CLI - 数据摄取（ingest）

启动方式（命令模板）：

- OFFLINE：`bash scripts/dev_ingest.sh <file_path> local.test <policy>`
- REAL：`bash scripts/dev_ingest.sh <file_path> local.default <policy>`
- policy 建议：
- 首次导入用 `new_version`
- 验证文件级去重用 `skip`

### G-01 基线摄取（Markdown）

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 运行：`bash scripts/dev_ingest.sh tests/fixtures/docs/sample.md <strategy> new_version`。

预期：

1. 返回 `status=ok`。
2. `md_norm.md` 落盘存在。

### G-02 PDF 摄取（含图）

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 运行：`bash scripts/dev_ingest.sh tests/fixtures/docs/with_images.pdf <strategy> new_version`。

预期：

1. `assets_written>=1`。
2. 后续 query 能返回 `asset_ids`（见 H-04）。

### G-03 负向：不支持格式拒绝

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 运行：`bash scripts/dev_ingest.sh tests/fixtures/docs/sample.txt <strategy> new_version`。

预期：

1. `status=error`，错误包含 `unsupported file type`。

### G-04 Dedup：同文件 skip

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 对同一文件连续两次 ingest。
2. 第一次 `policy=new_version`，第二次 `policy=skip`。

预期：

1. 第二次决策为 skip，且不进入 loader（trace spans 可验证）。

### G-05 多页 PDF 摄取（长文）

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 运行：`bash scripts/dev_ingest.sh tests/fixtures/docs/complex_technical_doc.pdf <strategy> new_version`。

预期：

1. `chunks_written` 明显大于 5。
2. `sparse_written` 与 chunks 数一致（hybrid 或 sparse 启用时）。

---

## H. CLI - 查询（query）

启动方式（命令模板）：

- OFFLINE：`bash scripts/dev_query.sh "<query>" local.test <top_k>`
- REAL：`bash scripts/dev_query.sh "<query>" local.default <top_k>`
- 前置：至少完成一次 ingest，否则 query 用例应标记 `BLOCKED (state)`

### H-01 稀疏关键词命中（FTS5）

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 确保已 ingest `sample.md`。
2. 运行：`bash scripts/dev_query.sh "FTS5" <strategy> 5`。

预期：

1. sources 中命中包含 `Chroma + FTS5.` 的 chunk。

### H-02 结构化长文命中（TOC）

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/complex_technical_doc.pdf`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 确保已 ingest `complex_technical_doc.pdf`。
2. 运行：`bash scripts/dev_query.sh "Table of Contents" <strategy> 8`。

预期：

1. Top-K 中至少一个 chunk 来自该 doc 的 TOC 附近内容。

### H-03 中文召回（12 万字）

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/blogger_intro.pdf`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 确保已 ingest `blogger_intro.pdf`。
2. 运行：`bash scripts/dev_query.sh "笔记有多少字" <strategy> 5`。

预期：

1. sources 命中包含 `12万字` 的 chunk。

### H-04 图片锚点贯通（asset_ids）

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/with_images.pdf`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 确保已 ingest `with_images.pdf`。
2. query：`bash scripts/dev_query.sh "embedded image" <strategy> 5`。

预期：

1. 至少一条 source 含 `asset_ids`。

### H-05 删除后查询不再命中（soft delete）

Profiles：OFFLINE/REAL

前置系统状态：至少 `S3_DELETED`

Setup（若当前 < S3）：

1. ingest `tests/fixtures/docs/sample.md`
2. 确认 query 命中
3. soft delete 该版本

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. ingest 任意文档并 query 确认命中。
2. soft delete 该 doc/version。
3. 再次 query 同样问题。

预期：

1. 第二次 query 不返回属于 deleted 版本的 sources。

---

## I. CLI - 评估（evaluate）

启动方式（命令模板）：

- OFFLINE：`bash scripts/dev_eval.sh <dataset_id> local.test <top_k>`
- REAL：`bash scripts/dev_eval.sh <dataset_id> local.default <top_k>`

### I-01 评估 runner 可运行且失败不崩

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 也可（但更推荐至少 `S1_INGESTED_MIN`）

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 运行：`bash scripts/dev_eval.sh rag_eval_small <strategy> 5`。

预期：

1. 输出 `run_id`。
2. 即使外部后端不可用，也应返回结构化指标（可为 NaN/backend_error），但进程不崩溃。

---

## J. MCP Server - 协议交互（stdio）

启动方式（stdio MCP server）：

- 启动：`bash scripts/module-rag-mcp --settings config/settings.yaml`
- 调用方式：
- 自动化（推荐）：用 Python/pytest 直接发 JSON-RPC 到子进程 stdin/stdout
- 手工：用最小 JSON-RPC 驱动脚本（后续由 Skills 生成/维护）

### J-01 initialize 协议版本协商

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 发送 JSON-RPC `initialize`，params.protocolVersion=2024-11-05。

预期：

1. result.protocolVersion=2024-11-05。

### J-02 tools/list 工具名合法

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `tools/list`。

预期：

1. tool.name 满足 `^[a-zA-Z0-9_-]+$`（不含点号）。

### J-03 tools/call ping 基线

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `tools/call`：name=`library_ping`，arguments={}。

预期：

1. 返回文本包含 `pong`。

### J-04 tools/call 支持 arguments 为 JSON 字符串

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `tools/call`：name=`library_ping`，arguments=`"{\"message\":\"hi\"}"`。

预期：

1. 返回文本包含 `hi`。

### J-05 default 兼容：ingest/query/assets/delete

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. `library_ingest` 传 `policy=default`、`strategy_config_id=default`。
2. `library_query` 传 `strategy_config_id=default`。
3. `library_query_assets` 传 `variant=default`、`max_bytes=default`。
4. `library_delete_document` 传 `mode=default`。

预期：

1. 不应返回 `-32602 invalid params`。

---

## K. Provider 切换 - DeepSeek LLM

说明：本专项验证“切换配置可装配 + 失败可解释 + 回退可用”。若外网不可用，REAL 用例可先标记 BLOCKED。

启动方式（配置切换）：

- 优先通过 `config/strategies/*.yaml` 或 `config/local.override.yaml` 切换 provider（不改代码）
- 执行链路：
- 只验证装配：跑不依赖 LLM 的 tool（`library_ping` / `tools/list`）
- 验证生成回退：跑 query，并在 LLM 失败时观察 fallback

### K-01 配置切换可装配（不跑外部）

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 使用一份 strategy（或 override）将 llm provider_id 切换为 `deepseek`。
2. 执行一次不依赖 LLM 的调用链（例如 MCP `library_ping` 或 tools/list）。

预期：

1. trace/providers 快照能反映 llm provider_id 切换（若该调用链会记录 providers）。

### K-02 REAL：DeepSeek LLM 生成可回退

Profiles：REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：REAL=TODO，Overall=TODO

步骤：

1. 用 deepseek 作为 llm，执行一次 query。
2. 人为制造 llm 调用失败（invalid key / 断网）。

预期：

1. 系统回退到 extractive 输出（仍返回 citations/sources）。
2. trace 记录 llm_error 与 fallback_used。

---

## L. Provider 切换 - Reranker 模式

启动方式（配置切换）：

- 通过 strategy/override 将 `reranker` 从 `noop` 切到真实 provider（例如 `openai_compatible`）
- 对同一 query 做 A/B：`rerank=off` vs `rerank=on`，对比 Top-K 与 trace 证据

### L-01 baseline：reranker=noop

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 关闭 reranker（noop），执行一次 query。

预期：

1. sources 排序来自 fusion（RRF）或原始候选集。

### L-02 REAL：启用 reranker 改变排序

Profiles：REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：REAL=TODO，Overall=TODO

步骤：

1. 启用 `openai_compatible_llm` reranker。
2. 对同一 query 连续运行：关闭 rerank 与开启 rerank。

预期：

1. Top-K 顺序发生变化。
2. trace 记录 rerank_used=true。

### L-03 REAL：rerank 失败自动降级

Profiles：REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：REAL=TODO，Overall=TODO

步骤：

1. 启用 reranker，但提供错误 key 或让请求失败。

预期：

1. query 仍成功返回（降级为 fusion 结果）。
2. trace 记录 rerank_error。

### L-04 OFFLINE：Cross-Encoder 真实推理（非 mock）

Profiles：OFFLINE

前置系统状态：无

状态：OFFLINE=TODO，REAL=SKIP，Overall=TODO

步骤：

1. 使用 `cross_encoder` provider（例如 `cross-encoder/ms-marco-MiniLM-L-6-v2`）对固定 query 与两条候选执行 rerank。
2. 断言 relevant passage 的排序高于无关 passage。
3. 记录推理结果用于回放。

预期：

1. 用例必须经过真实模型推理，不允许 mock `predict`。
2. 在相同输入下，结果稳定可复现（同分按原 rank 保序）。
3. 若依赖缺失或模型不可用，返回可解释阻断信息。

---

## M. 配置变更与容错

启动方式（配置注入入口）：

- settings：通过 `--settings <path>` 或 `MODULE_RAG_SETTINGS_PATH=<path>` 切换
- strategies：通过 `strategy_config_id` 选择 `config/strategies/*.yaml`
- endpoints/keys：通过 `model_endpoints.local.yaml` 与 `local.override.yaml` 控制（不提交到 git）

### M-01 缺失 model_endpoints 文件的行为

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 临时移除或通过 env 指向不存在的 endpoints 文件。
2. 启动 MCP server 或执行 ingest/query。

预期：

1. OFFLINE：可正常运行（fake/noop 不依赖 key）。
2. REAL：应返回结构化错误（而非崩溃），并给出可定位信息（缺 key/base_url）。

### M-02 provider_id 不存在的错误可定位

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 把某个 kind 的 provider_id 改成不存在值。
2. 执行触发该 kind 的调用链（ingest/query）。

预期：

1. 返回结构化错误，包含 `kind/provider_id`。

### M-03 tool 参数多余字段的容忍边界

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 调用 `library_ping`，附带多余字段（应被允许）。
2. 调用 `library_ingest`，附带多余字段（应被拒绝或明确忽略，口径需固定）。

预期：

1. ping 成功。
2. ingest 的行为可预测（要么报 unexpected field，要么明确忽略并在结构化 warnings 标注）。

---

## N. 数据生命周期闭环

启动方式（建议走 MCP tools，确保契约一致）：

- ingest：`library_ingest` 或 `scripts/dev_ingest.sh`
- delete：`library_delete_document`（soft/hard）
- list：`library_list_documents`（include_deleted）
- query：`library_query` 或 `scripts/dev_query.sh`

### N-01 soft delete 版本后不可被 query 命中

Profiles：OFFLINE/REAL

前置系统状态：至少 `S3_DELETED`

Setup（若当前 < S3）：

1. ingest `tests/fixtures/docs/sample.md`
2. soft delete 该版本

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. ingest 文档并 query 命中。
2. soft delete 对应版本。
3. 再 query 同问题。

预期：

1. sources 不包含 deleted 版本。
2. list_documents include_deleted=true 可看到 deleted 版本。

### N-02 hard delete 的入口与限制

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 通过 MCP tool 尝试 hard delete（mode=hard）。
2. 通过 AdminRunner 直接调用 hard delete（若需要）。

预期：

1. MCP tool 若未开放 hard delete，应明确拒绝（invalid params 或提示未启用）。
2. AdminRunner hard delete 后，fts5/vector/sqlite/fs 的 affected 统计一致。

---

## O. 文档替换与多场景验证

启动方式（数据准备 + 对比验证）：

- 建议固定在一个“可重复的干净 data_dir”里做（避免历史数据污染结论）
- 版本替换：优先用 `policy=new_version`，回归到旧内容用 `policy=skip`

### O-01 A→A1→A 的版本与去重一致性

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可（推荐在干净库执行）

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 准备文档 A（例如 sample.md 的副本），ingest（new_version）。
2. 修改为 A1（追加一行），ingest（new_version）。
3. 改回 A（内容与第一次完全一致），ingest（skip）。

预期：

1. SQLite 中对 A 的 file_sha256 记录可复用，第三次被判 skip。
2. 不会无上限堆积重复版本（在 skip policy 下）。

### O-02 多文档混合召回（避免单文档过拟合）

Profiles：OFFLINE/REAL

前置系统状态：至少 `S2_INGESTED_MULTI`

Setup（若当前 < S2）：

1. ingest `tests/fixtures/docs/sample.md`
2. ingest `tests/fixtures/docs/complex_technical_doc.pdf`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. ingest `sample.md` 与 `complex_technical_doc.pdf`。
2. query 一个跨文档的词（例如 `chunking` 或 `FTS5`）。

预期：

1. sources 可能来自多个 doc_id（若语料覆盖）。
2. trace 能反映 dense/sparse/fusion 的候选来源分布。

---

## P. Trace 与回放稳定性

启动方式（建议同时覆盖 API 与 CLI 触发）：

- ingest：`bash scripts/dev_ingest.sh`
- query：`bash scripts/dev_query.sh`
- traces：`GET /api/traces`、`GET /api/traces/{trace_id}` 或等价 TestClient 调用

### P-01 ingestion trace 的 stage 序列完整且顺序固定

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. ingest `tests/fixtures/docs/sample.md`。
2. 读取最新一条 ingestion trace。
3. 提取 stages 顺序。

预期：

1. stage 顺序固定为 `dedup -> loader -> asset_normalize -> transform_pre -> sectioner -> chunker -> transform_post -> embedding -> upsert`。
2. 每个 stage 都有 `status/start_ts/end_ts` 或等价耗时字段。
3. 不允许缺 stage、重排 stage 或把多阶段合并成单个模糊节点。

### P-02 query trace 的证据链完整

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. query 一个可命中的关键词。
2. 读取对应 query trace。
3. 检查 retrieval、fusion、rerank、response 相关字段。

预期：

1. trace 能看出 dense/sparse 候选、融合结果、rerank 前后差异（若启用 reranker）。
2. 若当前配置为 `reranker=noop`，trace 也要明确反映“未做真实精排”。
3. 结果中的 `trace_id` 能回查到完整明细。

### P-03 相同 query 的 replay_keys 与策略快照稳定

Profiles：OFFLINE

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=SKIP，Overall=TODO

步骤：

1. 在同一 `strategy_config_id` 下，对同一个 query 连续执行两次。
2. 分别读取两条 query trace。
3. 对比 `strategy_config_id/providers_snapshot/replay_keys` 等可回放字段。

预期：

1. 与策略相关的快照字段稳定一致。
2. replay 所需关键字段齐全，不依赖临时内存状态。
3. 同一配置下不应出现“第一条 trace 可解释、第二条 trace 缺字段”的漂移。

### P-04 失败 trace 仍然可诊断

Profiles：OFFLINE/REAL

前置系统状态：无

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 构造一个必然失败的请求（如缺失必填参数、provider_id 不存在、文件路径不存在）。
2. 读取最近失败 trace 或 dashboard 错误返回。
3. 检查错误字段与 stage 归属。

预期：

1. 失败不会吞掉 trace。
2. 错误信息能定位到具体入口或 stage，而不是只有笼统 `500`。
3. trace 中保留足够上下文，支持复盘失败原因。

---

## Q. 稳定性契约（canonical / chunk_id / asset_id）

启动方式（建议优先 OFFLINE，便于重复比对）：

- ingest：`bash scripts/dev_ingest.sh`
- list/get：`library_list_documents`、`library_get_document`
- sqlite 校验：必要时直接读取 `data/sqlite/*.sqlite`

### Q-01 文本 canonical 规范化不影响幂等判断

Profiles：OFFLINE

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=SKIP，Overall=TODO

步骤：

1. 准备两份语义相同、仅空白/换行差异不同的 Markdown 文件。
2. 分别 ingest。
3. 比较去重、版本判定与 chunk 结果。

预期：

1. 规范化规则应避免无意义空白差异导致大面积重复 chunk。
2. 真正内容不变时，系统要尽量复用既有结果或至少保持稳定切分。
3. 若策略明确把这类差异视为新版本，trace 中也应可解释。

### Q-02 chunk_id 对同内容稳定、对内容变化敏感

Profiles：OFFLINE

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=SKIP，Overall=TODO

步骤：

1. ingest 文档 A。
2. 记录其 chunk_id 集合。
3. 重新 ingest 完全相同内容的 A。
4. 再 ingest 修改过局部内容的 A1。

预期：

1. 相同内容下 chunk_id 应稳定可重算。
2. 局部内容变化应只影响相关 chunk，而不是整篇全部漂移。
3. chunk_id 设计应服务于 upsert/回归，而不是每次重新随机生成。

### Q-03 retrieval-only 增强不应污染原始正文层

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/with_images.pdf` 或任一含 enrichable 内容的文档

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. ingest 文档。
2. 获取 chunk 详情或落库内容。
3. 对比原始 `chunk_text` 与 retrieval 增强字段（如 `chunk_retrieval_text` 或等价字段）。

预期：

1. 原始正文层保持可追溯，不被后处理随意改写。
2. 检索增强信息进入 metadata 或 retrieval-only 字段。
3. 面向检索的增强与面向事实保真的正文层边界清晰。

### Q-04 asset_id 在重复 ingest 下稳定复用

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/with_images.pdf`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. ingest 含图片文档。
2. 记录返回或落库中的 `asset_id`。
3. 对同一文件重复 ingest。
4. 再通过 query + `library_query_assets` 回查资产。

预期：

1. 相同资产不应无限生成新的 asset_id。
2. query 命中的资产引用能被 `library_query_assets` 正常解析。
3. 生命周期删除后，资产引用与文件系统状态保持一致。

---

## R. MCP Tool 黑盒闭环

启动方式（只走 stdio / MCP 协议，不走内部 runner）：

- `initialize`
- `tools/list`
- `tools/call`

### R-01 ingest → query → get_document 黑盒闭环

Profiles：OFFLINE/REAL

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 通过 `library_ingest` 摄取 `sample.md`。
2. 通过 `library_query` 命中该文档。
3. 从 query 结果中拿到 `doc_id/version_id`。
4. 调用 `library_get_document` 读取文档详情。

预期：

1. 三个 MCP tools 的字段契约能串起来，不需要调用方猜内部实现。
2. `library_get_document` 返回的版本应与 query 命中的版本一致。
3. 整个链路不依赖 dashboard 私有接口。

### R-02 query_assets 能按 asset_id 返回可用内容

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/with_images.pdf`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. query 一个会命中图片锚点的描述。
2. 从结果中提取 `asset_id`。
3. 调用 `library_query_assets`。

预期：

1. 返回内容包含 `bytes_b64` 或等价可消费字段。
2. 不要求 query 直接内嵌图片本体；资产读取由独立 tool 完成。
3. 非法 `asset_id` 需返回结构化错误。

### R-03 list_documents / delete_document 生命周期闭环

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. `library_list_documents` 查看已有文档。
2. `library_delete_document` 执行 soft delete。
3. 再次 `library_list_documents`，分别测试 `include_deleted=false/true`。

预期：

1. 默认列表不返回 deleted 版本。
2. `include_deleted=true` 可回看历史版本。
3. query 结果不再命中已删除版本。

### R-04 错误请求的协议返回稳定

Profiles：OFFLINE/REAL

前置系统状态：无

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 对 `library_query` 传入非法参数类型。
2. 对 `library_get_document` 缺失 `version_id`。
3. 对不存在的 tool 发起调用。

预期：

1. 错误返回结构稳定，便于 MCP Client 统一处理。
2. 参数错误、业务错误、未知工具错误三类口径清晰。
3. 错误不应污染后续正常会话。

---

## S. 评估数据集与质量门禁

启动方式：

- `bash scripts/dev_eval.sh <dataset_id> <strategy_config_id> <top_k>`
- dashboard `/api/eval/*`

### S-01 retrieval_small 数据集契约完整

Profiles：OFFLINE

前置系统状态：无

状态：OFFLINE=TODO，REAL=SKIP，Overall=TODO

步骤：

1. 读取 `tests/datasets/retrieval_small.yaml`。
2. 校验 case 字段是否完整。
3. 校验每条 case 是否能映射到明确预期文档或命中目标。

预期：

1. 数据集结构稳定，字段缺失会被明确报错。
2. case 设计面向检索质量，而不是混杂生成结果判定。
3. 数据集规模应小而稳定，适合本地频繁回归。

### S-02 rag_eval_small 在最小语料上可复现

Profiles：OFFLINE/REAL

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. 先 ingest 与 `rag_eval_small` 对应的最小语料

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 运行 `rag_eval_small`。
2. 记录评估输出与 trace。
3. 再次运行同一 dataset 与同一 strategy。

预期：

1. OFFLINE 下结果波动应可控。
2. REAL 下即使分数略有浮动，也不应出现结构性失败。
3. 两次运行都能关联到完整 eval 记录。

### S-03 EvalRunner 结果落库完整

Profiles：OFFLINE/REAL

前置系统状态：无

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 运行任一 eval dataset。
2. 查询 `eval_runs` 与 `eval_case_results`。
3. 对照 dashboard `/api/eval/runs` 返回。

预期：

1. run 级、case 级结果都可追溯。
2. 数据库存储与 API 返回一致。
3. 失败 case 不会导致整次 run 静默丢失。

### S-04 质量门禁失败时有明确结论

Profiles：OFFLINE

前置系统状态：至少 `S1_INGESTED_MIN`

Setup：

1. 准备一个刻意劣化的策略配置（如过低 top_k、关闭关键召回链路）

状态：OFFLINE=TODO，REAL=SKIP，Overall=TODO

步骤：

1. 用正常策略跑一次 eval。
2. 用劣化策略再跑一次。
3. 对比关键指标、失败 case 与 traces。

预期：

1. 指标退化能被明确看出来，而不是只输出“跑完了”。
2. 失败 case 可追溯到具体 query / trace。
3. 这类测试能作为策略改动的质量门禁，而不是事后人工感觉。

---

## T. Golden / 回归基线

启动方式（建议固定 data_dir + 固定 strategy_config_id）：

- query：`bash scripts/dev_query.sh`
- eval：`bash scripts/dev_eval.sh`
- traces：dashboard API 或 sqlite 直读

### T-01 query trace 关键字段 shape 不漂移

Profiles：OFFLINE

前置系统状态：至少 `S1_INGESTED_MIN`

Setup（若当前为 S0_EMPTY）：

1. ingest `tests/fixtures/docs/sample.md`

状态：OFFLINE=TODO，REAL=SKIP，Overall=TODO

步骤：

1. 固定 query 与 strategy 跑一次。
2. 保存/比对 trace 关键字段 shape。
3. 与既有基线做回归比对。

预期：

1. stage 名称、关键证据字段、结果结构保持稳定。
2. 若结构变更，必须是显式升级，而不是静默漂移。
3. 这类用例可作为 dashboard / API / MCP 客户端兼容性保护。

### T-02 ingestion trace 关键 stages 不缺失

Profiles：OFFLINE

前置系统状态：`S0_EMPTY` 即可

状态：OFFLINE=TODO，REAL=SKIP，Overall=TODO

步骤：

1. 对固定文档执行 ingest。
2. 比对 ingestion trace 的 stage 集合与基础统计。

预期：

1. `dedup/loader/sectioner/chunker/embedding/upsert` 等关键阶段始终存在。
2. 阶段命名和职责变化需要同步更新基线，不允许悄悄改掉。
3. 用例能快速发现 pipeline contract 漂移。

### T-03 策略切换后的结果可比较

Profiles：OFFLINE/REAL

前置系统状态：至少 `S2_INGESTED_MULTI`

Setup（若当前 < S2）：

1. ingest `tests/fixtures/docs/sample.md`
2. ingest `tests/fixtures/docs/complex_technical_doc.pdf`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 用 `reranker=noop` 跑固定 query。
2. 用启用 reranker 的策略再跑一次。
3. 比较 sources、排序、trace 证据。

预期：

1. 两种策略结果可比较，差异能通过 trace 解释。
2. 若启用真实 reranker，不应破坏原有返回结构。
3. 策略升级应体现在“可解释差异”，而不是“随机变化”。

### T-04 文档替换后 retrieval baseline 不异常回退

Profiles：OFFLINE/REAL

前置系统状态：至少 `S2_INGESTED_MULTI`

Setup（若当前 < S2）：

1. ingest `tests/fixtures/docs/sample.md`
2. ingest `tests/fixtures/docs/complex_technical_doc.pdf`

状态：OFFLINE=TODO，REAL=TODO，Overall=TODO

步骤：

1. 记录一组固定 query 的 baseline 命中情况。
2. 替换其中一份文档为新版本。
3. 重新执行同一组 query。

预期：

1. 与未变更文档相关的 query 不应出现大面积意外回退。
2. 与变更文档相关的差异应主要集中在受影响 query。
3. 这类回归能提前发现 chunking/embedding/upsert 改动带来的副作用。
