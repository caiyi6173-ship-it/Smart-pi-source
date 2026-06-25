# RAG_EVAL_WORK_FILE：smartpi RAG 评测数据生成与自动评测框架

## 任务目标

为 `rag-chroma` 新增一套完整可运行的 RAG 评测框架，让其他大模型通过 **OpenAI-compatible 接口**生成大量评测问答、错误答案、迷惑选项、评分标准草稿，并能自动调用当前 RAG API 运行评测、输出报告。

核心原则：

- 大模型生成内容只用于 **评测与质量控制**，不得直接写入知识库作为事实资料。
- 所有生成题目必须绑定已有知识库 chunk，并保留 `document_id`、`chunk_id`、`title`、`source_type` 等证据来源。
- 默认复用当前 `rag-chroma` 工程，不重构主 RAG API。
- 新增内容集中放在 `rag-chroma/evals/`，避免影响线上查询链路。

## 当前工程背景

当前主线 RAG 目录：

```text
rag-chroma/
```

现有能力：

- FastAPI RAG API
- 文档导入
- chunk 切分
- 向量检索
- BM25 混合检索
- reranker 重排序
- metadata filter
- query rewrite
- 找不到就拒答

当前已有核心文件：

```text
rag-chroma/app/main.py
rag-chroma/app/config.py
rag-chroma/app/schemas.py
rag-chroma/app/retrieval/vector_store.py
rag-chroma/app/retrieval/service.py
rag-chroma/app/ingest/service.py
rag-chroma/scripts/ingest.py
rag-chroma/scripts/query_cli.py
```

本任务只新增评测框架，不直接修改主检索策略。

## 需要新增的目录结构

在 `rag-chroma/` 下新增：

```text
evals/
  README.md
  datasets/
    .gitkeep
  reports/
    .gitkeep
  rubrics/
    answer_quality.md
    citation_quality.md
    safety_quality.md
  scripts/
    generate_eval_set.py
    run_rag_eval.py
    judge_answers.py
  eval_client.py
  schemas.py
```

用途：

- `datasets/` 保存生成的评测集 JSONL
- `reports/` 保存自动评测报告
- `rubrics/` 保存人工可读评分标准
- `scripts/` 保存命令行脚本
- `eval_client.py` 封装 OpenAI-compatible LLM 调用
- `schemas.py` 定义评测数据结构

## OpenAI-compatible 模型配置

在 `rag-chroma/.env.example` 增加评测专用配置：

```env
EVAL_LLM_BASE_URL=https://api.example.com/v1
EVAL_LLM_API_KEY=
EVAL_LLM_MODEL=
EVAL_LLM_TEMPERATURE=0.2
EVAL_LLM_TIMEOUT_SECONDS=60
```

实现要求：

- 使用 `openai` Python SDK 的兼容模式。
- v1 只支持 OpenAI-compatible，不需要多个 provider 抽象。
- 如果缺少 `EVAL_LLM_API_KEY` 或 `EVAL_LLM_MODEL`，脚本应明确报错。
- 不复用 RAG 回答模型配置，避免生成器和被测系统混淆。

## 评测集 JSONL Schema

每行一个样本，字段固定如下：

```json
{
  "id": "eval_xxx",
  "question": "舌苔黄腻通常提示什么？",
  "question_type": "knowledge|classic|safety|retrieval|adversarial",
  "source_type": "modern_basics|classic_text|safety_rule|mixed",
  "expected_answer": "标准答案草稿",
  "wrong_answer": "常见错误答案",
  "distractors": ["迷惑选项1", "迷惑选项2", "迷惑选项3"],
  "rubric": {
    "must_include": ["必须包含的要点"],
    "must_not_include": ["不能出现的错误"],
    "citation_required": true,
    "safety_required": true
  },
  "evidence": [
    {
      "document_id": "...",
      "chunk_id": "...",
      "title": "...",
      "source_id": "...",
      "source_type": "...",
      "text": "原始chunk文本片段"
    }
  ],
  "metadata": {
    "generated_by": "model-name",
    "generated_at": "ISO datetime",
    "difficulty": "easy|medium|hard"
  }
}
```

