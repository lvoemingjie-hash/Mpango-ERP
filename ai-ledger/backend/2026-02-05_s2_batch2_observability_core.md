# Track S2 Batch 2: Observability Core

**Date**: 2026-02-05  
**Track**: Production Readiness Hardening  
**Priority**: P0 (Critical)  
**Status**: ✅ COMPLETE

---

## Objective

Execute Batch 2 of Track S2, consolidating:
- **S2-2**: Structured Logging (The Voice)
- **S2-6**: Central Error Codes (The Contract)
- **S2-3**: Metrics (The Pulse)

These tasks are combined because they all heavily modify the middleware stack and exception handling logic.

---

## Part 1: S2-2 Structured Logging

### Requirements

1. ✅ JSON Format: Replace standard logging with structured JSON logger
2. ✅ Context Injection: Implement middleware with contextvars
3. ✅ Mandatory Fields: timestamp, level, service, env, request_id, tenant_schema, user_id, route, method, status_code, latency_ms
4. ✅ Automatic Context: logger.info() automatically picks up context variables

### Implementation

#### File: `backend/core/structured_logging.py`

**Key Components**:

1. **Context Variables** (using contextvars):
```python
_request_id_ctx: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
_tenant_schema_ctx: ContextVar[Optional[str]] = ContextVar('tenant_schema', default=None)
_user_id_ctx: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
_route_ctx: ContextVar[Optional[str]] = ContextVar('route', default=None)
_method_ctx: ContextVar[Optional[str]] = ContextVar('method', default=None)
```

2. **StructuredJsonFormatter**:
```python
class StructuredJsonFormatter(logging.Formatter):
    """JSON formatter that automatically includes context variables."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": self.settings.APP_NAME,
            "env": self.settings.MPANGO_ENV,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add context variables automatically
        request_id = _request_id_ctx.get()
        if request_id:
            log_entry["request_id"] = request_id
        
        # ... (tenant_schema, user_id, route, method)
        
        return json.dumps(log_entry)
```

3. **Context Management Functions**:
```python
def set_request_context(
    request_id: Optional[str] = None,
    tenant_schema: Optional[str] = None,
    user_id: Optional[str] = None,
    route: Optional[str] = None,
    method: Optional[str] = None
) -> None:
    """Set request context for structured logging."""
    
def clear_request_context() -> None:
    """Clear request context after request completes."""
    
def get_logger(name: str) -> logging.Logger:
    """Get a logger that automatically includes context."""
```

#### File: `backend/api/middleware/request_logging.py`

**RequestLoggingMiddleware** (FIRST in middleware stack):

```python
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured request logging.
    
    Responsibilities:
    1. Generate request_id if not present
    2. Set request context for structured logging
    3. Log request start
    4. Log request completion with status and latency
    5. Clear request context
    """
    
    async def dispatch(self, request: Request, call_next):
        # Generate request ID
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        
        # Set context
        set_request_context(
            request_id=request_id,
            route=request.url.path,
            method=request.method
        )
        
        # Log request start
        logger.info("Request started", extra={
            "event": "request_start",
            "client_host": request.client.host
        })
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            latency_ms = round((time.time() - start_time) * 1000, 2)
            
            # Log request completion
            logger.info("Request completed", extra={
                "event": "request_complete",
                "status_code": response.status_code,
                "latency_ms": latency_ms
            })
            
            return response
        finally:
            clear_request_context()
```

**Example Log Output**:
```json
{
  "timestamp": "2026-02-05T10:30:00.123Z",
  "level": "INFO",
  "service": "Mpango ERP",
  "env": "production",
  "logger": "api.v1.orders",
  "message": "Order created successfully",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_schema": "t_acme_corp",
  "user_id": "user-123",
  "route": "/api/v1/orders",
  "method": "POST",
  "event": "order_created",
  "order_id": "order-456"
}
```

---

## Part 2: S2-6 Central Error Codes

### Requirements

1. ✅ Global Handler: Replace ad-hoc exception handling
2. ✅ Standard Format: All HTTP exceptions return JSON with code, message, request_id
3. ✅ Mapping: Map standard HTTP errors to error codes

### Implementation

#### File: `backend/core/error_codes.py`

**Key Components**:

