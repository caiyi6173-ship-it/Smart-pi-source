import logging
import re

from openai import OpenAI

from app.config import Settings
from app.generation.prompt import SAFETY_NOTICE, build_rag_messages
from app.schemas import Chunk

logger = logging.getLogger(__name__)


class AnswerGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        if settings.dashscope_api_key:
            self._client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url=settings.dashscope_base_url,
                timeout=settings.request_timeout_seconds,
            )

    @property
    def configured(self) -> bool:
        return self._client is not None

    def generate(self, question: str, chunks: list[Chunk], user_context: dict | None = None) -> str:
        if not chunks:
            return f"知识库未找到与“{question}”直接相关且达到可信阈值的依据，因此不生成推断性回答。\n\n{SAFETY_NOTICE}"

        if not self._client:
            snippets = "\n".join(f"- [{idx}] {chunk.text[:180]}" for idx, chunk in enumerate(chunks[:3], start=1))
            return f"开发模式占位回答：已检索到以下资料片段，可据此接入 Qwen3-max 生成正式回答。\n{snippets}\n\n{SAFETY_NOTICE}"

        try:
            response = self._client.chat.completions.create(
                model=self.settings.llm_model,
                messages=build_rag_messages(question, chunks, user_context),
                temperature=0.2,
            )
            answer = response.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("LLM API failed, falling back to offline placeholder answer: %s", exc)
            snippets = "\n".join(f"- [{idx}] {chunk.text[:180]}" for idx, chunk in enumerate(chunks[:3], start=1))
            answer = f"开发模式占位回答：在线大模型当前不可用，以下是已检索到的相关资料片段，可先用于人工核对。\n{snippets}"
        answer = _ensure_citation_markers(answer, chunks)
        if SAFETY_NOTICE not in answer:
            answer = f"{answer.rstrip()}\n\n{SAFETY_NOTICE}"
        return answer


def _ensure_citation_markers(answer: str, chunks: list[Chunk]) -> str:
    if not chunks or re.search(r"\[\d+\]", answer):
        return answer
    titles = []
    for idx, chunk in enumerate(chunks[:3], start=1):
        title = chunk.metadata.get("title", "未知来源")
        titles.append(f"[{idx}] {title}")
    return f"{answer.rstrip()}\n\n引用来源：{'; '.join(titles)}"
