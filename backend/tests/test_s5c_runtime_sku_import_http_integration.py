"""S5-C-R4 Runtime SKU Import HTTP Integration Test.

REQUIRES DEPLOYMENT: This test hits a live backend over HTTP.
Requires these environment variables to be set:
  MPANGO_RUNTIME_BASE_URL     - e.g. http://localhost:80
  MPANGO_RUNTIME_TEST_EMAIL   - valid login email
  MPANGO_RUNTIME_TEST_PASSWORD - valid login password (NOT printed in output)
  MPANGO_RUNTIME_TENANT_ID    - UUID of tenant to test with

If any are missing, ALL tests in this file are SKIPPED.

Validates the full import HTTP pipeline after R4 fix:
  1. Login -> get JWT
  2. Select tenant -> get tenant-scoped token
  3. POST /api/v1/skus/import/preview -> 200 + import_id
  4. POST /api/v1/skus/import/{import_id}/validate -> 200 + status
  5. POST /api/v1/skus/import/{import_id}/apply -> 200
"""
from __future__ import annotations

import csv
import io
import os
import uuid

import httpx
import pytest


# -- Environment gating ------------------------------------------------
_BASE_URL = os.environ.get("MPANGO_RUNTIME_BASE_URL")
_EMAIL = os.environ.get("MPANGO_RUNTIME_TEST_EMAIL")
_PASSWORD = os.environ.get("MPANGO_RUNTIME_TEST_PASSWORD")
_TENANT_ID = os.environ.get("MPANGO_RUNTIME_TENANT_ID")

_RUNTIME_MISSING = not all([_BASE_URL, _EMAIL, _PASSWORD, _TENANT_ID])

_skip_reason = (
    "runtime import HTTP proof requires MPANGO_RUNTIME_BASE_URL, "
    "MPANGO_RUNTIME_TEST_EMAIL, MPANGO_RUNTIME_TEST_PASSWORD, "
    "MPANGO_RUNTIME_TENANT_ID"
)


def _make_csv(rows: list[dict]) -> bytes:
    """Create CSV bytes from a list of row dicts."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


@pytest.mark.asyncio
@pytest.mark.skipif(_RUNTIME_MISSING, reason=_skip_reason)
async def test_sku_import_preview_validate_apply_happy_path():
    """Full authenticated import HTTP pipeline: preview -> validate -> apply."""
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0) as client:
        # Step 1: Login
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": _EMAIL, "password": _PASSWORD},
        )
        assert login_resp.status_code == 200, (
            f"Login failed: {login_resp.status_code}"
        )
        access_token = login_resp.json()["data"]["access_token"]

        # Step 2: Select tenant
        select_resp = await client.post(
            "/api/v1/auth/select-tenant",
            json={"tenant_id": _TENANT_ID},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert select_resp.status_code == 200, (
            f"Select tenant failed: {select_resp.status_code}"
        )
        tenant_token = select_resp.json()["data"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {tenant_token}"}

        # Step 3: Preview
        sku_code = f"R4-TEST-{uuid.uuid4().hex[:8].upper()}"
        csv_bytes = _make_csv([
            {"sku_code": sku_code, "name": "R4 Test Product", "unit": "piece"},
        ])

        preview_resp = await client.post(
            "/api/v1/skus/import/preview",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
            headers=auth_headers,
        )
        assert preview_resp.status_code == 200, (
            f"Preview failed: {preview_resp.status_code}"
        )
        preview_data = preview_resp.json()
        assert preview_data["success"] is True
        import_id = preview_data["data"]["import_id"]
        assert import_id is not None

        # Step 4: Validate
        validate_resp = await client.post(
            f"/api/v1/skus/import/{import_id}/validate",
            json={"mapping": {"sku_code": "sku_code", "name": "name", "unit": "unit"}},
            headers=auth_headers,
        )
        assert validate_resp.status_code == 200, (
            f"Validate failed: {validate_resp.status_code}"
        )
        validate_data = validate_resp.json()
        assert validate_data["success"] is True

        # Step 5: Apply
        apply_resp = await client.post(
            f"/api/v1/skus/import/{import_id}/apply",
            json={"on_conflict": "skip"},
            headers=auth_headers,
        )
        assert apply_resp.status_code == 200, (
            f"Apply failed: {apply_resp.status_code}"
        )
        apply_data = apply_resp.json()
        assert apply_data["success"] is True


@pytest.mark.asyncio
@pytest.mark.skipif(_RUNTIME_MISSING, reason=_skip_reason)
async def test_sku_import_preview_returns_401_without_token():
    """Preview without auth must return 401, not 500."""
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=10.0) as client:
        csv_bytes = _make_csv([{"sku_code": "X", "name": "X"}])
        resp = await client.post(
            "/api/v1/skus/import/preview",
            files={"file": ("test.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 401
