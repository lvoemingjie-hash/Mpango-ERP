# U4-F-R2: Runtime Data Intake Browser Reproof

| Field | Value |
|---|---|
| **Date** | 2026-07-02 |
| **Target HEAD** | `e7caa48` (merge: U4-F-R1 intake transaction search path fix) |
| **Deployed Commit** | `1c2803d` + U4 intake files applied via diff |
| **Operator** | automated |
| **Environment** | Tencent VPS 1.14.247.12, prod stack |
| **Verdict** | **STOP_AND_REPORT_CTO** |

---

## STOP Condition Triggered

**Create workspace failed:** `PERMISSION_DENIED: Permission 'intake:create' required`

The `intake:create` permission does not exist in the `permissions` table. Intake permissions were defined in U4-A code but never seeded into the database. The admin user has 23 permissions, none intake-related.

---

## Preflight

| Check | Result |
|---|---|
| SSH to VPS | Connected |
| GitHub fetch | FAILED (SSH permission denied, HTTPS GnuTLS error) |
| Target commit `e7caa48` | Applied via diff from local machine |
| 5/5 containers healthy | YES |
| DB backup | `/tmp/u4fr2_pre_redeploy_20260702.sql.gz` (17,591 bytes, sha256 `a0c98f1...`) |
| SKU count before | 10 |

---

## Rebuild/Redeploy

| Step | Result |
|---|---|
| Backend rebuild | ✓ |
| Backend recreate | ✓ healthy |
| Gateway recreate | ✓ healthy |
| intake.py in container | ✓ (line 195: `create_workspace`) |
| intake_service.py in container | ✓ |
| Alembic 024 migration | ✓ (applied via direct SQL) |
| All 4 intake tables created | ✓ |

---

## Intake Tables Created

| Table | Status |
|---|---|
| intake_workspaces | ✓ created |
| intake_uploads | ✓ created |
| intake_product_rows | ✓ created |
| intake_validation_issues | ✓ created |

---

## API Proof (FAILED)

| Step | Result |
|---|---|
| Login | ✓ LOGIN_OK |
| Select tenant | ✓ TENANT_OK |
| Create workspace | ✗ **PERMISSION_DENIED**: `intake:create` required |
| Upload CSV | NOT REACHED |
| Validate | NOT REACHED |

---

## RBAC Status

**Admin permissions (23 total):**
`dashboard:read`, `dashboards:read`, `finance:read`, `inventory:read`, `inventory:update`, `inventory:write`, `invitations:create`, `invitations:read`, `ledger:read`, `orders:create`, `orders:read`, `orders:update`, `orders:write`, `payments:create`, `payments:read`, `payments:update`, `pricing:read`, `reports:read`, `retailers:read`, `skus:import`, `skus:read`, `users:create`, `users:read`, `wholesalers:read`, `wholesalers:write`

**Missing permissions:**
- `intake:create` — required for workspace creation
- `intake:read` — likely required for listing
- `intake:update` — likely required for mapping
- `intake:delete` — likely required for cleanup

---

## DB Verification

| Metric | Before | After | Changed |
|---|---|---|---|
| SKU count | 10 | 10 | NO (staging-only ✓) |
| Intake workspaces | 0 | 0 | NO (blocked by permission) |
| Intake uploads | 0 | 0 | NO (blocked by permission) |
| Intake product rows | 0 | 0 | NO (blocked by permission) |
| Intake validation issues | 0 | 0 | NO (blocked by permission) |

---

## Health

| Check | Result |
|---|---|
| mpango_prod_backend | ✓ healthy |
| mpango_prod_gateway | ✓ healthy |
| mpango_prod_frontend | ✓ healthy |
| mpango_prod_postgres | ✓ healthy |
| mpango_prod_redis | ✓ healthy |
| /health/live | 200 |
| /health/ready | 200 |

---

## Root Cause

U4-A defined intake permission constants in code (`backend/constants/permissions.py` or similar) but the permission seed script was not updated to include `intake:create`, `intake:read`, `intake:update`, `intake:delete` in the `permissions` table. Without these DB rows, the RBAC middleware rejects all intake API calls.

---

## Required Product Fix

1. Seed intake permissions into the `permissions` table for the TEST001 tenant
2. Assign intake permissions to the admin role
3. Re-run U4-F-R2 after permission fix

---

## Files

| File | Purpose |
|---|---|
| `ai-ledger/ops/2026-07-02_u4f_r2_runtime_data_intake_browser_reproof.md` | This report |

---

## Verdict

**STOP_AND_REPORT_CTO**

Create workspace blocked by missing `intake:create` permission. Intake permissions not seeded in DB. U4-F-R1 code fix is deployed and intake tables are created, but RBAC blocks all intake API calls. CTO approval required to seed intake permissions.
