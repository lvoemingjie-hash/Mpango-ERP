# MVP Operations and Incident Runbook

## Status and scope

This runbook is the minimum response plan for pre-pilot and MVP operation. It
does not claim that production alert delivery, backup restore, or rollback has
already been exercised. The merged baseline is not yet customer-delivery approved.

## Service map

| Component | Expected responsibility | First checks |
|---|---|---|
| nginx gateway | Single browser entry and API proxy | container status, gateway logs, upstream health |
| React frontend | Wholesaler, retailer, and platform UI | root page, static assets, configured API origin |
| FastAPI backend | Auth, business APIs, health and metrics | `/healthz`, `/readyz`, `/metrics`, structured logs |
| PostgreSQL | Public identity plus tenant business schemas | connectivity, active sessions, migration head, storage |
| Redis | Cache/jobs/coordination | ping, memory, queue/cache symptoms, selected DB |
| Email adapter | Verification, invitation and recovery delivery | provider/sink health, delivery result without exposing content |

## Current observability truth

- Prometheus scrape configuration exists and targets backend `/metrics`.
- `prometheus.yml` has no alert rule files and no Alertmanager target.
- Platform operations pages expose health/error/latency/resource views and
  incident closeout records, but they are not proof of external paging.
- No accepted evidence currently proves customer-facing alert delivery, a
  backup restore drill, or a production rollback drill.

Before customer use, close these release gates:

```text
ALERT_RULES_CONFIGURED=true
ALERT_DELIVERY_DRILL=PASS
BACKUP_RESTORE_DRILL=PASS
APPLICATION_ROLLBACK_DRILL=PASS
DATABASE_FORWARD_RECOVERY_PLAN=ACCEPTED
ON_CALL_OWNER_AND_ESCALATION=RECORDED
```

## Severity and response targets

| Severity | Examples | Initial response |
|---|---|---|
| SEV-1 | system unavailable, login impossible, cross-tenant exposure, corrupt financial writes | Freeze writes if safe, preserve evidence, notify CTO immediately, target response within 15 minutes |
| SEV-2 | major workflow unavailable, payment/order failures, sustained 5xx or latency | Contain affected feature, notify owner, target response within 30 minutes |
| SEV-3 | limited defect with safe workaround | Record, prioritize, and monitor during business hours |

Customer-impacting security, tenant isolation, payment, inventory, and data
integrity events are SEV-1 until evidence supports a lower classification.

## First-response checklist

1. Record UTC/local time, affected customer/tenant category, route, user-visible
   symptom, and the exact deployed SHA. Do not copy secrets or full customer data.
2. Confirm whether the issue is ongoing and whether writes are unsafe.
3. Check gateway, frontend, backend, PostgreSQL, Redis, and email adapter health.
4. Capture request/correlation IDs, sanitized logs, metrics window, migration
   head, container/image IDs, and configuration-name presence.
5. Separate product red, invalid environment, dependency/provider failure, and
   operator error. Do not reclassify without deterministic evidence.
6. Decide: continue service, disable one feature, roll back application, or
   invoke database recovery.
7. Keep an append-only event timeline and name the decision owner.

## Safe containment

- Prefer disabling the smallest unsafe entry point over taking the whole system down.
- Never manually edit tenant tables as an unrecorded incident workaround.
- Do not delete evidence, failed jobs, ledger rows, declarations, or audit records.
- Do not expose passwords, tokens, invitation codes, reset links, or connection URLs.
- If tenant isolation is uncertain, stop affected data access before diagnosis.
- If financial write integrity is uncertain, stop confirmation/settlement writes
  while preserving read-only customer access where safe.

## Application rollback

Application rollback means redeploying the last accepted immutable image/SHA. It
does not mean rewriting Git history.

1. Identify the last accepted deployed SHA and its image digest.
2. Confirm whether the newer release applied a migration.
3. If database shape remains backward compatible, redeploy the prior image.
4. Run health, login, tenant isolation, RBAC, order read, and finance read smoke checks.
5. Verify 5xx/latency trends and customer symptom recovery.
6. Record rollback time, operator, SHA/digest, and post-rollback evidence.

Never run an Alembic downgrade in a customer database solely because the
application was rolled back. Destructive or data-reversing migration recovery
requires a migration-specific plan and CTO approval.

## Database recovery

1. Stop unsafe writes and preserve the failed environment.
2. Identify the recovery point objective and exact incident window.
3. Restore to a new database/instance where possible; do not overwrite the only copy.
4. Verify public schema, tenant schema set, Alembic head, row counts, constraints,
   critical order/payment/ledger invariants, and login/RBAC behavior.
5. Rebind staging or a controlled validation environment first.
6. Cut over only after evidence review and an explicit decision.

The target policy is RPO 1 hour and RTO 4 hours, but targets are not evidence.
A timed restore drill must demonstrate whether they are achievable.

## Customer communication

Communicate known impact, containment, and next update time. Do not speculate on
root cause or promise data integrity before verification. For a corrected issue,
state what customers should retry and whether duplicate submissions are safe.

## Closure

SEV-1 and SEV-2 require:

- immutable incident timeline and evidence manifest;
- deterministic root-cause classification;
- customer impact and data-integrity assessment;
- remediation plus regression-test delta;
- rollback/restore outcome where used;
- follow-up owner and deadline;
- CTO closeout before evidence cleanup.

## Useful repository pointers

- Compose topology: `docker-compose.yml`
- Prometheus scrape config: `prometheus.yml`
- Health and metrics routes: `backend/api/app.py`, `backend/api/v1/health.py`
- Structured logging: `backend/core/structured_logging.py`
- Platform incident contracts: `backend/api/v1/platform/p24/`
- Historical deployment incidents: `docs/incidents/`
- Older detailed runbook contract: `docs/contracts/ops_runbooks.md`
