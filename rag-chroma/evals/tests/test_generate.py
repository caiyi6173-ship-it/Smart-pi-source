"""generate_eval_set.py 辅助函数测试。"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

EVALS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVALS_ROOT))

from scripts.generate_eval_set import (
    build_difficulty_queue,
    is_duplicate,
    load_existing_ids,
    load_existing_questions,
    parse_difficulty_ratio,
    text_similarity,
)


class TestTextSimilarity:
    def test_identical(self):
        assert text_similarity("你好世界", "你好世界") == 1.0

    def test_completely_different(self):
        sim = text_similarity("abc", "xyz")
        assert sim == 0.0

    def test_empty(self):
        assert text_similarity("", "abc") == 0.0
        assert text_similarity("abc", "") == 0.0
        assert text_similarity("", "") == 0.0

    def test_partial(self):
        sim = text_similarity("舌苔黄腻", "舌苔白腻")
        assert 0 < sim < 1


class TestIsDuplicate:
    def test_duplicate(self):
        existing = ["舌苔黄腻通常提示什么？", "什么是阴阳五行？"]
        assert is_duplicate("舌苔黄腻通常提示什么？", existing) is True

    def test_not_duplicate(self):
        existing = ["舌苔黄腻通常提示什么？", "什么是阴阳五行？"]
        assert is_duplicate("脾胃虚寒如何调理？", existing) is False

    def test_near_duplicate(self):
        existing = ["舌苔黄腻通常提示什么疾病？"]
        assert is_duplicate("舌苔黄腻通常提示什么病症？", existing, threshold=0.85) is True

    def test_empty_existing(self):
        assert is_duplicate("任何问题", []) is False


class TestParseDifficultyRatio:
    def test_valid(self):
        r = parse_difficulty_ratio("3:4:3")
        assert r == {"easy": 3, "medium": 4, "hard": 3}

    def test_invalid_format(self):
        with pytest.raises(SystemExit):
            parse_difficulty_ratio("3:4")

    def test_non_integer(self):
        with pytest.raises(SystemExit):
            parse_difficulty_ratio("a:b:c")

    def test_all_zero(self):
        with pytest.raises(SystemExit):
            parse_difficulty_ratio("0:0:0")


class TestBuildDifficultyQueue:
    def test_length(self):
        queue = build_difficulty_queue(100, {"easy": 3, "medium": 4, "hard": 3})
        assert len(queue) == 100

    def test_distribution(self):
        queue = build_difficulty_queue(100, {"easy": 3, "medium": 4, "hard": 3})
        easy = queue.count("easy")
        medium = queue.count("medium")
        hard = queue.count("hard")
        # 允许 ±1 的误差（因为 round）
        assert 29 <= easy <= 31
        assert 39 <= medium <= 41
        assert 29 <= hard <= 31

    def test_contains_all(self):
        queue = build_difficulty_queue(10, {"easy": 1, "medium": 1, "hard": 1})
        assert "easy" in queue
        assert "medium" in queue
        assert "hard" in queue


class TestLoadExisting:
    def test_load_ids(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text(
            '{"id": "eval_aaa", "question": "q1"}\n'
            '{"id": "eval_bbb", "question": "q2"}\n'
            '{"bad json\n'
            '{"id": "eval_ccc", "question": "q3"}\n',
            encoding="utf-8",
        )
        ids = load_existing_ids(f)
        assert ids == {"eval_aaa", "eval_bbb", "eval_ccc"}

    def test_load_ids_missing_file(self, tmp_path):
        f = tmp_path / "nonexistent.jsonl"
        assert load_existing_ids(f) == set()

    def test_load_questions(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text(
            '{"id": "eval_aaa", "question": "问题一"}\n'
            '{"id": "eval_bbb", "question": "问题二"}\n',
            encoding="utf-8",
        )
        qs = load_existing_questions(f)
        assert qs == ["问题一", "问题二"]

    def test_load_questions_missing_file(self, tmp_path):
        f = tmp_path / "nonexistent.jsonl"
        assert load_existing_questions(f) == []
