#!/usr/bin/env python3
"""
Phase B5 Payments Minimal Loop - Ops Verification Script
Tests cash payment, transfer with idempotency against real DB in test mode.
"""
import os
import sys
import json
import time
import requests

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
API_URL = f"{BASE_URL}/api/v1/payments"

HEADERS = {
    "Content-Type": "application/json",
    # In test mode, no JWT required - auth bypass handles this
}

ORDER_ID = "550e8400-e29b-41d4-a716-446655440002"

def log(msg):
    print(f"[B5] {msg}")

def get_binding_balance():
    """Query outstanding_balance from DB directly for verification."""
    # Use docker exec to query PostgreSQL
    import subprocess
    cmd = [
        "docker", "compose", "exec", "postgres",
        "psql", "-U", "mpango", "-d", "mpango_erp",
        "-t", "-A", "-F", "|",
        "-c", "SELECT outstanding_balance FROM public.wholesaler_retailer_bindings WHERE id='550e8400-e29b-41d4-a716-446655440004';"
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

def test_cash_payment():
    log("=== TEST A: Cash Payment ===")
    
    balance_before = get_binding_balance()
    count_before = get_payments_count()
    log(f"Balance before: {balance_before}")
    log(f"Payments count before: {count_before}")
    
    payload = {
        "order_id": ORDER_ID,
        "amount": 40,
        "method": "cash"
    }
    
    resp = requests.post(API_URL, headers=HEADERS, json=payload)
    log(f"Status: {resp.status_code}")
    log(f"Response: {json.dumps(resp.json(), indent=2)}")
    
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}"
    
    balance_after = get_binding_balance()
    count_after = get_payments_count()
    log(f"Balance after: {balance_after}")
    log(f"Payments count after: {count_after}")
    
    # Cash payment should reduce outstanding balance
    assert balance_after == balance_before - 40, f"Balance should reduce by 40"
    assert count_after == count_before + 1, "Should have created 1 payment"
    
    log("✅ Cash payment PASSED\n")
    return balance_after

def test_transfer_payment_first():
    log("=== TEST B: Transfer Payment (First) ===")
    
    balance_before = get_binding_balance()
    count_before = get_payments_count()
    log(f"Balance before: {balance_before}")
    log(f"Payments count before: {count_before}")
    
    idempotency_key = "tx-001"
    headers = {**HEADERS, "Idempotency-Key": idempotency_key}
    
    payload = {
        "order_id": ORDER_ID,
        "amount": 30,
        "method": "transfer",
        "transaction_id": "TX001"
    }
    
    resp = requests.post(API_URL, headers=headers, json=payload)
    log(f"Status: {resp.status_code}")
    log(f"Response: {json.dumps(resp.json(), indent=2)}")
    
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}"
    
    balance_after = get_binding_balance()
    count_after = get_payments_count()
    log(f"Balance after: {balance_after}")
    log(f"Payments count after: {count_after}")
    
    # Transfer payment should reduce outstanding balance
    assert balance_after == balance_before - 30, f"Balance should reduce by 30"
    assert count_after == count_before + 1, "Should have created 1 payment"
    
    log("✅ Transfer payment (first) PASSED\n")
    return balance_after

def test_idempotent_replay():
    log("=== TEST C: Idempotent Replay (Same Request) ===")
    
    balance_before = get_binding_balance()
    count_before = get_payments_count()
    log(f"Balance before: {balance_before}")
    log(f"Payments count before: {count_before}")
    
    idempotency_key = "tx-001"
    headers = {**HEADERS, "Idempotency-Key": idempotency_key}
    
    payload = {
        "order_id": ORDER_ID,
        "amount": 30,
        "method": "transfer",
        "transaction_id": "TX001"
    }
    
    resp = requests.post(API_URL, headers=headers, json=payload)
    log(f"Status: {resp.status_code}")
    log(f"Response: {json.dumps(resp.json(), indent=2)}")
    
    # Idempotent replay should return same success status
    assert resp.status_code == 201, f"Expected 201 (idempotent), got {resp.status_code}"
    
    balance_after = get_binding_balance()
    count_after = get_payments_count()
    log(f"Balance after: {balance_after}")
    log(f"Payments count after: {count_after}")
    
    # Balance and count should NOT change on replay
    assert balance_after == balance_before, "Balance should NOT change on replay"
    assert count_after == count_before, "Payment count should NOT change on replay"
    
    log("✅ Idempotent replay PASSED\n")

def test_idempotency_violation():
    log("=== TEST D: Idempotency Violation (Same tx_id, different amount) ===")
    
    balance_before = get_binding_balance()
    count_before = get_payments_count()
    log(f"Balance before: {balance_before}")
    log(f"Payments count before: {count_before}")
    
    idempotency_key = "tx-001"
    headers = {**HEADERS, "Idempotency-Key": idempotency_key}
    
    payload = {
        "order_id": ORDER_ID,
        "amount": 35,  # Different amount!
        "method": "transfer",
        "transaction_id": "TX001"
    }
    
    resp = requests.post(API_URL, headers=headers, json=payload)
    log(f"Status: {resp.status_code}")
    log(f"Response: {json.dumps(resp.json(), indent=2)}")
    
    # Should return 409 Conflict
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}"
    
    balance_after = get_binding_balance()
    count_after = get_payments_count()
    log(f"Balance after: {balance_after}")
    log(f"Payments count after: {count_after}")
    
    # Balance and count should NOT change
    assert balance_after == balance_before, "Balance should NOT change on violation"
    assert count_after == count_before, "Payment count should NOT change on violation"
    
    log("✅ Idempotency violation PASSED\n")

def main():
    log("Phase B5 Payments Minimal Loop - Ops Verification")
    log(f"Base URL: {BASE_URL}")
    log(f"Order ID: {ORDER_ID}\n")
    
    try:
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
    except requests.exceptions.ConnectionError:
        log("❌ Connection failed. Is the backend running?")
        log(f"URL: {API_URL}")
        sys.exit(1)

if __name__ == "__main__":
    main()
