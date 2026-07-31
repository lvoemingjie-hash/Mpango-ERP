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
# CHECK-expression normalisation helpers (R4-R1: exact semantics)
# ---------------------------------------------------------------------------

def _normalize_check_expr(expr: str) -> str:
    """Normalise a pg_get_constraintdef CHECK body for semantic comparison.

    Lowercases, strips whitespace, and collapses so that superficial formatting
    differences do not cause false positives.  The caller still inspects the
    normalised string for dangerous patterns (OR TRUE, extra values, etc.).
    """
    return re.sub(r"\s+", " ", (expr or "")).strip().lower()


def _check_in_allowed_values(normalised: str, column: str,
                             allowed: tuple[str, ...]) -> bool:
    """Return True only when the CHECK constraint references *column*, contains
    every value in *allowed*, has no extra values, and no weakening clause."""
    # Must reference the correct column
    if column not in normalised:
        return False
    # Must contain every allowed literal
    for val in allowed:
        if val not in normalised:
            return False
    # Reject dangerous weakeners
    if "or true" in normalised or "or 1" in normalised:
        return False
    # Reject when the allowed set is a subset of a larger IN list — detect
    # extra single-quoted string literals that are not in *allowed*.
    literals = set(re.findall(r"'([^']*)'", normalised))
    extra_literals = literals - set(allowed)
    # 'pending' is a status *default*, not a CHECK literal for the amount check;
    # callers scope *allowed* to the relevant constraint so this is safe.
    if extra_literals:
        return False
    return True


def _check_amount_positive(normalised: str) -> bool:
    """Return True only for exact ``declared_amount > 0`` (reject >=, > -1, etc.)."""
    if "declared_amount" not in normalised:
        return False
    if "or true" in normalised:
        return False
    # Must use strict > (not >=)
    if ">=" in normalised:
        return False
    # Must compare against 0 (not -1, 1, or any other value)
    # PG rewrites > 0 as "> (0)::numeric" — extract the right-hand operand
    m = re.search(r"declared_amount\s*>\s*\(?([^)<\s]+)", normalised)
    if not m:
        return False
    rhs = m.group(1).strip("()")
    return rhs == "0"


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
# R3: pg_catalog semantic fail-closed preflight
# ---------------------------------------------------------------------------

PG_CATALOG_COLUMNS_SQL = """
    SELECT a.attname AS column_name,
           pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
           a.attnotnull AS not_null,
           pg_catalog.pg_get_expr(d.adbin, d.adrelid) AS column_default
    FROM pg_catalog.pg_attribute a
    JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE n.nspname = :schema AND c.relname = :table_name
      AND a.attnum > 0 AND NOT a.attisdropped
    ORDER BY a.attnum
"""

PG_CATALOG_CONSTRAINTS_SQL = """
    SELECT c.conname, c.contype,
           pg_catalog.pg_get_constraintdef(c.oid) AS constraint_def
    FROM pg_catalog.pg_constraint c
    JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = :schema AND t.relname = :table_name
"""

PG_CATALOG_INDEXES_SQL = """
    SELECT ic.relname AS index_name,
           i.indisunique,
           i.indisprimary,
           pg_catalog.pg_get_indexdef(i.indexrelid) AS index_def
    FROM pg_catalog.pg_index i
    JOIN pg_catalog.pg_class t ON t.oid = i.indrelid
    JOIN pg_catalog.pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = :schema AND t.relname = :table_name
"""


def _pg_catalog_columns(bind, schema, table_name):
    """Return {column_name: (data_type, not_null, column_default)} from pg_catalog."""
    return {(r[0], r[1], r[2], r[3]) for r in bind.execute(
        sa.text(PG_CATALOG_COLUMNS_SQL),
        {"schema": schema, "table_name": table_name},
    ).fetchall()}


