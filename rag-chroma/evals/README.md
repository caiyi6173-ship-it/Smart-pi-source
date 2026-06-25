# smartpi RAG 评测框架

基于 LLM 自动生成评测数据、运行 RAG 评测、自动评分的质量控制框架。

**重要声明：所有生成内容仅用于评测与质量控制，不得直接写入知识库作为事实资料。**

## 目录结构

```
evals/
  README.md          # 本文件
  eval_client.py     # OpenAI-compatible LLM 调用客户端
  schemas.py         # 评测数据结构 (Pydantic)
  datasets/          # 生成的评测集 JSONL
  reports/           # 自动评测报告
  rubrics/           # 人工可读评分标准
    answer_quality.md
    citation_quality.md
    safety_quality.md
  scripts/
    generate_eval_set.py  # 生成评测集
    run_rag_eval.py       # 运行 RAG 评测
    judge_answers.py      # 自动评分
    quality_report.py     # 评测集质量报告
    create_gold_set.py    # Gold set 标注工具
    diff_reports.py       # 报告对比与 CI 门禁
  tests/
    test_schemas.py       # 数据模型测试
    test_generate.py      # 生成脚本测试
    test_diff_reports.py  # 报告对比测试
    test_eval_client.py   # LLM 客户端测试
```

## 环境变量配置

在 `rag-chroma/.env` 中增加以下配置（与主 RAG 配置独立）：

```env
EVAL_LLM_BASE_URL=https://api.example.com/v1
EVAL_LLM_API_KEY=sk-...
EVAL_LLM_MODEL=gpt-4o-mini
EVAL_LLM_TEMPERATURE=0.2
EVAL_LLM_TIMEOUT_SECONDS=60
EVAL_LLM_MAX_RETRIES=3
EVAL_LLM_MIN_INTERVAL=0.5
```

- `EVAL_LLM_BASE_URL`：OpenAI-compatible API 地址（可选，默认 OpenAI）。
- `EVAL_LLM_API_KEY`：API Key（必填）。
- `EVAL_LLM_MODEL`：模型名（必填）。
- `EVAL_LLM_TEMPERATURE`：生成温度（可选，默认 0.2）。
- `EVAL_LLM_TIMEOUT_SECONDS`：超时秒数（可选，默认 60）。
- `EVAL_LLM_MAX_RETRIES`：LLM 调用最大重试次数（可选，默认 3）。
- `EVAL_LLM_MIN_INTERVAL`：两次 LLM 调用最小间隔秒数（可选，默认 0.5）。

不复用主 RAG 的 `DASHSCOPE_API_KEY`，避免生成器和被测系统混淆。

## 使用流程

### 1. 生成评测集

前提：向量库中已有导入的 chunks。

```bash
cd rag-chroma
python evals/scripts/generate_eval_set.py \
    --output evals/datasets/tcm_eval.jsonl \
    --samples 200 \
    --source-types modern_basics,classic_text,safety_rule \
    --concurrency 5 \
    --difficulty-ratio 3:4:3
```

参数说明：
- `--output`：输出 JSONL 路径（默认 `evals/datasets/tcm_eval.jsonl`）。
- `--samples`：目标样本数（默认 200）。
- `--source-types`：逗号分隔的 source_type 过滤。
- `--concurrency`：并发数（默认 5）。
- `--difficulty-ratio`：难度比例 easy:medium:hard（默认 3:4:3）。
- `--overwrite`：覆盖已有文件（断点续跑时不要加此参数）。

内置功能：
- **去重**：自动检测相似度 >= 0.85 的问题并跳过。
- **难度分布控制**：按 `--difficulty-ratio` 比例分配 easy/medium/hard。
- **Chunk 覆盖率**：生成完成后打印已使用 chunk 数量和覆盖率。

### 2. 运行 RAG 评测

前提：RAG API 已启动。

```bash
python evals/scripts/run_rag_eval.py \
    --dataset evals/datasets/tcm_eval.jsonl \
    --rag-url http://127.0.0.1:8094 \
    --output evals/reports/tcm_eval_report.json \
    --concurrency 10
```

参数说明：
- `--dataset`：评测集 JSONL 路径（必填）。
- `--rag-url`：RAG API 地址（默认 `http://127.0.0.1:8094`）。
- `--output`：报告输出路径（默认 `evals/reports/tcm_eval_report.json`）。
- `--concurrency`：并发数（默认 10）。

### 3. 自动评分

```bash
python evals/scripts/judge_answers.py \
    --dataset evals/datasets/tcm_eval.jsonl \
    --rag-report evals/reports/tcm_eval_report.json \
    --output evals/reports/tcm_judged_report.json \
    --concurrency 5
```

参数说明：
- `--dataset`：评测集 JSONL 路径（必填）。
- `--rag-report`：RAG 评测报告路径（必填）。
- `--output`：评分报告输出路径（默认 `evals/reports/tcm_judged_report.json`）。
- `--concurrency`：并发数（默认 5）。

### 4. 质量报告

分析评测集的分布、覆盖率、近似重复：

```bash
python evals/scripts/quality_report.py \
    --dataset evals/datasets/tcm_eval.jsonl \
    --output evals/reports/quality_report.json
```

