"""DC-12R1-S3-S2B-I1: payment_declarations, receipt_sequences, receipt_number, transaction_id widening, permission rename.

Revision ID: 037_payment_declarations_schema
Revises: 036_retailer_mvp_identity
Create Date: 2026-07-31

This migration is additive and forward-only. It:
1. Widens payments.transaction_id from VARCHAR(64) to VARCHAR(128) in every live
   tenant schema.
2. Adds payments.receipt_number VARCHAR(32) with a partial unique index in every
   live tenant schema.
3. Creates payment_declarations and receipt_sequences tables in every live tenant
   schema.
4. Renames the permission code client:payments:create -> client:payments:declare
   and adds payments:confirm_declaration.

Tenant enumeration uses the authoritative public.tenant_registrations JOIN
public.wholesalers pattern with the exact status sets from migrations 035/036.
alembic_version exists only in public; no per-tenant version checks.
Rogue/unregistered schemas are untouched. Read-only preflights fail closed
before any mutation. A failed migration leaves catalog fingerprints unchanged.
"""

from __future__ import annotations

import re
from typing import Any

import sqlalchemy as sa
from alembic import op


# ---------------------------------------------------------------------------
# revision identifiers
# ---------------------------------------------------------------------------

revision = "037_payment_declarations_schema"
down_revision = "036_retailer_mvp_identity"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# constants (exact copies from 035/036)
# ---------------------------------------------------------------------------

PUBLIC_SCHEMA = "public"
TENANT_SCHEMA_RE = re.compile(r"^t_[0-9a-f]{32}$")
LIVE_REGISTRATION_STATUSES = (
    "pending_email_verification",
    "email_verified",
    "provisioning",
    "active",
    "failed",
)
WHOLESALER_ACTIVE_STATUSES = ("active", "provisioning")

USERS = "users"
PAYMENTS = "payments"
ORDERS = "orders"

PAYMENT_DECLARATIONS = "payment_declarations"
RECEIPT_SEQUENCES = "receipt_sequences"

UX_PAYMENTS_RECEIPT_NUMBER = "ux_payments_receipt_number"
UX_DECLARATIONS_RETAILER_IDEM = "ux_payment_declarations_retailer_idem"
IX_DECLARATIONS_RETAILER_STATUS = "ix_payment_declarations_retailer_status"
IX_DECLARATIONS_WHOLESALER_STATUS = "ix_payment_declarations_wholesaler_status"

OLD_CLIENT_PAY_PERM = "client:payments:create"
NEW_CLIENT_PAY_PERM = "client:payments:declare"
NEW_CONFIRM_PERM = "payments:confirm_declaration"
NEW_CONFIRM_PERM_DESC = "Confirm or reject a retailer payment declaration"


