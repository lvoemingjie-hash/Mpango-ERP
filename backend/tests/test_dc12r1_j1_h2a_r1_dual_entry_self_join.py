"""DC-12R1-MVP-L1-J1-H2-A-R1: dual-entry retailer self-join (backend contract).

Covers the Phase 0 contracts end-to-end against a real PostgreSQL:
  - public supplier-code lookup returns ONLY a safe preview + signed
    short-lived join intent; unknown codes are uniformly neutral;
  - join intents are signature-verified, tamper/expiry fail closed;
  - registration accepts EXACTLY ONE of invitation_code / join_intent,
    never a client wholesaler_id, and requires email;
  - self-join binds to the SIGNED wholesaler only, idempotently;
  - the wholesaler can deactivate the relationship post-hoc
    (tenant-scoped neutral 404 cross-tenant);
  - the CRM list derives join_source (invite/code) from the used-invitation
    linkage.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.join_intent import (
    JOIN_INTENT_TTL_SECONDS,
    JoinIntentError,
    issue_join_intent,
    verify_join_intent,
)
from core.security import TokenPayload
from db.tenant_filter import run_as_system
from repositories.invitation_repository import InvitationRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _no_endpoint_rate_limit(monkeypatch):
    """Contract tests must not trip the endpoint-scoped buckets (all test
    clients share one IP bucket; a dedicated test below verifies the
    endpoint's rate-limit WIRING deterministically)."""

    class _NoLimit:
        async def check_endpoint_rate_limit(self, request, *, namespace, limit):
            return True, 0, limit

    import core.rate_limiter as rl

    monkeypatch.setattr(rl, "get_rate_limiter", lambda: _NoLimit())


def _run_phone() -> str:
    return f"+2557{uuid.uuid4().hex[:8].upper()}"


def _code(prefix: str = "R1WS") -> str:
    return f"{prefix}{uuid.uuid4().hex[:6].upper()}"


# ---------------------------------------------------------------------------
# Table bootstrap (same minimal public+RBAC pattern as the H2-A tests)
# ---------------------------------------------------------------------------

async def _prepare(async_session: AsyncSession) -> None:
    await async_session.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    for ddl in (
        """CREATE TABLE IF NOT EXISTS public.wholesalers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code VARCHAR(32) NOT NULL UNIQUE, name VARCHAR(255) NOT NULL,
            address TEXT, contact TEXT, plan_type VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT false, deleted_at TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            provisioned_at TIMESTAMPTZ, suspended_at TIMESTAMPTZ, suspension_reason TEXT)""",
        """CREATE TABLE IF NOT EXISTS public.retailers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            phone VARCHAR(32) NOT NULL UNIQUE, name VARCHAR(255),
            email VARCHAR(255), address TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT false, deleted_at TIMESTAMPTZ)""",
        """CREATE TABLE IF NOT EXISTS public.invitations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            wholesaler_id UUID NOT NULL REFERENCES public.wholesalers(id),
            retailer_phone VARCHAR(32), expires_at TIMESTAMPTZ,
            used_at TIMESTAMPTZ, used_retailer_id UUID REFERENCES public.retailers(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT false, deleted_at TIMESTAMPTZ)""",
        """CREATE TABLE IF NOT EXISTS public.wholesaler_retailer_bindings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wholesaler_id UUID NOT NULL REFERENCES public.wholesalers(id),
            retailer_id UUID NOT NULL REFERENCES public.retailers(id),
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            outstanding_balance NUMERIC(12,2) NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT false, deleted_at TIMESTAMPTZ,
            tenant_user_id UUID,
            CONSTRAINT uq_wholesaler_retailer UNIQUE (wholesaler_id, retailer_id))""",
        """CREATE TABLE IF NOT EXISTS public.retailer_credential_setup_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            retailer_id UUID NOT NULL REFERENCES public.retailers(id),
            binding_id UUID REFERENCES public.wholesaler_retailer_bindings(id),
            issued_by_wholesaler_id UUID REFERENCES public.wholesalers(id),
            token_hash VARCHAR(255) NOT NULL,
            purpose VARCHAR(50) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT false, deleted_at TIMESTAMPTZ)""",
    ):
        await async_session.execute(text(ddl))


async def _seed_wholesaler_with_rbac(
    db: AsyncSession,
    *,
    wholesaler_id: uuid.UUID,
    code: str,
    contact: str | None = None,
    status: str = "active",
) -> None:
    await db.execute(
        text(
            "INSERT INTO public.wholesalers (id, code, name, address, contact, status, is_deleted) "
            "VALUES (:id, :code, :name, '12 Supplier Avenue' || chr(10) || 'Kampala', :contact, :status, false) "
            "ON CONFLICT (id) DO UPDATE SET code = EXCLUDED.code, name = EXCLUDED.name, status = EXCLUDED.status"
        ),
        {"id": wholesaler_id, "code": code, "name": f"Tenant {code}", "contact": contact, "status": status},
    )
    tenant_schema = f"t_{str(wholesaler_id).replace('-', '')}"
    with run_as_system(reason="r1_tenant_rbac_seed"):
        await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"'))
        for stmt in (
            f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".users ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), email VARCHAR(255) NOT NULL UNIQUE, "
            "password_hash VARCHAR(255) NOT NULL, full_name TEXT, is_active BOOLEAN NOT NULL DEFAULT true, "
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
            f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".roles ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name VARCHAR(100) NOT NULL UNIQUE, "
            "description TEXT, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
            f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".permissions ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), code VARCHAR(100) NOT NULL UNIQUE, "
            "description TEXT, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, created_by UUID, updated_by UUID)",
            f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".user_roles ('
            f'user_id UUID NOT NULL REFERENCES "{tenant_schema}".users(id) ON DELETE CASCADE, '
            f'role_id UUID NOT NULL REFERENCES "{tenant_schema}".roles(id) ON DELETE CASCADE, '
            "PRIMARY KEY (user_id, role_id))",
            f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".role_permissions ('
            f'role_id UUID NOT NULL REFERENCES "{tenant_schema}".roles(id) ON DELETE CASCADE, '
            f'permission_id UUID NOT NULL REFERENCES "{tenant_schema}".permissions(id) ON DELETE CASCADE, '
            "PRIMARY KEY (role_id, permission_id))",
            f'INSERT INTO "{tenant_schema}".roles (name, description) '
            "VALUES ('retailer_operator', 'Retailer MVP') ON CONFLICT (name) DO NOTHING",
        ):
            await db.execute(text(stmt))
    await db.flush()


def _client_for(db: AsyncSession, router_factory, prefix: str = "/api/v1"):
    from fastapi import FastAPI

    from api.dependencies import get_db_session

    app = FastAPI()

    async def _override():
        yield db

    router = router_factory()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_db_session] = _override

    from core.error_codes import MpangoAPIException, mpango_exception_handler

    app.exception_handler(MpangoAPIException)(mpango_exception_handler)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


