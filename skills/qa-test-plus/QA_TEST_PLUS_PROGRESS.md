# QA Test Plus 执行进度

## 当前摘要

- 用例池总数: 100
- 当前自动化覆盖: 100
- 最新运行: 20260312_105812 (正式全量回归中止)
- 最近一次执行统计: PASS=2 | FAIL=0 | BLOCKED=0 | TOTAL=2 (D-10/J-07 重跑)

## 运行记录

### Run 20260312_105812

**执行配置**
- 策略: `local.production_like`
- settings: `config/settings.qa.plus.20260312_105812.main.yaml`
- 结果文件: `未生成（正式全量回归在 evaluator 长尾阶段中止）`

**执行总览**
- 自动化执行用例数: 未完成
- PASS=未汇总 | FAIL=未汇总 | BLOCKED=未汇总 | TOTAL=100

**已确认产物**
- 隔离 run 目录: `data/qa_plus_runs/20260312_105812`
- 已完成阶段目录: `main`, `ingest-isolated`, `ingest-failure`, `query-failure`, `strategies`
- 运行时已进入 `ragas` evaluator 阶段，stdout 多次出现 `LLM returned 1 generations instead of requested 3`

**失败诊断**
- 阶段: `eval / compare / deepseek` 长尾
- 位置: `skills/qa-test-plus/scripts/run_real_suite.py`
- 模型: `evaluator::ragas::qwen3.5-plus` 与 `evaluator::ragas::deepseek-chat`
- fallback: 无明确 fallback；主要现象是远端评估长时间运行，导致正式全量 run 无法在合理时间内收尾

**下一步**
- 按增量回填规则，不再整套重跑已确认成功的项
- 仅重跑仍阻塞的 evaluator 长尾 case，优先 `D/J` 相关

### Retry 20260312_103815_d10j07_retry

**重跑范围**
- 来源运行: `20260312_105812`
- 仅重跑用例: `D-10`, `J-07`

**重跑结果**
| Status | ID | Title | Note |
|---|---|---|---|
| PASS | D-10 | 使用 ragas evaluator 进行 CLI 评估 | prev=FAIL; run_id=464b9686-fef5-4aac-98e2-fb5cb025a161; metric_keys=ragas.faithfulness, ragas.answer_relevancy; case_count=1 |
| PASS | J-07 | Ragas / Judge 使用 DeepSeek | prev=FAIL; run_id=4c1e788c-52e9-4e73-a434-bac646ae1ceb; model=deepseek-chat; trace_id=trace_9271af9c04f144539bd8c1bc325dd6a7 |

**重跑详情**
- 结果文件: `/Users/lee/Documents/AI/MODULE-RAG/data/qa_plus_runs/20260312_103815_d10j07_retry/results/d10_j07_results.json`
- D-10 metrics: `ragas.faithfulness=0.0`, `ragas.answer_relevancy=0.0`
- J-07 metrics: `ragas.faithfulness=1.0`, `ragas.answer_relevancy=0.8404272846295092`
- 两条 stderr 均仍出现 `LLM returned 1 generations instead of requested 3`，但不再阻断执行

**结论**
- 仍失败的 case: `none`（本次仅重跑 `D-10/J-07`）
- 下一轮默认仅继续重跑正式全量 run 中尚未正式回填的剩余项
