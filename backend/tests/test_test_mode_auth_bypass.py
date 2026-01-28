import os
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class TestTestModeAuthBypass(unittest.TestCase):
    def test_payments_endpoint_callable_without_jwt_when_test_mode(self):
        os.environ["MPANGO_TEST_MODE"] = "true"

        from main import app

        async def _fake_create_payment(
            self,
            *,
            tenant_db,
            order_id,
            amount,
            method,
            transaction_id,
            created_by,
        ):
            return {
                "id": "11111111-1111-1111-1111-111111111111",
                "order_id": order_id,
                "retailer_id": "22222222-2222-2222-2222-222222222222",
                "transaction_id": transaction_id,
                "amount": amount,
                "method": method,
                "status": "pending",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }

        with patch(
            "services.payment_service.PaymentService.create_payment",
            new=_fake_create_payment,
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/v1/payments",
                json={
                    "order_id": "550e8400-e29b-41d4-a716-446655440002",
                    "amount": 100.0,
                    "method": "cash",
                },
            )

        self.assertEqual(resp.status_code, 201)
        payload = resp.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["order_id"], "550e8400-e29b-41d4-a716-446655440002")


if __name__ == "__main__":
    unittest.main()
