#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib import request

try:
    from smbus2 import SMBus  # type: ignore
except ImportError:
    SMBus = None  # type: ignore

AS6221_TEMP_REGISTER = 0x00
AS6221_DEFAULT_FALLBACK_ADDRESSES = (0x48, 0x58, 0x59)


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="smartpi sensor hub for AS6221 and MAX30102")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--device-id", default="raspberrypi5-edge")
    parser.add_argument("--backend-url", default="http://192.168.137.1:18080/api/v1/edge/telemetry")
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--upload-interval", type=float, default=2.0)
    parser.add_argument("--i2c-bus", type=int, default=1)
    parser.add_argument("--as6221-address", type=lambda value: int(value, 0), default=0x48)
    parser.add_argument(
        "--as6221-fallback-addresses",
        default="0x58,0x59",
        help="Comma separated AS6221 fallback addresses to probe after the preferred address",
    )
    parser.add_argument("--mock", action="store_true", help="Use synthetic readings when hardware/libs are unavailable")
    return parser


@dataclass
class TelemetryState:
    running: bool = True
    temperature_enabled: bool = True
    pulseox_enabled: bool = True
    device_id: str = "raspberrypi5-edge"
    captured_at: str | None = None
    skin_temperature_c: float | None = None
    heart_rate: int | None = None
    spo2: int | None = None
    sensor_status: dict[str, Any] = field(default_factory=dict)
    voice_assistant_status: str = "IDLE"
    last_voice_command: str | None = None
    last_error: str | None = None
    uploaded_at: str | None = None


class As6221Reader:
    def __init__(self, bus_id: int, address: int, fallback_addresses: tuple[int, ...], mock: bool) -> None:
        self.bus_id = bus_id
        self.preferred_address = address
        self.address = address
        self.fallback_addresses = fallback_addresses
        self.mock = mock
        self.last_detected_address: int | None = address if mock else None

    def candidate_addresses(self) -> list[int]:
        ordered: list[int] = []
        for candidate in (
            self.address,
            self.preferred_address,
            *self.fallback_addresses,
            *AS6221_DEFAULT_FALLBACK_ADDRESSES,
        ):
            if candidate not in ordered:
                ordered.append(candidate)
        return ordered

    def _raw_to_celsius(self, raw_bytes: list[int]) -> float:
        raw = (raw_bytes[0] << 8) | raw_bytes[1]
        if raw < 32767:
            return round(raw * 0.0078125, 2)
        return round(((raw - 1) * 0.0078125) * -1, 2)

    def read(self) -> float:
        if self.mock or SMBus is None:
            return round(32.6 + random.uniform(-0.4, 0.5), 2)
        with SMBus(self.bus_id) as bus:
            last_error: Exception | None = None
            for address in self.candidate_addresses():
                try:
                    raw_bytes = bus.read_i2c_block_data(address, AS6221_TEMP_REGISTER, 2)
                    self.address = address
                    self.last_detected_address = address
                    return self._raw_to_celsius(raw_bytes)
                except Exception as exc:
                    last_error = exc
            raise RuntimeError(
                f"AS6221 probe failed on addresses {[hex(addr) for addr in self.candidate_addresses()]}: {last_error}"
            )


class Max30102Reader:
    def __init__(self, mock: bool) -> None:
        self.mock = mock
        self.available = False
        self.sensor = None
        self.hrcalc = None
        if not mock:
            try:
                import max30102  # type: ignore
                import hrcalc  # type: ignore

                self.sensor = max30102.MAX30102()
                self.hrcalc = hrcalc
                self.available = True
            except Exception:
                self.available = False

    def read(self) -> tuple[int | None, int | None]:
        if self.mock or not self.available:
            heart_rate = int(round(72 + random.uniform(-4, 5)))
            spo2 = int(round(98 + random.uniform(-1, 1)))
            return heart_rate, max(90, min(100, spo2))

        red, ir = self.sensor.read_sequential()  # type: ignore[union-attr]
        if not red or not ir:
            return None, None
        bpm, bpm_valid, spo2, spo2_valid = self.hrcalc.calc_hr_and_spo2(ir, red)  # type: ignore[union-attr]
        return (int(round(bpm)) if bpm_valid else None, int(round(spo2)) if spo2_valid else None)


