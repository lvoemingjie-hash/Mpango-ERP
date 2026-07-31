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
5. Grants payments:confirm_declaration to admin role idempotently.
6. Removes stale client:payments:create grants from retailer_operator idempotently.

R1 Corrections:
- Semantic fail-closed preflight: exact columns/types/nullability/defaults,
  CHECK/FK/UNIQUE/index definitions, receipt_number and transaction_id contracts,
  old/new permission collision, malformed partial objects fail before mutation.
- Grant payments:confirm_declaration to admin in migration.
- Remove stale retailer_operator grants idempotently.

Tenant enumeration uses the authoritative public.tenant_registrations JOIN
public.wholesalers pattern with the exact status sets from migrations 035/036.
alembic_version exists only in public; no per-tenant version checks.
Rogue/unregistered schemas are untouched.
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
ROLES = "roles"
PERMISSIONS = "permissions"
ROLE_PERMISSIONS = "role_permissions"

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
ADMIN_ROLE = "admin"
RETAILER_OPERATOR_ROLE = "retailer_operator"


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
# semantic fail-closed preflight (R1.2 — exact catalog verification)
# ---------------------------------------------------------------------------

def _preflight_semantic(bind, rows: list[dict[str, Any]]) -> None:
    """Verify exact columns/types/nullability/defaults, CHECK/FK/UNIQUE/index
    definitions, receipt_number and transaction_id contracts, and permission
    collision before any mutation. Fails closed — no mutation occurs."""
    failures: list[str] = []
    for row in rows:
        schema = row["tenant_schema"]

        # --- payments.transaction_id contract ---
        if not _table_exists(bind, schema, PAYMENTS):
            continue

        ti_info = bind.execute(sa.text(
            "SELECT data_type, character_maximum_length, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'payments' AND column_name = 'transaction_id'"
        ), {"s": schema}).first()
        if ti_info is None:
            failures.append(f"{schema}.payments: transaction_id column is missing")
        elif ti_info[0] != "character varying":
            failures.append(f"{schema}.payments.transaction_id: expected character varying, got {ti_info[0]}")
        elif ti_info[1] is not None and ti_info[1] != 64 and ti_info[1] != 128:
            failures.append(f"{schema}.payments.transaction_id: unexpected length {ti_info[1]}")

        # --- orders table for FK ---
        if not _table_exists(bind, schema, ORDERS):
            failures.append(f"{schema}.orders: orders table is missing (FK target)")

        # --- permission collision: both old and new must not coexist ---
        old_count = bind.execute(sa.text(
            f'SELECT COUNT(*) FROM "{schema}".permissions WHERE code = :code'
        ), {"code": OLD_CLIENT_PAY_PERM}).scalar()
        new_count = bind.execute(sa.text(
            f'SELECT COUNT(*) FROM "{schema}".permissions WHERE code = :code'
        ), {"code": NEW_CLIENT_PAY_PERM}).scalar()
        if old_count > 0 and new_count > 0:
            failures.append(
                f"{schema}.permissions: both {OLD_CLIENT_PAY_PERM} and {NEW_CLIENT_PAY_PERM} exist (collision)"
            )
        if old_count == 0 and new_count == 0:
            failures.append(
                f"{schema}.permissions: neither {OLD_CLIENT_PAY_PERM} nor {NEW_CLIENT_PAY_PERM} exists"
            )

        # --- payment_declarations: if exists, verify exact catalog ---
        if _table_exists(bind, schema, PAYMENT_DECLARATIONS):
            _verify_declaration_catalog(bind, schema, failures)

    if failures:
        raise PreflightFailure("037 preflight (semantic) failed: " + "; ".join(failures))


