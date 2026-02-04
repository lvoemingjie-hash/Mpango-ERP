from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from api.context import AuthContext
from api.context.tenant import TenantContext
from auth.strategy import AuthStrategy


class _MockPermission:
    def __init__(self, code: str):
        self.code = code


class _MockRole:
    def __init__(self, name: str, permission_codes: list[str]):
        self.name = name
        self.permissions = [_MockPermission(code) for code in permission_codes]


class _MockUser:
    def __init__(self, roles: list[_MockRole]):
        self.roles = roles
        self.is_active = True


@dataclass
class _MockToken:
    user_id: str
    tenant_id: str
    tenant_schema: str
    type: str = "access"


class MockAuthStrategy(AuthStrategy):
    """Test auth strategy: inject a deterministic mock identity.

    This strategy is selected only when MPANGO_ENV=test via auth.factory.get_auth_strategy.
    """

    def __init__(
        self,
        *,
        user_id: str = "00000000-0000-0000-0000-000000000001",
        tenant_id: str = "00000000-0000-0000-0000-000000000000",
        tenant_schema: str = "t_dev",
        permission_codes: Optional[list[str]] = None,
    ) -> None:
        if permission_codes is None:
            permission_codes = [
                "payments:create",
                "orders:read",
                "orders:write",
            ]

        self._token = _MockToken(
            user_id=user_id,
            tenant_id=tenant_id,
            tenant_schema=tenant_schema,
        )
        self._user = _MockUser(
            roles=[
                _MockRole(
                    name="test",
                    permission_codes=permission_codes,
                )
            ]
        )

    async def authenticate(self, request: Request) -> Optional[AuthContext]:
        return AuthContext(token=self._token, raw_token="")

    async def resolve_tenant_context(self, auth_ctx: AuthContext) -> TenantContext:
        session = _LazyTenantSession(self._token.tenant_schema)
        return TenantContext(
            tenant_id=self._token.tenant_id,
            tenant_schema=self._token.tenant_schema,
            session=session,
            user=self._user,
        )


class _LazyTenantSession:
    """Lazy async session wrapper for MockAuthStrategy.

    - Avoids creating DB connections for endpoints that don't touch the DB (e.g. /health).
    - Still supports real DB operations when needed (execute/begin).
    """

    def __init__(self, tenant_schema: str):
        self._tenant_schema = tenant_schema
        self._session = None

    async def _ensure_session(self):
        if self._session is None:
            from sqlalchemy import text

            from database.session import AsyncSessionLocal

            self._session = AsyncSessionLocal()
            self._session.info["tenant_schema"] = self._tenant_schema
            await self._session.execute(text(f'SET LOCAL search_path TO "{self._tenant_schema}", public'))

    async def execute(self, *args, **kwargs):
        await self._ensure_session()
        return await self._session.execute(*args, **kwargs)

    async def commit(self):
        if self._session is None:
            return None
        return await self._session.commit()

    async def rollback(self):
        if self._session is None:
            return None
        return await self._session.rollback()

    async def close(self):
        if self._session is None:
            return None
        await self._session.close()
        self._session = None

    def begin(self):
        return _LazyTenantTransaction(self)


class _LazyTenantTransaction:
    def __init__(self, session: _LazyTenantSession):
        self._session = session

    async def __aenter__(self):
        await self._session._ensure_session()
        return self._session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self._session.rollback()
        else:
            await self._session.commit()
        return False
