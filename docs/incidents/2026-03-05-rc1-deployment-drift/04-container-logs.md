# Container Logs - v0.2.1-rc1 Deployment

## Backend Logs (last 100 lines)
Key entries showing health checks and request logging:
- All /health and /health/live requests return 200 OK
- No 500 errors in recent logs
- Services running normally

## Postgres Logs (last 50 lines)
Key errors:
1. **2026-02-19 03:34:44** - `ERROR: relation "public.wholesalers" does not exist`
   - This occurred during initial setup before migrations ran

2. **2026-03-05 02:52:35** - `ERROR: type "order_status" does not exist`
   - This was the initial migration 016 failure (before the fix was deployed)

3. **2026-03-05 04:39:43** - `FATAL: database "mpango" does not exist`
   - Backend trying to connect to wrong database name (mpango instead of mpango_erp)

## Gateway Logs (last 30 lines)
- All /health requests return 200 OK
- No errors in gateway logs
- Gateway routing correctly to backend
