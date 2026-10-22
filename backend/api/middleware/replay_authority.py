"""Replay authority gate for idempotent cache hits (R2).

CTO-AUTH-MPANGO-CACHED-REPLAY-AUTHORITY-R1-20261010 (repair round 2 — CTO
review findings F1/F2/F3, 2026-10-10).

A cached idempotent response must never be served without the SAME live
authority the original request passed. This gate is the single decision
point for "may the cached body be served for THIS request right now?".

Disposition classes (R2, closing F1/F2):

1. REGISTERED SEAM — routes whose decisive authority lives OUTSIDE the RBAC
   dependency classes (credential/subject/object checks in their handlers)
   are listed in ``_REPLAY_SEAMS``. Each seam RE-EXECUTES the existing
   product validation for that route — imported from the product modules,
   never duplicated and never weakened — WITHOUT running the handler, so no
   token is minted and no business write occurs while deciding:
     - POST /api/v1/auth/select-tenant: the TARGET tenant's current user
       state (exists / not deleted / is_active) via the same CRUD the
       resolver uses (crud.user.get_user_with_permissions), plus the
       wholesaler lookup (crud.wholesaler.get_wholesaler_by_id).
     - POST /api/v1/auth/refresh: the presented refresh credential is
       decoded (core.security.decode_token) and the contextual subject is
       revalidated with the handler's own validator
       (api.v1.auth._validate_contextual_refresh_subject). Identity-only
       refresh stays claim-based — the product's own recorded boundary,
       identical to what a fresh request would do.
     - POST /api/v1/orders and PUT /api/v1/pricing/prices: the current S1
       services.order_creation_service.assert_binding, shared with both
       live handlers; no pre-S1 SQL or handler is restored.
     - POST /api/v1/client/orders: the existing client identity resolver
       derives the retailer from the current binding, followed by that
       same S1 binding guard. Body fields never determine client ownership.

2. RBAC-CAPTURED — routes whose declared dependencies include
   ``RequirePermission`` / ``RequirePlatformAdmin``: the live account/tenant
   chain (JwtAuthStrategy.authenticate + resolve_tenant_context, which reads
   the CURRENT user row and public.wholesalers state) runs, then the route's
   own dependency instances are executed.

3. FAIL-CLOSED DEFAULTS (F1: absence of recognized dependencies does NOT
   mean public):
     - unauthenticated caller on any route without a seam and without RBAC:
       the cache is served only when the route uses no authentication
       context at all AND is outside the /api/v1/auth/ credential namespace
       (genuinely anonymous, credential-in-body routes like the public
       registration/lookup endpoints);
     - authenticated caller on a route that uses an auth context but has no
       RBAC dependency and no seam: refuse (fall through to a fresh,
       fully-authoritative execution).

A refusal withholds the cached body and falls back to the real middleware/
route stack. On RBAC-captured routes that refusal is produced inside
FastAPI's dependency pipeline BEFORE the handler; on seam routes the fresh
outcome is the product's own live behavior (each registered seam's product
authority — including the unified select-tenant refusal — decides), so a
refused replay never sees the OLD body and performs no replay-side work.
Corrected per CTO review of 23af21f0: this is a cache-withholding +
fresh-outcome contract, not a universal handler-refusal guarantee.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from fastapi import Request
from starlette.routing import Match

__all__ = [
    "collect_route_authority_dependencies",
    "replay_currently_authorized",
]

_CREDENTIAL_NAMESPACE = "/api/v1/auth/"


def _match_route(request: Request):
    """Return the app route that handles this request, or None.

    Uses Starlette's own matcher so the decision is the router's decision,
    not a path-pattern re-implementation.
    """
    scope = {
        "type": request.scope.get("type", "http"),
        "method": request.method,
        "path": request.scope.get("path", ""),
        "root_path": request.scope.get("root_path", ""),
    }
    for route in request.app.routes:
        try:
            match, _child = route.matches(scope)
        except Exception:  # pragma: no cover - defensive: non-http routes
            continue
        if match == Match.FULL:
            return route
    return None


def collect_route_authority_dependencies(route) -> list:
    """Collect the route's declared RBAC authority dependency instances.

    Only the product's own authority dependency classes qualify. Sub-device
    dependencies (database sessions etc.) are NOT collected: running them is
    the route pipeline's job during the fall-through rejection path.
    """
    from api.middleware.rbac import RequirePermission, RequirePlatformAdmin, RequireOwner

    authority = []
    seen = set()

    def _consider(call) -> None:
        if isinstance(call, (RequirePermission, RequirePlatformAdmin, RequireOwner)):
            key = id(call)
            if key not in seen:
                seen.add(key)
                authority.append(call)

    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        for dep in getattr(dependant, "dependencies", []) or []:
            _consider(getattr(dep, "call", None))
    for dep in getattr(route, "dependencies", []) or []:
        _consider(getattr(dep, "call", None))
    return authority


def _route_uses_auth_context(route) -> bool:
    """True when the route's dependency chain reads the authentication
    context (e.g. api.dependencies.get_current_user_context)."""
    from api.context.auth import get_auth_context

    def _scan(dependant) -> bool:
        for dep in getattr(dependant, "dependencies", []) or []:
            call = getattr(dep, "call", None)
            if call is get_auth_context or getattr(call, "__name__", "") == "get_current_user_context":
                return True
            if _scan(getattr(dep, "dependant", None) or dep):
                return True
        return False

    if _scan(getattr(route, "dependant", None)):
        return True
    for dep in getattr(route, "dependencies", []) or []:
        call = getattr(dep, "call", None)
        if getattr(call, "__name__", "") == "get_current_user_context":
            return True
    return False


# ---------------------------------------------------------------------------
# Registered replay seams (F1/F2). Each reuses existing product validation.
# Signature: async f(request, body, token, tenant_ctx) -> bool
# ---------------------------------------------------------------------------

async def _seam_select_tenant(request, body, token, tenant_ctx) -> bool:
    """Re-validate the TARGET tenant's current user state exactly as the
    select-tenant contract requires, without issuing any token."""
    if not isinstance(body, dict) or not body.get("tenant_id") or token is None:
        return False
    from crud.wholesaler import get_wholesaler_by_id
    from crud.user import get_user_with_permissions
    from api.context.tenant import create_tenant_session
    from database.session import AsyncSessionLocal
    from db.tenant_filter import run_as_system

    # The wholesaler lookup is a cross-tenant read; it uses the product's own
    # system-scope mechanism (the same one the revoke route uses) so the ORM
    # tenant filter is satisfied without weakening it.
    with run_as_system(reason="replay_authority_select_tenant_lookup"):
        public = AsyncSessionLocal()
        try:
            wholesaler = await get_wholesaler_by_id(public, body["tenant_id"])
        finally:
            await public.close()
    if wholesaler is None:
        return False
    tenant_schema = wholesaler.get_tenant_schema()
    token_tmap = getattr(token, "tmap", None)
    if token.is_identity_only and token_tmap:
        local_user_id = token_tmap.get(str(wholesaler.id))
        if not local_user_id:
            return False
        effective_user_id = local_user_id
    else:
        effective_user_id = token.user_id
    session = await create_tenant_session(tenant_schema)
    try:
        user = await get_user_with_permissions(session, effective_user_id)
    finally:
        await session.close()
    return (
        user is not None
        and not bool(getattr(user, "is_deleted", False))
        and bool(getattr(user, "is_active", False))
    )


async def _seam_refresh(request, body, token, tenant_ctx) -> bool:
    """Re-validate the presented refresh credential and its CURRENT subject
    with the handler's own validator; no token is minted here. Identity-only
    refresh remains claim-based — the product's own recorded boundary."""
    if not isinstance(body, dict) or not body.get("refresh_token"):
        return False
    from core.security import decode_token

    try:
        payload = decode_token(body["refresh_token"])
    except Exception:
        return False
    if getattr(payload, "type", None) != "refresh":
        return False
    if payload.is_identity_only:
        return True
    from api.v1.auth import _validate_contextual_refresh_subject
    from database.session import get_db

    # get_db is the product's own public-session dependency (the same one the
    # refresh handler uses); it establishes the session identity the ORM
    # tenant filter requires.
    agen = get_db()
    session = await agen.__anext__()
    try:
        await _validate_contextual_refresh_subject(session, payload)
    except Exception:
        return False
    finally:
        await agen.aclose()
    return True


