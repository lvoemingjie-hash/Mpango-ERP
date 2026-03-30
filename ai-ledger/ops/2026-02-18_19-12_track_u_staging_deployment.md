# Track U — Staging Deployment Report

**Date**: 2026-02-18 19:12 (UTC+08:00)  
**Engineer**: Senior DevOps Engineer  
**Scope**: v0.2.0 candidate UI → Staging environment  
**Boot Contract**: Acknowledged ✅

---

## Executive Summary

| 项目 | 状态 |
|------|------|
| Backend build check (`poetry check`) | ✅ PASS |
| Frontend build check (`tsc --noEmit`) | ✅ PASS (12 errors fixed) |
| Docker staging deployment | ✅ ALL 5 SERVICES HEALTHY |
| Boot Contract evidence (`/health` → 200) | ✅ PASS |

---

## Task 1: Health Check & Build

### Backend — `poetry check`

```
Exit code: 0
Warnings only (pyproject.toml deprecation notices — non-blocking)
```

### Frontend — `tsc --noEmit`

**Initial run**: 12 errors across 5 files.  
**After fix**: 0 errors, exit code 0.

| File | Error | Fix |
|------|-------|-----|
| `components/ui/Skeleton.tsx` | `style` prop not in `SkeletonProps` | Added `style?: React.CSSProperties` |
| `components/ui/StatusBadge.tsx` | Unused `React` import (TS6133) | Removed import |
| `pages/DashboardPage.tsx` | `stocks` declared but never read (TS6133) | Prefixed with `_` |
| `pages/DashboardPage.tsx` | `p.label` not on `ChartDataPoint` (TS2339) | Changed to `p.date` |
| `pages/DashboardPage.tsx` | `o.code` not on `Order` (TS2339) | Changed to `o.id.slice(0, 8)` |
| `pages/DashboardPage.tsx` | `o.customer_name` not on `Order` (TS2339) | Changed to `o.retailer_name ?? '—'` |
| `pages/DashboardPage.tsx` | `o.currency` not on `Order` (TS2339) | Used local `currency` state |
| `pages/inventory/InventoryPage.tsx` | `s.id` not on `StockView` (TS2339) | Changed to `s.sku_id` |
| `pages/orders/OrderListPage.tsx` | Unused `ORDER_STATUS_LABELS` (TS6133) | Removed from import |
| `pages/orders/OrderListPage.tsx` | `o.code` not on `Order` (TS2339) | Changed to `o.id.slice(0, 8)` |
| `pages/orders/OrderListPage.tsx` | `o.customer_name` not on `Order` (TS2339) | Changed to `o.retailer_name ?? '—'` |
| `pages/orders/OrderListPage.tsx` | `o.currency` not on `Order` (TS2339) | Hardcoded `KES` |

---

## Task 2: Staging Deployment

### Issues Discovered & Fixed

#### 1. Missing `.env` variables

`docker-compose.prod.yml` uses `${VAR:?error}` strict interpolation. Three required vars were missing:

| Variable | Value Added | Reason |
|----------|-------------|--------|
| `POSTGRES_DB` | `mpango_erp` | Required by postgres service + backend DATABASE_URL |
| `MPANGO_ENV` | `production` | Required by backend service |
| `REPORTING_USER_PASSWORD` | `MpangoReporting2026!` | Required by backend reporting migration |

#### 2. Windows CRLF in `docker-entrypoint.sh`

**Symptom**: `exec ./docker-entrypoint.sh: no such file or directory`  
**Root cause**: Windows CRLF (`\r\n`) in shebang `#!/bin/sh\r` breaks exec.  
**Fix**: Added `sed -i 's/\r$//' docker-entrypoint.sh` in `backend/Dockerfile` before `chmod +x`.

#### 3. Missing `frontend` service in `docker-compose.prod.yml`

