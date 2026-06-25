"""评测数据结构定义。字段与 JSONL schema 保持一致。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class EvalEvidence(BaseModel):
    """单条证据来源，必须关联已有知识库 chunk。"""

    document_id: str
    chunk_id: str
    title: str
    source_id: str
    source_type: str
    text: str


class EvalRubric(BaseModel):
    """评分标准。"""

    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    citation_required: bool = True
    safety_required: bool = False


class EvalMetadata(BaseModel):
    """生成元数据。"""

    generated_by: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class EvalSample(BaseModel):
    """单条评测样本。"""

    id: str = Field(pattern=r"^eval_\w+$")
    question: str = Field(min_length=1)
    question_type: Literal["knowledge", "classic", "safety", "retrieval", "adversarial"]
    source_type: Literal["modern_basics", "classic_text", "safety_rule", "mixed"]
    expected_answer: str = Field(min_length=1)
    wrong_answer: str = Field(min_length=1)
    distractors: list[str] = Field(min_length=1)
    rubric: EvalRubric
    evidence: list[EvalEvidence] = Field(min_length=1)
    metadata: EvalMetadata = Field(default_factory=EvalMetadata)

    @model_validator(mode="after")
    def check_safety_rubric(self) -> "EvalSample":
        if self.rubric.safety_required and self.question_type != "safety":
            # safety_required 时 question_type 应为 safety，但不强制，只记录
            pass
        return self


class RagEvalResult(BaseModel):
    """RAG 评测单条结果。"""

    sample_id: str
    question: str
    rag_answer: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    no_answer: bool = False
    retrieval_strategy: str = ""
    rerank_provider: str = ""
    error: str | None = None


class JudgeResult(BaseModel):
    """单条评分结果。"""

    sample_id: str
    score: int = Field(ge=0, le=5)
    citation_score: int = Field(ge=0, le=1, default=0)
    faithfulness_score: int = Field(ge=0, le=1, default=0)
    safety_score: int = Field(ge=0, le=1, default=0)
    completeness_score: int = Field(ge=0, le=1, default=0)
    issues: list[str] = Field(default_factory=list)
    verdict: Literal["pass", "warn", "fail"] = "pass"
    error: str | None = None