报告内容：
- 难度 / question_type / source_type 分布
- Chunk 使用覆盖率和频率分布
- 近似重复问题对（相似度 >= 0.85）

### 5. Gold Set 标注

创建人工标注的 gold set，用于校准自动评分：

```bash
# 第一步：抽取待标注样本
python evals/scripts/create_gold_set.py \
    --dataset evals/datasets/tcm_eval.jsonl \
    --sample 50 \
    --output evals/datasets/gold_set_unlabeled.jsonl

# 第二步：人工编辑 gold_set_unlabeled.jsonl，填写 _label 字段：
#   _label.human_score: 0-5 整数
#   _label.human_verdict: pass / warn / fail
#   _label.human_notes: 备注（可选）

# 第三步：验证并生成最终 gold set
python evals/scripts/create_gold_set.py \
    --validate evals/datasets/gold_set_unlabeled.jsonl \
    --output evals/datasets/gold_set.jsonl
```

验证规则：
- `human_score` 必须为 0-5 整数。
- `human_verdict` 必须为 pass/warn/fail。
- score 和 verdict 必须一致（score>=4→pass, 3→warn, <=2→fail）。

## JSONL 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 样本唯一 ID，格式 `eval_xxx` |
| `question` | string | 评测问题 |
| `question_type` | enum | knowledge / classic / safety / retrieval / adversarial |
| `source_type` | enum | modern_basics / classic_text / safety_rule / mixed |
| `expected_answer` | string | 基于 evidence 的标准答案 |
| `wrong_answer` | string | 常见错误答案 |
| `distractors` | list | 检索迷惑选项 |
| `rubric` | object | 评分标准（must_include、must_not_include、citation_required、safety_required） |
| `evidence` | list | 证据来源（document_id、chunk_id、title、source_id、source_type、text） |
| `metadata` | object | 生成元数据（generated_by、generated_at、difficulty） |

## 评分维度

| 维度 | 说明 |
|------|------|
| faithfulness_score | 是否忠于 evidence，未编造 |
| citation_score | 是否引用到正确来源 |
| safety_score | 是否包含必要安全提示 |
| completeness_score | 是否覆盖 must_include 要点 |
| verdict | pass (>=4) / warn (3) / fail (<=2) |

## 评分标准文档

详见：
- `rubrics/answer_quality.md` — 答案质量标准
- `rubrics/citation_quality.md` — 引用质量标准
- `rubrics/safety_quality.md` — 医疗安全标准

### 6. 报告对比与 CI 门禁

对比两份评测报告，检测回归：

```bash
# 对比 RAG 评测报告
python evals/scripts/diff_reports.py \
    --baseline evals/reports/tcm_eval_report_v1.json \
    --current evals/reports/tcm_eval_report_v2.json

# 对比评分报告
python evals/scripts/diff_reports.py \
    --baseline evals/reports/tcm_judged_report_v1.json \
    --current evals/reports/tcm_judged_report_v2.json \
    --type judged

# CI 门禁：平均分低于阈值则 exit 1
python evals/scripts/diff_reports.py \
    --baseline evals/reports/tcm_judged_report_v1.json \
    --current evals/reports/tcm_judged_report_v2.json \
    --type judged \
    --gate-min-score 3.5
```

对比内容：
- 总体指标变化（平均延迟、有答案率、引用命中率等）
- 按 question_type / source_type 的分组变化
- 新增/丢失/变化的样本
- 评分提升/下降/新增失败（judged 类型）

### 7. 运行测试

```bash
pip install pytest
python -m pytest Data/tests/ -v
```

测试覆盖：
- `test_schemas.py`：Pydantic 模型校验、JSON 往返、字段约束
- `test_generate.py`：去重、难度分布、chunk 覆盖率、文件加载
- `test_diff_reports.py`：报告对比逻辑、回归检测
- `test_eval_client.py`：mock LLM 调用、重试、错误处理

## 断点续跑

所有脚本支持断点续跑。如果中途中断，重新运行即可自动跳过已完成的样本：

- `generate_eval_set.py`：按 `sample_id` 跳过，追加写入 JSONL。
- `run_rag_eval.py`：按 `sample_id` 跳过，保留已有结果后追加。
- `judge_answers.py`：按 `sample_id` 跳过，保留已有结果后追加。

注意：断点续跑时**不要**加 `--overwrite` 参数。

## 重试机制

`eval_client.py` 内置指数退避重试：

- 网络连接错误、超时、429 速率限制：自动重试（最多 `EVAL_LLM_MAX_RETRIES` 次）。
- 400 参数错误等不可恢复错误：立即失败，不重试。
- JSON 解析失败：重试一次后放弃。
- 两次调用间隔不低于 `EVAL_LLM_MIN_INTERVAL` 秒，避免触发速率限制。

## 注意事项

1. 生成内容仅用于评测，不能作为知识库事实来源。
2. 评测 LLM 配置与主 RAG 配置独立，避免混淆。
3. 单条评分失败不会中断整个批次。
4. 所有 JSON 输出使用 `ensure_ascii=False`。
5. 脚本应独立运行，除 `run_rag_eval.py` 外不要求启动主服务。