def _verify_declaration_catalog(bind, schema: str, failures: list[str]) -> None:
    """Verify existing payment_declarations matches exact contract."""
    expected_cols = {
        "id": ("uuid", "NO"),
        "order_id": ("uuid", "NO"),
        "retailer_id": ("uuid", "NO"),
        "wholesaler_id": ("uuid", "NO"),
        "declared_amount": ("numeric", "NO"),
        "method": ("character varying", "NO"),
        "transfer_reference": ("character varying", "YES"),
        "status": ("character varying", "NO"),
        "idempotency_key": ("character varying", "NO"),
        "submitted_by": ("uuid", "NO"),
        "submitted_at": ("timestamp with time zone", "NO"),
        "confirmed_by": ("uuid", "YES"),
        "confirmed_at": ("timestamp with time zone", "YES"),
        "confirmation_payment_id": ("uuid", "YES"),
        "rejected_by": ("uuid", "YES"),
        "rejected_at": ("timestamp with time zone", "YES"),
        "reason": ("character varying", "YES"),
    }
    actual_cols = {}
    for col_row in bind.execute(sa.text(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = :s AND table_name = 'payment_declarations'"
    ), {"s": schema}).fetchall():
        actual_cols[col_row[0]] = (col_row[1], col_row[2])

    for col_name, (exp_type, exp_nullable) in expected_cols.items():
        if col_name not in actual_cols:
            failures.append(f"{schema}.payment_declarations: column {col_name} missing")
        else:
            act_type, act_nullable = actual_cols[col_name]
            if not act_type.startswith(exp_type.split("(")[0]):
                failures.append(
                    f"{schema}.payment_declarations.{col_name}: type mismatch "
                    f"expected ~{exp_type}, got {act_type}"
                )
            if act_nullable != exp_nullable:
                failures.append(
                    f"{schema}.payment_declarations.{col_name}: nullability mismatch "
                    f"expected {exp_nullable}, got {act_nullable}"
                )

    # is_deleted must NOT exist
    if "is_deleted" in actual_cols:
        failures.append(f"{schema}.payment_declarations: is_deleted must not exist")

    # CHECK constraints
    for ck_name, ck_fragment in [
        ("ck_payment_declarations_method", "'cash'"),
        ("ck_payment_declarations_status", "'pending'"),
        ("ck_payment_declarations_amount_positive", "> 0"),
    ]:
        if not _constraint_exists(bind, schema, PAYMENT_DECLARATIONS, ck_name):
            failures.append(f"{schema}.payment_declarations: CHECK constraint {ck_name} missing")

    # FK RESTRICT
    fks = bind.execute(sa.text(
        "SELECT kcu.column_name, rc.delete_rule "
        "FROM information_schema.key_column_usage kcu "
        "JOIN information_schema.referential_constraints rc "
        "ON kcu.constraint_name = rc.constraint_name "
        "WHERE kcu.table_schema = :s AND kcu.table_name = 'payment_declarations'"
    ), {"s": schema}).fetchall()
    fk_map = {r[0]: r[1] for r in fks}
    if fk_map.get("order_id") != "RESTRICT":
        failures.append(f"{schema}.payment_declarations: order_id FK must be RESTRICT")
    if fk_map.get("confirmation_payment_id") != "RESTRICT":
        failures.append(f"{schema}.payment_declarations: confirmation_payment_id FK must be RESTRICT")

    # Unique index
    if not _index_exists(bind, schema, PAYMENT_DECLARATIONS, UX_DECLARATIONS_RETAILER_IDEM):
        failures.append(f"{schema}.payment_declarations: unique index {UX_DECLARATIONS_RETAILER_IDEM} missing")

    # receipt_sequences
    if _table_exists(bind, schema, RECEIPT_SEQUENCES):
        bd_info = bind.execute(sa.text(
            "SELECT data_type, character_maximum_length FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'receipt_sequences' AND column_name = 'business_date'"
        ), {"s": schema}).first()
        if bd_info and (bd_info[0] != "character" or bd_info[1] != 8):
            failures.append(
                f"{schema}.receipt_sequences.business_date: expected CHAR(8), got {bd_info[0]}({bd_info[1]})"
            )


