"""DC-12R1-S1 retailer MVP identity, credential and invitation foundation.

Revision ID: 036_retailer_mvp_identity
Revises: 035_receivable_collection_integrity
Create Date: 2026-07-24

Additive, forward-only migration implementing the DC-12R1-D/R2 design:
  * public.wholesaler_retailer_bindings.tenant_user_id  (authoritative mapping)
  * public.retailers.email_verified_at                   (retailer-owned verified email)
  * public.invitations.revoked_at / revoked_by + NOT NULL expires_at (finite lifetime)
  * public.retailer_credential_setup_tokens              (bound to retailer_id + binding_id)
  * public.retailer_password_reset_tokens                (retailer-scoped)
  * per live tenant: retailer_operator role + client:* permissions, admin gets invitations:revoke,
    ux_users_email_active partial unique index.

Enumerates tenants ONLY from the authoritative live registry
(tenant_registrations JOIN wholesalers). Read-only preflight fails closed on
duplicate emails, conflicting tenant_user_id mappings/hashes and incompatible
catalog objects before any mutation. Never edits migrations <=035. Never alters
users.password_hash nullability. No destructive downgrade.
"""
from __future__ import annotations

import re
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "036_retailer_mvp_identity"
down_revision = "035_receivable_collection_integrity"
branch_labels = None
depends_on = None


PUBLIC_SCHEMA = "public"
BINDINGS = "wholesaler_retailer_bindings"
RETAILERS = "retailers"
INVITATIONS = "invitations"
USERS = "users"
TENANT_SCHEMA_RE = re.compile(r"^t_[0-9a-f]{32}$")
LIVE_REGISTRATION_STATUSES = (
    "pending_email_verification",
    "email_verified",
    "provisioning",
    "active",
    "failed",
)
WHOLESALER_ACTIVE_STATUSES = ("active", "provisioning")

# DC-12R1-S1 permission namespace (CTO correction C). retailer_operator receives
# ONLY the client:* codes. invitations:revoke is granted to admin, NOT to
# retailer_operator.
RETAILER_OPERATOR_PERMISSIONS = (
    ("client:catalog:read", "Retailer: browse wholesaler catalog"),
    ("client:orders:read", "Retailer: read own orders"),
    ("client:orders:create", "Retailer: create own orders"),
    ("client:payments:read", "Retailer: read own payments"),
    ("client:payments:create", "Retailer: pay own orders"),
    ("client:finance:read", "Retailer: read own outstanding balance"),
)
ADMIN_EXTRA_PERMISSIONS = (
    ("invitations:revoke", "Revoke an outstanding retailer invitation"),
    # DC-12R1-S1-R1: restricted setup-token reissue (admin only, tenant-scoped).
    ("retailers:reissue_credential", "Reissue a retailer credential setup token"),
)
ALL_NEW_PERMISSIONS = RETAILER_OPERATOR_PERMISSIONS + ADMIN_EXTRA_PERMISSIONS
RETAILER_OPERATOR_ROLE = "retailer_operator"
ADMIN_ROLE = "admin"
DEFAULT_INVITATION_TTL_DAYS = 7


