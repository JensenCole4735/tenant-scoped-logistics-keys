from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from .infrai_client import InfraiClient, InfraiError, InfraiTransportError


class EnvironmentInfrai:
    """Create the shared client on the first request, after process startup."""

    def __init__(self) -> None:
        self._client: InfraiClient | None = None

    @property
    def client(self) -> InfraiClient:
        if self._client is None:
            self._client = InfraiClient.from_env()
        return self._client

    def create_user(self, **kwargs: Any) -> dict[str, Any]:
        return self.client.create_user(**kwargs)

    def create_key(self, **kwargs: Any) -> dict[str, Any]:
        return self.client.create_key(**kwargs)

    def delete_user(self, user_id: str) -> dict[str, Any]:
        return self.client.delete_user(user_id)

    def revoke_key(self, key_id: str) -> dict[str, Any]:
        return self.client.revoke_key(key_id)


class ShipmentState(str, Enum):
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class ProofOfDelivery(BaseModel):
    object_key: str
    content_type: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ShipmentEvent(BaseModel):
    shipment_id: str
    state: ShipmentState
    occurred_at: datetime
    proof: ProofOfDelivery | None = None
    exception_reason: str | None = None

    @model_validator(mode="after")
    def require_state_evidence(self) -> "ShipmentEvent":
        if self.state is ShipmentState.DELIVERED and self.proof is None:
            raise ValueError("delivered shipments require proof of delivery")
        if self.state is ShipmentState.EXCEPTION and not self.exception_reason:
            raise ValueError("shipment exceptions require a reason")
        if self.state is not ShipmentState.EXCEPTION and self.exception_reason:
            raise ValueError("exception_reason belongs only to exception events")
        return self


class TenantOnboarding(BaseModel):
    tenant_id: str
    operator_email: str
    operator_name: str


class TenantAccess(BaseModel):
    tenant_id: str
    user_id: str
    key_id: str
    api_key: str


class OffboardingResult(BaseModel):
    tenant_id: str
    user_deleted: bool
    key_revoked: bool


class TenantRegistry:
    def __init__(self, infrai: Any) -> None:
        self.infrai = infrai
        self._access: dict[str, TenantAccess] = {}
        self._events: dict[str, list[ShipmentEvent]] = {}

    def onboard(self, request: TenantOnboarding) -> TenantAccess:
        operation_id = uuid4().hex
        user = self.infrai.create_user(
            email=request.operator_email,
            name=request.operator_name,
            metadata={"tenant_id": request.tenant_id, "role": "logistics-operator"},
            idempotency_key=f"tenant-{request.tenant_id}-user-{operation_id}",
        )
        user_id = str(user["id"])
        key = self.infrai.create_key(
            project_id=user_id,
            name=f"{request.tenant_id}-logistics",
            scopes=["shipments:write", "shipments:read"],
            idempotency_key=f"tenant-{request.tenant_id}-key-{operation_id}",
        )
        access = TenantAccess(
            tenant_id=request.tenant_id,
            user_id=user_id,
            key_id=str(key["id"]),
            api_key=str(key["key"]),
        )
        self._access[request.tenant_id] = access
        return access

    def offboard(self, tenant_id: str) -> OffboardingResult:
        access = self._access.get(tenant_id)
        if access is None:
            raise KeyError(tenant_id)

        user_deleted = False
        key_revoked = False
        first_error: Exception | None = None
        try:
            self.infrai.delete_user(access.user_id)
            user_deleted = True
        except (InfraiError, InfraiTransportError) as exc:
            first_error = exc
        try:
            self.infrai.revoke_key(access.key_id)
            key_revoked = True
        except (InfraiError, InfraiTransportError) as exc:
            if first_error is None:
                first_error = exc

        if first_error is not None:
            raise first_error
        del self._access[tenant_id]
        return OffboardingResult(
            tenant_id=tenant_id,
            user_deleted=user_deleted,
            key_revoked=key_revoked,
        )

    def record_event(self, tenant_id: str, event: ShipmentEvent) -> ShipmentEvent:
        if tenant_id not in self._access:
            raise KeyError(tenant_id)
        self._events.setdefault(tenant_id, []).append(event)
        return event


def create_app(infrai: Any = None) -> FastAPI:
    registry = TenantRegistry(infrai or EnvironmentInfrai())
    app = FastAPI(title="Tenant Logistics Access")

    @app.exception_handler(InfraiError)
    async def handle_infrai_error(_, exc: InfraiError):  # type: ignore[no-untyped-def]
        from fastapi.responses import JSONResponse

        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        return JSONResponse(status_code=status, content={"error": exc.code, "detail": exc.detail})

    @app.post("/tenants", response_model=TenantAccess, status_code=201)
    def onboard(request: TenantOnboarding) -> TenantAccess:
        return registry.onboard(request)

    @app.delete("/tenants/{tenant_id}", response_model=OffboardingResult)
    def offboard(tenant_id: str) -> OffboardingResult:
        try:
            return registry.offboard(tenant_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="tenant not found") from exc

    @app.post("/tenants/{tenant_id}/shipment-events", response_model=ShipmentEvent)
    def record_event(tenant_id: str, event: ShipmentEvent) -> ShipmentEvent:
        try:
            return registry.record_event(tenant_id, event)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="tenant not found") from exc

    return app


app = create_app()
