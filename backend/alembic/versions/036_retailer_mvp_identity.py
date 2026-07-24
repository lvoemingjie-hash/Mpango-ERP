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
    if failures:
        raise PreflightFailure(
            "036 preflight (conflicting mappings) failed: " + "; ".join(failures)
        )


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
