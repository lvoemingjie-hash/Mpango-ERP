"""Revalidate identity-only JWT authority against its signed tenant bindings."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from core.security import TokenPayload


@dataclass(frozen=True)
class CurrentIdentity:
    roles: list[str]
    tenant_user_map: dict[str, str]


def _refuse(code: str = "IDENTITY_REVOKED") -> HTTPException:
    return HTTPException(401, detail={"code": code, "message": "Identity is no longer authorized; sign in again"})


async def current_identity(db, token: TokenPayload) -> CurrentIdentity:
    """Old claims constrain the lookup, but never supply current authority.

    Schemas are derived from live wholesaler UUIDs, not client strings. A
    missing primary subject or lost platform role revokes both token uses.
    Legacy unbound identity tokens must authenticate again.
    """
    if token.tenant_id is not None or token.tenant_schema is not None or not token.tmap:
        raise _refuse("IDENTITY_BINDING_REQUIRED")
    try:
        primary = UUID(token.user_id)
        bindings = [(UUID(tid), UUID(uid)) for tid, uid in token.tmap.items()]
    except (TypeError, ValueError, AttributeError):
        raise _refuse("IDENTITY_BINDING_REQUIRED")

    current_map = {}
    roles = set()
    primary_live = False
    from api.context.tenant import _is_missing_tenant_resource_error

    for tenant, uid in bindings:
        live = (await db.execute(text(
            "SELECT id FROM public.wholesalers WHERE id=:tid "
            "AND is_deleted IS FALSE AND status='active'"
        ), {"tid": tenant})).first()
        if live is None:
            continue
        schema = "t_" + tenant.hex
        try:
            # A missing bound schema must not abort checks of other bindings.
            async with db.begin_nested():
                rows = (await db.execute(text(
                    f'SELECT u.id, r.name FROM "{schema}".users u '
                    f'LEFT JOIN "{schema}".user_roles ur ON ur.user_id=u.id '
                    f'LEFT JOIN "{schema}".roles r ON r.id=ur.role_id AND r.is_deleted IS FALSE '
                    "WHERE u.id=:uid AND u.is_active IS TRUE AND u.is_deleted IS FALSE"
                ), {"uid": uid})).all()
        except Exception as exc:
            if _is_missing_tenant_resource_error(exc):
                continue
            raise
        if not rows:
            continue
        primary_live |= uid == primary
        current_map[str(tenant)] = str(uid)
        roles.update(row.name for row in rows if row.name)

    if not primary_live:
        raise _refuse()
    if token.is_super_admin and "super_admin" not in roles:
        raise _refuse("PLATFORM_ROLE_REVOKED")
    # Existing tokens cannot acquire a newly granted role without a new login.
    return CurrentIdentity(sorted(roles.intersection(token.roles)), current_map)
