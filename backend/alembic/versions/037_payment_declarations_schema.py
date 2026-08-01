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
# R4-R2: PostgreSQL catalog identity validators
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

# FK constraint with full catalog identity: conkey/confkey/confrelid/confdeltype
PG_CATALOG_FK_SQL = """
    SELECT c.conname, c.conkey, c.confkey,
           c.confrelid::regclass::text AS target_table,
           c.confdeltype
    FROM pg_catalog.pg_constraint c
    JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = :schema AND t.relname = :table_name AND c.contype = 'f'
"""

# Index with full catalog identity: indkey/indpred/indisunique/indnatts/indnkeyatts
PG_CATALOG_INDEX_SQL = """
    SELECT ic.relname AS index_name,
           i.indisunique,
           i.indisprimary,
           i.indkey,
           i.indpred,
           pg_catalog.pg_get_expr(i.indpred, i.indrelid) AS pred_text,
           i.indnatts,
           i.indnkeyatts
    FROM pg_catalog.pg_index i
    JOIN pg_catalog.pg_class t ON t.oid = i.indrelid
    JOIN pg_catalog.pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = :schema AND t.relname = :table_name
"""

# CHECK constraint with pg_get_expr on conbin
PG_CATALOG_CHECK_SQL = """
    SELECT c.conname, c.conbin,
           pg_catalog.pg_get_expr(c.conbin, c.conrelid) AS check_expr
    FROM pg_catalog.pg_constraint c
    JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = :schema AND t.relname = :table_name AND c.contype = 'c'
"""

# PK constraint
PG_CATALOG_PK_SQL = """
    SELECT c.conname, c.conkey
    FROM pg_catalog.pg_constraint c
    JOIN pg_catalog.pg_class t ON t.oid = c.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = :schema AND t.relname = :table_name AND c.contype = 'p'
"""


def _pg_catalog_columns(bind, schema, table_name):
    """Return list of (column_name, data_type, not_null, column_default)."""
    return bind.execute(
        sa.text(PG_CATALOG_COLUMNS_SQL),
        {"schema": schema, "table_name": table_name},
    ).fetchall()


def _attnum_map(bind, schema, table_name):
    """Return {attnum: column_name} for resolving conkey/confkey/indkey."""
    rows = bind.execute(sa.text("""
        SELECT a.attnum, a.attname
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema AND c.relname = :table_name
          AND a.attnum > 0 AND NOT a.attisdropped
    """), {"schema": schema, "table_name": table_name}).fetchall()
    return {r[0]: r[1] for r in rows}


def _normalize_int2vector(val) -> list[int]:
    """Normalise a PG int2vector (conkey/confkey/indkey) from any driver
    representation to a list of ints."""
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [int(x) for x in val]
    raw = str(val).strip("[]{}()")
    return [int(x) for x in raw.replace(",", " ").split() if x.strip()]


def _resolve_indkey(indkey_val, attnum_map: dict) -> tuple[str, ...]:
    """Resolve pg_index.indkey to ordered column names.

    Expression columns use attnum 0 — represented as ``"<expr>"`` so callers
    can detect and reject them.
    """
    nums = _normalize_int2vector(indkey_val)
    result = []
    for n in nums:
        if n == 0:
            result.append("<expr>")
        else:
            result.append(attnum_map.get(n, f"?{n}"))
    return tuple(result)


def _normalize_expr(expr: str) -> str:
    """Normalise a pg_get_expr output for semantic comparison."""
    return re.sub(r"\s+", " ", (expr or "")).strip().lower()


# DELETE action codes (confdeltype) — may arrive as bytes or str
_DELETE_RESTRICT_CODES = ("r", b"r")


def _is_restrict(confdeltype) -> bool:
    """Check if confdeltype is RESTRICT, handling both bytes and str."""
    return confdeltype in _DELETE_RESTRICT_CODES


