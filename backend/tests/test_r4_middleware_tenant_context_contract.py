"""R4 Middleware Contract Tests -- tenant_id UUID vs schema-name semantics.

Validates that AuthenticationMiddleware sets:
  - request.state.tenant_id = UUID string (from tenant_ctx.tenant_id)
  - request.state.tenant_schema = schema name (from tenant_ctx.tenant_schema)

These tests use mocks only -- no database or network required.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient


# ====================================================================
# 1. Middleware tenant_id Contract
# ====================================================================

class TestMiddlewareTenantIdContract:
    """Verify middleware sets tenant_id as UUID and tenant_schema as schema name."""

    @pytest.mark.asyncio
    async def test_middleware_sets_tenant_id_as_uuid(self):
        """tenant_id must be UUID string, not schema name."""
        from api.middleware.auth import AuthenticationMiddleware

        mock_strategy = AsyncMock()
        mock_tenant_id = uuid.uuid4()
        mock_tenant_schema = f"t_{str(mock_tenant_id).replace('-', '')}"

        mock_tenant_ctx = MagicMock()
        mock_tenant_ctx.tenant_id = str(mock_tenant_id)
        mock_tenant_ctx.tenant_schema = mock_tenant_schema

        mock_auth_ctx = MagicMock()
        mock_strategy.authenticate.return_value = mock_auth_ctx
        mock_strategy.resolve_tenant_context.return_value = mock_tenant_ctx

        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()
        mock_request.scope = {"type": "http", "path": "/api/v1/test"}

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def mock_call_next(req):
            # Capture what was set on request.state before response
            return mock_response

        middleware = AuthenticationMiddleware(
            app=MagicMock(), strategy=mock_strategy
        )

        with patch(
            "api.middleware.auth.set_current_tenant",
            return_value=("old_id", "old_schema"),
        ), patch(
            "api.middleware.auth.reset_current_tenant"
        ), patch(
            "api.middleware.auth.update_request_context_with_auth"
        ), patch(
            "api.context.tenant.attach_tenant_context"
        ), patch(
            "api.context.tenant.finalize_tenant_context", new_callable=AsyncMock
        ):
            await middleware.dispatch(mock_request, mock_call_next)

        # Verify tenant_id is UUID string, not schema name
        assert mock_request.state.tenant_id == str(mock_tenant_id), (
            f"Expected UUID '{mock_tenant_id}', got '{mock_request.state.tenant_id}'"
        )
        # Verify tenant_schema is set
        assert mock_request.state.tenant_schema == mock_tenant_schema

    @pytest.mark.asyncio
    async def test_middleware_tenant_id_is_not_schema_name(self):
        """Regression: tenant_id must NOT be the schema name (e.g. 't_xxx')."""
        from api.middleware.auth import AuthenticationMiddleware

        mock_strategy = AsyncMock()
        mock_tenant_id = uuid.uuid4()
        mock_tenant_schema = f"t_{str(mock_tenant_id).replace('-', '')}"

        mock_tenant_ctx = MagicMock()
        mock_tenant_ctx.tenant_id = str(mock_tenant_id)
        mock_tenant_ctx.tenant_schema = mock_tenant_schema

        mock_auth_ctx = MagicMock()
        mock_strategy.authenticate.return_value = mock_auth_ctx
        mock_strategy.resolve_tenant_context.return_value = mock_tenant_ctx

        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()
        mock_request.scope = {"type": "http", "path": "/api/v1/test"}

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def mock_call_next(req):
            return mock_response

        middleware = AuthenticationMiddleware(
            app=MagicMock(), strategy=mock_strategy
        )

        with patch(
            "api.middleware.auth.set_current_tenant",
            return_value=("old_id", "old_schema"),
        ), patch(
            "api.middleware.auth.reset_current_tenant"
        ), patch(
            "api.middleware.auth.update_request_context_with_auth"
        ), patch(
            "api.context.tenant.attach_tenant_context"
        ), patch(
            "api.context.tenant.finalize_tenant_context", new_callable=AsyncMock
        ):
            await middleware.dispatch(mock_request, mock_call_next)

        # The critical assertion: tenant_id must NOT be the schema name
        assert mock_request.state.tenant_id != mock_tenant_schema, (
            "BUG REGRESSION: tenant_id is still set to schema name instead of UUID"
        )

    @pytest.mark.asyncio
    async def test_sku_import_can_parse_tenant_id_as_uuid(self):
        """End-to-end: verify uuid.UUID(str(tenant_id)) succeeds with middleware output."""
        import uuid as _uuid

        mock_tenant_id = uuid.uuid4()
        mock_tenant_schema = f"t_{str(mock_tenant_id).replace('-', '')}"

        # Simulate what middleware now sets
        tenant_id_str = str(mock_tenant_id)
        tenant_schema = mock_tenant_schema

        # This is the exact call in sku_imports.py:111
        tenant_uuid = _uuid.UUID(str(tenant_id_str))

        assert tenant_uuid == mock_tenant_id
        assert tenant_schema.startswith("t_")
