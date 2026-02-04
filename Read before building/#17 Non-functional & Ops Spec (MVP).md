# Non-functional & Ops Spec (MVP)

## 1. Availability, RPO/RTO, SLO
### 1.1 Targets (default for MVP)
- RPO (data loss): 1 hour.
- RTO (service restore): 4 hours.
- API availability (monthly): 99.5%.

### 1.2 Assumptions
- Single region deployment for MVP.
- Multi-tenancy is schema-per-tenant; cross-tenant operations are out of scope. (See Multi-Tenancy Spec)

## 2. Environments & Configuration
### 2.1 Environments
- local: docker compose
- staging: production-like, smaller scale
- production: live

### 2.2 Configuration & secrets
- Use AWS Secrets Manager for runtime secrets; GitHub Secrets for CI/CD only. [file:3]
- Secrets MUST NOT be committed to repo.
- Required secrets (minimum):
  - DATABASE_URL
  - JWT_SECRET_KEY
  - JWT_ALGORITHM
  - REDIS_URL
  - S3_BUCKET / S3 credentials or IAM role (IRSA)
- Rotation:
  - JWT secret: rotate every 90 days (MVP), with planned rollout window.
  - DB password: rotate every 90 days (or managed credentials when available).

## 3. Security Requirements
### 3.1 Transport & auth
- All external traffic over HTTPS (TLS 1.2+). [file:3]
- JWT access tokens are short-lived; refresh tokens supported per architecture. [file:3]
- Tenant is derived from JWT claims only; client-supplied tenant headers are not trusted. (See Multi-Tenancy Spec)

### 3.2 Authorization
- RBAC enforced on every protected endpoint (permission code required).
- Default roles: admin, sales, warehouse, finance. (See RBAC Matrix)

### 3.3 Data protection
- PII fields (phone, address, contact) should be treated as sensitive.
- Never log passwords, tokens, full card data, or full secrets.

## 4. Logging, Metrics, Tracing
### 4.1 Logging (structured)
- Backend logs MUST be JSON to stdout; collected by CloudWatch Logs in AWS. [file:3]
- Minimum log fields:
  - timestamp
  - level
  - service (e.g., backend-api, worker)
  - env (local/staging/prod)
  - request_id / correlation_id
  - tenant_id (or tenant_schema)
  - user_id (when authenticated)
  - path, method, status_code, latency_ms
  - error_code (for handled business exceptions)
- Log levels:
  - INFO for normal operations
  - WARN for retriable errors / unexpected conditions
  - ERROR for failed requests, worker task failures
- PII logging rule:
  - Do not log: password, passwordhash, JWT, full phone/address
  - Allow: masked identifiers (e.g., last 4 digits)

### 4.2 Metrics (CloudWatch)
- HTTP:
  - request_count by status_code
  - p50/p95 latency
  - 4xx rate, 5xx rate
- DB:
  - connection count
  - slow query count (if enabled)
- Worker (Celery):
  - queue depth
  - task success/failure
  - task latency
- Business (MVP minimal):
  - orders_created_count
  - purchase_orders_created_count
  - inventory_adjustments_count

### 4.3 Tracing
- Enable AWS X-Ray for backend request traces (sampling in prod). [file:3]
- Propagate a single request_id across API -> worker tasks.

## 5. Backup, Restore, Disaster Recovery
### 5.1 Database backup
- Production:
  - Automated daily snapshots with retention 14 days.
  - Point-in-time recovery (PITR) enabled (if supported by chosen DB service).
- Staging:
  - Daily snapshots with retention 7 days.

### 5.2 Restore procedure (runbook)
- Restore steps (high-level):
  1) Identify restore point timestamp.
  2) Restore DB cluster/instance to new endpoint.
  3) Update application DATABASE_URL to restored endpoint.
  4) Run smoke tests (login, list products, create order).
  5) Cut over traffic.
- Restore verification:
  - At least once per month in staging, simulate restore from production snapshot.

### 5.3 RPO/RTO alignment
- RPO 1 hour is met by PITR (preferred) or frequent snapshots.
- RTO 4 hours assumes:
  - Infra redeploy via IaC/CI-CD,
  - restore + smoke test + cutover within window.

## 6. Database Ops & Migrations
### 6.1 Migration toolchain
- Alembic is the single source of truth for schema changes. [file:15]
- All migrations must be reviewed and applied through CI/CD.
- No manual schema changes in production.

### 6.2 Multi-tenant migrations
- Each tenant schema requires running migrations.
- Provisioning must:
  - create schema
  - apply migrations to that schema
  - seed RBAC baseline data

### 6.3 Data integrity conventions
- UUID primary keys; created_at/updated_at; soft delete pattern where applicable. [file:15]
- Unique constraints for stable identifiers (e.g., code/email/sku) as defined in DB contract. [file:15]

## 7. Job & Queue Ops (Redis/Celery)
- Redis is used as broker/cache; Celery workers process asynchronous tasks. [file:3]
- Worker reliability:
  - tasks must be idempotent where possible (e.g., import jobs, inbound processing)
  - retries with exponential backoff for transient failures
- Observability:
  - task_id logged with request_id
  - failure logs include exception type and minimal context

## 8. File Storage (S3)
- Use S3 for file uploads/import artifacts (e.g., product catalog import). [file:3]
- Bucket policy:
  - private by default
  - presigned URLs for client uploads/downloads if needed
- Object naming:
  - prefix by tenant_id and purpose (e.g., `tenant/<tenant_id>/imports/<job_id>.csv`)

## 9. CI/CD & Release Management
### 9.1 CI gates
- Lint + type check + tests must pass before merge to main/develop. [file:6]
- Minimum coverage targets per CI/CD contract. [file:6]

### 9.2 Release strategy (MVP)
- Staging deploy on merges to develop; production deploy on main with manual approval.
- Rollback:
  - Application rollback: redeploy previous container tag.
  - DB rollback: avoid destructive migrations; prefer forward-fix.
  - Emergency: restore DB snapshot if needed (see restore runbook).

## 10. Incident response (MVP)
### 10.1 Alerting
- Alerts to Slack channel (dev-alerts) on:
  - 5xx rate spike
  - p95 latency spike
  - worker task failure spike
  - DB connectivity failures [file:6]

### 10.2 Severity levels
- SEV-1: system down / cannot login / cannot create orders
- SEV-2: partial outage / degraded performance
- SEV-3: minor bug / workaround exists

### 10.3 Post-incident
- Postmortem required for SEV-1 and SEV-2:
  - timeline
  - root cause
  - corrective actions
  - prevention tasks

## 11. Audit & Compliance (MVP minimal)
- Record critical operations in audit logs (can be a table or log stream):
  - user login attempts
  - role assignments
  - inventory adjustments
  - order confirmation/cancellation
  - inbound receiving
- Minimum audit fields:
  - tenant_id
  - user_id
  - action
  - entity_type
  - entity_id
  - timestamp
  - request_id
