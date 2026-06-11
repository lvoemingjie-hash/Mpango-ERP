# R-8A-R1 Gateway Route Polish — Correction for CTO External Review

**Date:** 2026-06-10
**Operator:** opencode
**Branch:** `ops/r8a-gateway-route-polish-2026-06-10` (from `origin/product-dev-recovered`)
**Commit:** `4728589`
**Modified files:** `nginx/gateway.conf` only
**Final Verdict:** **READY_FOR_CTO_GATEWAY_ROUTE_REVIEW**

---

## Background

CTO external review of the MVP deployment at `http://1.14.247.12` found:

| Endpoint | Expected | Actual | Result |
|----------|----------|--------|--------|
| `http://1.14.247.12/` | Frontend SPA HTML | Frontend SPA HTML | ✅ PASS |
| `http://1.14.247.12/health` | Backend health JSON | `{"status":"healthy"}` | ✅ PASS |
| `http://1.14.247.12/openapi.json` | OpenAPI JSON spec | Frontend SPA index.html | ❌ FAIL |
| `http://1.14.247.12/docs` | Swagger UI HTML | Frontend SPA index.html | ❌ FAIL |

**Root cause:** The nginx gateway at `nginx/gateway.conf` had no explicit routing for `/openapi.json`, `/docs`, or `/redoc`. These paths fell through to the catch-all `location /` block which proxies to the frontend nginx, which serves `index.html` for any unmatched route.

---

## Fix Applied

**File:** `nginx/gateway.conf` (`ops/r8a-gateway-route-polish-2026-06-10` branch)

Added three new `location` blocks before the catch-all `location /`:

```nginx
location /openapi.json {
    proxy_pass http://backend_upstream;
}

location /docs {
    proxy_pass http://backend_upstream;
}

location /redoc {
    proxy_pass http://backend_upstream;
}
```

**Config syntax validated:** `docker compose -f docker-compose.prod.yml config --services` exits 0.
`nginx -t` reports valid syntax (only warning is `host not found in upstream "backend:8000"`, expected outside Docker network).

---

## Scope of Change

| Item | Status |
|------|--------|
| Files modified | `nginx/gateway.conf` only |
| Lines changed | +16 new location blocks, updated header comment |
| Backend code | NOT modified ✅ |
| Frontend code | NOT modified ✅ |
| Database | NOT modified ✅ |
| `.env.prod` | NOT modified ✅ |
| Migration | NOT executed ✅ |
| Volume prune | NOT executed ✅ |
| India VPS | NOT connected ✅ |

---

## Deployment Instructions (for CTO)

1. **Review** the fix branch:
   ```
   git fetch origin
   git log origin/ops/r8a-gateway-route-polish-2026-06-10
   git diff origin/product-dev-recovered..origin/ops/r8a-gateway-route-polish-2026-06-10
   ```

2. **SSH into VPS** and apply:
   ```bash
   ssh ubuntu@1.14.247.12
   cd /opt/mpango-erp
   git fetch origin
   git checkout origin/ops/r8a-gateway-route-polish-2026-06-10 -- nginx/gateway.conf
   docker compose --env-file .env.prod up -d --no-deps gateway
   ```

3. **Verify:**
   ```bash
   curl -s http://1.14.247.12/openapi.json | head -20    # Should show JSON spec
   curl -sI http://1.14.247.12/openapi.json | head -5     # Content-Type: application/json
   curl -s http://1.14.247.12/docs | head -10             # Should show Swagger UI HTML
   curl -s http://1.14.247.12/health                       # Still returns health JSON
   curl -s http://1.14.247.12/ | head -5                  # Still returns frontend SPA
   ```

4. **Approve** and update verdict to:
   - `GATEWAY_ROUTE_POLISHED` (if all pass)
   - or `BLOCKED_GATEWAY_ROUTE_POLISH` (if any fail)

---

---

## R-8A Apply on Tencent VPS (2026-06-11 02:30 UTC)

