# DC-12R1-MVP-L1-PW1-R4-C1-R1-V2 — Official Provisioning Steps (Phase 3)

Date: 2026-08-20
Candidate: `f51c10943b5d1a67569d681e66a6d56e728860b4`
Mode: single clean run on a fresh empty database (no re-runs, no SQL writes).

## Scope

Provision four identities through the frozen candidate's real lifecycle and
consume them over real HTTP against `http://127.0.0.1:8000`:

| id | role | email | tenants |
|----|------|-------|---------|
| w1 | wholesaler owner (admin) | `pw1r4.w1.r4c1r1v2@pw1r4.dev` | single (own) |
| w2 | wholesaler owner (admin) | `pw1r4.w2.r4c1r1v2@pw1r4.dev` | single (own) |
| ra | retailer operator | `pw1r4.ra.r4c1r1v2@pw1r4.dev` | W1 + W2 (multi-tenant, 2 available tenants) |
| rb | retailer operator | `pw1r4.rb.r4c1r1v2@pw1r4.dev` | W1 only |

Canonical names: `PW1R1 Retailer A` (ra), `PW1R1 Retailer B` (rb).

## Method

- Signup + email-verification consume the **dev_sink** in-memory token capture
  mechanism of the frozen candidate (the same service functions that the HTTP
  endpoints wrap); no manual SQL, no hand-written verification codes.
- Every subsequent consumption step is a **real HTTP request** against
  `127.0.0.1:8000`:
  - `POST /api/v1/auth/setup-credential` → 200
  - `POST /api/v1/auth/login` → 200
  - `POST /api/v1/auth/select-tenant` → 200
  - `GET  /api/v1/auth/me` → 200
  - `POST /api/v1/retailers/register` → 201
  - `POST /api/v1/retailers/setup-credential` → 200 (after invitation token reissue)
  - `POST /api/v1/client/auth/login` → 200 (retailer portal)
- Negative paths confirmed: wholesaler wrong password → 401
  `INVALID_CREDENTIALS`; retailer portal wrong password → 401.

## Result

- **0 failed steps** (see `provision_evidence.json`; every step `ok: true`).
- Retailer login for ra at W1 returns exactly the canonical **six** permissions:
  `client:catalog:read`, `client:orders:read`, `client:orders:create`,
  `client:payments:read`, `client:payments:declare`, `client:finance:read`.
  Missing set is empty; `client:payments:declare` present.
- Tenant schemas (read-only inspection, excludes `t_dev`):
  - W1 `t_1d832289d9234eaab89d7b8a245c99d1` — 23 tables; roles `admin`,
    `retailer_operator`; 52 permissions.
  - W2 `t_b107b683f57b4ae1b0d833453b2ece45` — 23 tables; roles `admin`,
    `retailer_operator`; 52 permissions.

## Task-private identity material

Live credentials (including JWTs) live only in
`pw1r4b/provision/identities.json` (task-private, never committed, never in
reports). `provision_evidence.json` contains **no secrets**.