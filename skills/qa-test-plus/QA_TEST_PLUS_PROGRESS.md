# QA Test Plus 执行进度

## 当前摘要

- 用例池总数: 100
- 当前自动化覆盖: 100
- 最新运行: 20260318_154204 (正式全量回归中止)
- 最近一次执行统计: PASS=0 | FAIL=1 | BLOCKED=0 | TOTAL=100 (正式全量回归未完成)

## 运行记录

### Run 20260318_154204

**执行配置**
- 策略: `local.production_like`
- settings: `config/settings.qa.plus.20260318_154204.main.yaml`
- 结果文件: `未生成（正式全量回归在外部 provider HTTPS 读等待中中止）`

**执行总览**
- 自动化执行用例数: 未完成
- PASS=未汇总 | FAIL=未汇总 | BLOCKED=未汇总 | TOTAL=100

**用例结果**
| Status | ID | Title | Note |
|---|---|---|---|
| FAIL | D/J-长尾 | 全量 REAL 回归尾段 | entry=正式全量回归; run_root=data/qa_plus_runs/20260318_154204; stage=eval_or_provider_io; location=_ssl__SSLSocket_read/poll; provider_model=evaluator_or_provider_https; raw_error=外部 HTTPS 读等待长时间无返回 |

**失败诊断**
- 阶段: `eval_or_provider_io`
- 位置: `外部 provider HTTPS 读等待（sample 显示主线程阻塞在 _ssl__SSLSocket_read -> poll）`
- 模型: 尚未收敛到单一 provider；从 run 目录看已完成 `main / ingest-isolated / ingest-failure / query-failure / strategies`，但未推进到后续评估/compare 产物
- fallback: 无；进程在外部读等待中停滞，run 目录时间戳停止推进
- 伴随预期故障注入噪音: `http://127.0.0.1:9/v1/embeddings` 的 `Connection refused`

**下一步**
- 不再重跑整套
- 继续把阻塞调用精确缩到具体 case / provider，再对相应入口加超时与失败回填

### Run 20260313_203643

**执行配置**
- 策略: `local.production_like`
- settings: `config/settings.qa.plus.20260313_203643.main.yaml`
- 结果文件: `未生成（正式全量回归在 ragas 超时后悬挂中止）`

**执行总览**
- 自动化执行用例数: 未完成
- PASS=未汇总 | FAIL=未汇总 | BLOCKED=未汇总 | TOTAL=100

**用例结果**
| Status | ID | Title | Note |
|---|---|---|---|
| FAIL | D/J-长尾 | 全量 REAL 回归尾段 | entry=正式全量回归; run_root=data/qa_plus_runs/20260313_203643; stage=eval; location=ragas.executor + _ssl__SSLSocket_read/poll; provider_model=evaluator::ragas::qwen3.5-plus/deepseek-chat; raw_error=InstructorRetryException(Request timed out.) 连续 3 次后主进程未退出 |

**失败诊断**
- 阶段: `eval`
- 位置: `ragas.executor` 先抛 `InstructorRetryException(Request timed out.)`，随后主线程 sample 仍显示阻塞在 `_ssl__SSLSocket_read -> poll`
- 模型: `evaluator::ragas::qwen3.5-plus` 与 `evaluator::ragas::deepseek-chat`
- fallback: 无；run 目录只推进到 `main / ingest-isolated / ingest-failure / query-failure / strategies`，未生成 `eval-* / compare-* / results`
- 伴随预期故障注入噪音: `http://127.0.0.1:9/v1/embeddings` 的 `Connection refused`

**下一步**
- 不再整套重跑
- 只围绕 `D/J` 的 ragas 长尾做专项修复，重点处理“评估超时后主流程未退出”的收尾逻辑

### Run 20260313_201510

**执行配置**
- 策略: `local.production_like`
- settings: `config/settings.qa.plus.20260313_201510.main.yaml`
- 结果文件: `未生成（正式全量回归在外部 provider HTTPS 读等待中中止）`

**执行总览**
- 自动化执行用例数: 未完成
- PASS=未汇总 | FAIL=未汇总 | BLOCKED=未汇总 | TOTAL=100

**用例结果**
| Status | ID | Title | Note |
|---|---|---|---|
| FAIL | D/J-长尾 | 全量 REAL 回归尾段 | entry=正式全量回归; run_root=data/qa_plus_runs/20260313_201510; stage=eval_or_provider_io; location=_ssl__SSLSocket_read/poll; provider_model=evaluator_or_provider_https; raw_error=外部 HTTPS 读等待长时间无返回 |

**失败诊断**
- 阶段: `eval_or_provider_io`
- 位置: `外部 provider HTTPS 读等待（sample 显示主线程阻塞在 _ssl__SSLSocket_read -> poll）`
- 模型: 尚未收敛到单一 provider；从 run 目录看已完成 `main / ingest-isolated / ingest-failure / query-failure / strategies`，但未推进到后续评估/compare 产物
- fallback: 无；进程在外部读等待中停滞，run 目录时间戳停止推进
- 伴随预期故障注入噪音: `http://127.0.0.1:9/v1/embeddings` 的 `Connection refused`