# ---------------------------------------------------------------------------
# join_intent primitive contracts (P0-3)
# ---------------------------------------------------------------------------

class TestJoinIntentPrimitives:
    def test_roundtrip_and_binding(self):
        ws = uuid.uuid4()
        intent, expires_at = issue_join_intent(wholesaler_id=ws, wholesaler_code="R1WS99")
        payload = verify_join_intent(intent)
        assert payload.wholesaler_id == ws
        assert payload.wholesaler_code == "R1WS99"
        assert expires_at > datetime.now(timezone.utc)

    def test_tampered_signature_rejected(self):
        ws = uuid.uuid4()
        intent, _ = issue_join_intent(wholesaler_id=ws, wholesaler_code="R1WS99")
        base, sig = intent.split(".", 1)
        flipped = ("A" if not sig.startswith("A") else "B") + sig[1:]
        with pytest.raises(JoinIntentError):
            verify_join_intent(f"{base}.{flipped}")

    def test_tampered_payload_rejected(self):
        ws = uuid.uuid4()
        intent, _ = issue_join_intent(wholesaler_id=ws, wholesaler_code="R1WS99")
        base, sig = intent.split(".", 1)
        # Swap the payload for one naming a different wholesaler.
        import base64 as _b64
        import json as _json

        forged = {
            "v": 1, "ws": str(uuid.uuid4()), "code": "EVIL99",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "jti": "forged",
        }
        forged_b64 = _b64.urlsafe_b64encode(
            _json.dumps(forged, separators=(",", ":"), sort_keys=True).encode()
        ).rstrip(b"=").decode("ascii")
        with pytest.raises(JoinIntentError):
            verify_join_intent(f"{forged_b64}.{sig}")

    def test_expired_intent_rejected(self):
        ws = uuid.uuid4()
        intent, _ = issue_join_intent(
            wholesaler_id=ws,
            wholesaler_code="R1WS99",
            ttl_seconds=1,
            now=datetime.now(timezone.utc) - timedelta(seconds=JOIN_INTENT_TTL_SECONDS),
        )
        with pytest.raises(JoinIntentError):
            verify_join_intent(intent)

    def test_malformed_intent_rejected(self):
        for bad in ("", "not-an-intent", "a.b.c", "...."):
            with pytest.raises(JoinIntentError):
                verify_join_intent(bad)


