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

## Final Verdict

**READY_FOR_CTO_GATEWAY_ROUTE_REVIEW**

The fix is a targeted 16-line addition to `nginx/gateway.conf`. No backend, frontend, database, env, or infrastructure changes. The branch is isolated from `product-dev-recovered` and ready for review.
