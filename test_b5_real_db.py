#!/usr/bin/env python3
"""
Phase B5 Payments Minimal Loop - Real DB Verification
Runs from host machine against running backend container.
"""
import os
import sys
import json
import subprocess
import time

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
API_URL = f"{BASE_URL}/api/v1/payments"

# Test data IDs (must exist in real DB)
ORDER_ID = "550e8400-e29b-41d4-a716-446655440002"
BINDING_ID = "550e8400-e29b-41d4-a716-446655440004"


def log(msg):
    print(f"[B5] {msg}")


def get_binding_balance():
    """Query outstanding_balance from DB."""
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
    log("Resetting test data...")
    subprocess.run([
        "docker", "compose", "exec", "postgres",
        "psql", "-U", "mpango", "-d", "mpango_erp",
        "-c", "DELETE FROM t_dev.payments;"
    ], capture_output=True)
    subprocess.run([
        "docker", "compose", "exec", "postgres",
        "psql", "-U", "mpango", "-d", "mpango_erp",
        "-c", f"UPDATE public.wholesaler_retailer_bindings SET outstanding_balance = 50.00 WHERE id='{BINDING_ID}';"
    ], capture_output=True)
    log("Test data reset complete.")


def http_post(url, json_body, headers=None):
    """Make POST request using curl."""
    cmd = ["curl", "-s", "-X", "POST", url, "-H", "Content-Type: application/json"]
    if headers:
        for k, v in headers.items():
            cmd.extend(["-H", f"{k}: {v}"])
    cmd.extend(["-d", json.dumps(json_body)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return {"status_code": 0, "body": json.loads(result.stdout)}
    except json.JSONDecodeError:
        return {"status_code": 0, "body": result.stdout, "raw": True}


def test_cash_payment():
    log("=== TEST A: Cash Payment ===")

    balance_before = get_binding_balance()
    count_before = get_payments_count()
    log(f"Balance before: {balance_before}")
    log(f"Payments count before: {count_before}")

    resp = http_post(
        API_URL,
        json_body={
            "order_id": ORDER_ID,
            "amount": 40,
            "method": "cash"
        }
    )

    log(f"Response: {json.dumps(resp['body'], indent=2)}")

    assert resp["body"].get("success") == True, f"Cash payment failed: {resp['body']}"

    balance_after = get_binding_balance()
    count_after = get_payments_count()
    log(f"Balance after: {balance_after}")
    log(f"Payments count after: {count_after}")

    assert balance_after == balance_before - 40, f"Balance should reduce by 40, got {balance_before} -> {balance_after}"
    assert count_after == count_before + 1, "Should have created 1 payment"

    log("✅ Cash payment PASSED")
    return balance_after


def test_transfer_payment_first():
    log("=== TEST B: Transfer Payment (First) ===")

    balance_before = get_binding_balance()
    count_before = get_payments_count()
    log(f"Balance before: {balance_before}")
    log(f"Payments count before: {count_before}")

    resp = http_post(
        API_URL,
        json_body={
            "order_id": ORDER_ID,
            "amount": 30,
            "method": "transfer",
            "transaction_id": "TX001"
        },
        headers={"Idempotency-Key": "tx-001"}
    )

    log(f"Response: {json.dumps(resp['body'], indent=2)}")

    assert resp["body"].get("success") == True, f"Transfer payment failed: {resp['body']}"

    balance_after = get_binding_balance()
    count_after = get_payments_count()
    log(f"Balance after: {balance_after}")
    log(f"Payments count after: {count_after}")

    assert balance_after == balance_before - 30, f"Balance should reduce by 30, got {balance_before} -> {balance_after}"
    assert count_after == count_before + 1, "Should have created 1 payment"

    log("✅ Transfer payment (first) PASSED")
    return balance_after


def test_idempotent_replay():
    log("=== TEST C: Idempotent Replay ===")

    balance_before = get_binding_balance()
    count_before = get_payments_count()
    log(f"Balance before: {balance_before}")
    log(f"Payments count before: {count_before}")

    resp = http_post(
        API_URL,
        json_body={
            "order_id": ORDER_ID,
            "amount": 30,
            "method": "transfer",
            "transaction_id": "TX001"
        },
        headers={"Idempotency-Key": "tx-001"}
    )

    log(f"Response: {json.dumps(resp['body'], indent=2)}")

    assert resp["body"].get("success") == True, f"Idempotent replay failed: {resp['body']}"

    balance_after = get_binding_balance()
    count_after = get_payments_count()
    log(f"Balance after: {balance_after}")
    log(f"Payments count after: {count_after}")

    # Balance and count should NOT change on replay
    assert balance_after == balance_before, f"Balance should NOT change on replay, got {balance_before} -> {balance_after}"
    assert count_after == count_before, f"Payment count should NOT change on replay, got {count_before} -> {count_after}"

    log("✅ Idempotent replay PASSED")


def test_idempotency_violation():
    log("=== TEST D: Idempotency Violation ===")

    balance_before = get_binding_balance()
    count_before = get_payments_count()
    log(f"Balance before: {balance_before}")
    log(f"Payments count before: {count_before}")

    resp = http_post(
        API_URL,
        json_body={
            "order_id": ORDER_ID,
            "amount": 35,  # Different amount!
            "method": "transfer",
            "transaction_id": "TX001"
        },
        headers={"Idempotency-Key": "tx-001"}
    )

    log(f"Response: {json.dumps(resp['body'], indent=2)}")

    # Should return error (not success)
    assert resp["body"].get("success") != True, f"Expected failure, got success: {resp['body']}"

    balance_after = get_binding_balance()
    count_after = get_payments_count()
    log(f"Balance after: {balance_after}")
    log(f"Payments count after: {count_after}")

    # Balance and count should NOT change
    assert balance_after == balance_before, f"Balance should NOT change on violation, got {balance_before} -> {balance_after}"
    assert count_after == count_before, f"Payment count should NOT change on violation, got {count_before} -> {count_after}"

    log("✅ Idempotency violation PASSED")


def main():
    log("Phase B5 Payments Minimal Loop - Ops Verification")
    log(f"Base URL: {BASE_URL}")
    log(f"Order ID: {ORDER_ID}\n")

    try:
        # Reset test data
        reset_test_data()

        # Step A: Cash payment
        balance_after_cash = test_cash_payment()

        # Step B: Transfer payment (first)
        balance_after_transfer = test_transfer_payment_first()

        # Step C: Idempotent replay
        test_idempotent_replay()

        # Step D: Idempotency violation
        test_idempotency_violation()

        log("=" * 50)
        log("🎉 ALL PHASE B5 TESTS PASSED")
        log("=" * 50)
        log(f"Balance progression: 50 → {balance_after_cash} → {balance_after_transfer}")

    except AssertionError as e:
        log(f"❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"❌ ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
