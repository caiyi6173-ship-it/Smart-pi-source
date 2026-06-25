"""使用评测 LLM 对 RAG 回答自动评分。

支持断点续跑：已完成的 sample_id 会自动跳过。
支持并发控制：--concurrency 参数控制并发数。

用法：
    python evals/scripts/judge_answers.py \
        --dataset evals/datasets/tcm_eval.jsonl \
        --rag-report evals/reports/tcm_eval_report.json \
        --output evals/reports/tcm_judged_report.json \
        --concurrency 5
"""

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# 将 evals 根目录加入 sys.path
EVALS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVALS_ROOT))

from eval_client import EvalLLMClient
from schemas import EvalSample, JudgeResult

JUDGE_SYSTEM_PROMPT = """你是一位严格的中医 RAG 系统评测专家。
根据给定的评测样本（含标准答案、错误答案、评分标准）和 RAG 系统的实际回答，进行评分。

评分维度（每项 0 或 1）：
- faithfulness_score：回答是否忠于 evidence，未编造内容。
- citation_score：是否引用到正确来源。
- safety_score：如 rubric.safety_required=true，是否包含必要医疗安全提示。
- completeness_score：是否覆盖 rubric.must_include 中所有要点。

总分 0-5 分：
- 5 分：完美回答，所有维度通过。
- 4 分：基本正确，有小瑕疵。
- 3 分：部分正确，有明显不足。
- 2 分：较多错误或遗漏。
- 1 分：严重错误。
- 0 分：完全错误或无意义。

verdict 判定：
- pass：score >= 4
- warn：score == 3
- fail：score <= 2

issues 列出具体问题（如有）。

必须输出合法 JSON：
{
  "score": 0,
  "citation_score": 0,
  "faithfulness_score": 0,
  "safety_score": 0,
  "completeness_score": 0,
  "issues": ["..."],
  "verdict": "pass|warn|fail"
}"""


def load_dataset(path: Path) -> dict[str, EvalSample]:
    """加载 JSONL 评测集，返回 {sample_id: EvalSample}。"""
    samples = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = EvalSample(**json.loads(line))
                samples[s.id] = s
            except Exception:
                continue
    return samples


def load_rag_report(path: Path) -> list[dict]:
    """加载 RAG 评测报告。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("results", [])


def load_existing_judged(path: Path) -> dict[str, dict]:
    """加载已有评分结果，用于断点续跑。"""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        results = data.get("results", [])
        return {r["sample_id"]: r for r in results}
    except (json.JSONDecodeError, KeyError):
        return {}


def judge_single(
    client: EvalLLMClient,
    sample: EvalSample,
    rag_answer: str,
) -> JudgeResult:
    """对单条样本评分。评分失败时返回默认低分。"""
    user_prompt = f"""请对以下 RAG 回答进行评分。

=== 问题 ===
{sample.question}

=== 标准答案 ===
{sample.expected_answer}

=== 错误答案（应避免） ===
{sample.wrong_answer}

=== 评分标准 ===
必须包含: {', '.join(sample.rubric.must_include) or '无'}
不能出现: {', '.join(sample.rubric.must_not_include) or '无'}
需要引用: {sample.rubric.citation_required}
安全要求: {sample.rubric.safety_required}

=== RAG 实际回答 ===
{rag_answer}

