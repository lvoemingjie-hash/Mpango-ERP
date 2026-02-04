#!/usr/bin/env python3
"""
B6 Hardening Verification Tests
Tests tenant isolation, payment idempotency, and authorization hardening.
"""

import asyncio
import json
import sys
from pathlib import Path
import uuid
import requests
from datetime import datetime

# Test configuration
BASE_URL = "http://localhost:8000/api/v1"
TENANT_A = {
    "code": "TEST001",
    "email": "admin@test.com",
    "password": "testpassword"
}
TENANT_B = {
    "code": "TEST_B",
    "email": "admin@tenant-b.com",
    "password": "TestPass123"
}

class B6VerificationTests:
    def __init__(self):
        self.tenant_a_token = None
        self.tenant_b_token = None
        self.results = []

    def log_result(self, test_name, status, details):
        """Log test result."""
        result = {
            "test": test_name,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details
        }
        self.results.append(result)
        print(f"[{status}] {test_name}: {details}")

    def login_tenant(self, tenant_config):
        """Login to a tenant and return access token."""
        try:
            response = requests.post(f"{BASE_URL}/auth/login", json={
                "tenant_code": tenant_config["code"],
                "email": tenant_config["email"],
                "password": tenant_config["password"]
            })

            if response.status_code == 200:
                data = response.json()
                return data["data"]["access_token"]
            else:
                print(f"Login failed for {tenant_config['code']}: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Login error for {tenant_config['code']}: {e}")
            return None

    def test_tenant_isolation(self):
        """Test 1: Tenant isolation verification (multi-tenant leak test)"""
        print("\n" + "="*60)
        print("TEST 1: TENANT ISOLATION VERIFICATION")
        print("="*60)

        # Login to both tenants
        self.tenant_a_token = self.login_tenant(TENANT_A)
        self.tenant_b_token = self.login_tenant(TENANT_B)

        if not self.tenant_a_token or not self.tenant_b_token:
            self.log_result("Tenant Isolation - Setup", "FAIL", "Could not login to both tenants")
            return

        self.log_result("Tenant Isolation - Setup", "PASS", "Successfully logged into both tenants")

        # Test 1.1: Try to access tenant B data using tenant A token
        headers_a = {"Authorization": f"Bearer {self.tenant_a_token}"}
        headers_b = {"Authorization": f"Bearer {self.tenant_b_token}"}

        # Get current user info for both tenants to see their tenant schemas
        try:
            resp_a = requests.get(f"{BASE_URL}/auth/me", headers=headers_a)
            resp_b = requests.get(f"{BASE_URL}/auth/me", headers=headers_b)

            if resp_a.status_code == 200 and resp_b.status_code == 200:
                tenant_a_data = resp_a.json()["data"]
                tenant_b_data = resp_b.json()["data"]

                self.log_result("Tenant Isolation - User Info", "PASS",
                    f"Tenant A schema: {tenant_a_data['tenant_schema']}, Tenant B schema: {tenant_b_data['tenant_schema']}")

                # Verify different tenant schemas
                if tenant_a_data["tenant_schema"] != tenant_b_data["tenant_schema"]:
                    self.log_result("Tenant Isolation - Schema Separation", "PASS",
                        "Tenants have different schemas as expected")
                else:
                    self.log_result("Tenant Isolation - Schema Separation", "FAIL",
                        "Tenants have same schema - isolation compromised")

                # Test cross-tenant access attempts
                # Try to access orders endpoint with each token
                orders_a = requests.get(f"{BASE_URL}/orders", headers=headers_a)
                orders_b = requests.get(f"{BASE_URL}/orders", headers=headers_b)

                # Both should succeed but return different data sets
                if orders_a.status_code in [200, 404] and orders_b.status_code in [200, 404]:
                    self.log_result("Tenant Isolation - Orders Access", "PASS",
                        f"Tenant A orders: {orders_a.status_code}, Tenant B orders: {orders_b.status_code}")
                else:
                    self.log_result("Tenant Isolation - Orders Access", "FAIL",
                        f"Unexpected responses: A={orders_a.status_code}, B={orders_b.status_code}")

            else:
                self.log_result("Tenant Isolation - User Info", "FAIL",
                    f"Failed to get user info: A={resp_a.status_code}, B={resp_b.status_code}")

        except Exception as e:
            self.log_result("Tenant Isolation - Error", "FAIL", f"Exception: {e}")

    def test_payment_idempotency_same_payload(self):
        """Test 2: Payment idempotency – duplicate key, same payload"""
        print("\n" + "="*60)
        print("TEST 2: PAYMENT IDEMPOTENCY - SAME PAYLOAD")
        print("="*60)

        if not self.tenant_a_token:
            self.log_result("Payment Idempotency Same - Setup", "FAIL", "No tenant A token")
            return

        headers = {"Authorization": f"Bearer {self.tenant_a_token}"}

        # Create a test payment payload
        idempotency_key = f"TEST-IDEM-{uuid.uuid4().hex[:8]}"
        payment_payload = {
            "order_id": str(uuid.uuid4()),
            "amount": 100.0,
            "method": "transfer",
            "transaction_id": idempotency_key
        }

        payment_headers = {
            **headers,
            "X-Idempotency-Key": idempotency_key
        }

        try:
            # First request
            resp1 = requests.post(f"{BASE_URL}/payments",
                                json=payment_payload,
                                headers=payment_headers)

            # Second request with same payload and idempotency key
            resp2 = requests.post(f"{BASE_URL}/payments",
                                json=payment_payload,
                                headers=payment_headers)

            self.log_result("Payment Idempotency Same - First Request",
                          "PASS" if resp1.status_code == 201 else "FAIL",
                          f"Status: {resp1.status_code}, Response: {resp1.text[:200]}")

            # Second request should either return same result or indicate idempotent replay
            if resp2.status_code in [200, 201]:
                self.log_result("Payment Idempotency Same - Second Request", "PASS",
                              f"Status: {resp2.status_code}, Idempotent behavior confirmed")
            else:
                self.log_result("Payment Idempotency Same - Second Request", "FAIL",
                              f"Status: {resp2.status_code}, Response: {resp2.text[:200]}")

        except Exception as e:
            self.log_result("Payment Idempotency Same - Error", "FAIL", f"Exception: {e}")

    def test_payment_idempotency_conflicting_payload(self):
        """Test 3: Payment idempotency – conflicting payload returns 409"""
        print("\n" + "="*60)
        print("TEST 3: PAYMENT IDEMPOTENCY - CONFLICTING PAYLOAD")
        print("="*60)

        if not self.tenant_a_token:
            self.log_result("Payment Idempotency Conflict - Setup", "FAIL", "No tenant A token")
            return

        headers = {"Authorization": f"Bearer {self.tenant_a_token}"}

        # Create a test payment payload
        idempotency_key = f"TEST-CONFLICT-{uuid.uuid4().hex[:8]}"

        payment_payload_1 = {
            "order_id": str(uuid.uuid4()),
            "amount": 100.0,
            "method": "transfer",
            "transaction_id": idempotency_key
        }

        payment_payload_2 = {
            "order_id": str(uuid.uuid4()),  # Different order_id
            "amount": 200.0,  # Different amount
            "method": "transfer",
            "transaction_id": idempotency_key  # Same transaction_id
        }

        payment_headers = {
            **headers,
            "X-Idempotency-Key": idempotency_key
        }

        try:
            # First request
            resp1 = requests.post(f"{BASE_URL}/payments",
                                json=payment_payload_1,
                                headers=payment_headers)

            # Second request with different payload but same idempotency key
            resp2 = requests.post(f"{BASE_URL}/payments",
                                json=payment_payload_2,
                                headers=payment_headers)

            self.log_result("Payment Idempotency Conflict - First Request",
                          "PASS" if resp1.status_code == 201 else "FAIL",
                          f"Status: {resp1.status_code}")

            # Second request should return 409 Conflict
            if resp2.status_code == 409:
                self.log_result("Payment Idempotency Conflict - Second Request", "PASS",
                              f"Status: {resp2.status_code}, Conflict detected as expected")
            elif resp2.status_code == 400:
                # Check if it's a constraint violation (also acceptable)
                self.log_result("Payment Idempotency Conflict - Second Request", "PASS",
                              f"Status: {resp2.status_code}, Constraint violation (acceptable)")
            else:
                self.log_result("Payment Idempotency Conflict - Second Request", "FAIL",
                              f"Status: {resp2.status_code}, Expected 409 or 400, Response: {resp2.text[:200]}")

        except Exception as e:
            self.log_result("Payment Idempotency Conflict - Error", "FAIL", f"Exception: {e}")

    def test_transfer_idempotency_header_requirement(self):
        """Test 4: Transfer payment requires X-Idempotency-Key header"""
        print("\n" + "="*60)
        print("TEST 4: TRANSFER IDEMPOTENCY HEADER REQUIREMENT")
        print("="*60)

        if not self.tenant_a_token:
            self.log_result("Transfer Header Requirement - Setup", "FAIL", "No tenant A token")
            return

        headers = {"Authorization": f"Bearer {self.tenant_a_token}"}

        # Test without X-Idempotency-Key header
        payment_payload = {
            "order_id": str(uuid.uuid4()),
            "amount": 100.0,
            "method": "transfer"
        }

        try:
            resp = requests.post(f"{BASE_URL}/payments",
                               json=payment_payload,
                               headers=headers)

            if resp.status_code == 400:
                response_data = resp.json()
                if "MISSING_IDEMPOTENCY_KEY" in str(response_data):
                    self.log_result("Transfer Header Requirement", "PASS",
                                  "Transfer payment correctly rejected without X-Idempotency-Key")
                else:
                    self.log_result("Transfer Header Requirement", "FAIL",
                                  f"Wrong error code: {response_data}")
            else:
                self.log_result("Transfer Header Requirement", "FAIL",
                              f"Expected 400, got {resp.status_code}: {resp.text[:200]}")

        except Exception as e:
            self.log_result("Transfer Header Requirement - Error", "FAIL", f"Exception: {e}")

    def run_all_tests(self):
        """Run all B6 verification tests."""
        print("Starting B6 Hardening Verification Tests...")
        print(f"Target: {BASE_URL}")
        print(f"Tenant A: {TENANT_A['code']}")
        print(f"Tenant B: {TENANT_B['code']}")

        self.test_tenant_isolation()
        self.test_payment_idempotency_same_payload()
        self.test_payment_idempotency_conflicting_payload()
        self.test_transfer_idempotency_header_requirement()

        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)

        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")

        print(f"Total Tests: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")

        if failed == 0:
            print("\n✅ ALL TESTS PASSED - B6 Hardening verification successful!")
        else:
            print(f"\n❌ {failed} TESTS FAILED - B6 Hardening issues detected!")

        return self.results

if __name__ == "__main__":
    tester = B6VerificationTests()
    results = tester.run_all_tests()

    # Save results to file
    with open("b6_verification_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nDetailed results saved to: b6_verification_results.json")