def _preflight_semantic(bind, rows: list[dict[str, Any]]) -> None:
    """R4-R2: PostgreSQL catalog identity validators for exact column sets,
    types, lengths, precision/scale, nullability, defaults, PK/FK
    targets/delete actions, exact CHECK expressions, index
    uniqueness/keys/predicates.  Fails closed — no mutation occurs."""
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
        pay_cols = {c[0]: c for c in _pg_catalog_columns(bind, schema, PAYMENTS)}
        ti = pay_cols.get("transaction_id")
        if ti is None:
            failures.append(f"{schema}.payments: transaction_id column missing")
        else:
            if ti[1] not in ("character varying(64)", "character varying(128)"):
                failures.append(
                    f"{schema}.payments.transaction_id: expected VARCHAR(64) or VARCHAR(128), got {ti[1]}")
            if ti[2] is not False:
                failures.append(f"{schema}.payments.transaction_id: must be NOT NULL")

        # --- payments.receipt_number (may already exist from prior upgrade) ---
        rn = pay_cols.get("receipt_number")
        if rn:
            if rn[1] != "character varying(32)":
                failures.append(f"{schema}.payments.receipt_number: expected VARCHAR(32), got {rn[1]}")
            if rn[2]:
                failures.append(f"{schema}.payments.receipt_number: must be nullable")
            # Verify partial unique index via catalog identity
            _verify_partial_index(bind, schema, PAYMENTS, UX_PAYMENTS_RECEIPT_NUMBER,
                                  ("receipt_number",), "(receipt_number is not null)",
                                  failures)

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
            _verify_declaration_catalog(bind, schema, failures)

        # --- receipt_sequences ---
        if _table_exists(bind, schema, RECEIPT_SEQUENCES):
            _verify_receipt_sequences_catalog(bind, schema, failures)

    if failures:
        raise PreflightFailure("037 preflight (semantic) failed: " + "; ".join(failures))


def _check_is_exact_in(check_expr: str, column: str,
                       allowed: tuple[str, ...]) -> bool:
    """Verify a CHECK expression is the exact PG16 canonical shape.

    PG16 normalises ``IN ('a','b')`` to::

        ((col)::text = ANY ((ARRAY['a'::character varying, 'b'::character varying])::text[]))

    We build the expected canonical string and compare normalised form
    exactly.  This rejects extra AND/OR predicates, alternate operators,
    ``OR 1=1``, ``NOT IN``, ``<>`` chains and any non-equivalent shape.
    """
    expected = _build_canonical_any_expr(column, allowed)
    return _normalize_expr(check_expr) == expected


def _build_canonical_any_expr(column: str,
                              allowed: tuple[str, ...]) -> str:
    """Build the exact normalised PG16 expression for ``column IN (allowed)``."""
    arr_items = ", ".join(f"'{v}'::character varying" for v in allowed)
    expr = (
        f"(({column})::text = ANY "
        f"((ARRAY[{arr_items}])::text[]))"
    )
    return _normalize_expr(expr)


def _check_is_exact_amount_positive(check_expr: str) -> bool:
    """Verify CHECK is the exact PG16 canonical ``declared_amount > 0`` shape.

    PG16 normalises to ``(declared_amount > (0)::numeric)``.
    Exact comparison rejects ``>=``, ``AND amount < 10``, ``OR 1=1``, etc.
    """
    expected = _normalize_expr("(declared_amount > (0)::numeric)")
    return _normalize_expr(check_expr) == expected


def _normalize_default(expr: str) -> str:
    """Normalise a default expression: lowercase + collapse whitespace only.
    Does NOT strip type casts (use anchored allowlists instead)."""
    return re.sub(r"\s+", " ", (expr or "")).strip().lower()


# Anchored canonical default allowlists — exact expressions PG16 stores.
_STATUS_DEFAULT_CANONICAL = {
    "'pending'::character varying",
}
_NEXT_SEQ_DEFAULT_CANONICAL = {
    "1",
}


