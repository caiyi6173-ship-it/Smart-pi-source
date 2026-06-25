from app.clients.tongue_labels import TongueLabelResolver
from app.schemas import TongueResult


class TongueDiagnosisAgent:
    def __init__(self, resolver: TongueLabelResolver) -> None:
        self.resolver = resolver

    def run(
        self,
        message: str,
        *,
        tongue_labels: list[str] | None = None,
        tongue_confidences: dict[str, float] | None = None,
    ) -> TongueResult:
        labels = self.resolver.resolve_many(tongue_labels or [], tongue_confidences or {})
        label_names = [item["display_name_zh"] for item in labels if item.get("display_name_zh")]

        if label_names:
            label_text = "、".join(label_names)
            rag_question = f"舌象识别提示{label_text}，这些舌象在中医舌诊知识中通常如何解释？需要注意哪些安全边界？"
            explanation = (
                f"舌象识别标签：{label_text}。这些标签只能作为舌象特征提示，"
                "需要结合问诊、脉诊和其他症状，不能单独作为诊断依据。"
            )
        else:
            rag_question = message
            explanation = "未提供结构化舌象标签，将根据用户问题直接检索舌诊相关知识。"

        unverified = [item["display_name_zh"] for item in labels if not item.get("verified")]
        if unverified:
            explanation += f" 其中 {'、'.join(unverified)} 的标签映射尚未完全验证，解释时应更谨慎。"

        return TongueResult(
            explanation=explanation,
            followup_questions=["是否口苦或口干？", "是否腹胀、纳差或大便黏滞？", "舌象变化持续了多久？"],
            labels=labels,
            rag_question=rag_question,
            source_available=bool(labels),
        )
