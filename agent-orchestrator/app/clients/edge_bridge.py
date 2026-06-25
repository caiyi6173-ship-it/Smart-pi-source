from typing import Any

import httpx

from app.config import Settings


class EdgeBridgeClientError(RuntimeError):
    pass


class EdgeBridgeClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.edge_bridge_base_url.rstrip("/")
        self.timeout = settings.agent_request_timeout_seconds

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, url, json=payload or {})
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError as exc:
            raise EdgeBridgeClientError(f"edge bridge is not reachable: {url}") from exc
        except httpx.TimeoutException as exc:
            raise EdgeBridgeClientError(f"edge bridge timed out after {self.timeout} seconds: {url}") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise EdgeBridgeClientError(f"edge bridge returned HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise EdgeBridgeClientError(f"edge bridge request failed: {exc}") from exc
