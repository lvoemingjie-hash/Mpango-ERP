"""
P25-EC-R1 Identity Smoke Test -- Real-Stack Auth Boundary Verification.

Tests P10 platform guard against a running backend (uvicorn + Docker Postgres).
Provisions a minimal throwaway tenant schema (t_smoke_r1) with RBAC tables and
a seed user so that middleware resolve_tenant_context succeeds cleanly.  This
isolates the P10 auth boundary: we prove the guard admits identity-only
super_admin tokens and rejects tenant-context tokens with a clean 403.

R1 CHANGE: tenant_context_admin_deny must be a clean 401/403 -- NOT 500.
The previous run accepted 500 (TenantContextMissingError / UndefinedTable)
which is a middleware crash, not a clean denial.

Verifies:
  1. X-Platform-Operator header -> admitted (200)
  2. X-Platform-Test-Override header (prod env) -> rejected (403)
  3. Identity-only super_admin JWT -> admitted (200)
  4. No credentials -> denied (401)
  5. Wrong operator secret -> denied (403)
  6. Tenant-context super_admin JWT -> denied (401 or 403)

Usage:
  cd backend
  python ../verify/p25ec/identity_smoke.py
"""
import json
import os
import sys
import urllib.request
import urllib.error

# Ensure backend imports resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../../backend")

from core.security import create_identity_token, create_contextual_token

BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8001")
# P24 list_closeouts: guarded by require_platform_operator (P10 guard) but uses
# an IN-MEMORY store (no get_db dependency).  This isolates the P10 auth
# boundary from any tenant-schema DB dependency in the route handler.
ENDPOINT = "/api/v1/platform/p24/incident-closeouts"
FULL_URL = BASE_URL + ENDPOINT

OPERATOR_SECRET = os.environ.get("PLATFORM_OPERATOR_SECRET", "test-operator-secret")
TEST_OVERRIDE = os.environ.get("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")

# Tenant schema provisioned for this smoke test.
# SQL: CREATE SCHEMA t_smoke_r1; CREATE TABLE users/roles/permissions/user_roles/
#      role_permissions; INSERT seed user.
SMOKE_TENANT_SCHEMA = "t_smoke_r1"
SMOKE_TENANT_ID = "00000000-0000-0000-0000-000000000099"
SMOKE_USER_ID = "00000000-0000-0000-0000-000000000002"

results = []


def test_case(name, headers, expected_status_range, description):
    """Run a single test case and record the result."""
    req = urllib.request.Request(FULL_URL, method="GET")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        body = resp.read().decode()[:300]
        passed = status in expected_status_range
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode()[:300]
        passed = status in expected_status_range
    except Exception as e:
        status = -1
        body = str(e)[:300]
        passed = False

    results.append({
        "test": name,
        "description": description,
        "expected_status": str(sorted(expected_status_range)),
        "actual_status": status,
        "passed": passed,
        "body_preview": body,
    })
    marker = "PASS" if passed else "FAIL"
    print("[%s] %s: got %s (expected %s)" % (marker, name, status, sorted(expected_status_range)))


# -- Generate JWT tokens --

# Identity-only super_admin token (no tenant context)
identity_super_admin_jwt = create_identity_token(
    user_id="00000000-0000-0000-0000-000000000001",
    roles=["super_admin"],
)

# Tenant-context super_admin token (has tenant_id + tenant_schema).
# Points to the provisioned throwaway schema t_smoke_r1 where a seed user
# exists.  The middleware resolve_tenant_context will succeed, then the P10
# guard rejects because is_identity_only is False.
tenant_super_admin_jwt = create_contextual_token(
    user_id=SMOKE_USER_ID,
    roles=["super_admin"],
    tenant_id=SMOKE_TENANT_ID,
    tenant_schema=SMOKE_TENANT_SCHEMA,
)


# -- Run test cases --

print("=" * 70)
print("P25-EC-R1 Identity Smoke Test")
print("Endpoint: %s" % FULL_URL)
print("MPANGO_ENV: %s" % os.environ.get("MPANGO_ENV", "?"))
print("Tenant schema: %s (provisioned throwaway)" % SMOKE_TENANT_SCHEMA)
print("=" * 70)

# 1. X-Platform-Operator header -> 200
test_case(
    "operator_admit",
    {"X-Platform-Operator": OPERATOR_SECRET},
    {200},
    "Valid X-Platform-Operator secret should be admitted",
)

# 2. X-Platform-Test-Override header -> 403 in production env
test_case(
    "test_override",
    {"X-Platform-Test-Override": TEST_OVERRIDE},
    {403},
    "X-Platform-Test-Override rejected in production env (403)",
)

# 3. Identity-only super_admin JWT -> 200
test_case(
    "identity_super_admin_admit",
    {"Authorization": "Bearer " + identity_super_admin_jwt},
    {200},
    "Identity-only super_admin Bearer token should be admitted",
)

# 4. No credentials -> 401
test_case(
    "no_credentials_deny",
    {},
    {401},
    "No credentials should be denied (401)",
)

# 5. Wrong operator secret -> 403
test_case(
    "wrong_operator_deny",
    {"X-Platform-Operator": "wrong-secret-value"},
    {403},
    "Wrong X-Platform-Operator secret should be denied (403)",
)

# 6. Tenant-context super_admin JWT -> clean denial (401 or 403)
# R1 FIX: with a provisioned tenant schema, the middleware
# resolve_tenant_context succeeds.  The P10 guard then checks
# is_identity_only and rejects the token with 403 because the token
# carries tenant context (is_identity_only=False).
test_case(
    "tenant_context_admin_deny",
    {"Authorization": "Bearer " + tenant_super_admin_jwt},
    {401, 403},
    "Tenant-context super_admin token denied cleanly (401 or 403, NOT 500)",
)

# -- Summary --
print("=" * 70)
total = len(results)
passed = sum(1 for r in results if r["passed"])
failed = total - passed
print("Results: %d/%d passed, %d failed" % (passed, total, failed))
print("=" * 70)

# Output JSON for evidence capture
output = {
    "test_suite": "P25-EC-R1 Identity Smoke Test",
    "endpoint": FULL_URL,
    "mpango_env": os.environ.get("MPANGO_ENV", "?"),
    "tenant_schema": SMOKE_TENANT_SCHEMA,
    "summary": {"total": total, "passed": passed, "failed": failed},
    "cases": results,
}
print("\nJSON_EVIDENCE_START")
print(json.dumps(output, indent=2))
print("JSON_EVIDENCE_END")
