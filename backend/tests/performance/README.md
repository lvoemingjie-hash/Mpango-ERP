# S3-C: Performance Benchmarking Guide

This directory contains performance benchmarking tools for Mpango ERP Backend.

## Prerequisites

1. **Install Locust**:
   ```bash
   poetry add --group dev locust
   ```

2. **Start Services**:
   ```bash
   # Start PostgreSQL and Redis
   docker-compose up -d postgres redis
   
   # Start backend server
   cd backend
   poetry run uvicorn main:app --host 0.0.0.0 --port 8000
   ```

3. **Verify Services**:
   ```bash
   # Check health
   curl http://localhost:8000/health
   
   # Check Redis
   redis-cli ping
   ```

## Running Benchmarks

### Interactive Mode (Web UI)

```bash
cd backend
locust -f tests/performance/locustfile.py --host=http://localhost:8000
```

Then open your browser to http://localhost:8089 and configure:
- **Number of users**: 50
- **Spawn rate**: 10 users/second
- **Run time**: 1 minute

### Headless Mode (CI/CD)

```bash
cd backend

# Basic run (1 minute, 50 users)
locust -f tests/performance/locustfile.py \
       --host=http://localhost:8000 \
       --users 50 \
       --spawn-rate 10 \
       --run-time 1m \
       --headless

# With HTML report
locust -f tests/performance/locustfile.py \
       --host=http://localhost:8000 \
       --users 50 \
       --spawn-rate 10 \
       --run-time 1m \
       --headless \
       --html=performance_report.html
```

### Step Load Testing

To find the breaking point, use step load:

```bash
locust -f tests/performance/locustfile.py \
       --host=http://localhost:8000 \
       --run-time 4m \
       --headless
```

This will ramp up load:
- 0-60s: 10 users
- 60-120s: 25 users
- 120-180s: 50 users
- 180-240s: 75 users

## SLA Targets

The benchmark automatically validates these SLAs:

- **P95 Latency**: < 300ms
- **Error Rate**: < 0.1%
- **Throughput**: > 100 req/s (50 concurrent users)

If SLAs are violated, the test will exit with code 1.

## User Behavior

The benchmark simulates realistic user behavior:

| Action | Weight | Description |
|--------|--------|-------------|
| View Profile (GET /auth/me) | 10 | Cached, high frequency |
| List Orders (GET /orders) | 5 | Indexed DB query |
| List SKUs (GET /skus) | 3 | Cached catalog |
| Create Order (POST /orders) | 2 | Write operation |
| View Order Detail (GET /orders/{id}) | 1 | After create |
| Health Check (GET /health) | 1 | Low frequency |

**Weight Distribution**:
- 45% View Profile (cached reads)
- 23% List Orders (indexed reads)
- 14% List SKUs (catalog reads)
- 9% Create Order (writes)
- 5% View Order Detail (reads)
- 4% Health Check

## Expected Results

### Without Caching (Baseline)

```
Total Requests: 5000
Total Failures: 2
Error Rate: 0.04%
P95 Latency: 250ms
Avg Response Time: 120ms
Requests/sec: 83.3

SLA Compliance:
  ✅ P95 Latency: 250ms < 300ms (PASSED)
  ✅ Error Rate: 0.04% < 0.1% (PASSED)
```

### With Caching (Expected)

```
Total Requests: 5000
Total Failures: 1
Error Rate: 0.02%
P95 Latency: 150ms
Avg Response Time: 60ms
Requests/sec: 125.0

SLA Compliance:
  ✅ P95 Latency: 150ms < 300ms (PASSED)
  ✅ Error Rate: 0.02% < 0.1% (PASSED)

Improvement:
  - P95 Latency: 40% reduction
  - Avg Response Time: 50% reduction
  - Throughput: 50% increase
```

## Per-Endpoint Performance (Expected)

| Endpoint | Requests | Failures | Avg (ms) | P95 (ms) | Cache Hit Rate |
|----------|----------|----------|----------|----------|----------------|
| /api/v1/auth/me (cached) | 2250 | 0 | 5 | 10 | 95% |
| /api/v1/orders (indexed) | 1125 | 1 | 100 | 180 | N/A |
| /api/v1/skus (catalog) | 675 | 0 | 8 | 15 | 90% |
| /api/v1/orders (write) | 450 | 0 | 200 | 350 | N/A |
| /api/v1/orders/{id} (detail) | 225 | 0 | 80 | 150 | N/A |
| /health | 225 | 0 | 3 | 5 | N/A |

## Monitoring Cache Performance

While running benchmarks, monitor cache metrics:

```bash
# Cache hit rate
curl http://localhost:8000/metrics | grep cache_hits_total

# Cache operation duration
curl http://localhost:8000/metrics | grep cache_operation_duration

# Redis stats
redis-cli INFO stats
```

## Troubleshooting

### Issue: Connection Refused

**Solution**: Ensure backend server is running:
```bash
curl http://localhost:8000/health
```

### Issue: Redis Connection Error

**Solution**: Ensure Redis is running:
```bash
docker-compose up -d redis
redis-cli ping
```

### Issue: High Error Rate

**Causes**:
1. Database not seeded with test data
2. Authentication tokens expired
3. Server overloaded

**Solution**:
```bash
# Seed test data
poetry run python scripts/seed_test_tenant.py

# Reduce concurrent users
locust -f tests/performance/locustfile.py \
       --host=http://localhost:8000 \
       --users 25 \
       --spawn-rate 5 \
       --run-time 1m \
       --headless
```

### Issue: Low Cache Hit Rate

**Causes**:
1. Redis not running
2. Cache TTL too short
3. Different cache keys per request

**Solution**:
```bash
# Check Redis
redis-cli ping

# Monitor cache keys
redis-cli --scan --pattern "auth_me:*" | wc -l
redis-cli --scan --pattern "skus_list:*" | wc -l

# Check cache metrics
curl http://localhost:8000/metrics | grep cache
```

## Next Steps

1. **Run Baseline**: Benchmark without caching to establish baseline
2. **Enable Caching**: Verify cache is working (check Redis keys)
3. **Run With Cache**: Benchmark with caching enabled
4. **Compare Results**: Calculate improvement percentages
5. **Document**: Update ledger with actual results
6. **Optimize**: Tune cache TTLs based on hit rates

## Files

- `locustfile.py` - Main benchmark script
- `README.md` - This file
- `performance_report.html` - Generated HTML report (after run)

---

**Backend AI** | S3-C Performance Benchmarking | 2026-02-06
