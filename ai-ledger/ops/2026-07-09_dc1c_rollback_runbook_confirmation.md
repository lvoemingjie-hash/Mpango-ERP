# DC-1C-R1: Rollback Runbook Confirmation Gate (Clean)

- **Date**: 2026-07-09
- **Target Commit**: `9bb2b3090c946d5edb6a4d17958fdebe9c5dd95f`
- **Base Commit**: `76d62af465c70200792034adf8e54f9e26855e9e`
- **Verified By**: CTO
- **Ops Branch**: `ops/dc1c-r1-rollback-runbook-confirmation-clean-2026-07-09`

## Summary

Dry-run confirmation of rollback runbook for production at commit `9bb2b30`. No real restore executed. All secrets redacted.

## Dry-Run Verification Results

### 1. Backup Artifact ✅
- **Path**: `/home/ubuntu/.secure-backups/mpango_erp_dc1a_20260709-210407.sql`
- **Size**: 309,157 bytes (301.9 KB)
- **SHA256 prefix**: `b512815d80ccdb47`
- **Format**: PostgreSQL plain SQL dump (ASCII text)
- **Header**: `-- PostgreSQL database dump`
- **Readable**: ✅

### 2. Rollback Target Commit ✅
- **Commit**: `9bb2b3090c946d5edb6a4d17958fdebe9c5dd95f`
- **Type**: commit (resolvable)
- **Log**: `docs(g5-r1): remove promotion ledger trailing whitespace`
- **Branch**: `product-dev-recovered`
- **Diff from target to HEAD**: empty (current HEAD = target)

### 3. Docker Compose Config ✅
- **Config file**: `docker-compose.prod.yml`
- **Env file**: `.env.prod`
- **Parse result**: exit_code=0 (valid)

### 4. Restore Path ✅
- **DB container**: `mpango_prod_postgres` (postgres:15-alpine)
- **PG tools**: pg_dump, pg_restore, psql all available
- **psql version**: PostgreSQL 15.18
- **Target DB**: `mpango_erp` (user: `mpango`)

## Rollback Runbook

### Prerequisites
- SSH access to VPS `1.14.247.12` as `ubuntu`
- CTO explicit approval for production restore
- Database credentials from secure channel

### Step 1: Backup Current State (optional but recommended)
```bash
ssh ubuntu@<vps-ip>
cd /opt/mpango-erp
docker exec mpango_prod_postgres pg_dump -U mpango mpango_erp > ~/.secure-backups/mpango_erp_pre_rollback_$(date +%Y%m%d-%H%M%S).sql
```

### Step 2: Checkout Target Rollback Commit
```bash
cd /opt/mpango-erp
git fetch origin
git checkout 9bb2b3090c946d5edb6a4d17958fdebe9c5dd95f
```

### Step 3: Stop and Recreate Containers
```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod down
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

### Step 4: Restore Database
```bash
cat /home/ubuntu/.secure-backups/mpango_erp_dc1a_20260709-210407.sql | docker exec -i mpango_prod_postgres psql -U mpango -d mpango_erp
```

### Step 5: Verify Alembic/DB State
```bash
docker exec mpango_prod_backend alembic -c /app/alembic.ini heads
# Expected: 030_platform_backup_status_source
docker exec mpango_prod_backend alembic -c /app/alembic.ini current
# Expected: 030_platform_backup_status_source
```

### Step 6: Health Checks
```bash
# Container health
docker ps --format '{{.Names}} {{.Status}}'

# API health
curl -s http://localhost:80/health/live
curl -s http://localhost:80/health/ready

# OpenAPI
curl -s http://localhost:80/openapi.json | head -c 100
```

### Step 7: U6 Onboarding Smoke (minimum)
```bash
# Signup
curl -s -X POST http://localhost:80/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"rollback-test@example.com","password":"<password-from-secure-channel>"}'

# Verify email (use <token-from-email> from signup response)

# Login
curl -s -X POST http://localhost:80/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@mpango.xyz","password":"<password-from-secure-channel>"}'

# /me (use <jwt-redacted> from login response)
curl -s http://localhost:80/api/v1/auth/me -H "Authorization: Bearer <jwt-redacted>"
```

## Secrets Policy

- **Passwords**: Redacted as `<password-from-secure-channel>`
- **JWTs**: Redacted as `<jwt-redacted>`
- **Email verification tokens**: Redacted as `<token-from-email>`
- **DB credentials**: Not printed; referenced as "from secure channel"
- **SMTP credentials**: Not printed; stored only in `.env.prod` on VPS

## Stop Conditions

| Condition | Status |
|-----------|--------|
| Backup missing | ✅ PASS - backup exists |
| Backup checksum cannot be computed | ✅ PASS - SHA256 `b512815d80ccdb47` |
| Rollback target commit cannot be resolved | ✅ PASS - commit `9bb2b30` resolvable |
| Docker compose config invalid | ✅ PASS - config parses |
| Secret/JWT/password/token printed | ✅ PASS - all redacted |
| Real DB restore attempted | ✅ PASS - no restore executed |

## Verdict

**PASS_ROLLBACK_RUNBOOK_CONFIRMED**

All dry-run verifications passed. Rollback runbook is executable and ready for CTO approval. No secrets present in report.
