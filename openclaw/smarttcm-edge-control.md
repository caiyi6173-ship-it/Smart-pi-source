# smarttcm-edge-control

This OpenClaw-facing skill calls the local SmartTCM edge bridge running on the Raspberry Pi.

## Available actions

- `camera.start(profile)` -> `POST http://127.0.0.1:8092/control/camera/start`
- `camera.stop()` -> `POST http://127.0.0.1:8092/control/camera/stop`
- `camera.status()` -> `GET http://127.0.0.1:8092/control/camera/status`
- `sensors.start()` -> `POST http://127.0.0.1:8092/control/sensors/start`
- `sensors.stop()` -> `POST http://127.0.0.1:8092/control/sensors/stop`
- `telemetry.latest()` -> `GET http://127.0.0.1:8092/telemetry/latest`
- `analysis.trigger(deviceId, userId)` -> `POST http://127.0.0.1:8092/analysis/trigger`
- `analysis.latest(deviceId)` -> `GET http://127.0.0.1:8092/analysis/latest`
- `tongue.latest()` -> `GET http://127.0.0.1:8092/tongue/latest`

## Suggested Chinese command mapping

- `打开摄像头识别` -> `camera.start(low-latency)`
- `关闭摄像头识别` -> `camera.stop()`
- `打开温度检测` -> `sensors.start()`
- `关闭温度检测` -> `sensors.stop()`
- `读取皮肤温度` -> `telemetry.latest()`
- `读取当前心率和血氧` -> `telemetry.latest()`
- `读取最近一次舌象分析结果` -> `analysis.latest(deviceId)`
- `重新分析当前结果` -> `analysis.trigger(deviceId, userId)`

## Notes

- OpenClaw acts as the orchestration brain, not the I2C or MJPEG worker.
- SmartTCM keeps hardware access behind the local edge bridge so Plan A can run without OpenClaw.
