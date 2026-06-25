# Trusted RAG Design

本文档说明 smartpi RAG 当前的可信回答机制。目标不是让大模型“看起来会答”，而是让每个答案都能被证据、引用和评测追踪。

## 可信链路

```text
question
  -> query rewrite
  -> vector recall + BM25 recall + metadata routes
  -> RRF fusion
  -> cloud/local rerank
  -> relevance threshold
  -> evidence pack
  -> answer generation with citation markers
  -> safety notice
```

## Evidence Pack

`/api/v1/query` 返回的每条 citation 都对应一个实际 chunk，包含：

- `index`：答案正文里的引用编号，例如 `[1]`
- `title`：资料标题
- `source_id`：来源标识
- `source_type`：来源类型，例如 `classic_text`、`modern_basics`、`safety_rule`
- `document_id` / `chunk_id`：可回溯到向量库的证据 ID
- `page` / `section`：页码或章节，若导入资料提供
- `score`、`vector_score`、`lexical_score`、`rerank_score`：检索与重排序分数
- `retrieval_source`：证据来自 vector、BM25、hybrid 还是 rerank 后结果
- `excerpt`：用于前端展示和人工核对的证据片段

## Refusal Policy

当检索结果为空，或所有候选 chunk 被相似度阈值过滤掉时：

- `no_answer=true`
- `evidence_status=insufficient_evidence`
- `evidence_count=0`
- 答案必须明确说明“知识库未找到可靠依据”
- 不允许生成推断性中医解释

## Citation Policy

当存在证据时：

- prompt 会把每个 chunk 编号为 `[1]`、`[2]`、`[3]`
- 生成答案要求关键结论后标注证据编号
- 如果云端模型返回内容没有任何 `[n]` 引用编号，生成层会追加“引用来源”兜底段落
- API 的 `citations` 字段始终返回结构化证据，供前端、Agent 和评测脚本使用

## Safety Policy

所有生成答案都会附加固定医疗安全提示：

> 仅供中医知识参考，不能替代医生诊断。若存在急症、孕产、儿童、严重慢病或用药冲突，请及时线下就医。

涉及急症、孕产、儿童、严重慢病、用药冲突时，后续应优先召回 `safety_rule` 与 `modern_basics` 资料，并倾向建议线下就医。

## Evaluation Metrics

可信 RAG 评测建议至少跟踪：

- citation hit rate：答案引用是否命中 evidence chunk
- evidence chunk hit rate：检索是否召回标注证据
- no-answer precision：拒答是否真的证据不足
- faithfulness score：答案是否忠于 evidence
- safety score：是否包含必要安全边界
- latency：端到端延迟

现有评测框架位于 `evals/`，生成数据只用于测试，不得写入知识库作为事实来源。

## Remaining Work

- 按 `source_type` 设置不同相似度阈值
- 将人工审核通过的 gold set 固化到版本库
- 为 citation 增加原文位置偏移量，支持前端高亮
- 对古籍原文、现代科普、安全规则分别统计召回质量
- 增加 RAG 回答 diff 报告，防止知识库更新后质量回退
