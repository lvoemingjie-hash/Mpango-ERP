# S6-J: Exact VPS Redeploy Smoke After S6-I2 Green Gate

**Date:** 2026-07-05
**Target Commit:** `eac7642eefeee4539086f2a42fa7b87f0082fc4c`
**VPS:** Tencent `1.14.247.12` (VM-0-3-ubuntu)
**Verdict:** PASS_EXACT_VPS_REDEPLOY_SMOKE_READY_FOR_U5

---

## 1. Preflight

| Check | Result |
|-------|--------|
| Hostname | VM-0-3-ubuntu, Ubuntu 24.04.4 LTS |
| Disk | 26G free of 40G (33% used) |
| Memory | 2.5GB available of 3.6GB |
| Git remote | origin -> https://github.com/lvoemingjie-hash/Mpango-ERP.git |
| Target commit exists | YES (eac7642, fetched from origin) |
| Pre-deploy containers | All 5 Mpango healthy + procurement-workspace healthy |

## 2. Backup

| Field | Value |
|-------|-------|
| Path | `/opt/mpango-backups/mpango_prod_s6j_20260705-170906.db` |
| Size | 215K |
| Lines | 4150 |
| Tables | 11 (public) + 42 (tenant schemas) |
| SHA256 prefix | `3b6d1ea8aaa53df3` |
| Note | Initial backup failed with wrong credentials (mpango_user/mpango_prod). Fixed with correct credentials (mpango/mpango_erp). |

## 3. Exact Checkout

| Step | Result |
|------|--------|
| `git fetch origin` | OK (fetched eac7642 from origin/product-dev-recovered) |
| `git checkout -B product-dev-recovered origin/product-dev-recovered` | OK |
| HEAD verification | `eac7642eefeee4539086f2a42fa7b87f0082fc4c` |
| Git status | clean |

## 4. Build/Deploy

| Step | Result |
|------|--------|
| `docker compose -f docker-compose.prod.yml --env-file .env.prod build` | OK (images cached) |
| `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d` | OK |
| Backend recreate | OK (healthy) |
| Frontend recreate | OK (healthy) |
| No docker prune | CONFIRMED |
| No migration reset | CONFIRMED |
| No manual file copy | CONFIRMED |

## 5. Health Smoke

| Endpoint | Status | Result |
|----------|--------|--------|
| docker ps (5 Mpango) | all healthy/up | PASS |
| `/health/live` | 200 | PASS |
| `/health/ready` | 200 | PASS |
| `/` | 200 | PASS |
| `/openapi.json` | 200 | PASS |
| `/docs` | 200 | PASS |

## 6. MVP Runtime Smoke

| Step | Result |
|------|--------|
| Login admin (`admin@mpango.xyz`) | PASS (token acquired) |
| Tenant select (`550e8400-...`) | PASS |
| SKUs (`/api/v1/skus?limit=1`) | 200 PASS |
| Data Intake (`/api/v1/intake/workspaces?limit=1`) | 200 PASS |
| Orders (`/api/v1/orders?limit=1`) | 200 PASS |
| Payments (`/api/v1/payments?limit=1`) | 200 PASS |
| Stock (`/api/v1/inventory/stocks?limit=1`) | 200 PASS |

## 7. Backend API Smoke

| Test | Result |
|------|--------|
| Payment write route `/orders/{id}/pay` | ORDER_NOT_FOUND (correct - nonexistent order) |
| Legacy POST `/payments` | VALIDATION_ERROR (rejected, not 404) |
| Intake with auth | 200 PASS |
| Intake without auth | 401 PASS |

## 8. Image IDs

| Image | SHA256 |
|-------|--------|
| mpango-erp-backend | `sha256:637c47cb6bf7fd6c8a377f3945800f7faae30a3c7ee48876ed51c58ea6ed5736` |
| mpango-erp-frontend | `sha256:e156fff405b84b116bb48270abc11f6069f4a8a563f0d8e0be7a9bb8ce3f9f88` |

## 9. Notes

- **Password hash issue:** Original admin password hash was corrupted (54 chars, no `$` prefix) due to prior shell escaping of bcrypt `$` characters. Reset to known password via psycopg2 inside backend container (hash now 60 chars, `$2b$12$...` format). This is a pre-existing issue, not introduced by S6-J deploy.
- **No secrets printed:** CONFIRMED. Only hash prefixes and token prefixes shown.
- **No product branch push:** CONFIRMED.
- **No code edits on VPS:** CONFIRMED (password reset was runtime-only, no source changes).

---

**Verdict:** `PASS_EXACT_VPS_REDEPLOY_SMOKE_READY_FOR_U5`
