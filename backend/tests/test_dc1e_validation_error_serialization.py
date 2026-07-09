"""DC-1E validation error serialization regressions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from core.error_codes import validation_exception_handler
from core.security import TokenPayload


def test_pay_route_invalid_decimal_validation_error_returns_json_4xx_not_500(monkeypatch):
    """Canonical pay route must serialize Decimal validation details safely."""
    from api.dependencies import get_tenant_db_session
    from api.middleware import rbac as rbac_module
    from main import app

    token = TokenPayload(user_id="dc1e-user", roles=["super_admin"])
    original_get_auth_context = rbac_module.get_auth_context

    def _fake_auth_context(_request):
        return SimpleNamespace(token=token)

    def _fake_tenant_db_session():
        return MagicMock()

    rbac_module.get_auth_context = _fake_auth_context
    app.dependency_overrides[get_tenant_db_session] = _fake_tenant_db_session
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/v1/orders/{uuid.uuid4()}/pay?request=test",
            json={"amount": -1, "method": "cash"},
        )
    finally:
        rbac_module.get_auth_context = original_get_auth_context
        app.dependency_overrides.pop(get_tenant_db_session, None)

    assert 400 <= response.status_code < 500, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "Object of type Decimal is not JSON serializable" not in response.text
    assert "traceback" not in response.text.lower()


@pytest.mark.asyncio
async def test_validation_exception_handler_json_encodes_decimal_uuid_datetime_and_nested_values():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orders/test/pay",
            "headers": [],
        }
    )
    generated_id = uuid.uuid4()
    happened_at = datetime.now(timezone.utc)
    exc = RequestValidationError(
        [
            {
                "type": "greater_than",
                "loc": ("body", "amount"),
                "msg": "Input should be greater than 0",
                "input": Decimal("-1.00"),
                "ctx": {
                    "gt": Decimal("0"),
                    "order_id": generated_id,
                    "happened_at": happened_at,
                    "nested": [
                        {"amount": Decimal("10.50")},
                        {"ids": [generated_id]},
                    ],
                },
            }
        ]
    )

    response = await validation_exception_handler(request, exc)

    assert response.status_code == 422
    body = json.loads(response.body)
    validation_error = body["details"]["validation_errors"][0]
    assert validation_error["input"] == -1.0
    assert validation_error["ctx"]["gt"] == 0
    assert validation_error["ctx"]["order_id"] == str(generated_id)
    assert validation_error["ctx"]["happened_at"] == happened_at.isoformat()
    assert validation_error["ctx"]["nested"][0]["amount"] == 10.5
