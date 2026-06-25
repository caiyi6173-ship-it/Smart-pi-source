from dataclasses import dataclass, field
from typing import Any

from app.clients.edge_bridge import EdgeBridgeClient, EdgeBridgeClientError
from app.config import Settings
from app.schemas import AgentAction


@dataclass(frozen=True)
class DeviceActionSpec:
    action: str
    method: str
    path: str
    parameters: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = True
    aliases: tuple[str, ...] = ()
    result_dry_run: str = ""


class DeviceControlAgent:
    def __init__(self, settings: Settings, client: EdgeBridgeClient) -> None:
        self.settings = settings
        self.client = client
        self.actions = self._build_actions()

    def run(self, command: str, *, confirm: bool = False) -> AgentAction:
        spec = self._match_action(command)
        if spec is None:
            return AgentAction(
                action="unknown",
                parameters={"command": command},
                requires_confirmation=True,
                executed=False,
                dry_run=True,
                result="未识别到明确的 smartpi 设备动作，已停止执行。请明确说明要打开摄像头、读取分析结果、测温或测心率血氧。",
            )

        action = AgentAction(
            action=spec.action,
            parameters=dict(spec.parameters),
            method=spec.method,
            path=spec.path,
            action_marker=f"[[SMARTPI_ACTION:{spec.action}]]",
            requires_confirmation=spec.requires_confirmation,
            executed=False,
            dry_run=self.settings.device_dry_run,
            result=spec.result_dry_run or f"已生成动作计划：{spec.action}。当前为 dry-run，未执行真实硬件动作。",
        )

        if self.settings.device_dry_run:
            return action
        if spec.requires_confirmation and not confirm:
            action.result = f"动作 {spec.action} 需要确认后才能执行。当前未执行。"
            return action

        try:
            response = self.client.request(spec.method, spec.path, spec.parameters)
        except EdgeBridgeClientError as exc:
            action.result = str(exc)
            return action

        action.executed = True
        action.dry_run = False
        action.result = f"动作 {spec.action} 已发送到 edge bridge。"
        action.parameters["edge_response"] = response
        return action

    def _match_action(self, command: str) -> DeviceActionSpec | None:
        normalized = command.strip().lower()
        for spec in self.actions:
            if any(alias.lower() in normalized for alias in spec.aliases):
                return spec
        return None

    def _build_actions(self) -> list[DeviceActionSpec]:
        return [
            DeviceActionSpec(
                action="camera.start",
                method="POST",
                path="/control/camera/start",
                parameters={"profile": "low-latency"},
                aliases=("打开摄像头", "开启摄像头", "打开相机", "开始识别", "开始舌象识别", "看看舌象", "开始看舌头"),
                result_dry_run="已规划打开摄像头识别动作。当前为 dry-run，未启动摄像头。",
            ),
            DeviceActionSpec(
                action="camera.stop",
                method="POST",
                path="/control/camera/stop",
                aliases=("关闭摄像头", "关掉摄像头", "关闭相机", "停止识别", "结束摄像头识别", "别看了"),
                result_dry_run="已规划关闭摄像头识别动作。当前为 dry-run，未关闭真实服务。",
            ),
            DeviceActionSpec(
                action="sensor.temperature.start",
                method="POST",
                path="/control/sensors/temperature/start",
                aliases=("开始测温", "打开温度检测", "开启温度检测", "测体温", "测温度"),
                result_dry_run="已规划启动温度检测动作。当前为 dry-run，未操作传感器。",
            ),
            DeviceActionSpec(
                action="sensor.temperature.stop",
                method="POST",
                path="/control/sensors/temperature/stop",
                aliases=("停止测温", "关闭温度检测", "关掉温度检测"),
                result_dry_run="已规划停止温度检测动作。当前为 dry-run，未操作传感器。",
            ),
            DeviceActionSpec(
                action="sensor.pulseox.start",
                method="POST",
                path="/control/sensors/pulseox/start",
                aliases=("测心率", "测血氧", "打开心率血氧", "开始心率血氧", "检测心率", "检测血氧"),
                result_dry_run="已规划启动心率血氧检测动作。当前为 dry-run，未操作传感器。",
            ),
            DeviceActionSpec(
                action="sensor.pulseox.stop",
                method="POST",
                path="/control/sensors/pulseox/stop",
                aliases=("关闭心率血氧", "停止心率血氧", "停止测心率", "停止测血氧"),
                result_dry_run="已规划停止心率血氧检测动作。当前为 dry-run，未操作传感器。",
            ),
            DeviceActionSpec(
                action="telemetry.temperature.read",
                method="GET",
                path="/telemetry/latest",
                requires_confirmation=False,
                aliases=("读一下温度", "当前温度", "温度多少", "体温多少"),
                result_dry_run="已规划读取温度遥测动作。当前为 dry-run，未读取真实遥测。",
            ),
            DeviceActionSpec(
                action="telemetry.pulseox.read",
                method="GET",
                path="/telemetry/latest",
                requires_confirmation=False,
                aliases=("当前心率", "当前血氧", "心率血氧多少", "读一下心率", "读一下血氧"),
                result_dry_run="已规划读取心率血氧遥测动作。当前为 dry-run，未读取真实遥测。",
            ),
            DeviceActionSpec(
                action="analysis.latest",
                method="GET",
                path="/analysis/latest",
                requires_confirmation=False,
                aliases=("看看上次分析", "读取最近结果", "最近一次分析", "上次检查结果", "上次结果"),
                result_dry_run="已规划读取最近舌象分析结果动作。当前为 dry-run，未读取真实结果。",
            ),
            DeviceActionSpec(
                action="analysis.trigger",
                method="POST",
                path="/analysis/trigger",
                aliases=("重新分析", "再分析一次", "触发分析", "重新识别舌象"),
                result_dry_run="已规划触发舌象分析动作。当前为 dry-run，未触发真实分析。",
            ),
        ]