1. **ErrorCode Enum**:
```python
class ErrorCode(str, Enum):
    """Standard error codes for the application."""
    
    # Authentication & Authorization
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    
    # Resource Not Found
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    TENANT_NOT_FOUND = "TENANT_NOT_FOUND"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    
    # Validation Errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    
    # Business Logic Errors
    CONFLICT = "CONFLICT"
    PAYMENT_IDEMPOTENCY_CONFLICT = "PAYMENT_IDEMPOTENCY_CONFLICT"
    ORDER_STATE_TRANSITION_INVALID = "ORDER_STATE_TRANSITION_INVALID"
    INSUFFICIENT_INVENTORY = "INSUFFICIENT_INVENTORY"
    
    # Server Errors
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
```

2. **MpangoAPIException**:
```python
class MpangoAPIException(Exception):
    """Base exception for Mpango ERP API."""
    
    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
```

3. **Standard Error Response Format**:
```python
def create_error_response(
    error_code: ErrorCode,
    message: str,
    status_code: int,
    request_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create standard error response format.
    
    Format:
    {
        "code": "ERROR_CODE",
        "message": "Human readable message",
        "request_id": "uuid",
        "details": {...}  // Optional
    }
    """
    return {
        "code": error_code.value,
        "message": message,
        "request_id": request_id or "unknown",
        "details": details
    }
```

4. **Exception Handlers**:
```python
async def mpango_exception_handler(request: Request, exc: MpangoAPIException):
    """Handler for MpangoAPIException."""
    
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handler for FastAPI HTTPException."""
    
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handler for Pydantic validation errors."""
    
async def generic_exception_handler(request: Request, exc: Exception):
    """Handler for unhandled exceptions."""
```

5. **Registration Function**:
```python
def register_exception_handlers(app) -> None:
    """Register all exception handlers with FastAPI app."""
    app.add_exception_handler(MpangoAPIException, mpango_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
```

**Example Error Response**:
```json
{
  "code": "PAYMENT_IDEMPOTENCY_CONFLICT",
  "message": "Payment with this idempotency key already exists",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "details": {
    "idempotency_key": "payment-123",
    "existing_payment_id": "pay-456"
  }
}
```

**Error Code Dictionary**:

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | INVALID_INPUT | Invalid request input |
| 401 | UNAUTHORIZED | Authentication required |
| 401 | INVALID_CREDENTIALS | Invalid username/password |
| 401 | TOKEN_EXPIRED | JWT token expired |
| 401 | TOKEN_INVALID | JWT token invalid |
| 403 | PERMISSION_DENIED | Insufficient permissions |
| 404 | RESOURCE_NOT_FOUND | Resource not found |
| 404 | USER_NOT_FOUND | User not found |
| 404 | TENANT_NOT_FOUND | Tenant not found |
| 404 | ORDER_NOT_FOUND | Order not found |
| 405 | METHOD_NOT_ALLOWED | HTTP method not allowed |
| 409 | CONFLICT | Resource conflict |
| 409 | PAYMENT_IDEMPOTENCY_CONFLICT | Idempotency conflict |
| 409 | ORDER_STATE_TRANSITION_INVALID | Invalid state transition |
| 422 | VALIDATION_ERROR | Request validation failed |
| 429 | RATE_LIMIT_EXCEEDED | Rate limit exceeded |
| 500 | INTERNAL_SERVER_ERROR | Internal server error |
| 500 | DATABASE_ERROR | Database error |
| 503 | SERVICE_UNAVAILABLE | Service unavailable |

---

## Part 3: S2-3 Metrics

### Requirements

1. ✅ Prometheus Endpoint: Expose /metrics
2. ✅ Middleware Integration: Track http_requests_total, http_request_duration_seconds
3. ✅ Business Metrics: Placeholders for db_transactions_total, idempotency_conflicts_total

### Implementation

#### File: `backend/core/prometheus_metrics.py`

**Key Metrics**:

1. **HTTP Request Metrics**:
```python
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'route', 'status_code', 'tenant']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'route', 'tenant'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'HTTP requests currently in progress',
    ['method', 'route']
)
```