# ---------------------------------------------------------------------------
# lookup-code safe preview (P0-2)
# ---------------------------------------------------------------------------

async def test_lookup_code_returns_safe_preview_and_intent(async_session):
    await _prepare(async_session)
    ws = uuid.uuid4()
    code = _code()
    await _seed_wholesaler_with_rbac(
        async_session, wholesaler_id=ws, code=code, contact="+256700123456"
    )

    from api.v1.public_join import router as wholesalers_router

    async with _client_for(async_session, lambda: wholesalers_router, prefix="/api/v1") as client:
        resp = await client.post("/api/v1/wholesalers/lookup-code", json={"code": code.lower()})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["found"] is True
    assert data["name"] == f"Tenant {code}"
    assert data["region"] == "12 Supplier Avenue"
    # Masked contact never reveals the full number.
    assert "+256700123456" not in (data["contact_masked"] or "")
    assert data["contact_masked"] and "*" in data["contact_masked"]
    assert data["join_intent"]
    payload = verify_join_intent(data["join_intent"])
    assert payload.wholesaler_id == ws
    assert payload.wholesaler_code == code
    # No internal identifiers leaked.
    assert "id" not in data
    assert str(ws) not in resp.text


async def test_lookup_code_unknown_is_uniformly_neutral(async_session):
    await _prepare(async_session)
    from api.v1.public_join import router as wholesalers_router

    async with _client_for(async_session, lambda: wholesalers_router, prefix="/api/v1") as client:
        miss = await client.post(
            "/api/v1/wholesalers/lookup-code", json={"code": _code("MISS")}
        )
        malformed = await client.post(
            "/api/v1/wholesalers/lookup-code", json={"code": "bad-code!"}
        )
    assert miss.status_code == 200 and malformed.status_code == 200
    for resp in (miss, malformed):
        data = resp.json()["data"]
        assert data["found"] is False
        assert data["name"] is None and data["region"] is None
        assert data["contact_masked"] is None and data["join_intent"] is None


# ---------------------------------------------------------------------------
# dual-entry register (P0-4/P0-5)
# ---------------------------------------------------------------------------

async def test_register_via_join_intent_binds_to_signed_wholesaler(async_session):
    await _prepare(async_session)
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
    code_a = _code()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws_a, code=code_a)
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws_b, code=_code())
    # (re-seed A with a known code for a precise assertion)
    intent, _ = issue_join_intent(wholesaler_id=ws_a, wholesaler_code=code_a)
    phone = _run_phone()
    email = f"r1-{uuid.uuid4().hex[:6]}@example.com"

    from api.v1.retailers import router as retailers_router

    async with _client_for(async_session, lambda: retailers_router) as client:
        resp = await client.post(
            "/api/v1/retailers/register",
            json={"join_intent": intent, "phone": phone, "email": email},
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["wholesaler_code"] == code_a  # server-verified portal code
    assert data["binding"]["wholesaler_id"] == str(ws_a)

    # Exactly one binding, to the SIGNED wholesaler; none to B (T13).
    rows = await async_session.execute(
        text(
            "SELECT wholesaler_id FROM public.wholesaler_retailer_bindings "
            "WHERE retailer_id = (SELECT id FROM public.retailers WHERE phone = :p)"
        ),
        {"p": phone},
    )
    bound = [r[0] for r in rows.fetchall()]
    assert bound == [ws_a]


async def test_register_email_required_backend_red(async_session):
    """T6 backend RED: the real backend rejects a no-email registration."""
    await _prepare(async_session)
    ws = uuid.uuid4()
    code = _code()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws, code=code)
    intent, _ = issue_join_intent(wholesaler_id=ws, wholesaler_code=code)
    rejected_phone = _run_phone()

    from api.v1.retailers import router as retailers_router

    async with _client_for(async_session, lambda: retailers_router) as client:
        resp = await client.post(
            "/api/v1/retailers/register",
            json={"join_intent": intent, "phone": rejected_phone, "email": None},
        )
    assert resp.status_code == 422
    # Fail closed: the rejected submission's phone never reached persistence.
    count = await async_session.execute(
        text("SELECT COUNT(*) FROM public.retailers WHERE phone = :p"),
        {"p": rejected_phone},
    )
    assert count.scalar_one() == 0


