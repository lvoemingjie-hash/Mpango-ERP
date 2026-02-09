"""
S7-2 + S7-3: BI Access Enforcement Layer — The Police & The Recorder.

Philosophy: "The Law (S7-1) defines what is allowed. The Police (S7-2)
enforces it at the HTTP boundary. The Recorder (S7-3) logs every decision."

This module provides the enforcement layer that bridges FastAPI's HTTP
protocol with the pure-logic policy engine (S7-1). It performs exactly
ONE job: translate policy decisions into HTTP responses (200/403),
and delegates audit persistence to BackgroundTasks (fire-and-forget).

🔒 Constraint S7-1-A (CTO Mandate, Frozen):
    PolicySubject.roles MUST originate from a backend-trusted authority.
    `get_policy_subject()` loads roles from the DB-resolved TenantContext.user,
    NEVER from JWT token claims directly.

🔒 Constraint S7-1-C (CTO Mandate, Frozen):
    ALL BI permission checks MUST use one of these two entry points:
        1. RequireBIPermission  — Declarative (Depends) for static URNs
        2. enforce_bi_access    — Imperative (function call) for dynamic URNs
    It is STRICTLY FORBIDDEN to call evaluate_policy() directly from
    business code. Only this module may invoke the policy engine.

🔒 Constraint S7-3-C3 (CTO Mandate, Frozen):
    - The policy decision is already final before audit runs.
    - Audit failure MUST NOT affect the original request result.
    - Audit failure MUST be observable (structured error log).

Components:
    get_policy_subject(request)  — The Trust Boundary. Builds PolicySubject
                                   from request context. ONLY legal constructor.
    RequireBIPermission(action, urn) — Declarative enforcement via Depends().
    enforce_bi_access(subject, action, urn) — Imperative enforcement for
                                              dynamic URNs resolved at runtime.

Design Decisions:
- Follows the same class-based Depends() pattern as RequirePermission (rbac.py).
- No new logic — all decisions delegated to evaluate_policy().
- Fail-safe: if subject or asset cannot be resolved, default DENY (403).
- Audit: _audit_hook enqueues write_audit_log via BackgroundTasks (fire-and-forget).

Boot Contract Compliance:
- New file in api/middleware/ (same location as rbac.py)
- No modification to frozen core/ files
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import BackgroundTasks, HTTPException, Request, status

from api.context import get_auth_context, get_tenant_context
from core.governance.models import BIAction, BIAsset
from core.governance.policy import (
    PolicySubject,
    PolicyResult,
    evaluate_policy,
    POLICY_TENANT_ISOLATION,
)
from services.audit_writer import write_audit_log

logger = logging.getLogger("mpango.bi_access")


# ============================================================================
# 1. The Trust Boundary — get_policy_subject()
# ============================================================================

def get_policy_subject(request: Request) -> PolicySubject:
    """
    Build a PolicySubject from the current HTTP request context.

    This is the ONLY legal way to construct a PolicySubject in the HTTP layer.

    🔒 Constraint S7-1-A: Roles are loaded from the DB-resolved user object
    (TenantContext.user.roles), NOT from JWT token claims.

    🔒 This function is the single Trust Boundary for BI access control.
    Both RequireBIPermission and enforce_bi_access() depend on it.

    Args:
        request: The current FastAPI Request object.

    Returns:
        PolicySubject with user_id, tenant_id, and DB-sourced roles.

    Raises:
        HTTPException 401: If auth context or tenant context is missing.
        HTTPException 403: If user has no roles (fail-safe).
    """
    try:
        auth_ctx = get_auth_context(request)
    except HTTPException:
        raise  # Re-raise 401 from auth context
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_CONTEXT_UNAVAILABLE",
                "message": "Authentication context could not be resolved",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        tenant_ctx = get_tenant_context(request)
    except HTTPException:
        raise  # Re-raise 401 from tenant context
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "TENANT_CONTEXT_UNAVAILABLE",
                "message": "Tenant context could not be resolved",
            },
        )

    # 🔒 S7-1-A: Extract roles from DB-loaded user object, NOT from token
    user = tenant_ctx.user
    role_names: frozenset[str] = frozenset(
        role.name for role in getattr(user, "roles", [])
    )

    return PolicySubject(
        user_id=auth_ctx.token.user_id,
        tenant_id=auth_ctx.token.tenant_id,
        roles=role_names,
    )


# ============================================================================
# 2. Declarative Enforcement — RequireBIPermission
# ============================================================================

class RequireBIPermission:
    """
    Declarative BI access enforcement via FastAPI Depends().

    Use this for routes where the asset URN is known at route definition time.
    For dynamic URNs (resolved from request body/path), use enforce_bi_access().

    🔒 Constraint S7-1-C: This is one of only two legal enforcement entry points.

    Usage (as dependency injection):

        @router.get("/kpi/summary")
        async def kpi_summary(
            _policy = Depends(RequireBIPermission(
                BIAction.VIEW,
                "urn:bi:dashboard:executive:executive_summary",
            )),
        ):
            ...

    Usage (as route-level dependency):

        @router.get(
            "/dashboards/sales",
            dependencies=[Depends(RequireBIPermission(
                BIAction.VIEW,
                "urn:bi:dashboard:sales:sales_trend",
            ))],
        )
        async def get_sales_dashboard():
            ...

    The dependency returns the PolicyResult on success, which can be
    captured for logging or audit purposes.
    """

    def __init__(
        self,
        action: BIAction,
        asset_urn: str,
    ):
        """
        Initialize the BI permission enforcer.

        Args:
            action: The BIAction being attempted (VIEW, INTERACT, EXPORT, MANAGE).
            asset_urn: The static URN string of the target asset.
        """
        self.action = action
        self.asset_urn = asset_urn

    async def __call__(
        self,
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> PolicyResult:
        """
        Enforce the BI access policy.

        Builds a PolicySubject from the request, evaluates the policy,
        and raises HTTP 403 if denied. Enqueues audit log write via
        BackgroundTasks (S7-3: fire-and-forget).

        Returns:
            PolicyResult on success (for audit trail capture).

        Raises:
            HTTPException 401: If authentication/tenant context is missing.
            HTTPException 403: If the policy denies access.
        """
        subject = get_policy_subject(request)
        return enforce_bi_access(
            subject, self.action, self.asset_urn,
            background_tasks=background_tasks,
        )


# ============================================================================
# 3. Imperative Enforcement — enforce_bi_access()
# ============================================================================

def enforce_bi_access(
    subject: PolicySubject,
    action: BIAction,
    asset_urn_or_obj: str | BIAsset,
    background_tasks: Optional[BackgroundTasks] = None,
) -> PolicyResult:
    """
    Imperatively enforce BI access policy. Raises HTTP 403 if denied.

    Use this for routes where the asset URN is dynamic (resolved from
    request body, path parameters, or runtime computation).

    🔒 Constraint S7-1-C: This is one of only two legal enforcement entry points.

    Args:
        subject: PolicySubject built by get_policy_subject().
        action: The BIAction being attempted.
        asset_urn_or_obj: URN string or BIAsset object.
        background_tasks: Optional FastAPI BackgroundTasks for audit logging.
                          When provided, audit writes are fire-and-forget.
                          When None (e.g., in tests), audit is skipped gracefully.

    Returns:
        PolicyResult on success (for audit trail capture).

    Raises:
        HTTPException 403: If the policy denies access.
        HTTPException 403: If the asset URN is invalid or unregistered (fail-safe).

    Example (dynamic URN from request body):

        @router.post("/reports/analyze")
        async def analyze(
            request: Request,
            body: SemanticQueryRequest,
            subject: PolicySubject = Depends(get_policy_subject),
            background_tasks: BackgroundTasks,
        ):
            urn = f"urn:bi:report:sales:adhoc_{body.view.value}_analysis"
            enforce_bi_access(subject, BIAction.INTERACT, urn,
                              background_tasks=background_tasks)
            # ... proceed with analysis ...
    """
    # --- Fail-safe: resolve asset, deny on failure ---
    try:
        result = evaluate_policy(subject, action, asset_urn_or_obj)
    except (ValueError, TypeError) as exc:
        # Asset URN invalid or unregistered — fail-safe DENY
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "BI_ACCESS_DENIED",
                "message": "Access denied: unable to resolve the requested resource",
            },
        ) from exc

    # S7-3: Audit Hook — fire-and-forget via BackgroundTasks
    _audit_hook(result, subject.tenant_id, background_tasks)

    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_build_denial_detail(result),
        )

    return result


# ============================================================================
# 4. Internal Helpers
# ============================================================================

def _build_denial_detail(result: PolicyResult) -> dict:
    """
    Build the HTTP 403 error detail from a PolicyResult.

    Security: We expose the policy_name and a sanitized reason,
    but NOT internal asset metadata or role details that could
    aid an attacker in privilege escalation.

    For tenant isolation violations, we use a generic message
    to avoid confirming the existence of cross-tenant assets.
    """
    if result.policy_name == POLICY_TENANT_ISOLATION:
        return {
            "code": "BI_ACCESS_DENIED",
            "message": "Access denied: resource not available in your scope",
        }

    return {
        "code": "BI_ACCESS_DENIED",
        "message": f"Access denied: insufficient permissions for '{result.action}' action",
        "policy": result.policy_name,
    }


def _audit_hook(
    result: PolicyResult,
    tenant_id: str,
    background_tasks: Optional[BackgroundTasks] = None,
) -> None:
    """
    S7-3: Enqueue audit log write via BackgroundTasks (fire-and-forget).

    🔒 Constraint S7-3-C3:
        - The policy decision is already final before this runs.
        - Audit failure MUST NOT affect the original request result.
        - Audit failure MUST be observable (structured error log).

    Args:
        result: The PolicyResult from evaluate_policy().
        tenant_id: The tenant_id from PolicySubject.
        background_tasks: FastAPI BackgroundTasks instance.
                          If None (e.g., unit tests), audit is skipped gracefully.
    """
    if background_tasks is None:
        return

    try:
        background_tasks.add_task(write_audit_log, result, tenant_id)
    except Exception as exc:
        # 🔒 S7-3-C3: Audit enqueue failure must be observable, not fatal
        logger.error(
            "audit_log_enqueue_failed",
            exc_info=exc,
            extra={
                "actor_id": result.subject_id,
                "tenant_id": tenant_id,
                "action": result.action,
                "asset_urn": result.asset_urn,
                "allowed": result.allowed,
            },
        )
