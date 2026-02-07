"""
S3-C: Performance Benchmark Harness

Locust-based load testing for Mpango ERP Backend.

Philosophy: "Cache for Reads, Benchmark for Truth."

SLA Targets:
- P95 Latency < 300ms
- Error Rate < 0.1%
- Throughput > 100 req/s (50 concurrent users)

Usage:
    # Install locust
    poetry add --group dev locust
    
    # Run locally
    locust -f tests/performance/locustfile.py --host=http://localhost:8000
    
    # Run headless (1 minute, 50 users)
    locust -f tests/performance/locustfile.py --host=http://localhost:8000 \\
           --users 50 --spawn-rate 10 --run-time 1m --headless
    
    # Run with HTML report
    locust -f tests/performance/locustfile.py --host=http://localhost:8000 \\
           --users 50 --spawn-rate 10 --run-time 1m --headless \\
           --html=performance_report.html
"""
import json
import random
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner


# SLA Thresholds
SLA_P95_LATENCY_MS = 300
SLA_ERROR_RATE_PERCENT = 0.1


class MpangoERPUser(HttpUser):
    """
    Simulated user for Mpango ERP.
    
    User Behavior:
    1. Login (Get Token)
    2. View Profile (Cached - GET /auth/me)
    3. List Orders (Indexed DB query - GET /orders)
    4. Create Order (Write operation - POST /orders)
    5. View Order Detail (GET /orders/{id})
    """
    
    # Wait time between tasks (1-3 seconds)
    wait_time = between(1, 3)
    
    # User credentials (test mode)
    test_email = "admin@test.com"
    test_password = "admin123"
    
    # Authentication token
    token = None
    tenant_id = None
    
    def on_start(self):
        """
        Called when a user starts.
        Performs login to get authentication token.
        """
        self.login()
    
    def login(self):
        """
        S3-C: Login and get authentication token.
        
        This is a write operation (not cached).
        """
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self.test_email,
                "password": self.test_password
            },
            name="/api/v1/auth/login"
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data["data"]["access_token"]
            self.tenant_id = data["data"]["tenant_id"]
        else:
            # Login failed - stop this user
            self.environment.runner.quit()
    
    def get_headers(self):
        """Get headers with authentication token."""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
    
    @task(10)
    def view_profile(self):
        """
        S3-C: View user profile (GET /auth/me).
        
        This endpoint should be cached (TTL: 30s).
        High frequency check - weight: 10
        """
        self.client.get(
            "/api/v1/auth/me",
            headers=self.get_headers(),
            name="/api/v1/auth/me (cached)"
        )
    
    @task(5)
    def list_orders(self):
        """
        S3-C: List orders (GET /orders).
        
        This uses indexed DB query (not cached yet).
        Medium frequency - weight: 5
        """
        self.client.get(
            "/api/v1/orders?page=1&size=10",
            headers=self.get_headers(),
            name="/api/v1/orders (indexed)"
        )
    
    @task(2)
    def create_order(self):
        """
        S3-C: Create order (POST /orders).
        
        This is a write operation (not cached).
        Low frequency - weight: 2
        """
        order_data = {
            "retailer_id": "00000000-0000-0000-0000-000000000002",
            "items": [
                {
                    "product_name": f"Test Product {random.randint(1, 100)}",
                    "sku_code": f"SKU{random.randint(1, 100)}",
                    "quantity": random.randint(1, 10),
                    "unit_price": round(random.uniform(10.0, 100.0), 2)
                }
            ],
            "notes": "Performance test order"
        }
        
        response = self.client.post(
            "/api/v1/orders",
            json=order_data,
            headers=self.get_headers(),
            name="/api/v1/orders (write)"
        )
        
        # If order created successfully, view it
        if response.status_code == 201:
            data = response.json()
            order_id = data["data"]["id"]
            self.view_order_detail(order_id)
    
    def view_order_detail(self, order_id: str):
        """
        View order detail (GET /orders/{id}).
        
        This uses indexed DB query with eager loading.
        """
        self.client.get(
            f"/api/v1/orders/{order_id}",
            headers=self.get_headers(),
            name="/api/v1/orders/{id} (detail)"
        )
    
    @task(3)
    def list_skus(self):
        """
        S3-C: List SKUs/Products (GET /skus).
        
        This endpoint should be cached (TTL: 1 min).
        Product catalog is read-heavy.
        Medium frequency - weight: 3
        """
        self.client.get(
            "/api/v1/skus?page=1&size=20",
            headers=self.get_headers(),
            name="/api/v1/skus (catalog)"
        )
    
    @task(1)
    def health_check(self):
        """
        Health check (GET /health).
        
        Low frequency - weight: 1
        """
        self.client.get(
            "/health",
            name="/health"
        )


