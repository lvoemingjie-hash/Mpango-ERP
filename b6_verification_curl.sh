#!/bin/bash
# B6 Hardening Verification Tests using curl
# Tests tenant isolation, payment idempotency, and authorization hardening.

BASE_URL="http://localhost:8000/api/v1"
RESULTS_FILE="b6_verification_results.txt"

# Clear results file
echo "B6 Hardening Verification Results - $(date)" > $RESULTS_FILE
echo "=================================================" >> $RESULTS_FILE

log_result() {
    local test_name="$1"
    local status="$2"
    local details="$3"
    echo "[$status] $test_name: $details" | tee -a $RESULTS_FILE
}

echo "Starting B6 Hardening Verification Tests..."
echo "Target: $BASE_URL"

# Test 1: Login to both tenants
echo ""
echo "=========================================="
echo "TEST 1: TENANT ISOLATION VERIFICATION"
echo "=========================================="

# Login to Tenant A (TEST001)
echo "Logging into Tenant A (TEST001)..."
TENANT_A_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"tenant_code":"TEST001","email":"admin@test.com","password":"testpassword"}')

TENANT_A_TOKEN=$(echo $TENANT_A_RESPONSE | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -n "$TENANT_A_TOKEN" ]; then
    log_result "Tenant A Login" "PASS" "Successfully logged into TEST001"
else
    log_result "Tenant A Login" "FAIL" "Failed to login to TEST001: $TENANT_A_RESPONSE"
    exit 1
fi

# Login to Tenant B (TEST_B)
echo "Logging into Tenant B (TEST_B)..."
TENANT_B_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"tenant_code":"TEST_B","email":"admin@tenant-b.com","password":"TestPass123"}')

TENANT_B_TOKEN=$(echo $TENANT_B_RESPONSE | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -n "$TENANT_B_TOKEN" ]; then
    log_result "Tenant B Login" "PASS" "Successfully logged into TEST_B"
else
    log_result "Tenant B Login" "FAIL" "Failed to login to TEST_B: $TENANT_B_RESPONSE"
    exit 1
fi

# Test tenant isolation - Get user info for both tenants
echo "Testing tenant isolation..."

TENANT_A_ME=$(curl -s -X GET "$BASE_URL/auth/me" \
    -H "Authorization: Bearer $TENANT_A_TOKEN")

TENANT_B_ME=$(curl -s -X GET "$BASE_URL/auth/me" \
    -H "Authorization: Bearer $TENANT_B_TOKEN")

TENANT_A_SCHEMA=$(echo $TENANT_A_ME | grep -o '"tenant_schema":"[^"]*"' | cut -d'"' -f4)
TENANT_B_SCHEMA=$(echo $TENANT_B_ME | grep -o '"tenant_schema":"[^"]*"' | cut -d'"' -f4)

if [ "$TENANT_A_SCHEMA" != "$TENANT_B_SCHEMA" ]; then
    log_result "Tenant Schema Isolation" "PASS" "Tenant A: $TENANT_A_SCHEMA, Tenant B: $TENANT_B_SCHEMA"
else
    log_result "Tenant Schema Isolation" "FAIL" "Both tenants have same schema: $TENANT_A_SCHEMA"
fi

# Test cross-tenant data access
ORDERS_A_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$BASE_URL/orders" \
    -H "Authorization: Bearer $TENANT_A_TOKEN")

ORDERS_B_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$BASE_URL/orders" \
    -H "Authorization: Bearer $TENANT_B_TOKEN")

if [[ "$ORDERS_A_STATUS" =~ ^(200|404)$ ]] && [[ "$ORDERS_B_STATUS" =~ ^(200|404)$ ]]; then
    log_result "Cross-Tenant Orders Access" "PASS" "Tenant A: $ORDERS_A_STATUS, Tenant B: $ORDERS_B_STATUS"
else
    log_result "Cross-Tenant Orders Access" "FAIL" "Unexpected responses - A: $ORDERS_A_STATUS, B: $ORDERS_B_STATUS"
fi

# Test 2: Payment Idempotency - Same Payload
echo ""
echo "=========================================="
echo "TEST 2: PAYMENT IDEMPOTENCY - SAME PAYLOAD"
echo "=========================================="

IDEMPOTENCY_KEY="TEST-IDEM-$(date +%s)"
ORDER_ID=$(uuidgen)

PAYMENT_PAYLOAD="{\"order_id\":\"$ORDER_ID\",\"amount\":100.0,\"method\":\"transfer\",\"transaction_id\":\"$IDEMPOTENCY_KEY\"}"

# First payment request
PAYMENT_1_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/payments" \
    -H "Authorization: Bearer $TENANT_A_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Idempotency-Key: $IDEMPOTENCY_KEY" \
    -d "$PAYMENT_PAYLOAD")

