from app.schemas import Chunk


SAFETY_NOTICE = "仅供中医知识参考，不能替代医生诊断。若存在急症、孕产、儿童、严重慢病或用药冲突，请及时线下就医。"


def build_rag_messages(question: str, chunks: list[Chunk], user_context: dict | None = None) -> list[dict[str, str]]:
    evidence = "\n\n".join(
        f"[{idx}] 来源：{chunk.metadata.get('title', '未知')} | chunk={chunk.id}\n{chunk.text}"
        for idx, chunk in enumerate(chunks, start=1)
    )
    context_text = f"\n用户上下文：{user_context}" if user_context else ""
    system = (
        "你是 smartpi 的中医知识库问答助手。"
        "只能基于给定资料回答，不要编造来源。"
        "回答要清晰、谨慎、可追溯，并在最后加入医疗安全提示。"
        "如果资料不足，请明确说明知识库未找到可靠依据。"
    )
    user = f"问题：{question}{context_text}\n\n知识库资料：\n{evidence}\n\n请给出中文回答，并列出引用依据。"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

