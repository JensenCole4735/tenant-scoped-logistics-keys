from __future__ import annotations

import json
from datetime import datetime, timezone

from .infrai_client import InfraiClient
from .logistics_service import (
    ProofOfDelivery,
    ShipmentEvent,
    ShipmentState,
    TenantOnboarding,
    TenantRegistry,
)


def main() -> None:
    client = InfraiClient.from_env()
    registry = TenantRegistry(client)
    tenant_id = "north-dock"
    onboarded = False
    try:
        access = registry.onboard(
            TenantOnboarding(
                tenant_id=tenant_id,
                operator_email="chenhua@changba.com",
                operator_name="North Dock Dispatch",
            )
        )
        onboarded = True
        print(
            json.dumps(
                {
                    "tenant_id": access.tenant_id,
                    "user_id": access.user_id,
                    "key_id": access.key_id,
                    "next_step": "store api_key in your secret manager now",
                },
                indent=2,
            )
        )
        event = registry.record_event(
            access.tenant_id,
            ShipmentEvent(
                shipment_id="SHP-2048",
                state=ShipmentState.DELIVERED,
                occurred_at=datetime.now(timezone.utc),
                proof=ProofOfDelivery(
                    object_key="pod/SHP-2048.jpg",
                    content_type="image/jpeg",
                    sha256="a" * 64,
                ),
            ),
        )
        print(event.model_dump_json(indent=2))
    finally:
        if onboarded:
            offboarding = registry.offboard(tenant_id)
            print(offboarding.model_dump_json(indent=2))
        client.close()


if __name__ == "__main__":
    main()