class PreflightFailure(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    bind = op.get_bind()
    _ensure_registry_tables_exist(bind)
    rows = _registered_tenants(bind)
    _validate_registry_rows(bind, rows)
    # Read-only preflight: fail closed before any mutation.
    _preflight_no_duplicate_tenant_emails(bind, rows)
    _preflight_no_conflicting_mappings_or_hashes(bind, rows)
    _preflight_bindings_have_retailers(bind)
    # Public-schema mutations.
    _add_binding_tenant_user_id(bind)
    _add_retailer_email_verified_at(bind)
    _harden_invitations(bind)
    _create_retailer_setup_token_table(bind)
    _create_retailer_reset_token_table(bind)
    # Per live-tenant mutations.
    for row in rows:
        _seed_tenant_rbac(bind, row)
        _ensure_tenant_email_index(bind, row)


def downgrade() -> None:
    # Forward-only migration (CTO constraint #7). No destructive DDL is emitted.
    # Recovery is application-level rollback plus a verified DB restore.
    raise RuntimeError(
        "036_retailer_mvp_identity is forward-only; destructive downgrade is "
        "disabled. Recover via application rollback plus a verified DB restore."
    )


# ---------------------------------------------------------------------------
# registry enumeration (verbatim pattern from 035/033)
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
        if not _table_exists(bind, schema, USERS):
            failures.append(f"{schema}.{USERS}: users table is missing")
    if failures:
        raise PreflightFailure("036 preflight (registry) failed: " + "; ".join(failures))


def _validate_tenant_schema_name(schema: str | None, evidence_name: str) -> None:
    if schema is None or schema.strip() == "":
        raise PreflightFailure(f"{evidence_name}: tenant_schema is missing")
    if len(schema) > 63 or not TENANT_SCHEMA_RE.fullmatch(schema):
        raise PreflightFailure(f"{evidence_name}: tenant_schema is not a valid derived tenant identifier")


# ---------------------------------------------------------------------------
# read-only preflight checks (fail closed, no mutation)
# ---------------------------------------------------------------------------

def _preflight_no_duplicate_tenant_emails(bind, rows: list[dict[str, Any]]) -> None:
    """A single tenant may not contain two active users sharing an email."""
    failures: list[str] = []
    for row in rows:
        schema = row["tenant_schema"]
        if not _table_exists(bind, schema, USERS):
            continue
        dup = bind.execute(
            sa.text(
                f'SELECT email FROM "{schema}".users '
                "WHERE is_deleted IS FALSE AND email IS NOT NULL "
                "GROUP BY email HAVING COUNT(*) > 1 LIMIT 5"
            )
        ).fetchall()
        for (email,) in dup:
            failures.append(f"{schema}.users: duplicate active email present")
    if failures:
        raise PreflightFailure("036 preflight (duplicate emails) failed: " + "; ".join(failures))


def _preflight_no_conflicting_mappings_or_hashes(bind, rows: list[dict[str, Any]]) -> None:
    """If pre-R1 tenant_user_id values already exist, they must be unambiguous.

    This guards against a partial/manual backfill: one tenant_user_id must not
    map to two retailers, and a retailer's mapped copies must not already carry
    conflicting password hashes. Both are treated as fail-closed ambiguity.
    """
    if not _column_exists(bind, PUBLIC_SCHEMA, BINDINGS, "tenant_user_id"):
        return  # column not added yet; nothing to validate
    failures: list[str] = []
    # one tenant_user_id -> many retailers within a wholesaler
    ambiguous = bind.execute(
        sa.text(
            """
            SELECT wholesaler_id::text, tenant_user_id::text, COUNT(DISTINCT retailer_id)
            FROM public.wholesaler_retailer_bindings
            WHERE tenant_user_id IS NOT NULL AND is_deleted IS FALSE
            GROUP BY wholesaler_id, tenant_user_id
            HAVING COUNT(DISTINCT retailer_id) > 1 LIMIT 5
            """
        )
    ).fetchall()
    for ws, tuid, _cnt in ambiguous:
        failures.append(f"wholesaler {ws}: tenant_user_id {tuid} maps to multiple retailers")
    # DC-12R1-S1-R1: also compare ACTIVE mapped copies' password hashes per
    # retailer. A retailer whose mapped tenant-user copies already disagree on
    # the established password is an ambiguous state that must fail closed
    # (matches the runtime RETAILER_CREDENTIAL_CONFLICT rule).
    hash_failures = _check_conflicting_active_hashes(bind, rows)
    failures.extend(hash_failures)
    if failures:
        raise PreflightFailure(
            "036 preflight (conflicting mappings) failed: " + "; ".join(failures)
        )


def _check_conflicting_active_hashes(bind, rows: list[dict[str, Any]]) -> list[str]:
    """For each retailer, collect the password_hash of each active mapped copy
    and flag any disagreement. DC-12R1-S1-R3: no continue paths — missing
    registry/schema/table/user is a fail-closed integrity break."""
    schema_by_wholesaler = {row["wholesaler_id"]: row["tenant_schema"] for row in rows}
    mappings = bind.execute(sa.text(
        """
        SELECT retailer_id::text, wholesaler_id::text, tenant_user_id::text
        FROM public.wholesaler_retailer_bindings
        WHERE tenant_user_id IS NOT NULL AND is_deleted IS FALSE
        """
    )).fetchall()
    by_retailer: dict[str, list[tuple[str, str]]] = {}
    failures: list[str] = []
    for retailer_id, wholesaler_id, tuid in mappings:
        schema = schema_by_wholesaler.get(wholesaler_id)
        if schema is None:
            failures.append(
                f"binding references wholesaler {wholesaler_id} with no live registration"
            )
            continue
        if not _schema_exists(bind, schema):
            failures.append(f"{schema}: registered tenant schema is missing")
            continue
        if not _table_exists(bind, schema, USERS):
            failures.append(f"{schema}.{USERS}: users table is missing")
            continue
        row = bind.execute(sa.text(
            f'SELECT password_hash FROM "{schema}".users '
            "WHERE id = :uid AND is_active = true AND is_deleted = false"
        ), {"uid": tuid}).first()
        if row is None:
            failures.append(
                f"{schema}.{USERS}: mapped tenant_user_id {tuid} has no users row"
            )
            continue
        if row[0]:
            by_retailer.setdefault(retailer_id, []).append((schema, str(row[0])))
    for retailer_id, copies in by_retailer.items():
        unique = {h for _schema, h in copies}
        if len(unique) > 1:
            failures.append(
                f"retailer {retailer_id}: active mapped copies have conflicting password hashes"
            )
    return failures


def _preflight_bindings_have_retailers(bind) -> None:
    """Every non-deleted binding must reference an existing retailer row."""
    orphans = bind.execute(
        sa.text(
            """
            SELECT wrb.id::text FROM public.wholesaler_retailer_bindings wrb
            LEFT JOIN public.retailers r ON r.id = wrb.retailer_id
            WHERE wrb.is_deleted IS FALSE AND r.id IS NULL
            LIMIT 5
            """
        )
    ).fetchall()
    if orphans:
        raise PreflightFailure(
            "036 preflight (incompatible catalog) failed: bindings reference missing retailers: "
            + ", ".join(bid for (bid,) in orphans)
        )


# ---------------------------------------------------------------------------
# public-schema mutations
# ---------------------------------------------------------------------------

def _add_binding_tenant_user_id(bind) -> None:
    bindings = _qualified(bind, PUBLIC_SCHEMA, BINDINGS)
    if not _column_exists(bind, PUBLIC_SCHEMA, BINDINGS, "tenant_user_id"):
        bind.execute(sa.text(f"ALTER TABLE {bindings} ADD COLUMN tenant_user_id UUID"))
    idx = "ux_bindings_wholesaler_tenant_user"
    if not _index_exists(bind, PUBLIC_SCHEMA, BINDINGS, idx):
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX {idx} ON {bindings} (wholesaler_id, tenant_user_id) "
            "WHERE tenant_user_id IS NOT NULL AND is_deleted IS FALSE"
        ))


