# 模拟面试报告

**项目**：Modular RAG MCP Server  
**面试时间**：2026-03-18 21:24:06  
**面试风格**：FAST（速攻广度型）  
**掷骰结果**：4  
**评分**：6.8/10

---

## 一、面试记录

> 以下问题与回答均按本场面试实际原文记录。

### 方向 1：项目综述

| 题号 | 问题（原文） | 候选人回答（原文，不摘要） | 评估 | 参考答案 |
|-----|-------------|---------------------------|------|---------|
| Q1 | 这个系统里有哪几类存储？它们各自负责什么？为什么不能只用一个存储？ | 存储一共是分成三路，第一路就是本地文件系统存储，它其实就是原文件，然后就是这种事实存的东西，然后就是 loader 处理之后的那种 Markdown 文件，然后还有那种图片会把它作为资产存储起来。然后另外一层是 SQLite，它其实存储的是那种，比如说会有一些切分之后的 chunk，然后还会有一些就比如说会对那个 chunk 去进行一个 summary，或者对它进行关键词的抽取，包括因为那种 OCR 和 caption 是可选的。它也可以去对那个图片去进行一个处理，因为这些都是属于增强信息，它其实也是放在那个 circle light 里面。还有一路就是 Chrome Chroma，其实就是保存那个 embedding 之后的那种文本。他们是不可以用一个存储的，因为他们的那个文件的形式都是不一样的，你就比如说 embedding 的文件，它是经过向量化的，这是把一个文本转成那种向量的形式，这个是没有办法放在本地或者用 SQLite进行处理的。 | ⚠️ | [→ 查看](#a-项目存储) |

### 方向 2：简历深挖

| 题号 | 问题（原文） | 候选人回答（原文，不摘要） | 评估 | 露馅 | 参考答案 |
|-----|-------------|---------------------------|------|-----|---------|
| Q2 | 你简历里写了“多渠道信息增强”和“将元数据注入到 chunk 的 metadata 中”，还提到可以对每个 chunk 用 LLM 生成 summary 或关键词。那我具体问一下：这些增强信息最后是写到哪些字段里的？`transform_post` 这一层在你们链路里到底承担什么职责？ | 就比如说对于图片你可以对它进行 OCR 和 caption，那如果 OCR 的话你就会产生 OCR text，然后 caption 你也会有 caption text，然后如果是开启了那个文本的那个大语言模型的一个关键词提取，或者说 summary 的话。那它也会有 keywords 和 summary 这样的一些字段，那就还包括一些文本和结构方面的东西，就比如说 section_path，还有 tag 之类的东西，都是放在这个增强信息里面的。那所以说这个 Transformer post 它起到的作用其实就是把这些增强信息，嗯，和那个塞到那个 metadata 里面，和那个，但它并不污染正文，它并不是直接和那个正文拼接到一起的，然后这是它做的第一个事情，就是用作增强，然后做的第。然后做的第二个事情就是说把那个，因为我们会有图片，我们那个图片会把它的那个每个图片会有，每就相当于一个资产，每个资产会有一个 asset ID，然后把这个 asset ID 也存储到那个 chunk 对应的 metadata上面。就说我这个 chunk，哎，有这个 asset，然后会把这个 chunk 就是文章哪个地方应用了这个，引用了这个资产，把那个anchor也存到这个meatadata里面去，会把这些东西都存去，所以就是transform-post起到的作用。第一个是对那个文本进行一个增强，另外一个是对那个资产进行一个映射。 | ✅ | 否 | [→ 查看](#a-transform-post) |

### 方向 3：技术深挖

| 题号 | 问题（原文） | 候选人回答（原文，不摘要） | 评估 | 参考答案 |
|-----|-------------|---------------------------|------|---------|
| Q3 | 你简历里写你们做了 100+ REAL case 的 QA 回归，而且是 skill 驱动。那我问得具体一点：你们这套 QA 是怎么分层的？为什么不用一套测试把所有事情都测完？ | 就是在完成模块的时候，因为我们是一个模块的完成的，然后在完成模块的时候，我们就进行了针对每一个模块有模块级的验证，然后在完成了若干个模块形成一个链路，比如说 query 链路，ingest 的链路的时候。我们也有那种链路级的测试，然后到最后完成之后也做了端到端的测试，然后是这个所有的测试都完成之后，我们是用了100多个 Real case，但这个 real case 它测的就不太一样，就是首先我们是跑了一些 CLI，因为就是通过 CLI 去看看那个。interest 还有 query，这还有包括评估这些链路是不是正常的，然后就还做了一些，比如说故意给输入注入一些故障，或者说给模型注入一些故障，看这个系统是不是反应是不是符合预期的，然后说我们也做了一些 profile 的一些对比。还有那个大语言模型，你选择不同的模型去产生对最后结果的一个影响，就包括说还有一些，就是一些对比实验，没为什么没有用统一的一个测试去做，其实是因为你就比如说像刚刚提到的那些那100多个 real case。它在整个阶段中它的那个状态是不一样的，就是他不是一个可以用，就是一个头一下走到尾的，他是存在很多中间状态的，所以我们就写了一些脚本，然后让他直接从一个状态到另一个状态，这样单独去测某些状态。 | ✅ | [→ 查看](#a-测试体系) |
| Q4 | 如果项目中某个 LLM Provider 挂了，系统会怎么表现？你们做了哪些降级或 fallback 设计？ | 大语言模型的 provider挂了的话，我们按照优先级提供了其他的一些大语言模型的提供商，所以一个不行的话他会去按照优先级去使用另外的，那然后如果按照链路上来讲，比如说embedding 的模型坏了的话，那它会直接使用sparse-only的模式，rerank 的过程坏了的话，那就直接返回 rff 排序的结果。然后就比如说 OCR 之类的失败了的话，就直接基于事实文本进行操作 | ⚠️ | [→ 查看](#a-provider-fallback) |

---

## 二、参考答案

### <a id="a-项目存储"></a>Q1 参考答案：系统里有哪些存储，为什么不能只用一个？

当前系统至少有四类存储层：

1. **本地文件系统**
   - `data/raw`：原始文件
   - `data/md`：规范化 Markdown
   - `data/assets`：图片等资产文件
2. **`app.sqlite`**
   - 文档、版本、chunk 元数据、asset 映射、评估结果等主数据
3. **`fts.sqlite`**
   - FTS5 / BM25 稀疏检索文本
4. **`chroma_lite.sqlite` / Chroma**
   - Dense embedding 向量与对应 metadata

不能只用一个存储的原因不是“格式不同”这么简单，而是**检索模式、索引结构、访问路径和生命周期管理都不同**：文件系统适合持久化原文与资产，SQLite 适合事务型元数据与本地索引，向量库存的是 embedding 空间和 ANN 检索结构。把它们强行并到一个存储，会让查询性能、幂等 upsert、删除一致性和可观测性都变差。

### <a id="a-transform-post"></a>Q2 参考答案：`transform_post` 的职责是什么？

`transform_post` 不是简单“往 metadata 里塞点东西”，它承担两件关键职责：

1. **生成检索增强信息**
   - 例如：`keywords`、`summary`、`caption_text`、OCR 结果、`enrich_keys`
   - 这些增强结果会进入 chunk metadata，部分还会参与构造 `chunk_retrieval_text`
2. **组织资产引用链路**
   - 把 `asset_id`、anchor、section/path 等信息挂到 chunk 上，形成 chunk 与图片资产的映射关系

关键边界是：
- **不直接污染 `chunk.text` 正文**
- 而是通过 metadata / retrieval view / sidecar enrichment 提供增强能力

### <a id="a-测试体系"></a>Q3 参考答案：为什么 QA 要分层？

这套 QA 的合理分层应至少包括：

1. **模块级验证**
   - 单个 provider / 单个 stage / 单个 API 的行为
2. **链路级验证**
   - 如 ingest 链路、query 链路、eval 链路
3. **端到端验证**
   - CLI / MCP / Dashboard consistency / compare / lifecycle / 故障注入
4. **REAL case 回归**
   - 使用真实文档、真实 provider、真实策略组合做长链路回归

不能只用一套测试把所有事情测完，因为：
- 不同问题发生在不同抽象层
- 全量 E2E 成本高、定位慢、对外部依赖敏感
- 很多测试需要人为构造中间状态、故障注入或隔离 settings

所以项目里才会同时保留 unit / integration / e2e / skill-driven REAL regression。

### <a id="a-provider-fallback"></a>Q4 参考答案：Provider 挂了时怎么降级？

这题的关键不是“换一个 provider”这么简单，而是要区分**链路不同阶段的 fallback**：

1. **Embedder 挂了**
   - 某些场景可以退到 sparse-only
   - 但如果当前 query 强依赖 dense route，结果质量会明显下降
2. **Reranker 挂了**
   - 明确 fallback 到 fusion / RRF 结果
   - trace 中应记录 `warn.rerank_fallback`
3. **OCR / caption / enricher 挂了**
   - 不阻断主链路
   - 只会缺失增强信息，主检索仍可基于事实文本运行
4. **Judge / evaluator 挂了**
   - 不应拖死主业务 query
   - 评估 case 标失败或 blocked
5. **LLM Provider 整体不可用**
   - 如果有多 provider 策略可切换，可以切到下一提供方
   - 但不是所有组件都能无缝切换，embedding / rerank / judge / evaluator 的 fallback 口径不同

---

## 三、简历包装点评

### 包装合理 ✅

- **“将元数据注入到 chunk 的 metadata 中；可选对每个 chunk 使用 llm 生成 summary 或关键词并注入到 metadata 中”**：你能说出 OCR、caption、keywords、summary、`asset_id`、anchor 这些具体信息，说明你对 `transform_post` 的职责不是只停留在标题层面。
- **“建立了覆盖 100+ REAL case 的自动化 QA 回归体系”**：你能解释为什么测试要分层，以及为什么 skill 驱动的 REAL case 不能简单等价成“一套从头跑到尾的 E2E”，这一点是成立的。

### 露馅点 ❌

- **“存储设计理解较完整”** → 你把增强信息也说成“放在 circle light 里面”，并且没有清晰分开 `app.sqlite / fts.sqlite / Chroma / 文件系统` 各自的真实职责。**严重性：中**
- **“Provider 挂了有清晰降级策略”** → 你回答到了 sparse-only 和 rerank fallback，但把“按优先级切换其他大模型提供商”说得过于笼统，没有区分 embedding、rerank、judge、evaluator 各自的 fallback 差异。**严重性：中**
- **“RRF 与 fallback 细节掌握”** → 你提到“rff 排序”，术语本身都说错了，面试中会被认为掌握不够扎实。**严重性：低**

### 改进建议

- 把存储层背成固定答案：`文件系统 + app.sqlite + fts.sqlite + Chroma`，每层一句话说明职责。
- 把 fallback 按阶段背清楚：`embedder / reranker / enricher / evaluator` 分开说，不要混成“LLM 挂了就切 provider”。
- 术语必须准确，特别是 `RRF`、`Cross-Encoder`、`retrieval view`、`chunk_retrieval_text` 这类高频词。

---

## 四、综合评价

**优势**
- 对 `transform_post`、metadata enrichment、asset 映射这条链路掌握相对扎实。
- 对 QA 为什么不能只用一套测试覆盖所有问题，解释比较自然，说明你参与过真实测试组织。
- 回答时能从业务效果、模块职责和工程流程三个层次切换，不是只会背名词。

**薄弱点**
- 存储架构回答不够准确，混淆了不同层的职责边界。
- 降级与 fallback 只答到了概念，没有体现 trace、provider snapshot、阶段化降级这类实现细节。
- 理论术语精度不够，容易在强压力面试或源码面试里失分。

**面试官建议**
- 重点补强 3 类固定题：
  1. 存储架构与删除一致性
  2. fallback 设计与 trace 可观测性
  3. RRF / Cross-Encoder / Ragas 指标的标准定义
- 回答时尽量使用“阶段 → 字段 → 行为结果”的结构，例如：
  - `reranker 挂了 → warn.rerank_fallback → effective_rank_source=fusion`
- 对简历里的“量化结果”准备一套更标准的复述方式，避免泛泛而谈。

---

## 五、评分

| 维度 | 分数（满分 10） | 评分依据（具体扣分原因） |
|-----|--------------|--------------------------------|
| 项目架构掌握 | 7.0 | 了解主链路和模块职责，但存储分层与 provider fallback 讲得不够精确。 |
| 简历真实性 | 7.5 | 多数内容能自圆其说，没有明显完全答不上来的点，但有几处实现口径较模糊。 |
| 算法理论深度 | 5.8 | 本轮没有体现出 RRF、Cross-Encoder、评估指标等理论深度，术语精度也一般。 |
| 实现细节掌握 | 6.4 | `transform_post` 答得较好，但 SQLite/FTS/Chroma 边界和 fallback 细节不够硬。 |
| 表达清晰度 | 7.2 | 表达连续，方向大体对，但有重复和口误，结构性还可以更强。 |
| **综合** | **6.8** | 具备项目参与感和整体理解，但距离“技术面试里很稳地扛住深问”还有一段距离。 |

