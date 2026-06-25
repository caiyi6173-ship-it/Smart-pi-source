"""schemas.py 测试。"""

import json
import pytest
from pathlib import Path
import sys

EVALS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVALS_ROOT))

from schemas import (
    EvalEvidence,
    EvalMetadata,
    EvalRubric,
    EvalSample,
    JudgeResult,
    RagEvalResult,
)


class TestEvalEvidence:
    def test_valid(self):
        ev = EvalEvidence(
            document_id="doc1",
            chunk_id="chunk1",
            title="测试",
            source_id="src1",
            source_type="modern_basics",
            text="这是文本",
        )
        assert ev.document_id == "doc1"

    def test_missing_field(self):
        with pytest.raises(Exception):
            EvalEvidence(document_id="doc1", chunk_id="chunk1")


class TestEvalRubric:
    def test_defaults(self):
        r = EvalRubric()
        assert r.must_include == []
        assert r.citation_required is True
        assert r.safety_required is False

    def test_custom(self):
        r = EvalRubric(
            must_include=["要点1"],
            must_not_include=["错误1"],
            safety_required=True,
        )
        assert r.safety_required is True


class TestEvalSample:
    VALID_SAMPLE = {
        "id": "eval_abc123",
        "question": "舌苔黄腻通常提示什么？",
        "question_type": "knowledge",
        "source_type": "modern_basics",
        "expected_answer": "湿热内蕴",
        "wrong_answer": "阴虚火旺",
        "distractors": ["气滞血瘀", "脾肾阳虚"],
        "rubric": {
            "must_include": ["湿热"],
            "must_not_include": ["阴虚"],
            "citation_required": True,
            "safety_required": False,
        },
        "evidence": [
            {
                "document_id": "doc1",
                "chunk_id": "chunk1",
                "title": "舌诊",
                "source_id": "src1",
                "source_type": "modern_basics",
                "text": "舌苔黄腻主湿热",
            }
        ],
    }

    def test_valid(self):
        s = EvalSample(**self.VALID_SAMPLE)
        assert s.id == "eval_abc123"
        assert s.question_type == "knowledge"
        assert len(s.evidence) == 1

    def test_invalid_id(self):
        data = {**self.VALID_SAMPLE, "id": "bad_id"}
        with pytest.raises(Exception):
            EvalSample(**data)

    def test_invalid_question_type(self):
        data = {**self.VALID_SAMPLE, "question_type": "invalid"}
        with pytest.raises(Exception):
            EvalSample(**data)

    def test_empty_question(self):
        data = {**self.VALID_SAMPLE, "question": ""}
        with pytest.raises(Exception):
            EvalSample(**data)

    def test_empty_evidence(self):
        data = {**self.VALID_SAMPLE, "evidence": []}
        with pytest.raises(Exception):
            EvalSample(**data)

    def test_empty_distractors(self):
        data = {**self.VALID_SAMPLE, "distractors": []}
        with pytest.raises(Exception):
            EvalSample(**data)

    def test_json_roundtrip(self):
        s = EvalSample(**self.VALID_SAMPLE)
        j = json.dumps(s.model_dump(), ensure_ascii=False)
        s2 = EvalSample(**json.loads(j))
        assert s.id == s2.id
        assert s.question == s2.question


class TestRagEvalResult:
    def test_valid(self):
        r = RagEvalResult(sample_id="eval_abc", question="test")
        assert r.latency_ms == 0
        assert r.no_answer is False

    def test_with_error(self):
        r = RagEvalResult(sample_id="eval_abc", question="test", error="timeout")
        assert r.error == "timeout"


class TestJudgeResult:
    def test_valid(self):
        j = JudgeResult(sample_id="eval_abc", score=4, verdict="pass")
        assert j.score == 4

    def test_invalid_score(self):
        with pytest.raises(Exception):
            JudgeResult(sample_id="eval_abc", score=6, verdict="pass")

    def test_invalid_verdict(self):
        with pytest.raises(Exception):
            JudgeResult(sample_id="eval_abc", score=4, verdict="invalid")

    def test_score_verdict_consistency(self):
        # schema 本身不强制一致性，但结构合法
        j = JudgeResult(sample_id="eval_abc", score=2, verdict="pass")
        assert j.score == 2  # 不一致但不报错，由 judge 脚本逻辑处理
