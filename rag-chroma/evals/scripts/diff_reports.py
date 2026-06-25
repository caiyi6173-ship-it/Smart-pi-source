"""对比两份评测报告，输出变化趋势。

用于 CI 门禁和版本间效果回归检测。

用法：
    # 对比两份 RAG 评测报告
    python evals/scripts/diff_reports.py \
        --baseline evals/reports/tcm_eval_report_v1.json \
        --current evals/reports/tcm_eval_report_v2.json

    # 对比两份评分报告
    python evals/scripts/diff_reports.py \
        --baseline evals/reports/tcm_judged_report_v1.json \
        --current evals/reports/tcm_judged_report_v2.json \
        --type judged

    # CI 门禁模式：平均分低于阈值则 exit 1
    python evals/scripts/diff_reports.py \
        --baseline evals/reports/tcm_judged_report_v1.json \
        --current evals/reports/tcm_judged_report_v2.json \
        --type judged \
        --gate-min-score 3.5
"""

import argparse
import json
import sys
from pathlib import Path


def load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def diff_rag_reports(baseline: dict, current: dict) -> dict:
    """对比两份 RAG 评测报告。"""
    b = baseline.get("summary", {})
    c = current.get("summary", {})

    def delta(key: str) -> dict:
        bv = b.get(key, 0)
        cv = c.get(key, 0)
        if isinstance(bv, (int, float)) and isinstance(cv, (int, float)):
            d = cv - bv
            pct = round(d / bv * 100, 1) if bv else 0
            return {"baseline": bv, "current": cv, "delta": d, "delta_pct": pct}
        return {"baseline": bv, "current": cv}

    # 按 question_type 对比
    b_types = baseline.get("per_question_type", {})
    c_types = current.get("per_question_type", {})
    all_types = sorted(set(b_types) | set(c_types))
    type_diff = {}
    for qt in all_types:
        bt = b_types.get(qt, {})
        ct = c_types.get(qt, {})
        type_diff[qt] = {
            "baseline_count": bt.get("count", 0),
            "current_count": ct.get("count", 0),
            "baseline_avg_latency": bt.get("avg_latency_ms", 0),
            "current_avg_latency": ct.get("avg_latency_ms", 0),
        }

    # 找出新增和丢失的 sample_id
    b_ids = {r["sample_id"] for r in baseline.get("results", [])}
    c_ids = {r["sample_id"] for r in current.get("results", [])}
    new_ids = c_ids - b_ids
    lost_ids = b_ids - c_ids
    common_ids = b_ids & c_ids

    # 对比共有样本的具体变化
    b_map = {r["sample_id"]: r for r in baseline.get("results", [])}
    c_map = {r["sample_id"]: r for r in current.get("results", [])}
    changed_samples = []
    for sid in sorted(common_ids):
        br = b_map[sid]
        cr = c_map[sid]
        changes = {}
        if br.get("no_answer") != cr.get("no_answer"):
            changes["no_answer"] = {"baseline": br.get("no_answer"), "current": cr.get("no_answer")}
        if br.get("error") != cr.get("error"):
            changes["error"] = {"baseline": br.get("error"), "current": cr.get("error")}
        bl = br.get("latency_ms", 0)
        cl = cr.get("latency_ms", 0)
        if abs(bl - cl) > 500:  # 延迟变化超过 500ms 才记录
            changes["latency_ms"] = {"baseline": bl, "current": cl}
        if changes:
            changed_samples.append({"sample_id": sid, "changes": changes})

    return {
        "summary_diff": {
            "total_samples": delta("total_samples"),
            "errors": delta("errors"),
            "has_answer_count": delta("has_answer_count"),
            "no_answer_count": delta("no_answer_count"),
            "avg_latency_ms": delta("avg_latency_ms"),
            "citation_hit_rate": delta("citation_hit_rate"),
            "evidence_hit_rate": delta("evidence_hit_rate"),
        },
        "per_question_type": type_diff,
        "sample_changes": {
            "new_count": len(new_ids),
            "lost_count": len(lost_ids),
            "changed_count": len(changed_samples),
            "new_ids": sorted(new_ids)[:20],
            "lost_ids": sorted(lost_ids)[:20],
            "changed": changed_samples[:20],
        },
    }


