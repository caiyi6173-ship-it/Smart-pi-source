#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class ServiceProbe:
    name: str
    systemd_unit: str
    health_url: str
    required_status: str | None = "ok"


PROBES = [
    ServiceProbe("rag", "smarttcm-rag-chroma.service", "http://127.0.0.1:8095/health", "ok"),
    ServiceProbe("agent", "smartpi-agent-orchestrator.service", "http://127.0.0.1:8096/health", "ok"),
    ServiceProbe("voice", "smarttcm-voice-agent.service", "http://127.0.0.1:8093/health", None),
]


def systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=20)


def is_active(unit: str) -> bool:
    result = systemctl("is-active", unit)
    return result.returncode == 0 and result.stdout.strip() == "active"


def restart(unit: str) -> tuple[bool, str]:
    result = systemctl("restart", unit)
    message = (result.stderr or result.stdout).strip()
    return result.returncode == 0, message


def fetch_json(url: str, timeout: float) -> tuple[bool, dict[str, Any] | None, str]:
    try:
        with request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return True, payload, ""
    except error.URLError as exc:
        return False, None, str(exc)
    except Exception as exc:
        return False, None, repr(exc)


def check_probe(probe: ServiceProbe, timeout: float) -> dict[str, Any]:
    active = is_active(probe.systemd_unit)
    http_ok, payload, http_error = fetch_json(probe.health_url, timeout)
    status_ok = True
    if probe.required_status is not None:
        status_ok = bool(payload and payload.get("status") == probe.required_status)
    healthy = active and http_ok and status_ok
    return {
        "name": probe.name,
        "unit": probe.systemd_unit,
        "active": active,
        "health_url": probe.health_url,
        "http_ok": http_ok,
        "status_ok": status_ok,
        "healthy": healthy,
        "http_error": http_error,
        "payload": payload or {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check smartpi Raspberry Pi service health.")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--restart-unhealthy", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    checked_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    results = [check_probe(probe, args.timeout) for probe in PROBES]
    restarted: list[dict[str, Any]] = []
    if args.restart_unhealthy:
        for result in results:
            if result["healthy"]:
                continue
            ok, message = restart(result["unit"])
            restarted.append({"unit": result["unit"], "ok": ok, "message": message})

    report = {"checked_at": checked_at, "healthy": all(item["healthy"] for item in results), "results": results, "restarted": restarted}
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"[{checked_at}] smartpi health: {'ok' if report['healthy'] else 'degraded'}")
        for item in results:
            detail = item["payload"].get("lastError") or item["http_error"] or ""
            print(
                f"- {item['name']}: healthy={item['healthy']} active={item['active']} "
                f"http_ok={item['http_ok']} status_ok={item['status_ok']} {detail}"
            )
        for item in restarted:
            print(f"- restarted {item['unit']}: ok={item['ok']} {item['message']}")
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