# SLA Validation Events

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    S3-C: Validate SLA after test completion.
    
    Checks:
    - P95 latency < 300ms
    - Error rate < 0.1%
    """
    stats = environment.stats
    
    print("\n" + "="*80)
    print("S3-C: SLA VALIDATION")
    print("="*80)
    
    # Calculate overall stats
    total_requests = stats.total.num_requests
    total_failures = stats.total.num_failures
    error_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0
    
    # Get P95 latency
    p95_latency = stats.total.get_response_time_percentile(0.95)
    
    # Check SLA compliance
    sla_passed = True
    
    print(f"\nPerformance Metrics:")
    print(f"  Total Requests: {total_requests}")
    print(f"  Total Failures: {total_failures}")
    print(f"  Error Rate: {error_rate:.2f}%")
    print(f"  P95 Latency: {p95_latency:.2f}ms")
    print(f"  Avg Response Time: {stats.total.avg_response_time:.2f}ms")
    print(f"  Requests/sec: {stats.total.total_rps:.2f}")
    
    print(f"\nSLA Targets:")
    print(f"  P95 Latency: < {SLA_P95_LATENCY_MS}ms")
    print(f"  Error Rate: < {SLA_ERROR_RATE_PERCENT}%")
    
    print(f"\nSLA Compliance:")
    
    # Check P95 latency
    if p95_latency > SLA_P95_LATENCY_MS:
        print(f"  ❌ P95 Latency: {p95_latency:.2f}ms > {SLA_P95_LATENCY_MS}ms (FAILED)")
        sla_passed = False
    else:
        print(f"  ✅ P95 Latency: {p95_latency:.2f}ms < {SLA_P95_LATENCY_MS}ms (PASSED)")
    
    # Check error rate
    if error_rate > SLA_ERROR_RATE_PERCENT:
        print(f"  ❌ Error Rate: {error_rate:.2f}% > {SLA_ERROR_RATE_PERCENT}% (FAILED)")
        sla_passed = False
    else:
        print(f"  ✅ Error Rate: {error_rate:.2f}% < {SLA_ERROR_RATE_PERCENT}% (PASSED)")
    
    print("\n" + "="*80)
    if sla_passed:
        print("✅ ALL SLAs PASSED")
    else:
        print("❌ SLA VIOLATION DETECTED")
    print("="*80 + "\n")
    
    # Print per-endpoint stats
    print("\nPer-Endpoint Performance:")
    print(f"{'Endpoint':<40} {'Requests':<10} {'Failures':<10} {'Avg (ms)':<10} {'P95 (ms)':<10}")
    print("-" * 80)
    
    for name, stat in stats.entries.items():
        if stat.num_requests > 0:
            p95 = stat.get_response_time_percentile(0.95)
            print(f"{name:<40} {stat.num_requests:<10} {stat.num_failures:<10} "
                  f"{stat.avg_response_time:<10.2f} {p95:<10.2f}")
    
    # Exit with error code if SLA failed
    if not sla_passed and isinstance(environment.runner, MasterRunner):
        environment.process_exit_code = 1


# Custom shape for ramping load (optional)
class StepLoadShape:
    """
    Custom load shape for step-wise load increase.
    
    Ramps up users in steps to find breaking point.
    """
    
    def tick(self):
        run_time = self.get_run_time()
        
        if run_time < 60:
            # 0-60s: 10 users
            return (10, 2)
        elif run_time < 120:
            # 60-120s: 25 users
            return (25, 5)
        elif run_time < 180:
            # 120-180s: 50 users
            return (50, 10)
        elif run_time < 240:
            # 180-240s: 75 users
            return (75, 15)
        else:
            # Stop after 4 minutes
            return None


if __name__ == "__main__":
    print("""
    S3-C: Mpango ERP Performance Benchmark
    
    Usage:
        # Run with Web UI
        locust -f locustfile.py --host=http://localhost:8000
        
        # Run headless (1 minute, 50 users)
        locust -f locustfile.py --host=http://localhost:8000 \\
               --users 50 --spawn-rate 10 --run-time 1m --headless
        
        # Run with HTML report
        locust -f locustfile.py --host=http://localhost:8000 \\
               --users 50 --spawn-rate 10 --run-time 1m --headless \\
               --html=performance_report.html
    
    SLA Targets:
        - P95 Latency < 300ms
        - Error Rate < 0.1%
    """)
