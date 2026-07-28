"""DC-12R1-H2 (R1): Structured HTTP Error Serialization Boundary.

Proves the production ``http_exception_handler`` serializes every
``HTTPException`` into the standard flat ``{code, message, request_id}``
envelope. The handler **never creates a repr by stringifying a non-string
detail**: dict/list/int/None/object details are normalized, never rendered
with ``str()`` into the public ``message`` field.

Two distinct evidence families are covered (kept separate per DC-12R1-H2-R1):

1. **Real RBAC dependency evidence** — the REAL ``RequirePermission`` /
   ``RequirePlatformAdmin`` dependencies are executed over actual HTTP on
   ``/rbac/perm``, ``/rbac/perm_no_tenant`` and ``/rbac/platform`` (context is
   attached by a deterministic test *middleware* that runs before the deps),
   asserting exact ``403`` + ``PERMISSION_DENIED`` /
   ``TENANT_CONTEXT_REQUIRED`` / ``PLATFORM_ADMIN_REQUIRED``, no permission
   bypass, and no dict repr in response or logs.
2. **Raw-shape (detail-normalization) evidence** — exercises the handler with
   hand-crafted ``HTTPException(detail=...)`` shapes that mirror the RBAC
   raises, plus the R1 JSON-safety / code-validation contract.

R1 additions: NaN / +/-Infinity rejection; non-string top-level AND nested
keys rejection; bytes/set/tuple/arbitrary-object rejection; unsafe details
omitted with NO 500 (status/code/message/request_id preserved); valid nested
JSON details preserved; invalid/oversized code falls back to the
status-derived code; ordinary string-detail compatibility.
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
    """A minimal FastAPI app that registers the production exception handlers.

    A deterministic test *middleware* attaches auth/tenant context based on the
    requested path so the REAL ``RequirePermission`` / ``RequirePlatformAdmin``
    dependencies reach their denial branches over actual HTTP. The same app
    also exposes raw ``HTTPException(detail=...)`` routes that mirror the RBAC
    raise shapes and the R1 JSON-safety / code-validation cases, so the full
    ``HTTPException -> response`` serialization path is tested exactly as
    production serves it.
    """
    app = FastAPI()
    register_exception_handlers(app)

    # --- context-attach test middleware -------------------------------------
    # Runs for every request BEFORE route dependencies resolve, attaching the
    # auth (+tenant) context deterministically per route. This lets the REAL
    # RBAC deps execute against controlled identities.
    @app.middleware("http")
    async def _attach_test_context(request: Request, call_next):
        path = request.url.path
        if path == "/rbac/perm":
            # Contextual token, tenant context attached, but the user holds no
            # permissions -> RequirePermission("orders:read") denies.
            _attach_context(request, token=_contextual_token(), user=_FakeUser(perms=[]))
        elif path == "/rbac/perm_no_tenant":
            # Contextual token but NO tenant context attached ->
            # RequirePermission's tenant-context lookup fails -> 403
            # TENANT_CONTEXT_REQUIRED.
            _attach_context(request, token=_contextual_token())
        elif path == "/rbac/platform":
            # Identity-only token, not a super admin ->
            # RequirePlatformAdmin denies -> 403 PLATFORM_ADMIN_REQUIRED.
            _attach_context(request, token=_identity_token())
        return await call_next(request)

    # --- real RBAC dependency routes ----------------------------------------
    @app.get("/rbac/perm")
    async def _perm_route(token: TokenPayload = Depends(RequirePermission("orders:read"))):
        return {"ok": True}

    @app.get("/rbac/perm_no_tenant")
    async def _perm_no_tenant_route(
        token: TokenPayload = Depends(RequirePermission("orders:read")),
    ):
        return {"ok": True}

    @app.get("/rbac/platform")
    async def _platform_route(token: TokenPayload = Depends(RequirePlatformAdmin())):
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


def _assert_flat_envelope(body: dict, expected_code: str):
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


def _assert_no_repr_anywhere(text: str):
    """No Python dict/list repr markers anywhere in a serialized body."""
    assert "'code'" not in text, f"dict repr leaked: {text}"
    assert "{'" not in text and "'}" not in text
    assert "['" not in text


# ===========================================================================
# §1 REAL RBAC DEPENDENCY EVIDENCE (actual deps over actual HTTP)
# ===========================================================================


class TestRealRBACDependencies:
    """Executes the REAL RequirePermission / RequirePlatformAdmin deps over
    actual HTTP (context attached by a deterministic test middleware) and
    asserts the exact 403 + denial code, no permission bypass, and no dict
    repr in response or logs."""

    async def test_permission_denied_via_real_require_permission(
        self, client: AsyncClient
    ):
        resp = await client.get("/rbac/perm")
        assert resp.status_code == HTTPStatus.FORBIDDEN
        body = resp.json()
        _assert_flat_envelope(body, "PERMISSION_DENIED")
        assert body["message"] == "Permission 'orders:read' required"
        _assert_no_repr_anywhere(resp.text)

    async def test_tenant_context_required_via_real_require_permission(
        self, client: AsyncClient
    ):
        resp = await client.get("/rbac/perm_no_tenant")
        assert resp.status_code == HTTPStatus.FORBIDDEN
        body = resp.json()
        _assert_flat_envelope(body, "TENANT_CONTEXT_REQUIRED")
        assert body["message"] == "Please select a tenant first (POST /auth/select-tenant)"
        _assert_no_repr_anywhere(resp.text)

    async def test_platform_admin_required_via_real_require_platform_admin(
        self, client: AsyncClient
    ):
        resp = await client.get("/rbac/platform")
        assert resp.status_code == HTTPStatus.FORBIDDEN
        body = resp.json()
        _assert_flat_envelope(body, "PLATFORM_ADMIN_REQUIRED")
        assert body["message"].startswith("Platform endpoints require")
        _assert_no_repr_anywhere(resp.text)

    async def test_no_permission_bypass_real_rbac_routes(self, client: AsyncClient):
        """None of the protected RBAC routes ever returns 200 — i.e. the real
        deps are never bypassed and always deny for the attached identities."""
        for path in ("/rbac/perm", "/rbac/perm_no_tenant", "/rbac/platform"):
            resp = await client.get(path)
            assert resp.status_code == HTTPStatus.FORBIDDEN, (
                f"{path} was bypassed (got {resp.status_code})"
            )

    async def test_real_rbac_logging_has_no_raw_detail_repr(
        self, client: AsyncClient
    ):
        import core.error_codes as ec_module

        with mock.patch.object(ec_module.logger, "warning") as warn:
            await client.get("/rbac/perm")

        assert warn.called
        args, kwargs = warn.call_args
        rendered = str(args[0]) if args else ""
        assert "HTTP Exception: 403" in rendered
        assert "{'code'" not in rendered
        assert "Permission 'orders:read' required" not in rendered
        extra = kwargs.get("extra", {})
        assert extra.get("error_code") == "PERMISSION_DENIED"
        assert extra.get("status_code") == 403
        for forbidden in ("error_message", "details", "detail", "message"):
            assert forbidden not in extra


# ===========================================================================
# §2 RAW-SHAPE EVIDENCE (handler detail-normalization, mirroring RBAC raises)
# ===========================================================================


class TestRawShapeDenialCodes:
    """The three RBAC denial shapes — raised as raw
    ``HTTPException(detail={dict})`` — serialize to the flat envelope with the
    SAME code and 403 status, never a str(dict) repr."""

    @pytest.mark.parametrize(
        "path,expected_code",
        [
            ("/raw/permission_denied", "PERMISSION_DENIED"),
            ("/raw/tenant_context_required", "TENANT_CONTEXT_REQUIRED"),
            ("/raw/platform_admin_required", "PLATFORM_ADMIN_REQUIRED"),
        ],
    )
    async def test_raw_dict_detail_is_flat_envelope(
        self, client: AsyncClient, path, expected_code
    ):
        resp = await client.get(path)
        # Status preserved (no bypass).
        assert resp.status_code == HTTPStatus.FORBIDDEN
        body = resp.json()
        _assert_flat_envelope(body, expected_code)
        _assert_no_repr_anywhere(resp.text)


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


class TestStringDetailCompatibility:
    async def test_string_detail_preserves_message_and_status(self, client: AsyncClient):
        resp = await client.get("/raw/string_detail")
        assert resp.status_code == HTTPStatus.NOT_FOUND
        body = resp.json()
        # String detail: message preserved verbatim; code from status mapping.
        assert body["message"] == "Widget does not exist"
        assert body["code"] == STATUS_CODE_TO_ERROR_CODE[404].value


class TestMalformedDetailFailClosed:
    @pytest.mark.parametrize(
        "path", ["/raw/malformed_detail_list", "/raw/malformed_detail_int"]
    )
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
        assert "42" not in message  # the int must not leak


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
            _assert_no_repr_anywhere(resp.text)


# ===========================================================================
# §3 R1 — public details JSON-safety fail-closed (handler-level contract)
# ===========================================================================


class _HandlerProbe:
    """Drive http_exception_handler directly to test detail normalization
    independent of routing."""

    async def handle(self, exc: HTTPException, *, request_id: str = "req-test") -> tuple[int, dict]:
        import json

        request = StarletteRequest(
            {"type": "http", "headers": [], "method": "GET", "path": "/"}
        )
        request.state.request_id = request_id
        response = await http_exception_handler(request, exc)
        return response.status_code, json.loads(response.body)


class TestPublicDetailsJsonSafety(_HandlerProbe):
    """R1: public ``details`` must be GENUINELY JSON-safe — recursive string
    keys, only None/bool/int/str/finite-float; reject NaN/+Inf/-Inf,
    bytes/set/tuple/objects. Unsafe details are OMITTED (no 500) while status,
    sanitized code/message and request_id survive."""

    async def test_nan_details_omitted_no_500(self):
        sc, body = await self.handle(
            HTTPException(
                422,
                detail={"code": "INVALID_INPUT", "message": "bad", "details": {"ratio": float("nan")}},
            )
        )
        assert sc == 422  # no 500
        assert body["code"] == "INVALID_INPUT"
        assert body["message"] == "bad"
        assert body["request_id"] == "req-test"
        assert "details" not in body, "NaN details must be omitted"

    async def test_infinity_details_omitted_no_500(self):
        for bad in (float("inf"), float("-inf")):
            sc, body = await self.handle(
                HTTPException(
                    422,
                    detail={"code": "INVALID_INPUT", "message": "bad", "details": {"v": bad}},
                )
            )
            assert sc == 422
            assert "details" not in body, f"+/-Infinity details must be omitted: {bad}"

    async def test_non_string_top_level_key_details_omitted(self):
        sc, body = await self.handle(
            HTTPException(
                422,
                detail={"code": "INVALID_INPUT", "message": "bad", "details": {1: "x"}},
            )
        )
        assert sc == 422
        assert body["code"] == "INVALID_INPUT"
        assert "details" not in body, "non-string top-level key must be omitted"

    async def test_non_string_nested_key_details_omitted(self):
        sc, body = await self.handle(
            HTTPException(
                422,
                detail={
                    "code": "INVALID_INPUT",
                    "message": "bad",
                    "details": {"outer": {1: "nested-key-not-string"}},
                },
            )
        )
        assert sc == 422
        assert "details" not in body, "non-string nested key must be omitted"

    @pytest.mark.parametrize(
        "bad_value,label",
        [
            (b"secret-bytes", "bytes"),
            (bytearray(b"x"), "bytearray"),
            ({1, 2, 3}, "set"),
            (frozenset({1, 2}), "frozenset"),
            ((1, 2), "tuple"),
        ],
    )
    async def test_unsupported_container_types_omitted(self, bad_value, label):
        sc, body = await self.handle(
            HTTPException(
                422,
                detail={"code": "INVALID_INPUT", "message": "bad", "details": {"v": bad_value}},
            )
        )
        assert sc == 422, f"{label}: handler must not 500"
        assert body["code"] == "INVALID_INPUT"
        assert "details" not in body, f"{label} details must be omitted"
        # The unsafe value's repr must never appear in the response body.
        import json

        assert label not in json.dumps(body)

    async def test_arbitrary_object_details_omitted(self):
        class _Arbitrary:
            pass

        sc, body = await self.handle(
            HTTPException(
                422,
                detail={"code": "INVALID_INPUT", "message": "bad", "details": {"v": _Arbitrary()}},
            )
        )
        assert sc == 422
        assert "details" not in body

    async def test_valid_nested_json_details_preserved(self):
        sc, body = await self.handle(
            HTTPException(
                422,
                detail={
                    "code": "INVALID_INPUT",
                    "message": "ok",
                    "details": {
                        "a": {"b": [1, 2.5, None, True, "x"]},
                        "c": 3,
                    },
                },
            )
        )
        assert sc == 422
        assert body["details"] == {"a": {"b": [1, 2.5, None, True, "x"]}, "c": 3}


class TestPublicCodeStrictness(_HandlerProbe):
    """R1: public codes must match ``^[A-Z][A-Z0-9_]{0,63}$``. Malformed /
    oversized codes fall back to the status-derived code (message preserved)."""

    @pytest.mark.parametrize(
        "bad_code,label",
        [
            ("lower_case", "lowercase"),
            ("HAS SPACE", "space"),
            ("DASH-CODE", "dash"),
            ("1STARTS_DIGIT", "leading digit"),
            ("code'with'quote", "quote"),
            ("A" * 65, "oversized (65 chars)"),
        ],
    )
    async def test_invalid_code_falls_back_to_status_code(self, bad_code, label):
        sc, body = await self.handle(
            HTTPException(
                403,
                detail={"code": bad_code, "message": "denied"},
            )
        )
        assert sc == 403
        # Falls back to the status-derived code for 403.
        assert body["code"] == STATUS_CODE_TO_ERROR_CODE[403].value, (
            f"{label} code should fall back to status-derived code"
        )
        # The malformed/oversized code never appears in the response.
        assert bad_code not in json_dumps(body)
        assert body["message"] == "denied"

    async def test_max_length_valid_code_preserved(self):
        # Exactly 64 chars is valid (^[A-Z][A-Z0-9_]{0,63}$).
        valid = "A" + "B" * 63
        sc, body = await self.handle(
            HTTPException(409, detail={"code": valid, "message": "ok"})
        )
        assert sc == 409
        assert body["code"] == valid


class TestHandlerNeverRaises(_HandlerProbe):
    """R1: the exception handler itself must NEVER raise, even on pathological
    detail inputs — it fail-closes to the standard envelope."""

    @pytest.mark.parametrize(
        "detail",
        [
            ["a", "list"],
            42,
            None,
            {"only_message_no_code": "x"},
            {"code": "BAD CODE!", "message": "x"},
            {"code": "OK", "details": {1: 2}},
            object(),
        ],
    )
    async def test_handler_returns_envelope_never_raises(self, detail):
        sc, body = await self.handle(HTTPException(403, detail=detail))
        # Always a flat envelope, original status preserved.
        assert sc == 403
        assert "code" in body and isinstance(body["message"], str)
        assert body["request_id"] == "req-test"


class TestStringDetailCompatibilityDirect(_HandlerProbe):
    async def test_string_detail_keeps_message(self):
        sc, body = await self.handle(HTTPException(404, detail="gone"))
        assert sc == 404
        assert body["message"] == "gone"
        assert body["code"] == STATUS_CODE_TO_ERROR_CODE[404].value

    async def test_dict_detail_extracts_code_and_message(self):
        sc, body = await self.handle(
            HTTPException(403, detail={"code": "PERMISSION_DENIED", "message": "nope"})
        )
        assert sc == 403
        assert body["code"] == "PERMISSION_DENIED"
        assert body["message"] == "nope"

    async def test_none_detail_fail_closed(self):
        sc, body = await self.handle(HTTPException(400, detail=None))
        assert sc == 400
        assert body["code"] == STATUS_CODE_TO_ERROR_CODE[400].value
        assert isinstance(body["message"], str)
        assert "None" not in body["message"]

    async def test_nested_dict_detail_extra_keys_do_not_leak(self):
        sc, body = await self.handle(
            HTTPException(
                500,
                detail={"code": "X", "message": "y", "internal_field": "leak"},
            )
        )
        # An arbitrary extra dict key must never surface (only string code +
        # message are extracted; the rest of the dict is dropped).
        assert sc == 500
        assert body["message"] == "y"
        assert "leak" not in json_dumps(body)

    async def test_status_preserved_for_all_variants(self):
        for code in (400, 401, 403, 404, 409, 422, 429, 500):
            sc, body = await self.handle(
                HTTPException(code, detail={"code": "X", "message": "m"})
            )
            assert sc == code


def json_dumps(body: dict) -> str:
    import json

    return json.dumps(body)
