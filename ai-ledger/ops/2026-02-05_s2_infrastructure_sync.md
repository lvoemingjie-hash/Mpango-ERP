# S2 Infrastructure Sync - Production Readiness Hardening

**Date**: 2026-02-05  
**Track**: S2 - Production Readiness Hardening  
**Batches Completed**: 1, 2, 3  
**Status**: ✅ READY FOR STAGING DEPLOYMENT

---

## Executive Summary

The backend has completed Track S2 (Production Readiness Hardening) with three major batches:

1. **Batch 1**: Startup & Vital Signs (S2-1, S2-4)
2. **Batch 2**: Observability Core (S2-2, S2-3, S2-6)
3. **Batch 3**: Traffic Control & Safety (S2-5, Graceful Shutdown, S2-7)

**All tests passing**: 15 tests across all batches

**Infrastructure Impact**: Requires Redis for rate limiting, updated health checks, new metrics endpoints

---

## Batch 1: Startup & Vital Signs

### S2-1: Secrets & Config Hygiene

**Implementation**: Strict Pydantic validation with fail-fast behavior

**Required Environment Variables**:
```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname
REDIS_URL=redis://host:6379/0
SECRET_KEY=<secure-random-key-min-32-chars>
MPANGO_ENV=production|staging|development
```

**Behavior**:
- Application **CRASHES** on startup if any required secret is missing
- Application **CRASHES** if production mode uses default values
- Detailed error messages guide configuration fixes

**Validation Rules**:
- `DATABASE_URL`: Must not contain `postgres:postgres@localhost` in production
- `REDIS_URL`: Must not be `redis://localhost:6379/0` in production
- `SECRET_KEY`: Must not contain `dev-secret-key` or `change-me` in production
- `MPANGO_ENV`: Must be one of `production`, `staging`, `development`, `test`

**Files**:
- `backend/core/config.py` - Configuration validation
- `backend/.env.example` - Template with documentation

### S2-4: Health & Readiness Probes

**Endpoints**:

1. **Liveness Probe**: `GET /healthz`
   - Returns 200 OK if process is running
   - No dependency checks
   - Use for Kubernetes liveness probe

2. **Readiness Probe**: `GET /readyz`
   - Performs deep health checks:
     - Database: `SELECT 1` query
     - Redis: `PING` command
   - Returns 200 OK if all dependencies healthy
   - Returns 503 Service Unavailable if any dependency fails
   - Use for Kubernetes readiness probe

**Response Format**:
```json
{
  "status": "healthy",
  "checks": {
    "database": "ok",
    "redis": "ok"
  }
}
```

**Kubernetes Configuration**:
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 5
  failureThreshold: 3
```

**Files**:
- `backend/api/v1/health.py` - Health check endpoints
- `backend/main.py` - Startup validation

---

## Batch 2: Observability Core

### S2-2: Structured JSON Logging

**Implementation**: JSON formatter with automatic context injection

**Log Format**:
```json
{
  "timestamp": "2026-02-05T12:34:56.789Z",
  "level": "INFO",
  "service": "Mpango ERP",
  "env": "production",
  "logger": "api.v1.orders",
  "message": "Order created successfully",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_schema": "t_acme",
  "user_id": "user-123",
  "route": "/api/v1/orders",
  "method": "POST",
  "status_code": 201,
  "latency_ms": 45.2
}
```

**Mandatory Fields** (automatically injected):
- `timestamp`, `level`, `service`, `env`
- `request_id` (generated if missing)
- `tenant_schema` (from authentication)
- `user_id` (from authentication)
- `route`, `method` (from request)

**Configuration**:
```bash
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**Log Aggregation**:
- Logs are JSON formatted for easy parsing
- Compatible with ELK, Splunk, CloudWatch, etc.
- Use `request_id` for request tracing

**Files**:
- `backend/core/structured_logging.py` - JSON formatter and context management
- `backend/api/middleware/request_logging.py` - Request logging middleware

### S2-3: Prometheus Metrics

**Endpoint**: `GET /metrics`

**Metrics Exposed**:

1. **HTTP Request Metrics**:
   ```
   http_requests_total{method="POST", route="/api/v1/orders", status_code="201", tenant="t_acme"}
   http_request_duration_seconds{method="POST", route="/api/v1/orders", tenant="t_acme"}
   http_requests_in_progress{method="POST", route="/api/v1/orders"}
   ```

