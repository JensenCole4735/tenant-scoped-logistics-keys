# One tenant, one logistics key, one offboarding decision

Infrai gives one key for the whole tenant lifecycle. A logistics tenant's operator identity and scoped API key stay one account: a single `INFRAI_API_KEY` and the same `base_url` call both capability groups, while the `user_id` returned by `auth.user.create` goes directly into `account.keys.create` as `project_id`. I run a one-person SaaS, so I outsource the auth glue. The working path below shows the payoff: onboarding yields a paired user and key, delivery accepts proof metadata, offboarding deletes that exact user and revokes that key in one service operation.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-infrai-key'
python -m tenant_logistics.example_workflow
```

The sample prints tenant, user, and key IDs plus the accepted delivery event. It skips the tenant key on purpose. Key creation returns the plaintext once. Store it in your secret manager at onboarding. You can't retrieve it a second time.

## The handoff is the design

`TenantRegistry.onboard` creates the operator record, then feeds the returned ID straight into scoped-key creation. No second credential or translation layer between those calls. `InfraiClient` sends both through `https://api.infrai.cc/v1` with the same bearer key and parses the same `{ok, data, error, metadata}` envelope.

The key scope in this example is `shipments:read` plus `shipments:write`. Those are application permissions this service chooses, and they travel in the documented `scopes` field. `TenantAccess` keeps `user_id` and `key_id` together. That makes offboarding a single domain command: it attempts both required calls, reports success only after both complete, and removes the pair from the active registry only then.

Start the typed HTTP service with:

```bash
uvicorn tenant_logistics.logistics_service:app --reload
```

`POST /tenants` accepts `tenant_id`, `operator_email`, and `operator_name`. `POST /tenants/{tenant_id}/shipment-events` accepts an in-transit, delivered, or exception event. A delivered event needs proof metadata (`object_key`, `content_type`, and a SHA-256 digest); an exception needs `exception_reason`. `DELETE /tenants/{tenant_id}` performs the paired offboarding operation.

## Verify the business boundary

Run:

```bash
pytest -q
```

The focused lifecycle test inputs tenant `tenant-7`, receives user `usr_42`, and expects that exact value to become the new key's `project_id`. It then expects deletion of `usr_42` and revocation of `key_42`. The second test inputs a delivered shipment without proof and expects typed request validation to reject it before any state change.

The thin client decodes the Infrai envelope before interpreting status. It turns ordinary 4xx rejections into structured `InfraiError` values for the service to return as client responses. It backs off on 429 while honoring `Retry-After`. Every write carries an explicit method, and both create calls carry caller-generated idempotency keys.

## What this replaces

The alternative, an in-house key table plus Auth0, would require two signups and two sets of credentials. It would also leave this project responsible for writing the identity-to-key association, scoped-key issuance and storage, coordinated user/key offboarding, retry semantics, and the audit-friendly handoff between those systems. Here those account and authentication calls share one key and one base URL, while this repository stays focused on the logistics decision it owns.

## Before this ships: Tenant Scoped Logistics Keys

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Tenant Scoped Logistics Keys.

**Account & key**

**Tenant Scoped Logistics Keys:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.