约束：

- `expected_answer` 必须基于 `evidence`，不能引入证据外知识。
- `wrong_answer` 要代表真实容易出现的错误，例如过度诊断、误用古籍、忽略安全边界。
- `distractors` 用于选择题或检索迷惑项，必须看起来合理但不完全正确。
- `safety_required=true` 时，评分必须检查医疗安全提示。

## 脚本一：生成评测集

新增：

```text
rag-chroma/evals/scripts/generate_eval_set.py
```

命令示例：

```bash
cd rag-chroma
python evals/scripts/generate_eval_set.py \
  --output evals/datasets/tcm_eval.jsonl \
  --samples 200 \
  --questions-per-chunk 2 \
  --source-types modern_basics,classic_text,safety_rule
```

行为要求：

- 从当前向量库读取已导入 chunks。
- 如果没有 chunks，报错提示先运行：

```bash
python scripts/ingest.py data/raw --source-type mixed
```

- 每个样本选择 1-3 个 evidence chunks。
- 调用评测 LLM 生成：
  - question
  - expected_answer
  - wrong_answer
  - distractors
  - rubric
  - difficulty
  - question_type
- 输出 JSONL。
- 生成失败的样本跳过并记录错误数量。
- 默认不覆盖已有文件，除非传入 `--overwrite`。

## 脚本二：运行 RAG 自动评测

新增：

```text
rag-chroma/evals/scripts/run_rag_eval.py
```

命令示例：

```bash
python evals/scripts/run_rag_eval.py \
  --dataset evals/datasets/tcm_eval.jsonl \
  --rag-url http://127.0.0.1:8095 \
  --output evals/reports/tcm_eval_report.json
```

行为要求：

- 对每个样本调用 `POST /api/v1/query`。
- 请求包含：
  - `question`
  - `top_k`
  - `include_chunks=true`
  - `filters` 根据样本 `source_type` 可选传入
- 保存每条结果：
  - RAG answer
  - citations
  - retrieved chunk ids
  - latency_ms
  - no_answer
  - retrieval_strategy
  - rerank_provider
- 输出总体报告：
  - 样本数
  - 平均延迟
  - 有答案率
  - 引用命中率
  - evidence chunk 命中率
  - no-answer 情况
  - 每类 question_type 的统计

## 脚本三：自动评分

新增：

```text
rag-chroma/evals/scripts/judge_answers.py
```

命令示例：

```bash
python evals/scripts/judge_answers.py \
  --dataset evals/datasets/tcm_eval.jsonl \
  --rag-report evals/reports/tcm_eval_report.json \
  --output evals/reports/tcm_judged_report.json
```

评分方式：

- 使用 OpenAI-compatible 评测模型。
- 每条样本按 0-5 分评分。
- 单条评分失败不应中断整个批次。

单条评分输出结构：

```json
{
  "sample_id": "eval_xxx",
  "score": 4,
  "citation_score": 1,
  "faithfulness_score": 1,
  "safety_score": 1,
  "completeness_score": 1,
  "issues": ["引用不够具体"],
  "verdict": "pass|warn|fail"
}
```

默认评分维度：

- `faithfulness_score`：是否忠于 evidence
- `citation_score`：是否引用到正确来源
- `safety_score`：是否包含必要医疗安全边界
- `completeness_score`：是否覆盖 rubric 要点
- `wrong_answer_detection`：是否避免了 wrong_answer 中的错误说法

总体报告包含：

- 平均分
- pass/warn/fail 数量
- 低分样本列表
- 常见失败原因
- 按 `source_type`、`question_type` 的分组表现

## eval_client.py 要求

新增：

```text
rag-chroma/evals/eval_client.py
```

职责：

- 读取 `EVAL_LLM_BASE_URL`
- 读取 `EVAL_LLM_API_KEY`
- 读取 `EVAL_LLM_MODEL`
- 读取 `EVAL_LLM_TEMPERATURE`
- 读取 `EVAL_LLM_TIMEOUT_SECONDS`
- 调用 OpenAI-compatible chat completions
- 支持要求模型输出 JSON
- 对非 JSON 输出做清晰错误提示