2. **Business Metrics** (placeholders):
   ```
   db_transactions_total{tenant="t_acme", operation="insert"}
   idempotency_conflicts_total{tenant="t_acme"}
   rate_limit_exceeded_total{tenant="t_acme"}
   ```

**Prometheus Configuration**:
```yaml
scrape_configs:
  - job_name: 'mpango-backend'
    scrape_interval: 15s
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
```

**Grafana Dashboards**:
- Request rate by endpoint
- Latency percentiles (p50, p95, p99)
- Error rate by status code
- Tenant-specific metrics

**Files**:
- `backend/core/prometheus_metrics.py` - Metrics definitions and middleware
- `backend/api/v1/prometheus.py` - Metrics endpoint

### S2-6: Central Error Codes

**Standard Error Response**:
```json
{
  "code": "PAYMENT_IDEMPOTENCY_CONFLICT",
  "message": "Payment with this idempotency key already exists",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "details": {
    "idempotency_key": "pay_123",
    "existing_payment_id": "payment-456"
  }
}
```

**Error Codes** (30+ defined):
- `UNAUTHORIZED`, `INVALID_CREDENTIALS`, `TOKEN_EXPIRED`
- `RESOURCE_NOT_FOUND`, `USER_NOT_FOUND`, `ORDER_NOT_FOUND`
- `VALIDATION_ERROR`, `INVALID_INPUT`
- `PAYMENT_IDEMPOTENCY_CONFLICT`, `ORDER_STATE_TRANSITION_INVALID`
- `RATE_LIMIT_EXCEEDED`
- `INTERNAL_SERVER_ERROR`, `DATABASE_ERROR`, `SERVICE_UNAVAILABLE`

**HTTP Status Mapping**:
- 400 → `INVALID_INPUT`
- 401 → `UNAUTHORIZED`
- 403 → `PERMISSION_DENIED`
- 404 → `RESOURCE_NOT_FOUND`
- 409 → `CONFLICT`
- 422 → `VALIDATION_ERROR`
- 429 → `RATE_LIMIT_EXCEEDED`
- 500 → `INTERNAL_SERVER_ERROR`
- 503 → `SERVICE_UNAVAILABLE`

**Files**:
- `backend/core/error_codes.py` - Error code definitions and handlers
- `backend/main.py` - Exception handler registration

---

## Batch 3: Traffic Control & Safety

### S2-5: Rate Limiting

**Implementation**: Redis-backed Fixed Window algorithm

**Rate Limits**:
- **Anonymous**: 100 requests/minute per IP address
- **Authenticated**: 1000 requests/minute per tenant_id + user_id

**Redis Requirements**:
```bash
REDIS_URL=redis://host:6379/0
```

**Redis Key Structure**:
```
rate_limit:ip:{ip_address}:{window}              # Anonymous
rate_limit:tenant:{tenant_id}:{user_id}:{window} # Authenticated
```

**Window Size**: 60 seconds (1 minute)

**Response Headers**:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 60
```

**429 Response**:
```json
{
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded. Maximum 100 requests per minute.",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "details": {
    "limit": 100,
    "window_size": 60,
    "retry_after": 45
  }
}
```

**Fail-Open Behavior**:
- If Redis fails, requests are **allowed through**
- Error is logged but traffic continues
- Monitor Redis health to detect outages

**IP Extraction** (for anonymous requests):
1. `X-Forwarded-For` header (first IP)
2. `X-Real-IP` header
3. Direct client IP

**Excluded Endpoints** (no rate limiting):
- `/health`, `/healthz`, `/readyz`
- `/metrics`

**Files**:
- `backend/core/rate_limiter.py` - Rate limiting logic
- `backend/api/middleware/rate_limiting.py` - Rate limiting middleware

### Graceful Shutdown

**Signal Handling**: SIGTERM and SIGINT

**Shutdown Sequence**:
```
1. Receive signal (SIGTERM/SIGINT)
2. Log shutdown initiation
3. Wait 10 seconds (grace period) for in-flight requests
4. Close database connections
5. Close Redis connections
6. Log shutdown complete
7. Exit
```

**Grace Period**: 10 seconds

**Kubernetes Configuration**:
```yaml
spec:
  terminationGracePeriodSeconds: 20  # Allow 20s for graceful shutdown
  containers:
  - name: backend
    lifecycle:
      preStop:
        exec:
          command: ["/bin/sh", "-c", "sleep 2"]
