---
name: qa-baseline
description: Run MODULE-RAG QA baseline (OFFLINE + REAL) from QA_TEST.md, using clean data dirs and writing QA_TEST_PROGRESS.md with evidence and next steps.
---

# QA Baseline Runner (OFFLINE + REAL)

## Purpose

- 将 `/Users/lee/Documents/AI/MODULE-RAG/QA_TEST.md` 固化为一次可重复执行的回归流程（支持 baseline smoke 与 A..O 全量）。
- 产出 `QA_TEST_PROGRESS.md`：记录“做了什么、结果是什么、下一步是什么”，并附带证据（trace_id、关键计数）。
- 判定口径：
  - `OFFLINE` 可在无外网环境稳定回归；
  - `REAL` 需要外网 + 密钥/endpoint；若环境不可用必须标记 `BLOCKED(env:network)`，不能误判为系统失败。
  - `REAL` 的“外网可达”通常只在**本机 Terminal**成立；在受限沙箱里跑 REAL 很可能被判 `BLOCKED(env:network)`。

## Trigger

当用户提出以下需求时触发：

- “跑一遍 QA baseline（offline + real）并回填进度”
- “根据 QA_TEST.md 执行并生成 QA_TEST_PROGRESS.md”
- “把 QA_TEST.md 的 A..O 用例逐条执行并回填”
- “用干净库跑回归（每次生成独立 data_dir）”

## Inputs

- `QA_TEST.md`（用例与口径；本 Skill 按默认 baseline 路径执行，不解析全文做全覆盖）
- `config/model_endpoints.local.yaml`（REAL 需要；OFFLINE 不需要）
- `config/strategies/local.test.yaml`（OFFLINE）
- `config/strategies/local.default.yaml`（REAL）

## Outputs

- `QA_TEST_PROGRESS.md`
  - 每个用例除了 PASS/FAIL/BLOCKED 之外，还必须记录：
  - 该用例在做什么（来自 QA_TEST.md 的“步骤”摘要）
  - 该用例的预期结果（来自 QA_TEST.md 的“预期”摘要）
  - 本次执行结果（OFFLINE/REAL 各自 status + trace_id + error；以及 Overall）
- `config/settings.qa.<run_id>.offline.yaml`（本地生成，.gitignore 已忽略）
- `config/settings.qa.<run_id>.real.yaml`（本地生成，.gitignore 已忽略）
- `data/qa_runs/<run_id>/{offline,real}/...`（干净库）

## Steps

### 0) Choose Execution Context (important)

本 Skill 有两种可执行形态，**不要混用口径**：

- 形态 A（推荐：本机 Terminal 全量回归）：
  - 同一台机器里把 `OFFLINE + REAL` 一次跑完，得到真正的 `Overall=PASS/FAIL` 判定。
- 形态 B（Codex/沙箱内做 OFFLINE 回归 + 本机补 REAL）：
  - 沙箱里只跑 `OFFLINE`（用于快速回归）。
  - `REAL` 必须在本机 Terminal 补跑；否则会长期显示 `BLOCKED(env:network)` 或 `REAL=N/A`。
  - 注意：分两次跑会在 `QA_TEST_PROGRESS.md` 产生两个 Run block（同一 run_id 需要手工对照/合并口径）。

### 1) Choose Run Id

- 生成 `run_id`（例如 `YYYYMMDD_HHMMSS`），用于隔离本次产物路径。

### 2) Create Clean Settings (offline + real)

- 生成两份 settings 文件（不要覆盖已有）：
- OFFLINE：默认 `strategy_config_id=local.test`
- REAL：默认 `strategy_config_id=local.default`
- 两者的 paths 指向 `data/qa_runs/<run_id>/{offline,real}`，避免污染历史数据。

### 3) Run OFFLINE Baseline (must pass)

按如下最小闭环执行并断言：

