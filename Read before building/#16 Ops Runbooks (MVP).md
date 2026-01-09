# Ops Runbooks (MVP)

## 0. Scope & architecture assumptions
### 0.1 Scope
Operational runbooks for:
- ECS deployment (backend-service & worker-service)
- Tenant provisioning (schema-per-tenant)
- DB backup/restore drill
- Incident triage (API, DB, Redis/Celery)

### 0.2 Architecture assumptions (MVP)
- Same Docker image is used for both services, but deployed as two ECS services:
  - `backend-service`: FastAPI HTTP API
  - `worker-service`: Celery worker
- Shared infrastructure:
  - One PostgreSQL (Aurora/RDS)
  - One Redis used as broker + result backend
- Tenant strategy: schema-per-tenant (see Multi-Tenancy Spec). [file:3]

### 0.3 References
- Multi-Tenancy Spec (MVP) [file:20]
- RBAC Matrix (MVP)
- CI/CD Contract [file:6]
- Database Contract (Alembic conventions) [file:15]

---

## 1. Deploy & rollback (ECS)
### 1.1 Release artifacts
- Docker image tag format: `vX.Y.Z-<commit-sha>` (or similar). [file:6]
- Two ECS services use the same image tag, but can be deployed independently.

### 1.2 Deploy to staging
#### Deploy backend-service only (API changes, no worker impact)
1) Update ECS service `backend-service` task definition to new image tag.
2) Rolling update.
3) Run smoke tests (Section 1.5).
* Note (MVP frozen):
- Deployment strategy uses ECS rolling update only.
- CodeDeploy blue/green is out of scope for MVP.


#### Deploy worker-service only (job changes, no API restart)
1) Update ECS service `worker-service` task definition to new image tag.
2) Rolling update.
3) Verify queue health (Section 4).

#### Deploy both
- Deploy `backend-service` first, then `worker-service` (recommended).

### 1.3 Deploy to production
- Trigger: merge to main + manual approval (per CI/CD). [file:6]
- Recommended order:
  1) backend-service
  2) worker-service
- After each deploy: run the relevant verification steps.

### 1.4 Rollback
#### Rollback backend-service
- Redeploy `backend-service` to previous stable image tag.
- Run smoke tests.
- Confirm error rate and latency return to baseline.

#### Rollback worker-service
- Redeploy `worker-service` to previous stable image tag.
- Verify queue depth decreases and failures stop.

#### Rollback both
- Rollback backend-service first, then worker-service (to restore API compatibility first).

### 1.5 Smoke test checklist (minimum)
- Auth:
  - Login with valid tenant_code + admin user -> 200 and JWT returned.
- API health:
  - Basic GET endpoints return 200 (e.g., /docs in non-prod, /health if implemented).
- Multi-tenancy sanity:
  - Token claims include tenant_id and tenant_schema (spot-check).
- RBAC sanity:
  - A non-admin role calling an admin-only endpoint returns 403.

---

## 2. Scaling runbook

### 2.0 Pre-scaling checklist (required)
Before scaling backend-service or worker-service:
1) Confirm DB_max_connections (from DB parameter group / instance settings).
2) Confirm current backend/worker desired_count.
3) Confirm connection pool settings:
   - backend_connections_per_instance
   - worker_connections_per_instance
4) Confirm Celery concurrency:
   - `CELERY_WORKER_CONCURRENCY` (default = vCPU count)
5) Apply the guardrail in Section 2.3. If exceeded, do NOT scale up; reduce concurrency, reduce desired_count, or scale DB first.

### 2.1 Scale worker-service (typical)
Use case: heavy imports / OCR / procurement suggestions / long jobs.
- Increase desired count:
  - `worker-service desired_count: 2 -> 10`
- Verify:
  - Redis queue depth trends down
  - Task success rate normal
  - No DB connection exhaustion

Rollback:
- Reduce desired count back to baseline once backlog clears.

### 2.2 Scale backend-service (API throughput)
- Increase desired count for `backend-service` only if:
  - p95 latency rises
  - CPU/memory saturation
  - 5xx due to timeouts
- Verify:
  - p95 latency improves
  - 5xx rate decreases

### 2.3 Scaling guardrails (MVP)
- Watch DB connection limits when scaling either service.
- Prefer worker scaling before API scaling for async workloads.

- (backend_max_instances × backend_connections_per_instance + worker_max_instances × worker_connections_per_instance) <= DB_max_connections × 0.70

---

