"""调用本地 RAG API 运行评测，输出评测报告 JSON。

支持断点续跑：已完成的 sample_id 会自动跳过。
支持并发控制：--concurrency 参数控制并发数。

用法：
    python evals/scripts/run_rag_eval.py \
        --dataset evals/datasets/tcm_eval.jsonl \
        --rag-url http://127.0.0.1:8094 \
        --output evals/reports/tcm_eval_report.json \
        --concurrency 10
"""

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

# 将 evals 根目录加入 sys.path
EVALS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVALS_ROOT))

from schemas import EvalSample, RagEvalResult


def load_dataset(path: Path) -> list[EvalSample]:
    """加载 JSONL 评测集。"""
    samples = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(EvalSample(**json.loads(line)))
            except Exception as e:
                print(f"  警告：第 {i} 行解析失败，跳过: {e}", file=sys.stderr)
    return samples


def load_existing_results(path: Path) -> tuple[dict[str, dict], list[dict]]:
    """加载已有结果，用于断点续跑。返回 (sample_id->result 映射, 原始列表)。"""
    results: list[dict] = []
    if not path.exists():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        results = data.get("results", [])
    except (json.JSONDecodeError, KeyError):
        pass
    by_id = {r["sample_id"]: r for r in results}
    return by_id, results


async def call_rag_api_async(
    client: httpx.AsyncClient,
    rag_url: str,
    sample: EvalSample,
) -> RagEvalResult:
    """异步调用 RAG /api/v1/query 并返回结果。"""
    payload: dict = {
        "question": sample.question,
        "top_k": 8,
        "include_chunks": True,
    }
    if sample.source_type != "mixed":
        payload["filters"] = {"source_type": sample.source_type}

    start = time.perf_counter()
    try:
        resp = await client.post(f"{rag_url}/api/v1/query", json=payload, timeout=60)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        resp.raise_for_status()
        data = resp.json()
        return RagEvalResult(
            sample_id=sample.id,
            question=sample.question,
            rag_answer=data.get("answer", ""),
            citations=[c for c in data.get("citations", [])],
            retrieved_chunk_ids=[c.get("chunk_id", "") for c in data.get("citations", [])],
            latency_ms=elapsed_ms,
            no_answer=data.get("no_answer", False),
            retrieval_strategy=data.get("retrieval_strategy", ""),
            rerank_provider=data.get("rerank_provider", ""),
        )
    except httpx.ConnectError:
        return RagEvalResult(
            sample_id=sample.id,
            question=sample.question,
            error=f"无法连接 RAG API ({rag_url})，请确认服务已启动。",
        )
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return RagEvalResult(
            sample_id=sample.id,
            question=sample.question,
            latency_ms=elapsed_ms,
            error=str(e),
        )


async def run_eval(
    rag_url: str,
    samples: list[EvalSample],
    existing: dict[str, dict],
    concurrency: int,
) -> list[RagEvalResult]:
    """并发运行 RAG 评测。返回完整结果列表（含已有）。"""
    # 先恢复已有结果
    results: list[RagEvalResult] = []
    pending: list[EvalSample] = []
    for s in samples:
        if s.id in existing:
            r = existing[s.id]
            results.append(RagEvalResult(**r))
        else:
            pending.append(s)

    if not pending:
        print("所有样本已完成，无需重新评测")
        return results

    print(f"已有 {len(results)} 条结果，待评测 {len(pending)} 条，并发数 {concurrency}")

    semaphore = asyncio.Semaphore(concurrency)
    total = len(samples)

    async def eval_one(sample: EvalSample) -> RagEvalResult:
        async with semaphore:
            async with httpx.AsyncClient() as client:
                return await call_rag_api_async(client, rag_url, sample)

    # 批量并发
    batch_size = concurrency * 2  # 每批提交量略大于并发数
    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start:batch_start + batch_size]
        batch_results = await asyncio.gather(
            *[eval_one(s) for s in batch], return_exceptions=True
        )
        for sample, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                result = RagEvalResult(
                    sample_id=sample.id,
                    question=sample.question,
                    error=str(result),
                )
            results.append(result)
            status = "错误" if result.error else ("拒答" if result.no_answer else "OK")
            print(f"  [{len(results)}/{total}] {sample.id} -> {status} ({result.latency_ms}ms)")

    return results


