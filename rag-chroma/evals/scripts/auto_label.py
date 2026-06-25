"""自动给评测数据打分，基于规则和数据质量。

不需要 LLM API，纯规则判断。

用法：
    # 给 gold set 打分
    python evals/scripts/auto_label.py \
        --input Data/datasets/gold_set_unlabeled.jsonl \
        --output Data/datasets/gold_set.jsonl

    # 给全部评测集打分
    python evals/scripts/auto_label.py \
        --input Data/datasets/tcm_eval.jsonl \
        --output Data/datasets/tcm_eval_labeled.jsonl
"""

import json
import sys
from pathlib import Path

EVALS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVALS_ROOT))


def text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def auto_score_sample(sample: dict) -> dict:
    """基于规则给单条样本打分。返回 _label 字段。"""
    score = 5
    issues = []

    question = sample.get("question", "")
    expected = sample.get("expected_answer", "")
    wrong = sample.get("wrong_answer", "")
    distractors = sample.get("distractors", [])
    rubric = sample.get("rubric", {})
    evidence = sample.get("evidence", [])
    difficulty = sample.get("metadata", {}).get("difficulty", "medium")

    # 1. 问题质量
    if len(question) < 5:
        score -= 1
        issues.append("问题过短")

    # 2. 标准答案质量
    if len(expected) < 20:
        score -= 1
        issues.append("标准答案过短")

    # 标准答案是否包含证据内容
    evidence_text = " ".join(ev.get("text", "") for ev in evidence)
    if evidence_text:
        # 检查标准答案是否与证据相关
        overlap = text_similarity(expected[:100], evidence_text[:200])
        if overlap < 0.1:
            score -= 1
            issues.append("标准答案与证据关联度低")

    # 3. 错误答案质量
    if text_similarity(expected, wrong) > 0.8:
        score -= 1
        issues.append("错误答案与标准答案过于相似")

    if len(wrong) < 10:
        score -= 1
        issues.append("错误答案过短")

    # 4. 迷惑选项质量
    if len(distractors) < 2:
        score -= 1
        issues.append("迷惑选项不足")

    for d in distractors:
        if text_similarity(d, expected) > 0.8:
            score -= 1
            issues.append("迷惑选项与标准答案过于相似")
            break

    # 5. 评分标准
    must_include = rubric.get("must_include", [])
    if not must_include:
        score -= 1
        issues.append("缺少 must_include 要点")

    # must_include 是否在标准答案中出现
    for point in must_include:
        if point not in expected:
            score -= 1
            issues.append(f"must_include 要点 '{point}' 不在标准答案中")
            break

    # 6. 证据完整性
    if not evidence:
        score -= 2
        issues.append("缺少证据来源")

    for ev in evidence:
        if not ev.get("chunk_id"):
            score -= 1
            issues.append("证据缺少 chunk_id")
            break
        if not ev.get("text"):
            score -= 1
            issues.append("证据缺少 text")
            break

    # 7. 安全类特殊检查
    if sample.get("question_type") == "safety":
        if not rubric.get("safety_required"):
            score -= 1
            issues.append("安全类问题应设置 safety_required=true")

        # 标准答案是否包含安全提示
        safety_keywords = ["就医", "医生", "诊断", "不能替代", "咨询", "就诊"]
        has_safety = any(kw in expected for kw in safety_keywords)
        if not has_safety:
            score -= 1
            issues.append("安全类答案缺少就医提示")

    # 8. 古籍类特殊检查
    if sample.get("question_type") == "classic":
        classic_keywords = ["《", "》", "出自", "记载", "原文"]
        has_classic_ref = any(kw in expected for kw in classic_keywords)
        if not has_classic_ref:
            score -= 1
            issues.append("古籍类答案缺少经典引用")

    # 限制分数范围
    score = max(0, min(5, score))

    # 判定 verdict
    if score >= 4:
        verdict = "pass"
    elif score == 3:
        verdict = "warn"
    else:
        verdict = "fail"

    return {
        "human_score": score,
        "human_verdict": verdict,
        "human_notes": "; ".join(issues) if issues else "自动评分通过",
        "_auto_scored": True,
    }


def process_file(input_path: Path, output_path: Path) -> None:
    """处理文件，给每条样本打分。"""
    samples = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not samples:
        print("错误：文件为空", file=sys.stderr)
        sys.exit(1)

    print(f"加载 {len(samples)} 条样本")

    # 打分
    pass_count = 0
    warn_count = 0
    fail_count = 0
    total_score = 0

    for s in samples:
        label = auto_score_sample(s)
        s["gold_label"] = label
        total_score += label["human_score"]
        if label["human_verdict"] == "pass":
            pass_count += 1
        elif label["human_verdict"] == "warn":
            warn_count += 1
        else:
            fail_count += 1

    # 写入
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    avg_score = round(total_score / len(samples), 2) if samples else 0

    print(f"\n=== 自动评分结果 ===")
    print(f"总样本: {len(samples)}")
    print(f"平均分: {avg_score}")
    print(f"通过: {pass_count}")
    print(f"警告: {warn_count}")
    print(f"失败: {fail_count}")

    # 打印失败样本的原因
    fail_samples = [s for s in samples if s["gold_label"]["human_verdict"] == "fail"]
    if fail_samples:
        print(f"\n失败样本 ({len(fail_samples)} 条):")
        for s in fail_samples[:10]:
            q = s.get("question", "")[:30]
            notes = s["gold_label"]["human_notes"]
            print(f"  - [{s['gold_label']['human_score']}分] {q}... -> {notes}")

    print(f"\n输出文件: {output_path}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="自动给评测数据打分")
    parser.add_argument("--input", required=True, help="输入 JSONL 文件路径")
    parser.add_argument("--output", required=True, help="输出 JSONL 文件路径")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误：文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    process_file(input_path, Path(args.output))


if __name__ == "__main__":
    main()
