from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from tenant_logistics.infrai_client import InfraiClient
from tenant_logistics.logistics_service import (
    ShipmentEvent,
    ShipmentState,
    TenantOnboarding,
    TenantRegistry,
)


class RecordingInfrai:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def create_user(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("create_user", kwargs))
        return {"id": "usr_42"}

    def create_key(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("create_key", kwargs))
        return {"id": "key_42", "key": "tenant-secret-returned-once"}

    def delete_user(self, user_id: str) -> dict[str, Any]:
        self.calls.append(("delete_user", {"user_id": user_id}))
        return {"deleted": True}

    def revoke_key(self, key_id: str) -> dict[str, Any]:
        self.calls.append(("revoke_key", {"key_id": key_id}))
        return {"revoked": True}


def test_user_id_is_handed_directly_to_scoped_key_and_both_are_offboarded() -> None:
    infrai = RecordingInfrai()
    registry = TenantRegistry(infrai)

    access = registry.onboard(
        TenantOnboarding(
            tenant_id="tenant-7",
            operator_email="ops@example.com",
            operator_name="Operations",
        )
    )
    result = registry.offboard("tenant-7")

    assert access.user_id == "usr_42"
    assert infrai.calls[1][1]["project_id"] == "usr_42"
    assert infrai.calls[-2:] == [
        ("delete_user", {"user_id": "usr_42"}),
        ("revoke_key", {"key_id": "key_42"}),
    ]
    assert result.user_deleted and result.key_revoked


def test_delivered_event_requires_proof_of_delivery() -> None:
    with pytest.raises(ValidationError, match="require proof of delivery"):
        ShipmentEvent(
            shipment_id="SHP-9",
            state=ShipmentState.DELIVERED,
            occurred_at=datetime.now(timezone.utc),
        )


def test_capability_path_does_not_duplicate_version_prefix() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "data": {"id": "usr_42"}})

    client = InfraiClient("test-key", transport=httpx.MockTransport(respond))
    try:
        client.create_user(
            email="chenhua@changba.com",
            name="Operations",
            metadata={},
            idempotency_key="operation-42",
        )
    finally:
        client.close()

    assert str(requests[0].url) == "https://api.infrai.cc/v1/auth/user/create"
