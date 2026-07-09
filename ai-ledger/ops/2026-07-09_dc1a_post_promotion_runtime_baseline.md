# DC-1A: Post-Promotion Runtime Baseline

- **Date**: 2026-07-09
- **Target Commit**: `9bb2b3090c946d5edb6a4d17958fdebe9c5dd95f`
- **Verified By**: CTO
- **Ops Branch**: `ops/dc1a-post-promotion-runtime-baseline-2026-07-09`

## Summary

Full runtime baseline on VPS (`1.14.247.12`) at target commit `9bb2b30` after U6 onboarding chain passed end-to-end.

## Results

### Step 1: Preflight
- HEAD matches target `9bb2b30` ✅
- Git branch: `product-dev-recovered`

### Step 2: DB Backup
- Backup: `~/.secure-backups/mpango_erp_dc1a_20260709-210407.sql`
- Size: 309,157 bytes (301.9 KB)
- SHA256: `b512815d80cc...`

### Step 3: Exact Rebuild/Redeploy
- `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`
- Backend + frontend recreated ✅
- No code changes — exact commit rebuild

### Step 4: Container/Health Checks
- 5/5 containers healthy ✅
- `/health/live`: 200 ✅
- `/health/ready`: 200 ✅
- `/openapi.json`: 200 ✅
- Frontend `/`: 200 ✅
- Frontend `/docs`: 200 ✅

### Step 5: Alembic/DB Baseline
- Current: `030_platform_backup_status_source` ✅
- Single head ✅
- Version table matches ✅

### Step 6: U6 Onboarding Smoke
- Signup: 202 ✅
- Email verification: 200 ✅
- Provisioning: wholesaler + schema + setup token ✅
- Setup credential: 200 ✅
- Login: JWT returned ✅
- Select tenant: contextual JWT ✅
- /me: email, roles, permissions correct ✅
- SMTP delivery confirmed via 126.com ✅

### Step 7: Product Runtime Smoke
- SKUs: 200 ✅
- Wholesalers: 200 ✅
- Retailers: 200 ✅
- Orders: 200 ✅
- Inventory stocks: 200 ✅
- Inventory logs: 200 ✅
- Roles: 200 ✅
- Users: 200 ✅
- Payments: 200 ✅
- Intake workspaces: 200 ✅
- Dashboard KPI: 200 ✅

### Step 8: Platform Runtime Smoke
- Platform health: 200 ✅
- Platform info: 200 ✅
- No 500 errors across all endpoints ✅
- Auth boundary: tenant token correctly blocked from platform endpoints ✅

## Verdict

**PASS_EXACT_VPS_RUNTIME_BASELINE_READY_FOR_NEXT_PHASE**

All steps passed. Production at target commit `9bb2b30` is healthy and runtime-verified.

## Backup Location
`/home/ubuntu/.secure-backups/mpango_erp_dc1a_20260709-210407.sql` (309,157 bytes)
