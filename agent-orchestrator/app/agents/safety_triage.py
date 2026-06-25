from app.schemas import SafetyResult


class SafetyTriageAgent:
    urgent_keywords = {
        "胸痛",
        "呼吸困难",
        "昏迷",
        "抽搐",
        "大出血",
        "中风",
        "休克",
        "高烧不退",
        "剧烈头痛",
        "意识不清",
    }
    high_risk_keywords = {
        "孕妇",
        "怀孕",
        "儿童",
        "小孩",
        "婴儿",
        "糖尿病",
        "心脏病",
        "肾病",
        "肝病",
        "抗凝药",
        "降压药",
        "停药",
        "用药冲突",
        "肿瘤",
        "癌",
    }

    def run(self, message: str) -> SafetyResult:
        if any(keyword in message for keyword in self.urgent_keywords):
            return SafetyResult(
                risk_level="urgent",
                safety_required=True,
                must_refuse=True,
                safety_message="该问题可能涉及急症风险，请立即联系医生或前往线下医疗机构处理。",
                reason="命中急症风险关键词",
            )
        if any(keyword in message for keyword in self.high_risk_keywords):
            return SafetyResult(
                risk_level="high",
                safety_required=True,
                must_refuse=False,
                safety_message="仅供中医知识参考，不能替代医生诊断。涉及特殊人群、慢病或用药问题时，请咨询医生。",
                reason="命中高风险医疗关键词",
            )
        return SafetyResult(reason="未命中高风险规则")
