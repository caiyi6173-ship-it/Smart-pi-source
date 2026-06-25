from pathlib import Path

from app.agents.tongue_agent import TongueDiagnosisAgent
from app.clients.tongue_labels import TongueLabelResolver


def test_tongue_labels_resolve_to_chinese_names():
    resolver = TongueLabelResolver(Path("../config/class_map.json"))
    agent = TongueDiagnosisAgent(resolver)

    result = agent.run(
        "帮我解释这次舌象",
        tongue_labels=["yellowcoates", "chihenshe"],
        tongue_confidences={"yellowcoates": 0.86, "chihenshe": 0.74},
    )

    names = [item["display_name_zh"] for item in result.labels]
    assert names == ["黄苔舌", "齿痕舌"]
    assert "黄苔舌、齿痕舌" in result.rag_question
    assert result.source_available is True


def test_unknown_tongue_label_is_kept_but_unverified():
    resolver = TongueLabelResolver(Path("../config/class_map.json"))
    agent = TongueDiagnosisAgent(resolver)

    result = agent.run("解释舌象", tongue_labels=["unknown_label"])

    assert result.labels[0]["display_name_zh"] == "unknown_label"
    assert result.labels[0]["verified"] is False