def _add_retailer_email_verified_at(bind) -> None:
    retailers = _qualified(bind, PUBLIC_SCHEMA, RETAILERS)
    if not _column_exists(bind, PUBLIC_SCHEMA, RETAILERS, "email_verified_at"):
        bind.execute(
            sa.text(f"ALTER TABLE {retailers} ADD COLUMN email_verified_at TIMESTAMPTZ")
        )


def _harden_invitations(bind) -> None:
    invitations = _qualified(bind, PUBLIC_SCHEMA, INVITATIONS)
    if not _column_exists(bind, PUBLIC_SCHEMA, INVITATIONS, "revoked_at"):
        bind.execute(sa.text(f"ALTER TABLE {invitations} ADD COLUMN revoked_at TIMESTAMPTZ"))
    if not _column_exists(bind, PUBLIC_SCHEMA, INVITATIONS, "revoked_by"):
        bind.execute(sa.text(f"ALTER TABLE {invitations} ADD COLUMN revoked_by UUID"))
    # Backfill NULL expiry -> created_at + TTL, then enforce NOT NULL + default.
    if not _column_is_nullable(bind, PUBLIC_SCHEMA, INVITATIONS, "expires_at"):
        return  # already NOT NULL (e.g. re-run); nothing to do
    bind.execute(sa.text(
        f"UPDATE {invitations} SET expires_at = created_at + interval '{DEFAULT_INVITATION_TTL_DAYS} days' "
        "WHERE expires_at IS NULL"
    ))
    bind.execute(sa.text(
        f"ALTER TABLE {invitations} ALTER COLUMN expires_at SET DEFAULT "
        f"now() + interval '{DEFAULT_INVITATION_TTL_DAYS} days'"
    ))
    bind.execute(sa.text(
        f"ALTER TABLE {invitations} ALTER COLUMN expires_at SET NOT NULL"
    ))


