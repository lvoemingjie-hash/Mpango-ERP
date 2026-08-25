"""DC-12R1-MVP-L1-J1-H2-B-R3-R1: user-role-assignment async serialization closure.

Real PostgreSQL 16 + real ASGI truth tests for
PUT /api/v1/users/{user_id}/roles against the OFFICIAL dual-tenant
provisioning path (signup -> verify-email -> setup-credential -> login ->
select-tenant), the same permission chain the frozen H2-B-R3 browser
journey M1 needs (users:create + roles:assign).

Confirmed causal path this file locks:

  assign_user_roles_endpoint -> assign_roles_to_user -> user_to_read

  crud/user.py assign_roles_to_user flushed the UPDATE, then ran a PARTIAL
  ``db.refresh(user, ["roles"])``. The flush's SQL-expression onupdate
  (``updated_at = now()``) leaves scalar state expired for post-fetch and a
  partial refresh never reloads it, so ``user_to_read`` then reads
  ``user.updated_at`` in synchronous context -> async implicit lazy-load /
  MissingGreenlet -> 500 after a successful role assignment.

Contract proven here:

  T1  Official tenant + real users:create; PUT roles -> 200 with the FULL
      UserRead scalar set (id/email/full_name/is_active/created_at/updated_at)
      plus the assigned admin role. Old code: 500 MissingGreenlet (RED).
  T2  CRUD-level: after assign_roles_to_user returns, ``user_to_read`` runs
      synchronously with an engine-level cursor probe attached -> ZERO SQL
      statements and no MissingGreenlet (nothing expired left behind).
  T3  Fresh-session persistence: the role binding is really committed and
      exists EXACTLY once; a second identical PUT replaces (never duplicates).
  T4  Invalid role ID (malformed UUID and unknown UUID) -> exact 400
      INVALID_ROLE with ZERO partial user_roles bindings.
  T5  Unknown user -> exact 404 USER_NOT_FOUND.
  T6  Same email provisioned in TWO tenants; each tenant assigns its own
      admin role to its own copy -> bindings stay tenant-isolated and the
      two role IDs never cross.
  T7  The real permission chain: owner's real admin permissions authorize
      POST /users (users:create) and PUT roles (roles:assign); a role-less
      in-tenant user is denied 403 PERMISSION_DENIED by the same chain.
  T8  Rollback path: assign_roles_to_user inside a transaction that rolls
      back leaves ZERO user_roles residue (flush-only writes are fully
      transactional).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text

from api.app import app
from api.middleware.auth import AuthenticationMiddleware
from api.v1.users import user_to_read
from auth.strategies.jwt import JwtAuthStrategy
from auth.strategies.mock import MockAuthStrategy
from crud.user import (
    assign_roles_to_user,
    create_user,
    get_user_by_id,
)
from database.session import AsyncSessionLocal, async_engine
from services.email_delivery import (
    clear_dev_email_deliveries,
    get_dev_email_deliveries,
)

pytestmark = pytest.mark.asyncio

USERS_URL = "/api/v1/users"
AUTH_SIGNUP = "/api/v1/auth/signup"
AUTH_VERIFY = "/api/v1/auth/verify-email"
AUTH_SETUP = "/api/v1/auth/onboarding/setup-credential"
AUTH_LOGIN = "/api/v1/auth/login"
AUTH_SELECT = "/api/v1/auth/select-tenant"

OWNER_PW = "R3r1OwnerPw_01!"  # pragma: allowlist secret
MEMBER_PW = "R3r1MemberPw_01!"  # pragma: allowlist secret


def _find_auth_middleware(application: FastAPI) -> AuthenticationMiddleware | None:
    """Locate the live AuthenticationMiddleware instance in the built ASGI
    stack (or None when the stack has not been built yet)."""
    node = getattr(application, "middleware_stack", None)
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        if isinstance(node, AuthenticationMiddleware):
            return node
        node = getattr(node, "app", None)
    return None


@pytest.fixture(autouse=True)
async def _real_jwt_strategy():
    """Run every test in this module against the REAL JwtAuthStrategy.

    The shared test app is wired under MPANGO_ENV=test, which selects
    MockAuthStrategy (fixed identity that ignores the Authorization header).
    The official dual-tenant provisioning path needs the real JWT chain —
    login issues real tokens, the middleware decodes them, resolves the real
    tenant session and the real user permission set. Swap the strategy on
    BOTH wiring layers — the built middleware stack instance (if the stack
    already exists) and the not-yet-built user_middleware spec (so a stack
    built mid-test also gets Jwt) — and restore the mock on both layers
    afterwards so later suites keep their environment. Restoring only one
    layer leaves Jwt baked into the built stack (or the spec) and poisons
    every later test process-shared with this app.
    """
    swapped: list[tuple[object, str, object]] = []
    original_mock: MockAuthStrategy | None = None
    jwt_strategy = JwtAuthStrategy()

    mw = _find_auth_middleware(app)
    if mw is not None and isinstance(mw._strategy, MockAuthStrategy):
        original_mock = mw._strategy
        swapped.append((mw, "_strategy", mw._strategy))
        mw._strategy = jwt_strategy

    for entry in app.user_middleware:
        if entry.cls is AuthenticationMiddleware and isinstance(
            entry.kwargs.get("strategy"), MockAuthStrategy
        ):
            original_mock = original_mock or entry.kwargs["strategy"]
            swapped.append((entry.kwargs, "strategy", entry.kwargs["strategy"]))
            entry.kwargs["strategy"] = jwt_strategy

    try:
        yield
    finally:
        for target, attr, original in swapped:
            if isinstance(target, dict):
                target[attr] = original
            else:
                setattr(target, attr, original)
        # The stack may have been BUILT during the test with the swapped
        # strategy — the live instance then holds our Jwt object even though
        # the spec above was restored. Restore it too (identity-checked).
        live = _find_auth_middleware(app)
        if (
            live is not None
            and original_mock is not None
            and live._strategy is jwt_strategy
        ):
            live._strategy = original_mock


@pytest.fixture(autouse=True)
async def _r3r1_isolation():
    """Deterministic per-test state: drop every tenant schema + registration
    so the cross-tenant login scan and role lookups never see leftovers
    from a previous test (same approach as the H2-B runtime closure suite)."""
    await _reset_tenant_state()
    clear_dev_email_deliveries()
    try:
        yield
    finally:
        clear_dev_email_deliveries()


async def _reset_tenant_state() -> None:
    async with AsyncSessionLocal() as db:
        ids = (
            await db.execute(text("SELECT id FROM public.wholesalers"))
        ).scalars().all()
        for wid in ids:
            schema = f"t_{str(wid).replace('-', '')}"
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        if ids:
            await db.execute(text("DELETE FROM public.tenant_registrations"))
        await db.execute(text("DELETE FROM public.wholesalers"))
        await db.commit()


def _client() -> AsyncClient:
    """Real ASGI client on the production app with its production session
    dependencies (per-request sessions, commit on success / rollback on
    failure). Unhandled exceptions surface as 500 responses (not raised)
    so the old-code MissingGreenlet is observable as a status code."""
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    )


async def _official_tenant(*, owner_pw: str = OWNER_PW) -> dict:
    """Provision ONE tenant through the official lifecycle and log its owner
    in to a contextual (tenant-scoped) JWT.

    Returns email/password/tenant_id/tenant_schema, the contextual bearer
    token, and the owner's tenant-local user id.
    """
    email = f"r3r1_{uuid.uuid4().hex}@example.com"

    async with _client() as client:
        r = await client.post(
            AUTH_SIGNUP,
            json={
                "companyName": f"R3R1 Company {uuid.uuid4().hex[:8]}",
                "country": "KE",
                "email": email,
                "phone": "+254700000000",
                "businessType": "wholesale",
                "password": owner_pw,
            },
        )
        assert r.status_code == 202, r.text

    verify_token = [
        d for d in get_dev_email_deliveries(email) if d.purpose == "email_verification"
    ][0].token
    async with _client() as client:
        v = await client.post(AUTH_VERIFY, json={"token": verify_token})
        assert v.status_code == 200, v.text

    setup_token = [
        d for d in get_dev_email_deliveries(email) if d.purpose == "owner_setup"
    ][0].token
    async with _client() as client:
        s = await client.post(
            AUTH_SETUP,
            json={"setupToken": setup_token, "password": owner_pw},
        )
        assert s.status_code == 200, s.text

    async with _client() as client:
        lg = await client.post(
            AUTH_LOGIN, json={"email": email, "password": owner_pw}
        )
        assert lg.status_code == 200, lg.text
        login_data = lg.json()["data"]
        tenant_id = login_data["available_tenants"][0]["id"]
        sel = await client.post(
            AUTH_SELECT,
            json={"tenant_id": tenant_id},
            headers={"Authorization": f"Bearer {login_data['access_token']}"},
        )
        assert sel.status_code == 200, sel.text
        token = sel.json()["data"]["access_token"]

    async with AsyncSessionLocal() as db:
        schema = (
            await db.execute(
                text(
                    "SELECT tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email = :e"
                ),
                {"e": email},
            )
        ).scalar_one()
        owner_user_id = (
            await db.execute(
                text(f'SELECT id FROM "{schema}".users WHERE email = :e'),
                {"e": email},
            )
        ).scalar_one()

    return {
        "email": email,
        "password": owner_pw,
        "tenant_id": tenant_id,
        "tenant_schema": schema,
        "token": token,
        "owner_user_id": str(owner_user_id),
    }


def _auth(ctx: dict) -> dict:
    return {"Authorization": f"Bearer {ctx['token']}"}


async def _tenant_admin_role_id(schema: str) -> str:
    async with AsyncSessionLocal() as db:
        rid = (
            await db.execute(
                text(f"SELECT id FROM \"{schema}\".roles WHERE name = 'admin'")
            )
        ).scalar_one()
    return str(rid)


async def _create_tenant_user(ctx: dict, email: str) -> str:
    """Real users:create permission chain (the browser journey M1 path)."""
    async with _client() as client:
        r = await client.post(
            USERS_URL,
            json={
                "email": email,
                "password": MEMBER_PW,
                "full_name": "R3 R1 Member",
            },
            headers=_auth(ctx),
        )
        assert r.status_code == 201, r.text
        return r.json()["data"]["id"]


async def _user_role_binding_count(schema: str, user_id: str) -> int:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                text(
                    f'SELECT COUNT(*) FROM "{schema}".user_roles '
                    "WHERE user_id = :uid"
                ),
                {"uid": user_id},
            )
        ).scalar_one()


async def _user_role_binding_count_for_role(
    schema: str, user_id: str, role_id: str
) -> int:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                text(
                    f'SELECT COUNT(*) FROM "{schema}".user_roles '
                    "WHERE user_id = :uid AND role_id = :rid"
                ),
                {"uid": user_id, "rid": role_id},
            )
        ).scalar_one()


# ---------------------------------------------------------------------------
# T1 — official provisioning happy path: 200 with the full scalar set
# ---------------------------------------------------------------------------

async def test_t1_put_roles_200_full_scalars_and_admin_role():
    ctx = await _official_tenant()
    member_email = f"t1_{uuid.uuid4().hex}@example.com"
    target_id = await _create_tenant_user(ctx, member_email)
    admin_role_id = await _tenant_admin_role_id(ctx["tenant_schema"])

    async with _client() as client:
        r = await client.put(
            f"{USERS_URL}/{target_id}/roles",
            json={"role_ids": [admin_role_id]},
            headers=_auth(ctx),
        )

    # Old code: 500 (MissingGreenlet during user_to_read). Closure: 200.
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["id"] == target_id
    assert data["email"] == member_email
    assert data["is_active"] is True
    assert data["full_name"] == "R3 R1 Member"
    # The expired-scalar contract: both timestamps must serialize (old code
    # died exactly on updated_at).
    assert data["created_at"], data
    assert data["updated_at"], data
    assert data["updated_at"] >= data["created_at"]
    assert [role["name"] for role in data["roles"]] == ["admin"]
    assert data["roles"][0]["id"] == admin_role_id


# ---------------------------------------------------------------------------
# T2 — zero implicit SQL / zero MissingGreenlet during serialization
# ---------------------------------------------------------------------------

async def test_t2_serialization_zero_implicit_sql_no_missing_greenlet():
    ctx = await _official_tenant()
    schema = ctx["tenant_schema"]
    admin_role_id = await _tenant_admin_role_id(schema)
    member_email = f"t2_{uuid.uuid4().hex}@example.com"

    async with AsyncSessionLocal() as db:
        db.info["tenant_schema"] = schema
        await db.execute(text(f'SET LOCAL search_path TO "{schema}", public'))

        user = await create_user(
            db, email=member_email, password=MEMBER_PW, full_name="T2 Member"
        )
        target = await get_user_by_id(db, str(user.id))
        assert target is not None

        result_user = await assign_roles_to_user(
            db=db,
            user=target,
            role_ids=[admin_role_id],
            updated_by=ctx["owner_user_id"],
        )

        statements: list[str] = []

        def _probe(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(async_engine.sync_engine, "before_cursor_execute", _probe)
        try:
            # Synchronous serialization, exactly like the endpoint does —
            # no await, no greenlet context. Expired state here would raise
            # MissingGreenlet (old code) or fire implicit SQL.
            payload = user_to_read(result_user)
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _probe)

        assert statements == [], (
            "user_to_read triggered implicit SQL: "
            f"{[s[:120] for s in statements]}"
        )
        assert payload.updated_at is not None
        assert payload.created_at is not None
        assert payload.email == member_email
        assert [role.name for role in payload.roles] == ["admin"]

        await db.rollback()


# ---------------------------------------------------------------------------
# T3 — fresh-session persistence, exactly once
# ---------------------------------------------------------------------------

async def test_t3_fresh_session_binding_persisted_exactly_once():
    ctx = await _official_tenant()
    schema = ctx["tenant_schema"]
    member_email = f"t3_{uuid.uuid4().hex}@example.com"
    target_id = await _create_tenant_user(ctx, member_email)
    admin_role_id = await _tenant_admin_role_id(schema)

    async with _client() as client:
        r = await client.put(
            f"{USERS_URL}/{target_id}/roles",
            json={"role_ids": [admin_role_id]},
            headers=_auth(ctx),
        )
        assert r.status_code == 200, r.text

    # Fresh session: committed, exactly one binding to exactly that role.
    assert await _user_role_binding_count(schema, target_id) == 1
    assert (
        await _user_role_binding_count_for_role(schema, target_id, admin_role_id) == 1
    )

    # Replace semantics: identical second PUT must not duplicate the binding.
    async with _client() as client:
        r2 = await client.put(
            f"{USERS_URL}/{target_id}/roles",
            json={"role_ids": [admin_role_id]},
            headers=_auth(ctx),
        )
        assert r2.status_code == 200, r2.text
    assert await _user_role_binding_count(schema, target_id) == 1


# ---------------------------------------------------------------------------
# T4 — exact 400 INVALID_ROLE, zero partial binding
# ---------------------------------------------------------------------------

async def test_t4_invalid_role_exact_400_and_zero_partial_binding():
    ctx = await _official_tenant()
    schema = ctx["tenant_schema"]
    target_id = await _create_tenant_user(ctx, f"t4_{uuid.uuid4().hex}@example.com")
    admin_role_id = await _tenant_admin_role_id(schema)

    async with _client() as client:
        for bad_payload in (
            {"role_ids": ["not-a-uuid"]},
            {"role_ids": [str(uuid.uuid4())]},
            # One valid + one unknown: the whole request must fail, no partials.
            {"role_ids": [admin_role_id, str(uuid.uuid4())]},
        ):
            r = await client.put(
                f"{USERS_URL}/{target_id}/roles",
                json=bad_payload,
                headers=_auth(ctx),
            )
            assert r.status_code == 400, r.text
            assert r.json()["detail"]["code"] == "INVALID_ROLE", r.text

    assert await _user_role_binding_count(schema, target_id) == 0


# ---------------------------------------------------------------------------
# T5 — exact 404 USER_NOT_FOUND
# ---------------------------------------------------------------------------

async def test_t5_unknown_user_exact_404_user_not_found():
    ctx = await _official_tenant()
    admin_role_id = await _tenant_admin_role_id(ctx["tenant_schema"])

    async with _client() as client:
        r = await client.put(
            f"{USERS_URL}/{str(uuid.uuid4())}/roles",
            json={"role_ids": [admin_role_id]},
            headers=_auth(ctx),
        )

    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "USER_NOT_FOUND", r.text


# ---------------------------------------------------------------------------
# T6 — dual-tenant same-email isolation
# ---------------------------------------------------------------------------

async def test_t6_dual_tenant_same_email_isolated_role_assignment():
    ctx_a = await _official_tenant()
    ctx_b = await _official_tenant()
    shared_email = f"shared_{uuid.uuid4().hex}@example.com"

    user_a = await _create_tenant_user(ctx_a, shared_email)
    user_b = await _create_tenant_user(ctx_b, shared_email)
    assert user_a != user_b

    role_a = await _tenant_admin_role_id(ctx_a["tenant_schema"])
    role_b = await _tenant_admin_role_id(ctx_b["tenant_schema"])
    assert role_a != role_b  # per-tenant role rows, never shared

    for ctx, target, role in ((ctx_a, user_a, role_a), (ctx_b, user_b, role_b)):
        async with _client() as client:
            r = await client.put(
                f"{USERS_URL}/{target}/roles",
                json={"role_ids": [role]},
                headers=_auth(ctx),
            )
            assert r.status_code == 200, r.text
            assert [ro["name"] for ro in r.json()["data"]["roles"]] == ["admin"]

    # Each tenant's copy carries exactly its own tenant's binding — the
    # other tenant's role never appears.
    assert (
        await _user_role_binding_count_for_role(
            ctx_a["tenant_schema"], user_a, role_a
        )
        == 1
    )
    assert (
        await _user_role_binding_count_for_role(
            ctx_a["tenant_schema"], user_a, role_b
        )
        == 0
    )
    assert (
        await _user_role_binding_count_for_role(
            ctx_b["tenant_schema"], user_b, role_b
        )
        == 1
    )
    assert (
        await _user_role_binding_count_for_role(
            ctx_b["tenant_schema"], user_b, role_a
        )
        == 0
    )

    # Tenant listing isolation: each tenant sees only its own copy of the
    # shared email, exactly one row.
    for ctx in (ctx_a, ctx_b):
        async with _client() as client:
            lst = await client.get(USERS_URL, headers=_auth(ctx))
            assert lst.status_code == 200, lst.text
            matches = [
                u
                for u in lst.json()["data"]["items"]
                if u["email"] == shared_email
            ]
            assert len(matches) == 1


# ---------------------------------------------------------------------------
# T7 — the real permission chain (users:create + roles:assign)
# ---------------------------------------------------------------------------

async def test_t7_real_permission_chain_and_denial():
    ctx = await _official_tenant()
    schema = ctx["tenant_schema"]
    member_email = f"t7_{uuid.uuid4().hex}@example.com"

    # users:create through the real chain (owner holds the seeded admin
    # role + ADMIN_PERMISSIONS from the official provisioning).
    member_id = await _create_tenant_user(ctx, member_email)
    admin_role_id = await _tenant_admin_role_id(schema)

    # Log the role-less member in through the same official auth path and
    # try roles:assign with them — the real RBAC dependency must deny 403.
    async with _client() as client:
        lg = await client.post(
            AUTH_LOGIN, json={"email": member_email, "password": MEMBER_PW}
        )
        assert lg.status_code == 200, lg.text
        login_data = lg.json()["data"]
        tenant_id = login_data["available_tenants"][0]["id"]
        assert tenant_id == ctx["tenant_id"]
        sel = await client.post(
            AUTH_SELECT,
            json={"tenant_id": tenant_id},
            headers={"Authorization": f"Bearer {login_data['access_token']}"},
        )
        assert sel.status_code == 200, sel.text
        member_token = sel.json()["data"]["access_token"]

        denied = await client.put(
            f"{USERS_URL}/{member_id}/roles",
            json={"role_ids": [admin_role_id]},
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert denied.status_code == 403, denied.text
        assert denied.json()["detail"]["code"] == "PERMISSION_DENIED", denied.text

    assert await _user_role_binding_count(schema, member_id) == 0

    # The SAME request under the owner's real roles:assign permission passes.
    async with _client() as client:
        allowed = await client.put(
            f"{USERS_URL}/{member_id}/roles",
            json={"role_ids": [admin_role_id]},
            headers=_auth(ctx),
        )
        assert allowed.status_code == 200, allowed.text

    assert (
        await _user_role_binding_count_for_role(schema, member_id, admin_role_id) == 1
    )


# ---------------------------------------------------------------------------
# T8 — rollback path leaves zero user_roles residue
# ---------------------------------------------------------------------------

async def test_t8_rollback_leaves_zero_user_roles_residue():
    ctx = await _official_tenant()
    schema = ctx["tenant_schema"]
    admin_role_id = await _tenant_admin_role_id(schema)
    member_email = f"t8_{uuid.uuid4().hex}@example.com"

    async with AsyncSessionLocal() as db:
        db.info["tenant_schema"] = schema
        await db.execute(text(f'SET LOCAL search_path TO "{schema}", public'))

        user = await create_user(
            db, email=member_email, password=MEMBER_PW, full_name="T8 Member"
        )
        target = await get_user_by_id(db, str(user.id))
        assigned = await assign_roles_to_user(
            db=db, user=target, role_ids=[admin_role_id]
        )
        # The returned object already reports the new binding (flushed in
        # the still-open transaction)...
        assert [role.name for role in assigned.roles] == ["admin"]

        # ...but an abort before commit must revert EVERYTHING, including
        # the user_roles mutation (no residue survives the rollback).
        await db.rollback()

    assert await _user_role_binding_count(schema, str(user.id)) == 0
