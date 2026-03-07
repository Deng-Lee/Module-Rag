---
name: dev-spec-highlights
description: 基于 DEV_SPEC.md（或 dev_spec.md）抽取可落地的项目亮点，并按“大模型开发工程师/Agent 工程方向”的岗位画像输出简历化亮点。适用于用户要求“提炼项目亮点/生成简历话术/按岗位匹配亮点”时。
---

# Dev Spec Highlights

## 概览

从 `DEV_SPEC.md` 中抽取 5–8 个具体可落地的项目亮点，按固定结构写入 `PROJECT_HIGHLIGHTS.md`：亮点标题、技术要点、简历话术方向。强调实现细节，避免名词堆砌。

## 输入与输出

- 输入文件：仓库根目录 `DEV_SPEC.md`（优先）或 `dev_spec.md`。
- 岗位画像：默认使用 `references/role_llm_dev.md`，如用户提供岗位文本则优先采用。
- 输出文件：仓库根目录 `PROJECT_HIGHLIGHTS.md`。

## 流程

1. 定位 `DEV_SPEC.md`（或 `dev_spec.md`）。缺失则停止并向用户索要正确路径。
2. 加载 `references/role_llm_dev.md`。不处理图片输入，岗位画像必须为文本。
3. 解析 `DEV_SPEC.md` 的具体机制，避免抽象标签。每个要点必须锚定到组件、接口或数据流。
4. 按岗位画像聚类为 5–8 个互不重复的亮点主题。
5. 按固定格式写入 `PROJECT_HIGHLIGHTS.md`：亮点标题（1 句）、**技术要点：**（3–6 条）、**简历话术方向：**（2–3 条）。
6. 质量检查并迭代，确保每个亮点具体且不重叠。

## 质量检查

- 每条技术要点必须对应具体机制（pipeline 阶段、provider、IR、schema、trace、tool）。
- 禁止泛化描述（如“提升性能/稳定性”）而不解释实现方式。
- 亮点不重复、范围不重叠。
- 亮点数量保持在 5–8 之间。

## 失败处理

- 找不到 `DEV_SPEC.md`：提示正确路径并停止。
- 亮点过于抽象：改写为具体组件与数据流术语。
- 写入失败：报告路径错误并改用有效位置。

## 反模式

- 名词堆砌、缺少实现锚点。
- 将不相关机制强行合并为一个亮点。
- 多个亮点重复表达同一内容。
- 用未来时或愿景表述冒充已完成成果。

## 示例

输入（摘自 `DEV_SPEC.md`）：

```
系统仅允许通过 IngestionPipeline.run() 触发离线文档摄取流程。
流水线拓扑固定：Loader → Transformer(pre) → Sectioner → Chunker → Transformer(post) → Embedding → Upsert
```

输出（一个亮点示例）：

```
## 亮点：单一入口 + 冻结拓扑的离线摄取流水线
**技术要点：**
1. 仅允许通过 IngestionPipeline.run() 触发离线摄取，确保语义一致与可回放。
2. 流水线拓扑固定：Loader → Transformer(pre) → Sectioner → Chunker → Transformer(post) → Embedding → Upsert。

**简历话术方向：**
1. 设计单一入口、冻结拓扑的摄取流水线，支持策略演进而不改主流程。
```

## 资源

- `references/role_llm_dev.md`：大模型开发工程师岗位画像。
