from __future__ import annotations

from typing import Optional

from fastapi import Request

from api.context import AuthContext, extract_bearer_token, resolve_auth_context
from auth.strategy import AuthStrategy


class JwtAuthStrategy(AuthStrategy):
    """
    Production auth strategy: JWT bearer token + tenant context derived from token.

    H-Fix-01: Identity-only JWTs (no tenant_id/tenant_schema) are valid.
    For these tokens, resolve_tenant_context returns None so the middleware
    skips tenant context attachment.  Endpoints that require tenant context
    will fail at the dependency level (get_tenant_db_session), which is correct.
    """

    async def authenticate(self, request: Request) -> Optional[AuthContext]:
        raw_token = extract_bearer_token(request)
        if not raw_token:
            return None
        context = resolve_auth_context(raw_token)
        if context.token.is_identity_only:
            from database.session import AsyncSessionLocal
            from services.identity_authority import current_identity
            async with AsyncSessionLocal() as session:
                current = await current_identity(session, context.token)
            context.token = context.token.model_copy(update={
                "roles": current.roles, "tmap": current.tenant_user_map,
            })
        return context

    async def resolve_tenant_context(self, auth_ctx: AuthContext):
        # H-Fix-01: Identity-only tokens have no tenant context.
        # Return None so the middleware skips tenant attachment.
        if auth_ctx.token.is_identity_only:
            return None

        from api.context.tenant import resolve_tenant_context

        return await resolve_tenant_context(auth_ctx.token)