def _verify_declaration_catalog(bind, schema: str, failures: list[str]) -> None:
    """R4-R2: Catalog identity verification of payment_declarations."""
    col_rows = _pg_catalog_columns(bind, schema, PAYMENT_DECLARATIONS)
    col_map = {c[0]: c for c in col_rows}

    # Exact column set — no extras, no missing
    expected_names = {"id", "order_id", "retailer_id", "wholesaler_id",
                       "declared_amount", "method", "transfer_reference", "status",
                       "idempotency_key", "submitted_by", "submitted_at",
                       "confirmed_by", "confirmed_at", "confirmation_payment_id",
                       "rejected_by", "rejected_at", "reason"}
    extra = set(col_map) - expected_names
    missing = expected_names - set(col_map)
    if extra:
        failures.append(f"{schema}.payment_declarations: unexpected columns {sorted(extra)}")
    if missing:
        failures.append(f"{schema}.payment_declarations: missing columns {sorted(missing)}")

    # Exact types and nullability
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
            continue
        # Exact format_type equality — no substring/prefix matching
        if c[1] != exp_type:
            failures.append(
                f"{schema}.payment_declarations.{col_name}: type {c[1]!r} expected {exp_type!r}")
        if c[2] != exp_notnull:
            failures.append(
                f"{schema}.payment_declarations.{col_name}: not_null={c[2]} expected {exp_notnull}")

    # status DEFAULT: anchored canonical allowlist — exact expression match
    status_col = col_map.get("status")
    if status_col:
        norm = _normalize_default(status_col[3] or "")
        if norm not in _STATUS_DEFAULT_CANONICAL:
            failures.append(
                f"{schema}.payment_declarations.status: DEFAULT must be 'pending'::character varying, got {status_col[3]!r}")

    # CHECK constraints via pg_get_expr(conbin) — exact allowlist comparison
    check_rows = bind.execute(
        sa.text(PG_CATALOG_CHECK_SQL),
        {"schema": schema, "table_name": PAYMENT_DECLARATIONS},
    ).fetchall()
    check_exprs = [r[2] for r in check_rows]

    if not any(_check_is_exact_in(e, "method", ("cash", "transfer")) for e in check_exprs):
        failures.append(f"{schema}.payment_declarations: CHECK method must be exactly IN ('cash','transfer')")
    if not any(_check_is_exact_in(e, "status", ("pending", "confirmed", "rejected")) for e in check_exprs):
        failures.append(
            f"{schema}.payment_declarations: CHECK status must be exactly IN ('pending','confirmed','rejected')")
    if not any(_check_is_exact_amount_positive(e) for e in check_exprs):
        failures.append(f"{schema}.payment_declarations: CHECK declared_amount>0 missing/wrong")

    # FK constraints via catalog identity: resolve complete conkey/confkey
    # vectors to column names; require exactly one column per FK.
    decl_attnum_map = _attnum_map(bind, schema, PAYMENT_DECLARATIONS)
    fk_rows = bind.execute(
        sa.text(PG_CATALOG_FK_SQL),
        {"schema": schema, "table_name": PAYMENT_DECLARATIONS},
    ).fetchall()

    # Expected FKs: (local_col_name, target_qualified, ref_col_name, desc)
    expected_fks = [
        ("order_id", f"{schema}.orders", "id", "orders(id)"),
        ("confirmation_payment_id", f"{schema}.payments", "id", "payments(id)"),
    ]
    for exp_local_col, exp_target, exp_ref_col, desc in expected_fks:
        found = False
        for fk in fk_rows:
            conkey = _normalize_int2vector(fk[1])
            confkey = _normalize_int2vector(fk[2])
            target = fk[3]
            confdeltype = fk[4]
            # Require exactly one column in both vectors (reject composite FK)
            if len(conkey) != 1 or len(confkey) != 1:
                continue
            local_col = decl_attnum_map.get(conkey[0])
            if local_col != exp_local_col or target != exp_target:
                continue
            if not _is_restrict(confdeltype):
                continue
            # Verify referenced column name matches
            target_schema, target_table = target.rsplit(".", 1)
            ref_cols = _attnum_map(bind, target_schema, target_table)
            ref_col_name = ref_cols.get(confkey[0])
            if ref_col_name == exp_ref_col:
                found = True
                break
        if not found:
            failures.append(
                f"{schema}.payment_declarations: {exp_local_col} FK to {desc} ON DELETE RESTRICT missing/wrong")

    # Reject any FK with non-RESTRICT delete action
    for fk in fk_rows:
        if not _is_restrict(fk[4]):
            conkey = _normalize_int2vector(fk[1])
            local_col = decl_attnum_map.get(conkey[0], "?") if conkey else "?"
            failures.append(
                f"{schema}.payment_declarations: FK on {local_col} has delete action {fk[4]!r}, must be RESTRICT")

    # Index validation via catalog identity: indkey/indpred/indisunique
    pay_attnum = _attnum_map(bind, schema, PAYMENT_DECLARATIONS)
    _verify_index_catalog(bind, schema, PAYMENT_DECLARATIONS, pay_attnum,
                          UX_DECLARATIONS_RETAILER_IDEM, True, ("retailer_id", "idempotency_key"), None, failures)
    _verify_index_catalog(bind, schema, PAYMENT_DECLARATIONS, pay_attnum,
                          IX_DECLARATIONS_RETAILER_STATUS, False, ("retailer_id", "status"), None, failures)
    _verify_index_catalog(bind, schema, PAYMENT_DECLARATIONS, pay_attnum,
                          IX_DECLARATIONS_WHOLESALER_STATUS, False, ("wholesaler_id", "status"), None, failures)