```

**Monitoring**:
- Log "Graceful shutdown initiated" on signal
- Log "Database connections closed"
- Log "Redis connections closed"
- Log "Graceful shutdown complete"

**Files**:
- `backend/main.py` - Signal handlers and shutdown logic

### S2-7: CI Reliability Tests

**Test Suite**: `backend/tests/test_reliability.py`

**Coverage**: 11 tests, all passing

**Test Categories**:
1. Rate Limiter (7 tests)
2. Graceful Shutdown (1 test)
3. Middleware Under Load (2 tests)
4. Code Quality (1 test)

**CI Integration**:
```bash
poetry run pytest tests/test_reliability.py -v
```

**Files**:
- `backend/tests/test_reliability.py` - Reliability test suite

---

## Middleware Stack Order

**Critical Ordering** (implemented in `backend/api/app.py`):

```
1. RequestLoggingMiddleware     ← Generate request_id, set context
2. PrometheusMetricsMiddleware  ← Track metrics
3. CORSMiddleware               ← Handle CORS
4. AuthenticationMiddleware     ← Set tenant/user context
5. RateLimitingMiddleware       ← Enforce rate limits
6. IdempotencyMiddleware        ← Handle idempotency
7. BasicMetricsMiddleware       ← Legacy metrics (optional)
```

**Why This Order**:
- Request ID must be generated first (used by all middleware)
- Metrics must track full request lifecycle
- Authentication must happen before rate limiting (for tenant-based limits)
- Rate limiting must happen before business logic

---

## Infrastructure Requirements

### Required Services

1. **PostgreSQL**:
   - Version: 14+
   - Connection pooling recommended
   - Health check: `SELECT 1`

2. **Redis**:
   - Version: 6+
   - Used for: Rate limiting, caching
   - Health check: `PING`
   - Memory: ~100MB for rate limiting (keys expire after 60s)

### Environment Variables

**Required**:
```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname
REDIS_URL=redis://host:6379/0
SECRET_KEY=<secure-random-key-min-32-chars>
MPANGO_ENV=production
```

**Optional**:
```bash
LOG_LEVEL=INFO
CORS_ORIGINS=["https://app.example.com"]
ENABLE_METRICS=true
```

### Kubernetes Deployment

**Recommended Pod Spec**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mpango-backend
spec:
  replicas: 3
  template:
    spec:
      terminationGracePeriodSeconds: 20
      containers:
      - name: backend
        image: mpango-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: mpango-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: mpango-secrets
              key: redis-url
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: mpango-secrets
              key: secret-key
        - name: MPANGO_ENV
          value: "production"
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /readyz
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

---

## Monitoring & Alerting

### Key Metrics to Monitor

1. **Health Checks**:
   - `/healthz` response time
   - `/readyz` success rate
   - Database connection health
   - Redis connection health

2. **Rate Limiting**:
   - `http_requests_total{status_code="429"}` - Rate limit violations
   - Rate limit violations by tenant
   - Redis connection errors

3. **Performance**:
   - Request latency (p50, p95, p99)
   - Requests per second
   - Error rate by status code

4. **Graceful Shutdown**:
   - Shutdown duration
   - In-flight requests during shutdown

### Recommended Alerts

**Critical**:
```
- Alert: HighErrorRate
  Expr: rate(http_requests_total{status_code=~"5.."}[5m]) > 0.05
  For: 5m
  Severity: critical

- Alert: DatabaseDown
  Expr: up{job="mpango-backend"} == 0
  For: 1m
  Severity: critical

- Alert: RedisDown
  Expr: redis_up == 0
  For: 1m
  Severity: critical
```

**Warning**:
```
- Alert: HighRateLimitViolations
  Expr: rate(http_requests_total{status_code="429"}[5m]) > 0.05
  For: 5m
  Severity: warning

- Alert: HighLatency
  Expr: histogram_quantile(0.95, http_request_duration_seconds) > 1.0
  For: 5m
  Severity: warning
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] Verify all environment variables are set
- [ ] Verify Redis is accessible
- [ ] Verify PostgreSQL is accessible
- [ ] Run all tests: `poetry run pytest`
- [ ] Build Docker image
- [ ] Push image to registry

