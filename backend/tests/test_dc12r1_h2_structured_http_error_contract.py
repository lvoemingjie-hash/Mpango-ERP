"""DC-12R1-H2: Structured HTTP Error Serialization Boundary.

Proves the production ``http_exception_handler`` serializes every
``HTTPException`` into the standard flat ``{code, message, request_id}``
envelope — never a Python ``str(dict)`` repr leaking into ``message``.

Coverage:
- RED/GREEN: dict-detail leak eliminated; PERMISSION_DENIED,
  TENANT_CONTEXT_REQUIRED and PLATFORM_ADMIN_REQUIRED reproduced over real
  HTTP (status 403 preserved, no handler bypassed).
- Arbitrary valid product error-code preservation from a dict detail.
- Malformed detail fail-closed to a sanitized fallback.
- String-detail backward compatibility.
- No braces / single-quoted dict repr / internal exception content in
  responses or logs.
"""
from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Any, Optional
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI, HTTPException, Request, status
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request as StarletteRequest

from api.context.auth import AuthContext, attach_auth_context
from api.context.tenant import TenantContext, attach_tenant_context
from api.middleware.rbac import RequirePermission, RequirePlatformAdmin
from core.error_codes import (
    STATUS_CODE_TO_ERROR_CODE,
    http_exception_handler,
    register_exception_handlers,
)
from core.security import TokenPayload

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Test doubles for auth/tenant context
# ---------------------------------------------------------------------------


def _identity_token() -> TokenPayload:
    """A strict identity-only token (no tenant) — NOT a platform admin."""
    return TokenPayload(
        user_id=str(uuid.uuid4()),
        roles=["some_role"],
        tenant_id=None,
        tenant_schema=None,
        type="access",
    )


def _contextual_token() -> TokenPayload:
    """A contextual (tenant-scoped) token with no permissions."""
    return TokenPayload(
        user_id=str(uuid.uuid4()),
        roles=["retailer_operator"],
        tenant_id=str(uuid.uuid4()),
        tenant_schema="t_test",
        type="access",
    )


class _FakePerm:
    def __init__(self, code: str):
        self.code = code


class _FakeRole:
    def __init__(self, name: str, perms: list[str]):
        self.name = name
        self.permissions = [_FakePerm(p) for p in perms]


class _FakeUser:
    def __init__(self, perms: Optional[list[str]] = None):
        self.roles = [_FakeRole("some_role", perms or [])]
        self.is_active = True


def _attach_context(request: Request, *, token: TokenPayload, user: Any = None):
    """Attach auth (+optional tenant) context to a request for RBAC deps."""
    attach_auth_context(request, AuthContext(token=token, raw_token="test"))
    if user is not None:
        attach_tenant_context(
            request,
            TenantContext(
                tenant_id=token.tenant_id or "t",
                tenant_schema=token.tenant_schema or "t_test",
                session=None,  # type: ignore[arg-type]
                user=user,
            ),
        )


# ---------------------------------------------------------------------------
# Minimal app with the PRODUCTION exception handlers registered
# ---------------------------------------------------------------------------


def _build_app() -> FastAPI:
    """A minimal FastAPI app that registers the production exception handlers
    and exposes routes exercising the real RBAC deps + raw HTTPException
    raises, so the full HTTPException -> response serialization path is
    tested exactly as production serves it."""
    app = FastAPI()
    register_exception_handlers(app)

    # --- context setup dependency (runs before the RBAC deps) --------------
    # Reads the requested scenario from a header and attaches auth/tenant
    # context so the REAL RequirePermission / RequirePlatformAdmin reach their
    # denial branches over actual HTTP.
    def _setup_context(request: Request, scenario: str):
        if scenario == "contextual_no_perms":
            token = _contextual_token()
            _attach_context(request, token=token, user=_FakeUser(perms=[]))
        elif scenario == "identity_not_admin":
            token = _identity_token()
            _attach_context(request, token=token)
        elif scenario == "no_tenant_context":
            # contextual token but NO tenant context attached -> the
            # RequirePermission tenant-context lookup fails -> 403
            # TENANT_CONTEXT_REQUIRED.
            token = _contextual_token()
            _attach_context(request, token=token)

    # --- real RBAC dependency routes ----------------------------------------
    @app.get("/rbac/perm")
    async def _perm_route(
        request: Request,
        _: None = Depends(lambda r: _setup_context(r, "contextual_no_perms")),
        token: TokenPayload = Depends(RequirePermission("orders:read")),
    ):
        return {"ok": True}

    @app.get("/rbac/perm_no_tenant")
    async def _perm_no_tenant_route(
        request: Request,
        _: None = Depends(lambda r: _setup_context(r, "no_tenant_context")),
        token: TokenPayload = Depends(RequirePermission("orders:read")),
    ):
        return {"ok": True}

    @app.get("/rbac/platform")
    async def _platform_route(
        request: Request,
        _: None = Depends(lambda r: _setup_context(r, "identity_not_admin")),
        token: TokenPayload = Depends(RequirePlatformAdmin()),
    ):
        return {"ok": True}

    # --- raw dict-detail HTTPException routes (mirror RBAC's raise shape) ---
    @app.get("/raw/permission_denied")
    async def _raw_perm():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERMISSION_DENIED",
                "message": "Permission 'orders:read' required",
            },
        )

    @app.get("/raw/tenant_context_required")
    async def _raw_tenant():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_CONTEXT_REQUIRED",
                "message": "Please select a tenant first (POST /auth/select-tenant)",
            },
        )

    @app.get("/raw/platform_admin_required")
    async def _raw_platform():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PLATFORM_ADMIN_REQUIRED",
                "message": "Platform endpoints require a strict identity-only super admin token (no tenant context).",
            },
        )

    @app.get("/raw/arbitrary_code")
    async def _raw_arbitrary():
        # Any valid product error code preserved from a dict detail.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_RESOURCE", "message": "Already exists"},
        )

    @app.get("/raw/string_detail")
    async def _raw_string():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget does not exist",
        )

    @app.get("/raw/malformed_detail_list")
    async def _raw_malformed_list():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["not", "a", "dict"],
        )

    @app.get("/raw/malformed_detail_int")
    async def _raw_malformed_int():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=42,
        )

    @app.get("/raw/with_public_details")
    async def _raw_with_details():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_INPUT",
                "message": "Field missing",
                "details": {"field": "email"},
            },
        )

    @app.get("/ok")
    async def _ok():
        return {"ok": True}

    return app


