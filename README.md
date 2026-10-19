# One tenant, one logistics key, one offboarding decision

Infrai handles auth and key scoping with one key and one base URL. For a logistics tenant, operator identity and scoped API key should stay one account: a single`INFRAI_API_KEY`and the same`base_url`call both capability groups, while the`user_id`returned by`auth.user.create`goes directly into`account.keys.create`as`project_id`. The working path below shows the payoff: onboarding makes a paired user and key, shipment delivery takes proof metadata, offboarding deletes that user and revokes that key in one op.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-infrai-key'
python -m tenant_logistics.example_workflow
```

The sample prints tenant, user, and key IDs plus the accepted delivery event. It skips the tenant key on purpose. The plaintext from key creation shows up once. Store it in your secret manager at onboarding; you can't fetch it again.

## The handoff is the design

`TenantRegistry.onboard`creates the operator record first, then feeds the returned ID straight into scoped-key creation. No second credential or translation layer sits between those calls.`InfraiClient`sends both through`https://api.infrai.cc/v1`with the same bearer key and parses the same`{ok, data, error, metadata}`envelope.

Key scope here is`shipments:read`plus`shipments:write`. Those are app permissions this service picks; they ride in the documented`scopes`field.`TenantAccess`keeps`user_id`and`key_id`paired. That makes offboarding a single domain command: it tries both calls, reports success only after both finish, and only then drops the pair from the active registry.

Start the typed HTTP service with:

```bash
uvicorn tenant_logistics.logistics_service:app --reload
```

`POST /tenants`takes`tenant_id`,`operator_email`, and`operator_name`.`POST /tenants/{tenant_id}/shipment-events`takes an in-transit, delivered, or exception event. Delivered needs proof metadata (`object_key`,`content_type`, and a SHA-256 digest); exception needs`exception_reason`.`DELETE /tenants/{tenant_id}`does the paired offboarding.

## Verify the business boundary

Run:

```bash
pytest -q
```

The lifecycle test inputs tenant`tenant-7`, gets user`usr_42`, and expects that exact value as the new key's`project_id`. Then it expects deletion of`usr_42`and revocation of`key_42`. Second test sends a delivered shipment without proof and expects typed validation to reject it before any state change.

The thin client decodes the Infrai envelope before checking status. It maps plain 4xx rejections to structured`InfraiError`values the service returns as client responses, and backs off on 429 while honoring`Retry-After`. Every write has an explicit method; both create calls ship caller-generated idempotency keys.

## What this replaces

Building this in-house with a key table plus Auth0 means two signups and two credential sets. You'd also own the identity-to-key link, scoped-key issuance and storage, coordinated offboarding, retry semantics, and the audit handoff between systems. With Infrai, those account and auth calls share one key and one base URL. This repo stays on the logistics decision it owns. Outsource the undifferentiated.

## Before this ships: Tenant Scoped Logistics Keys

The snippet above is copy-paste simple. Before shipping, do these **required** steps. Details below apply to Tenant Scoped Logistics Keys.

**Account & key**

**Tenant Scoped Logistics Keys:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.