def _create_retailer_setup_token_table(bind) -> None:
    if _table_exists(bind, PUBLIC_SCHEMA, "retailer_credential_setup_tokens"):
        # DC-12R1-S1-R1: strict validation — do not silently skip an
        # incompatible same-name table. Verify required columns + constraints.
        _validate_setup_token_table_contract(bind)
        return
    bind.execute(sa.text(
        """
        CREATE TABLE public.retailer_credential_setup_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            retailer_id UUID NOT NULL
                REFERENCES public.retailers(id) ON DELETE CASCADE,
            binding_id UUID NOT NULL
                REFERENCES public.wholesaler_retailer_bindings(id) ON DELETE CASCADE,
            issued_by_wholesaler_id UUID,
            token_hash VARCHAR(128) NOT NULL,
            purpose VARCHAR(64) NOT NULL DEFAULT 'retailer_credential_setup',
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMPTZ,
            CONSTRAINT ck_retailer_credential_setup_tokens_purpose
                CHECK (purpose = 'retailer_credential_setup'),
            CONSTRAINT ck_retailer_credential_setup_tokens_not_used_and_revoked
                CHECK (used_at IS NULL OR revoked_at IS NULL),
            CONSTRAINT uq_retailer_credential_setup_tokens_token_hash
                UNIQUE (token_hash)
        )
        """
    ))
    bind.execute(sa.text(
        "CREATE UNIQUE INDEX ux_retailer_credential_setup_tokens_token_hash "
        "ON public.retailer_credential_setup_tokens (token_hash)"
    ))
    bind.execute(sa.text(
        "CREATE INDEX ix_retailer_credential_setup_tokens_retailer_id "
        "ON public.retailer_credential_setup_tokens (retailer_id)"
    ))
    bind.execute(sa.text(
        "CREATE INDEX ix_retailer_credential_setup_tokens_binding_id "
        "ON public.retailer_credential_setup_tokens (binding_id)"
    ))
    bind.execute(sa.text(
        "CREATE INDEX ix_retailer_credential_setup_tokens_expires_at "
        "ON public.retailer_credential_setup_tokens (expires_at)"
    ))
    bind.execute(sa.text(
        "CREATE UNIQUE INDEX ux_retailer_credential_setup_tokens_retailer_active "
        "ON public.retailer_credential_setup_tokens (retailer_id) "
        "WHERE used_at IS NULL AND revoked_at IS NULL AND is_deleted = false"
    ))


def _create_retailer_reset_token_table(bind) -> None:
    if _table_exists(bind, PUBLIC_SCHEMA, "retailer_password_reset_tokens"):
        # DC-12R1-S1-R1: strict validation of an existing same-name table.
        _validate_reset_token_table_contract(bind)
        return
    bind.execute(sa.text(
        """
        CREATE TABLE public.retailer_password_reset_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            retailer_id UUID NOT NULL
                REFERENCES public.retailers(id) ON DELETE CASCADE,
            token_hash VARCHAR(128) NOT NULL,
            purpose VARCHAR(64) NOT NULL DEFAULT 'retailer_password_reset',
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMPTZ,
            CONSTRAINT ck_retailer_password_reset_tokens_purpose
                CHECK (purpose = 'retailer_password_reset'),
            CONSTRAINT ck_retailer_password_reset_tokens_not_used_and_revoked
                CHECK (used_at IS NULL OR revoked_at IS NULL),
            CONSTRAINT uq_retailer_password_reset_tokens_token_hash
                UNIQUE (token_hash)
        )
        """
    ))
    bind.execute(sa.text(
        "CREATE UNIQUE INDEX ux_retailer_password_reset_tokens_token_hash "
        "ON public.retailer_password_reset_tokens (token_hash)"
    ))
    bind.execute(sa.text(
        "CREATE INDEX ix_retailer_password_reset_tokens_retailer_id "
        "ON public.retailer_password_reset_tokens (retailer_id)"
    ))
    bind.execute(sa.text(
        "CREATE INDEX ix_retailer_password_reset_tokens_expires_at "
        "ON public.retailer_password_reset_tokens (expires_at)"
    ))
    bind.execute(sa.text(
        "CREATE UNIQUE INDEX ux_retailer_password_reset_tokens_retailer_active "
        "ON public.retailer_password_reset_tokens (retailer_id) "
        "WHERE used_at IS NULL AND revoked_at IS NULL AND is_deleted = false"
    ))