class PreflightFailure(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# registry enumeration (verbatim pattern from 035/036)
# ---------------------------------------------------------------------------

def _ensure_registry_tables_exist(bind) -> None:
    for table_name in ("tenant_registrations", "wholesalers"):
        if not _table_exists(bind, PUBLIC_SCHEMA, table_name):
            raise PreflightFailure(
                f"public.{table_name} is missing; cannot enumerate live tenants"
            )


def _registered_tenants(bind) -> list[dict[str, Any]]:
    stmt = sa.text(
        """
        SELECT tr.id::text AS registration_id,
               tr.tenant_schema AS tenant_schema,
               tr.status AS registration_status,
               tr.wholesaler_id::text AS registration_wholesaler_id,
               w.id::text AS wholesaler_id,
               w.status AS wholesaler_status,
               ('t_' || replace(w.id::text, '-', '')) AS derived_schema
        FROM public.tenant_registrations tr
        JOIN public.wholesalers w ON w.id = tr.wholesaler_id
        WHERE tr.is_deleted IS FALSE
          AND tr.status IN :registration_statuses
          AND w.is_deleted IS FALSE
          AND w.status IN :wholesaler_statuses
        ORDER BY tr.tenant_schema, tr.id
        """
    ).bindparams(
        sa.bindparam("registration_statuses", expanding=True),
        sa.bindparam("wholesaler_statuses", expanding=True),
    )
    rows = bind.execute(
        stmt,
        {
            "registration_statuses": list(LIVE_REGISTRATION_STATUSES),
            "wholesaler_statuses": list(WHOLESALER_ACTIVE_STATUSES),
        },
    ).mappings()
    return [dict(row) for row in rows]


def _validate_registry_rows(bind, rows: list[dict[str, Any]]) -> None:
    failures: list[str] = []
    seen_schemas: dict[str, str] = {}
    for row in rows:
        schema = row["tenant_schema"]
        registration_id = row["registration_id"]
        evidence_name = schema or f"registration {registration_id}"
        try:
            _validate_tenant_schema_name(schema, evidence_name)
        except PreflightFailure as exc:
            failures.append(str(exc))
            continue
        if schema in seen_schemas:
            failures.append(f"{schema}: duplicate live tenant registry rows")
        seen_schemas[schema] = registration_id
        if row["registration_wholesaler_id"] != row["wholesaler_id"]:
            failures.append(f"{schema}: registration wholesaler does not match joined wholesaler")
        if schema != row["derived_schema"]:
            failures.append(f"{schema}: tenant_schema does not match wholesaler-derived schema")
        if not _schema_exists(bind, schema):
            failures.append(f"{schema}: registered tenant schema is missing")
            continue
        if not _table_exists(bind, schema, PAYMENTS):
            failures.append(f"{schema}.{PAYMENTS}: payments table is missing")
        if not _table_exists(bind, schema, ORDERS):
            failures.append(f"{schema}.{ORDERS}: orders table is missing")
    if failures:
        raise PreflightFailure("037 preflight (registry) failed: " + "; ".join(failures))


def _validate_tenant_schema_name(schema: str | None, evidence_name: str) -> None:
    if schema is None or schema.strip() == "":
        raise PreflightFailure(f"{evidence_name}: tenant_schema is missing")
    if len(schema) > 63 or not TENANT_SCHEMA_RE.fullmatch(schema):
        raise PreflightFailure(f"{evidence_name}: tenant_schema is not a valid derived tenant identifier")


# ---------------------------------------------------------------------------
# read-only preflight checks (fail closed, no mutation)
# ---------------------------------------------------------------------------

def _preflight_payments_catalog(bind, rows: list[dict[str, Any]]) -> None:
    """Verify payments table has expected columns before mutating."""
    failures: list[str] = []
    for row in rows:
        schema = row["tenant_schema"]
        if not _table_exists(bind, schema, PAYMENTS):
            continue  # already caught in _validate_registry_rows
        # transaction_id must exist (it was added in migration 021)
        if not _column_exists(bind, schema, PAYMENTS, "transaction_id"):
            failures.append(f"{schema}.{PAYMENTS}: transaction_id column is missing")
        # orders table must exist for FK
        if not _table_exists(bind, schema, ORDERS):
            failures.append(f"{schema}.{ORDERS}: orders table is missing (FK target)")
        # client:payments:create permission should exist (seeded by 036)
        perm_exists = bind.execute(sa.text(
            f"SELECT 1 FROM \"{schema}\".permissions WHERE code = :code"
        ), {"code": OLD_CLIENT_PAY_PERM}).first()
        if not perm_exists:
            # Check if it was already renamed (idempotent second upgrade)
            new_exists = bind.execute(sa.text(
                f"SELECT 1 FROM \"{schema}\".permissions WHERE code = :code"
            ), {"code": NEW_CLIENT_PAY_PERM}).first()
            if not new_exists:
                failures.append(
                    f"{schema}.permissions: neither {OLD_CLIENT_PAY_PERM} nor {NEW_CLIENT_PAY_PERM} exists"
                )
    if failures:
        raise PreflightFailure("037 preflight (payments catalog) failed: " + "; ".join(failures))


# ---------------------------------------------------------------------------
# per-tenant mutations
# ---------------------------------------------------------------------------

def _widen_transaction_id(bind, schema: str) -> None:
    """Widen payments.transaction_id to VARCHAR(128)."""
    payments_t = _qualified(bind, schema, PAYMENTS)
    bind.execute(sa.text(
        f"ALTER TABLE {payments_t} ALTER COLUMN transaction_id TYPE VARCHAR(128)"
    ))


def _add_receipt_number(bind, schema: str) -> None:
    """Add payments.receipt_number VARCHAR(32) with partial unique index."""
    payments_t = _qualified(bind, schema, PAYMENTS)
    if not _column_exists(bind, schema, PAYMENTS, "receipt_number"):
        bind.execute(sa.text(
            f"ALTER TABLE {payments_t} ADD COLUMN receipt_number VARCHAR(32)"
        ))
    if not _index_exists(bind, schema, PAYMENTS, UX_PAYMENTS_RECEIPT_NUMBER):
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {UX_PAYMENTS_RECEIPT_NUMBER} "
            f"ON {payments_t} (receipt_number) WHERE receipt_number IS NOT NULL"
        ))