## 3. Tenant provisioning (schema-per-tenant)
### 3.1 Inputs
- tenant_code (Wholesaler.code): `^[A-Z0-9]+$`, globally unique. [file:20]
- Wholesaler metadata
- Admin user credentials

### 3.2 Provisioning steps
#### Step A — Create wholesaler record (public schema)
- Insert into `public.wholesalers`:
  - id (uuid), code, name, plan_type, timestamps
- Verify:
  - `SELECT id, code FROM public.wholesalers WHERE code = '<TENANT_CODE>';`

#### Step B — Compute tenant_schema
- Rule: `t_<uuid_without_dashes>` derived from wholesaler.id. [file:20]

#### Step C — Create schema
- `CREATE SCHEMA IF NOT EXISTS "<TENANT_SCHEMA>";`

#### Step D — Run Alembic migrations for tenant schema
- `alembic upgrade head -x tenant_schema=<TENANT_SCHEMA>` [file:20][file:15]
- Verify:
  - `SELECT * FROM "<TENANT_SCHEMA>".alembic_version;`

#### Step E — Seed RBAC baseline
- Create roles: admin, sales, warehouse, finance
- Insert permissions and role-permission mappings (admin = ALL). [file:15]
- Verify counts:
  - roles, permissions, role_permissions, user_roles

#### Step F — Create first admin user
- Create user record and link to admin role.
- Verify login returns JWT with tenant claims. [file:20]

### 3.3 Provisioning rollback
- If schema created but tenant unusable:
  - Prefer: disable tenant (soft delete / inactive) and fix forward.
  - Destructive drop schema only if confirmed empty:
    - `DROP SCHEMA "<TENANT_SCHEMA>" CASCADE;`

---

## 4. Redis/Celery worker operations
### 4.1 Symptoms
- Jobs not completing
- Queue depth increasing
- Worker errors in logs

### 4.2 Quick checks
- worker-service running tasks?
- recent deploy to worker-service?
- Redis connectivity errors?
- DB connection errors from worker?

### 4.3 Remediation
- Restart worker-service only:
  - force new deployment / restart tasks
- If a specific job is failing repeatedly:
  - disable the triggering API feature temporarily
  - hotfix task retry/backoff behavior
- Verify:
  - queue depth decreases
  - failure rate returns to baseline

---

## 5. Database backup & restore drill
### 5.1 Default backup policy (MVP)
- Production:
  - Daily snapshots, retention 14 days
  - PITR enabled if available
- Staging:
  - Daily snapshots, retention 7 days

### 5.2 Monthly restore drill (staging)
1) Select restore point (snapshot or point-in-time).
2) Restore DB to new endpoint (do not overwrite existing).
3) Point staging backend-service + worker-service to restored DATABASE_URL.
4) Redeploy both services (backend-service first, then worker-service).
5) Run smoke tests + a simple worker job (if available).
6) Document timestamps and outcomes (restore start/end, cutover time).

### 5.3 Emergency production restore (SEV-1)
1) Declare incident and stop risky changes (freeze deploys).
2) Consider temporarily disabling write-heavy endpoints if possible.
3) Restore DB to new endpoint.
4) Update secrets/config for DATABASE_URL.
5) Deploy backend-service then worker-service.
6) Smoke tests.
7) Postmortem.

---

## 6. Incident triage (quick)
### 6.1 API 5xx spike
- Check:
  - correlated with backend-service deploy?
  - DB connectivity?
- Actions:
  - rollback backend-service first
  - if still failing, check DB health / restore plan

### 6.2 Worker backlog spike
- Check:
  - worker-service deploy?
  - Redis health?
- Actions:
  - scale worker-service (Section 2.1)
  - rollback worker-service if deploy correlated

### 6.3 DB connection exhaustion
- Check:
  - recent scaling changes?
  - worker-service concurrency too high?
- Actions:
  - reduce worker-service desired_count
  - reduce worker concurrency (if configured)
  - scale DB if necessary

---

## 7. Operational checklists
### 7.1 Pre-deploy
- CI green (lint/type/tests/coverage). [file:6]
- Migration reviewed (no destructive change).
- Secrets present and correct per env.
- Decide deploy scope:
  - backend-service only / worker-service only / both

### 7.2 Post-deploy
- Smoke tests passed.
- Error rate and p95 latency normal.
- Worker queue stable.
- RBAC spot-check: expected 403s occur.

### 7.3 Monthly
- Staging restore drill completed.
- Secrets rotation review.
- Tenant provisioning dry-run in staging (optional).