### Pre-Apply Safety Gate

| Check | Result |
|-------|--------|
| HEAD before apply | `b8a31f8` ✅ |
| `git status --short` | Empty ✅ |
| Containers pre-apply | 5/5 healthy ✅ |
| `/health` pre-apply | `{"status":"healthy"}` ✅ |

### Fetch and Checkout

| Action | Result |
|--------|--------|
| `git fetch origin product-dev-recovered` | `b8a31f8..11e4287` ✅ |
| `git checkout --detach 11e4287` | HEAD now at `11e4287 merge: gateway route polish for docs and OpenAPI` ✅ |
| `git status --short` | Empty ✅ |
| `nginx/gateway.conf` has `/openapi.json` route | 2 occurrences (header + location) ✅ |
| `nginx/gateway.conf` has `/docs` route | 1 occurrence ✅ |
| `nginx/gateway.conf` has `/redoc` route | 1 occurrence ✅ |

### Nginx Config Validation

| Check | Result |
|-------|--------|
| `docker compose exec gateway nginx -t` | `syntax is ok` / `test is successful` ✅ |

### Gateway Reload/Recreate

| Attempt | Result |
|---------|--------|
| `docker compose exec gateway nginx -s reload` | Signal sent, but config did NOT take effect (old routes still served) |
| `docker compose up -d --no-deps --force-recreate gateway` | Gateway container recreated, new config loaded ✅ |

**Only gateway was recreated.** Backend, frontend, postgres, and redis were untouched (all still showing `17 hours ago` uptime).

### External Verification

| Endpoint | Expected | Actual | Result |
|----------|----------|--------|--------|
| `http://127.0.0.1/openapi.json` | JSON spec | `{"openapi":"3.1.0","info":{"title":"Mpango ERP API"`... Content-Type: `application/json` | ✅ PASS |
| `http://1.14.247.12/openapi.json` | JSON spec | `{"openapi":"3.1.0","info":{"title":"Mpango ERP API"`... Content-Type: `application/json` | ✅ PASS |
| `http://127.0.0.1/docs` | Swagger UI | `<!DOCTYPE html><html><head><link...swagger-ui.css>` | ✅ PASS |
| `http://1.14.247.12/docs` | Swagger UI | `<!DOCTYPE html><html><head><link...swagger-ui.css>` | ✅ PASS |
| `http://127.0.0.1/health` | Health JSON | `{"status":"healthy"}` | ✅ PASS |
| `http://1.14.247.12/health` | Health JSON | `{"status":"healthy"}` | ✅ PASS |
| `http://127.0.0.1/` | Frontend SPA | Frontend SPA HTML | ✅ PASS |
| `http://1.14.247.12/` | Frontend SPA | Frontend SPA HTML | ✅ PASS |
| Container health after apply | 5/5 healthy | 5/5 healthy (gateway recreated, others untouched) | ✅ PASS |

### Compliance Confirmation

| Requirement | Status |
|-------------|--------|
| No DB migration | ✅ |
| No volume deletion | ✅ |
| No prune/cleanup | ✅ |
| No secrets printed | ✅ |
| No India VPS | ✅ |
| No product code modified | ✅ |
| No backend/frontend/postgres/redis rebuilt | ✅ |
| Only gateway container recreated | ✅ |

---

## Final Verdict

**GATEWAY_ROUTE_POLISHED**

All gateway route polish objectives achieved:
1. `/openapi.json` now returns OpenAPI JSON spec (Content-Type: application/json) — both local and public
2. `/docs` now returns Swagger UI HTML — both local and public
3. `/health` unchanged — still returns backend health JSON
4. `/` unchanged — still returns frontend SPA HTML
5. Only gateway container was recreated; no other services touched
6. Product HEAD updated to `11e4287` on VPS

**Ready for CTO external re-review.** Do not proceed to DNS/HTTPS without CTO approval.