def _pg_catalog_constraints(bind, schema, table_name):
    """Return {(conname, contype, constraint_def)} from pg_catalog."""
    return {(r[0], r[1], r[2]) for r in bind.execute(
        sa.text(PG_CATALOG_CONSTRAINTS_SQL),
        {"schema": schema, "table_name": table_name},
    ).fetchall()}


def _pg_catalog_indexes(bind, schema, table_name):
    """Return {(index_name, indisunique, index_def)} from pg_catalog."""
    return {(r[0], r[1], r[3]) for r in bind.execute(
        sa.text(PG_CATALOG_INDEXES_SQL),
        {"schema": schema, "table_name": table_name},
    ).fetchall()}


def _preflight_semantic(bind, rows: list[dict[str, Any]]) -> None:
    """R3/R4-R1: pg_catalog semantic validators for exact column sets, types,
    lengths, precision/scale, nullability, defaults, PK/FK targets/delete
    actions, exact CHECK expressions, index uniqueness/keys/predicates.
    Fails closed — no mutation occurs."""
    failures: list[str] = []
    for row in rows:
        schema = row["tenant_schema"]

        # --- required tables: fail, never continue ---
        if not _table_exists(bind, schema, PAYMENTS):
            failures.append(f"{schema}.{PAYMENTS}: table missing")
            continue
        if not _table_exists(bind, schema, ORDERS):
            failures.append(f"{schema}.{ORDERS}: table missing (FK target)")
        if not _table_exists(bind, schema, PERMISSIONS):
            failures.append(f"{schema}.{PERMISSIONS}: table missing")

        # --- payments.transaction_id: exact VARCHAR(64) pre-upgrade or VARCHAR(128) ---
        ti_cols = _pg_catalog_columns(bind, schema, PAYMENTS)
        ti_match = [c for c in ti_cols if c[0] == "transaction_id"]
        if not ti_match:
            failures.append(f"{schema}.payments: transaction_id column missing")
        else:
            ti_type = ti_match[0][1]
            # Reject unbounded VARCHAR; accept only character varying(64) or (128)
            if ti_type not in ("character varying(64)", "character varying(128)"):
                failures.append(
                    f"{schema}.payments.transaction_id: expected VARCHAR(64) or VARCHAR(128), got {ti_type}")
            if ti_match[0][2] is not False:
                failures.append(f"{schema}.payments.transaction_id: must be NOT NULL")

        # --- payments.receipt_number (may already exist from prior upgrade) ---
        rn_match = [c for c in ti_cols if c[0] == "receipt_number"]
        if rn_match:
            rn = rn_match[0]
            if rn[1] != "character varying(32)":
                failures.append(f"{schema}.payments.receipt_number: expected VARCHAR(32), got {rn[1]}")
            if rn[2]:
                failures.append(f"{schema}.payments.receipt_number: must be nullable")
            # Verify partial unique index when column exists
            pay_indexes = _pg_catalog_indexes(bind, schema, PAYMENTS)
            rn_idx = [i for i in pay_indexes if i[0] == UX_PAYMENTS_RECEIPT_NUMBER]
            if not rn_idx:
                failures.append(
                    f"{schema}.payments: index {UX_PAYMENTS_RECEIPT_NUMBER} missing")
            else:
                idx_def = rn_idx[0][2] or ""
                if "UNIQUE" not in idx_def.upper():
                    failures.append(
                        f"{schema}.payments: {UX_PAYMENTS_RECEIPT_NUMBER} must be UNIQUE")
                if "receipt_number IS NOT NULL" not in idx_def:
                    failures.append(
                        f"{schema}.payments: {UX_PAYMENTS_RECEIPT_NUMBER} must have partial predicate")

        # --- permission collision ---
        old_count = bind.execute(sa.text(
            f'SELECT COUNT(*) FROM "{schema}".permissions WHERE code = :code'
        ), {"code": OLD_CLIENT_PAY_PERM}).scalar()
        new_count = bind.execute(sa.text(
            f'SELECT COUNT(*) FROM "{schema}".permissions WHERE code = :code'
        ), {"code": NEW_CLIENT_PAY_PERM}).scalar()
        if old_count > 0 and new_count > 0:
            failures.append(f"{schema}.permissions: collision — both {OLD_CLIENT_PAY_PERM} and {NEW_CLIENT_PAY_PERM} exist")
        if old_count == 0 and new_count == 0:
            failures.append(f"{schema}.permissions: neither {OLD_CLIENT_PAY_PERM} nor {NEW_CLIENT_PAY_PERM} exists")

        # --- payment_declarations ---
        if _table_exists(bind, schema, PAYMENT_DECLARATIONS):
            _verify_declaration_catalog_pg(bind, schema, failures)

        # --- receipt_sequences ---
        if _table_exists(bind, schema, RECEIPT_SEQUENCES):
            _verify_receipt_sequences_pg(bind, schema, failures)

    if failures:
        raise PreflightFailure("037 preflight (semantic) failed: " + "; ".join(failures))