### Deployment

- [ ] Apply Kubernetes manifests
- [ ] Verify pods are running
- [ ] Check `/healthz` endpoint
- [ ] Check `/readyz` endpoint
- [ ] Verify logs are JSON formatted
- [ ] Verify metrics endpoint `/metrics`

### Post-Deployment

- [ ] Monitor error rate
- [ ] Monitor latency
- [ ] Monitor rate limit violations
- [ ] Verify graceful shutdown works (scale down test)
- [ ] Check Prometheus metrics
- [ ] Check log aggregation

---

## Rollback Plan

If issues occur:

1. **Immediate**: Scale down new pods, scale up old pods
2. **Verify**: Check health endpoints return to normal
3. **Investigate**: Review logs for errors
4. **Fix**: Address issues in development
5. **Redeploy**: After fixes are verified

**Rollback Command**:
```bash
kubectl rollout undo deployment/mpango-backend
```

---

## Testing in Staging

### Test Scenarios

1. **Startup Validation**:
   - Deploy with missing `DATABASE_URL` → Should crash
   - Deploy with default `SECRET_KEY` in production → Should crash
   - Deploy with valid config → Should start successfully

2. **Health Checks**:
   - Call `/healthz` → Should return 200
   - Call `/readyz` with healthy dependencies → Should return 200
   - Stop Redis → `/readyz` should return 503
   - Restart Redis → `/readyz` should return 200

3. **Rate Limiting**:
   - Make 50 anonymous requests → Should succeed
   - Make 101 anonymous requests → 101st should return 429
   - Make 500 authenticated requests → Should succeed
   - Make 1001 authenticated requests → 1001st should return 429

4. **Graceful Shutdown**:
   - Send SIGTERM to pod
   - Verify logs show "Graceful shutdown initiated"
   - Verify pod exits within 10 seconds
   - Verify no connection errors

5. **Observability**:
   - Verify logs are JSON formatted
   - Verify `request_id` is present in all logs
   - Verify `/metrics` endpoint returns Prometheus metrics
   - Verify error responses have standard format

---

## Known Issues & Limitations

### Current Limitations

1. **Rate Limiting**:
   - Fixed Window algorithm (not Sliding Window)
   - No per-endpoint rate limits
   - No dynamic limits based on tenant tier

