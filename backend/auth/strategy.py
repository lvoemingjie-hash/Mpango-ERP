from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from fastapi import Request

from api.context import AuthContext, TenantContext


class AuthStrategy(ABC):
    """Authentication strategy interface.

    Strategies are responsible for:
    - parsing request auth information (e.g. Authorization header)
    - creating AuthContext
    - resolving TenantContext

    Middleware remains environment-agnostic and delegates to the selected strategy.
    """

    @abstractmethod
    async def authenticate(self, request: Request) -> Optional[AuthContext]:
        """Return AuthContext if request is authenticated, else None."""

    @abstractmethod
    async def resolve_tenant_context(self, auth_ctx: AuthContext) -> TenantContext:
        """Return tenant context for an authenticated request."""
