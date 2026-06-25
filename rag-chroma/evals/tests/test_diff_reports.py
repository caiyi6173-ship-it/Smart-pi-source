"""diff_reports.py 测试。"""

import sys
from pathlib import Path

import pytest

EVALS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVALS_ROOT))

from scripts.diff_reports import diff_judged_reports, diff_rag_reports


def _make_rag_report(sample_ids: list[str], **overrides) -> dict:
    """构造测试用 RAG 报告。"""
    results = []
    for sid in sample_ids:
        r = {
            "sample_id": sid,
            "question": f"question_{sid}",
            "rag_answer": "answer",
            "latency_ms": 100,
            "no_answer": False,
            "error": None,
        }
        r.update(overrides)
        results.append(r)
    return {
        "summary": {
            "total_samples": len(results),
            "errors": sum(1 for r in results if r.get("error")),
            "has_answer_count": sum(1 for r in results if not r.get("no_answer") and not r.get("error")),
            "no_answer_count": sum(1 for r in results if r.get("no_answer")),
            "avg_latency_ms": 100,
            "citation_hit_rate": 0.5,
            "evidence_hit_rate": 0.6,
        },
        "per_question_type": {},
        "results": results,
    }


def _make_judged_report(sample_ids: list[str], **overrides) -> dict:
    """构造测试用评分报告。"""
    results = []
    for sid in sample_ids:
        r = {
            "sample_id": sid,
            "score": 4,
            "verdict": "pass",
            "issues": [],
            "error": None,
        }
        r.update(overrides)
        results.append(r)
    return {
        "summary": {
            "total": len(results),
            "avg_score": 4.0,
            "pass_count": len(results),
            "warn_count": 0,
            "fail_count": 0,
        },
        "per_source_type": {},
        "per_question_type": {},
        "results": results,
    }


class TestDiffRagReports:
    def test_identical(self):
        r = _make_rag_report(["a", "b", "c"])
        diff = diff_rag_reports(r, r)
        s = diff["summary_diff"]
        assert s["total_samples"]["delta"] == 0
        assert s["avg_latency_ms"]["delta"] == 0

    def test_regression(self):
        baseline = _make_rag_report(["a", "b", "c"])
        current = _make_rag_report(["a", "b", "c"], no_answer=True)
        diff = diff_rag_reports(baseline, current)
        assert diff["summary_diff"]["no_answer_count"]["delta"] == 3

    def test_new_samples(self):
        baseline = _make_rag_report(["a", "b"])
        current = _make_rag_report(["a", "b", "c", "d"])
        diff = diff_rag_reports(baseline, current)
        assert diff["sample_changes"]["new_count"] == 2
        assert diff["sample_changes"]["lost_count"] == 0

    def test_lost_samples(self):
        baseline = _make_rag_report(["a", "b", "c"])
        current = _make_rag_report(["a"])
        diff = diff_rag_reports(baseline, current)
        assert diff["sample_changes"]["lost_count"] == 2


class TestDiffJudgedReports:
    def test_identical(self):
        r = _make_judged_report(["a", "b"])
        diff = diff_judged_reports(r, r)
        assert diff["summary_diff"]["avg_score"]["delta"] == 0
        assert diff["score_changes"]["improved_count"] == 0
        assert diff["score_changes"]["degraded_count"] == 0

    def test_improvement(self):
        baseline = _make_judged_report(["a"], score=2, verdict="fail")
        current = _make_judged_report(["a"], score=4, verdict="pass")
        diff = diff_judged_reports(baseline, current)
        assert diff["score_changes"]["improved_count"] == 1
        assert diff["score_changes"]["degraded_count"] == 0

    def test_degradation(self):
        baseline = _make_judged_report(["a"], score=4, verdict="pass")
        current = _make_judged_report(["a"], score=1, verdict="fail")
        diff = diff_judged_reports(baseline, current)
        assert diff["score_changes"]["degraded_count"] == 1
        assert diff["new_failures"]["count"] == 1

    def test_verdict_change(self):
        baseline = _make_judged_report(["a"], score=4, verdict="pass")
        current = _make_judged_report(["a"], score=3, verdict="warn")
        diff = diff_judged_reports(baseline, current)
        assert diff["verdict_changes"]["count"] == 1