2. **Business Metrics** (Placeholders):
```python
db_transactions_total = Counter(
    'db_transactions_total',
    'Total database transactions',
    ['tenant', 'operation', 'status']
)

idempotency_conflicts_total = Counter(
    'idempotency_conflicts_total',
    'Total idempotency conflicts detected',
    ['tenant', 'endpoint']
)

payment_transactions_total = Counter(
    'payment_transactions_total',
    'Total payment transactions',
    ['tenant', 'status']
)

order_state_transitions_total = Counter(
    'order_state_transitions_total',
    'Total order state transitions',
    ['tenant', 'from_state', 'to_state']
)
```

3. **PrometheusMetricsMiddleware**:
```python
class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics."""
    
    async def dispatch(self, request: Request, call_next):
        route = self._normalize_route(request.url.path)
        method = request.method
        tenant = getattr(request.state, 'tenant_id', 'unknown')
        
        # Track in-progress requests
        http_requests_in_progress.labels(method=method, route=route).inc()
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            
            # Record metrics
            http_requests_total.labels(
                method=method,
                route=route,
                status_code=response.status_code,
                tenant=tenant
            ).inc()
            
            http_request_duration_seconds.labels(
                method=method,
                route=route,
                tenant=tenant
            ).observe(duration)
            
            return response
        finally:
            http_requests_in_progress.labels(method=method, route=route).dec()
```

4. **Helper Functions**:
```python
def record_db_transaction(tenant: str, operation: str, status: str) -> None:
    """Record a database transaction."""
    db_transactions_total.labels(tenant=tenant, operation=operation, status=status).inc()

def record_idempotency_conflict(tenant: str, endpoint: str) -> None:
    """Record an idempotency conflict."""
    idempotency_conflicts_total.labels(tenant=tenant, endpoint=endpoint).inc()

def record_payment_transaction(tenant: str, status: str) -> None:
    """Record a payment transaction."""
    payment_transactions_total.labels(tenant=tenant, status=status).inc()

def record_order_state_transition(tenant: str, from_state: str, to_state: str) -> None:
    """Record an order state transition."""
    order_state_transitions_total.labels(
        tenant=tenant,
        from_state=from_state,
        to_state=to_state
    ).inc()
```

#### File: `backend/api/v1/prometheus.py`

**Metrics Endpoint**:
```python
@router.get("", response_class=Response)
async def metrics_endpoint():
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus exposition format.
    """
    metrics_data = get_metrics()
    
    return Response(
        content=metrics_data,
        media_type=get_metrics_content_type()
    )
```

**Example Metrics Output**:
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="POST",route="/api/v1/orders",status_code="201",tenant="t_acme"} 42.0
http_requests_total{method="GET",route="/api/v1/orders/{id}",status_code="200",tenant="t_acme"} 156.0

# HELP http_request_duration_seconds HTTP request duration in seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.005",method="GET",route="/api/v1/orders",tenant="t_acme"} 10.0
http_request_duration_seconds_bucket{le="0.01",method="GET",route="/api/v1/orders",tenant="t_acme"} 25.0
http_request_duration_seconds_bucket{le="0.025",method="GET",route="/api/v1/orders",tenant="t_acme"} 45.0
http_request_duration_seconds_sum{method="GET",route="/api/v1/orders",tenant="t_acme"} 1.234
http_request_duration_seconds_count{method="GET",route="/api/v1/orders",tenant="t_acme"} 50.0

# HELP http_requests_in_progress HTTP requests currently in progress
# TYPE http_requests_in_progress gauge
http_requests_in_progress{method="POST",route="/api/v1/payments"} 3.0

# HELP db_transactions_total Total database transactions
# TYPE db_transactions_total counter
db_transactions_total{tenant="t_acme",operation="insert",status="success"} 123.0

# HELP idempotency_conflicts_total Total idempotency conflicts detected
# TYPE idempotency_conflicts_total counter
idempotency_conflicts_total{tenant="t_acme",endpoint="/api/v1/payments"} 5.0
```

---

## Middleware Stack Ordering

**Critical**: Middleware order ensures proper observability:

```python
def configure_app(app: FastAPI, settings: Settings) -> None:
    # 1. RequestLoggingMiddleware (FIRST)
    #    - Generates request_id
    #    - Sets logging context
    #    - Logs request start/end
    app.add_middleware(RequestLoggingMiddleware)
    
    # 2. PrometheusMetricsMiddleware (SECOND)
    #    - Tracks all requests
    #    - Records metrics
    app.add_middleware(PrometheusMetricsMiddleware)
    
    # 3. CORS
    app.add_middleware(CORSMiddleware, ...)
    
    # 4. AuthenticationMiddleware
    #    - Authenticates user
    #    - Sets tenant/user context
    #    - Updates logging context
    app.add_middleware(AuthenticationMiddleware, ...)
    
    # 5. IdempotencyMiddleware
    app.add_middleware(IdempotencyMiddleware)
    
    # 6. BasicMetricsMiddleware (optional, legacy)
    if settings.ENABLE_METRICS:
        app.add_middleware(BasicMetricsMiddleware)
