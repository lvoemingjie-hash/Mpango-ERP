from __future__ import annotations

from typing import Optional

from fastapi import Request

from api.context import AuthContext, extract_bearer_token, resolve_auth_context
from auth.strategy import AuthStrategy


class JwtAuthStrategy(AuthStrategy):
    """Production auth strategy: JWT bearer token + tenant context derived from token."""

    async def authenticate(self, request: Request) -> Optional[AuthContext]:
        raw_token = extract_bearer_token(request)
        if not raw_token:
            return None
        return resolve_auth_context(raw_token)

    async def resolve_tenant_context(self, auth_ctx: AuthContext):
        from api.context.tenant import resolve_tenant_context

        return await resolve_tenant_context(auth_ctx.token)