**下一步**
- 不再重跑整套
- 先把阻塞调用精确缩到具体 case / provider，再对相应入口加超时与失败回填


### Run 20260313_172130

**执行配置**
- 策略: `local.production_like`
- settings: `config/settings.qa.plus.20260313_172130.main.yaml`
- 结果文件: `未生成（正式全量回归在外部 provider HTTPS 读等待中中止）`

**执行总览**
- 自动化执行用例数: 未完成
- PASS=未汇总 | FAIL=未汇总 | BLOCKED=未汇总 | TOTAL=100

**用例结果**
| Status | ID | Title | Note |
|---|---|---|---|
| FAIL | D/J-长尾 | 全量 REAL 回归尾段 | entry=正式全量回归; run_root=data/qa_plus_runs/20260313_172130; stage=eval; location=_ssl__SSLSocket_read/poll; provider_model=evaluator::ragas::qwen3.5-plus/deepseek-chat; raw_error=外部 HTTPS 读等待长时间无返回 |

**失败诊断**
- 阶段: `eval`
- 位置: `外部 provider HTTPS 读等待（sample 显示主线程阻塞在 _ssl__SSLSocket_read -> poll）`
- 模型: `evaluator::ragas::qwen3.5-plus` 与 `evaluator::ragas::deepseek-chat`
- fallback: 无；进程未继续产生产物，run 目录停止在 `main / ingest-isolated / ingest-failure / query-failure / strategies`
- 伴随预期故障注入噪音: `http://127.0.0.1:9/v1/embeddings` 的 `Connection refused`

**下一步**
- 不再重跑整套已走过的前半段
- 仅围绕 `D/J` 相关 evaluator/provider 长尾做专项重跑或进一步缩减外部评估上下文


### Run 20260313_170959

**执行配置**
- 策略: `local.production_like`
- settings: `config/settings.qa.plus.20260313_170959.main.yaml`
- 结果文件: `未生成（正式全量回归在外部 provider HTTPS 读等待中中止）`

**执行总览**
- 自动化执行用例数: 未完成
- PASS=未汇总 | FAIL=未汇总 | BLOCKED=未汇总 | TOTAL=100

**用例结果**
| Status | ID | Title | Note |
|---|---|---|---|
| FAIL | D/J-长尾 | 全量 REAL 回归尾段 | entry=正式全量回归; run_root=data/qa_plus_runs/20260313_170959; stage=eval; location=_ssl__SSLSocket_read/poll; provider_model=evaluator::ragas::qwen3.5-plus/deepseek-chat; raw_error=外部 HTTPS 读等待长时间无返回 |

**失败诊断**
- 阶段: `eval`
- 位置: `外部 provider HTTPS 读等待（sample 显示主线程阻塞在 _ssl__SSLSocket_read -> poll）`
- 模型: `evaluator::ragas::qwen3.5-plus` 与 `evaluator::ragas::deepseek-chat`
- fallback: 无；进程未继续产生产物，run 目录停止在 `main / ingest-isolated / ingest-failure / query-failure / strategies`
- 伴随预期故障注入噪音: `http://127.0.0.1:9/v1/embeddings` 的 `Connection refused`

**下一步**
- 不再重跑整套已走过的前半段
- 仅围绕 `D/J` 相关 evaluator/provider 长尾做专项重跑或进一步缩减外部评估上下文


### Run 20260312_155947

**执行配置**
- 策略: `local.production_like`
- settings: `config/settings.qa.plus.20260312_155947.main.yaml`
- 结果文件: `未生成（正式全量回归在 ragas evaluator 超时后中止）`

**执行总览**
- 自动化执行用例数: 未完成
- PASS=未汇总 | FAIL=未汇总 | BLOCKED=未汇总 | TOTAL=100

**用例结果**
| Status | ID | Title | Note |
|---|---|---|---|
| FAIL | D/J-长尾 | 全量 REAL 回归尾段 | entry=正式全量回归; run_root=data/qa_plus_runs/20260312_155947; stage=eval; provider_model=evaluator::ragas::qwen3.5-plus/deepseek-chat; raw_error=APITimeoutError(Request timed out.) |

**失败诊断**
- 阶段: `eval`
- 位置: `ragas.executor`
- 模型: `evaluator::ragas::qwen3.5-plus` 与 `evaluator::ragas::deepseek-chat`
- fallback: 无；主现象是 `LLM returned 1 generations instead of requested 3` 后进入 `APITimeoutError(Request timed out.)`
- 伴随环境噪音: Qwen embedding 还出现过 `Connection reset by peer`

**下一步**
- 不再重跑整套已走过的前半段
- 只围绕 `D/J` 相关 evaluator 长尾做专项重跑或继续收敛 provider 超时参数


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