建议接口：

```python
class EvalLLMClient:
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        ...
```

## schemas.py 要求

新增：

```text
rag-chroma/evals/schemas.py
```

建议定义：

- `EvalEvidence`
- `EvalRubric`
- `EvalMetadata`
- `EvalSample`
- `RagEvalResult`
- `JudgeResult`

字段要和 JSONL schema 保持一致。

优先使用 Pydantic，便于校验生成结果。

## Rubric 文档

新增三份可人工阅读的评分文档：

```text
rag-chroma/evals/rubrics/answer_quality.md
rag-chroma/evals/rubrics/citation_quality.md
rag-chroma/evals/rubrics/safety_quality.md
```

内容要覆盖：

- 什么是好答案
- 什么是幻觉
- 什么是证据不足
- 什么是引用不合格
- 什么情况下必须拒答
- 什么情况下必须提示线下就医

## evals/README.md 要求

新增：

```text
rag-chroma/evals/README.md
```

必须说明：

- 评测框架用途
- 环境变量配置
- 如何生成数据
- 如何运行 RAG 评测
- 如何自动评分
- JSONL 字段解释
- 生成内容不能直接作为知识库事实来源

同时在 `rag-chroma/README.md` 增加 `Evaluation` 小节，链接到：

```text
evals/README.md
```

## 测试要求

实现完成后必须验证：

### 1. Schema 测试

- 生成的 JSONL 每行都能被 `schemas.py` 解析。
- 缺字段、错误类型、空 evidence 应被拒绝。

### 2. 生成脚本测试

- 无 chunks 时给出清晰错误。
- 有 chunks 时能生成至少 5 条样本。
- `--overwrite` 行为正确。
- 生成结果包含：
  - question
  - expected_answer
  - wrong_answer
  - distractors
  - rubric
  - evidence

### 3. RAG 评测脚本测试

- 能读取 JSONL。
- 能调用本地 RAG API。
- 能输出 report JSON。
- API 不可用时给出清晰错误。

### 4. 自动评分脚本测试

- 能读取 dataset 和 rag report。
- 能调用评测 LLM。
- 能输出 judged report。
- 单条评分失败不应中断整个批次。

### 5. 回归检查

- 不改变 `/api/v1/query`、`/api/v1/ingest` 等现有 API 行为。
- 不把生成数据写入 `data/raw`。
- 不影响现有 `tests/`。

## 验收标准

完成后应满足：

- `rag-chroma/evals/` 目录完整存在。
- `.env.example` 包含 `EVAL_LLM_*` 配置。
- 可以通过命令生成 JSONL 评测集。
- 可以通过命令调用本地 RAG API 生成评测报告。
- 可以通过命令调用评测模型生成打分报告。
- 文档说明完整，其他开发者能按 README 使用。
- 生成内容明确标注为评测材料，不作为知识库事实来源。

## 明确不做

本任务不做以下内容：

- 不修改主 RAG 检索算法。
- 不修改 `/api/v1/query` 返回结构。
- 不引入新的向量库。
- 不把大模型生成内容导入 `data/raw`。
- 不做人工审核 UI。
- 不做多 provider 抽象。
- 不做并发、断点续跑等高级能力，后续可扩展。

## 实现注意事项

- 当前主线 RAG 目录是 `rag-chroma/`。
- 当前工程使用 Python、FastAPI、Pydantic、OpenAI SDK。
- 评测数据默认从已经导入向量库的 chunks 中抽取。
- 如果本地没有向量数据，应提示用户先导入资料。
- 评测脚本应尽量独立运行，不要求启动完整主服务，除了 `run_rag_eval.py` 需要 RAG API 已启动。
- 所有 JSON 输出使用 `ensure_ascii=False`。
- 所有文件读写使用 UTF-8。
- 错误提示要清楚，方便非原作者排查。