- Ingest：`tests/fixtures/docs/sample.md`（`policy=new_version`）
- Assert：`status=ok` 且 `chunks_written>0` 且 `dense_written>0` 且 `sparse_written>=0`
- Query：`"FTS5"`（`top_k=5`）
- Assert：返回 `sources` 非空（至少 1 个 chunk_id）
- Dashboard API（方案B：API-only）
- Assert：
- `GET /api/overview` 200 且 keys 包含 `assets/health/providers`
- `GET /api/documents` 200 且 items 数 >= 1
- `GET /api/traces?trace_type=ingestion` 200 且 items 数 >= 1
- `GET /api/traces?trace_type=query` 200 且 items 数 >= 1

### 4) Run REAL Baseline (best-effort; may be BLOCKED(env))

执行同一闭环，但增加环境前置检查：

- Preflight DNS：对 `base_url` 的 host 做解析（例如 `dashscope.aliyuncs.com`）
- Preflight HTTP（可选）：对 embeddings endpoint 发一次最小请求（若密钥存在）

若 REAL 运行失败：

- 若错误包含 DNS/网络不可达（典型：`[Errno 8] nodename nor servname provided`），标记 `BLOCKED(env:network)`，并在“下一步”给出恢复建议（本机 Terminal 执行）。
- 若返回 4xx/5xx 且能连接到服务（如 401/403/400），标记 `FAIL(system or config)`，并记录 provider/model/endpoint_key 与错误码。

### 5) Write QA_TEST_PROGRESS.md

按固定模板追加一个 Run block：

- 本次做了什么（命令/入口/策略/干净库路径）
- 结果是什么（OFFLINE/REAL 分开写，含 PASS/FAIL/BLOCKED 与 trace_id/关键计数）
- 下一步是什么（对 FAIL/BLOCKED 给出可执行动作）

## Failure Handling

- 任何阶段失败都必须：
- 保留 trace_id（若有）
- 记录关键计数（chunks_written、dense_written、sparse_written）
- 给出下一步的“可执行命令”

失败类型口径（写入 `QA_TEST_PROGRESS.md`）：

- `BLOCKED(env:network)`：环境网络/DNS 限制导致无法访问外部模型（常见于受限沙箱）。
- `FAIL(system)`：本机网络可达但系统逻辑错误（如 chunk=0、查询空召回、入库失败、接口 5xx）。
- `FAIL(config)`：网络可达但配置错误（endpoint_key/model/api_key 不匹配导致 4xx）。

## Anti-patterns

- 只跑 REAL 或只跑 OFFLINE 就标记整体 PASS（必须分别记录）。
- REAL 在受限环境失败就判定系统失败（应标记 `BLOCKED(env)`）。
- 不做“干净库”隔离导致历史数据污染结论。
- 只写“失败了”不写证据与下一步命令。

## Examples

在仓库根目录执行（本机 Terminal，推荐，一次跑完 OFFLINE+REAL）：

```bash
PYTHONPATH=. .venv/bin/python skills/qa-baseline/scripts/run_baseline.py --suite all --profiles offline,real
```

执行 QA_TEST.md A..O 全量（逐条执行并回填）：

```bash
PYTHONPATH=. .venv/bin/python skills/qa-baseline/scripts/run_baseline.py --suite all --profiles offline,real
```

只跑 OFFLINE（用于快速回归）：

```bash
PYTHONPATH=. .venv/bin/python skills/qa-baseline/scripts/run_baseline.py --profiles offline
```

只跑 REAL（用于“本机补跑 REAL”，例如沙箱里先跑过 OFFLINE 了）：

```bash
PYTHONPATH=. .venv/bin/python skills/qa-baseline/scripts/run_baseline.py --suite all --profiles real
```

指定 run_id（便于复现与对比）：

```bash
PYTHONPATH=. .venv/bin/python skills/qa-baseline/scripts/run_baseline.py --run-id 20260303_181055
```