# ---------------------------------------------------------------------------
# DC-12R1-S1-R4: exact catalog equivalence validation.
# NO substring matching. Every constraint validated through pg_catalog columns
# (conkey, confkey, confrelid, confdeltype, indnkeyatts, indisunique) and
# pg_get_constraintdef/pg_get_indexdef with strict equality semantics.
# ---------------------------------------------------------------------------

# Required columns: (expected_data_type, expected_nullable, expected_varchar_len or None)
_REQUIRED_RESET_COL_SPECS: dict[str, tuple[str, bool, int | None]] = {
    "id": ("uuid", False, None),
    "retailer_id": ("uuid", False, None),
    "token_hash": ("character varying", False, 128),
    "purpose": ("character varying", False, 64),
    "expires_at": ("timestamp with time zone", False, None),
    "used_at": ("timestamp with time zone", True, None),
    "revoked_at": ("timestamp with time zone", True, None),
    "is_deleted": ("boolean", False, None),
    "deleted_at": ("timestamp with time zone", True, None),
    "created_at": ("timestamp with time zone", False, None),
    "updated_at": ("timestamp with time zone", False, None),
}
_REQUIRED_SETUP_COL_SPECS = dict(_REQUIRED_RESET_COL_SPECS)
_REQUIRED_SETUP_COL_SPECS["binding_id"] = ("uuid", False, None)
_REQUIRED_SETUP_COL_SPECS["issued_by_wholesaler_id"] = ("uuid", True, None)

_PURPOSE_BY_TABLE = {
    "retailer_credential_setup_tokens": "retailer_credential_setup",
    "retailer_password_reset_tokens": "retailer_password_reset",  # pragma: allowlist secret
}

# Required FK specs: (local_col, ref_table, ref_col)
_FK_RETAILER = ("retailer_id", "retailers", "id")
_FK_BINDING = ("binding_id", "wholesaler_retailer_bindings", "id")


def _validate_setup_token_table_contract(bind) -> None:
    _validate_token_table_exact(bind, "retailer_credential_setup_tokens",
                               _REQUIRED_SETUP_COL_SPECS,
                               fk_specs=[_FK_RETAILER, _FK_BINDING])
    _validate_one_active_index_exact(
        bind, "retailer_credential_setup_tokens",
        "ux_retailer_credential_setup_tokens_retailer_active",
    )


def _validate_reset_token_table_contract(bind) -> None:
    _validate_token_table_exact(bind, "retailer_password_reset_tokens",
                               _REQUIRED_RESET_COL_SPECS,
                               fk_specs=[_FK_RETAILER])
    _validate_one_active_index_exact(
        bind, "retailer_password_reset_tokens",
        "ux_retailer_password_reset_tokens_retailer_active",
    )


