# DC-2B Exact VPS Delivery Candidate Runtime Recheck

Date: 2026-07-12
Ops branch: `ops/dc2b-exact-vps-delivery-runtime-recheck-2026-07-12`
Target: `origin/product-dev-recovered @ 1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`
VPS: `1.14.247.12`
Project dir: `/opt/mpango-erp`

## Scope

Runtime recheck was started for the delivery candidate after DC-2M2 merge. The task required a hard stop if any tracked file was dirty before checkout, especially `docker-compose.prod.yml`.

No deployment was performed. No VPS checkout was performed. No `.env.prod` values were read or printed. No database backup, compose config, container rebuild, Alembic migration, smoke test, or log scan was performed after the hard stop.

## Preflight Evidence

- SSH key login to VPS succeeded as `ubuntu`.
- `git fetch origin` completed on the VPS.
- `git rev-parse origin/product-dev-recovered` returned the required target SHA: `1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`.
- Tracked-clean check failed before checkout.

Tracked dirty output:

```text
 M docker-compose.prod.yml
```

## Hard Stop

Hard stop condition fired: tracked dirty file exists before checkout.

Dirty tracked file:

- `docker-compose.prod.yml`

This is explicitly called out by the task as a hard stop condition. Continuing would risk overwriting or masking environment-specific compose drift and would invalidate exact-candidate delivery evidence.

## Not Performed

- Database backup: not performed because preflight hard stop fired first.
- Exact checkout: not performed.
- `docker compose ... config -q`: not performed.
- `docker compose ... up -d --build`: not performed.
- Container health verification: not performed.
- Alembic head/current verification: not performed.
- Health smoke: not performed.
- Auth/onboarding smoke: not performed.
- Product smoke: not performed.
- DC-2M2 runtime schema proof: not performed.
- Backend log scan: not performed.

## Required Inclusion Checks

Could not be validated on VPS because the tracked dirty `docker-compose.prod.yml` hard stop fired before checkout and deploy.

- DC-2H SMTP compose wiring: not validated on VPS.
- DC-2M2 legacy tenant reconciliation migration: not validated on VPS.
- Alembic head `031_legacy_tenant_reconciliation`: not validated on VPS.

## Secret Handling

- No `.env.prod` values were read or printed.
- No database password, SMTP password, JWT, token, or backup contents were printed.
- No log lines were printed.

## Final Verdict

`STOP_AND_REPORT_CTO`

Reason: VPS tracked dirty preflight failure on `docker-compose.prod.yml`.