async def _seam_order_create(request, body, token, tenant_ctx) -> bool:
    """Re-run the current S1 create-order binding guard without writes."""
    if tenant_ctx is None or token is None or not isinstance(body, dict):
        return False
    from services.order_creation_service import assert_binding

    await assert_binding(tenant_ctx.session, token.tenant_id, body.get("retailer_id"))
    return True


async def _seam_client_order_create(request, body, token, tenant_ctx) -> bool:
    """Use the live client resolver, not a request-provided retailer id."""
    if tenant_ctx is None or token is None or not isinstance(body, dict):
        return False
    from api.v1.client.dependencies import resolve_client_identity
    from services.order_creation_service import assert_binding

    client = await resolve_client_identity(request)
    await assert_binding(tenant_ctx.session, client.tenant_id, client.retailer_id)
    return True


async def _seam_pricing_set(request, body, token, tenant_ctx) -> bool:
    """Re-run the pricing handler's current S1 binding guard."""
    if tenant_ctx is None or token is None or not isinstance(body, dict):
        return False
    from services.order_creation_service import assert_binding

    await assert_binding(tenant_ctx.session, token.tenant_id, body.get("retailer_id"))
    return True


_REPLAY_SEAMS: Dict[Tuple[str, str], Callable[..., Awaitable[bool]]] = {
    ("POST", "/api/v1/auth/select-tenant"): _seam_select_tenant,
    ("POST", "/api/v1/auth/refresh"): _seam_refresh,
    ("POST", "/api/v1/orders"): _seam_order_create,
    ("POST", "/api/v1/client/orders"): _seam_client_order_create,
    ("PUT", "/api/v1/pricing/prices"): _seam_pricing_set,
}


