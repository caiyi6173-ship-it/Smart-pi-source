#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import parse, request


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="smartpi local edge bridge for OpenClaw and voice control")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--backend-base-url", default="http://192.168.137.1:18080")
    parser.add_argument("--stream-base-url", default="http://127.0.0.1:8081")
    parser.add_argument("--sensor-base-url", default="http://127.0.0.1:8091")
    parser.add_argument("--voice-base-url", default="http://127.0.0.1:8093")
    parser.add_argument("--device-id", default="raspberrypi5-edge")
    parser.add_argument("--user-id", default="front_dashboard_user")
    parser.add_argument("--camera-start-script", default="/home/pi/smartpi/edge/pi_start_mjpeg_stream.sh")
    parser.add_argument("--camera-stop-script", default="/home/pi/smartpi/edge/pi_stop_mjpeg_stream.sh")
    parser.add_argument("--voice-service-name", default="smartpi-voice-agent.service")
    parser.add_argument("--voice-env-path", default="/home/pi/smartpi/config/voice_agent.env")
    return parser


class EdgeBridge:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args

    def run(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                if self.path.startswith("/status"):
                    self.respond(HTTPStatus.OK, outer.status())
                    return
                if self.path.startswith("/voice/status"):
                    self.respond(HTTPStatus.OK, outer.voice_status())
                    return
                if self.path.startswith("/voice/context"):
                    params = parse.parse_qs(parse.urlsplit(self.path).query)
                    self.respond(
                        HTTPStatus.OK,
                        outer.voice_context(
                            params.get("userId", [outer.args.user_id])[0],
                            params.get("deviceId", [outer.args.device_id])[0],
                        ),
                    )
                    return
                if self.path.startswith("/control/camera/status"):
                    self.respond(HTTPStatus.OK, outer.camera_status())
                    return
                if self.path.startswith("/telemetry/latest"):
                    self.respond(HTTPStatus.OK, outer.telemetry_latest())
                    return
                if self.path.startswith("/analysis/latest"):
                    params = parse.parse_qs(parse.urlsplit(self.path).query)
                    self.respond(HTTPStatus.OK, outer.analysis_latest(params.get("deviceId", [outer.args.device_id])[0]))
                    return
                if self.path.startswith("/tongue/latest"):
                    self.respond(HTTPStatus.OK, outer.tongue_latest())
                    return
                self.respond(HTTPStatus.NOT_FOUND, {"error": "Not found"})

            def do_POST(self) -> None:
                payload = self.read_json()
                if self.path.startswith("/control/camera/start"):
                    self.respond(HTTPStatus.OK, outer.camera_start(str(payload.get("profile", "low-latency"))))
                    return
                if self.path.startswith("/control/camera/stop"):
                    self.respond(HTTPStatus.OK, outer.camera_stop())
                    return
                if self.path.startswith("/control/voice/start"):
                    self.respond(HTTPStatus.OK, outer.voice_start())
                    return
                if self.path.startswith("/control/voice/stop"):
                    self.respond(HTTPStatus.OK, outer.voice_stop())
                    return
                if self.path.startswith("/control/voice/manual-wake"):
                    speak_reply = bool(payload.get("speakReply", True))
                    self.respond(HTTPStatus.OK, outer.voice_manual_wake(speak_reply))
                    return
                if self.path.startswith("/control/voice/memory/clear"):
                    self.respond(HTTPStatus.OK, outer.voice_clear_memory())
                    return
                if self.path.startswith("/control/voice/restart"):
                    self.respond(HTTPStatus.OK, outer.voice_restart())
                    return
                if self.path.startswith("/control/voice/wake-word"):
                    wake_word = str(payload.get("wakeWord", "")).strip()
                    persist = bool(payload.get("persist", True))
                    self.respond(HTTPStatus.OK, outer.voice_set_wake_word(wake_word, persist))
                    return
                if self.path.startswith("/control/sensors/temperature/start"):
                    self.respond(HTTPStatus.OK, outer.temperature_start())
                    return
                if self.path.startswith("/control/sensors/temperature/stop"):
                    self.respond(HTTPStatus.OK, outer.temperature_stop())
                    return
                if self.path.startswith("/control/sensors/pulseox/start"):
                    self.respond(HTTPStatus.OK, outer.pulseox_start())
                    return
                if self.path.startswith("/control/sensors/pulseox/stop"):
                    self.respond(HTTPStatus.OK, outer.pulseox_stop())
                    return
                if self.path.startswith("/control/sensors/start"):
                    self.respond(HTTPStatus.OK, outer.sensors_start())
                    return
                if self.path.startswith("/control/sensors/stop"):
                    self.respond(HTTPStatus.OK, outer.sensors_stop())
                    return
                if self.path.startswith("/analysis/trigger"):
                    self.respond(HTTPStatus.OK, outer.analysis_trigger(payload.get("deviceId"), payload.get("userId")))
                    return
                self.respond(HTTPStatus.NOT_FOUND, {"error": "Not found"})

            def read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    return {}
                try:
                    return json.loads(self.rfile.read(length).decode("utf-8"))
                except json.JSONDecodeError:
                    return {}

            def respond(self, status: int, payload: dict[str, Any]) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        ThreadingHTTPServer((self.args.host, self.args.port), Handler).serve_forever()

    def status(self) -> dict[str, Any]:
        camera = self.safe_call(self.camera_status, {"status": "DOWN", "message": "camera service unavailable"})
        telemetry = self.safe_call(self.telemetry_latest, {"running": False, "sensorStatus": {}, "lastError": "sensor hub unavailable"})
        voice = self.voice_status()
        return {
            "status": "UP",
            "cameraRunning": camera.get("status") == "UP",
            "sensorsRunning": bool(telemetry.get("running", False)),
            "voiceAssistantStatus": voice.get("voiceAssistantStatus", "OFFLINE"),
            "lastVoiceCommand": voice.get("lastVoiceCommand"),
            "lastReply": voice.get("lastReply"),
            "lastHeardText": voice.get("lastHeardText"),
            "lastWakeDetectedAt": voice.get("lastWakeDetectedAt"),
            "wakeWord": voice.get("wakeWord"),
            "turnId": voice.get("turnId"),
            "turnStartedAt": voice.get("turnStartedAt"),
            "turnFinishedAt": voice.get("turnFinishedAt"),
            "lastWakeMs": voice.get("lastWakeMs"),
            "lastRecordMs": voice.get("lastRecordMs"),
            "lastSttMs": voice.get("lastSttMs"),
            "lastRouteMs": voice.get("lastRouteMs"),
            "lastLlmMs": voice.get("lastLlmMs"),
            "lastTtsMs": voice.get("lastTtsMs"),
            "lastEndToEndMs": voice.get("lastEndToEndMs"),
            "audioPipelineMode": voice.get("audioPipelineMode"),
            "memoryEnabled": voice.get("memoryEnabled"),
            "memoryTurnCount": voice.get("memoryTurnCount"),
            "memoryUpdatedAt": voice.get("memoryUpdatedAt"),
            "sensorStatus": telemetry.get("sensorStatus", {}),
            "temperatureEnabled": telemetry.get("temperatureEnabled"),
            "pulseoxEnabled": telemetry.get("pulseoxEnabled"),
            "deviceId": self.args.device_id,
            "updatedAt": iso_now(),
        }

    def camera_start(self, profile: str) -> dict[str, Any]:
        return self.run_script(self.args.camera_start_script, profile)

    def camera_stop(self) -> dict[str, Any]:
        return self.run_script(self.args.camera_stop_script)

    def camera_status(self) -> dict[str, Any]:
        return self.http_json("GET", f"{self.args.stream_base_url}/health")

    def voice_start(self) -> dict[str, Any]:
        return self.run_systemctl("start", self.args.voice_service_name)

    def voice_stop(self) -> dict[str, Any]:
        return self.run_systemctl("stop", self.args.voice_service_name)

    def voice_manual_wake(self, speak_reply: bool) -> dict[str, Any]:
        return self.http_json("POST", f"{self.args.voice_base_url}/manual-wake", {"speakReply": speak_reply}, timeout=30)

    def voice_clear_memory(self) -> dict[str, Any]:
        return self.http_json("POST", f"{self.args.voice_base_url}/memory/clear", {}, timeout=10)

    def voice_restart(self) -> dict[str, Any]:
        return self.run_systemctl("restart", self.args.voice_service_name)

    def voice_set_wake_word(self, wake_word: str, persist: bool) -> dict[str, Any]:
        if not wake_word:
            raise RuntimeError("wakeWord is required")
        voice_status = self.http_json("POST", f"{self.args.voice_base_url}/config/wake-word", {"wakeWord": wake_word})
        if persist:
            self.persist_wake_word(wake_word)
        return {
            "status": "OK",
            "wakeWord": wake_word,
            "persisted": persist,
            "voiceStatus": voice_status,
        }

    def sensors_start(self) -> dict[str, Any]:
        return self.http_json("POST", f"{self.args.sensor_base_url}/control/start", {})

    def sensors_stop(self) -> dict[str, Any]:
        return self.http_json("POST", f"{self.args.sensor_base_url}/control/stop", {})

    def temperature_start(self) -> dict[str, Any]:
        return self.http_json("POST", f"{self.args.sensor_base_url}/control/temperature/start", {})

    def temperature_stop(self) -> dict[str, Any]:
        return self.http_json("POST", f"{self.args.sensor_base_url}/control/temperature/stop", {})

    def pulseox_start(self) -> dict[str, Any]:
        return self.http_json("POST", f"{self.args.sensor_base_url}/control/pulseox/start", {})

    def pulseox_stop(self) -> dict[str, Any]:
        return self.http_json("POST", f"{self.args.sensor_base_url}/control/pulseox/stop", {})

    def telemetry_latest(self) -> dict[str, Any]:
        return self.http_json("GET", f"{self.args.sensor_base_url}/telemetry/latest")

    def analysis_latest(self, device_id: str | None) -> dict[str, Any]:
        query = parse.urlencode({"deviceId": device_id or self.args.device_id})
        return self.http_json("GET", f"{self.args.backend_base_url}/api/v1/analysis/latest?{query}")

    def tongue_latest(self) -> dict[str, Any]:
        health = self.camera_status()
        return {
            "deviceId": self.args.device_id,
            "capturedAt": health.get("hitUpdatedAt") or health.get("lastUpdatedAt"),
            "lastLabels": health.get("lastLabels", []),
            "hitFrameReady": health.get("hitFrameReady", False),
            "hitUpdatedAt": health.get("hitUpdatedAt"),
            "hitLabels": health.get("hitLabels", []),
        }

    def analysis_trigger(self, device_id: str | None, user_id: str | None) -> dict[str, Any]:
        device_id = device_id or self.args.device_id
        user_id = user_id or self.args.user_id
        tongue = self.tongue_latest()
        labels = [str(item).strip() for item in tongue.get("lastLabels", []) if str(item).strip()]
        if not labels:
            raise RuntimeError("No tongue labels available from the live stream")
        telemetry = self.telemetry_latest()
        payload = {
            "userId": user_id,
            "source": "device",
            "deviceId": device_id,
            "capturedAt": telemetry.get("capturedAt") or iso_now(),
            "tongueLabels": labels,
            "tongueDescription": "树莓派视频流实时识别",
            "heartRate": telemetry.get("heartRate"),
            "spo2": telemetry.get("spo2"),
            "sensorReadings": {
                "skinTemperatureC": telemetry.get("skinTemperatureC"),
                "heartRate": telemetry.get("heartRate"),
                "spo2": telemetry.get("spo2"),
            },
        }
        image_bytes = self.safe_read_snapshot()
        return self.submit_analysis(payload, image_bytes)

    def voice_status(self) -> dict[str, Any]:
        try:
            return self.http_json("GET", f"{self.args.voice_base_url}/health", timeout=2)
        except Exception:
            return {
                "voiceAssistantStatus": "OFFLINE",
                "lastVoiceCommand": None,
                "lastReply": None,
                "lastHeardText": None,
                "lastWakeDetectedAt": None,
                "wakeWord": None,
                "turnId": None,
                "turnStartedAt": None,
                "turnFinishedAt": None,
                "lastWakeMs": None,
                "lastRecordMs": None,
                "lastSttMs": None,
                "lastRouteMs": None,
                "lastLlmMs": None,
                "lastTtsMs": None,
                "lastEndToEndMs": None,
                "audioPipelineMode": None,
                "memoryEnabled": True,
                "memoryTurnCount": 0,
                "memoryUpdatedAt": None,
                "lastError": "voice service unavailable",
                "updatedAt": iso_now(),
            }

    def voice_context(self, user_id: str | None, device_id: str | None) -> dict[str, Any]:
        query = parse.urlencode(
            {
                "userId": user_id or self.args.user_id,
                "deviceId": device_id or self.args.device_id,
            }
        )
        response = self.http_json("GET", f"{self.args.backend_base_url}/api/frontend/dashboard/voice/context?{query}")
        if isinstance(response.get("data"), dict):
            return response["data"]
        return response

    def persist_wake_word(self, wake_word: str) -> None:
        env_path = Path(self.args.voice_env_path)
        env_path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()

        replaced = False
        for index, line in enumerate(lines):
            if line.strip().startswith("WAKE_WORD="):
                lines[index] = f"WAKE_WORD={wake_word}"
                replaced = True
                break
        if not replaced:
            lines.append(f"WAKE_WORD={wake_word}")

        env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def safe_read_snapshot(self) -> bytes | None:
        for path in ("/hit-snapshot", "/snapshot"):
            try:
                return self.http_bytes("GET", f"{self.args.stream_base_url}{path}")
            except Exception:
                continue
        return None

    def run_script(self, script_path: str, *args: str) -> dict[str, Any]:
        process = subprocess.run([script_path, *args], capture_output=True, text=True, check=False)
        return {
            "status": "OK" if process.returncode == 0 else "ERROR",
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
            "returnCode": process.returncode,
        }

    def run_systemctl(self, action: str, service_name: str) -> dict[str, Any]:
        process = subprocess.run(
            ["sudo", "-n", "systemctl", action, service_name],
            capture_output=True,
            text=True,
            check=False,
        )
        payload = {
            "status": "OK" if process.returncode == 0 else "ERROR",
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
            "returnCode": process.returncode,
        }
        payload["voiceStatus"] = self.voice_status()
        return payload

    def submit_analysis(self, payload: dict[str, Any], image_bytes: bytes | None) -> dict[str, Any]:
        boundary = f"----smartpiEdgeBridge{int(datetime.now().timestamp() * 1000)}"
        body = bytearray()
        body.extend(self.multipart_text(boundary, "payload", json.dumps(payload, ensure_ascii=False)))
        if image_bytes:
            body.extend(self.multipart_file(boundary, "tongueImage", "edge_hit_snapshot.jpg", "image/jpeg", image_bytes))
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        req = request.Request(
            f"{self.args.backend_base_url}/api/v1/analysis",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with request.urlopen(req, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))

    def multipart_text(self, boundary: str, name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"{name}\"\r\n\r\n"
            f"{value}\r\n"
        ).encode("utf-8")

    def multipart_file(self, boundary: str, name: str, filename: str, content_type: str, data: bytes) -> bytes:
        header = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        return header + data + b"\r\n"

    def http_json(self, method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 15) -> dict[str, Any]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = request.Request(url, data=data, headers=headers, method=method)
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def http_bytes(self, method: str, url: str) -> bytes:
        req = request.Request(url, method=method)
        with request.urlopen(req, timeout=15) as response:
            return response.read()

    def safe_call(self, func, fallback: dict[str, Any]) -> dict[str, Any]:
        try:
            return func()
        except Exception as exc:
            payload = dict(fallback)
            payload.setdefault("message", str(exc))
            return payload


def main() -> None:
    EdgeBridge(build_parser().parse_args()).run()


if __name__ == "__main__":
    main()
