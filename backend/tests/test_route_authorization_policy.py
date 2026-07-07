"""
S1: Route Authorization Policy Harness.

Establishes a route authorization policy contract that prevents any non-public
API route from lacking an explicit permission / authentication strategy.

Approach:
    This harness scans the live FastAPI application route table (not just
    text matching for RequirePermission) and classifies every /api/v1/**
    route into one of:

        public                 -- explicitly open (health probes, prometheus)
        authenticated          -- requires a valid JWT, no specific permission
        tenant_permission:<c>  -- Requires RequirePermission("<code>")
        platform_permission:<c>-- Requires platform-scoped permission (platform routes)
        internal_only          -- test/diagnostic endpoints gated to system:admin
        non_compliant          -- NO auth strategy detected (FAIL by contract)

    Any /api/v1/** route that is not classified into one of the first five
    categories AND is not on the explicit PUBLIC_ALLOWLIST is treated as a
    policy violation. The harness never silently relaxes checks; findings are
    recorded as xfail tests so they are visible and tracked, not hidden.

Task S1: test/contract-only harness - scans routes and classifies them.
Task S2: production fix - all 12 findings resolved (8 platform + 2 export + 2 profiling).
         xfail markers for fixed routes removed; master gate now passes green.
Task S2-R1: platform super-admin boundary fix - replaced RequirePermission("system:admin")
         on all 8 platform routes with RequirePlatformAdmin() which requires an
         identity-only super admin token, closing the gap where contextual tenant
         admins with system:admin could access cross-tenant platform data.
Task S2-R2: strict identity context fix - RequirePlatformAdmin now uses explicit
         AND checks (tenant_id is None AND tenant_schema is None) instead of
         TokenPayload.is_identity_only (OR semantics), rejecting partial-context
         tokens that could bypass the platform gate.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Environment bootstrap (must run before importing api.app).
#
# IMPORTANT: The project-root .env sets MPANGO_ENV=production, which
# tests/conftest.py loads via os.environ.setdefault BEFORE this module runs.
# That means a plain setdefault here is a no-op. We must HARD-SET MPANGO_ENV
# to "test" so that api.app.create_app() registers the /api/v1/test/**
# diagnostic routes (gated by `if settings.MPANGO_ENV != "production"`).
# We also clear the get_settings() lru_cache so any cached Settings instance
# built with MPANGO_ENV=production is discarded before the app is built.
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")  # pragma: allowlist secret
os.environ.setdefault(
    "SECRET_KEY",
    hashlib.sha256(b"mpango-test-runner-key-not-for-production").hexdigest(),  # pragma: allowlist secret
)
os.environ["MPANGO_ENV"] = "test"  # HARD-SET: override .env=production loaded by conftest
os.environ.setdefault(
    "REPORTING_DATABASE_URL",
    "postgresql://reporting_user:test@localhost:5432/mpango_erp",  # pragma: allowlist secret
)
os.environ.setdefault("REPORTING_USER_PASSWORD", "test")  # pragma: allowlist secret

# Clear any cached Settings instance that may have been built with the
# .env-sourced MPANGO_ENV=production before this module forced it to "test".
try:
    from core.config import get_settings as _get_settings
    _get_settings.cache_clear()
except Exception:
    pass

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute, APIRouter
from starlette.requests import Request as StarletteRequest

from api.app import app
from api.dependencies import get_current_user_context
from api.middleware.rbac import RequirePermission, RequirePlatformAdmin
from core.security import TokenPayload


# ===========================================================================
# Policy Classification Engine
# ===========================================================================

# Functions/callables that constitute an authentication strategy when present
# in a route's dependency tree. Presence of any of these means the route is
# NOT "non_compliant" (it requires some form of auth).
AUTH_DEPENDENCY_NAMES: Set[str] = {
    "RequirePermission",       # api.middleware.rbac.RequirePermission
    "RequirePlatformAdmin",    # api.middleware.rbac.RequirePlatformAdmin (S2-R1)
    "RequireBIPermission",     # api.middleware.bi_access.RequireBIPermission
    "RequireAnyIntakePermission",  # api.v1.intake.RequireAnyIntakePermission
    "RequireAllPermissions",   # api.v1.intake.RequireAllPermissions
    "get_current_user_context",  # api.dependencies (validates JWT)
    "resolve_client_identity",   # api.v1.client.dependencies (JWT + retailer binding)
    "get_policy_subject",        # api.middleware.bi_access (JWT + tenant context)
}

# DB-only dependencies that do NOT constitute an auth strategy. Their presence
# without an auth dependency means the route is non_compliant.
NON_AUTH_DEPENDENCY_NAMES: Set[str] = {
    "get_db",
    "get_db_session",
    "get_tenant_db_session",
    "get_job_queue",
    "get_reporting_session",
}

# Permission codes that grant platform-level access. Any route under
# /api/v1/platform/** MUST carry one of these (or be on the public allowlist
# for the platform health probe only).
PLATFORM_PERMISSION_PREFIXES: Tuple[str, ...] = (
    "platform:",
    "system:",
)

# Explicit, minimal allowlist of genuinely-public /api/v1/** routes.
# These are pre-auth endpoints that either exchange credentials for tokens or
# perform self-service operations that are intentionally open.
# Adding to this list requires CTO sign-off -- it is the ONLY escape hatch.
#
# - /api/v1/auth/login          : credentials exchanged for tokens (pre-auth)
# - /api/v1/auth/signup         : public tenant registration front-door skeleton
# - /api/v1/auth/verify-email   : public email verification token exchange
# - /api/v1/auth/onboarding/status : public onboarding status token exchange
# - /api/v1/auth/refresh        : refresh token in body (pre-auth, validates internally)
# - /api/v1/invitations/{code}  : pre-auth invitation code validation (retailer signup flow)
# - /api/v1/retailers/register  : pre-auth retailer self-registration via invitation code
#
# NOTE: NO platform, export, or business data routes are on this list.
PUBLIC_ALLOWLIST: Set[str] = {
    "/api/v1/auth/login",
    "/api/v1/auth/signup",
    "/api/v1/auth/verify-email",
    "/api/v1/auth/onboarding/status",
    "/api/v1/auth/refresh",
    "/api/v1/invitations/{code}",
    "/api/v1/retailers/register",
}

# Internal-only test/diagnostic endpoints. These MUST still be gated by
# system:admin permission (checked separately). Listed here so the harness
# classifies them as internal_only rather than non_compliant.
INTERNAL_PATH_PREFIXES: Tuple[str, ...] = (
    "/api/v1/test/",
)


@dataclass
class RouteClassification:
    """The classified policy verdict for a single route."""

    method: str
    path: str
    policy: str  # one of: public, authenticated, tenant_permission:*,
    #             platform_permission:*, internal_only, non_compliant
    permission_code: Optional[str] = None
    detected_auth_deps: List[str] = field(default_factory=list)
    detected_non_auth_deps: List[str] = field(default_factory=list)
    source_file: Optional[str] = None

    @property
    def is_compliant(self) -> bool:
        return self.policy != "non_compliant"

    def __str__(self) -> str:
        code = f" [{self.permission_code}]" if self.permission_code else ""
        return f"{self.method:7} {self.path:55} -> {self.policy}{code}"


def _collect_all_dependencies(route: APIRoute) -> List[Any]:
    """
    Recursively collect all dependency callables from a route's dependant tree.

    FastAPI builds a Dependant tree; each node has `.call` (the dependency
    callable) and `.dependencies` (nested dependants). We walk the whole tree.
    """
    seen: Set[int] = set()
    result: List[Any] = []

    def _walk(dependant: Any) -> None:
        if dependant is None:
            return
        for sub in getattr(dependant, "dependencies", []) or []:
            obj_id = id(sub)
            if obj_id in seen:
                continue
            seen.add(obj_id)
            if sub.call is not None:
                result.append(sub.call)
            _walk(sub)

    _walk(getattr(route, "dependant", None))
    return result


def _dependency_name(dep: Any) -> str:
    """
    Return the canonical name of a dependency callable.

    - Class instances used as Depends (RequirePermission, RequireBIPermission):
      use the class name via type(dep).__name__.
    - Plain functions (get_current_user_context, resolve_client_identity, etc.):
      use the function's __name__ attribute. type(func).__name__ would return
      "function" for all of them, which is useless for classification.
    - functools.partial / lambdas: fall back to func.__name__ if present.
    """
    # Plain function or lambda: use __name__ (e.g. "get_current_user_context")
    func_name = getattr(dep, "__name__", None)
    if func_name and func_name != "<lambda>":
        return func_name
    # partial objects expose .func
    inner = getattr(dep, "func", None)
    if inner is not None and hasattr(inner, "__name__"):
        return inner.__name__
    # Class instance (RequirePermission etc.)
    return type(dep).__name__


def _extract_permission_code(dep: Any) -> Optional[str]:
    """Extract a representative permission code from RBAC dependency instances."""
    # RequirePermission stores the code on .permission
    permission = getattr(dep, "permission", None)
    if permission:
        return str(permission)
    # RequireAnyIntakePermission/RequireAllPermissions store a set on .permissions.
    permissions = getattr(dep, "permissions", None)
    if permissions:
        return sorted(str(value) for value in permissions)[0]
    # RequireBIPermission stores action + asset_urn (no simple code)
    action = getattr(dep, "action", None)
    asset_urn = getattr(dep, "asset_urn", None)
    if action is not None:
        urn_suffix = asset_urn.split(":")[-1] if asset_urn else "unknown"
        return f"bi:{action}:{urn_suffix}"
    return None


def classify_route(route: APIRoute) -> RouteClassification:
    """
    Classify a single FastAPI route into a policy category.

    Classification logic (in priority order):
      1. PUBLIC_ALLOWLIST        -> public
      2. INTERNAL_PATH_PREFIXES  -> internal_only (permission checked separately)
      3. RequirePermission with platform/system code -> platform_permission
      4. RBAC permission dependency                 -> tenant_permission
      5. get_current_user_context / resolve_client_identity / get_policy_subject
                                                   -> authenticated
      6. No auth dependency detected -> non_compliant
    """
    methods = sorted(getattr(route, "methods", set()) or set())
    method = ",".join(methods) if methods else "?"
    path = route.path

    deps = _collect_all_dependencies(route)
    auth_deps: List[str] = []
    non_auth_deps: List[str] = []
    permission_code: Optional[str] = None
    found_require_permission = False

    for dep in deps:
        name = _dependency_name(dep)
        if name in AUTH_DEPENDENCY_NAMES:
            auth_deps.append(name)
            if name in (
                "RequirePermission",
                "RequirePlatformAdmin",
                "RequireBIPermission",
                "RequireAnyIntakePermission",
                "RequireAllPermissions",
            ):
                found_require_permission = True
                code = _extract_permission_code(dep)
                if code and permission_code is None:
                    permission_code = code
        elif name in NON_AUTH_DEPENDENCY_NAMES:
            non_auth_deps.append(name)
        else:
            # Unknown dependency -- treat as non-auth unless its name suggests auth.
            non_auth_deps.append(name)

    # Determine source file for the endpoint (for findings report).
    endpoint = getattr(route, "endpoint", None)
    source_file = None
    if endpoint and hasattr(endpoint, "__module__"):
        source_file = endpoint.__module__

    # --- Classification (priority order) ---
    if path in PUBLIC_ALLOWLIST:
        policy = "public"
    elif any(path.startswith(p) for p in INTERNAL_PATH_PREFIXES):
        policy = "internal_only"
    elif found_require_permission and permission_code:
        if any(
            permission_code.startswith(prefix)
            for prefix in PLATFORM_PERMISSION_PREFIXES
        ):
            policy = f"platform_permission"
        else:
            policy = "tenant_permission"
    elif auth_deps:
        # Has auth dep but no RequirePermission (e.g. get_current_user_context)
        policy = "authenticated"
        permission_code = None
    else:
        policy = "non_compliant"

    return RouteClassification(
        method=method,
        path=path,
        policy=policy,
        permission_code=permission_code,
        detected_auth_deps=auth_deps,
        detected_non_auth_deps=non_auth_deps,
        source_file=source_file,
    )


def scan_all_routes() -> List[RouteClassification]:
    """Scan the FastAPI app route table and classify every /api/v1/** route."""
    classifications: List[RouteClassification] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1/"):
            continue
        classifications.append(classify_route(route))
    # Stable sort: by path then method
    classifications.sort(key=lambda c: (c.path, c.method))
    return classifications


# ===========================================================================
# Computed Findings (evaluated once at module import)
# ===========================================================================

ALL_CLASSIFICATIONS: List[RouteClassification] = scan_all_routes()

NON_COMPLIANT_ROUTES: List[RouteClassification] = [
    c for c in ALL_CLASSIFICATIONS if c.policy == "non_compliant"
]

PLATFORM_ROUTES: List[RouteClassification] = [
    c for c in ALL_CLASSIFICATIONS if c.path.startswith("/api/v1/platform/")
]

PLATFORM_NON_COMPLIANT: List[RouteClassification] = [
    c for c in PLATFORM_ROUTES if not c.is_compliant
]

EXPORT_ROUTES: List[RouteClassification] = [
    c for c in ALL_CLASSIFICATIONS if c.path.startswith("/api/v1/exports")
]

EXPORT_NON_COMPLIANT: List[RouteClassification] = [
    c for c in EXPORT_ROUTES if not c.is_compliant
]

INTERNAL_ROUTES: List[RouteClassification] = [
    c for c in ALL_CLASSIFICATIONS
    if any(c.path.startswith(p) for p in INTERNAL_PATH_PREFIXES)
]


# ===========================================================================
# Test Suite
# ===========================================================================

class TestHarnessIntegrity:
    """Tests that verify the harness itself is wired correctly."""

    def test_harness_scans_all_api_v1_routes(self):
        """The harness must discover and classify all /api/v1/** routes."""
        assert len(ALL_CLASSIFICATIONS) > 0, "Harness found zero /api/v1/ routes"
        # Every classification must have a non-empty policy
        for c in ALL_CLASSIFICATIONS:
            assert c.policy, f"Route {c.path} has empty policy"

    def test_no_route_is_unclassified(self):
        """Every route must receive a policy verdict (never 'unknown')."""
        for c in ALL_CLASSIFICATIONS:
            assert c.policy != "", f"Route {c.method} {c.path} has no policy"

    def test_harness_detects_auth_dependencies_correctly(self):
        """
        The harness MUST correctly detect auth dependencies in a route's
        dependency tree (not just RequirePermission text).

        S2 fixed all 12 previously-non-compliant routes by adding explicit
        auth dependencies. This test verifies the harness detects those
        deps, proving it scans the FastAPI dependant tree correctly.
        """
        # Platform routes now use RequirePlatformAdmin (S2-R1)
        for c in PLATFORM_ROUTES:
            assert c.detected_auth_deps, (
                f"Platform route {c.path} has no detected auth deps. "
                f"The harness may be broken."
            )
        # Export status/download routes now have get_current_user_context
        export_get_routes = [
            c for c in EXPORT_ROUTES if "GET" in c.method
        ]
        for c in export_get_routes:
            assert c.detected_auth_deps, (
                f"Export route {c.path} has no detected auth deps. "
                f"The harness may be broken."
            )

    def test_known_good_routes_are_classified_correctly(self):
        """Spot-check that routes known to use RequirePermission are classified."""
        users_routes = [c for c in ALL_CLASSIFICATIONS if c.path == "/api/v1/users"]
        assert len(users_routes) > 0, "Harness did not find /api/v1/users routes"
        for c in users_routes:
            assert c.policy == "tenant_permission", (
                f"{c.path} should be tenant_permission, got {c.policy}"
            )
            assert c.permission_code and c.permission_code.startswith("users:"), (
                f"{c.path} permission code should be users:*, got {c.permission_code}"
            )

    def test_classification_table_printable(self):
        """The full classification table must be printable for audit."""
        lines = [str(c) for c in ALL_CLASSIFICATIONS]
        # Join into one report (printed in test output on failure)
        report = "\n".join(lines)
        assert len(report) > 0


class TestRoutePolicyContract:
    """
    Strict policy contract tests.

    These tests assert the IDEAL state where all /api/v1/** routes comply.
    Currently, several routes are non-compliant (see findings). These are
    marked xfail to document the findings WITHOUT relaxing the harness.

    When a non-compliant route is fixed in production code, the corresponding
    xfail will become xpass (unexpected pass), signaling the finding is
    resolved and the marker should be removed.
    """

    def test_all_api_v1_routes_are_classified(self):
        """Every /api/v1/** route must be classified into a known policy."""
        valid_policies = {
            "public",
            "authenticated",
            "tenant_permission",
            "platform_permission",
            "internal_only",
        }
        for c in ALL_CLASSIFICATIONS:
            assert c.policy in valid_policies | {"non_compliant"}, (
                f"{c.method} {c.path} has unknown policy: {c.policy}"
            )

    def test_no_unclassified_business_routes(self):
        """
        No business route (non-platform, non-test, non-public-allowlist)
        may be non_compliant.

        This is the master gate. After S2 production fixes, all routes
        comply and this gate passes green. If any route regresses to
        non-compliant, the failure message lists every offending route.
        """
        if NON_COMPLIANT_ROUTES:
            findings = "\n".join(
                f"  - {c.method} {c.path}  (deps: {c.detected_non_auth_deps})"
                for c in NON_COMPLIANT_ROUTES
            )
            pytest.fail(
                f"{len(NON_COMPLIANT_ROUTES)} route(s) lack an explicit auth "
                f"strategy:\n{findings}\n\n"
                f"See ai-ledger/product-ai/2026-06-18_s1_route_authorization_"
                f"policy_harness.md for the findings inventory."
            )


class TestPlatformRoutePolicy:
    """
    Platform routes (/api/v1/platform/**) MUST require platform-level
    permission. S2 added RequirePermission("system:admin") to all 8 routes;
    S2-R1 upgraded them to RequirePlatformAdmin() for tighter boundary control.
    """

    def test_platform_routes_exist(self):
        """Confirm platform routes are registered (sanity check)."""
        assert len(PLATFORM_ROUTES) > 0, "No /api/v1/platform/** routes found"

    def test_all_platform_routes_require_platform_permission(self):
        """
        Every /api/v1/platform/** route MUST have platform_permission or
        platform_admin strategy.

        S2 RESOLVED (was: all 8 platform routes had NO auth at all):
          - GET  /api/v1/platform/health
          - GET  /api/v1/platform/info
          - GET  /api/v1/platform/tenants/
          - GET  /api/v1/platform/tenants/{wholesaler_id}
          - GET  /api/v1/platform/audit/
          - GET  /api/v1/platform/audit/summary
          - GET  /api/v1/platform/audit/{log_id}
          - GET  /api/v1/platform/stats/

        S2-R1: Routes upgraded from RequirePermission("system:admin") to
        RequirePlatformAdmin() - only identity-only super admin tokens are
        accepted, preventing contextual tenant admins with system:admin
        from accessing cross-tenant platform data.

        Impact: Any caller (including unauthenticated) can list ALL tenants,
        read provisioning logs, read audit logs, and view platform stats.
        """
        violations = [
            c for c in PLATFORM_ROUTES
            if c.policy not in ("platform_permission",)
        ]
        assert violations == [], (
            "Platform routes without platform_permission: "
            + ", ".join(c.path for c in violations)
        )

    def test_platform_routes_have_auth_dependency(self):
        """Platform routes must have at least one auth dependency, not just get_db."""
        no_auth = [
            c for c in PLATFORM_ROUTES
            if not c.detected_auth_deps
        ]
        assert no_auth == [], (
            "Platform routes with zero auth dependencies: "
            + ", ".join(c.path for c in no_auth)
        )


# ===========================================================================
# S2-R1: Platform Admin Boundary Tests
# ===========================================================================

class TestPlatformAdminBoundary:
    """
    S2-R1: Verify that RequirePlatformAdmin enforces the correct boundary.

    RequirePlatformAdmin is stricter than RequirePermission("system:admin"):
    - It requires ``token.is_identity_only == True`` (no tenant context)
    - It requires ``token.is_super_admin == True`` (carries super_admin role)
    - A contextual token (tenant selected) is ALWAYS rejected, even if the
      user is a super_admin - platform data must only be accessed from the
      platform scope.
    - A tenant admin whose tenant role grants ``system:admin`` is rejected
      because their token is contextual (has tenant_id/tenant_schema).

    S2-R2: Partial-context tokens (one field set, other None) are also rejected.
    The dependency uses strict AND checks (tenant_id is None AND tenant_schema
    is None), NOT TokenPayload.is_identity_only which uses OR semantics.
    """

    @staticmethod
    def _authed_request(token: TokenPayload) -> StarletteRequest:
        """Create a Request with a specific auth context attached."""
        from api.context.auth import AuthContext
        request = StarletteRequest({"type": "http", "headers": []})
        request.state.auth_context = AuthContext(token=token, raw_token="test-token")
        return request

    @staticmethod
    def _bare_request() -> StarletteRequest:
        """Create a Request with no auth context (simulates missing JWT)."""
        return StarletteRequest({"type": "http", "headers": []})

    @pytest.mark.asyncio
    async def test_identity_only_super_admin_allowed(self):
        """Identity-only super admin token -> access granted."""
        token = TokenPayload(user_id="sa-1", roles=["super_admin"])
        # is_identity_only=True (no tenant_id/tenant_schema), is_super_admin=True
        request = self._authed_request(token)

        rp = RequirePlatformAdmin()
        result = await rp(request)
        assert result.is_super_admin
        assert result.is_identity_only

    @pytest.mark.asyncio
    async def test_contextual_tenant_admin_rejected(self):
        """
        Contextual tenant admin with system:admin in their tenant role -> 403.

        This is the core S2-R1 fix: RequirePermission("system:admin") would
        have allowed this token (it checks tenant role permissions), but
        RequirePlatformAdmin rejects it because the token is NOT identity-only.
        """
        token = TokenPayload(
            user_id="admin-1",
            tenant_id="00000000-0000-0000-0000-000000000001",
            tenant_schema="t_abc123",
            roles=["admin"],  # system:admin would come from tenant role, not token
        )
        request = self._authed_request(token)

        rp = RequirePlatformAdmin()
        with pytest.raises(HTTPException) as exc:
            await rp(request)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "PLATFORM_ADMIN_REQUIRED"

    @pytest.mark.asyncio
    async def test_contextual_super_admin_rejected(self):
        """
        Contextual super admin (selected a tenant) -> 403.

        Even though the user IS a super_admin, their token carries tenant
        context. Platform endpoints must be accessed from identity-only scope.
        """
        token = TokenPayload(
            user_id="sa-1",
            tenant_id="00000000-0000-0000-0000-000000000001",
            tenant_schema="t_abc123",
            roles=["super_admin"],
        )
        # is_identity_only=False, is_super_admin=True
        request = self._authed_request(token)

        rp = RequirePlatformAdmin()
        with pytest.raises(HTTPException) as exc:
            await rp(request)
        assert exc.value.status_code == 403

    # --- S2-R2: Partial-context boundary tests ---

    @pytest.mark.asyncio
    async def test_partial_context_tenant_id_set_schema_none_rejected(self):
        """
        Token with tenant_id set but tenant_schema None + super_admin -> 403.

        S2-R2 finding: TokenPayload.is_identity_only uses OR semantics:
            tenant_id is None OR tenant_schema is None
        This token has tenant_schema=None, so is_identity_only returns True.
        Under S2-R1's implementation, this token would have been ALLOWED
        because the check was `token.is_identity_only and token.is_super_admin`.

        S2-R2 fix: RequirePlatformAdmin now checks explicitly:
            token.tenant_id is None AND token.tenant_schema is None
        This partial-context token is correctly rejected.
        """
        token = TokenPayload(
            user_id="sa-1",
            tenant_id="00000000-0000-0000-0000-000000000001",
            tenant_schema=None,  # partial: tenant_id set, schema missing
            roles=["super_admin"],
        )
        # Verify the token WOULD pass the old OR-based check
        assert token.is_identity_only is True  # OR: True OR False = True
        assert token.is_super_admin is True

        request = self._authed_request(token)

        rp = RequirePlatformAdmin()
        with pytest.raises(HTTPException) as exc:
            await rp(request)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "PLATFORM_ADMIN_REQUIRED"

    @pytest.mark.asyncio
    async def test_partial_context_tenant_id_none_schema_set_rejected(self):
        """
        Token with tenant_id None but tenant_schema set + super_admin -> 403.

        S2-R2 finding: Same OR-vs-AND gap as the previous test, but in the
        opposite direction. This token has tenant_id=None, so
        is_identity_only returns True via OR. Under S2-R1, it would pass.

        S2-R2 fix: Explicit AND check rejects this partial-context token.
        """
        token = TokenPayload(
            user_id="sa-1",
            tenant_id=None,  # partial: schema set, tenant_id missing
            tenant_schema="t_abc123",
            roles=["super_admin"],
        )
        # Verify the token WOULD pass the old OR-based check
        assert token.is_identity_only is True  # OR: True OR False = True
        assert token.is_super_admin is True

        request = self._authed_request(token)

        rp = RequirePlatformAdmin()
        with pytest.raises(HTTPException) as exc:
            await rp(request)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "PLATFORM_ADMIN_REQUIRED"

    @pytest.mark.asyncio
    async def test_regular_user_rejected(self):
        """Regular tenant user -> 403."""
        token = TokenPayload(
            user_id="user-1",
            tenant_id="00000000-0000-0000-0000-000000000001",
            tenant_schema="t_abc123",
            roles=["cashier"],
        )
        request = self._authed_request(token)

        rp = RequirePlatformAdmin()
        with pytest.raises(HTTPException) as exc:
            await rp(request)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self):
        """No auth context -> 401."""
        request = self._bare_request()

        rp = RequirePlatformAdmin()
        with pytest.raises(HTTPException) as exc:
            await rp(request)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_platform_routes_use_require_platform_admin(self):
        """All 8 platform routes MUST use RequirePlatformAdmin (not RequirePermission)."""
        for c in PLATFORM_ROUTES:
            assert "RequirePlatformAdmin" in c.detected_auth_deps, (
                f"Platform route {c.path} does NOT use RequirePlatformAdmin. "
                f"Detected auth deps: {c.detected_auth_deps}"
            )

    def test_platform_routes_reject_non_platform_admin_http(self):
        """
        HTTP GET /api/v1/platform/** with mock (non-super-admin) auth -> 403.

        In the test environment, MockAuthStrategy authenticates all requests
        with a contextual non-super-admin token (tenant_id=t_dev, roles=[]).
        RequirePlatformAdmin rejects this with 403 PLATFORM_ADMIN_REQUIRED.
        """
        from fastapi.testclient import TestClient

        client = TestClient(app, raise_server_exceptions=False)
        protected_paths = [
            "/api/v1/platform/health",
            "/api/v1/platform/info",
            "/api/v1/platform/tenants/",
            "/api/v1/platform/audit/summary",
            "/api/v1/platform/stats/",
        ]
        failures = []
        for path in protected_paths:
            resp = client.get(path)
            if resp.status_code not in (401, 403):
                failures.append(
                    f"{path} -> {resp.status_code} (expected 401/403)"
                )
        assert failures == [], (
            "Platform routes accessible by non-platform-admin:\n" + "\n".join(failures)
        )


class TestExportRoutePolicy:
    """
    Exports status/download routes (/api/v1/exports/{job_id} and
    /api/v1/exports/{job_id}/download). S2 fixed both by adding explicit
    Depends(get_current_user_context) alongside the body-level tenant check
    (defense in depth).
    """

    def test_export_create_has_permission(self):
        """POST /api/v1/exports MUST have RequirePermission (it does)."""
        create_routes = [
            c for c in EXPORT_ROUTES if "POST" in c.method
        ]
        assert len(create_routes) == 1
        assert create_routes[0].policy == "tenant_permission"
        assert create_routes[0].permission_code == "exports:create"

    def test_export_status_has_explicit_permission(self):
        """GET /api/v1/exports/{job_id} must have an explicit auth dependency."""
        status_routes = [
            c for c in EXPORT_ROUTES
            if "GET" in c.method and c.path == "/api/v1/exports/{job_id}"
        ]
        assert len(status_routes) == 1
        assert status_routes[0].is_compliant, (
            f"{status_routes[0].path} has no explicit auth dependency. "
            f"Detected deps: {status_routes[0].detected_non_auth_deps}"
        )

    def test_export_download_has_explicit_permission(self):
        """GET /api/v1/exports/{job_id}/download must have explicit auth."""
        download_routes = [
            c for c in EXPORT_ROUTES
            if "GET" in c.method and c.path == "/api/v1/exports/{job_id}/download"
        ]
        assert len(download_routes) == 1
        assert download_routes[0].is_compliant, (
            f"{download_routes[0].path} has no explicit auth dependency. "
            f"Detected deps: {download_routes[0].detected_non_auth_deps}"
        )

    def test_streaming_exports_have_permission(self):
        """GET /api/v1/orders/export and /api/v1/inventory/export have exports:create."""
        streaming = [
            c for c in ALL_CLASSIFICATIONS
            if c.path in ("/api/v1/orders/export", "/api/v1/inventory/export")
        ]
        assert len(streaming) == 2
        for c in streaming:
            assert c.policy == "tenant_permission", (
                f"{c.path} should be tenant_permission, got {c.policy}"
            )
            assert c.permission_code == "exports:create"


class TestOrderPaymentRoutePolicy:
    """Order payment writes must use the payment permission contract."""

    def test_order_pay_route_requires_payments_create(self):
        """POST /api/v1/orders/{order_id}/pay is the canonical payment write path."""
        pay_routes = [
            c for c in ALL_CLASSIFICATIONS
            if "POST" in c.method and c.path == "/api/v1/orders/{order_id}/pay"
        ]
        assert len(pay_routes) == 1

        route = pay_routes[0]
        assert route.policy == "tenant_permission"
        assert route.permission_code == "payments:create"
        assert route.permission_code != "orders:update"


class TestInternalRoutePolicy:
    """Internal/test endpoints (/api/v1/test/**) must be gated by system:admin."""

    def test_internal_routes_exist(self):
        """Confirm internal test routes are registered (sanity check)."""
        assert len(INTERNAL_ROUTES) > 0, "No /api/v1/test/** routes found"

    def test_all_internal_routes_require_system_admin(self):
        """All /api/v1/test/** routes must require system:admin permission."""
        no_admin = [
            c for c in INTERNAL_ROUTES
            if c.permission_code != "system:admin"
        ]
        assert no_admin == [], (
            "Internal routes without system:admin: "
            + ", ".join(c.path for c in no_admin)
        )


class TestPublicAllowlistIntegrity:
    """The public allowlist must remain minimal and explicit."""

    def test_public_allowlist_is_minimal(self):
        """The PUBLIC_ALLOWLIST must only contain pre-auth auth/registration routes."""
        assert PUBLIC_ALLOWLIST == {
            "/api/v1/auth/login",
            "/api/v1/auth/signup",
            "/api/v1/auth/verify-email",
            "/api/v1/auth/onboarding/status",
            "/api/v1/auth/refresh",
            "/api/v1/invitations/{code}",
            "/api/v1/retailers/register",
        }, (
            "PUBLIC_ALLOWLIST was modified. Any addition requires CTO sign-off. "
            "Current: " + str(PUBLIC_ALLOWLIST)
        )

    def test_no_platform_route_in_allowlist(self):
        """No platform route may be on the public allowlist."""
        for path in PUBLIC_ALLOWLIST:
            assert not path.startswith("/api/v1/platform/"), (
                f"Platform route {path} must NOT be in the public allowlist."
            )

    def test_allowlisted_routes_are_classified_public(self):
        """Routes on the allowlist must be classified as public."""
        for c in ALL_CLASSIFICATIONS:
            if c.path in PUBLIC_ALLOWLIST:
                assert c.policy == "public", (
                    f"{c.path} is in allowlist but classified as {c.policy}"
                )


class TestFindingsInventory:
    """
    Prints the complete findings inventory. This test always passes -- its
    purpose is to emit the classification table into the test output for the
    ledger. It documents what the harness found, run after run.
    """

    def test_print_full_classification_table(self, capsys):
        """Emit the full route classification table for audit/ledger."""
        lines = [
            "",
            "=" * 78,
            "S1 ROUTE AUTHORIZATION POLICY HARNESS -- CLASSIFICATION TABLE",
            "=" * 78,
            f"Total /api/v1/** routes scanned: {len(ALL_CLASSIFICATIONS)}",
            f"Compliant:                      {len(ALL_CLASSIFICATIONS) - len(NON_COMPLIANT_ROUTES)}",
            f"Non-compliant:                  {len(NON_COMPLIANT_ROUTES)}",
            "-" * 78,
        ]
        for c in ALL_CLASSIFICATIONS:
            code = f" [{c.permission_code}]" if c.permission_code else ""
            lines.append(f"{c.method:7} {c.path:55} {c.policy}{code}")
        lines.append("-" * 78)
        lines.append("NON-COMPLIANT FINDINGS (P0/P1/P2):")
        for c in NON_COMPLIANT_ROUTES:
            lines.append(
                f"  {c.method:7} {c.path:55} deps={c.detected_non_auth_deps}  "
                f"src={c.source_file}"
            )
        lines.append("=" * 78)

        report = "\n".join(lines)
        print(report)
        captured = capsys.readouterr()
        assert "CLASSIFICATION TABLE" in captured.out


# ===========================================================================
# S2 Smoke Tests: Auth Gate Verification
# ===========================================================================

class TestSmokeAuthGate:
    """
    S2 Smoke: Verify auth dependencies reject unauthenticated requests.

    Each test creates a bare Request with no auth_context attached to
    request.state, then invokes the dependency directly. The dependency
    MUST raise HTTPException(401) -- proving that without a valid JWT,
    the route handler body is never reached.

    Additionally, HTTP-level smoke tests verify the full middleware stack
    returns 401/403 for unauthenticated requests to previously-vulnerable
    routes.
    """

    @staticmethod
    def _bare_request() -> StarletteRequest:
        """Create a Request with no auth context (simulates missing JWT)."""
        return StarletteRequest({"type": "http", "headers": []})

    # --- Dependency-level smoke tests (guaranteed to work without DB) ---

    @pytest.mark.asyncio
    async def test_require_permission_system_admin_rejects_no_auth(self):
        """RequirePermission('system:admin') -> 401 without auth context."""
        rp = RequirePermission("system:admin")
        request = self._bare_request()
        with pytest.raises(HTTPException) as exc:
            await rp(request)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_permission_exports_create_rejects_no_auth(self):
        """RequirePermission('exports:create') -> 401 without auth context."""
        rp = RequirePermission("exports:create")
        request = self._bare_request()
        with pytest.raises(HTTPException) as exc:
            await rp(request)
        assert exc.value.status_code == 401

    def test_get_current_user_context_rejects_no_auth(self):
        """get_current_user_context -> 401 without auth context."""
        request = self._bare_request()
        with pytest.raises(HTTPException) as exc:
            get_current_user_context(request)
        assert exc.value.status_code == 401

    # --- HTTP-level smoke tests (verify full middleware stack) ---

    # NOTE: Platform HTTP smoke test moved to TestPlatformAdminBoundary
    # (test_platform_routes_reject_non_platform_admin_http) for S2-R1.

    def test_export_routes_reject_unauthenticated_http(self):
        """
        HTTP GET /api/v1/exports/{id} and /download must not return 200.

        NOTE: In the test environment, MockAuthStrategy (auth/strategies/mock.py)
        authenticates ALL requests regardless of Authorization header. This means
        the "unauthenticated -> 401" path cannot be exercised via TestClient here.
        The dependency-level test (test_get_current_user_context_rejects_no_auth)
        proves that get_current_user_context raises 401 without auth context.

        For this HTTP-level test, we verify the route is NOT wide-open: it must
        not return 200. In test env it returns 500 (DB unavailable after mock auth
        passes); in production (JwtAuthStrategy) it would return 401.
        """
        from fastapi.testclient import TestClient

        client = TestClient(app, raise_server_exceptions=False)
        protected_paths = [
            "/api/v1/exports/00000000-0000-0000-0000-000000000000",
            "/api/v1/exports/00000000-0000-0000-0000-000000000000/download",
        ]
        failures = []
        for path in protected_paths:
            resp = client.get(path)
            # 200 would mean the route is wide-open (no auth, no error)
            # Any other status proves the route requires auth/resources.
            if resp.status_code == 200:
                failures.append(
                    f"{path} -> 200 (route is wide-open!)"
                )
        assert failures == [], "Export routes are unexpectedly accessible:\n" + "\n".join(failures)
