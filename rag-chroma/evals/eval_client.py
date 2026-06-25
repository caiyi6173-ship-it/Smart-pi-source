"""OpenAI-compatible 评测 LLM 客户端，带重试和速率限制。"""

import json
import os
import sys
import time
from typing import Any

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

load_dotenv()


class EvalLLMClient:
    """封装 OpenAI-compatible chat completions，要求模型输出 JSON。"""

    def __init__(self) -> None:
        base_url = os.getenv("EVAL_LLM_BASE_URL")
        api_key = os.getenv("EVAL_LLM_API_KEY")
        model = os.getenv("EVAL_LLM_MODEL")
        self.temperature = float(os.getenv("EVAL_LLM_TEMPERATURE", "0.2"))
        self.timeout = int(os.getenv("EVAL_LLM_TIMEOUT_SECONDS", "60"))
        self.max_retries = int(os.getenv("EVAL_LLM_MAX_RETRIES", "3"))
        self.min_interval = float(os.getenv("EVAL_LLM_MIN_INTERVAL", "0.5"))

        if not api_key:
            print("错误：未设置 EVAL_LLM_API_KEY，请在 .env 中配置。", file=sys.stderr)
            sys.exit(1)
        if not model:
            print("错误：未设置 EVAL_LLM_MODEL，请在 .env 中配置。", file=sys.stderr)
            sys.exit(1)

        self.model = model
        self.client = OpenAI(
            base_url=base_url or "https://api.openai.com/v1",
            api_key=api_key,
            timeout=self.timeout,
        )
        self._last_call_time: float = 0.0

    def _rate_limit(self) -> None:
        """简单的速率限制：确保两次调用间隔不低于 min_interval。"""
        elapsed = time.monotonic() - self._last_call_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call_time = time.monotonic()

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        """调用 LLM 并要求返回 JSON。带指数退避重试。

        可重试错误：网络连接、超时、429 速率限制。
        不可重试错误：400 参数错误、JSON 解析失败（会重试一次后放弃）。
        """
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            self._rate_limit()
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                content = response.choices[0].message.content or ""
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    # JSON 解析失败，如果是最后一次尝试则抛出，否则重试
                    last_error = ValueError(f"LLM 返回的不是合法 JSON:\n{content[:500]}")
                    if attempt == self.max_retries:
                        raise last_error from e
                    # 可能是模型输出不完整，重试
                    wait = 2 ** attempt
                    print(f"  JSON 解析失败，{wait}s 后重试 ({attempt}/{self.max_retries})", file=sys.stderr)
                    time.sleep(wait)
                    continue

            except (APIConnectionError, APITimeoutError) as e:
                last_error = e
                wait = 2 ** attempt
                print(f"  网络错误: {e}，{wait}s 后重试 ({attempt}/{self.max_retries})", file=sys.stderr)
                time.sleep(wait)
                continue

            except RateLimitError as e:
                last_error = e
                wait = min(2 ** attempt * 2, 30)  # 429 等更久
                print(f"  速率限制: {e}，{wait}s 后重试 ({attempt}/{self.max_retries})", file=sys.stderr)
                time.sleep(wait)
                continue

            except Exception as e:
                # 其他错误（如 400）不重试
                raise e

        # 理论上不会到这里，但防御性编程
        raise last_error or RuntimeError("未知错误")