def _verify_declaration_catalog_pg(bind, schema: str, failures: list[str]) -> None:
    """R3/R4-R1: pg_catalog verification of payment_declarations."""
    cols = _pg_catalog_columns(bind, schema, PAYMENT_DECLARATIONS)
    col_map = {c[0]: c for c in cols}  # name -> (name, type, not_null, default)

    # Exact column set — no extras, no missing
    actual_names = set(col_map.keys())
    expected_names = {"id", "order_id", "retailer_id", "wholesaler_id",
                       "declared_amount", "method", "transfer_reference", "status",
                       "idempotency_key", "submitted_by", "submitted_at",
                       "confirmed_by", "confirmed_at", "confirmation_payment_id",
                       "rejected_by", "rejected_at", "reason"}
    extra = actual_names - expected_names
    missing = expected_names - actual_names
    if extra:
        failures.append(f"{schema}.payment_declarations: unexpected columns {sorted(extra)}")
    if missing:
        failures.append(f"{schema}.payment_declarations: missing columns {sorted(missing)}")

    # Exact types, lengths, precision and nullability
    type_checks = {
        "id": ("uuid", True),
        "order_id": ("uuid", True),
        "retailer_id": ("uuid", True),
        "wholesaler_id": ("uuid", True),
        "declared_amount": ("numeric(12,2)", True),
        "method": ("character varying(16)", True),
        "transfer_reference": ("character varying(128)", False),
        "status": ("character varying(16)", True),
        "idempotency_key": ("character varying(64)", True),
        "submitted_by": ("uuid", True),
        "submitted_at": ("timestamp with time zone", True),
        "confirmed_by": ("uuid", False),
        "confirmed_at": ("timestamp with time zone", False),
        "confirmation_payment_id": ("uuid", False),
        "rejected_by": ("uuid", False),
        "rejected_at": ("timestamp with time zone", False),
        "reason": ("character varying(256)", False),
    }
    for col_name, (exp_type, exp_notnull) in type_checks.items():
        c = col_map.get(col_name)
        if c is None:
            continue  # caught above
        # For types with explicit length/precision/scale, require exact match;
        # for types without (uuid, integer, timestamp), starts-with is sufficient.
        if "(" in exp_type:
            if exp_type not in c[1]:
                failures.append(
                    f"{schema}.payment_declarations.{col_name}: type {c[1]} expected {exp_type}")
        elif not c[1].startswith(exp_type):
            failures.append(
                f"{schema}.payment_declarations.{col_name}: type {c[1]} expected ~{exp_type}")
        if c[2] != exp_notnull:
            failures.append(
                f"{schema}.payment_declarations.{col_name}: not_null={c[2]} expected {exp_notnull}")

    # Status must have DEFAULT 'pending' (reject missing or wrong default)
    status_col = col_map.get("status")
    if status_col:
        default = status_col[3] or ""
        if "'pending'" not in default.lower():
            failures.append(
                f"{schema}.payment_declarations.status: DEFAULT must be 'pending', got {default!r}")

    # Exact CHECK semantics (normalised — reject OR TRUE, extra values, weakeners)
    constraints = _pg_catalog_constraints(bind, schema, PAYMENT_DECLARATIONS)
    check_defs = [r[2] for r in constraints if r[1] in (b"c", "c")]
    check_norm = [_normalize_check_expr(d) for d in check_defs]

    # method IN ('cash','transfer')
    if not any(_check_in_allowed_values(n, "method", ("cash", "transfer")) for n in check_norm):
        failures.append(f"{schema}.payment_declarations: CHECK method must be exactly IN ('cash','transfer')")
    # status IN ('pending','confirmed','rejected')
    if not any(_check_in_allowed_values(n, "status", ("pending", "confirmed", "rejected"))
               for n in check_norm):
        failures.append(
            f"{schema}.payment_declarations: CHECK status must be exactly IN ('pending','confirmed','rejected')")
    # declared_amount > 0 (exact — reject >=, > -1, OR TRUE weakeners)
    if not any(_check_amount_positive(n) for n in check_norm):
        failures.append(f"{schema}.payment_declarations: CHECK declared_amount>0 missing/wrong")

    # FK: validate local column, target schema/table/column, delete action
    fk_defs = [r[2] for r in constraints if r[1] in (b"f", "f")]
    # order_id FK -> schema.orders(id) ON DELETE RESTRICT
    if not any("order_id" in d and f"{schema}" in d and "orders" in d
               and "(id)" in d and "RESTRICT" in d.upper() for d in fk_defs):
        failures.append(
            f"{schema}.payment_declarations: order_id FK to {schema}.orders(id) ON DELETE RESTRICT missing/wrong")
    # confirmation_payment_id FK -> schema.payments(id) ON DELETE RESTRICT
    if not any("confirmation_payment_id" in d and f"{schema}" in d and "payments" in d
               and "(id)" in d and "RESTRICT" in d.upper() for d in fk_defs):
        failures.append(
            f"{schema}.payment_declarations: confirmation_payment_id FK to {schema}.payments(id) ON DELETE RESTRICT missing/wrong")
    # Reject CASCADE on any FK
    if any("CASCADE" in d.upper() for d in fk_defs):
        failures.append(f"{schema}.payment_declarations: FK with CASCADE is forbidden")

    # Index uniqueness, exact ordered keys, exact predicate
    indexes = _pg_catalog_indexes(bind, schema, PAYMENT_DECLARATIONS)
    idx_map = {i[0]: i for i in indexes}

    # UX: unique on (retailer_id, idempotency_key)
    if UX_DECLARATIONS_RETAILER_IDEM not in idx_map:
        failures.append(f"{schema}.payment_declarations: unique index {UX_DECLARATIONS_RETAILER_IDEM} missing")
    else:
        ux = idx_map[UX_DECLARATIONS_RETAILER_IDEM]
        if not ux[1]:
            failures.append(f"{schema}.payment_declarations: {UX_DECLARATIONS_RETAILER_IDEM} must be UNIQUE")
        # pg_get_indexdef returns: CREATE UNIQUE INDEX ... ON ... (retailer_id, idempotency_key)
        ux_def = ux[2] or ""
        if "(retailer_id, idempotency_key)" not in ux_def.replace("  ", " "):
            failures.append(
                f"{schema}.payment_declarations: {UX_DECLARATIONS_RETAILER_IDEM} keys must be (retailer_id, idempotency_key)")

    # IX retailer_status
    if IX_DECLARATIONS_RETAILER_STATUS not in idx_map:
        failures.append(f"{schema}.payment_declarations: index {IX_DECLARATIONS_RETAILER_STATUS} missing")
    else:
        ix_def = idx_map[IX_DECLARATIONS_RETAILER_STATUS][2] or ""
        if "(retailer_id, status)" not in ix_def.replace("  ", " "):
            failures.append(
                f"{schema}.payment_declarations: {IX_DECLARATIONS_RETAILER_STATUS} keys must be (retailer_id, status)")

    # IX wholesaler_status
    if IX_DECLARATIONS_WHOLESALER_STATUS not in idx_map:
        failures.append(f"{schema}.payment_declarations: index {IX_DECLARATIONS_WHOLESALER_STATUS} missing")
    else:
        ix_def = idx_map[IX_DECLARATIONS_WHOLESALER_STATUS][2] or ""
        if "(wholesaler_id, status)" not in ix_def.replace("  ", " "):
            failures.append(
                f"{schema}.payment_declarations: {IX_DECLARATIONS_WHOLESALER_STATUS} keys must be (wholesaler_id, status)")


