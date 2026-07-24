"""Client API dependencies — secure retailer identity resolution.

CTO P0 Mandate: retailer_id MUST be derived server-side from the authenticated
user's identity. It is NEVER accepted from request body or query parameters.

DC-12R1-S1 authoritative resolution (replaces the email lookup):
1. Require a contextual (non-identity-only) token with a tenant.
2. Require the retailer_operator role on the tenant user.
3. Resolve retailer_id via the authoritative mapping:
       token.user_id  ->  binding.tenant_user_id  ->  binding.retailer_id
   Email is NEVER used to infer retailer_id after authentication.
4. Require binding.wholesaler_id == token.tenant_id and status == 'active'.

This prevents:
- Cross-retailer order injection (user cannot forge retailer_id)
- Tenant boundary bypass (binding must exist in current tenant)
- Email-based identity confusion (resolution no longer keys on email)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import text

from api.context import get_auth_context, get_tenant_context
from core.security import TokenPayload


RETAILER_OPERATOR_ROLE = "retailer_operator"


@dataclass
class ClientIdentity:
    """Resolved client (retailer) identity for the current request."""

    user_id: str
    retailer_id: str
    tenant_id: str
    token: TokenPayload


async def resolve_client_identity(request: Request) -> ClientIdentity:
    """
    Resolve the authenticated retailer identity via the authoritative mapping.

    Raises HTTP 403 if:
    - Token is identity-only (no tenant context)
    - The tenant user lacks the retailer_operator role
    - No binding maps token.user_id (via tenant_user_id) for this tenant
    - The binding is not active
    """
    auth_ctx = get_auth_context(request)
    token = auth_ctx.token

    if token.is_identity_only:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_CONTEXT_REQUIRED",
                "message": "Please select a tenant first",
            },
        )

    tenant_ctx = get_tenant_context(request)
    user = tenant_ctx.user
    tenant_id = token.tenant_id
    user_id = token.user_id
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "NO_RETAILER_LINK", "message": "Unauthenticated"},
        )

    # Require the retailer_operator role on the tenant user.
    if not _has_retailer_operator_role(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "NOT_RETAILER_OPERATOR",
                "message": "This account is not a retailer operator",
            },
        )

    session = tenant_ctx.session

    # Authoritative resolution: token.user_id -> binding.tenant_user_id -> retailer_id.
    # No email lookup. Wholesaler match enforced in the same query.
    result = await session.execute(
        text(
            """
            SELECT retailer_id, status
            FROM public.wholesaler_retailer_bindings
            WHERE wholesaler_id = :tenant_id
              AND tenant_user_id = :user_id
              AND is_deleted IS FALSE
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "BINDING_NOT_FOUND",
                "message": "No retailer relationship mapped to this account",
            },
        )

    if row.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "BINDING_NOT_ACTIVE",
                "message": "No active relationship with this supplier",
            },
        )

    return ClientIdentity(
        user_id=user_id,
        retailer_id=str(row.retailer_id),
        tenant_id=tenant_id,
        token=token,
    )


def _has_retailer_operator_role(user) -> bool:
    """True if the tenant user carries the retailer_operator role.

    The user object is loaded by the tenant context with its roles relationship.
    Falls back gracefully if roles are not loaded.
    """
    roles = getattr(user, "roles", None)
    if not roles:
        return False
    try:
        return any(getattr(r, "name", None) == RETAILER_OPERATOR_ROLE for r in roles)
    except TypeError:
        return False
