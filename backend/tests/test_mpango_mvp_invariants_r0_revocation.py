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

R1-R1 evidence-closure round (branch
zcode/mpango-mvp-invariants-r1-r1-test-evidence-closure-2026-09-08, CTO
findings F1/F3 of 2026-09-08) — test-only changes, product bytes untouched:

- F1: the isolation control now uses IDENTICAL query parameters and the SAME
  SKU business code in both tenants; records are distinguished by id + a
  tenant-distinctive name, and ONE shared assertion
  (assert_listing_exactly_own_tenant — also fed broken shapes by the guards
  counterexamples) accepts only the caller's own record. The DB-isolation
  control states and enforces an explicit cache-isolation premise (evicting
  the tenant-shared skus_list cache entries between the two listings on the
  task-owned Redis). The cache-reachable same-key leak is a REGISTERED risk
  with its own bounded diagnostic node: it asserts the correct invariant and
  is expected NAMED RED when the cache is reachable, explicit SKIP when it
  is not.
- F3: the refresh negatives are decoupled — (a) a nonexistent user inside a
  REAL ACTIVE tenant must hit PRINCIPAL_NOT_FOUND (not the tenant branch);
  (b) a token whose claims are byte-identical to the issuer's but whose
  signature key differs must be refused at the signature layer, with a
  recording sentinel proving the subject DB query was never reached; (c) a
  bounded fault injected at exactly the subject SELECT (FastAPI
  dependency_override) must issue ZERO tokens (issuer call count 0) without
  forcing the service fault into a 401, while the same live subject still
  refreshes with the fault disarmed. Shared helpers
  assert_refresh_refused_with_code / assert_refresh_fault_carries_no_issuance
  give each refusal branch a specific-code + zero-token contract; guards
  counterexamples feed them masked codes, token-bearing bodies and
  issuer-invoking shapes to prove no masking.

External evidence (AI_REPORT_INBOX/external-architecture-2026-09-06):
- supplementary-probes.json: http_deleted_user_suspended_tenant_skus = 200
- counterexamples.json: suspended_tenant_context_resolved=true,
  soft_deleted_user_context_resolved=true,
  refresh_nonexistent_principal_issued=true

Environment premises:
- Task-exclusive disposable loopback PostgreSQL 16 (ownership guard enforced).
- MPANGO_ENV must not normalize to "test" (MockAuthStrategy would bypass the
  real JWT middleware); run with MPANGO_ENV=staging as the external lab did.
- REDIS_URL must point at a throwaway address so no existing Redis instance
  is touched: unreachable (focused premise) → read-through caches fail open;
  a reachable TASK-OWNED Redis (full-suite premise) is required only by the
  cache diagnostic node, which then reproduces the registered leak as a
  named RED.
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
from decimal import Decimal

import httpx
import pytest
from jose import jwt as jose_jwt
from sqlalchemy import text

from core.config import get_settings
from core.security import create_contextual_token, decode_token, hash_password

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


