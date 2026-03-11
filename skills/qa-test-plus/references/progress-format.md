# QA Test Plus 进度回填格式

`QA_TEST_PLUS_PROGRESS.md` 的展示目标不是“记流水账”，而是让人一眼看清：
- 这次跑了什么
- 跑的是哪套 strategy / settings
- 哪些 case 通过、失败、阻塞
- 失败卡在什么环节、哪个模型、是否触发 fallback
- 下一步该怎么继续

## 顶部摘要格式

文件顶部固定保留一段摘要：

```md
# QA Test Plus 执行进度

## 当前摘要

- 用例池总数: <来自 QA_TEST_PLUS.md 的设计规模>
- 当前自动化覆盖: <当前脚本实际覆盖数>
- 最新运行: <run_id 或 none>
- 最近一次执行统计: PASS=<n> | FAIL=<n> | BLOCKED=<n> | TOTAL=<n>
```

当自动化已经覆盖全部 `v1` 用例时，这两个数字可以相同；否则不要混写。

## 单次运行区块格式

每次运行追加一个完整区块：

```md
### Run <run_id>

**执行配置**
- 策略: `<strategy_config_id>`
- settings: `<path>`
- 结果文件: `<result_json>`

**执行总览**
- 自动化执行用例数: <n>
- PASS=<n> | FAIL=<n> | BLOCKED=<n> | TOTAL=<n>

**用例结果**
| 用例ID | 标题 | 状态 | 执行入口 | 关键证据 | 失败链路 |
|---|---|---|---|---|---|
| B-01 | 摄取 simple.pdf | PASS | CLI 摄取 | file=simple.pdf; trace_id=...; doc_id=... | - |
| D-01 | 运行 rag_eval_small | FAIL | CLI 评估 | run_id=...; metric_keys=... | eval / evaluator::qwen-turbo / 429 quota exceeded |

**Profile 对比**
- 参与策略: local.default, local.production_like
- 首个失败策略: <若无则写 none>
- 指标差异: {"hit_rate@k": 0.1, "mrr": -0.03}

**失败诊断**
- D-01: 阶段=eval, 位置=..., 模型=..., fallback=...
- I-01: 阶段=config_load, 位置=..., 模型=..., fallback=...

**下一步**
- 若全绿: 可继续扩展 `v2` 新用例或追加新的 REAL profile
- 若有失败: 列出 1-3 条最直接的修复动作
```

## 关键证据字段建议

优先展示这些字段：
- `file`
- `query`
- `trace_id`
- `run_id`
- `doc_id`
- `deleted_doc_id`
- `top_chunk_id`

不要把整段 JSON 直接塞进表格；表格只放高信息密度的证据。

## 失败链路格式

失败链路统一压缩为一行：

```text
<stage> / <provider_model> / <raw_error>
```

示例：
- `preflight_dns / embedder::openai_compatible::text-embedding-v3 / gaierror: nodename nor servname provided`
- `eval / evaluator::qwen-turbo / 429 insufficient_quota`
- `query / reranker::openai_compatible_llm::qwen-turbo / rerank request timeout`

## 中文展示要求

- 标题、区块名、表头、总结语全部使用中文
- 保留 `run_id / trace_id / strategy_config_id / provider_model` 这类技术字段的英文标识
- 不要混用中英文标题，例如不要写 `Run Summary`、`Compare summary`
