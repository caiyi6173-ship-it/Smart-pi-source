# Retrieval Pipeline

The current retrieval layer implements a production-shaped hybrid RAG pipeline while keeping dependencies light enough for Raspberry Pi development.

## Flow

1. Query rewrite
   - Expands common TCM terms with curated synonyms.
   - Example: `舌苔黄腻` also recalls `黄腻苔`, `湿热`, `痰热`.

2. Multi-route recall
   - Vector recall from the configured vector backend.
   - BM25 lexical recall over stored chunks.
   - Metadata filters are applied before both recall routes.

3. Fusion
   - Uses reciprocal rank fusion (RRF).
   - Weighted by `VECTOR_WEIGHT` and `LEXICAL_WEIGHT`.

4. Rerank
   - Default provider is DashScope `qwen3-rerank`, a cloud cross-encoder reranker.
   - If `DASHSCOPE_API_KEY` is missing or the cloud call fails, the service falls back to the lightweight local reranker.
   - The local fallback combines vector score, BM25 score, query-token overlap, and title overlap.

5. Threshold and abstention
   - Chunks below `MIN_RELEVANCE_SCORE` are dropped.
   - If fewer than `MIN_CHUNKS_FOR_ANSWER` chunks remain, the answer generator refuses to answer from unsupported evidence.

## API

- `POST /api/v1/query`: runs retrieval and answer generation.
- `POST /api/v1/retrieve`: returns retrieval diagnostics without generation.

## Main Settings

```env
ENABLE_QUERY_REWRITE=true
ENABLE_HYBRID_SEARCH=true
ENABLE_RERANK=true
RERANK_PROVIDER=dashscope
RERANK_MODEL=qwen3-rerank
RERANK_URL=https://dashscope.aliyuncs.com/compatible-api/v1/reranks
RERANK_TOP_N=0
RERANK_INSTRUCTION=Given a TCM question, rank the documents by their evidence relevance. Prefer passages that directly answer the question and contain source-specific knowledge.
RECALL_TOP_K=24
LEXICAL_TOP_K=24
VECTOR_WEIGHT=0.65
LEXICAL_WEIGHT=0.35
MIN_RELEVANCE_SCORE=0.08
MIN_CHUNKS_FOR_ANSWER=1
```

## Remaining Production Work

- Replace curated rewrite dictionary with a versioned domain synonym table.
- Tune DashScope rerank top_n, instruction, and score thresholds on a real TCM evaluation set.
- Persist BM25 indexes for large corpora instead of scanning chunks.
- Add retrieval evaluation datasets and metrics.
- Tune thresholds per corpus and query class.