def _verify_receipt_sequences_pg(bind, schema: str, failures: list[str]) -> None:
    """R3/R4-R1: pg_catalog verification of receipt_sequences.

    Must contain exactly business_date CHAR(8) NOT NULL PK and next_seq INTEGER
    NOT NULL DEFAULT 1.  Any extra column is rejected.
    """
    cols = _pg_catalog_columns(bind, schema, RECEIPT_SEQUENCES)
    col_map = {c[0]: c for c in cols}

    # Exact column set — only business_date and next_seq
    actual_names = set(col_map.keys())
    expected_names = {"business_date", "next_seq"}
    extra = actual_names - expected_names
    missing = expected_names - actual_names
    if extra:
        failures.append(f"{schema}.receipt_sequences: unexpected columns {sorted(extra)}")
    if missing:
        failures.append(f"{schema}.receipt_sequences: missing columns {sorted(missing)}")

    # business_date CHAR(8) NOT NULL PK
    if "business_date" not in col_map:
        failures.append(f"{schema}.receipt_sequences: business_date column missing")
    else:
        bd = col_map["business_date"]
        if bd[1] != "character(8)":
            failures.append(f"{schema}.receipt_sequences.business_date: expected character(8), got {bd[1]}")
        if not bd[2]:
            failures.append(f"{schema}.receipt_sequences.business_date: must be NOT NULL (PK)")

    # next_seq INTEGER NOT NULL DEFAULT 1
    if "next_seq" not in col_map:
        failures.append(f"{schema}.receipt_sequences: next_seq column missing")
    else:
        ns = col_map["next_seq"]
        if ns[1] != "integer":
            failures.append(f"{schema}.receipt_sequences.next_seq: expected integer, got {ns[1]}")
        if not ns[2]:
            failures.append(f"{schema}.receipt_sequences.next_seq: must be NOT NULL")
        # DEFAULT must be exactly 1 (PG stores as '1' or '1::integer')
        default = ns[3] or ""
        # Extract the leading numeric token from the default expression
        m = re.match(r"'?(\d+)", default.strip())
        if not m or m.group(1) != "1":
            failures.append(
                f"{schema}.receipt_sequences.next_seq: DEFAULT must be 1, got {default!r}")

    # PK constraint must exist on business_date
    constraints = _pg_catalog_constraints(bind, schema, RECEIPT_SEQUENCES)
    pk_defs = [r[2] for r in constraints if r[1] in (b"p", "p")]
    if not any("business_date" in d for d in pk_defs):
        failures.append(f"{schema}.receipt_sequences: PRIMARY KEY on business_date missing")


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
        f"WHERE role_id IN (SELECT id FROM {roles_t} WHERE name != :admin_role) "
        f"AND permission_id IN (SELECT id FROM {perms_t} WHERE code = :confirm_code)"
    ), {"admin_role": ADMIN_ROLE, "confirm_code": NEW_CONFIRM_PERM})


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
