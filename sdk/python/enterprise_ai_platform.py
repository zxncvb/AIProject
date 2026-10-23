"""Small dependency-light client for the versioned public application API."""
from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class EnterpriseAIError(RuntimeError):
    """Raised when the public API returns a non-success response."""

    def __init__(self, status: int, payload: object):
        self.status = status
        self.payload = payload
        super().__init__(f"Enterprise AI API request failed ({status}): {payload}")


class EnterpriseAIPlatformClient:
    """Client for ``/api/v1/public/apps`` and result polling endpoints."""

    def __init__(self, base_url: str, *, app_key: str = "", timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.app_key = app_key
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.app_key:
            headers["X-App-Key"] = self.app_key
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw
            raise EnterpriseAIError(exc.code, payload) from exc

    def get_runtime(self, tenant_slug: str, app_slug: str) -> dict:
        return self._request("GET", f"/api/v1/public/apps/{tenant_slug}/{app_slug}")

    def invoke(self, tenant_slug: str, app_slug: str, input_data: dict | None = None) -> dict:
        return self._request(
            "POST",
            f"/api/v1/public/apps/{tenant_slug}/{app_slug}/invoke",
            {"input": input_data or {}},
        )

    def get_result(self, result_token: str) -> dict:
        return self._request("GET", f"/api/v1/public/runs/{result_token}")
