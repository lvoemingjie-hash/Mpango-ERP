# DC-10K Finance Receivables Runtime Fix

Date: 2026-07-13

## Baseline

- Base branch: `origin/product-dev-recovered`
- Base commit: `3dd881165f30aae283cf99bb830125293e1b963a`
- Work branch: `codex/dc10k-finance-receivables-runtime-fix-2026-07-13`

## Customer Symptom

Opening the sidebar Money page produced HTTP 500 and the frontend message:
`Could not load accounts receivable data. Check your connection and try again.`

The Finance page loads summary, receivables summary, and receivable orders in
one request group. A failure in any member makes the page unavailable.

## Root Cause

`ReceivablesService.list_receivable_orders` subtracted a PostgreSQL
timezone-aware `TIMESTAMPTZ` value from `datetime.utcnow()`, which is naive.
The real PostgreSQL regression failed before the fix with:

`TypeError: can't subtract offset-naive and offset-aware datetimes`

The legacy receivables endpoint had the same unsafe age calculation.

The investigation also found that public receivable binding queries were not
scoped by the current wholesaler. This could mix another wholesaler's binding
balance or retailer name into the current tenant's Finance view.

## Fix

- Normalize order timestamps to UTC before calculating non-negative age days.
- Apply the same helper to the legacy receivables endpoint.
- Require the authenticated wholesaler ID in both receivables service methods.
- Scope tenant orders and public binding/name queries by that wholesaler ID.
- Preserve existing response shapes, permissions, and read-only behavior.
- Rename the sidebar label from `Money` to `Finance`; the `/finance` route is
  unchanged.

## Regression Evidence

- RED real PostgreSQL proof reproduced the exact naive/aware `TypeError`.
- DC-10K real PostgreSQL tests: `2 passed`.
- Finance service/API tests plus DC-10K tests: `40 passed`.
- Finance, payment, ledger, and route-policy gate: `147 passed, 1 xfailed`.
- Frontend S5-B real-user sidebar smoke: `1 passed`.
- Frontend production build: passed, with existing duplicate-jsdom and chunk
  size warnings only.
- Fresh Alembic upgrade: passed; single head remains
  `032_payment_method_integrity`.

The existing mock-only Finance tests passed before the fix because their
timestamps were naive. The new tests use real PostgreSQL `TIMESTAMPTZ` values
and real public binding rows.

## Scope And Safety

- No migration.
- No finance response contract change.
- No payment, ledger, auth, RBAC, export, deployment, or configuration change.
- No package or lockfile change.
- No production/VPS access.
- No secrets, tokens, passwords, or production data were read or printed.

## Verdict

`PASS_FOR_CTO_DC10K_REVIEW`

The source-level Finance 500 path is closed and tenant scoping is enforced.
Production remains unchanged until this isolated branch is reviewed, merged,
and redeployed for exact runtime verification.