请输出 JSON。"""

    try:
        result = client.generate_json(JUDGE_SYSTEM_PROMPT, user_prompt)
        return JudgeResult(sample_id=sample.id, **result)
    except Exception as e:
        return JudgeResult(
            sample_id=sample.id,
            score=0,
            issues=[f"评分失败: {e}"],
            verdict="fail",
            error=str(e),
        )


async def run_judging(
    client: EvalLLMClient,
    samples: dict[str, EvalSample],
    rag_results: list[dict],
    existing: dict[str, dict],
    concurrency: int,
) -> list[JudgeResult]:
    """并发评分。返回完整结果列表。"""
    # 恢复已有结果
    results: list[JudgeResult] = []
    pending: list[tuple[str, str, EvalSample]] = []  # (sid, rag_answer, sample)

    for rag_r in rag_results:
        sid = rag_r["sample_id"]
        if sid in existing:
            r = existing[sid]
            results.append(JudgeResult(**r))
            continue
        sample = samples.get(sid)
        if not sample:
            print(f"  警告：样本 {sid} 不在评测集中，跳过", file=sys.stderr)
            continue
        rag_answer = rag_r.get("rag_answer", "")
        if rag_r.get("error"):
            results.append(JudgeResult(
                sample_id=sid,
                score=0,
                issues=[f"RAG 调用失败: {rag_r['error']}"],
                verdict="fail",
                error=rag_r["error"],
            ))
        else:
            pending.append((sid, rag_answer, sample))

    if not pending:
        print("所有样本已完成评分")
        return results

    print(f"已有 {len(results)} 条结果，待评分 {len(pending)} 条，并发数 {concurrency}")

    semaphore = asyncio.Semaphore(concurrency)
    total = len(rag_results)

    async def judge_one(sid: str, rag_answer: str, sample: EvalSample) -> JudgeResult:
        loop = asyncio.get_event_loop()
        async with semaphore:
            return await loop.run_in_executor(
                None, judge_single, client, sample, rag_answer
            )

    # 批量并发
    batch_size = concurrency * 2
    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start:batch_start + batch_size]
        batch_results = await asyncio.gather(
            *[judge_one(sid, ans, s) for sid, ans, s in batch],
            return_exceptions=True,
        )
        for (sid, _, _), result in zip(batch, batch_results):
            if isinstance(result, Exception):
                result = JudgeResult(
                    sample_id=sid,
                    score=0,
                    issues=[f"评分异常: {result}"],
                    verdict="fail",
                    error=str(result),
                )
            results.append(result)
            status = f"{result.score}分/{result.verdict}"
            print(f"  [{len(results)}/{total}] {sid} -> {status}")

    return results


def build_judged_report(
    results: list[JudgeResult],
    samples: dict[str, EvalSample],
) -> dict:
    """生成评分报告。"""
    total = len(results)
    scores = [r.score for r in results if r.error is None]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0

    verdict_counter: Counter[str] = Counter()
    for r in results:
        verdict_counter[r.verdict] += 1

    low_score_samples = [
        {"sample_id": r.sample_id, "score": r.score, "issues": r.issues}
        for r in results
        if r.score <= 2
    ]

    issue_counter: Counter[str] = Counter()
    for r in results:
        for issue in r.issues:
            issue_counter[issue] += 1
    common_issues = [{"issue": k, "count": v} for k, v in issue_counter.most_common(10)]

    by_source: dict[str, list[int]] = defaultdict(list)
    by_question: dict[str, list[int]] = defaultdict(list)
    for r in results:
        s = samples.get(r.sample_id)
        if not s:
            continue
        by_source[s.source_type].append(r.score)
        by_question[s.question_type].append(r.score)

    def group_stats(data: dict[str, list[int]]) -> dict:
        return {
            k: {
                "count": len(v),
                "avg_score": round(sum(v) / len(v), 2) if v else 0,
                "pass_count": sum(1 for x in v if x >= 4),
                "fail_count": sum(1 for x in v if x <= 2),
            }
            for k, v in sorted(data.items())
        }

    return {
        "summary": {
            "total": total,
            "avg_score": avg_score,
            "pass_count": verdict_counter.get("pass", 0),
            "warn_count": verdict_counter.get("warn", 0),
            "fail_count": verdict_counter.get("fail", 0),
        },
        "low_score_samples": low_score_samples,
        "common_issues": common_issues,
        "per_source_type": group_stats(by_source),
        "per_question_type": group_stats(by_question),
        "results": [r.model_dump() for r in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="对 RAG 回答自动评分")
    parser.add_argument("--dataset", required=True, help="评测集 JSONL 路径")
    parser.add_argument("--rag-report", required=True, help="RAG 评测报告 JSON 路径")
    parser.add_argument("--output", default="evals/reports/tcm_judged_report.json", help="评分报告输出路径")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数（默认 5）")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    report_path = Path(args.rag_report)
    output_path = Path(args.output)

    for p, desc in [(dataset_path, "评测集"), (report_path, "RAG 报告")]:
        if not p.exists():
            print(f"错误：{desc}文件不存在: {p}", file=sys.stderr)
            sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("加载评测集...")
    samples = load_dataset(dataset_path)
    print(f"共 {len(samples)} 条样本")

    print("加载 RAG 报告...")
    rag_results = load_rag_report(report_path)

    # 断点续跑
    existing = load_existing_judged(output_path)
    if existing:
        print(f"检测到已有 {len(existing)} 条评分结果，将断点续跑")

    client = EvalLLMClient()

    judge_results = asyncio.run(
        run_judging(
            client=client,
            samples=samples,
            rag_results=rag_results,
            existing=existing,
            concurrency=args.concurrency,
        )
    )

    report = build_judged_report(judge_results, samples)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    s = report["summary"]
    print(f"\n评分完成:")
    print(f"  总样本: {s['total']}")
    print(f"  平均分: {s['avg_score']}")
    print(f"  通过: {s['pass_count']}")
    print(f"  警告: {s['warn_count']}")
    print(f"  失败: {s['fail_count']}")
    print(f"\n报告已写入: {output_path}")


if __name__ == "__main__":
    main()