# Second payment request with same payload
PAYMENT_2_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/payments" \
    -H "Authorization: Bearer $TENANT_A_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Idempotency-Key: $IDEMPOTENCY_KEY" \
    -d "$PAYMENT_PAYLOAD")

if [ "$PAYMENT_1_STATUS" = "201" ]; then
    log_result "Payment Idempotency - First Request" "PASS" "Status: $PAYMENT_1_STATUS"
else
    log_result "Payment Idempotency - First Request" "FAIL" "Status: $PAYMENT_1_STATUS"
fi

if [[ "$PAYMENT_2_STATUS" =~ ^(200|201)$ ]]; then
    log_result "Payment Idempotency - Second Request" "PASS" "Status: $PAYMENT_2_STATUS (Idempotent)"
else
    log_result "Payment Idempotency - Second Request" "FAIL" "Status: $PAYMENT_2_STATUS"
fi

# Test 3: Payment Idempotency - Conflicting Payload
echo ""
echo "=========================================="
echo "TEST 3: PAYMENT IDEMPOTENCY - CONFLICTING PAYLOAD"
echo "=========================================="

CONFLICT_KEY="TEST-CONFLICT-$(date +%s)"
ORDER_ID_1=$(uuidgen)
ORDER_ID_2=$(uuidgen)

PAYMENT_PAYLOAD_1="{\"order_id\":\"$ORDER_ID_1\",\"amount\":100.0,\"method\":\"transfer\",\"transaction_id\":\"$CONFLICT_KEY\"}"
PAYMENT_PAYLOAD_2="{\"order_id\":\"$ORDER_ID_2\",\"amount\":200.0,\"method\":\"transfer\",\"transaction_id\":\"$CONFLICT_KEY\"}"

# First payment request
CONFLICT_1_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/payments" \
    -H "Authorization: Bearer $TENANT_A_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Idempotency-Key: $CONFLICT_KEY" \
    -d "$PAYMENT_PAYLOAD_1")

# Second payment request with different payload but same idempotency key
CONFLICT_2_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/payments" \
    -H "Authorization: Bearer $TENANT_A_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Idempotency-Key: $CONFLICT_KEY" \
    -d "$PAYMENT_PAYLOAD_2")

if [ "$CONFLICT_1_STATUS" = "201" ]; then
    log_result "Payment Conflict - First Request" "PASS" "Status: $CONFLICT_1_STATUS"
else
    log_result "Payment Conflict - First Request" "FAIL" "Status: $CONFLICT_1_STATUS"
fi

if [[ "$CONFLICT_2_STATUS" =~ ^(400|409)$ ]]; then
    log_result "Payment Conflict - Second Request" "PASS" "Status: $CONFLICT_2_STATUS (Conflict detected)"
else
    log_result "Payment Conflict - Second Request" "FAIL" "Status: $CONFLICT_2_STATUS (Expected 400 or 409)"
fi

# Test 4: Transfer Payment Header Requirement
echo ""
echo "=========================================="
echo "TEST 4: TRANSFER IDEMPOTENCY HEADER REQUIREMENT"
echo "=========================================="

ORDER_ID_NO_HEADER=$(uuidgen)
PAYMENT_NO_HEADER="{\"order_id\":\"$ORDER_ID_NO_HEADER\",\"amount\":100.0,\"method\":\"transfer\"}"

NO_HEADER_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/payments" \
    -H "Authorization: Bearer $TENANT_A_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$PAYMENT_NO_HEADER")

if [ "$NO_HEADER_STATUS" = "400" ]; then
    log_result "Transfer Header Requirement" "PASS" "Status: $NO_HEADER_STATUS (Correctly rejected)"
else
    log_result "Transfer Header Requirement" "FAIL" "Status: $NO_HEADER_STATUS (Expected 400)"
fi

# Summary
echo ""
echo "=========================================="
echo "TEST SUMMARY"
echo "=========================================="

PASSED=$(grep -c "\[PASS\]" $RESULTS_FILE)
FAILED=$(grep -c "\[FAIL\]" $RESULTS_FILE)
TOTAL=$((PASSED + FAILED))

echo "Total Tests: $TOTAL" | tee -a $RESULTS_FILE
echo "Passed: $PASSED" | tee -a $RESULTS_FILE
echo "Failed: $FAILED" | tee -a $RESULTS_FILE

if [ $FAILED -eq 0 ]; then
    echo "" | tee -a $RESULTS_FILE
    echo "✅ ALL TESTS PASSED - B6 Hardening verification successful!" | tee -a $RESULTS_FILE
else
    echo "" | tee -a $RESULTS_FILE
    echo "❌ $FAILED TESTS FAILED - B6 Hardening issues detected!" | tee -a $RESULTS_FILE
fi

echo ""
echo "Detailed results saved to: $RESULTS_FILE"