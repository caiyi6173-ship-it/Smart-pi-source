from app.agents.device_agent import DeviceControlAgent
from app.clients.edge_bridge import EdgeBridgeClient
from app.config import Settings


def make_agent(dry_run: bool = True) -> DeviceControlAgent:
    settings = Settings(device_dry_run=dry_run)
    return DeviceControlAgent(settings, EdgeBridgeClient(settings))


def test_camera_start_is_planned_as_dry_run():
    action = make_agent().run("打开摄像头识别")

    assert action.action == "camera.start"
    assert action.method == "POST"
    assert action.path == "/control/camera/start"
    assert action.action_marker == "[[SMARTPI_ACTION:camera.start]]"
    assert action.requires_confirmation is True
    assert action.dry_run is True
    assert action.executed is False


def test_temperature_read_is_planned_without_confirmation():
    action = make_agent().run("读一下温度")

    assert action.action == "telemetry.temperature.read"
    assert action.method == "GET"
    assert action.path == "/telemetry/latest"
    assert action.requires_confirmation is False
    assert action.dry_run is True
    assert action.executed is False


def test_unknown_device_command_is_not_executed():
    action = make_agent().run("启动未知设备")

    assert action.action == "unknown"
    assert action.executed is False
    assert action.dry_run is True