async def test_register_both_or_neither_credential_rejected(async_session):
    """T5: invitation_code and join_intent are strictly either-or."""
    await _prepare(async_session)
    ws = uuid.uuid4()
    code = _code()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws, code=code)
    intent, _ = issue_join_intent(wholesaler_id=ws, wholesaler_code=code)
    email = f"r1-{uuid.uuid4().hex[:6]}@example.com"

    from api.v1.retailers import router as retailers_router

    async with _client_for(async_session, lambda: retailers_router) as client:
        both = await client.post(
            "/api/v1/retailers/register",
            json={
                "join_intent": intent,
                "invitation_code": "SOMECODE",
                "phone": _run_phone(),
                "email": email,
            },
        )
        neither = await client.post(
            "/api/v1/retailers/register",
            json={"phone": _run_phone(), "email": email},
        )
        # A client-submitted wholesaler_id must be ignored outright: the
        # schema has no such field, and extra keys never reach the service.
        ghost = await client.post(
            "/api/v1/retailers/register",
            json={
                "join_intent": intent,
                "wholesaler_id": str(uuid.uuid4()),
                "phone": _run_phone(),
                "email": f"r1-{uuid.uuid4().hex[:6]}@example.com",
            },
        )
    assert both.status_code == 422
    assert neither.status_code == 422
    assert ghost.status_code == 201
    assert ghost.json()["data"]["wholesaler_code"] == code


async def test_register_tampered_intent_binds_nothing(async_session):
    """T4 backend: a tampered join_intent never binds."""
    await _prepare(async_session)
    ws = uuid.uuid4()
    code = _code()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws, code=code)
    intent, _ = issue_join_intent(wholesaler_id=ws, wholesaler_code=code)
    base, sig = intent.split(".", 1)
    tampered = f"{base}.{('A' if not sig.startswith('A') else 'B') + sig[1:]}"

    from api.v1.retailers import router as retailers_router

    async with _client_for(async_session, lambda: retailers_router) as client:
        resp = await client.post(
            "/api/v1/retailers/register",
            json={
                "join_intent": tampered,
                "phone": _run_phone(),
                "email": f"r1-{uuid.uuid4().hex[:6]}@example.com",
            },
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "JOIN_INTENT_INVALID"
    # Fail closed: the tampered submission's retailer was never created.
    import json as _json

    sent_phone = _json.loads(resp.request.read().decode("utf-8"))["phone"]
    count = await async_session.execute(
        text("SELECT COUNT(*) FROM public.retailers WHERE phone = :p"),
        {"p": sent_phone},
    )
    assert count.scalar_one() == 0


async def test_self_join_is_idempotent(async_session):
    """T7 backend: resubmission returns the SAME relationship."""
    await _prepare(async_session)
    ws = uuid.uuid4()
    code = _code()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws, code=code)
    intent, _ = issue_join_intent(wholesaler_id=ws, wholesaler_code=code)
    phone = _run_phone()
    email = f"r1-{uuid.uuid4().hex[:6]}@example.com"

    from api.v1.retailers import router as retailers_router

    async with _client_for(async_session, lambda: retailers_router) as client:
        first = await client.post(
            "/api/v1/retailers/register",
            json={"join_intent": intent, "phone": phone, "email": email},
        )
        await async_session.commit()
        # Fresh intent for the same wholesaler (the first is still valid).
        intent2, _ = issue_join_intent(wholesaler_id=ws, wholesaler_code=code)
        second = await client.post(
            "/api/v1/retailers/register",
            json={"join_intent": intent2, "phone": phone, "email": email},
        )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["data"]["binding"]["id"] == second.json()["data"]["binding"]["id"]

    count = await async_session.execute(
        text(
            "SELECT COUNT(*) FROM public.wholesaler_retailer_bindings b "
            "JOIN public.retailers r ON r.id = b.retailer_id WHERE r.phone = :p"
        ),
        {"p": phone},
    )
    assert count.scalar_one() == 1