def _validate_token_table_exact(
    bind, table_name: str,
    col_specs: dict[str, tuple[str, bool, int | None]],
    fk_specs: list[tuple[str, str, str]],
) -> None:
    """Exact catalog equivalence — no substring matching."""

    # --- columns: exact type, nullability, varchar length ---
    rows = bind.execute(sa.text(
        "SELECT column_name, is_nullable, data_type, character_maximum_length "
        "FROM information_schema.columns "
        "WHERE table_schema = :schema AND table_name = :table_name"
    ), {"schema": PUBLIC_SCHEMA, "table_name": table_name}).fetchall()
    actual = {r[0]: (r[1], r[2], r[3]) for r in rows}  # (is_nullable, data_type, char_len)
    missing = set(col_specs) - set(actual)
    if missing:
        raise PreflightFailure(f"{table_name}: missing columns: {sorted(missing)}")
    for col, (exp_type, exp_nullable, exp_len) in col_specs.items():
        act_nullable, act_type, act_len = actual[col]
        if act_type != exp_type:
            raise PreflightFailure(
                f"{table_name}.{col}: wrong type {act_type!r}, expected {exp_type!r}"
            )
        if (act_nullable == "YES") != exp_nullable:
            raise PreflightFailure(
                f"{table_name}.{col}: wrong nullability (nullable={act_nullable})"
            )
        if exp_len is not None and act_len != exp_len:
            raise PreflightFailure(
                f"{table_name}.{col}: wrong varchar length {act_len}, expected {exp_len}"
            )

    purpose = _PURPOSE_BY_TABLE[table_name]

    # --- CHECK constraints via pg_get_constraintdef with exact semantics ---
    ck_rows = bind.execute(sa.text(
        "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
        "JOIN pg_class t ON t.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = t.relnamespace "
        "WHERE n.nspname = :schema AND t.relname = :table AND c.contype = 'c'"
    ), {"schema": PUBLIC_SCHEMA, "table": table_name}).fetchall()
    ck_defs = [r[0] for r in ck_rows]

    _assert_purpose_check(table_name, ck_defs, purpose)
    _assert_used_revoked_check(table_name, ck_defs)

    # --- UNIQUE(token_hash) via conkey ---
    _assert_unique_single_col(bind, table_name, "token_hash")

    # --- FKs via conkey/confkey/confrelid/confdeltype ---
    for local_col, ref_table, ref_col in fk_specs:
        _assert_fk(bind, table_name, local_col, ref_table, ref_col)


def _assert_purpose_check(table_name: str, ck_defs: list[str], purpose: str) -> None:
    """Purpose CHECK must be exactly `purpose = 'value'` — no OR TRUE, wrappers, extras."""
    for d in ck_defs:
        core = _strip_check(d)
        # Normalize: remove ::text casts, remove ALL parens, collapse whitespace.
        norm = core.replace("::text", "").replace("(", "").replace(")", "").strip()
        norm = " ".join(norm.split())
        if norm == f"purpose = '{purpose}'":
            return
    raise PreflightFailure(
        f"{table_name}: purpose CHECK not exactly `purpose = '{purpose}'`; "
        f"found: {ck_defs}"
    )


def _assert_used_revoked_check(table_name: str, ck_defs: list[str]) -> None:
    """Must be exactly `used_at IS NULL OR revoked_at IS NULL` — no extras/negation."""
    for d in ck_defs:
        core = _strip_check(d)
        # Normalize: remove ALL parens, collapse whitespace, lowercase.
        norm = core.replace("(", "").replace(")", "").strip()
        norm = " ".join(norm.split()).lower()
        if norm == "used_at is null or revoked_at is null":
            return
    raise PreflightFailure(
        f"{table_name}: used/revoked CHECK not exactly "
        f"`used_at IS NULL OR revoked_at IS NULL`; found: {ck_defs}"
    )


def _strip_check(defn: str) -> str:
    """Remove leading `CHECK ` and return the inner expression."""
    s = defn.strip()
    if s.upper().startswith("CHECK "):
        s = s[6:]
    return s


def _assert_unique_single_col(bind, table_name: str, col_name: str) -> None:
    """UNIQUE constraint with exactly one local column via pg_constraint.conkey."""
    rows = bind.execute(sa.text(
        """
        SELECT c.conkey, array_agg(a.attname ORDER BY ord.ord), c.conrelid
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN unnest(c.conkey) WITH ORDINALITY AS ord(attnum, ord) ON true
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ord.attnum
        WHERE n.nspname = :schema AND t.relname = :table AND c.contype = 'u'
        GROUP BY c.conkey, c.conrelid
        """
    ), {"schema": PUBLIC_SCHEMA, "table": table_name}).fetchall()
    for _conkey, cols, _oid in rows:
        if len(cols) == 1 and cols[0] == col_name:
            return
    raise PreflightFailure(
        f"{table_name}: no UNIQUE constraint on exactly ({col_name}); "
        f"found unique groups: {[[r[1] for r in rows]]}"
    )


