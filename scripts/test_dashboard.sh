#!/bin/bash
set -e

echo '=== Step 1: Login ==='
LOGIN_RESP=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@mpango.demo","password":"DemoAdmin2026!"}')
echo "$LOGIN_RESP" | python3 -m json.tool 2>/dev/null || echo "$LOGIN_RESP"

IDENTITY_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['access_token'])")
TENANT_ID=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['available_tenants'][0]['id'])")
echo "Identity Token: ${IDENTITY_TOKEN:0:30}..."
echo "Tenant ID: $TENANT_ID"

echo ''
echo '=== Step 2: Select Tenant ==='
CTX_RESP=$(curl -s -X POST http://localhost:8000/api/v1/auth/select-tenant \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $IDENTITY_TOKEN" \
  -d "{\"tenant_id\":\"$TENANT_ID\"}")
echo "$CTX_RESP" | python3 -m json.tool 2>/dev/null || echo "$CTX_RESP"

CTX_TOKEN=$(echo "$CTX_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['access_token'])")
echo "Contextual Token: ${CTX_TOKEN:0:30}..."

echo ''
echo '=== Step 3: Test Dashboard KPI ==='
curl -s -w '\nHTTP_CODE: %{http_code}\n' \
  http://localhost:8000/api/v1/dashboards/kpi/summary \
  -H "Authorization: Bearer $CTX_TOKEN"

echo ''
echo '=== Step 4: Test Orders ==='
curl -s -w '\nHTTP_CODE: %{http_code}\n' \
  "http://localhost:8000/api/v1/orders?page=1&size=5" \
  -H "Authorization: Bearer $CTX_TOKEN"

echo ''
echo '=== Step 5: Test Inventory ==='
curl -s -w '\nHTTP_CODE: %{http_code}\n' \
  "http://localhost:8000/api/v1/inventory/stocks?page=1&size=10" \
  -H "Authorization: Bearer $CTX_TOKEN"
