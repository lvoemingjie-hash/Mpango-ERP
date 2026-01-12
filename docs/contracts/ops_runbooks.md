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
- Tenant strategy: schema-per-tenant

---

## 1. Deploy & rollback (ECS)

### 1.1 Release artifacts
- Docker image tag format: `vX.Y.Z-<commit-sha>`
- Two ECS services use the same image tag, but can be deployed independently.

### 1.2 Deploy to staging
#### Deploy backend-service only
1) Update ECS service `backend-service` task definition to new image tag.
2) Rolling update.
3) Run smoke tests.

#### Deploy worker-service only
1) Update ECS service `worker-service` task definition to new image tag.
2) Rolling update.
3) Verify queue health.

### 1.3 Deploy to production
- Trigger: merge to main + manual approval.
- Recommended order: backend-service first, then worker-service.

### 1.4 Rollback
- Redeploy to previous stable image tag.
- Run smoke tests.
- Confirm error rate and latency return to baseline.

### 1.5 Smoke test checklist
- Auth: Login with valid tenant_code + admin user -> 200 and JWT returned.
- API health: Basic GET endpoints return 200.
- Multi-tenancy sanity: Token claims include tenant_id and tenant_schema.
- RBAC sanity: Non-admin role calling admin-only endpoint returns 403.

---

## 2. Scaling runbook

### 2.0 Pre-scaling checklist
Before scaling:
1) Confirm DB_max_connections.
2) Confirm current backend/worker desired_count.
3) Confirm connection pool settings.
4) Apply the guardrail in Section 2.3.

### 2.1 Scale worker-service
Use case: heavy imports / long jobs.
- Increase desired count.
- Verify queue depth trends down.

### 2.2 Scale backend-service
- Increase desired count if p95 latency rises or 5xx due to timeouts.

### 2.3 Scaling guardrails
```
(backend_max_instances × backend_connections_per_instance + 
 worker_max_instances × worker_connections_per_instance) 
 <= DB_max_connections × 0.70
```

---

## 3. Tenant provisioning (schema-per-tenant)

### 3.1 Inputs
- tenant_code (Wholesaler.code): `^[A-Z0-9]+$`, globally unique.
- Wholesaler metadata
- Admin user credentials

### 3.2 Provisioning steps

#### Step A — Create wholesaler record (public schema)
- Insert into `public.wholesalers`: id, code, name, plan_type, timestamps

#### Step B — Compute tenant_schema
- Rule: `t_<uuid_without_dashes>` derived from wholesaler.id.

#### Step C — Create schema
- `CREATE SCHEMA IF NOT EXISTS "<TENANT_SCHEMA>";`

#### Step D — Run Alembic migrations
- `alembic upgrade head -x tenant_schema=<TENANT_SCHEMA>`

#### Step E — Seed RBAC baseline
- Create roles: admin, sales, warehouse, finance
- Insert permissions and role-permission mappings

#### Step F — Create first admin user
- Create user record and link to admin role.
- Verify login returns JWT with tenant claims.

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
- Restart worker-service only.
- If specific job failing: disable triggering API feature temporarily.

---

## 5. Database backup & restore drill

### 5.1 Default backup policy (MVP)
- Production: Daily snapshots, retention 14 days, PITR enabled.
- Staging: Daily snapshots, retention 7 days.

### 5.2 Monthly restore drill (staging)
1) Select restore point.
2) Restore DB to new endpoint.
3) Point staging services to restored DATABASE_URL.
4) Redeploy both services.
5) Run smoke tests.
6) Document timestamps and outcomes.

---

## 6. Incident triage (quick)

### 6.1 API 5xx spike
- Check: correlated with backend-service deploy? DB connectivity?
- Actions: rollback backend-service first.

### 6.2 Worker backlog spike
- Check: worker-service deploy? Redis health?
- Actions: scale worker-service, rollback if deploy correlated.

### 6.3 DB connection exhaustion
- Check: recent scaling changes? worker concurrency too high?
- Actions: reduce worker-service desired_count, reduce concurrency.

---

## 7. Operational checklists

### 7.1 Pre-deploy
- CI green.
- Migration reviewed.
- Secrets present and correct.
- Decide deploy scope.

### 7.2 Post-deploy
- Smoke tests passed.
- Error rate and p95 latency normal.
- Worker queue stable.
- RBAC spot-check.

### 7.3 Monthly
- Staging restore drill completed.
- Secrets rotation review.