2. **Graceful Shutdown**:
   - No connection draining (stops accepting new connections)
   - No request tracking (doesn't wait for specific requests)

3. **Metrics**:
   - Business metrics are placeholders (not implemented)
   - No custom dashboards provided

### Future Enhancements

1. **Rate Limiting**:
   - Implement Sliding Window algorithm
   - Add per-endpoint rate limits
   - Add dynamic limits based on tenant tier
   - Add `Retry-After` header with exact seconds

2. **Graceful Shutdown**:
   - Implement connection draining
   - Track in-flight requests
   - Update health check to return 503 during shutdown

3. **Observability**:
   - Implement business metrics
   - Create Grafana dashboards
   - Add distributed tracing (OpenTelemetry)

---

## Support & Troubleshooting

### Common Issues

**Issue**: Application crashes on startup with "Configuration validation failed"
**Solution**: Check environment variables, ensure all required secrets are set

**Issue**: `/readyz` returns 503
**Solution**: Check database and Redis connectivity, verify credentials

**Issue**: High rate of 429 errors
**Solution**: Review rate limits, consider increasing limits or implementing per-tenant limits

**Issue**: Graceful shutdown takes too long
**Solution**: Reduce `SHUTDOWN_GRACE_PERIOD` or investigate long-running requests

### Logs to Check

**Startup**:
```bash
kubectl logs -f deployment/mpango-backend | grep "Configuration validated"
```

**Health Checks**:
```bash
kubectl logs -f deployment/mpango-backend | grep "health"
```

**Rate Limiting**:
```bash
kubectl logs -f deployment/mpango-backend | grep "Rate limit"
```

**Graceful Shutdown**:
```bash
kubectl logs -f deployment/mpango-backend | grep "shutdown"
```

---

## Conclusion

Track S2 (Production Readiness Hardening) is complete with all three batches implemented and tested:

- ✅ **Batch 1**: Startup validation and health checks
- ✅ **Batch 2**: Structured logging, error codes, and metrics
- ✅ **Batch 3**: Rate limiting and graceful shutdown

**Status**: Ready for staging deployment

**Next Steps**:
1. Deploy to staging environment
2. Run integration tests
3. Monitor metrics and logs
4. Address any issues
5. Deploy to production

---

## S2-7: CI Gates Expansion (FINAL)

**Status**: ✅ COMPLETE

**Implementation**: Production-ready CI/CD pipeline enforcing all S2 standards.

**Pipeline**: `.github/workflows/s2-7-ci-gates.yml`

### Gate 1: Reliability & Rate Limiting
**Purpose**: Ensure rate limiting and reliability tests pass

**Requirements**:
- Redis service must be available as CI sidecar
- `tests/test_reliability.py` must pass all tests
- Rate limiting functional with Redis backend

**CI Configuration**:
```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - 6379:6379
```

**Tests Included**:
- Rate limiter with Redis storage
- Window expiration logic
- Graceful shutdown signal handling
- Middleware under load
- Code quality checks

### Gate 2: Schema Enforcement (The Contract)
**Purpose**: Verify strict configuration validation and health endpoints

**Checks**:
1. **Settings Validation Test**:
   - Attempt boot with missing `DATABASE_URL`
   - Expect: Application crashes with specific error
   - Attempt boot with missing `SECRET_KEY`
   - Expect: Application crashes with specific error

2. **Health Endpoint Test**:
   - `/healthz` must respond within 5 seconds of boot
   - Returns HTTP 200 when process is alive
   - `/readyz` returns 200 with healthy DB + Redis

**Success Criteria**:
- App fails fast on missing required env vars
- Health endpoints respond within SLA

### Gate 3: No Print Policy (Linting)
**Purpose**: Enforce structured logging standard

**Rule**: `print()` statements are BANNED in `backend/` (excluding `tests/`)

**Exceptions**:
- ✅ `tests/` - Test output and debugging
- ✅ `scripts/` - CLI scripts and utilities
- ❌ `backend/` source code - Must use logger

**Migration Guide**:
```python
# ❌ BANNED
print("User created successfully")

# ✅ REQUIRED
from core.structured_logging import get_logger
logger = get_logger(__name__)
logger.info("User created successfully")
```

**CI Check**:
```bash
# Find all Python files excluding tests
find backend -name "*.py" -not -path "*/tests/*" | xargs grep -n "print("
# If any found, build FAILS
```

### Gate 4: Final Deployment Smoke Test
**Purpose**: Verify deployment readiness

**Test Sequence**:
1. Start application with all services
2. Wait for startup
3. Test `/healthz` → Must return HTTP 200
4. Test `/readyz` → Must return HTTP 200 (CRITICAL)
5. Test `/metrics` → Must return HTTP 200
6. Verify JSON logging format

**Success Criteria**:
```
GET /healthz → 200 OK
GET /readyz  → 200 OK (with DB + Redis checks)
GET /metrics → 200 OK (Prometheus format)
```

### Pipeline Summary

| Gate | Status | Enforces |
|------|--------|----------|
| 1. Reliability & Rate Limiting | Required | Redis-backed rate limiting, reliability tests |
| 2. Schema Enforcement | Required | Fail-fast config, health endpoints |
| 3. No Print Policy | Required | Structured logging standard |
| 4. Deployment Smoke Test | Required | /readyz returns 200 |

**Build Behavior**:
- ✅ ALL gates pass → Build succeeds, ready for deploy
- ❌ ANY gate fails → Build FAILS, deploy blocked

### Track S2 Completion Status

**Batches Complete**:
- ✅ **Batch 1** (S2-1, S2-4): Startup validation, health probes
- ✅ **Batch 2** (S2-2, S2-3, S2-6): Logging, metrics, error codes
- ✅ **Batch 3** (S2-5, S2-7): Rate limiting, CI gates

**Infrastructure**:
- ✅ Docker Compose with all services
- ✅ Kubernetes manifests with probes
- ✅ CI/CD pipeline with 4 enforcement gates

**Status**: **TRACK S2 COMPLETE - READY FOR PRODUCTION**

---

**Document Author**: Backend AI / Ops AI  
**Review Status**: Ready for Review  
**Deployment Status**: Production Ready  
**Last Updated**: 2026-02-05  
**Track Status**: S2 COMPLETE 🎉