# ---------------------------------------------------------------------------
# post-hoc deactivation + join source (P0-5)
# ---------------------------------------------------------------------------

async def _join_by_code(async_session, *, ws: uuid.UUID, code: str) -> str:
    from api.v1.retailers import router as retailers_router

    intent, _ = issue_join_intent(wholesaler_id=ws, wholesaler_code=code)
    async with _client_for(async_session, lambda: retailers_router) as client:
        resp = await client.post(
            "/api/v1/retailers/register",
            json={
                "join_intent": intent,
                "phone": _run_phone(),
                "email": f"r1-{uuid.uuid4().hex[:6]}@example.com",
            },
        )
    assert resp.status_code == 201, resp.text
    await async_session.commit()
    return resp.json()["data"]["retailer"]["id"]


async def test_deactivate_is_tenant_scoped_and_idempotent(async_session):
    await _prepare(async_session)
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
    code_a = _code()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws_a, code=code_a)
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws_b, code=_code())
    retailer_id = await _join_by_code(async_session, ws=ws_a, code=code_a)

    from api.v1.retailers import deactivate_retailer_binding

    token_a = TokenPayload(user_id=str(uuid.uuid4()), tenant_id=str(ws_a), roles=["admin"])
    token_b = TokenPayload(user_id=str(uuid.uuid4()), tenant_id=str(ws_b), roles=["admin"])

    # Cross-tenant deactivation is a neutral 404 (T13).
    with pytest.raises(Exception) as exc_b:
        await deactivate_retailer_binding(retailer_id, token=token_b, db=async_session)
    assert getattr(exc_b.value, "status_code", None) == 404

    first = await deactivate_retailer_binding(retailer_id, token=token_a, db=async_session)
    assert first.data.status == "inactive"
    second = await deactivate_retailer_binding(retailer_id, token=token_a, db=async_session)
    assert second.data.status == "inactive"

    row = await async_session.execute(
        text("SELECT status FROM public.wholesaler_retailer_bindings WHERE retailer_id = :r"),
        {"r": retailer_id},
    )
    assert row.scalar_one() == "inactive"