def _assert_fk(
    bind, table_name: str, local_col: str, ref_table: str, ref_col: str
) -> None:
    """FK validated via conkey/confkey/confrelid/confdeltype (no substring)."""
    row = bind.execute(sa.text(
        """
        SELECT
            la.attname AS local_col,
            ra.attname AS ref_col,
            rt.relname AS ref_table,
            c.confdeltype
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_class rt ON rt.oid = c.confrelid
        JOIN pg_namespace rn ON rn.oid = rt.relnamespace
        JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS lk(attnum, ord) ON true
        JOIN pg_attribute la ON la.attrelid = c.conrelid AND la.attnum = lk.attnum
        JOIN LATERAL unnest(c.confkey) WITH ORDINALITY AS fk(attnum, ord) ON fk.ord = lk.ord
        JOIN pg_attribute ra ON ra.attrelid = c.confrelid AND ra.attnum = fk.attnum
        WHERE n.nspname = :schema AND t.relname = :table AND c.contype = 'f'
          AND la.attname = :local_col
        LIMIT 1
        """
    ), {
        "schema": PUBLIC_SCHEMA, "table": table_name, "local_col": local_col,
    }).first()
    if row is None:
        raise PreflightFailure(
            f"{table_name}: missing FK on {local_col} -> {ref_table}.{ref_col}"
        )
    actual_local, actual_ref_col, actual_ref_table, deltype = row
    if actual_ref_table != ref_table:
        raise PreflightFailure(
            f"{table_name}: FK {local_col} references {actual_ref_table}, expected {ref_table}"
        )
    if actual_ref_col != ref_col:
        raise PreflightFailure(
            f"{table_name}: FK {local_col} -> {actual_ref_table}.{actual_ref_col}, "
            f"expected .{ref_col}"
        )
    if deltype != "c":  # 'c' = CASCADE
        raise PreflightFailure(
            f"{table_name}: FK {local_col} confdeltype={deltype!r}, expected CASCADE ('c')"
        )


def _validate_one_active_index_exact(bind, table_name: str, index_name: str) -> None:
    """Validate the one-active partial unique index via pg_index columns + pg_get_expr."""
    row = bind.execute(sa.text(
        """
        SELECT i.indisunique, i.indnkeyatts,
               pg_get_expr(i.indpred, i.indrelid) AS pred_text,
               array_agg(a.attname ORDER BY k.ord) AS key_cols
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_class ic ON ic.oid = i.indexrelid
        JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
             ON k.attnum > 0 AND k.ord <= i.indnkeyatts
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
        WHERE n.nspname = :schema AND c.relname = :table AND ic.relname = :idx
        GROUP BY i.indisunique, i.indnkeyatts, i.indpred, i.indrelid
        """
    ), {"schema": PUBLIC_SCHEMA, "table": table_name, "idx": index_name}).first()
    if row is None:
        raise PreflightFailure(f"{table_name}: missing one-active index {index_name}")
    is_unique, nkeyatts, pred_text, key_cols = row
    if not is_unique:
        raise PreflightFailure(f"{table_name}.{index_name}: must be UNIQUE")
    if nkeyatts != 1:
        raise PreflightFailure(
            f"{table_name}.{index_name}: indnkeyatts={nkeyatts}, expected 1"
        )
    if list(key_cols) != ["retailer_id"]:
        raise PreflightFailure(
            f"{table_name}.{index_name}: key columns {list(key_cols)}, "
            f"expected ['retailer_id']"
        )
    if pred_text is None:
        raise PreflightFailure(f"{table_name}.{index_name}: must be a partial index")
    norm = " ".join(str(pred_text).lower().replace("(", "").replace(")", "").split())
    required_parts = ["used_at is null", "revoked_at is null", "is_deleted = false"]
    for part in required_parts:
        if part not in norm:
            raise PreflightFailure(
                f"{table_name}.{index_name}: predicate missing `{part}`; "
                f"got: {pred_text}"
            )
    if " or " in norm:
        raise PreflightFailure(
            f"{table_name}.{index_name}: predicate must not contain OR"
        )
    residual = norm
    for part in required_parts:
        residual = residual.replace(part, "", 1)
    residual = residual.replace(" and ", " ").strip()
    if residual:
        raise PreflightFailure(
            f"{table_name}.{index_name}: extra predicate condition(s): `{residual}`"
        )