**Symptom**: Gateway nginx fails with `host not found in upstream "frontend:80"`  
**Root cause**: `nginx/gateway.conf` references `frontend:80` upstream but no frontend service existed in the prod compose file.  
**Fix**: Added `frontend` service block with build context `./frontend`, healthcheck, and added `frontend: condition: service_healthy` to gateway's `depends_on`.

#### 4. Alpine IPv6 healthcheck failure

**Symptom**: Frontend and gateway containers marked `unhealthy` despite nginx running.  
**Root cause**: `wget http://localhost:80/` in Alpine resolves `localhost` to `::1` (IPv6), but nginx binds `0.0.0.0` (IPv4 only) → connection refused.  
**Fix**: Changed all healthcheck URLs from `localhost` to `127.0.0.1` in:
- `frontend/Dockerfile`
- `docker-compose.prod.yml` (frontend healthcheck)
- `docker-compose.prod.yml` (gateway healthcheck)

### Final Service Status

```
NAME                   IMAGE                        STATUS                    PORTS
mpango_prod_postgres   postgres:15-alpine           Up 11 minutes (healthy)   5432/tcp
mpango_prod_redis      redis:7-alpine               Up 11 minutes (healthy)   6379/tcp
mpango_prod_backend    windsurfmpangoerp-backend     Up 6 minutes (healthy)    8000/tcp
mpango_prod_frontend   windsurfmpangoerp-frontend    Up 3 minutes (healthy)    80/tcp
mpango_prod_gateway    nginx:alpine                  Up 49 seconds (healthy)   0.0.0.0:80->80/tcp
```

### Boot Contract Evidence

```bash
# Command
Invoke-WebRequest -Uri http://localhost:80/health -UseBasicParsing

# Response (HTTP 200)
{"status":"healthy","service":"mpango-erp-backend","version":"0.1.0","timestamp":"2026-02-18T11:08:04.703096"}
```

```bash
# Command
Invoke-WebRequest -Uri http://localhost:80/health/live -UseBasicParsing

# Response (HTTP 200)
{"status":"healthy","service":"mpango-erp-backend","version":"0.1.0","timestamp":"2026-02-18T11:08:05.800246"}
```

### UI Verification

| Check | Evidence |
|-------|----------|
| Sidebar shows "Sales" | `Sidebar.tsx:22` → `{ label: 'Sales', path: '/orders', ... }` |
| Empty State on order list | `OrderListPage.tsx:147-157` → `<EmptyState title="Ready to make your first sale?" ...>` |
| SPA served via gateway | `http://localhost:80/` → 200, title "Mpango ERP - African Wholesale-Retail Management" |

---

## Files Modified

| File | Change |
|------|--------|
| `frontend/src/components/ui/Skeleton.tsx` | Added `style` prop to SkeletonProps |
| `frontend/src/components/ui/StatusBadge.tsx` | Removed unused `React` import |
| `frontend/src/pages/DashboardPage.tsx` | Fixed 5 type errors (unused var, missing fields) |
| `frontend/src/pages/inventory/InventoryPage.tsx` | `s.id` → `s.sku_id` |
| `frontend/src/pages/orders/OrderListPage.tsx` | Fixed 4 type errors (unused import, missing fields) |
| `backend/Dockerfile` | CRLF fix: `sed -i 's/\r$//' docker-entrypoint.sh` |
| `frontend/Dockerfile` | Healthcheck: `localhost` → `127.0.0.1` |
| `docker-compose.prod.yml` | Added frontend service, fixed all healthcheck URLs |
| `.env` | Added `POSTGRES_DB`, `MPANGO_ENV`, `REPORTING_USER_PASSWORD` |

---

## Recommendations

1. **Add `frontend` to `.env.example`** — document the new service's build requirements
2. **Root `.env` in VCS** — still tracked; should be `.gitignore`d with only `.env.example` committed
3. **Version bump** — backend still reports `v0.1.0` in health endpoint; update to `v0.2.0` before release tag