async def test_list_derives_join_source(async_session):
    await _prepare(async_session)
    ws = uuid.uuid4()
    code_a = _code()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws, code=code_a)

    # Entry B: code self-join -> source 'code'.
    retailer_code_id = await _join_by_code(async_session, ws=ws, code=code_a)

    # Entry A: invitation acceptance -> source 'invite'.
    phone = _run_phone()
    invite_code = f"R1INV{uuid.uuid4().hex[:10].upper()}"
    with run_as_system(reason="r1_invitation_seed"):
        await InvitationRepository().create(
            async_session,
            code=invite_code,
            wholesaler_id=ws,
            retailer_phone=phone,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
    from api.v1.retailers import list_retailers
    from api.v1.retailers import router as retailers_router

    async with _client_for(async_session, lambda: retailers_router) as client:
        resp = await client.post(
            "/api/v1/retailers/register",
            json={
                "invitation_code": invite_code,
                "phone": phone,
                "email": f"r1-{uuid.uuid4().hex[:6]}@example.com",
            },
        )
    assert resp.status_code == 201, resp.text
    await async_session.commit()

    # List through the real endpoint body with a contextual token.
    token = TokenPayload(user_id=str(uuid.uuid4()), tenant_id=str(ws), roles=["admin"])
    page = await list_retailers(page=1, size=50, token=token, db=async_session)
    sources = {item.retailer.id: item.join_source for item in page.data.items}
    assert sources[retailer_code_id] == "code"
    invited_retailer_id = resp.json()["data"]["retailer"]["id"]
    assert sources[invited_retailer_id] == "invite"


async def test_register_endpoint_is_rate_limit_wired(async_session, monkeypatch):
    """The public register endpoint consults the endpoint-scoped limiter and
    surfaces its 429 (dual-entry contract: separately rate limited)."""
    await _prepare(async_session)

    calls = {"n": 0}

    class _TwoThenLimit:
        async def check_endpoint_rate_limit(self, request, *, namespace, limit):
            calls["n"] += 1
            if calls["n"] > 2:
                from core.error_codes import ErrorCode, MpangoAPIException

                raise MpangoAPIException(
                    error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                    message="Rate limit exceeded.",
                    status_code=429,
                    details={"limit": limit, "window_size": 60, "retry_after": 60},
                )
            return True, calls["n"], limit

    import core.rate_limiter as rl

    monkeypatch.setattr(rl, "get_rate_limiter", lambda: _TwoThenLimit())

    from api.v1.retailers import router as retailers_router

    async with _client_for(async_session, lambda: retailers_router) as client:
        ok1 = await client.post(
            "/api/v1/retailers/register",
            json={"join_intent": "x", "phone": _run_phone(), "email": "a@example.com"},
        )
        ok2 = await client.post(
            "/api/v1/retailers/register",
            json={"join_intent": "x", "phone": _run_phone(), "email": "b@example.com"},
        )
        limited = await client.post(
            "/api/v1/retailers/register",
            json={"join_intent": "x", "phone": _run_phone(), "email": "c@example.com"},
        )
    # First two pass the limiter (then fail later validation — 400 invalid
    # intent); the third is rejected BY the limiter with 429 + headers.
    assert ok1.status_code == 400 and ok2.status_code == 400
    assert limited.status_code == 429
    # Retry-After/X-RateLimit headers are enriched by the full-stack
    # middleware (covered by the S2-5 rate-limit suites); here we prove the
    # endpoint wiring itself: limiter consulted, 429 surfaced.
    assert calls["n"] == 3


# ---------------------------------------------------------------------------
# H2-A-R2/F2: active-wholesaler fail-closed (Kilo F2 closure)
# ---------------------------------------------------------------------------

async def test_lookup_code_neutral_for_every_non_active_lifecycle(async_session):
    """missing / deleted / suspended / provisioning / deactivated all return
    the SAME neutral not-found shape — no lifecycle disclosure."""
    await _prepare(async_session)
    from api.v1.public_join import router as public_join_router

    lifecycles = {
        "deleted": {"status": "active", "deleted": True},
        "suspended": {"status": "suspended", "deleted": False},
        "provisioning": {"status": "provisioning", "deleted": False},
        "deactivated": {"status": "deactivated", "deleted": False},
    }
    seeded = {}
    for name, cfg in lifecycles.items():
        ws = uuid.uuid4()
        code = _code()
        await _seed_wholesaler_with_rbac(
            async_session, wholesaler_id=ws, code=code, status=cfg["status"]
        )
        if cfg["deleted"]:
            await async_session.execute(
                text("UPDATE public.wholesalers SET is_deleted = true WHERE id = :i"),
                {"i": ws},
            )
        seeded[name] = code
    await async_session.flush()

    async with _client_for(async_session, lambda: public_join_router) as client:
        miss = await client.post(
            "/api/v1/wholesalers/lookup-code", json={"code": _code("MISS")}
        )
        responses = {}
        for name, code in seeded.items():
            responses[name] = await client.post(
                "/api/v1/wholesalers/lookup-code", json={"code": code}
            )

    assert miss.status_code == 200 and miss.json()["data"]["found"] is False
    for name, resp in responses.items():
        assert resp.status_code == 200, name
        data = resp.json()["data"]
        assert data["found"] is False, name
        assert data["name"] is None and data["region"] is None, name
        assert data["contact_masked"] is None and data["join_intent"] is None, name


async def test_join_intent_fails_closed_when_wholesaler_deactivates(async_session):
    """Intent issued while ACTIVE; supplier turns inactive before
    registration -> neutral rejection, ZERO side effects."""
    await _prepare(async_session)
    from services.email_delivery import (
        clear_dev_email_deliveries,
        get_dev_retailer_email_deliveries,
    )

    clear_dev_email_deliveries()
    ws = uuid.uuid4()
    code = _code()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws, code=code)
    intent, _ = issue_join_intent(wholesaler_id=ws, wholesaler_code=code)

    # Supplier deactivates between lookup and registration.
    await async_session.execute(
        text("UPDATE public.wholesalers SET status = 'deactivated' WHERE id = :i"),
        {"i": ws},
    )
    await async_session.flush()

    phone = _run_phone()
    email = f"r2-{uuid.uuid4().hex[:6]}@example.com"
    from api.v1.retailers import router as retailers_router

    async with _client_for(async_session, lambda: retailers_router) as client:
        resp = await client.post(
            "/api/v1/retailers/register",
            json={"join_intent": intent, "phone": phone, "email": email},
        )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "INVITATION_NOT_FOUND"  # single neutral code
    assert detail["message"] == "Registration failed"
    assert "deactivat" not in resp.text.lower()

    # ZERO persisted side effects (the API never commits on failure): roll
    # back any staged rows, then prove nothing for THIS submission exists —
    # no retailer, no binding, no setup token, no email delivery. Counts are
    # phone/retailer-scoped: the shared fresh-DB run carries committed rows
    # from earlier tests by design.
    await async_session.rollback()
    for sql, params in (
        ("SELECT COUNT(*) FROM public.retailers WHERE phone = :p", {"p": phone}),
        (
            "SELECT COUNT(*) FROM public.wholesaler_retailer_bindings b "
            "JOIN public.retailers r ON r.id = b.retailer_id WHERE r.phone = :p",
            {"p": phone},
        ),
        (
            "SELECT COUNT(*) FROM public.retailer_credential_setup_tokens t "
            "JOIN public.retailers r ON r.id = t.retailer_id WHERE r.phone = :p",
            {"p": phone},
        ),
    ):
        count = await async_session.execute(text(sql), params)
        assert count.scalar_one() == 0, sql
    assert get_dev_retailer_email_deliveries(email) == []


