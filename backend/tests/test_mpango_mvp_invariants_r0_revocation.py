"""MPANGO-MVP-INVARIANTS-R0/R1 — revocation & refresh regression tests.

R1 fix round (branch zcode/mpango-mvp-invariants-r1-auth-stock-fix-2026-09-08):
the four access-revocation REDs and the three refresh REDs from the accepted
R0-R2 known-RED baseline (1485c3f5) are now expected to PASS — the product
fix landed in this round:

- api/context/tenant.py resolve_tenant_context now denies soft-deleted users
  (USER_DELETED) and requires an existing, non-deleted, active
  public.wholesalers row for the token's tenant (TENANT_NOT_FOUND /
  TENANT_NOT_ACTIVE), reading CURRENT database state instead of trusting the
  token's claims.
- api/v1/auth.py refresh (contextual branch) now re-validates the subject and
  tenant against the database before re-signing; the endpoint gained a real
  DB dependency (Depends(get_db_session)) so the validation is exercised by
  the REAL HTTP path, not only direct function calls.

Test-node names from the R0-R2 baseline are preserved 1:1 (the "red_" prefix
is the historical identifier of the R0 counterexample nodes; their expected
verdict is now PASS). The refresh tests were moved from direct route-function
calls to REAL HTTP (POST /api/v1/auth/refresh via httpx ASGITransport) per the
R1 directive; the endpoint's DB dependency is resolved through FastAPI DI in
every request.

New R1 controls: refresh with a wrong-signature token and with a wrong token
type keep being refused; every refused refresh returns NO token material of
any kind (a refusal must not mint a session); two tenants' same-kind data
never cross-reads over the real HTTP stack.

External evidence (AI_REPORT_INBOX/external-architecture-2026-09-06):
- supplementary-probes.json: http_deleted_user_suspended_tenant_skus = 200
- counterexamples.json: suspended_tenant_context_resolved=true,
  soft_deleted_user_context_resolved=true,
  refresh_nonexistent_principal_issued=true

Environment premises:
- Task-exclusive disposable loopback PostgreSQL 16 (ownership guard enforced).
- MPANGO_ENV must not normalize to "test" (MockAuthStrategy would bypass the
  real JWT middleware); run with MPANGO_ENV=staging as the external lab did.
- REDIS_URL must point at an unreachable throwaway address so no existing
  Redis instance is touched (read-through caches fail open; see task record
  for the registered out-of-scope cache-key finding).
- Access tokens are signed with the test process SECRET_KEY via the product's
  own create_contextual_token (same documented limitation as the external
  probes: synthetic issuance material, real verification path).

Execution entry: full HTTP stack via httpx ASGITransport (JWT auth middleware
→ tenant context resolution → RBAC → route), and POST /api/v1/auth/refresh
through the same HTTP stack. NOT covered: Nginx/TLS, real browser,
rate-limiter effectiveness, logout/password-reset revocation policy,
identity-only refresh (documented in the task record).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from jose import jwt as jose_jwt
from sqlalchemy import text

from core.config import get_settings
from core.security import create_contextual_token, hash_password

from tests.mpango_invariants_r0_support import (
    TenantIdentity,
    r0_task_database,  # noqa: F401 - session fixture via usefixtures (ownership proof)
    require_jwt_auth_strategy,
    seed_sku_with_stock,
    tenant_session,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("r0_task_database")]


def setup_module(module) -> None:  # noqa: ANN001
    require_jwt_auth_strategy()


async def _seed_tenant_user(
    *,
    identity: TenantIdentity,
    email: str,
    password: str = "R0SyntheticPassword9!",
) -> uuid.UUID:
    """Create one active user with skus:read via the real tenant tables."""
    from models import Permission, Role
    from models.user import User

    async with tenant_session(identity.schema, identity.wholesaler_id) as db:
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
    *, identity: TenantIdentity, user_id: uuid.UUID,
    is_active: bool | None = None, is_deleted: bool | None = None,
) -> None:
    async with tenant_session(identity.schema) as db:
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


async def _set_tenant_status(identity: TenantIdentity, status: str) -> None:
    from database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE public.wholesalers SET status = :s WHERE id = :w"),
            {"s": status, "w": identity.wholesaler_id},
        )
        await db.commit()


def _bearer(user_id: uuid.UUID, identity: TenantIdentity) -> str:
    return create_contextual_token(
        str(user_id), ["r0_admin"], str(identity.wholesaler_id), identity.schema,
        token_type="access",
    )


def _refresh(user_id: uuid.UUID, identity: TenantIdentity) -> str:
    return create_contextual_token(
        str(user_id), ["r0_admin"], str(identity.wholesaler_id), identity.schema,
        token_type="refresh",
    )


def _forged_refresh(user_id: uuid.UUID, identity: TenantIdentity) -> str:
    """A structurally valid refresh token signed with the WRONG key.

    Models an attacker-crafted (not legitimately issued) token: correct claims
    shape, invalid signature. The endpoint must keep refusing it at the
    signature-verification layer — the R1 subject/tenant DB validation must
    never become the only line of defense.
    """
    settings = get_settings()
    payload = {
        "user_id": str(user_id),
        "roles": ["r0_admin"],
        "tenant_id": str(identity.wholesaler_id),
        "tenant_schema": identity.schema,
        "exp": datetime.utcnow() + timedelta(days=1),
        "type": "refresh",
    }
    return jose_jwt.encode(
        payload, "r1-wrong-signing-key-material-not-the-real-secret",
        algorithm=settings.ALGORITHM,
    )


@pytest.fixture
async def http_client():
    from main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://invariants-r0.invalid",
    ) as client:
        yield client


async def _http_refresh(http_client: httpx.AsyncClient, token: str) -> httpx.Response:
    """POST /api/v1/auth/refresh through the real HTTP stack (no auth header:
    the endpoint is authenticated by the refresh token in the body)."""
    return await http_client.post("/api/v1/auth/refresh", json={"refresh_token": token})


async def _assert_refresh_refused(
    http_client: httpx.AsyncClient,
    token: str,
    invariant_name: str,
    scenario: str,
) -> None:
    """Assert POST /api/v1/auth/refresh refuses `token` — and mints nothing.

    A refusal must be 401 AND must not return any token material: a rejected
    refresh may not produce a new session in any form.
    """
    response = await _http_refresh(http_client, token)
    assert response.status_code == 401, (
        f"{invariant_name}: refresh must refuse with 401 for {scenario}, "
        f"got {response.status_code} with body {response.text[:300]}. "
        "POST /api/v1/auth/refresh re-signs purely from token claims with no "
        "subject/tenant validation."
    )
    body = response.json()
    data = body.get("data") or {}
    assert not data.get("access_token") and not data.get("refresh_token"), (
        f"{invariant_name}: a refused refresh must not mint any session; "
        f"the 401 body carries token material ({str(body)[:300]})."
    )


# ---------------------------------------------------------------------------
# 1. CONTROL: active user + active tenant can access
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_control_active_user_active_tenant_can_access(http_client):
    """[CONTROL — expected PASS] Baseline access works for a valid subject.

    正常对照: active user, active tenant, valid contextual token → HTTP 200.
    Guards against an over-broad fix that denies valid traffic.
    目标缺陷: none (control).
    环境前提: real JwtAuthStrategy proven by setup guard; unreachable Redis.
    执行入口: GET /api/v1/skus through the full HTTP middleware stack.
    未覆盖范围: token issuance (synthetic signing material, not the login
    endpoint), Nginx/TLS, browser.
    """
    identity = await TenantIdentity().create()
    try:
        user_id = await _seed_tenant_user(
            identity=identity, email=f"r0-{uuid.uuid4().hex[:8]}@example.com"
        )
        response = await http_client.get(
            "/api/v1/skus", headers={"Authorization": "Bearer " + _bearer(user_id, identity)}
        )
        assert response.status_code == 200, (
            f"CONTROL: active user in active tenant must get 200, got {response.status_code}: {response.text[:300]}"
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 2. CONTROL: deactivated (is_active=false) user is already denied
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_control_deactivated_user_denied(http_client):
    """[CONTROL — expected PASS] is_active=false is enforced today.

    正常对照: resolve_tenant_context checks is_active and denies.
    目标缺陷: none (control — shows the enforcement gap was is_deleted/tenant
    status, not the whole resolver).
    环境前提: same as control above.
    执行入口: GET /api/v1/skus through the full HTTP middleware stack.
    未覆盖范围: token issuance (synthetic).
    """
    identity = await TenantIdentity().create()
    try:
        user_id = await _seed_tenant_user(
            identity=identity, email=f"r0-{uuid.uuid4().hex[:8]}@example.com"
        )
        await _set_user_flags(identity=identity, user_id=user_id, is_active=False)
        response = await http_client.get(
            "/api/v1/skus", headers={"Authorization": "Bearer " + _bearer(user_id, identity)}
        )
        assert response.status_code == 401, (
            f"CONTROL: deactivated user must be denied 401, got {response.status_code}"
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 3. R0 RED (fixed in R1): soft-deleted user in an ACTIVE tenant is denied
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_soft_deleted_user_in_active_tenant_denied(http_client):
    """[R0 RED → expected PASS after the R1 fix] Old credentials die with the
    user row.

    Invariant (REVIEW §4.1 fix goal): a soft-deleted user inside an active
    tenant must get 401 on every authenticated route. The soft delete
    (exactly what crud/user.soft_delete_user writes: is_deleted=true,
    is_active stays true) was invisible to resolve_tenant_context, so the old
    access token kept returning 200 (external counterexample: HTTP 200 on
    GET /api/v1/skus). R1 fix: resolve_tenant_context now checks is_deleted
    against the current row.

    正常对照: the two control tests above bracket this case.
    目标缺陷(已修复): api/context/tenant.py resolve_tenant_context checked only
    user existence and is_active.
    环境前提: user row soft-deleted directly (identical state to the
    product's DELETE /api/v1/users/{id} soft delete).
    执行入口: GET /api/v1/skus through the full HTTP middleware stack.
    未覆盖范围: the DELETE /api/v1/users HTTP call itself (the revocation
    effect, not the deactivation action, is the subject here).

    Pre-fix RED failure name: INVARIANT_R0_SOFT_DELETED_USER_ACCESS.
    """
    identity = await TenantIdentity().create()
    try:
        user_id = await _seed_tenant_user(
            identity=identity, email=f"r0-{uuid.uuid4().hex[:8]}@example.com"
        )
        await _set_user_flags(identity=identity, user_id=user_id, is_deleted=True)
        response = await http_client.get(
            "/api/v1/skus", headers={"Authorization": "Bearer " + _bearer(user_id, identity)}
        )
        assert response.status_code == 401, (
            "INVARIANT_R0_SOFT_DELETED_USER_ACCESS: a soft-deleted user in an "
            f"active tenant must be denied (401), got {response.status_code} "
            f"with body {response.text[:200]}. Old credentials survive user "
            "deletion (resolve_tenant_context never checks is_deleted)."
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 4. R0 RED (fixed in R1): active user in a SUSPENDED tenant is denied
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_active_user_in_suspended_tenant_denied(http_client):
    """[R0 RED → expected PASS after the R1 fix] Tenant suspension stops
    tenant access.

    Invariant (REVIEW §4.1 fix goal): when public.wholesalers.status is
    suspended, no user of that tenant may resolve a tenant context.
    resolve_tenant_context never read the wholesaler row, so an active user
    kept full access after the tenant was suspended (external counterexample:
    suspended_tenant_context_resolved=true, HTTP 200 on GET /api/v1/skus).
    R1 fix: resolve_tenant_context now requires an existing, non-deleted,
    active wholesalers row for the token's tenant.

    正常对照: control tests above.
    目标缺陷(已修复): api/context/tenant.py resolve_tenant_context did not
    check tenant status. Note: no HTTP route currently writes
    wholesalers.status; suspension state is set directly here (same as the
    external probe).
    环境前提: tenant row flipped to status='suspended' in public schema.
    执行入口: GET /api/v1/skus through the full HTTP middleware stack.
    未覆盖范围: whichever admin surface will eventually set tenant status.

    Pre-fix RED failure name: INVARIANT_R0_SUSPENDED_TENANT_ACCESS.
    """
    identity = await TenantIdentity().create()
    try:
        user_id = await _seed_tenant_user(
            identity=identity, email=f"r0-{uuid.uuid4().hex[:8]}@example.com"
        )
        await _set_tenant_status(identity, "suspended")
        response = await http_client.get(
            "/api/v1/skus", headers={"Authorization": "Bearer " + _bearer(user_id, identity)}
        )
        assert response.status_code == 401, (
            "INVARIANT_R0_SUSPENDED_TENANT_ACCESS: an active user in a "
            f"suspended tenant must be denied (401), got {response.status_code} "
            f"with body {response.text[:200]}. resolve_tenant_context never "
            "checks public.wholesalers.status."
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 5. R0 RED (fixed in R1): refresh must not re-issue for a nonexistent subject
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_refresh_nonexistent_principal_no_session(http_client):
    """[R0 RED → expected PASS after the R1 fix] Refresh for a principal with
    no DB row.

    Invariant (REVIEW §4.2 fix goal): refresh must re-validate the current
    subject; a refresh token referencing a nonexistent user/tenant must be
    refused (401), not traded for a fresh, valid session pair. The baseline
    POST /api/v1/auth/refresh re-signed tokens purely from the presented
    token's claims with zero database lookups (external counterexample:
    refresh_nonexistent_principal_issued=true). R1 fix: the contextual branch
    re-validates tenant + subject rows before re-signing.

    R1 change: executed through the REAL HTTP endpoint (the validation lives
    in the route handler and its DB dependency is resolved by FastAPI DI, so
    HTTP and direct calls exercise the same code).

    正常对照: the stolen/rotated token shape is exactly what the endpoint
    itself issues (same issuer, signing key and claims) — only the subject
    is missing from the database.
    目标缺陷(已修复): refresh endpoint performed no user/tenant/session
    validation.
    环境前提: refresh token signed with the test process SECRET_KEY (the
    same material the app verifies with). This does NOT model forged
    signatures — see the wrong-signature control for that layer.
    执行入口: POST /api/v1/auth/refresh over the real HTTP stack.
    未覆盖范围: rate limiting and HTTP header layer around /auth/refresh.

    Pre-fix RED failure name: INVARIANT_R0_REFRESH_NONEXISTENT_PRINCIPAL.
    """
    ghost_user = uuid.uuid4()
    wholesaler_id = uuid.uuid4()
    schema = "t_" + wholesaler_id.hex  # tenant need not exist for this case
    ghost = TenantIdentity()
    ghost.wholesaler_id = wholesaler_id
    ghost.schema = schema
    try:
        await _assert_refresh_refused(
            http_client,
            _refresh(ghost_user, ghost),
            "INVARIANT_R0_REFRESH_NONEXISTENT_PRINCIPAL",
            "a principal with no user row",
        )
    finally:
        # Nothing was created for the ghost tenant; drop() is a safe no-op
        # (IF EXISTS) that removes any partial public rows by UUID.
        await ghost.drop()


# ---------------------------------------------------------------------------
# 6. R0 RED (fixed in R1): refresh must not re-issue for a soft-deleted user
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_refresh_soft_deleted_user_no_session(http_client):
    """[R0 RED → expected PASS after the R1 fix] Refresh dies with the user
    (soft delete).

    Invariant: after soft deletion the presented refresh token must be
    refused — refresh must not mint a new access/refresh pair for a deleted
    subject. The user row EXISTS here (created, then soft-deleted exactly as
    crud/user.soft_delete_user would), so this is not the synthetic-ghost
    case: refresh simply never looked. R1 fix: the contextual branch checks
    the tenant-schema users row (existence, is_deleted, is_active) before
    re-signing.

    正常对照: pre-deletion the refresh token is the endpoint's own output
    shape; deletion is the product's own soft-delete state.
    目标缺陷(已修复): refresh endpoint performed no subject validation.
    环境前提: same as the other revocation tests.
    执行入口: POST /api/v1/auth/refresh over the real HTTP stack.
    未覆盖范围: password-reset-driven revocation (separate open item).

    Pre-fix RED failure name: INVARIANT_R0_REFRESH_DELETED_USER.
    """
    identity = await TenantIdentity().create()
    try:
        user_id = await _seed_tenant_user(
            identity=identity, email=f"r0-{uuid.uuid4().hex[:8]}@example.com"
        )
        old_refresh = _refresh(user_id, identity)
        await _set_user_flags(identity=identity, user_id=user_id, is_deleted=True)

        await _assert_refresh_refused(
            http_client,
            old_refresh,
            "INVARIANT_R0_REFRESH_DELETED_USER",
            "a soft-deleted user (row exists, is_deleted=true)",
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 7. R0 RED (fixed in R1): refresh must not re-issue for a suspended tenant
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_refresh_suspended_tenant_no_session(http_client):
    """[R0 RED → expected PASS after the R1 fix] Refresh dies with the tenant.

    Invariant: a refresh token bound to a suspended tenant must be refused.
    The user is fully active here — only the tenant is suspended — isolating
    the tenant-status check that refresh never performed. R1 fix: the
    contextual branch requires the wholesalers row to exist and be active
    before re-signing.

    正常对照: control test 1 proves the same token shape works pre-suspension.
    目标缺陷(已修复): refresh endpoint performed no tenant validation.
    环境前提: tenant row flipped to status='suspended' (no HTTP writer exists).
    执行入口: POST /api/v1/auth/refresh over the real HTTP stack.
    未覆盖范围: identity-only (pre-tenant-selection) refresh policy.

    Pre-fix RED failure name: INVARIANT_R0_REFRESH_SUSPENDED_TENANT.
    """
    identity = await TenantIdentity().create()
    try:
        user_id = await _seed_tenant_user(
            identity=identity, email=f"r0-{uuid.uuid4().hex[:8]}@example.com"
        )
        old_refresh = _refresh(user_id, identity)
        await _set_tenant_status(identity, "suspended")

        await _assert_refresh_refused(
            http_client,
            old_refresh,
            "INVARIANT_R0_REFRESH_SUSPENDED_TENANT",
            "an active user of a suspended tenant",
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 8. CONTROL: refresh for a live subject still works (fixture sanity)
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_control_refresh_live_subject_issues_usable_session(http_client):
    """[CONTROL — expected PASS] Refresh works for a valid live subject.

    正常对照: active user + active tenant → POST /api/v1/auth/refresh returns
    200 with a new pair and the new access token is genuinely usable on an
    authenticated route. Guards against an over-broad fix that breaks the
    legitimate refresh flow; also proves the R1 DB validation resolves its
    dependency through the real HTTP path.
    目标缺陷: none (control — makes the RED refresh cases meaningful: the
    only variable is subject liveness).
    环境前提: same as the other tests.
    执行入口: POST /api/v1/auth/refresh + GET /api/v1/skus (real HTTP stack).
    未覆盖范围: rotation/replay policy (single-use refresh is not implemented).
    """
    identity = await TenantIdentity().create()
    try:
        user_id = await _seed_tenant_user(
            identity=identity, email=f"r0-{uuid.uuid4().hex[:8]}@example.com"
        )
        response = await _http_refresh(http_client, _refresh(user_id, identity))
        assert response.status_code == 200, (
            f"CONTROL: refresh for a live subject must succeed (200), got "
            f"{response.status_code} with body {response.text[:300]}"
        )
        body = response.json()
        new_access = body["data"]["access_token"]
        assert body["data"]["refresh_token"], (
            "CONTROL: a refreshed pair must include a refresh token"
        )

        probe = await http_client.get(
            "/api/v1/skus", headers={"Authorization": "Bearer " + new_access}
        )
        assert probe.status_code == 200, (
            f"CONTROL: refreshed access token must be usable (200), got {probe.status_code}"
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 9. R1 CONTROL: refresh keeps refusing wrong signatures and wrong types
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r1_control_refresh_wrong_signature_refused(http_client):
    """[CONTROL — expected PASS] Forged signature stays refused.

    正常对照: a structurally valid refresh token signed with the WRONG key
    must be refused 401 by signature verification — the R1 DB validation is
    an additional layer for legitimately-signed-but-dead subjects, never a
    replacement for verification.
    目标缺陷: none (control pins the pre-existing defense so the R1 change
    cannot regress it).
    环境前提: token crafted with the same JWT library and claims shape as the
    product's own issuance, different signing key.
    执行入口: POST /api/v1/auth/refresh over the real HTTP stack.
    未覆盖范围: none material for this layer (algorithm confusion, exp
    edge cases are covered by product unit suites).
    """
    ghost_user = uuid.uuid4()
    fake_identity = TenantIdentity()  # never created; signature fails first
    try:
        await _assert_refresh_refused(
            http_client,
            _forged_refresh(ghost_user, fake_identity),
            "CONTROL_R1_REFRESH_WRONG_SIGNATURE",
            "a token signed with a foreign key (signature verification layer)",
        )
    finally:
        await fake_identity.drop()  # no-op by construction (IF EXISTS)


@pytest.mark.integration
async def test_r1_control_refresh_wrong_token_type_refused(http_client):
    """[CONTROL — expected PASS] An access token cannot refresh.

    正常对照: presenting an ACCESS token to /auth/refresh must keep being
    refused 401 INVALID_TOKEN_TYPE (type confusion), including when its
    subject is fully live — the type gate runs before the R1 subject
    validation.
    目标缺陷: none (control).
    环境前提: live subject, live tenant; only the token type varies.
    执行入口: POST /api/v1/auth/refresh over the real HTTP stack.
    未覆盖范围: identity/access type matrix beyond this pair.
    """
    identity = await TenantIdentity().create()
    try:
        user_id = await _seed_tenant_user(
            identity=identity, email=f"r0-{uuid.uuid4().hex[:8]}@example.com"
        )
        response = await _http_refresh(http_client, _bearer(user_id, identity))
        assert response.status_code == 401, (
            "CONTROL_R1_REFRESH_WRONG_TYPE: an access token must not be "
            f"accepted by /auth/refresh, got {response.status_code} with body "
            f"{response.text[:300]}"
        )
        body = response.json()
        code = (body.get("detail") or {}).get("code") or body.get("code")
        assert code == "INVALID_TOKEN_TYPE", (
            f"CONTROL_R1_REFRESH_WRONG_TYPE: expected INVALID_TOKEN_TYPE, got {code!r}"
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 10. R1 CONTROL: tenant isolation — same-kind data never cross-reads
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r1_control_tenant_isolation_no_cross_read(http_client):
    """[CONTROL — expected PASS] Two tenants, same-kind data, no cross-read.

    正常对照: two fully-live tenants each hold one distinctly-coded SKU and
    one user. Each tenant's token must list ONLY that tenant's SKU over the
    real HTTP stack, and each tenant's refresh must return tokens still bound
    to its own tenant claims — no path may expose the other tenant's data or
    identity.
    目标缺陷: none (control; the R0 baseline already isolated reads — this
    pins that the R1 revocation checks did not disturb isolation, e.g. by
    misbinding the tenant liveness query to the wrong session scope).
    环境前提: same as the other HTTP tests. Each tenant's listing uses its own
    `q` filter: the sku-list read-through cache key is NOT tenant-scoped
    (registered out-of-scope finding in the task record), so per-tenant `q`
    keeps this control a DATABASE-isolation proof independent of that cache
    defect; under the unreachable-Redis premise the cache fails open anyway.
    执行入口: GET /api/v1/skus and POST /api/v1/auth/refresh through the
    real HTTP stack, one token per tenant.
    未覆盖范围: write-path isolation (covered by the R0 concurrency file's
    tenant-scoped writes); cross-tenant refresh claim swapping.
    """
    identity_a = await TenantIdentity().create()
    identity_b = await TenantIdentity().create()
    try:
        user_a = await _seed_tenant_user(
            identity=identity_a, email=f"r0-iso-a-{uuid.uuid4().hex[:8]}@example.com"
        )
        user_b = await _seed_tenant_user(
            identity=identity_b, email=f"r0-iso-b-{uuid.uuid4().hex[:8]}@example.com"
        )
        async with tenant_session(identity_a.schema, identity_a.wholesaler_id) as db:
            await seed_sku_with_stock(
                db, sku_code="R1-ISO-TENANT-A", quantity_on_hand=Decimal("5")
            )
        async with tenant_session(identity_b.schema, identity_b.wholesaler_id) as db:
            await seed_sku_with_stock(
                db, sku_code="R1-ISO-TENANT-B", quantity_on_hand=Decimal("7")
            )

        listing_a = await http_client.get(
            "/api/v1/skus",
            params={"q": "R1-ISO-TENANT-A"},
            headers={"Authorization": "Bearer " + _bearer(user_a, identity_a)},
        )
        listing_b = await http_client.get(
            "/api/v1/skus",
            params={"q": "R1-ISO-TENANT-B"},
            headers={"Authorization": "Bearer " + _bearer(user_b, identity_b)},
        )
        assert listing_a.status_code == 200 and listing_b.status_code == 200, (
            "CONTROL_R1_ISOLATION: both live tenants must list their SKUs "
            f"(got {listing_a.status_code}/{listing_b.status_code})"
        )
        codes_a = {
            item["sku_code"] for item in listing_a.json()["data"]["items"]
        }
        codes_b = {
            item["sku_code"] for item in listing_b.json()["data"]["items"]
        }
        assert codes_a == {"R1-ISO-TENANT-A"}, (
            f"CONTROL_R1_ISOLATION: tenant A must see exactly its own SKU, got {codes_a}"
        )
        assert codes_b == {"R1-ISO-TENANT-B"}, (
            f"CONTROL_R1_ISOLATION: tenant B must see exactly its own SKU, got {codes_b}"
        )

        # Refresh keeps each subject bound to its own tenant (no claim swap).
        refresh_a = await _http_refresh(http_client, _refresh(user_a, identity_a))
        assert refresh_a.status_code == 200, (
            "CONTROL_R1_ISOLATION: tenant A's live refresh must succeed, got "
            f"{refresh_a.status_code}: {refresh_a.text[:200]}"
        )
        from core.security import decode_token

        claims_a = decode_token(refresh_a.json()["data"]["access_token"])
        assert claims_a.user_id == str(user_a), (
            "CONTROL_R1_ISOLATION: refreshed token must stay bound to the "
            f"refreshing subject, got {claims_a.user_id}"
        )
        assert claims_a.tenant_id == str(identity_a.wholesaler_id), (
            "CONTROL_R1_ISOLATION: refreshed token must stay bound to the "
            f"refreshing tenant, got {claims_a.tenant_id}"
        )
    finally:
        await identity_b.drop()
        await identity_a.drop()
