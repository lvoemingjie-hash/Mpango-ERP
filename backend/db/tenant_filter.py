from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
import uuid

from sqlalchemy import event
from sqlalchemy.orm import Session


_current_tenant_id: ContextVar[str | None] = ContextVar("mpango_current_tenant_id", default=None)
_current_tenant_schema: ContextVar[str | None] = ContextVar("mpango_current_tenant_schema", default=None)
_system_scope_reason: ContextVar[str | None] = ContextVar("mpango_system_scope_reason", default=None)

_SESSION_SYSTEM_SCOPE_KEY = "mpango_system_scope_reason"

_INSTALLED = False


class TenantContextMissingError(RuntimeError):
    """Raised when a tenant-scoped query executes without valid tenant context."""


@contextmanager
def run_as_system(*, reason: str):
    """
    Explicitly bypass tenant guardrail for system-wide operations.

    Usage:
        with run_as_system(reason="public_wholesaler_lookup"):
            ...
    """
    if not reason:
        raise ValueError("System scope reason must be provided")

    token = _system_scope_reason.set(reason)
    try:
        yield
    finally:
        _system_scope_reason.reset(token)


def mark_session_as_system(session: Session, *, reason: str) -> None:
    """Mark a DB session as an explicit system-wide scope bypass."""
    if not reason:
        raise ValueError("System scope reason must be provided")
    session.info[_SESSION_SYSTEM_SCOPE_KEY] = reason


def clear_session_system_scope(session: Session) -> None:
    """Remove session-level system scope bypass marker if present."""
    if getattr(session, "info", None):
        session.info.pop(_SESSION_SYSTEM_SCOPE_KEY, None)


def set_current_tenant(*, tenant_id: str | None, tenant_schema: str | None) -> tuple[Any, Any]:
    token_id = _current_tenant_id.set(tenant_id)
    token_schema = _current_tenant_schema.set(tenant_schema)
    return token_id, token_schema


def reset_current_tenant(token_id: Any, token_schema: Any) -> None:
    _current_tenant_id.reset(token_id)
    _current_tenant_schema.reset(token_schema)


def get_current_tenant_id() -> str | None:
    return _current_tenant_id.get()


def get_current_tenant_schema() -> str | None:
    return _current_tenant_schema.get()


def _get_effective_tenant_id(session: Session) -> str | None:
    tenant_id = None
    if getattr(session, "info", None):
        tenant_id = session.info.get("tenant_id")
    return tenant_id or get_current_tenant_id()


def _get_effective_tenant_schema(session: Session) -> str | None:
    tenant_schema = None
    if getattr(session, "info", None):
        tenant_schema = session.info.get("tenant_schema")
    return tenant_schema or get_current_tenant_schema()


def _get_system_scope_reason(session: Session) -> str | None:
    session_reason = None
    if getattr(session, "info", None):
        session_reason = session.info.get(_SESSION_SYSTEM_SCOPE_KEY)
    return session_reason or _system_scope_reason.get()


def _mapper_requires_tenant_id_filter(model_cls: type) -> bool:
    return hasattr(model_cls, "tenant_id") or hasattr(model_cls, "wholesaler_id")


def _mapper_requires_tenant_uuid(model_cls: type) -> bool:
    return hasattr(model_cls, "wholesaler_id")


def _statement_requires_tenant_id_filter(execute_state) -> bool:
    for mapper in getattr(execute_state, "all_mappers", ()):
        if _mapper_requires_tenant_id_filter(mapper.class_):
            return True
    return False


def _statement_requires_tenant_uuid(execute_state) -> bool:
    for mapper in getattr(execute_state, "all_mappers", ()):
        if _mapper_requires_tenant_uuid(mapper.class_):
            return True
    return False


def _parse_tenant_uuid(tenant_id: str | None) -> uuid.UUID | None:
    if not tenant_id:
        return None
    try:
        return uuid.UUID(str(tenant_id))
    except (TypeError, ValueError):
        return None


def _require_tenant_context(execute_state) -> None:
    session: Session = execute_state.session

    tenant_schema = _get_effective_tenant_schema(session)
    if not tenant_schema:
        raise TenantContextMissingError("Tenant context required")

    if _statement_requires_tenant_id_filter(execute_state):
        tenant_id = _get_effective_tenant_id(session)
        if not tenant_id:
            raise TenantContextMissingError(
                "Tenant context missing: tenant_id required for tenant-scoped query"
            )

        if _statement_requires_tenant_uuid(execute_state) and _parse_tenant_uuid(tenant_id) is None:
            raise TenantContextMissingError(
                "Tenant context invalid: tenant_id must be a UUID for wholesaler-scoped query"
            )


def _maybe_apply_tenant_id_criteria(execute_state) -> None:
    """Inject tenant WHERE clauses directly into the statement.

    Previous implementation used ``with_loader_criteria(DeclarativeBase, ...)``
    with ``track_closure_variables=False``.  SQLAlchemy caches the resulting SQL
    fragment keyed on the entity class; when a sync unit-test ran first with a
    non-UUID tenant_id the cached fragment carried a ``None`` bind-param value
    that poisoned every subsequent async query on the same process.

    The fix: iterate over the statement's mappers and append explicit ``.where()``
    clauses.  This is evaluated fresh on every execution — no caching, no leaks.
    """
    session: Session = execute_state.session
    tenant_id = _get_effective_tenant_id(session)
    if not tenant_id:
        return

    tenant_uuid = _parse_tenant_uuid(tenant_id)

    stmt = execute_state.statement
    for mapper in getattr(execute_state, "all_mappers", ()):
        cls = mapper.class_
        if hasattr(cls, "tenant_id"):
            stmt = stmt.where(getattr(cls, "tenant_id") == tenant_id)
        elif hasattr(cls, "wholesaler_id") and tenant_uuid is not None:
            stmt = stmt.where(getattr(cls, "wholesaler_id") == tenant_uuid)
    execute_state.statement = stmt


def _is_system_scope_bypass(execute_state) -> bool:
    if execute_state.execution_options.get("ignore_tenant") is True:
        return True

    system_reason = _get_system_scope_reason(execute_state.session)
    return system_reason is not None


def install_global_tenant_filter() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    @event.listens_for(Session, "do_orm_execute")
    def _do_orm_execute(execute_state):  # type: ignore[no-redef]
        if _is_system_scope_bypass(execute_state):
            return

        if not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
            return

        _require_tenant_context(execute_state)
        _maybe_apply_tenant_id_criteria(execute_state)

    _INSTALLED = True


install_global_tenant_filter()