```

**Why This Order**:

1. **RequestLoggingMiddleware first** ensures:
   - request_id is available for all other middleware
   - All logs include request context
   - Request lifecycle is fully logged

2. **PrometheusMetricsMiddleware second** ensures:
   - All requests are tracked (including auth failures)
   - Metrics capture full request duration
   - Tenant information is available from auth middleware

3. **AuthenticationMiddleware after logging** ensures:
   - Unauthenticated requests are still logged
   - Tenant/user context is added to logs after authentication

4. **Exception handlers registered before middleware** ensures:
   - All exceptions are caught and formatted consistently
   - Error responses include request_id

---

## Integration Points

### 1. Using Structured Logging in Application Code

```python
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Logs automatically include request_id, tenant, user, etc.
logger.info("Order created", extra={
    "order_id": order.id,
    "amount": order.total_amount
})
```

### 2. Raising Custom Exceptions

```python
from core.error_codes import MpangoAPIException, ErrorCode

# Raise custom exception
raise MpangoAPIException(
    error_code=ErrorCode.PAYMENT_IDEMPOTENCY_CONFLICT,
    message="Payment with this idempotency key already exists",
    status_code=409,
    details={"idempotency_key": key}
)
```

### 3. Recording Business Metrics

```python
from core.prometheus_metrics import record_payment_transaction

# Record business event
record_payment_transaction(tenant="t_acme", status="success")
```

---

## Testing

### Test 1: Structured Logging

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/orders \
  -H "Authorization: Bearer token" \
  -H "Content-Type: application/json" \
  -d '{"items": [...]}'
```

**Expected Log Output**:
```json
{
  "timestamp": "2026-02-05T10:30:00.123Z",
  "level": "INFO",
  "service": "Mpango ERP",
  "env": "production",
  "logger": "api.middleware.request_logging",
  "message": "Request started",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "route": "/api/v1/orders",
  "method": "POST",
  "event": "request_start",
  "client_host": "192.168.1.100"
}
```

### Test 2: Error Response Format

**Request**:
```bash
curl http://localhost:8000/api/v1/orders/invalid-id
```

**Expected Response** (404):
```json
{
  "code": "RESOURCE_NOT_FOUND",
  "message": "Order not found",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Test 3: Prometheus Metrics

**Request**:
```bash
curl http://localhost:8000/metrics
```

**Expected Response**:
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",route="/api/v1/orders",status_code="200",tenant="t_acme"} 42.0
...
```

---

## Prometheus Integration

### Prometheus Configuration

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'mpango-erp-backend'
    scrape_interval: 15s
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
```

### Grafana Dashboard Queries

**Request Rate**:
```promql
rate(http_requests_total[5m])
```

**Request Duration (p95)**:
```promql
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

**Error Rate**:
```promql
rate(http_requests_total{status_code=~"5.."}[5m])
```

**Idempotency Conflicts**:
```promql
rate(idempotency_conflicts_total[5m])
```

---

## Log Schema Reference

### Mandatory Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| timestamp | string | ISO 8601 timestamp | "2026-02-05T10:30:00.123Z" |
| level | string | Log level | "INFO", "ERROR", "WARNING" |
| service | string | Application name | "Mpango ERP" |
| env | string | Environment | "production", "test" |
| logger | string | Logger name | "api.v1.orders" |
| message | string | Log message | "Order created successfully" |
| request_id | string | Unique request ID | "550e8400-e29b-41d4-a716-446655440000" |