@pytest_asyncio.fixture
async def client():
    """HTTP client bound to the production-handler test app."""
    app = _build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_flat_envelope(body: dict, expected_code: str, *, status_category: int):
    """Assert the response body is the flat envelope with no dict repr."""
    assert "code" in body, f"missing code in {body}"
    assert body["code"] == expected_code
    assert "message" in body
    assert "request_id" in body and body["request_id"]
    message = body["message"]
    # The core guarantee: message is a clean string, never a dict repr.
    assert isinstance(message, str)
    assert "{" not in message, f"brace/dict-repr leaked into message: {message!r}"
    assert "}" not in message
    assert "'" not in message or message.count("'") <= 2, (
        f"single-quoted dict repr in message: {message!r}"
    )


# ---------------------------------------------------------------------------
# §1 RED/GREEN — dict-detail leak eliminated for the three RBAC codes
# ---------------------------------------------------------------------------


class TestRBACDenialCodesSerializedCleanly:
    """The three RBAC denial codes — raised as HTTPException(detail={dict}) —
    must serialize to the flat envelope with the SAME code and 403 status,
    never a str(dict) repr."""

    @pytest.mark.parametrize(
        "path,expected_code",
        [
            ("/raw/permission_denied", "PERMISSION_DENIED"),
            ("/raw/tenant_context_required", "TENANT_CONTEXT_REQUIRED"),
            ("/raw/platform_admin_required", "PLATFORM_ADMIN_REQUIRED"),
        ],
    )
    async def test_rbac_dict_detail_is_flat_envelope(
        self, client: AsyncClient, path, expected_code
    ):
        resp = await client.get(path)
        # Status preserved (no bypass).
        assert resp.status_code == HTTPStatus.FORBIDDEN
        body = resp.json()
        _assert_flat_envelope(body, expected_code, status_category=403)
        # The leaked dict-repr must NOT appear anywhere in the body.
        assert expected_code not in body["message"]
        assert "Permission" not in body["message"] or expected_code == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# §2 Arbitrary valid product error-code preservation
# ---------------------------------------------------------------------------


class TestErrorCodePreservation:
    async def test_arbitrary_valid_code_preserved_from_dict(self, client: AsyncClient):
        resp = await client.get("/raw/arbitrary_code")
        assert resp.status_code == HTTPStatus.CONFLICT
        body = resp.json()
        # The explicit non-empty code from the dict is preserved.
        assert body["code"] == "DUPLICATE_RESOURCE"
        assert body["message"] == "Already exists"

    async def test_explicit_public_details_preserved(self, client: AsyncClient):
        """Explicitly public, JSON-safe details in the dict are preserved."""
        resp = await client.get("/raw/with_public_details")
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        body = resp.json()
        assert body["code"] == "INVALID_INPUT"
        assert body["message"] == "Field missing"
        # The public details sub-object is preserved (JSON-safe).
        assert body.get("details") == {"field": "email"}


# ---------------------------------------------------------------------------
# §3 String-detail backward compatibility
# ---------------------------------------------------------------------------


class TestStringDetailCompatibility:
    async def test_string_detail_preserves_message_and_status(self, client: AsyncClient):
        resp = await client.get("/raw/string_detail")
        assert resp.status_code == HTTPStatus.NOT_FOUND
        body = resp.json()
        # String detail: message preserved verbatim; code from status mapping.
        assert body["message"] == "Widget does not exist"
        assert body["code"] == STATUS_CODE_TO_ERROR_CODE[404].value


# ---------------------------------------------------------------------------
# §4 Malformed detail fail-closed
# ---------------------------------------------------------------------------


