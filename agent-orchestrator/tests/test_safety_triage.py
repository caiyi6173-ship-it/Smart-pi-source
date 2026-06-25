from app.agents.safety_triage import SafetyTriageAgent


def test_urgent_medical_question_is_refused():
    result = SafetyTriageAgent().run("我胸痛可以喝什么中药？")

    assert result.risk_level == "urgent"
    assert result.must_refuse is True
    assert "线下医疗机构" in result.safety_message


def test_normal_question_is_low_risk():
    result = SafetyTriageAgent().run("舌苔黄腻说明什么？")

    assert result.risk_level == "low"
    assert result.must_refuse is False
