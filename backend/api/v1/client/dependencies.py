"""Client API dependencies — secure retailer identity resolution.

CTO P0 Mandate: retailer_id MUST be derived server-side from the
authenticated user's identity. It is NEVER accepted from request body
or query parameters.

Resolution strategy:
1. Get authenticated user from tenant context (JWT → user_id → User)
2. Look up public.retailers by matching User.email → Retailer.email
3. Verify an active wholesaler_retailer_binding exists for this tenant
4. Return the verified retailer_id

This prevents:
- Cross-retailer order injection (user cannot forge retailer_id)
- Tenant boundary bypass (binding must exist in current tenant)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import text

from api.context import get_auth_context, get_tenant_context
from core.security import TokenPayload


@dataclass
class ClientIdentity:
    """Resolved client (retailer) identity for the current request."""
    user_id: str
    retailer_id: str
    tenant_id: str
    token: TokenPayload


async def resolve_client_identity(request: Request) -> ClientIdentity:
    """
    Resolve the authenticated retailer identity from JWT + DB lookup.

    Raises HTTP 403 if:
    - User has no linked retailer record
    - No active binding exists for this tenant
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

    # Resolve retailer_id from user email via public.retailers + binding
    session = tenant_ctx.session
    user_email = getattr(user, "email", None)
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "NO_RETAILER_LINK",
                "message": "User account has no email — cannot resolve retailer identity",
            },
        )

    # Step 1: Find retailer by email in public schema
    result = await session.execute(
        text(
            "SELECT id FROM public.retailers "
            "WHERE email = :email AND is_deleted IS NOT TRUE "
            "LIMIT 1"
        ),
        {"email": user_email},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "RETAILER_NOT_FOUND",
                "message": "No retailer profile linked to this account",
            },
        )

    retailer_id = str(row.id)

    # Step 2: Verify active binding between this retailer and the current tenant
    binding_result = await session.execute(
        text(
            "SELECT id FROM public.wholesaler_retailer_bindings "
            "WHERE wholesaler_id = :tenant_id "
            "  AND retailer_id = :retailer_id "
            "  AND status = 'active' "
            "LIMIT 1"
        ),
        {"tenant_id": tenant_id, "retailer_id": retailer_id},
    )
    binding_row = binding_result.fetchone()
    if binding_row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "BINDING_NOT_ACTIVE",
                "message": "No active relationship with this supplier",
            },
        )

    return ClientIdentity(
        user_id=token.user_id,
        retailer_id=retailer_id,
        tenant_id=tenant_id,
        token=token,
    )