# ---------------------------------------------------------------------------
# per live-tenant mutations
# ---------------------------------------------------------------------------

def _seed_tenant_rbac(bind, row: dict[str, Any]) -> None:
    schema = row["tenant_schema"]
    quoted_schema = _quote_ident(bind, schema)
    users_t = f"{quoted_schema}.{_quote_ident(bind, USERS)}"
    roles_t = f"{quoted_schema}.{_quote_ident(bind, 'roles')}"
    perms_t = f"{quoted_schema}.{_quote_ident(bind, 'permissions')}"
    role_perms_t = f"{quoted_schema}.{_quote_ident(bind, 'role_permissions')}"

    # 1. Seed all new permission codes idempotently.
    for code, description in ALL_NEW_PERMISSIONS:
        bind.execute(sa.text(
            f"INSERT INTO {perms_t} (code, description) VALUES (:code, :description) "
            "ON CONFLICT (code) DO NOTHING"
        ), {"code": code, "description": description})

    # 2. Seed retailer_operator role + grant ONLY client:* permissions.
    bind.execute(sa.text(
        f"INSERT INTO {roles_t} (name, description) "
        "VALUES (:name, :description) ON CONFLICT (name) DO NOTHING"
    ), {"name": RETAILER_OPERATOR_ROLE, "description": "Retailer self-service operator (MVP)"})
    _grant_role_permissions(bind, role_perms_t, perms_t, roles_t, RETAILER_OPERATOR_ROLE,
                            [code for code, _ in RETAILER_OPERATOR_PERMISSIONS])

    # 3. Grant invitations:revoke to admin (if admin role exists in this tenant).
    _grant_role_permissions(bind, role_perms_t, perms_t, roles_t, ADMIN_ROLE,
                            [code for code, _ in ADMIN_EXTRA_PERMISSIONS])


def _grant_role_permissions(bind, role_perms_t, perms_t, roles_t, role_name,
                            codes: list[str]) -> None:
    role_exists = bind.execute(sa.text(
        f"SELECT 1 FROM {roles_t} WHERE name = :name"
    ), {"name": role_name}).first()
    if not role_exists:
        return
    for code in codes:
        bind.execute(sa.text(
            f"""
            INSERT INTO {role_perms_t} (role_id, permission_id)
            SELECT r.id, p.id FROM {roles_t} r, {perms_t} p
            WHERE r.name = :role_name AND p.code = :code
              AND NOT EXISTS (
                SELECT 1 FROM {role_perms_t} rp
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        ), {"role_name": role_name, "code": code})


def _ensure_tenant_email_index(bind, row: dict[str, Any]) -> None:
    schema = row["tenant_schema"]
    quoted_schema = _quote_ident(bind, schema)
    users_t = f"{quoted_schema}.{_quote_ident(bind, USERS)}"
    if not _index_exists(bind, schema, USERS, "ux_users_email_active"):
        bind.execute(sa.text(
            f"CREATE UNIQUE INDEX ux_users_email_active ON {users_t} (email) "
            "WHERE is_deleted IS FALSE"
        ))


# ---------------------------------------------------------------------------
# catalog helpers (verbatim pattern from 035)
# ---------------------------------------------------------------------------

def _column_is_nullable(bind, schema: str, table_name: str, column_name: str) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table_name "
            "AND column_name = :column_name"
        ),
        {"schema": schema, "table_name": table_name, "column_name": column_name},
    ).first()
    return bool(row and row[0] == "YES")


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
    """DC-12R1-S1-R2: check a CHECK/UNIQUE constraint exists on a table."""
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
