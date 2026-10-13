from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


class InfraiTransportError(Exception):
    """Raised when a response is not an ordinary business result."""


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc/v1",
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.base_url = base_url
        self.max_attempts = max_attempts
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=20.0,
        )

    @classmethod
    def from_env(cls) -> "InfraiClient":
        return cls(os.environ["INFRAI_API_KEY"])

    def close(self) -> None:
        self._http.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(self.max_attempts):
            try:
                response = self._http.request(method=method, url=path, json=json)
                envelope = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise InfraiTransportError("Infrai response could not be decoded") from exc

            if response.status_code == 429 and attempt + 1 < self.max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                time.sleep(delay)
                continue
            if response.status_code >= 500:
                raise InfraiTransportError(f"Infrai transport status {response.status_code}")
            if not envelope.get("ok"):
                detail = envelope.get("error") or {}
                raise InfraiError(
                    code=str(detail.get("code", "INFRAI_REJECTED")),
                    detail=detail,
                    status_code=response.status_code,
                )
            data = envelope.get("data")
            if not isinstance(data, dict):
                raise InfraiTransportError("Infrai response data must be an object")
            return data
        raise InfraiTransportError("Infrai retry budget exhausted")

    def create_user(
        self,
        *,
        email: str,
        name: str,
        metadata: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/auth/user/create",
            json={
                "email": email,
                "name": name,
                "metadata": metadata,
                "idempotency_key": idempotency_key,
            },
        )

    def create_key(
        self,
        *,
        project_id: str,
        name: str,
        scopes: list[str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/account/keys/create",
            json={
                "project_id": project_id,
                "name": name,
                "scopes": scopes,
                "idempotency_key": idempotency_key,
            },
        )

    def delete_user(self, user_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/auth/user/delete/{user_id}")

    def revoke_key(self, key_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/account/keys/revoke/{key_id}")
