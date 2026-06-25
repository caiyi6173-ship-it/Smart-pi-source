from app.agents.intent_router import IntentRouterAgent


def test_routes_tongue_question_to_tongue_explain():
    result = IntentRouterAgent().run("舌苔黄腻说明什么？")

    assert result.primary_intent == "tongue_explain"
    assert result.need_rag is True


def test_routes_classic_question_to_classic_interpret():
    result = IntentRouterAgent().run("伤寒论中太阳病是什么？")

    assert result.primary_intent == "classic_interpret"
    assert result.need_rag is True


def test_routes_device_command_to_device_control():
    result = IntentRouterAgent().run("打开摄像头识别")

    assert result.primary_intent == "device_control"
    assert result.need_device_action is True