def _verify_index_catalog(bind, schema, table_name, attnum_map,
                          index_name, expect_unique, expect_keys, expect_pred,
                          failures):
    """Verify index via pg_index catalog columns.

    Checks: indisunique, indkey (every entry, reject expression keys),
    indnatts/indnkeyatts (no INCLUDE columns, no extra keys), indpred.
    """
    rows = bind.execute(
        sa.text(PG_CATALOG_INDEX_SQL),
        {"schema": schema, "table_name": table_name},
    ).fetchall()
    idx = None
    for r in rows:
        if r[0] == index_name:
            idx = r
            break
    if idx is None:
        failures.append(f"{schema}.{table_name}: index {index_name} missing")
        return
    is_unique = idx[1]
    indkey = idx[3]
    indpred_node = idx[4]
    pred_text = idx[5]
    indnatts = idx[6]
    indnkeyatts = idx[7]

    if is_unique != expect_unique:
        failures.append(
            f"{schema}.{table_name}: {index_name} unique={is_unique}, expected {expect_unique}")

    # Resolve all indkey entries — expression keys (attnum 0) are flagged as <expr>
    actual_keys = _resolve_indkey(indkey, attnum_map)
    if "<expr>" in actual_keys:
        failures.append(
            f"{schema}.{table_name}: {index_name} must not contain expression columns, got {actual_keys}")
    if actual_keys != tuple(expect_keys):
        failures.append(
            f"{schema}.{table_name}: {index_name} keys={actual_keys}, expected {expect_keys}")

    # Reject INCLUDE columns (indnatts > indnkeyatts)
    if indnatts != indnkeyatts:
        failures.append(
            f"{schema}.{table_name}: {index_name} has INCLUDE columns "
            f"(indnatts={indnatts}, indnkeyatts={indnkeyatts})")

    if expect_pred is None:
        if indpred_node is not None:
            failures.append(
                f"{schema}.{table_name}: {index_name} must not have a predicate, got {pred_text!r}")
    else:
        if indpred_node is None:
            failures.append(
                f"{schema}.{table_name}: {index_name} missing required predicate {expect_pred!r}")
        else:
            norm_pred = _normalize_expr(pred_text)
            if norm_pred != expect_pred:
                failures.append(
                    f"{schema}.{table_name}: {index_name} predicate={norm_pred!r}, expected {expect_pred!r}")


def _verify_partial_index(bind, schema, table_name, index_name,
                          expect_keys, expect_pred, failures):
    """Verify a partial unique index on payments."""
    attnum_map = _attnum_map(bind, schema, table_name)
    _verify_index_catalog(bind, schema, table_name, attnum_map,
                          index_name, True, expect_keys, expect_pred, failures)


def _verify_receipt_sequences_catalog(bind, schema: str, failures: list[str]) -> None:
    """R4-R2: Catalog identity verification of receipt_sequences."""
    col_rows = _pg_catalog_columns(bind, schema, RECEIPT_SEQUENCES)
    col_map = {c[0]: c for c in col_rows}

    # Exact column set — only business_date and next_seq
    expected_names = {"business_date", "next_seq"}
    extra = set(col_map) - expected_names
    missing = expected_names - set(col_map)
    if extra:
        failures.append(f"{schema}.receipt_sequences: unexpected columns {sorted(extra)}")
    if missing:
        failures.append(f"{schema}.receipt_sequences: missing columns {sorted(missing)}")

    # business_date CHAR(8) NOT NULL PK
    bd = col_map.get("business_date")
    if bd is None:
        failures.append(f"{schema}.receipt_sequences: business_date column missing")
    else:
        if bd[1] != "character(8)":
            failures.append(f"{schema}.receipt_sequences.business_date: expected character(8), got {bd[1]}")
        if not bd[2]:
            failures.append(f"{schema}.receipt_sequences.business_date: must be NOT NULL (PK)")

    # next_seq INTEGER NOT NULL DEFAULT 1
    ns = col_map.get("next_seq")
    if ns is None:
        failures.append(f"{schema}.receipt_sequences: next_seq column missing")
    else:
        if ns[1] != "integer":
            failures.append(f"{schema}.receipt_sequences.next_seq: expected integer, got {ns[1]}")
        if not ns[2]:
            failures.append(f"{schema}.receipt_sequences.next_seq: must be NOT NULL")
        # DEFAULT: anchored canonical allowlist — exact expression match
        norm = _normalize_default(ns[3] or "")
        if norm not in _NEXT_SEQ_DEFAULT_CANONICAL:
            failures.append(
                f"{schema}.receipt_sequences.next_seq: DEFAULT must be 1, got {ns[3]!r}")

    # PK constraint via catalog identity: conkey must be exactly [business_date]
    pk_rows = bind.execute(
        sa.text(PG_CATALOG_PK_SQL),
        {"schema": schema, "table_name": RECEIPT_SEQUENCES},
    ).fetchall()
    attnum_map = _attnum_map(bind, schema, RECEIPT_SEQUENCES)
    name_to_attnum = {v: k for k, v in attnum_map.items()}
    bd_attnum = name_to_attnum.get("business_date")
    found_pk = False
    for pk in pk_rows:
        conkey = _normalize_int2vector(pk[1])
        # Must be exactly one column (reject composite PK)
        if len(conkey) != 1:
            continue
        if bd_attnum is not None and conkey[0] == bd_attnum:
            found_pk = True
            break
    if not found_pk:
        failures.append(f"{schema}.receipt_sequences: PRIMARY KEY on exactly business_date missing")


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