def _forged_refresh(valid_refresh_token: str) -> str:
    """A refresh token IDENTICAL to a legitimately issued one except for the
    signature key (F3.2 "only the signature changes").

    The claims are decoded from the real token itself and re-signed with a
    foreign key, so exp/roles/tenant claims are byte-for-byte the issuer's
    own — the ONLY variable is the signature. The endpoint must keep
    refusing it at the signature-verification layer; the subject/tenant DB
    validation must never become the only line of defense.
    """
    settings = get_settings()
    claims = jose_jwt.decode(
        valid_refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
    )
    return jose_jwt.encode(
        claims, "r1r1-wrong-signing-key-material-not-the-real-secret",
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
# R1-R1 shared assertion helpers (SINGLE implementations).
#
# The real HTTP tests below AND the guards-file semantic counterexamples call
# exactly these functions — there is no control-only copy of the logic.
# ---------------------------------------------------------------------------

def extract_refresh_error_code(body) -> str | None:
    """Extract the public error code from a refresh error response body.

    The product's DC-12R1-H2 handler serializes HTTPException into the flat
    ``{code, message, request_id}`` envelope; the tolerant lookup also accepts
    a nested ``{"detail": {"code": ...}}`` shape so the assertions do not
    depend on the envelope revision.
    """
    if not isinstance(body, dict):
        return None
    detail = body.get("detail")
    if isinstance(detail, dict) and detail.get("code"):
        return str(detail["code"])
    if isinstance(body.get("code"), str):
        return str(body["code"])
    return None


def assert_refresh_response_carries_no_tokens(response, *, label: str) -> None:
    """A refused or faulted refresh must not return any session material.

    Works for ANY status (401 refusals and non-401 service faults alike):
    wherever a ``data`` payload exists it must carry no access/refresh token.
    """
    try:
        body = response.json()
    except Exception:
        body = {}
    data = body.get("data") or {}
    assert not data.get("access_token") and not data.get("refresh_token"), (
        f"{label}: the response must not carry session material, got "
        f"status={response.status_code} body={str(body)[:300]}."
    )


def assert_refresh_refused_with_code(response, *, expected_code: str, label: str) -> None:
    """Shared decoupled-refusal assertion (F3): a target rejection branch is
    proven by ALL THREE facets together — (1) HTTP 401, (2) the SPECIFIC
    product error code, and (3) zero token material — so no other rejection
    condition can mask the branch under test (CTO F3: decoupled negatives).
    """
    assert response.status_code == 401, (
        f"{label}: expected HTTP 401 with code {expected_code!r}, got "
        f"{response.status_code} with body {response.text[:300]}."
    )
    body = response.json()
    code = extract_refresh_error_code(body)
    assert code == expected_code, (
        f"{label}: expected the {expected_code!r} rejection branch, got "
        f"code={code!r} (body {str(body)[:300]}). A different rejection "
        "condition must not mask the branch under test."
    )
    assert_refresh_response_carries_no_tokens(response, label=label)


def assert_refresh_fault_carries_no_issuance(response, *, issuer_calls: int, label: str) -> None:
    """Shared service-fault assertion (F3.3): when the subject database query
    faults, the token issuer must not have been invoked, the response must
    not look like a success, and no session material may be returned. The
    status is deliberately NOT forced to 401 — a service fault is not an
    authentication verdict.
    """
    assert issuer_calls == 0, (
        f"{label}: the token issuer must not be invoked once the subject "
        f"validation has faulted, got {issuer_calls} call(s)."
    )
    assert not 200 <= response.status_code < 300, (
        f"{label}: a faulted subject validation must not surface as a "
        f"success-looking {response.status_code}."
    )
    assert_refresh_response_carries_no_tokens(response, label=label)


def assert_listing_exactly_own_tenant(
    listing_body,
    *,
    own_sku_id: str,
    own_name_marker: str,
    shared_code: str,
    label: str,
    invariant: str = "CONTROL_R1_ISOLATION",
) -> None:
    """Shared tenant-isolation assertion over a real GET /api/v1/skus body.

    Both tenants hold a SKU with the SAME business code; this assertion
    accepts ONLY the caller's own record — exactly one item whose record id
    AND tenant-distinctive name both match — so any cross-tenant leakage
    (the other tenant's same-code row, or a mixed page) is rejected. It is
    the single implementation shared by the real HTTP isolation control, the
    cache diagnostic, and the guards negative controls.
    """
    data = listing_body.get("data") or {}
    items = data.get("items")
    assert items is not None, (
        f"{invariant}[{label}]: listing body has no items list "
        f"({str(listing_body)[:200]})."
    )
    ids = [str(item.get("id")) for item in items]
    assert ids == [own_sku_id], (
        f"{invariant}[{label}]: the listing must contain EXACTLY this "
        f"tenant's own record id {own_sku_id}, got {ids}. Another tenant's "
        "same-code record or a mixed result page must be rejected here — "
        "filtering by the tenant's own code must not be what hides a "
        "cross-tenant read."
    )
    item = items[0]
    assert item.get("sku_code") == shared_code, (
        f"{invariant}[{label}]: expected the shared business code "
        f"{shared_code!r}, got {item.get('sku_code')!r}."
    )
    assert item.get("name") == own_name_marker, (
        f"{invariant}[{label}]: expected this tenant's distinctive record "
        f"name {own_name_marker!r}, got {item.get('name')!r}."
    )


async def _sku_list_cache_reachable() -> bool:
    """Probe whether the sku-list read-through cache backend is reachable."""
    try:
        from core.cache import get_redis_client

        client = await get_redis_client()
        await client.ping()
        return True
    except Exception:
        return False


async def _evict_sku_list_cache_entries() -> str:
    """Evict tenant-shared `skus_list:*` entries on the task-owned Redis.

    Explicit premise enforcement for the DB-isolation control (CTO F1): the
    sku-list cache key has NO tenant dimension (registered out-of-scope
    finding), so with a reachable cache the second same-key listing could be
    served from the first tenant's cached page instead of the database.
    Evicting the entries between the two listings guarantees each listing
    executes the real JWT → tenant-resolution → SQL path; the product stack
    is untouched. With an unreachable cache this is a no-op (fail-open
    premise). Only the task-owned Redis instance is ever touched.
    """
    try:
        from core.cache import get_redis_client

        client = await get_redis_client()
        removed = 0
        async for key in client.scan_iter(match="skus_list:*", count=200):
            await client.delete(key)
            removed += 1
        return f"evicted={removed}"
    except Exception as exc:
        return f"cache-unreachable({type(exc).__name__})"


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
# 9. R1/R1-R1 CONTROLS: refresh keeps refusing wrong signatures and wrong
#    types; the signature rejection is DECOUPLED from every database branch
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r1_control_refresh_wrong_signature_refused(http_client, monkeypatch):
    """[CONTROL — expected PASS] Signature-only rejection, decoupled (F3.2).

    正常对照: a refresh token whose claims are byte-for-byte the issuer's own
    (decoded from the real token and re-signed with a foreign key — ONLY the
    signature differs) and whose tenant and subject are REAL and active must
    be refused 401 INVALID_REFRESH_TOKEN by signature verification.
    目标缺陷: none (control pins the pre-existing defense so the R1 DB
    validation can never substitute for verification).
    解耦证明 (F3.2): the contextual subject DB query is instrumented with a
    recording pass-through sentinel — it must NEVER be reached; combined with
    the INVALID_REFRESH_TOKEN code assertion this proves the rejection
    happened at the signature layer, not at a downstream database branch.
    The real token decoder and the real HTTP routing are used throughout
    (the sentinel only records; it never replaces decoding).
    环境前提: real tenant + real user exist; forged token carries their exact
    claims.
    执行入口: POST /api/v1/auth/refresh over the real HTTP stack.
    未覆盖范围: algorithm-confusion and exp edge cases (product unit suites).
    """
    import api.v1.auth as auth_routes

    identity = await TenantIdentity().create()
    try:
        user_id = await _seed_tenant_user(
            identity=identity, email=f"r1r1-{uuid.uuid4().hex[:8]}@example.com"
        )
        valid_refresh = _refresh(user_id, identity)
        forged = _forged_refresh(valid_refresh)
        assert forged != valid_refresh

        subject_query = {"reached": False}
        original_validate = auth_routes._validate_contextual_refresh_subject

        async def recording_validate(db, payload):  # noqa: ANN001
            subject_query["reached"] = True
            return await original_validate(db, payload)

        monkeypatch.setattr(
            auth_routes, "_validate_contextual_refresh_subject", recording_validate
        )

        response = await _http_refresh(http_client, forged)
        assert_refresh_refused_with_code(
            response,
            expected_code="INVALID_REFRESH_TOKEN",
            label="CONTROL_R1_REFRESH_WRONG_SIGNATURE[valid-subject]",
        )
        assert subject_query["reached"] is False, (
            "CONTROL_R1_REFRESH_WRONG_SIGNATURE: the contextual subject "
            "database query must not run for a token that fails signature "
            "verification — the signature layer must reject before any "
            "database branch is consulted."
        )
    finally:
        await identity.drop()


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
# 10. R1-R1 (CTO F1) CONTROLS: tenant isolation proven with IDENTICAL query
#     parameters and an IDENTICAL business code; the cache-reachable same-key
#     leak is a separate bounded diagnostic, never folded in here.
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r1_control_tenant_isolation_same_query_same_code_db_only(http_client):
    """[CONTROL — expected PASS] Same query params + same SKU code, distinct
    records: each listing contains EXACTLY the caller's own record.

    正常对照 (F1 redesign of the former different-codes/different-q control):
    two fully-live tenants each seed a SKU with the SAME business code but
    their own record id and a tenant-distinctive name. BOTH requests use the
    IDENTICAL query parameters. The shared assertion
    assert_listing_exactly_own_tenant (single implementation, also fed broken
    shapes by the guards negative controls) accepts only the caller's own
    record, so a cross-tenant read can no longer be hidden by per-tenant
    filtering or by comparing business codes alone.
    目标缺陷: none (control; pins that the R1 revocation checks did not
    disturb database-level tenant isolation).
    环境前提 (explicit cache-isolation premise): between the two listings the
    tenant-shared `skus_list:*` cache entries are evicted on the task-owned
    Redis (_evict_sku_list_cache_entries), so each listing executes the real
    JWT → tenant-resolution → SQL path independent of the registered
    non-tenant-scoped cache key. The cache-reachable same-key leak is a
    separate registered risk with its own bounded diagnostic node (expected
    named RED when the cache is reachable); it is deliberately NOT folded
    into this control.
    执行入口: GET /api/v1/skus (identical params, per-tenant tokens) and
    POST /api/v1/auth/refresh for BOTH tenants through the real HTTP stack.
    未覆盖边界: write-path isolation (covered by the R0 concurrency file's
    tenant-scoped writes); arbitrary claim-substitution tokens — tampering
    user_id/tenant_id inside a validly-signed token is a forgery scenario
    owned by the signature layer, not asserted here; cache-reachable
    same-key behaviour (separate diagnostic node).
    """
    identity_a = await TenantIdentity().create()
    identity_b = await TenantIdentity().create()
    try:
        user_a = await _seed_tenant_user(
            identity=identity_a, email=f"r1r1-iso-a-{uuid.uuid4().hex[:8]}@example.com"
        )
        user_b = await _seed_tenant_user(
            identity=identity_b, email=f"r1r1-iso-b-{uuid.uuid4().hex[:8]}@example.com"
        )
        shared_code = f"R1ISOSHARED{uuid.uuid4().hex[:8].upper()}"
        async with tenant_session(identity_a.schema, identity_a.wholesaler_id) as db:
            sku_id_a = await seed_sku_with_stock(
                db, sku_code=shared_code, quantity_on_hand=Decimal("5"),
                name="ISOLATION-MARKER-TENANT-A",
            )
        async with tenant_session(identity_b.schema, identity_b.wholesaler_id) as db:
            sku_id_b = await seed_sku_with_stock(
                db, sku_code=shared_code, quantity_on_hand=Decimal("7"),
                name="ISOLATION-MARKER-TENANT-B",
            )

        params = {"q": shared_code}  # IDENTICAL query parameters for both
        listing_a = await http_client.get(
            "/api/v1/skus", params=params,
            headers={"Authorization": "Bearer " + _bearer(user_a, identity_a)},
        )
        await _evict_sku_list_cache_entries()
        listing_b = await http_client.get(
            "/api/v1/skus", params=params,
            headers={"Authorization": "Bearer " + _bearer(user_b, identity_b)},
        )
        assert listing_a.status_code == 200 and listing_b.status_code == 200, (
            "CONTROL_R1_ISOLATION: both live tenants must list their SKUs "
            f"(got {listing_a.status_code}/{listing_b.status_code})"
        )
        assert_listing_exactly_own_tenant(
            listing_a.json(),
            own_sku_id=str(sku_id_a), own_name_marker="ISOLATION-MARKER-TENANT-A",
            shared_code=shared_code, label="tenant-A",
        )
        assert_listing_exactly_own_tenant(
            listing_b.json(),
            own_sku_id=str(sku_id_b), own_name_marker="ISOLATION-MARKER-TENANT-B",
            shared_code=shared_code, label="tenant-B",
        )

        # F1.5: BOTH tenants refresh; every identity claim must match the
        # refreshing tenant's own real identity (subject, tenant_id, schema).
        for identity, user_id, label in (
            (identity_a, user_a, "A"), (identity_b, user_b, "B"),
        ):
            refresh = await _http_refresh(http_client, _refresh(user_id, identity))
            assert refresh.status_code == 200, (
                f"CONTROL_R1_ISOLATION: tenant {label}'s live refresh must "
                f"succeed, got {refresh.status_code}: {refresh.text[:200]}"
            )
            claims = decode_token(refresh.json()["data"]["access_token"])
            assert claims.user_id == str(user_id), (
                f"CONTROL_R1_ISOLATION[{label}]: refreshed token must stay "
                f"bound to the refreshing subject, got {claims.user_id}"
            )
            assert claims.tenant_id == str(identity.wholesaler_id), (
                f"CONTROL_R1_ISOLATION[{label}]: refreshed token must stay "
                f"bound to the refreshing tenant, got {claims.tenant_id}"
            )
            assert claims.tenant_schema == identity.schema, (
                f"CONTROL_R1_ISOLATION[{label}]: refreshed token must stay "
                f"bound to the refreshing tenant schema, got {claims.tenant_schema}"
            )
    finally:
        await identity_b.drop()
        await identity_a.drop()


@pytest.mark.integration
async def test_r1_red_diagnostic_sku_list_cache_not_tenant_scoped(http_client):
    """[REGISTERED-RISK DIAGNOSTIC — expected NAMED RED when the sku-list
    cache is reachable; explicit SKIP when it is not] Identical query keys
    must not serve one tenant's cached page to another.

    正常对照: the same shared assertion as the DB-isolation control is used
    (invariant name overridden), so this diagnostic cannot pass on weaker
    terms than the control.
    登记风险 (registered, NOT authorized to fix): the sku-list read-through
    cache key (skus_list:{page}:{size}:{is_active}:{q}) has no tenant
    dimension. With a reachable cache, tenant B's listing under the SAME key
    as tenant A's can be served from A's cached page — a cross-tenant read
    that never touches the database. This node reproduces that shape once,
    in a bounded way (fresh tenants, a run-unique query token, no other
    cache traffic), and asserts the CORRECT invariant; today it therefore
    FAILS with INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED when the cache
    is reachable (the named RED), and PASSES only if the cache key ever
    becomes tenant-safe. When the cache is unreachable the premise is absent
    and the node SKIPs with an explicit reason (never counted as GREEN
    evidence either way). No cache implementation change is authorized.
    环境前提: reachable task-owned Redis for the RED shape; unreachable
    cache → skip (premise absent).
    执行入口: GET /api/v1/skus with identical params, two tenant tokens,
    real HTTP stack (cache hit path included).
    未覆盖范围: any cache namespace other than skus_list:*; write caches.
    """
    if not await _sku_list_cache_reachable():
        pytest.skip(
            "INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED: premise absent — "
            "the sku-list cache is unreachable (fail-open), so the "
            "cross-tenant same-key cache leak cannot be reproduced in this "
            "run. This diagnostic only means anything with a reachable cache."
        )
    identity_a = await TenantIdentity().create()
    identity_b = await TenantIdentity().create()
    try:
        user_a = await _seed_tenant_user(
            identity=identity_a, email=f"r1r1-cdiag-a-{uuid.uuid4().hex[:8]}@example.com"
        )
        user_b = await _seed_tenant_user(
            identity=identity_b, email=f"r1r1-cdiag-b-{uuid.uuid4().hex[:8]}@example.com"
        )
        shared_code = f"R1CACHEDIAG{uuid.uuid4().hex[:8].upper()}"
        async with tenant_session(identity_a.schema, identity_a.wholesaler_id) as db:
            sku_id_a = await seed_sku_with_stock(
                db, sku_code=shared_code, quantity_on_hand=Decimal("5"),
                name="CACHE-DIAG-MARKER-TENANT-A",
            )
        async with tenant_session(identity_b.schema, identity_b.wholesaler_id) as db:
            sku_id_b = await seed_sku_with_stock(
                db, sku_code=shared_code, quantity_on_hand=Decimal("7"),
                name="CACHE-DIAG-MARKER-TENANT-B",
            )

        params = {"q": shared_code}  # identical cache key for both tenants
        listing_a = await http_client.get(
            "/api/v1/skus", params=params,
            headers={"Authorization": "Bearer " + _bearer(user_a, identity_a)},
        )
        assert listing_a.status_code == 200, (
            f"cache diagnostic: tenant A listing must succeed, got {listing_a.status_code}"
        )
        assert_listing_exactly_own_tenant(
            listing_a.json(),
            own_sku_id=str(sku_id_a), own_name_marker="CACHE-DIAG-MARKER-TENANT-A",
            shared_code=shared_code, label="cache-diag-A",
            invariant="INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED",
        )
        # Same key, NO eviction: the registered risk shape.
        listing_b = await http_client.get(
            "/api/v1/skus", params=params,
            headers={"Authorization": "Bearer " + _bearer(user_b, identity_b)},
        )
        assert listing_b.status_code == 200, (
            f"cache diagnostic: tenant B listing must succeed, got {listing_b.status_code}"
        )
        assert_listing_exactly_own_tenant(
            listing_b.json(),
            own_sku_id=str(sku_id_b), own_name_marker="CACHE-DIAG-MARKER-TENANT-B",
            shared_code=shared_code, label="cache-diag-B",
            invariant="INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED",
        )
    finally:
        await identity_b.drop()
        await identity_a.drop()


# ---------------------------------------------------------------------------
# 11. R1-R1 (CTO F3) DECOUPLED refresh negatives: each rejection branch and
#     the fault path proven INDEPENDENTLY, over the real HTTP stack.
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r1_refresh_nonexistent_user_in_active_tenant_principal_branch(http_client):
    """[CONTROL — expected PASS] Ghost user inside a REAL ACTIVE tenant hits
    the PRINCIPAL_NOT_FOUND branch (F3.1 decoupling).

    正常对照: tenant and at least one real user exist and the tenant is
    active — only the subject varies (a user_id with no row). The refusal
    must come from the subject branch (PRINCIPAL_NOT_FOUND), NOT from the
    tenant branch (TENANT_NOT_FOUND) that masked this shape in the former
    combined ghost-tenant-and-user node.
    目标缺陷: none (control proving the R1 subject-existence branch is
    reachable on its own).
    环境前提: real active tenant via TenantIdentity; refresh token carries
    the real tenant claims and a nonexistent user id.
    执行入口: POST /api/v1/auth/refresh over the real HTTP stack.
    未覆盖范围: inactive-user branch (PRINCIPAL_INACTIVE) — the soft-deleted
    and deactivated paths are covered by the R0 RED nodes above.
    """
    identity = await TenantIdentity().create()
    try:
        await _seed_tenant_user(
            identity=identity, email=f"r1r1-ghost-{uuid.uuid4().hex[:8]}@example.com"
        )
        ghost_user = uuid.uuid4()
        response = await _http_refresh(http_client, _refresh(ghost_user, identity))
        assert_refresh_refused_with_code(
            response,
            expected_code="PRINCIPAL_NOT_FOUND",
            label="CONTROL_R1_REFRESH_GHOST_USER_IN_ACTIVE_TENANT",
        )
    finally:
        await identity.drop()


@pytest.mark.integration
async def test_r1_refresh_subject_db_fault_zero_issuance(http_client, monkeypatch):
    """[CONTROL — expected PASS] A bounded fault in the subject DB query
    issues NOTHING (F3.3), and a live subject still refreshes.

    正常对照: with the fault disarmed, the same live subject refreshes 200
    with a usable pair.
    目标缺陷: none (control proving the R1 validation fails closed on
    infrastructure faults: no session may be minted from a half-validated
    subject).
    环境前提: the fault is injected at exactly ONE boundary — the
    `{schema}.users` subject SELECT inside the real dependency-provided
    session — via app.dependency_overrides on get_db_session (FastAPI's own
    override mechanism; the route, its real routing and the real wholesaler
    lookup are untouched). The issuer (create_contextual_token) is wrapped
    with a counting pass-through. Both instruments are restored before the
    test ends and live only in this test's process.
    执行入口: POST /api/v1/auth/refresh over the real HTTP stack.
    未覆盖范围: faults in the wholesaler (tenant) lookup; timeout-class
    faults (a bounded immediate exception is used).
    """
    import api.v1.auth as auth_routes
    from api.dependencies import get_db_session
    from main import app as app_under_test

    identity = await TenantIdentity().create()
    try:
        user_id = await _seed_tenant_user(
            identity=identity, email=f"r1r1-fault-{uuid.uuid4().hex[:8]}@example.com"
        )
        fault = {"armed": True, "hits": 0}
        issuer_calls = {"count": 0}

        real_issuer = auth_routes.create_contextual_token

        def counting_issuer(*args, **kwargs):  # noqa: ANN001
            issuer_calls["count"] += 1
            return real_issuer(*args, **kwargs)

        monkeypatch.setattr(auth_routes, "create_contextual_token", counting_issuer)

        class _FaultingExecuteSession:
            """Delegating proxy: real session; only the subject SELECT faults."""

            def __init__(self, session):
                self._session = session

            def __getattr__(self, name):
                return getattr(self._session, name)

            async def execute(self, statement, *args, **kwargs):  # noqa: ANN001
                sql = str(statement)
                if ".users" in sql and "is_active" in sql:
                    fault["hits"] += 1
                    raise RuntimeError("r1r1 bounded subject-query fault")
                return await self._session.execute(statement, *args, **kwargs)

        async def faulting_db_session():
            async for session in get_db_session():
                if fault["armed"]:
                    yield _FaultingExecuteSession(session)
                else:
                    yield session

        app_under_test.dependency_overrides[get_db_session] = faulting_db_session
        try:
            response = await _http_refresh(http_client, _refresh(user_id, identity))
        finally:
            app_under_test.dependency_overrides.pop(get_db_session, None)

        assert fault["hits"] >= 1, (
            "CONTROL_R1_REFRESH_SUBJECT_DB_FAULT: harness fault — the bounded "
            "subject-query fault never fired, so a no-issuance verdict would "
            "be vacuous."
        )
        assert_refresh_fault_carries_no_issuance(
            response,
            issuer_calls=issuer_calls["count"],
            label="CONTROL_R1_REFRESH_SUBJECT_DB_FAULT",
        )

        # Control: the same live subject with the fault disarmed refreshes.
        response_ok = await _http_refresh(http_client, _refresh(user_id, identity))
        assert response_ok.status_code == 200, (
            "CONTROL_R1_REFRESH_SUBJECT_DB_FAULT: with the fault disarmed the "
            f"live subject must still refresh (200), got {response_ok.status_code}"
        )
        assert response_ok.json()["data"]["access_token"], (
            "CONTROL_R1_REFRESH_SUBJECT_DB_FAULT: the disarmed refresh must "
            "issue an access token"
        )
    finally:
        await identity.drop()