def diff_judged_reports(baseline: dict, current: dict) -> dict:
    """对比两份评分报告。"""
    b = baseline.get("summary", {})
    c = current.get("summary", {})

    def delta(key: str) -> dict:
        bv = b.get(key, 0)
        cv = c.get(key, 0)
        if isinstance(bv, (int, float)) and isinstance(cv, (int, float)):
            d = cv - bv
            pct = round(d / bv * 100, 1) if bv else 0
            return {"baseline": bv, "current": cv, "delta": d, "delta_pct": pct}
        return {"baseline": bv, "current": cv}

    # 按 source_type 对比
    b_src = baseline.get("per_source_type", {})
    c_src = current.get("per_source_type", {})
    all_src = sorted(set(b_src) | set(c_src))
    src_diff = {}
    for st in all_src:
        bs = b_src.get(st, {})
        cs = c_src.get(st, {})
        src_diff[st] = {
            "baseline_avg": bs.get("avg_score", 0),
            "current_avg": cs.get("avg_score", 0),
            "baseline_pass": bs.get("pass_count", 0),
            "current_pass": cs.get("pass_count", 0),
            "baseline_fail": bs.get("fail_count", 0),
            "current_fail": cs.get("fail_count", 0),
        }

    # 对比共有样本的评分变化
    b_map = {r["sample_id"]: r for r in baseline.get("results", [])}
    c_map = {r["sample_id"]: r for r in current.get("results", [])}
    common_ids = set(b_map) & set(c_map)

    score_changes = []
    verdict_changes = []
    improved = 0
    degraded = 0

    for sid in sorted(common_ids):
        bs = b_map[sid].get("score", 0)
        cs = c_map[sid].get("score", 0)
        bv = b_map[sid].get("verdict", "")
        cv = c_map[sid].get("verdict", "")

        if bs != cs:
            d = cs - bs
            score_changes.append({
                "sample_id": sid,
                "baseline_score": bs,
                "current_score": cs,
                "delta": d,
            })
            if d > 0:
                improved += 1
            else:
                degraded += 1

        if bv != cv:
            verdict_changes.append({
                "sample_id": sid,
                "baseline_verdict": bv,
                "current_verdict": cv,
            })

    # 找出新增失败的样本
    new_failures = []
    for sid in sorted(common_ids):
        bv = b_map[sid].get("verdict", "")
        cv = c_map[sid].get("verdict", "")
        if bv == "pass" and cv == "fail":
            new_failures.append({
                "sample_id": sid,
                "baseline_score": b_map[sid].get("score", 0),
                "current_score": c_map[sid].get("score", 0),
                "issues": c_map[sid].get("issues", []),
            })

    return {
        "summary_diff": {
            "total": delta("total"),
            "avg_score": delta("avg_score"),
            "pass_count": delta("pass_count"),
            "warn_count": delta("warn_count"),
            "fail_count": delta("fail_count"),
        },
        "per_source_type": src_diff,
        "score_changes": {
            "improved_count": improved,
            "degraded_count": degraded,
            "unchanged_count": len(common_ids) - len(score_changes),
            "samples": score_changes[:30],
        },
        "verdict_changes": {
            "count": len(verdict_changes),
            "samples": verdict_changes[:20],
        },
        "new_failures": {
            "count": len(new_failures),
            "samples": new_failures[:20],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="对比两份评测报告")
    parser.add_argument("--baseline", required=True, help="基线报告路径")
    parser.add_argument("--current", required=True, help="当前报告路径")
    parser.add_argument("--type", choices=["rag", "judged"], default="rag", help="报告类型（默认 rag）")
    parser.add_argument("--output", help="差异报告输出路径（可选）")
    parser.add_argument("--gate-min-score", type=float, help="CI 门禁：平均分低于此值则 exit 1（仅 judged 类型）")
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)

    for p, desc in [(baseline_path, "基线"), (current_path, "当前")]:
        if not p.exists():
            print(f"错误：{desc}报告不存在: {p}", file=sys.stderr)
            sys.exit(1)

    baseline = load_report(baseline_path)
    current = load_report(current_path)

    if args.type == "rag":
        diff = diff_rag_reports(baseline, current)
    else:
        diff = diff_judged_reports(baseline, current)

    diff["_meta"] = {
        "baseline": str(baseline_path),
        "current": str(current_path),
        "type": args.type,
    }

    # 输出
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"差异报告已写入: {output_path}")

    # 打印摘要
    print(f"\n=== 报告对比 ({args.type}) ===")
    print(f"基线: {baseline_path}")
    print(f"当前: {current_path}")

    summary = diff.get("summary_diff", {})
    for key, val in summary.items():
        if isinstance(val, dict) and "delta" in val:
            direction = "↑" if val["delta"] > 0 else ("↓" if val["delta"] < 0 else "→")
            pct = f" ({val['delta_pct']}%)" if "delta_pct" in val else ""
            print(f"  {key}: {val['baseline']} → {val['current']} {direction}{pct}")

    if args.type == "judged":
        sc = diff.get("score_changes", {})
        print(f"\n  评分提升: {sc.get('improved_count', 0)} 条")
        print(f"  评分下降: {sc.get('degraded_count', 0)} 条")
        nf = diff.get("new_failures", {})
        if nf.get("count", 0) > 0:
            print(f"  新增失败: {nf['count']} 条 ⚠️")

    # CI 门禁
    if args.gate_min_score is not None and args.type == "judged":
        current_avg = summary.get("avg_score", {}).get("current", 0)
        if current_avg < args.gate_min_score:
            print(f"\n❌ CI 门禁失败: 平均分 {current_avg} < 阈值 {args.gate_min_score}")
            sys.exit(1)
        else:
            print(f"\n✅ CI 门禁通过: 平均分 {current_avg} >= 阈值 {args.gate_min_score}")


if __name__ == "__main__":
    main()