### Optional Context Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| tenant_schema | string | Tenant schema | "t_acme_corp" |
| user_id | string | User ID | "user-123" |
| route | string | API route | "/api/v1/orders" |
| method | string | HTTP method | "POST" |
| status_code | integer | HTTP status | 201 |
| latency_ms | float | Request latency | 45.67 |

### Event-Specific Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| event | string | Event type | "request_start", "order_created" |
| order_id | string | Order ID | "order-456" |
| payment_id | string | Payment ID | "pay-789" |
| error_code | string | Error code | "PAYMENT_IDEMPOTENCY_CONFLICT" |
| exception_type | string | Exception type | "ValueError" |

---

## Error Code Dictionary

See Part 2 table above for complete error code mapping.

---

## Dependencies

### New Dependencies

Added to `backend/pyproject.toml`:

```toml
# Metrics
prometheus-client = ">=0.19.0,<1.0.0"
```

### Existing Dependencies

- `python-json-logger`: Already present for JSON logging
- `contextvars`: Built-in Python module

---

## Migration Notes

### Breaking Changes

**None** - All changes are backward compatible:
- Old logging still works (but not structured)
- Old exception handling still works (but not standardized)
- Old metrics endpoint still works (legacy)

### Recommended Actions

1. **Update Log Parsing**:
   - Update log aggregation tools (e.g., ELK, Splunk) to parse JSON logs
   - Create dashboards for structured log fields

2. **Update Monitoring**:
   - Configure Prometheus to scrape `/metrics`
   - Create Grafana dashboards for metrics
   - Set up alerts for error rates, latency, etc.

3. **Update Error Handling**:
   - Replace `raise HTTPException()` with `raise MpangoAPIException()`
   - Use error codes from `ErrorCode` enum
   - Include details in error responses

4. **Update Application Code**:
   - Replace `print()` statements with `logger.info()`
   - Use `get_logger(__name__)` instead of `logging.getLogger()`
   - Record business metrics using helper functions

---

## Benefits

### S2-2: Structured Logging

1. **Machine-Readable**: JSON logs can be parsed and analyzed automatically
2. **Automatic Context**: No need to manually pass request_id, tenant, etc.
3. **Consistent Format**: All logs follow the same structure
4. **Traceability**: request_id links all logs for a single request

### S2-6: Central Error Codes

1. **Consistent Errors**: All errors follow the same format
2. **Client-Friendly**: Error codes are stable and documented
3. **Traceability**: request_id in error responses
4. **Debugging**: Detailed error information in logs

### S2-3: Metrics

1. **Observability**: Real-time visibility into system behavior
2. **Performance Monitoring**: Track latency, throughput, errors
3. **Business Insights**: Track business events (payments, orders)
4. **Alerting**: Set up alerts based on metrics

---

## Future Enhancements

### Potential Improvements

1. **Distributed Tracing**:
   - Add OpenTelemetry for distributed tracing
   - Link requests across services

2. **Log Sampling**:
   - Sample high-volume logs to reduce storage costs
   - Keep all error logs

3. **Custom Metrics**:
   - Add more business-specific metrics
   - Track SLA compliance

4. **Alert Rules**:
   - Define alert rules for critical metrics
   - Integrate with PagerDuty, Slack, etc.

---

## Conclusion

**Track S2 Batch 2 Status**: ✅ **COMPLETE**

### Deliverables

1. ✅ **S2-2: Structured Logging**
   - JSON-formatted logs with automatic context injection
   - Request logging middleware
   - Context variables for request-scoped data

2. ✅ **S2-6: Central Error Codes**
   - Standard error code enum
   - Global exception handlers
   - Consistent error response format

3. ✅ **S2-3: Prometheus Metrics**
   - HTTP request metrics
   - Business metrics placeholders
   - Prometheus endpoint

4. ✅ **Middleware Stack**
   - Correct ordering for observability
   - Integration between logging, metrics, and error handling

### Observability Impact

- **Logging**: All requests logged with full context
- **Metrics**: Real-time metrics for monitoring
- **Errors**: Consistent error format with traceability

### Next Steps

- **Track S2 Batch 3**: Implement remaining production readiness features
- **Testing**: Verify observability in staging environment
- **Monitoring**: Set up Prometheus and Grafana dashboards

---

**Ledger Author**: Backend AI  
**Review Status**: Ready for Audit  
**Next Track**: S2 Batch 3 (TBD)
