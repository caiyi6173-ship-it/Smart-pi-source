"""从评测集中抽取样本创建人工标注的 gold set。

从已有评测集中随机抽取 N 条，生成待标注文件。
人工标注后生成 gold_set.jsonl，用于校准自动评分。

用法：
    # 第一步：抽取待标注样本
    python evals/scripts/create_gold_set.py \
        --dataset evals/datasets/tcm_eval.jsonl \
        --sample 50 \
        --output evals/datasets/gold_set_unlabeled.jsonl

    # 第二步：人工编辑 gold_set_unlabeled.jsonl，填写 human_score (0-5) 和 human_verdict (pass/warn/fail)

    # 第三步：验证标注文件
    python evals/scripts/create_gold_set.py \
        --validate evals/datasets/gold_set_unlabeled.jsonl \
        --output evals/datasets/gold_set.jsonl
"""

import argparse
import json
import random
import sys
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


def create_unlabeled(dataset_path: Path, n: int, output_path: Path) -> None:
    """从评测集抽取 N 条待标注样本。"""
    samples = load_samples(dataset_path)
    if not samples:
        print("错误：评测集为空", file=sys.stderr)
        sys.exit(1)

    n = min(n, len(samples))
    selected = random.sample(samples, n)

    # 添加待标注字段
    for s in selected:
        s["_label"] = {
            "human_score": None,  # 0-5
            "human_verdict": None,  # pass/warn/fail
            "human_notes": "",  # 标注备注
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for s in selected:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"已抽取 {n} 条待标注样本写入 {output_path}")
    print(f"\n请人工编辑该文件，填写 _label 中的三个字段：")
    print(f"  human_score: 0-5 整数")
    print(f"  human_verdict: pass / warn / fail")
    print(f"  human_notes: 备注（可选）")
    print(f"\n编辑完成后运行：")
    print(f"  python evals/scripts/create_gold_set.py --validate {output_path} --output evals/datasets/gold_set.jsonl")


def validate_and_finalize(unlabeled_path: Path, output_path: Path) -> None:
    """验证标注文件并生成最终 gold set。"""
    samples = load_samples(unlabeled_path)
    if not samples:
        print("错误：文件为空", file=sys.stderr)
        sys.exit(1)

    valid = 0
    invalid = 0
    finalized = []

    for i, s in enumerate(samples, 1):
        label = s.pop("_label", None)
        if not label:
            print(f"  第 {i} 条：缺少 _label 字段，跳过", file=sys.stderr)
            invalid += 1
            continue

        score = label.get("human_score")
        verdict = label.get("human_verdict")

        # 校验
        errors = []
        if score is None:
            errors.append("human_score 为空")
        elif not isinstance(score, int) or score < 0 or score > 5:
            errors.append(f"human_score 必须为 0-5 整数，实际为 {score}")

        if verdict not in ("pass", "warn", "fail"):
            errors.append(f"human_verdict 必须为 pass/warn/fail，实际为 {verdict}")

        # score 和 verdict 一致性
        if score is not None and verdict is not None:
            expected_verdict = "pass" if score >= 4 else ("warn" if score == 3 else "fail")
            if verdict != expected_verdict:
                errors.append(f"score={score} 对应 verdict 应为 {expected_verdict}，实际为 {verdict}")

        if errors:
            print(f"  第 {i} 条 ({s.get('id', '?')}): {'; '.join(errors)}", file=sys.stderr)
            invalid += 1
            continue

        s["gold_label"] = {
            "human_score": score,
            "human_verdict": verdict,
            "human_notes": label.get("human_notes", ""),
        }
        finalized.append(s)
        valid += 1

    if not finalized:
        print("错误：无有效标注", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for s in finalized:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\n验证完成: {valid} 条有效, {invalid} 条无效")
    print(f"Gold set 写入: {output_path}")

    # 打印标注分布
    scores = [s["gold_label"]["human_score"] for s in finalized]
    avg = round(sum(scores) / len(scores), 2)
    from collections import Counter
    verdict_dist = Counter(s["gold_label"]["human_verdict"] for s in finalized)
    print(f"\n标注分布:")
    print(f"  平均分: {avg}")
    print(f"  verdict: {dict(verdict_dist)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="创建/验证人工标注 gold set")
    parser.add_argument("--dataset", help="评测集 JSONL 路径（抽取模式）")
    parser.add_argument("--sample", type=int, default=50, help="抽取数量（默认 50）")
    parser.add_argument("--validate", help="待标注文件路径（验证模式）")
    parser.add_argument("--output", required=True, help="输出路径")
    args = parser.parse_args()

    output_path = Path(args.output)

    if args.validate:
        # 验证模式
        validate_and_finalize(Path(args.validate), output_path)
    elif args.dataset:
        # 抽取模式
        create_unlabeled(Path(args.dataset), args.sample, output_path)
    else:
        print("错误：需要 --dataset（抽取模式）或 --validate（验证模式）", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
