"""MPANGO-MVP-INVARIANTS-R0 — revocation & refresh regression candidates (known-RED).

Converts the external architecture review's revocation counterexamples into
formal pytest cases on the frozen baseline bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f.

THIS FILE IS A REGRESSION CANDIDATE, NOT A GREEN MERGE CANDIDATE:
tests marked [TARGET-DEFECT RED] assert the access-revocation invariants the
external review showed the baseline violates (HTTP 200 after user soft-delete
or tenant suspension; refresh re-issuing sessions for dead subjects). They are
expected to FAIL (named RED) until the product is fixed. Never edit the
expectation to make them pass.

External evidence (AI_REPORT_INBOX/external-architecture-2026-09-06):
- supplementary-probes.json: http_deleted_user_suspended_tenant_skus = 200
- counterexamples.json: suspended_tenant_context_resolved=true,
  soft_deleted_user_context_resolved=true,
  refresh_nonexistent_principal_issued=true

Environment premises:
- Task-exclusive disposable loopback PostgreSQL (guard enforced).
- MPANGO_ENV must NOT be "test" (MockAuthStrategy would bypass the real JWT
  middleware); run with MPANGO_ENV=staging as the external lab did.
- REDIS_URL must point at an unreachable throwaway address so no existing
  Redis instance is touched.
- Access tokens are signed with the test process SECRET_KEY via the product's
  own create_contextual_token (same documented limitation as the external
  probes: synthetic issuance material, real verification path).

Execution entry: full HTTP stack via httpx ASGITransport (JWT auth middleware
→ tenant context resolution → RBAC → route), plus the refresh endpoint
function. NOT covered: Nginx/TLS, real browser, rate-limiter effectiveness,
logout/password-reset revocation policy (documented in the task report).
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import text

from core.security import create_contextual_token, decode_token, hash_password
from models import User
from schemas.auth import RefreshTokenRequest

from tests.mpango_invariants_r0_support import (
    assert_loopback_test_database,
    bootstrap_tenant,
    drop_tenant,
    new_tenant_identity,
    require_jwt_auth_strategy,
    seed_public_tenant_rows,
    tenant_session,
)


def setup_module(module) -> None:  # noqa: ANN001
    assert_loopback_test_database()
    require_jwt_auth_strategy()


async def _seed_tenant_user(
    *,
    schema: str,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
    email: str,
    password: str = "R0SyntheticPassword9!",
) -> uuid.UUID:
    """Create one active user with skus:read via the real tenant tables."""
    from models import Permission, Role

    async with tenant_session(schema, wholesaler_id) as db:
        perm = (
            await db.execute(text("SELECT id FROM permissions WHERE code = 'skus:read' LIMIT 1"))
        ).scalar_one_or_none()
        if perm is None:
            perm = Permission(code="skus:read", description="r0 synthetic permission")
            db.add(perm)
            await db.flush()
        role = Role(name=f"r0_admin_{uuid.uuid4().hex[:8]}", description="r0 synthetic role")
        role.permissions.append(perm)
        db.add(role)
        await db.flush()
        user = User(
            email=email,
            password_hash=hash_password(password),
            is_active=True,
            roles=[role],
        )
        db.add(user)
        await db.flush()
        user_id = user.id
    return user_id


async def _set_user_flags(
    *, schema: str, user_id: uuid.UUID, is_active: bool | None = None, is_deleted: bool | None = None
) -> None:
    async with tenant_session(schema, uuid.UUID(int=0)) as db:
        if is_active is not None:
            await db.execute(
                text("UPDATE users SET is_active = :v WHERE id = :u"),
                {"v": is_active, "u": user_id},
            )
        if is_deleted is not None:
            await db.execute(
                text("UPDATE users SET is_deleted = :v, deleted_at = now() WHERE id = :u"),
                {"v": is_deleted, "u": user_id},
            )


async def _set_tenant_status(wholesaler_id: uuid.UUID, status: str) -> None:
    from database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE public.wholesalers SET status = :s WHERE id = :w"),
            {"s": status, "w": wholesaler_id},
        )
        await db.commit()


def _bearer(user_id: uuid.UUID, wholesaler_id: uuid.UUID, schema: str) -> str:
    return create_contextual_token(
        str(user_id), ["r0_admin"], str(wholesaler_id), schema, token_type="access"
    )


def _refresh(user_id: uuid.UUID, wholesaler_id: uuid.UUID, schema: str) -> str:
    return create_contextual_token(
        str(user_id), ["r0_admin"], str(wholesaler_id), schema, token_type="refresh"
    )


async def _assert_refresh_refused(token: str, invariant_name: str, scenario: str) -> None:
    """Assert POST /auth/refresh refuses `token`; produce a named RED otherwise.

    On the fixed product the endpoint raises HTTPException 401 → PASS. On the
    current baseline it returns a fresh token pair instead of raising, which
    fails with the named invariant so the RED is unambiguous in reports.
    """
    from api.v1.auth import refresh_token

    issued = None
    try:
        issued = await refresh_token(RefreshTokenRequest(refresh_token=token))
    except HTTPException as refused:
        assert refused.status_code == 401, (
            f"{invariant_name}: refresh must refuse with 401, got {refused.status_code}"
        )
        return
    claims = decode_token(issued.data.access_token)
    pytest.fail(
        f"{invariant_name}: refresh must NOT re-issue a session for {scenario}; "
        f"it returned a fresh pair (access token authenticates user_id="
        f"{claims.user_id}, tenant {claims.tenant_id}, roles={claims.roles}). "
        "POST /api/v1/auth/refresh re-signs purely from token claims with no "
        "subject/tenant/session validation."
    )


@pytest.fixture
async def http_client():
    from main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://invariants-r0.invalid",
    ) as client:
        yield client


class TenantEnv:
    def __init__(self, wholesaler_id, retailer_id, schema):
        self.wholesaler_id = wholesaler_id
        self.retailer_id = retailer_id
        self.schema = schema


async def _make_env() -> TenantEnv:
    wholesaler_id, retailer_id, schema = new_tenant_identity()
    await bootstrap_tenant(schema)
    await seed_public_tenant_rows(wholesaler_id=wholesaler_id, retailer_id=retailer_id)
    return TenantEnv(wholesaler_id, retailer_id, schema)


async def _drop_env(env: TenantEnv) -> None:
    await drop_tenant(env.schema, wholesaler_id=env.wholesaler_id, retailer_id=env.retailer_id)


# ---------------------------------------------------------------------------
# 1. CONTROL: active user + active tenant can access
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_control_active_user_active_tenant_can_access(http_client):
    """[CONTROL — expected PASS] Baseline access works for a valid subject.

    正常对照: active user, active tenant, valid contextual token → HTTP 200.
    目标缺陷: none (control).
    环境前提: MPANGO_ENV=staging (real JwtAuthStrategy), unreachable Redis.
    执行入口: GET /api/v1/skus through the full HTTP middleware stack.
    未覆盖范围: token issuance (synthetic signing material, not the login
    endpoint), Nginx/TLS, browser.
    """
    env = await _make_env()
    try:
        user_id = await _seed_tenant_user(
            schema=env.schema,
            wholesaler_id=env.wholesaler_id,
            retailer_id=env.retailer_id,
            email=f"r0-{uuid.uuid4().hex[:8]}@example.com",
        )
        response = await http_client.get(
            "/api/v1/skus",
            headers={"Authorization": "Bearer " + _bearer(user_id, env.wholesaler_id, env.schema)},
        )
        assert response.status_code == 200, (
            f"CONTROL: active user in active tenant must get 200, got {response.status_code}: {response.text[:300]}"
        )
    finally:
        await _drop_env(env)


# ---------------------------------------------------------------------------
# 2. CONTROL: deactivated (is_active=false) user is already denied
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_control_deactivated_user_denied(http_client):
    """[CONTROL — expected PASS] is_active=false is enforced today.

    正常对照: resolve_tenant_context checks is_active and denies.
    目标缺陷: none (control — shows the enforcement gap is is_deleted/tenant
    status, not the whole resolver).
    环境前提: same as control above.
    执行入口: GET /api/v1/skus through the full HTTP middleware stack.
    未覆盖范围: token issuance (synthetic).
    """
    env = await _make_env()
    try:
        user_id = await _seed_tenant_user(
            schema=env.schema,
            wholesaler_id=env.wholesaler_id,
            retailer_id=env.retailer_id,
            email=f"r0-{uuid.uuid4().hex[:8]}@example.com",
        )
        await _set_user_flags(schema=env.schema, user_id=user_id, is_active=False)
        response = await http_client.get(
            "/api/v1/skus",
            headers={"Authorization": "Bearer " + _bearer(user_id, env.wholesaler_id, env.schema)},
        )
        assert response.status_code == 401, (
            f"CONTROL: deactivated user must be denied 401, got {response.status_code}"
        )
    finally:
        await _drop_env(env)


# ---------------------------------------------------------------------------
# 3. TARGET-DEFECT RED: soft-deleted user in an ACTIVE tenant is denied
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_soft_deleted_user_in_active_tenant_denied(http_client):
    """[TARGET-DEFECT RED] Old credentials must die with the user row.

    Invariant (REVIEW §4.1 fix goal): a soft-deleted user inside an active
    tenant must get 401 on every authenticated route. Today the soft delete
    (exactly what crud/user.soft_delete_user writes: is_deleted=true,
    is_active stays true) is invisible to resolve_tenant_context and to the
    RBAC role loader, so the old access token keeps returning 200 (external
    counterexample: HTTP 200 on GET /api/v1/skus).

    正常对照: the two control tests above bracket this case.
    目标缺陷: api/context/tenant.py resolve_tenant_context checks only
    user existence and is_active; crud/user.get_user_with_permissions does
    not filter is_deleted.
    环境前提: user row soft-deleted directly (identical state to the
    product's DELETE /api/v1/users/{id} soft delete).
    执行入口: GET /api/v1/skus through the full HTTP middleware stack.
    未覆盖范围: the DELETE /api/v1/users HTTP call itself (the revocation
    effect, not the deactivation action, is the subject here).

    Expected RED failure name: INVARIANT_R0_SOFT_DELETED_USER_ACCESS.
    """
    env = await _make_env()
    try:
        user_id = await _seed_tenant_user(
            schema=env.schema,
            wholesaler_id=env.wholesaler_id,
            retailer_id=env.retailer_id,
            email=f"r0-{uuid.uuid4().hex[:8]}@example.com",
        )
        await _set_user_flags(schema=env.schema, user_id=user_id, is_deleted=True)
        response = await http_client.get(
            "/api/v1/skus",
            headers={"Authorization": "Bearer " + _bearer(user_id, env.wholesaler_id, env.schema)},
        )
        assert response.status_code == 401, (
            "INVARIANT_R0_SOFT_DELETED_USER_ACCESS: a soft-deleted user in an "
            f"active tenant must be denied (401), got {response.status_code} "
            f"with body {response.text[:200]}. Old credentials survive user "
            "deletion (resolve_tenant_context never checks is_deleted)."
        )
    finally:
        await _drop_env(env)


# ---------------------------------------------------------------------------
# 4. TARGET-DEFECT RED: active user in a SUSPENDED tenant is denied
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_active_user_in_suspended_tenant_denied(http_client):
    """[TARGET-DEFECT RED] Tenant suspension must stop tenant access.

    Invariant (REVIEW §4.1 fix goal): when public.wholesalers.status is
    suspended, no user of that tenant may resolve a tenant context. Today
    resolve_tenant_context never reads the wholesaler row, so an active user
    keeps full access after the tenant is suspended (external counterexample:
    suspended_tenant_context_resolved=true, HTTP 200 on GET /api/v1/skus).

    正常对照: control tests above.
    目标缺陷: api/context/tenant.py resolve_tenant_context does not check
    tenant status. Note: no HTTP route currently writes wholesalers.status;
    suspension state is set directly here (same as the external probe).
    环境前提: tenant row flipped to status='suspended' in public schema.
    执行入口: GET /api/v1/skus through the full HTTP middleware stack.
    未覆盖范围: whichever admin surface will eventually set tenant status.

    Expected RED failure name: INVARIANT_R0_SUSPENDED_TENANT_ACCESS.
    """
    env = await _make_env()
    try:
        user_id = await _seed_tenant_user(
            schema=env.schema,
            wholesaler_id=env.wholesaler_id,
            retailer_id=env.retailer_id,
            email=f"r0-{uuid.uuid4().hex[:8]}@example.com",
        )
        await _set_tenant_status(env.wholesaler_id, "suspended")
        response = await http_client.get(
            "/api/v1/skus",
            headers={"Authorization": "Bearer " + _bearer(user_id, env.wholesaler_id, env.schema)},
        )
        assert response.status_code == 401, (
            "INVARIANT_R0_SUSPENDED_TENANT_ACCESS: an active user in a "
            f"suspended tenant must be denied (401), got {response.status_code} "
            f"with body {response.text[:200]}. resolve_tenant_context never "
            "checks public.wholesalers.status."
        )
    finally:
        await _drop_env(env)


# ---------------------------------------------------------------------------
# 5. TARGET-DEFECT RED: refresh must not re-issue for a nonexistent subject
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_refresh_nonexistent_principal_no_session():
    """[TARGET-DEFECT RED] Refresh for a principal with no DB row.

    Invariant (REVIEW §4.2 fix goal): refresh must re-validate the current
    subject; a refresh token referencing a nonexistent user must be refused
    (401), not traded for a fresh, valid session pair. Today
    POST /api/v1/auth/refresh (api/v1/auth.py:450) re-signs tokens purely
    from the presented token's claims with zero database lookups (external
    counterexample: refresh_nonexistent_principal_issued=true).

    正常对照: the stolen/rotated token shape is exactly what the endpoint
    itself issues (same issuer, signing key and claims) — only the subject
    is missing from the database.
    目标缺陷: refresh endpoint performs no user/tenant/session validation.
    环境前提: refresh token signed with the test process SECRET_KEY (the
    same material the app verifies with). This does NOT model forged
    signatures — an attacker still needs a validly signed token.
    执行入口: api.v1.auth.refresh_token (the POST /api/v1/auth/refresh
    handler) called directly; it has no auth dependencies by design.
    未覆盖范围: rate limiting and HTTP header layer around /auth/refresh.

    Expected RED failure name: INVARIANT_R0_REFRESH_NONEXISTENT_PRINCIPAL.
    """
    ghost_user = uuid.uuid4()
    wholesaler_id = uuid.uuid4()
    schema = "t_" + wholesaler_id.hex  # tenant need not exist for this case
    await _assert_refresh_refused(
        _refresh(ghost_user, wholesaler_id, schema),
        "INVARIANT_R0_REFRESH_NONEXISTENT_PRINCIPAL",
        "a principal with no user row",
    )


# ---------------------------------------------------------------------------
# 6. TARGET-DEFECT RED: refresh must not re-issue for a soft-deleted user
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_refresh_soft_deleted_user_no_session():
    """[TARGET-DEFECT RED] Refresh dies with the user (soft delete).

    Invariant: after soft deletion the presented refresh token must be
    refused — refresh must not mint a new access/refresh pair for a deleted
    subject. The user row EXISTS here (created, then soft-deleted exactly as
    crud/user.soft_delete_user would), so this is not the synthetic-ghost
    case: refresh simply never looks.

    正常对照: pre-deletion the refresh token is the endpoint's own output
    shape; deletion is the product's own soft-delete state.
    目标缺陷: refresh endpoint performs no subject validation.
    环境前提: same as the other revocation tests.
    执行入口: api.v1.auth.refresh_token handler.
    未覆盖范围: password-reset-driven revocation (separate open item).

    Expected RED failure name: INVARIANT_R0_REFRESH_DELETED_USER.
    """
    env = await _make_env()
    try:
        email = f"r0-{uuid.uuid4().hex[:8]}@example.com"
        user_id = await _seed_tenant_user(
            schema=env.schema,
            wholesaler_id=env.wholesaler_id,
            retailer_id=env.retailer_id,
            email=email,
        )
        old_refresh = _refresh(user_id, env.wholesaler_id, env.schema)
        await _set_user_flags(schema=env.schema, user_id=user_id, is_deleted=True)

        await _assert_refresh_refused(
            old_refresh,
            "INVARIANT_R0_REFRESH_DELETED_USER",
            "a soft-deleted user (row exists, is_deleted=true)",
        )
    finally:
        await _drop_env(env)


# ---------------------------------------------------------------------------
# 7. TARGET-DEFECT RED: refresh must not re-issue for a suspended tenant
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_refresh_suspended_tenant_no_session():
    """[TARGET-DEFECT RED] Refresh dies with the tenant.

    Invariant: a refresh token bound to a suspended tenant must be refused.
    The user is fully active here — only the tenant is suspended — isolating
    the tenant-status check that refresh never performs.

    正常对照: control test 1 proves the same token shape works pre-suspension.
    目标缺陷: refresh endpoint performs no tenant validation.
    环境前提: tenant row flipped to status='suspended' (no HTTP writer exists).
    执行入口: api.v1.auth.refresh_token handler.
    未覆盖范围: identity-only (pre-tenant-selection) refresh policy.

    Expected RED failure name: INVARIANT_R0_REFRESH_SUSPENDED_TENANT.
    """
    env = await _make_env()
    try:
        user_id = await _seed_tenant_user(
            schema=env.schema,
            wholesaler_id=env.wholesaler_id,
            retailer_id=env.retailer_id,
            email=f"r0-{uuid.uuid4().hex[:8]}@example.com",
        )
        old_refresh = _refresh(user_id, env.wholesaler_id, env.schema)
        await _set_tenant_status(env.wholesaler_id, "suspended")

        await _assert_refresh_refused(
            old_refresh,
            "INVARIANT_R0_REFRESH_SUSPENDED_TENANT",
            "an active user of a suspended tenant",
        )
    finally:
        await _drop_env(env)


# ---------------------------------------------------------------------------
# 8. CONTROL: refresh for a live subject still works (fixture sanity)
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_control_refresh_live_subject_issues_usable_session(http_client):
    """[CONTROL — expected PASS] Refresh works for a valid live subject.

    正常对照: active user + active tenant → refresh returns a new pair and
    the new access token is genuinely usable on an authenticated route.
    目标缺陷: none (control — makes the RED refresh cases meaningful: the
    only variable is subject liveness).
    环境前提: same as the other tests.
    执行入口: api.v1.auth.refresh_token handler + GET /api/v1/skus.
    未覆盖范围: rotation/replay policy (single-use refresh is not implemented).
    """
    env = await _make_env()
    try:
        user_id = await _seed_tenant_user(
            schema=env.schema,
            wholesaler_id=env.wholesaler_id,
            retailer_id=env.retailer_id,
            email=f"r0-{uuid.uuid4().hex[:8]}@example.com",
        )
        from api.v1.auth import refresh_token

        response = await refresh_token(
            RefreshTokenRequest(refresh_token=_refresh(user_id, env.wholesaler_id, env.schema))
        )
        assert response.success is True and response.data.access_token, (
            "CONTROL: refresh for a live subject must succeed"
        )
        new_access = response.data.access_token
        claims = decode_token(new_access)
        assert claims.user_id == str(user_id)
        assert claims.type == "access"

        probe = await http_client.get(
            "/api/v1/skus", headers={"Authorization": "Bearer " + new_access}
        )
        assert probe.status_code == 200, (
            f"CONTROL: refreshed access token must be usable (200), got {probe.status_code}"
        )
    finally:
        await _drop_env(env)
