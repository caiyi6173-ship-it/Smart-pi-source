"""eval_client.py 测试（mock LLM 调用）。"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

EVALS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVALS_ROOT))


def _mock_openai_response(content: dict | str):
    """构造 mock 的 OpenAI 响应。"""
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


class TestEvalLLMClient:
    @patch.dict("os.environ", {
        "EVAL_LLM_API_KEY": "test-key",
        "EVAL_LLM_MODEL": "test-model",
        "EVAL_LLM_BASE_URL": "http://test.api/v1",
        "EVAL_LLM_MAX_RETRIES": "2",
        "EVAL_LLM_MIN_INTERVAL": "0",
    })
    def test_generate_json_success(self):
        from eval_client import EvalLLMClient
        client = EvalLLMClient()
        expected = {"key": "value"}
        client.client.chat.completions.create = MagicMock(
            return_value=_mock_openai_response(expected)
        )
        result = client.generate_json("system", "user")
        assert result == expected

    @patch.dict("os.environ", {
        "EVAL_LLM_API_KEY": "test-key",
        "EVAL_LLM_MODEL": "test-model",
        "EVAL_LLM_BASE_URL": "http://test.api/v1",
        "EVAL_LLM_MAX_RETRIES": "2",
        "EVAL_LLM_MIN_INTERVAL": "0",
    })
    def test_generate_json_invalid_json_retries(self):
        from eval_client import EvalLLMClient
        from openai import APIConnectionError
        client = EvalLLMClient()
        # 第一次返回非法 JSON，第二次成功
        client.client.chat.completions.create = MagicMock(
            side_effect=[
                _mock_openai_response("not json at all"),
                _mock_openai_response({"ok": True}),
            ]
        )
        result = client.generate_json("system", "user")
        assert result == {"ok": True}

    @patch.dict("os.environ", {
        "EVAL_LLM_API_KEY": "test-key",
        "EVAL_LLM_MODEL": "test-model",
        "EVAL_LLM_BASE_URL": "http://test.api/v1",
        "EVAL_LLM_MAX_RETRIES": "2",
        "EVAL_LLM_MIN_INTERVAL": "0",
    })
    def test_generate_json_all_retries_fail(self):
        from eval_client import EvalLLMClient
        client = EvalLLMClient()
        client.client.chat.completions.create = MagicMock(
            return_value=_mock_openai_response("not json")
        )
        with pytest.raises(ValueError, match="不是合法 JSON"):
            client.generate_json("system", "user")

    @patch.dict("os.environ", {
        "EVAL_LLM_API_KEY": "",
        "EVAL_LLM_MODEL": "test-model",
    })
    def test_missing_api_key_exits(self):
        with pytest.raises(SystemExit):
            from eval_client import EvalLLMClient
            EvalLLMClient()

    @patch.dict("os.environ", {
        "EVAL_LLM_API_KEY": "test-key",
        "EVAL_LLM_MODEL": "",
    })
    def test_missing_model_exits(self):
        with pytest.raises(SystemExit):
            from eval_client import EvalLLMClient
            EvalLLMClient()