class SensorHub:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.state = TelemetryState(device_id=args.device_id)
        self.state.sensor_status = {
            "as6221": "starting",
            "as6221Address": hex(args.as6221_address),
            "max30102": "starting",
            "temperatureEnabled": True,
            "pulseoxEnabled": True,
        }
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        fallback_addresses = tuple(
            int(value.strip(), 0)
            for value in str(args.as6221_fallback_addresses).split(",")
            if value.strip()
        )
        self.as6221 = As6221Reader(args.i2c_bus, args.as6221_address, fallback_addresses, args.mock)
        self.max30102 = Max30102Reader(args.mock)

    def run(self) -> None:
        threading.Thread(target=self.sample_loop, daemon=True, name="sensor-sample-loop").start()
        threading.Thread(target=self.upload_loop, daemon=True, name="sensor-upload-loop").start()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                if self.path.startswith("/health") or self.path.startswith("/telemetry/latest"):
                    self.json_response(HTTPStatus.OK, outer.snapshot())
                    return
                self.json_response(HTTPStatus.NOT_FOUND, {"error": "Not found"})

            def do_POST(self) -> None:
                if self.path.startswith("/control/start"):
                    outer.set_running(True)
                    self.json_response(HTTPStatus.OK, outer.snapshot())
                    return
                if self.path.startswith("/control/stop"):
                    outer.set_running(False)
                    self.json_response(HTTPStatus.OK, outer.snapshot())
                    return
                if self.path.startswith("/control/temperature/start"):
                    outer.set_temperature_enabled(True)
                    self.json_response(HTTPStatus.OK, outer.snapshot())
                    return
                if self.path.startswith("/control/temperature/stop"):
                    outer.set_temperature_enabled(False)
                    self.json_response(HTTPStatus.OK, outer.snapshot())
                    return
                if self.path.startswith("/control/pulseox/start"):
                    outer.set_pulseox_enabled(True)
                    self.json_response(HTTPStatus.OK, outer.snapshot())
                    return
                if self.path.startswith("/control/pulseox/stop"):
                    outer.set_pulseox_enabled(False)
                    self.json_response(HTTPStatus.OK, outer.snapshot())
                    return
                self.json_response(HTTPStatus.NOT_FOUND, {"error": "Not found"})

            def json_response(self, status: int, payload: dict[str, Any]) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer((self.args.host, self.args.port), Handler)
        try:
            server.serve_forever()
        finally:
            self.stop_event.set()
            server.server_close()

    def set_running(self, running: bool) -> None:
        with self.lock:
            self.state.running = running
            if not running:
                self.state.sensor_status["as6221"] = "stopped"
                self.state.sensor_status["max30102"] = "stopped"

    def set_temperature_enabled(self, enabled: bool) -> None:
        with self.lock:
            self.state.temperature_enabled = enabled
            self.state.sensor_status["temperatureEnabled"] = enabled
            if not enabled:
                self.state.sensor_status["as6221"] = "stopped"
                self.state.skin_temperature_c = None

    def set_pulseox_enabled(self, enabled: bool) -> None:
        with self.lock:
            self.state.pulseox_enabled = enabled
            self.state.sensor_status["pulseoxEnabled"] = enabled
            if not enabled:
                self.state.sensor_status["max30102"] = "stopped"
                self.state.heart_rate = None
                self.state.spo2 = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "status": "UP",
                "running": self.state.running,
                "deviceId": self.state.device_id,
                "capturedAt": self.state.captured_at,
                "skinTemperatureC": self.state.skin_temperature_c,
                "heartRate": self.state.heart_rate,
                "spo2": self.state.spo2,
                "sensorStatus": dict(self.state.sensor_status),
                "temperatureEnabled": self.state.temperature_enabled,
                "pulseoxEnabled": self.state.pulseox_enabled,
                "voiceAssistantStatus": self.state.voice_assistant_status,
                "lastVoiceCommand": self.state.last_voice_command,
                "lastError": self.state.last_error,
                "uploadedAt": self.state.uploaded_at,
            }

    def sample_loop(self) -> None:
        while not self.stop_event.is_set():
            if not self.state.running:
                time.sleep(0.5)
                continue
            captured_at = iso_now()
            status_map: dict[str, Any] = {}
            errors: list[str] = []
            skin_temp = None
            heart_rate = None
            spo2 = None

            if self.state.temperature_enabled:
                try:
                    skin_temp = self.as6221.read()
                    status_map["as6221"] = "online"
                    status_map["as6221Address"] = hex(self.as6221.last_detected_address or self.as6221.address)
                except Exception as exc:
                    status_map["as6221"] = "offline"
                    status_map["as6221Address"] = hex(self.as6221.address)
                    errors.append(f"AS6221 read failed: {exc}")
            else:
                status_map["as6221"] = "stopped"
                status_map["as6221Address"] = hex(self.as6221.address)

            if self.state.pulseox_enabled:
                try:
                    heart_rate, spo2 = self.max30102.read()
                    status_map["max30102"] = "online" if heart_rate is not None or spo2 is not None else "warming_up"
                except Exception as exc:
                    status_map["max30102"] = "offline"
                    errors.append(f"MAX30102 read failed: {exc}")
            else:
                status_map["max30102"] = "stopped"

            with self.lock:
                self.state.captured_at = captured_at
                self.state.skin_temperature_c = skin_temp if self.state.temperature_enabled else None
                self.state.heart_rate = heart_rate if self.state.pulseox_enabled else None
                self.state.spo2 = spo2 if self.state.pulseox_enabled else None
                self.state.sensor_status.update(status_map)
                self.state.sensor_status["temperatureEnabled"] = self.state.temperature_enabled
                self.state.sensor_status["pulseoxEnabled"] = self.state.pulseox_enabled
                self.state.last_error = " | ".join(errors) if errors else None
            time.sleep(self.args.sample_interval)

    def upload_loop(self) -> None:
        while not self.stop_event.is_set():
            time.sleep(self.args.upload_interval)
            snapshot = self.snapshot()
            if not snapshot["running"]:
                continue
            payload = {
                "deviceId": snapshot["deviceId"],
                "capturedAt": snapshot["capturedAt"] or iso_now(),
                "skinTemperatureC": snapshot["skinTemperatureC"],
                "heartRate": snapshot["heartRate"],
                "spo2": snapshot["spo2"],
                "sensorStatus": snapshot["sensorStatus"],
                "voiceAssistantStatus": snapshot["voiceAssistantStatus"],
                "lastVoiceCommand": snapshot["lastVoiceCommand"],
            }
            try:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                req = request.Request(
                    self.args.backend_url,
                    data=body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    method="POST",
                )
                with request.urlopen(req, timeout=10) as response:
                    response.read()
                with self.lock:
                    self.state.uploaded_at = iso_now()
            except Exception as exc:
                with self.lock:
                    self.state.last_error = f"Telemetry upload failed: {exc}"


def main() -> None:
    SensorHub(build_parser().parse_args()).run()


if __name__ == "__main__":
    main()
