"""分析评测集质量，输出质量报告。

用法：
    python evals/scripts/quality_report.py \
        --dataset evals/datasets/tcm_eval.jsonl \
        --output evals/reports/quality_report.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load_samples(path: Path) -> list[dict]:
    samples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return samples


def text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def find_near_duplicates(samples: list[dict], threshold: float = 0.85) -> list[dict]:
    """找出近似重复的问题对。"""
    duplicates = []
    questions = [(i, s.get("question", "")) for i, s in enumerate(samples)]
    for i in range(len(questions)):
        for j in range(i + 1, len(questions)):
            sim = text_similarity(questions[i][1], questions[j][1])
            if sim >= threshold:
                duplicates.append({
                    "index_a": i,
                    "index_b": j,
                    "similarity": round(sim, 3),
                    "question_a": questions[i][1][:100],
                    "question_b": questions[j][1][:100],
                })
    return duplicates


def analyze_chunk_coverage(samples: list[dict]) -> dict:
    """分析 chunk 使用覆盖率。"""
    used_chunk_ids: set[str] = set()
    chunk_usage: Counter[str] = Counter()
    for s in samples:
        for ev in s.get("evidence", []):
            cid = ev.get("chunk_id", "")
            if cid:
                used_chunk_ids.add(cid)
                chunk_usage[cid] += 1

    # 使用频率分布
    freq_dist: Counter[int] = Counter()
    for count in chunk_usage.values():
        freq_dist[count] += 1

    return {
        "unique_chunks_used": len(used_chunk_ids),
        "total_evidence_refs": sum(chunk_usage.values()),
        "usage_frequency_distribution": dict(sorted(freq_dist.items())),
        "most_used_chunks": [
            {"chunk_id": cid, "count": cnt}
            for cid, cnt in chunk_usage.most_common(10)
        ],
    }


def analyze_distributions(samples: list[dict]) -> dict:
    """分析各维度分布。"""
    difficulty: Counter[str] = Counter()
    question_type: Counter[str] = Counter()
    source_type: Counter[str] = Counter()
    safety_required = 0
    has_distractors = 0
    distractor_counts: Counter[int] = Counter()

    for s in samples:
        meta = s.get("metadata", {})
        difficulty[meta.get("difficulty", "unknown")] += 1
        question_type[s.get("question_type", "unknown")] += 1
        source_type[s.get("source_type", "unknown")] += 1

        rubric = s.get("rubric", {})
        if rubric.get("safety_required"):
            safety_required += 1

        dist = s.get("distractors", [])
        if dist:
            has_distractors += 1
            distractor_counts[len(dist)] += 1

    return {
        "difficulty": dict(sorted(difficulty.items())),
        "question_type": dict(sorted(question_type.items())),
        "source_type": dict(sorted(source_type.items())),
        "safety_required_count": safety_required,
        "has_distractors_count": has_distractors,
        "distractor_count_distribution": dict(sorted(distractor_counts.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="分析评测集质量")
    parser.add_argument("--dataset", required=True, help="评测集 JSONL 路径")
    parser.add_argument("--output", default="evals/reports/quality_report.json", help="报告输出路径")
    parser.add_argument("--dup-threshold", type=float, default=0.85, help="去重相似度阈值（默认 0.85）")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"错误：文件不存在: {dataset_path}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"加载评测集: {dataset_path}")
    samples = load_samples(dataset_path)
    if not samples:
        print("错误：评测集为空", file=sys.stderr)
        sys.exit(1)
    print(f"共 {len(samples)} 条样本")

    print("分析分布...")
    distributions = analyze_distributions(samples)

    print("分析 chunk 覆盖率...")
    coverage = analyze_chunk_coverage(samples)

    print(f"检查近似重复 (阈值={args.dup_threshold})...")
    duplicates = find_near_duplicates(samples, args.dup_threshold)

    report = {
        "total_samples": len(samples),
        "distributions": distributions,
        "chunk_coverage": coverage,
        "near_duplicates": {
            "threshold": args.dup_threshold,
            "count": len(duplicates),
            "pairs": duplicates[:50],  # 最多输出 50 对
        },
    }

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 打印摘要
    d = distributions
    print(f"\n=== 质量报告 ===")
    print(f"总样本: {len(samples)}")
    print(f"\n难度: {d['difficulty']}")
    print(f"类型: {d['question_type']}")
    print(f"来源: {d['source_type']}")
    print(f"安全要求: {d['safety_required_count']} 条")
    print(f"\nChunk 覆盖: {coverage['unique_chunks_used']} 个独立 chunk 被使用")
    print(f"近似重复: {len(duplicates)} 对")
    if duplicates:
        print("  前 5 对:")
        for p in duplicates[:5]:
            print(f"    [{p['similarity']}] {p['question_a'][:50]}... <-> {p['question_b'][:50]}...")

    print(f"\n报告已写入: {output_path}")


if __name__ == "__main__":
    main()
