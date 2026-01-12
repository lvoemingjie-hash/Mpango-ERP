# Non-functional & Ops Spec (MVP)

## 1. Availability, RPO/RTO, SLO
### 1.1 Targets (default for MVP)
- RPO (data loss): 1 hour.
- RTO (service restore): 4 hours.
- API availability (monthly): 99.5%.

### 1.2 Assumptions
- Single region deployment for MVP.
- Multi-tenancy is schema-per-tenant.

## 2. Environments & Configuration
### 2.1 Environments
- local: docker compose
- staging: production-like, smaller scale
- production: live

### 2.2 Configuration & secrets
- Use AWS Secrets Manager for runtime secrets; GitHub Secrets for CI/CD only.
- Secrets MUST NOT be committed to repo.
- Required secrets (minimum):
  - DATABASE_URL
  - JWT_SECRET_KEY
  - JWT_ALGORITHM
  - REDIS_URL
  - S3_BUCKET / S3 credentials or IAM role (IRSA)
- Rotation:
  - JWT secret: rotate every 90 days.
  - DB password: rotate every 90 days.

## 3. Security Requirements
### 3.1 Transport & auth
- All external traffic over HTTPS (TLS 1.2+).
- JWT access tokens are short-lived; refresh tokens supported.
- Tenant is derived from JWT claims only.

### 3.2 Authorization
- RBAC enforced on every protected endpoint.
- Default roles: admin, sales, warehouse, finance.

### 3.3 Data protection
- PII fields should be treated as sensitive.
- Never log passwords, tokens, full card data, or full secrets.

## 4. Logging, Metrics, Tracing
### 4.1 Logging (structured)
- Backend logs MUST be JSON to stdout.
- Minimum log fields:
  - timestamp, level, service, env
  - request_id / correlation_id
  - tenant_id, user_id
  - path, method, status_code, latency_ms
  - error_code (for handled business exceptions)
- PII logging rule:
  - Do not log: password, passwordhash, JWT, full phone/address

### 4.2 Metrics (CloudWatch)
- HTTP: request_count, p50/p95 latency, 4xx rate, 5xx rate
- DB: connection count, slow query count
- Worker: queue depth, task success/failure, task latency
- Business: orders_created_count, purchase_orders_created_count

### 4.3 Tracing
- Enable AWS X-Ray for backend request traces.
- Propagate request_id across API -> worker tasks.

## 5. Backup, Restore, Disaster Recovery
### 5.1 Database backup
- Production: Daily snapshots, retention 14 days, PITR enabled.
- Staging: Daily snapshots, retention 7 days.

### 5.2 Restore procedure
1) Identify restore point timestamp.
2) Restore DB to new endpoint.
3) Update DATABASE_URL.
4) Run smoke tests.
5) Cut over traffic.

## 6. Database Ops & Migrations
### 6.1 Migration toolchain
- Alembic is the single source of truth for schema changes.
- All migrations must be reviewed and applied through CI/CD.
- No manual schema changes in production.

### 6.2 Multi-tenant migrations
- Each tenant schema requires running migrations.
- Provisioning must: create schema, apply migrations, seed RBAC.

## 7. Job & Queue Ops (Redis/Celery)
- Redis is used as broker/cache; Celery workers process async tasks.
- Tasks must be idempotent where possible.
- Retries with exponential backoff for transient failures.

## 8. File Storage (S3)
- Use S3 for file uploads/import artifacts.
- Bucket policy: private by default.
- Object naming: `tenant/<tenant_id>/imports/<job_id>.csv`

## 9. CI/CD & Release Management
### 9.1 CI gates
- Lint + type check + tests must pass before merge.
- Minimum coverage targets per CI/CD contract.

### 9.2 Release strategy (MVP)
- Staging deploy on merges to develop.
- Production deploy on main with manual approval.
- Rollback: redeploy previous container tag.

## 10. Incident response (MVP)
### 10.1 Alerting
- Alerts to Slack on: 5xx spike, p95 latency spike, worker failures, DB failures.

### 10.2 Severity levels
- SEV-1: system down / cannot login / cannot create orders
- SEV-2: partial outage / degraded performance
- SEV-3: minor bug / workaround exists

### 10.3 Post-incident
- Postmortem required for SEV-1 and SEV-2.

## 11. Audit & Compliance (MVP minimal)
- Record critical operations in audit logs:
  - user login attempts
  - role assignments
  - inventory adjustments
  - order confirmation/cancellation
  - inbound receiving
- Minimum audit fields:
  - tenant_id, user_id, action, entity_type, entity_id, timestamp, request_id