async def replay_currently_authorized(
    request: Request, body: Optional[Any] = None
) -> bool:
    """Decide whether a cached response may be served for this request.

    True  — the route's full authority (registered seam and/or RBAC
            dependencies over the live account/tenant state) accepts the
            CURRENT request.
    False — any authority refuses, or the disposition is fail-closed. The
            caller must withhold the cache and fall through to the real
            stack, which produces the authentic result with zero handler
            execution whenever the authority refuses.
    """
    route = _match_route(request)
    if route is None:
        return False

    authority = collect_route_authority_dependencies(route)
    seam = _REPLAY_SEAMS.get((request.method, request.scope.get("path", "")))
    uses_auth_context = _route_uses_auth_context(route)

    from api.context.auth import attach_auth_context
    from api.context.tenant import attach_tenant_context, clear_tenant_context

    strategy = getattr(request.app.state, "auth_strategy", None)
    if strategy is None:
        return False
    tenant_ctx = None
    try:
        try:
            auth_ctx = await strategy.authenticate(request)
        except Exception:
            auth_ctx = None

        if auth_ctx is None:
            # No recognizable principal. A seam route may still be decided
            # from its body credential (e.g. refresh); everything else is
            # served only when genuinely anonymous (no authority dependency,
            # no auth-context usage, outside the credential namespace).
            if seam is not None:
                try:
                    return bool(await seam(request, body, None, None))
                except Exception:
                    return False
            return (
                not authority
                and not uses_auth_context
                and not request.scope.get("path", "").startswith(_CREDENTIAL_NAMESPACE)
            )

        attach_auth_context(request, auth_ctx)
        token = auth_ctx.token
        try:
            tenant_ctx = await strategy.resolve_tenant_context(auth_ctx)
        except Exception:
            # Live account/tenant revocation — the replay is not authorized.
            return False
        if tenant_ctx is not None:
            attach_tenant_context(request, tenant_ctx)

        if seam is not None:
            try:
                if not await seam(request, body, token, tenant_ctx):
                    return False
            except Exception:
                return False

        for dep in authority:
            try:
                await dep(request)
            except Exception:
                return False

        # Auth-context-using routes without captured authority and without a
        # registered seam are fail-closed (F1): never serve from cache.
        if not authority and seam is None and uses_auth_context:
            return False
        return True
    finally:
        if tenant_ctx is not None:
            try:
                clear_tenant_context(request)
            except Exception:
                pass
            try:
                await tenant_ctx.session.close()
            except Exception:
                pass
