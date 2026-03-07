# 项目亮点（基于 DEV_SPEC）

## 亮点 1：单一入口 + 冻结拓扑的离线摄取流水线
**技术要点：**
1. 仅允许通过 `IngestionPipeline.run()` 触发离线摄取，确保语义一致与可回放。
2. 流水线拓扑固定：`Loader → Transformer(pre) → Sectioner → Chunker → Transformer(post) → Embedding → Upsert`。
3. 阶段实现通过 Provider 注册与配置选择，不改变拓扑即可替换策略。
4. 摄取前进行 `sha256` 边写盘哈希与去重，支持 `skip/new_version` 版本策略。
5. 统一 `on_progress` 回调与阶段级观测点，避免入口侧分叉。

**简历话术方向：**
1. 设计单一入口、冻结拓扑的 Ingestion Pipeline，通过配置替换阶段实现，支持策略演进而不改主流程。
2. 落地文件级去重与版本控制（`sha256` 边写盘计算），降低重复解析与索引成本。

## 亮点 2：结构化 QueryIR + 分层检索链路
**技术要点：**
1. Query 预处理产出结构化 `QueryIR`，与 MCP 路由解耦，便于回放与版本化。
2. 检索链路分层：Dense/Sparse 并行召回 → RRF 融合 → 可选 Rerank → 生成。
3. 过滤规则分层（Pre/Post/Rerank）保证“可执行字段”优先，软偏好只调权不裁剪。
4. 失败回退路径清晰：`Rerank > Fusion > Dense-only > Sparse-only`。

**简历话术方向：**
1. 实现 QueryIR 驱动的检索编排，支持混合召回、融合与可选精排，并定义稳定回退策略。
2. 将过滤与排序责任分层（Pre/Post/Rerank），提升检索稳定性与可解释性。

## 亮点 3：MCP Tool 化接口与传输层无感扩展
**技术要点：**
1. 所有能力以 MCP Tool 统一暴露，输入输出 schema 固化为对外契约。
2. 默认 stdio + 预留 Streamable HTTP，保持协议语义一致、执行层无感。
3. MCP 只负责编排与路由，Query 解析与检索策略留在内部执行层。
4. Tool 返回统一携带 `trace_id`，作为跨层可观测锚点。

**简历话术方向：**
1. 将 RAG 能力封装为 MCP Tool 契约，保证多客户端无痛接入与稳定接口升级。
2. 实现传输层无感设计（stdio/HTTP），避免部署形态变化引入执行层重写。

## 亮点 4：Trace-First 可观测与回放体系
**技术要点：**
1. 统一 `IngestionTrace`/`QueryTrace` 骨架：Header/Spans/Events/Aggregates。
2. 关键观测点产出指针与摘要（`doc_id/chunk_id/asset_id/score`），避免复制事实层。
3. 以 `trace_id/job_id` 贯穿全链路，实现可回放与诊断。
4. Dashboard 基于稳定 `span.name/event.kind` 动态渲染，无需随策略变更改代码。

**简历话术方向：**
1. 构建 Trace-First 观测体系，摄取与查询全链路可回放、可诊断。
2. 将观测作为 sidecar 能力接入，最小侵入保障策略快速迭代。

## 亮点 5：多模态资产链路与引用可溯源
**技术要点：**
1. 解析阶段定位图片资产但不在 Loader 内处理，保持职责边界清晰。
2. 资产归一化器统一提取、去重与引用替换，输出稳定 `asset_id`。
3. OCR/Caption 作为扩展能力注入后处理阶段，预留多模态检索路径。
4. MCP 侧提供 `query_assets` 工具，支持客户端按需拉取资源。

**简历话术方向：**
1. 设计资产归一化与 `asset_id` 引用机制，保障多模态内容可溯源可复用。
2. 多模态能力以扩展点形式接入，不破坏核心解析与检索链路。

## 亮点 6：IR-First + Provider Registry 的可插拔架构
**技术要点：**
1. 统一 IR（`SectionIR/ChunkIR/QueryIR`）作为跨层稳定契约。
2. `ProviderRegistry -> Factory -> Provider` 分层实现策略替换与依赖注入。
3. Noop Provider 表达可选能力（如 `reranker.noop`），避免拓扑分叉。
4. 新 Provider 通过配置切换（如 `openai_compatible` 适配层），避免改主流程。

**简历话术方向：**
1. 以 IR-First 契约驱动模块解耦，Provider Registry 实现策略插拔与配置化切换。
2. 通过 Noop Provider 处理可选能力，保证主流程稳定与可测试性。

## 亮点 7：评估体系与策略对比闭环
**技术要点：**
1. 评估复用线上 Query 路径，旁路捕获 artifacts 与指标。
2. Dataset/Judge Provider 统一评估数据与打分接口（LLM-as-judge / rule-based）。
3. 指标覆盖检索与生成（HitRate@K/MRR/nDCG 等），支持策略对比。

**简历话术方向：**
1. 构建可复用评估链路，复用线上 Query 并输出可对比指标。
2. 评估数据集与裁判接口模块化，支持策略 A/B 与回归对比。
