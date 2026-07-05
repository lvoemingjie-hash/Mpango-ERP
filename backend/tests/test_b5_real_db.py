#!/usr/bin/env python3
"""
Phase B5 Payments Minimal Loop - Real DB Verification
Uses FastAPI TestClient with MPANGO_ENV=test for auth strategy selection.
"""
import os
import shutil
import sys
import unittest
import uuid

# Ensure backend root is in path for imports (same pattern as existing tests)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ["MPANGO_ENV"] = "test"

from fastapi.testclient import TestClient

# Import app AFTER setting MPANGO_ENV (strategy selection happens during startup)
from main import app

# Test data IDs (must exist in real DB)
ORDER_ID = "550e8400-e29b-41d4-a716-446655440002"
BINDING_ID = "550e8400-e29b-41d4-a716-446655440004"


def get_binding_balance():
    """Query outstanding_balance from DB."""
    import subprocess
    cmd = [
        "docker", "compose", "exec", "postgres",
        "psql", "-U", "mpango", "-d", "mpango_erp",
        "-t", "-A", "-c", f"SELECT outstanding_balance FROM public.wholesaler_retailer_bindings WHERE id='{BINDING_ID}';"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return float(result.stdout.strip())
    return None


def get_payments_count():
    """Count payments in DB."""
    import subprocess
    cmd = [
        "docker", "compose", "exec", "postgres",
        "psql", "-U", "mpango", "-d", "mpango_erp",
        "-t", "-A", "-c", "SELECT COUNT(*) FROM t_dev.payments;"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return int(result.stdout.strip())
    return None


def reset_test_data():
    """Reset payments and binding balance for clean test."""
    import subprocess
    subprocess.run([
        "docker", "compose", "exec", "postgres",
        "psql", "-U", "mpango", "-d", "mpango_erp",
        "-c", "DELETE FROM t_dev.payments;"
    ], capture_output=True)
    subprocess.run([
        "docker", "compose", "exec", "postgres",
        "psql", "-U", "mpango", "-d", "mpango_erp",
        "-c", "UPDATE public.wholesaler_retailer_bindings SET outstanding_balance = 50.00 WHERE id='550e8400-e29b-41d4-a716-446655440004';"
    ], capture_output=True)


def get_payments_count():
    """Count payments in DB."""
    import subprocess
    cmd = [
        "docker", "compose", "exec", "postgres",
        "psql", "-U", "mpango", "-d", "mpango_erp",
        "-t", "-A", "-c", "SELECT COUNT(*) FROM t_dev.payments;"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return int(result.stdout.strip())
    return None


@unittest.skipUnless(shutil.which("docker"), "docker CLI not available (running inside container)")
class TestB5RealDB(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Reset payments table for clean test
        import subprocess
        subprocess.run([
            "docker", "compose", "exec", "postgres",
            "psql", "-U", "mpango", "-d", "mpango_erp",
            "-c", "DELETE FROM t_dev.payments;"
        ], capture_output=True)
        # Reset binding balance
        subprocess.run([
            "docker", "compose", "exec", "postgres",
            "psql", "-U", "mpango", "-d", "mpango_erp",
            "-c", "UPDATE public.wholesaler_retailer_bindings SET outstanding_balance = 50.00 WHERE id='550e8400-e29b-41d4-a716-446655440004';"
        ], capture_output=True)

    def test_cash_payment(self):
        """TEST A: Legacy payment endpoint is disabled for cash writes."""
        print("\n=== TEST A: Cash Payment ===")

        resp = self.client.post(
            "/api/v1/payments",
            json={
                "order_id": ORDER_ID,
                "amount": 40,
                "method": "cash"
            }
        )

        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.json()}")

        self.assertEqual(resp.status_code, 409)
        self.assertIn("PAYMENT_WRITE_PATH_DISABLED", str(resp.json()))

    def test_transfer_payment_first(self):
        """TEST B: Legacy payment endpoint is disabled for transfer writes."""
        print("\n=== TEST B: Transfer Payment (First) ===")

        resp = self.client.post(
            "/api/v1/payments",
            headers={"X-Idempotency-Key": f"legacy-disabled-{uuid.uuid4()}"},
            json={
                "order_id": ORDER_ID,
                "amount": 30,
                "method": "transfer",
                "transaction_id": f"TX-{uuid.uuid4()}"
            }
        )

        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.json()}")

        self.assertEqual(resp.status_code, 409)
        self.assertIn("PAYMENT_WRITE_PATH_DISABLED", str(resp.json()))

    def test_idempotent_replay(self):
        """TEST C: Disabled legacy path returns before legacy write behavior."""
        print("\n=== TEST C: Idempotent Replay ===")

        resp = self.client.post(
            "/api/v1/payments",
            json={
                "order_id": ORDER_ID,
                "amount": 30,
                "method": "transfer",
                "transaction_id": f"TX-{uuid.uuid4()}"
            }
        )

        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.json()}")

        self.assertEqual(resp.status_code, 409)
        self.assertIn("PAYMENT_WRITE_PATH_DISABLED", str(resp.json()))

    def test_idempotency_violation(self):
        """TEST D: Legacy path remains disabled for conflicting writes too."""
        print("\n=== TEST D: Idempotency Violation ===")

        resp = self.client.post(
            "/api/v1/payments",
            headers={"X-Idempotency-Key": f"legacy-disabled-{uuid.uuid4()}"},
            json={
                "order_id": ORDER_ID,
                "amount": 35,  # Different amount!
                "method": "transfer",
                "transaction_id": f"TX-{uuid.uuid4()}"
            }
        )

        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.json()}")

        self.assertEqual(resp.status_code, 409)
        self.assertIn("PAYMENT_WRITE_PATH_DISABLED", str(resp.json()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