async def test_soft_deleted_wholesaler_join_intent_fails_closed(async_session):
    await _prepare(async_session)
    ws = uuid.uuid4()
    code = _code()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws, code=code)
    intent, _ = issue_join_intent(wholesaler_id=ws, wholesaler_code=code)

    await async_session.execute(
        text("UPDATE public.wholesalers SET is_deleted = true WHERE id = :i"),
        {"i": ws},
    )
    await async_session.flush()

    from api.v1.retailers import router as retailers_router

    async with _client_for(async_session, lambda: retailers_router) as client:
        resp = await client.post(
            "/api/v1/retailers/register",
            json={
                "join_intent": intent,
                "phone": _run_phone(),
                "email": f"r2-{uuid.uuid4().hex[:6]}@example.com",
            },
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVITATION_NOT_FOUND"


async def test_invitation_registration_inherits_active_guard(async_session):
    """Entry A: a live invitation from a supplier that later deactivates can
    no longer be consumed — same neutral rejection, zero side effects."""
    await _prepare(async_session)
    from services.email_delivery import clear_dev_email_deliveries

    clear_dev_email_deliveries()
    ws = uuid.uuid4()
    code = _code()
    await _seed_wholesaler_with_rbac(async_session, wholesaler_id=ws, code=code)
    phone = _run_phone()
    invite_code = f"R2INV{uuid.uuid4().hex[:10].upper()}"
    with run_as_system(reason="r2_invitation_seed"):
        await InvitationRepository().create(
            async_session,
            code=invite_code,
            wholesaler_id=ws,
            retailer_phone=phone,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
    # Supplier is suspended AFTER the invitation was issued.
    await async_session.execute(
        text("UPDATE public.wholesalers SET status = 'suspended' WHERE id = :i"),
        {"i": ws},
    )
    await async_session.flush()

    from api.v1.retailers import router as retailers_router

    async with _client_for(async_session, lambda: retailers_router) as client:
        resp = await client.post(
            "/api/v1/retailers/register",
            json={
                "invitation_code": invite_code,
                "phone": phone,
                "email": f"r2-{uuid.uuid4().hex[:6]}@example.com",
            },
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVITATION_NOT_FOUND"
    assert "suspend" not in resp.text.lower()
    # Invitation NOT consumed (usable again if the supplier reactivates).
    row = await async_session.execute(
        text("SELECT status, used_at FROM public.invitations WHERE code = :c"),
        {"c": invite_code},
    )
    status, used_at = row.one()
    assert status == "active" and used_at is None
    # Zero persisted side effects (rollback staged rows first — the
    # invitation path stages the retailer BEFORE the wholesaler guard fires;
    # nothing is ever committed).
    await async_session.rollback()
    retailers = await async_session.execute(
        text("SELECT COUNT(*) FROM public.retailers WHERE phone = :p"), {"p": phone}
    )
    assert retailers.scalar_one() == 0
