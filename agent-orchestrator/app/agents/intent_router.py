from app.schemas import IntentResult


class IntentRouterAgent:
    device_keywords = {
        "打开",
        "关闭",
        "拍照",
        "拍摄",
        "补光灯",
        "舵机",
        "重启",
        "启动",
        "摄像头",
        "相机",
        "识别",
        "测温",
        "温度",
        "心率",
        "血氧",
        "遥测",
        "上次分析",
        "最近结果",
        "重新分析",
        "再分析",
    }
    tongue_keywords = {
        "舌",
        "舌苔",
        "舌质",
        "舌象",
        "黄腻",
        "齿痕",
        "裂纹",
        "胖大",
        "红舌",
        "紫舌",
        "剥苔",
    }
    classic_keywords = {
        "伤寒论",
        "金匮",
        "黄帝内经",
        "素问",
        "灵枢",
        "温病",
        "太阳病",
        "少阳",
        "条文",
        "古籍",
        "难经",
        "本草经",
        "脾胃论",
    }
    project_keywords = {"项目", "部署", "树莓派", "接口", "代码", "服务", "端口", "github", "环境"}
    tcm_keywords = {
        "中医",
        "气血",
        "阴阳",
        "脾胃",
        "湿热",
        "痰湿",
        "方剂",
        "经络",
        "证候",
        "体质",
        "养生",
        "寒热",
        "虚实",
        "五行",
        "脏腑",
    }

    def run(self, message: str, must_refuse: bool = False) -> IntentResult:
        if must_refuse:
            return IntentResult(primary_intent="unsafe_medical")

        normalized = message.strip().lower()
        if any(keyword in normalized for keyword in self.device_keywords):
            return IntentResult(primary_intent="device_control", need_device_action=True)
        if any(keyword in normalized for keyword in self.tongue_keywords):
            return IntentResult(primary_intent="tongue_explain", secondary_intents=["tcm_knowledge"], need_rag=True)
        if any(keyword in normalized for keyword in self.classic_keywords):
            return IntentResult(primary_intent="classic_interpret", need_rag=True)
        if any(keyword in normalized for keyword in self.project_keywords):
            return IntentResult(primary_intent="project_help")
        if any(keyword in normalized for keyword in self.tcm_keywords):
            return IntentResult(primary_intent="tcm_knowledge", need_rag=True)
        return IntentResult(primary_intent="general_chat")
