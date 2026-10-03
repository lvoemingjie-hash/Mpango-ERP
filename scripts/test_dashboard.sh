#!/bin/bash
set -e
for name in MPANGO_DASHBOARD_BASE_URL MPANGO_TEST_ADMIN_PASSWORD; do
    if [[ -z "${!name:-}" || -z "${!name//[[:space:]]/}" ]]; then
        printf 'SMOKE_INPUT_REQUIRED: %s\n' "$name" >&2
        exit 2
    fi
done
BASE_URL="$MPANGO_DASHBOARD_BASE_URL"

echo '=== Step 1: Login ==='
LOGIN_RESP=$(python3 -c 'import json,os; print(json.dumps(dict(email="admin@mpango.demo",password=os.environ["MPANGO_TEST_ADMIN_PASSWORD"])))' | curl -s -X POST "$BASE_URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d @-)
echo 'Login response received (credentials/tokens not displayed)'

IDENTITY_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['access_token'])")
TENANT_ID=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['available_tenants'][0]['id'])")
echo 'Identity token acquired (not displayed)'
echo "Tenant ID: $TENANT_ID"

echo ''
echo '=== Step 2: Select Tenant ==='
CTX_RESP=$(curl -s -X POST "$BASE_URL/auth/select-tenant" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $IDENTITY_TOKEN" \
  -d "{\"tenant_id\":\"$TENANT_ID\"}")
echo 'Context response received (token not displayed)'

CTX_TOKEN=$(echo "$CTX_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['access_token'])")
echo 'Context token acquired (not displayed)'

echo ''
echo '=== Step 3: Test Dashboard KPI ==='
curl -s -w '\nHTTP_CODE: %{http_code}\n' \
  "$BASE_URL/dashboards/kpi/summary" \
  -H "Authorization: Bearer $CTX_TOKEN"

echo ''
echo '=== Step 4: Test Orders ==='
curl -s -w '\nHTTP_CODE: %{http_code}\n' \
  "$BASE_URL/orders?page=1&size=5" \
  -H "Authorization: Bearer $CTX_TOKEN"

echo ''
echo '=== Step 5: Test Inventory ==='
curl -s -w '\nHTTP_CODE: %{http_code}\n' \
  "$BASE_URL/inventory/stocks?page=1&size=10" \
  -H "Authorization: Bearer $CTX_TOKEN"