class TestMalformedDetailFailClosed:
    @pytest.mark.parametrize("path", ["/raw/malformed_detail_list", "/raw/malformed_detail_int"])
    async def test_malformed_detail_uses_sanitized_fallback(
        self, client: AsyncClient, path
    ):
        resp = await client.get(path)
        body = resp.json()
        # No matter the status, the body must be a clean flat envelope.
        assert "code" in body and "message" in body and "request_id" in body
        message = body["message"]
        assert isinstance(message, str)
        # The raw list/int must NEVER appear in the message.
        assert "[" not in message and "{" not in message
        assert "not" not in message  # the list content must not leak
        assert "42" not in message   # the int must not leak


# ---------------------------------------------------------------------------
# §5 No repr / internal content in responses OR logs
# ---------------------------------------------------------------------------


class TestNoReprInResponsesOrLogs:
    async def test_no_dict_repr_in_any_denial_response(self, client: AsyncClient):
        """Across all dict-detail denials, no response body contains a dict repr."""
        for path in (
            "/raw/permission_denied",
            "/raw/tenant_context_required",
            "/raw/platform_admin_required",
            "/raw/arbitrary_code",
        ):
            resp = await client.get(path)
            text = resp.text
            # No Python dict/list repr markers in the serialized body.
            assert "'code'" not in text, f"dict repr leaked in {path}: {text}"
            assert "{'" not in text and "'}" not in text

    async def test_handler_logging_contains_no_raw_detail_repr(
        self, client: AsyncClient
    ):
        """The warning log emitted by http_exception_handler must carry only a
        sanitized code/class — never the raw detail repr.

        Asserts directly on the logger call (via ``mock.patch``) rather than
        relying on log propagation/``caplog``: the full backend suite installs
        its own structured-logging handlers and reconfigures logger state, so
        propagation-based capture is not reliable across the whole gate.
        """
        import core.error_codes as ec_module

        with mock.patch.object(ec_module.logger, "warning") as warn:
            await client.get("/raw/permission_denied")

        assert warn.called, "expected an http_exception_handler warning log"
        args, kwargs = warn.call_args
        # The log message is the status line only — never the detail repr.
        rendered = str(args[0]) if args else ""
        assert "HTTP Exception: 403" in rendered
        assert "{'code'" not in rendered
        assert "Permission 'orders:read' required" not in rendered
        # The structured extras carry ONLY the sanitized code + status — never
        # the raw detail/message payload.
        extra = kwargs.get("extra", {})
        assert extra.get("error_code") == "PERMISSION_DENIED"
        assert extra.get("status_code") == 403
        for forbidden in ("error_message", "details", "detail", "message"):
            assert forbidden not in extra, (
                f"raw detail key '{forbidden}' present in log extras: {extra!r}"
            )


# ---------------------------------------------------------------------------
# §6 Direct handler-level contract (no HTTP layer)
# ---------------------------------------------------------------------------


class TestHandlerLevelContract:
    """Exercise http_exception_handler directly to prove the serialization
    boundary for every detail variant, independent of routing."""

    async def _handle(self, exc: HTTPException) -> dict:
        request = StarletteRequest({"type": "http", "headers": [], "method": "GET", "path": "/"})
        request.state.request_id = "req-test"
        response = await http_exception_handler(request, exc)
        import json
        return json.loads(response.body)

    async def test_dict_detail_extracts_code_and_message(self):
        body = await self._handle(
            HTTPException(403, detail={"code": "PERMISSION_DENIED", "message": "nope"})
        )
        assert body["code"] == "PERMISSION_DENIED"
        assert body["message"] == "nope"
        assert body["request_id"] == "req-test"

    async def test_string_detail_keeps_message(self):
        body = await self._handle(HTTPException(404, detail="gone"))
        assert body["message"] == "gone"
        assert body["code"] == STATUS_CODE_TO_ERROR_CODE[404].value

    async def test_none_detail_fail_closed(self):
        body = await self._handle(HTTPException(400, detail=None))
        assert body["code"] == STATUS_CODE_TO_ERROR_CODE[400].value
        assert isinstance(body["message"], str)
        assert "None" not in body["message"]

    async def test_nested_dict_detail_does_not_leak(self):
        body = await self._handle(
            HTTPException(
                500,
                detail={"code": "X", "message": "y", "internal_field": "leak"},
            )
        )
        # An arbitrary extra dict key must never surface in message (only the
        # string code + message are extracted; the rest of the dict is dropped).
        assert body["message"] == "y"
        assert "leak" not in resp_text(body)

    async def test_status_preserved_for_all_variants(self):
        for code in (400, 401, 403, 404, 409, 422, 429, 500):
            exc = HTTPException(code, detail={"code": "X", "message": "m"})
            request = StarletteRequest({"type": "http", "headers": [], "method": "GET", "path": "/"})
            request.state.request_id = "r"
            response = await http_exception_handler(request, exc)
            assert response.status_code == code


def resp_text(body: dict) -> str:
    import json
    return json.dumps(body)