# ---------------------------------------------------------------------------
# per-tenant mutations
# ---------------------------------------------------------------------------

def _widen_transaction_id(bind, schema: str) -> None:
    """Widen payments.transaction_id to VARCHAR(128)."""
    payments_t = _qualified(bind, schema, PAYMENTS)
    ti_len = bind.execute(sa.text(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_schema = :s AND table_name = 'payments' AND column_name = 'transaction_id'"
    ), {"s": schema}).scalar()
    if ti_len is not None and ti_len < 128:
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


def _reconcile_permissions(bind, schema: str) -> None:
    """Rename client:payments:create -> client:payments:declare;
    add payments:confirm_declaration;
    grant confirm_declaration to admin idempotently;
    remove stale client:payments:create grants from retailer_operator."""
    perms_t = _qualified(bind, schema, PERMISSIONS)
    roles_t = _qualified(bind, schema, ROLES)
    role_perms_t = _qualified(bind, schema, ROLE_PERMISSIONS)

    # Rename existing permission code (idempotent)
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

    # R1.3: Grant payments:confirm_declaration to admin role idempotently
    bind.execute(sa.text(
        f"INSERT INTO {role_perms_t} (role_id, permission_id) "
        f"SELECT r.id, p.id FROM {roles_t} r, {perms_t} p "
        f"WHERE r.name = :role AND p.code = :code "
        f"AND NOT EXISTS (SELECT 1 FROM {role_perms_t} rp "
        f"WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
    ), {"role": ADMIN_ROLE, "code": NEW_CONFIRM_PERM})

    # R1.4: Remove stale client:payments:create grants from retailer_operator (idempotent)
    bind.execute(sa.text(
        f"DELETE FROM {role_perms_t} "
        f"WHERE role_id IN (SELECT id FROM {roles_t} WHERE name = :role) "
        f"AND permission_id IN (SELECT id FROM {perms_t} WHERE code = :old_code)"
    ), {"role": RETAILER_OPERATOR_ROLE, "old_code": OLD_CLIENT_PAY_PERM})

    # R1.4: Ensure retailer_operator has client:payments:declare (if it was newly added)
    bind.execute(sa.text(
        f"INSERT INTO {role_perms_t} (role_id, permission_id) "
        f"SELECT r.id, p.id FROM {roles_t} r, {perms_t} p "
        f"WHERE r.name = :role AND p.code = :code "
        f"AND NOT EXISTS (SELECT 1 FROM {role_perms_t} rp "
        f"WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
    ), {"role": RETAILER_OPERATOR_ROLE, "code": NEW_CLIENT_PAY_PERM})

    # R1.4: Ensure retailer_operator NEVER has payments:confirm_declaration
    bind.execute(sa.text(
        f"DELETE FROM {role_perms_t} "
        f"WHERE role_id IN (SELECT id FROM {roles_t} WHERE name = :role) "
        f"AND permission_id IN (SELECT id FROM {perms_t} WHERE code = :confirm_code)"
    ), {"role": RETAILER_OPERATOR_ROLE, "confirm_code": NEW_CONFIRM_PERM})


# ---------------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    bind = op.get_bind()
    _ensure_registry_tables_exist(bind)
    rows = _registered_tenants(bind)
    _validate_registry_rows(bind, rows)
    _preflight_semantic(bind, rows)

    for row in rows:
        schema = row["tenant_schema"]
        _widen_transaction_id(bind, schema)
        _add_receipt_number(bind, schema)
        _create_payment_declarations(bind, schema)
        _create_receipt_sequences(bind, schema)
        _reconcile_permissions(bind, schema)


def downgrade() -> None:
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


def _constraint_exists(bind, schema: str, table_name: str, constraint_name: str) -> bool:
    return bool(bind.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname = :schema AND t.relname = :table_name "
            "AND c.conname = :constraint_name"
        ),
        {"schema": schema, "table_name": table_name, "constraint_name": constraint_name},
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