def _create_payment_declarations(bind, schema: str) -> None:
    """Create payment_declarations table."""
    if _table_exists(bind, schema, PAYMENT_DECLARATIONS):
        return
    orders_t = _qualified(bind, schema, ORDERS)
    payments_t = _qualified(bind, schema, PAYMENTS)
    decl_t = _qualified(bind, schema, PAYMENT_DECLARATIONS)
    bind.execute(sa.text(f"""
        CREATE TABLE {decl_t} (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES {orders_t}(id) ON DELETE RESTRICT,
            retailer_id UUID NOT NULL,
            wholesaler_id UUID NOT NULL,
            declared_amount NUMERIC(12,2) NOT NULL,
            method VARCHAR(16) NOT NULL,
            transfer_reference VARCHAR(128),
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            idempotency_key VARCHAR(64) NOT NULL,
            submitted_by UUID NOT NULL,
            submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            confirmed_by UUID,
            confirmed_at TIMESTAMPTZ,
            confirmation_payment_id UUID REFERENCES {payments_t}(id) ON DELETE RESTRICT,
            rejected_by UUID,
            rejected_at TIMESTAMPTZ,
            reason VARCHAR(256),
            CONSTRAINT ck_payment_declarations_method
                CHECK (method IN ('cash', 'transfer')),
            CONSTRAINT ck_payment_declarations_status
                CHECK (status IN ('pending', 'confirmed', 'rejected')),
            CONSTRAINT ck_payment_declarations_amount_positive
                CHECK (declared_amount > 0)
        )
    """))
    bind.execute(sa.text(
        f"CREATE UNIQUE INDEX {UX_DECLARATIONS_RETAILER_IDEM} "
        f"ON {decl_t} (retailer_id, idempotency_key)"
    ))
    bind.execute(sa.text(
        f"CREATE INDEX {IX_DECLARATIONS_RETAILER_STATUS} "
        f"ON {decl_t} (retailer_id, status)"
    ))
    bind.execute(sa.text(
        f"CREATE INDEX {IX_DECLARATIONS_WHOLESALER_STATUS} "
        f"ON {decl_t} (wholesaler_id, status)"
    ))


def _create_receipt_sequences(bind, schema: str) -> None:
    """Create receipt_sequences table."""
    if _table_exists(bind, schema, RECEIPT_SEQUENCES):
        return
    rs_t = _qualified(bind, schema, RECEIPT_SEQUENCES)
    bind.execute(sa.text(f"""
        CREATE TABLE {rs_t} (
            business_date CHAR(8) PRIMARY KEY,
            next_seq INTEGER NOT NULL DEFAULT 1
        )
    """))


def _rename_permission_and_add_confirm(bind, schema: str) -> None:
    """Rename client:payments:create -> client:payments:declare; add payments:confirm_declaration."""
    perms_t = _qualified(bind, schema, "permissions")
    # Rename existing permission code (idempotent: only if old code exists)
    old_exists = bind.execute(sa.text(
        f"SELECT 1 FROM {perms_t} WHERE code = :code"
    ), {"code": OLD_CLIENT_PAY_PERM}).first()
    if old_exists:
        bind.execute(sa.text(
            f"UPDATE {perms_t} SET code = :new_code, "
            f"description = 'Retailer: submit payment declaration' "
            f"WHERE code = :old_code"
        ), {"new_code": NEW_CLIENT_PAY_PERM, "old_code": OLD_CLIENT_PAY_PERM})
    # Add payments:confirm_declaration permission (idempotent)
    bind.execute(sa.text(
        f"INSERT INTO {perms_t} (code, description) "
        f"VALUES (:code, :desc) ON CONFLICT (code) DO NOTHING"
    ), {"code": NEW_CONFIRM_PERM, "desc": NEW_CONFIRM_PERM_DESC})


# ---------------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    bind = op.get_bind()
    _ensure_registry_tables_exist(bind)
    rows = _registered_tenants(bind)
    _validate_registry_rows(bind, rows)
    _preflight_payments_catalog(bind, rows)

    for row in rows:
        schema = row["tenant_schema"]
        _widen_transaction_id(bind, schema)
        _add_receipt_number(bind, schema)
        _create_payment_declarations(bind, schema)
        _create_receipt_sequences(bind, schema)
        _rename_permission_and_add_confirm(bind, schema)


def downgrade() -> None:
    # Forward-only: reverting a financial schema migration is unsafe.
    raise RuntimeError(
        "037_payment_declarations_schema is forward-only. "
        "Downgrade is not supported."
    )


# ---------------------------------------------------------------------------
# catalog helpers (verbatim from 035/036)
# ---------------------------------------------------------------------------

def _column_exists(bind, schema: str, table_name: str, column_name: str) -> bool:
    return bool(bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table_name "
            "AND column_name = :column_name"
        ),
        {"schema": schema, "table_name": table_name, "column_name": column_name},
    ).first())


def _table_exists(bind, schema: str, table_name: str) -> bool:
    return bool(bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table_name"
        ),
        {"schema": schema, "table_name": table_name},
    ).first())


def _index_exists(bind, schema: str, table_name: str, index_name: str) -> bool:
    return bool(bind.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename = :table_name "
            "AND indexname = :index_name"
        ),
        {"schema": schema, "table_name": table_name, "index_name": index_name},
    ).first())


def _schema_exists(bind, schema: str) -> bool:
    return bool(bind.execute(
        sa.text("SELECT 1 FROM pg_namespace WHERE nspname = :schema"),
        {"schema": schema},
    ).first())


def _qualified(bind, schema: str, table_name: str) -> str:
    return f"{_quote_ident(bind, schema)}.{_quote_ident(bind, table_name)}"


def _quote_ident(bind, identifier: str | None) -> str:
    if identifier is None:
        raise PreflightFailure("identifier is missing")
    return bind.execute(
        sa.text("SELECT quote_ident(:identifier)"), {"identifier": identifier}
    ).scalar_one()