def build_report(results: list[RagEvalResult], samples: list[EvalSample]) -> dict:
    """生成总体报告。"""
    total = len(results)
    errors = sum(1 for r in results if r.error)
    no_answer_count = sum(1 for r in results if r.no_answer)
    has_answer = total - errors - no_answer_count
    latencies = [r.latency_ms for r in results if r.latency_ms > 0]
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0

    sample_map = {s.id: s for s in samples}
    citation_hit = 0
    evidence_hit = 0
    for r in results:
        s = sample_map.get(r.sample_id)
        if not s:
            continue
        for ev in s.evidence:
            snippet = ev.text[:30]
            if snippet and snippet in r.rag_answer:
                citation_hit += 1
                break
        ev_ids = {ev.chunk_id for ev in s.evidence}
        if ev_ids & set(r.retrieved_chunk_ids):
            evidence_hit += 1

    type_counter: Counter[str] = Counter()
    type_latency: dict[str, list[int]] = {}
    type_no_answer: Counter[str] = Counter()
    for r in results:
        s = sample_map.get(r.sample_id)
        if not s:
            continue
        qt = s.question_type
        type_counter[qt] += 1
        type_latency.setdefault(qt, []).append(r.latency_ms)
        if r.no_answer:
            type_no_answer[qt] += 1

    per_type_stats = {}
    for qt in sorted(type_counter):
        lats = type_latency.get(qt, [])
        per_type_stats[qt] = {
            "count": type_counter[qt],
            "avg_latency_ms": int(sum(lats) / len(lats)) if lats else 0,
            "no_answer_count": type_no_answer.get(qt, 0),
        }

    return {
        "summary": {
            "total_samples": total,
            "errors": errors,
            "has_answer_count": has_answer,
            "no_answer_count": no_answer_count,
            "avg_latency_ms": avg_latency,
            "citation_hit_count": citation_hit,
            "citation_hit_rate": round(citation_hit / total, 3) if total else 0,
            "evidence_hit_count": evidence_hit,
            "evidence_hit_rate": round(evidence_hit / total, 3) if total else 0,
        },
        "per_question_type": per_type_stats,
        "results": [r.model_dump() for r in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="调用 RAG API 运行评测")
    parser.add_argument("--dataset", required=True, help="评测集 JSONL 路径")
    parser.add_argument("--rag-url", default="http://127.0.0.1:8094", help="RAG API 地址")
    parser.add_argument("--output", default="evals/reports/tcm_eval_report.json", help="报告输出路径")
    parser.add_argument("--concurrency", type=int, default=10, help="并发数（默认 10）")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"错误：评测集文件不存在: {dataset_path}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"加载评测集: {dataset_path}")
    samples = load_dataset(dataset_path)
    if not samples:
        print("错误：评测集为空", file=sys.stderr)
        sys.exit(1)
    print(f"共 {len(samples)} 条样本")

    # 断点续跑：加载已有结果
    existing_map, _ = load_existing_results(output_path)
    if existing_map:
        print(f"检测到已有 {len(existing_map)} 条结果，将断点续跑")

    print(f"开始评测，RAG API: {args.rag_url}")
    results = asyncio.run(
        run_eval(
            rag_url=args.rag_url,
            samples=samples,
            existing=existing_map,
            concurrency=args.concurrency,
        )
    )

    report = build_report(results, samples)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    s = report["summary"]
    print(f"\n评测完成:")
    print(f"  总样本: {s['total_samples']}")
    print(f"  有答案: {s['has_answer_count']}")
    print(f"  拒答:   {s['no_answer_count']}")
    print(f"  错误:   {s['errors']}")
    print(f"  平均延迟: {s['avg_latency_ms']}ms")
    print(f"  引用命中率: {s['citation_hit_rate']}")
    print(f"  证据命中率: {s['evidence_hit_rate']}")
    print(f"\n报告已写入: {output_path}")


if __name__ == "__main__":
    main()
