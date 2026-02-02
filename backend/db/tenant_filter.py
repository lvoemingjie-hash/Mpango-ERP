from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from sqlalchemy import event
from sqlalchemy import bindparam
from sqlalchemy import true
from sqlalchemy.orm import DeclarativeBase, Session, with_loader_criteria


_current_tenant_id: ContextVar[str | None] = ContextVar("mpango_current_tenant_id", default=None)
_current_tenant_schema: ContextVar[str | None] = ContextVar("mpango_current_tenant_schema", default=None)

_INSTALLED = False


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


def _require_tenant_context(session: Session) -> None:
    tenant_schema = None
    if getattr(session, "info", None):
        tenant_schema = session.info.get("tenant_schema")

    tenant_schema = tenant_schema or get_current_tenant_schema()

    if not tenant_schema:
        raise RuntimeError("Tenant context required")


def _maybe_apply_tenant_id_criteria(execute_state) -> None:
    tenant_id = None
    session: Session = execute_state.session
    if getattr(session, "info", None):
        tenant_id = session.info.get("tenant_id")

    tenant_id = tenant_id or get_current_tenant_id()
    if not tenant_id:
        return

    tenant_id_param = bindparam("mpango_tenant_id", tenant_id)

    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            DeclarativeBase,
            lambda cls: (getattr(cls, "tenant_id") == tenant_id_param) if hasattr(cls, "tenant_id") else true(),
            include_aliases=True,
            track_closure_variables=False,
        )
    )


def install_global_tenant_filter() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    @event.listens_for(Session, "do_orm_execute")
    def _do_orm_execute(execute_state):  # type: ignore[no-redef]
        if execute_state.execution_options.get("ignore_tenant") is True:
            return

        if not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
            return

        _require_tenant_context(execute_state.session)
        _maybe_apply_tenant_id_criteria(execute_state)

    _INSTALLED = True


install_global_tenant_filter()
