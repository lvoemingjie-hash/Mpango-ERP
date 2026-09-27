"""SKU-M1 tenant-local catalog identity and durable order-line linkage.

Revision ID: 038_catalog_identity_vertical_slice
Revises: 037_payment_declarations_schema
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op


revision = "038_catalog_identity_vertical_slice"
down_revision = "037_payment_declarations_schema"
branch_labels = None
depends_on = None

TENANT_SCHEMA_RE = re.compile(r"^t_[0-9a-f]{32}$")
LIVE_REGISTRATION_STATUSES = (
    "pending_email_verification",
    "email_verified",
    "provisioning",
    "active",
    "failed",
)
WHOLESALER_ACTIVE_STATUSES = ("active", "provisioning")


class PreflightFailure(RuntimeError):
    pass


TENANT_AUTHORITY_ROLE = "mpango_app"


class TenantDDLAuthorityError(RuntimeError):
    """Named refusal: the migration identity cannot lawfully read or alter
    app-owned tenant objects (missing one-way capability, mixed tenant
    ownership, or a SET ROLE leaked from an earlier window)."""


def _open_tenant_ddl_authority(bind, schemas: list[str], purpose: str):
    """Open the narrowest SET ROLE window for tenant reads/DDL.

    Returns the pre-window ``current_user`` (the window token) when the
    one-way capability window is required, or ``None`` when the current
    identity already holds direct CREATE authority on every listed tenant
    schema (legacy single-role / superuser shapes) and needs no window.

    Fails closed with a NAMED error before touching any tenant object when
    a previous window's SET ROLE leaked (``current_user != session_user``),
    when tenant schema ownership is mixed, or when the admin-provisioned
    one-way capability (GRANT app TO migrate WITH INHERIT FALSE, SET TRUE)
    is absent.
    """
    identity = bind.execute(sa.text("SELECT current_user, session_user")).fetchone()
    current_user, session_user = identity[0], identity[1]
    if current_user != session_user:
        raise TenantDDLAuthorityError(
            f"tenant DDL authority window for {purpose!r} refused: "
            f"current_user {current_user!r} != session_user "
            f"{session_user!r} — a SET ROLE from an earlier window leaked "
            "and must be reset before any further tenant work"
        )
    authority = bind.execute(sa.text(
        "SELECT n.nspname, has_schema_privilege(current_user, n.nspname, "
        "'CREATE') FROM pg_catalog.pg_namespace n "
        "WHERE n.nspname = ANY(:schemas) ORDER BY n.nspname"
    ), {"schemas": list(schemas)}).fetchall()
    if not authority:
        raise TenantDDLAuthorityError(
            f"tenant DDL authority window for {purpose!r} refused: none of "
            f"the tenant schemas {sorted(schemas)} exist in pg_namespace "
            "(registry/catalog drift)"
        )
    without_create = [row[0] for row in authority if not row[1]]
    if not without_create:
        return None
    with_create = [row[0] for row in authority if row[1]]
    if with_create:
        raise TenantDDLAuthorityError(
            f"tenant DDL authority window for {purpose!r} refused: mixed "
            f"tenant ownership — CREATE held on {with_create} but not on "
            f"{without_create}; sanctioned topologies are uniformly owned"
        )
    can_set = bind.execute(sa.text(
        "SELECT pg_has_role(current_user, :role, 'SET')"
    ), {"role": TENANT_AUTHORITY_ROLE}).scalar()
    if not can_set:
        raise TenantDDLAuthorityError(
            f"tenant DDL authority for {purpose!r} refused: identity "
            f"{current_user!r} holds no CREATE on tenant schema(s) "
            f"{without_create} and cannot SET ROLE "
            f"{TENANT_AUTHORITY_ROLE!r} — the one-way migration tenant-DDL "
            f"capability (GRANT {TENANT_AUTHORITY_ROLE} TO {current_user} "
            "WITH INHERIT FALSE, SET TRUE, applied by the admin in "
            "provisioning phase 1) is absent on this deployment"
        )
    bind.execute(sa.text(f'SET ROLE "{TENANT_AUTHORITY_ROLE}"'))
    bound = bind.execute(sa.text("SELECT current_user")).scalar()
    if bound != TENANT_AUTHORITY_ROLE:
        raise TenantDDLAuthorityError(
            f"tenant DDL authority window for {purpose!r} refused: SET ROLE "
            f"bound current_user {bound!r}, expected "
            f"{TENANT_AUTHORITY_ROLE!r}"
        )
    return current_user


def _close_tenant_ddl_authority(bind, token, purpose: str) -> None:
    """Close the window: RESET ROLE and prove the migration identity is back.

    Called from ``finally`` — SET ROLE survives transaction rollback, so the
    reset must run even when the window body failed.
    """
    if token is None:
        return
    bind.execute(sa.text("RESET ROLE"))
    restored = bind.execute(sa.text("SELECT current_user")).scalar()
    if restored != token:
        raise TenantDDLAuthorityError(
            f"tenant DDL authority window for {purpose!r} failed to restore "
            f"current_user {token!r} (now {restored!r})"
        )


def _tenant_ddl_authority_window(bind, schemas: list[str], purpose: str, body) -> None:
    """Run ``body()`` under the narrowest tenant-authority window.

    The body runs inside a SAVEPOINT so that a body failure leaves the
    enclosing Alembic transaction in a usable state for the mandatory
    identity reset (a plain RESET ROLE is refused with 25P02 inside an
    aborted transaction); the original exception is always re-raised and
    Alembic's outer rollback still discards every partial write.
    """
    token = _open_tenant_ddl_authority(bind, schemas, purpose)
    if token is None:
        body()
        return
    try:
        nested = bind.begin_nested()
        try:
            body()
            nested.commit()
        except Exception:
            nested.rollback()
            raise
    finally:
        _close_tenant_ddl_authority(bind, token, purpose)


def _table_exists(bind, schema: str, table: str) -> bool:
    # pg_catalog, not information_schema: the migration authority must see
    # app-owned tenant tables even though privilege-filtered views hide them
    # (G1-R2E-P1 authority contract; genuinely absent tables are still
    # rejected by name through the same call sites).
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname=:schema AND c.relname=:table "
                "AND c.relkind IN ('r', 'p', 'v', 'f')"
            ),
            {"schema": schema, "table": table},
        ).scalar()
    )


def _column_exists(bind, schema: str, table: str, column: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_catalog.pg_attribute a "
                "JOIN pg_catalog.pg_class c ON c.oid = a.attrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname=:schema AND c.relname=:table "
                "AND a.attname=:column "
                "AND a.attnum > 0 AND NOT a.attisdropped"
            ),
            {"schema": schema, "table": table, "column": column},
        ).scalar()
    )


def _registered_tenants(bind) -> list[str]:
    if not _table_exists(bind, "public", "tenant_registrations") or not _table_exists(
        bind, "public", "wholesalers"
    ):
        raise PreflightFailure("authoritative tenant registry tables are missing")
    rows = bind.execute(
        sa.text(
            """
            SELECT tr.tenant_schema, ('t_' || replace(w.id::text, '-', '')) AS derived_schema,
                   tr.status AS registration_status, w.status AS wholesaler_status
            FROM public.tenant_registrations tr
            JOIN public.wholesalers w ON w.id = tr.wholesaler_id
            WHERE tr.is_deleted IS FALSE
              AND w.is_deleted IS FALSE
            ORDER BY tr.tenant_schema, tr.id
            """
        )
    ).mappings()
    schemas: list[str] = []
    for row in rows:
        schema = row["tenant_schema"]
        if not schema or not TENANT_SCHEMA_RE.fullmatch(schema):
            raise PreflightFailure("registered tenant schema is malformed")
        if schema != row["derived_schema"]:
            raise PreflightFailure(f"{schema}: registry schema does not match wholesaler identity")
        if (
            row["registration_status"] not in LIVE_REGISTRATION_STATUSES
            or row["wholesaler_status"] not in WHOLESALER_ACTIVE_STATUSES
        ):
            raise PreflightFailure(
                f"{schema}: registered tenant is outside SKU-M1 live migration statuses"
            )
        if schema not in schemas:
            schemas.append(schema)
    return schemas


def _preflight_tenant(bind, schema: str) -> None:
    for table in (
        "skus",
        "orders",
        "order_items",
        "inventory_stocks",
        "inventory_movements",
        "inventory_reservations",
    ):
        if not _table_exists(bind, schema, table):
            raise PreflightFailure(f"{schema}.{table} is missing")
    catalog_exists = _table_exists(bind, schema, "catalog_products")
    new_columns = (
        _column_exists(bind, schema, "skus", "catalog_product_id"),
        _column_exists(bind, schema, "skus", "package_quantity"),
        _column_exists(bind, schema, "order_items", "sellable_unit_id"),
        _column_exists(bind, schema, "order_items", "identity_status"),
        _column_exists(bind, schema, "order_items", "unit_snapshot"),
    )
    if catalog_exists or any(new_columns):
        raise PreflightFailure(f"{schema}: partial or pre-existing SKU-M1 schema detected")

    q = f'"{schema}"'
    unsafe_missing_stock = bind.execute(
        sa.text(
            f"""
            SELECT s.id
              FROM {q}.skus s
              LEFT JOIN {q}.inventory_stocks stock ON stock.sku_id = s.id
             WHERE s.is_deleted IS FALSE
               AND stock.id IS NULL
               AND (
                   EXISTS (
                       SELECT 1 FROM {q}.inventory_movements movement
                        WHERE movement.sku_id = s.id AND movement.is_deleted IS FALSE
                   ) OR EXISTS (
                       SELECT 1 FROM {q}.inventory_reservations reservation
                        WHERE reservation.sku_id = s.id AND reservation.is_deleted IS FALSE
                   )
               )
             LIMIT 1
            """
        )
    ).scalar()
    if unsafe_missing_stock is not None:
        raise PreflightFailure(
            f"{schema}: active SKU has inventory evidence but no stock row"
        )

    deleted_stock_for_active_sku = bind.execute(
        sa.text(
            f"""
            SELECT s.id
              FROM {q}.skus s
              JOIN {q}.inventory_stocks stock ON stock.sku_id = s.id
             WHERE s.is_deleted IS FALSE AND stock.is_deleted IS TRUE
             LIMIT 1
            """
        )
    ).scalar()
    if deleted_stock_for_active_sku is not None:
        raise PreflightFailure(
            f"{schema}: active SKU has only a soft-deleted stock row"
        )


def _upgrade_tenant(bind, schema: str) -> None:
    q = f'"{schema}"'
    script = f"""
            CREATE TABLE {q}.catalog_products (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(64),
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMPTZ,
                created_by UUID,
                updated_by UUID
            );
            CREATE INDEX ix_catalog_products_name ON {q}.catalog_products (name);
            CREATE INDEX ix_catalog_products_is_active ON {q}.catalog_products (is_active);

            ALTER TABLE {q}.skus
                ADD COLUMN catalog_product_id UUID,
                ADD COLUMN package_quantity NUMERIC(12,3) NOT NULL DEFAULT 1.000;

            INSERT INTO {q}.catalog_products
                (id, name, description, category, is_active, created_at, updated_at,
                 is_deleted, deleted_at, created_by, updated_by)
            SELECT id, name, description, category, is_active, created_at, updated_at,
                   is_deleted, deleted_at, created_by, updated_by
            FROM {q}.skus;

            UPDATE {q}.skus SET catalog_product_id = id;
            ALTER TABLE {q}.skus
                ALTER COLUMN catalog_product_id SET NOT NULL,
                ADD CONSTRAINT fk_skus_catalog_product
                    FOREIGN KEY (catalog_product_id) REFERENCES {q}.catalog_products(id) ON DELETE RESTRICT,
                ADD CONSTRAINT ck_skus_package_quantity_positive CHECK (package_quantity > 0);
            CREATE INDEX ix_skus_catalog_product_id ON {q}.skus (catalog_product_id);

            INSERT INTO {q}.inventory_stocks (sku_id)
            SELECT s.id
              FROM {q}.skus s
              LEFT JOIN {q}.inventory_stocks stock ON stock.sku_id = s.id
             WHERE s.is_deleted IS FALSE AND stock.id IS NULL;

            ALTER TABLE {q}.order_items
                ADD COLUMN sellable_unit_id UUID,
                ADD COLUMN identity_status VARCHAR(32) NOT NULL DEFAULT 'legacy',
                ADD COLUMN unit_snapshot VARCHAR(32);

            WITH reservation_proof AS (
                SELECT order_item_id, min(sku_id::text)::uuid AS sku_id
                FROM {q}.inventory_reservations
                WHERE is_deleted IS FALSE
                GROUP BY order_item_id
                HAVING count(DISTINCT sku_id) = 1
            )
            UPDATE {q}.order_items oi
               SET sellable_unit_id = proof.sku_id,
                   identity_status = 'linked_legacy'
              FROM reservation_proof proof
              JOIN {q}.skus s ON s.id = proof.sku_id
             WHERE oi.id = proof.order_item_id;

            ALTER TABLE {q}.order_items
                ADD CONSTRAINT fk_order_items_sellable_unit
                    FOREIGN KEY (sellable_unit_id) REFERENCES {q}.skus(id) ON DELETE RESTRICT,
                ADD CONSTRAINT ck_order_items_identity_status
                    CHECK (identity_status IN ('legacy', 'linked_legacy', 'stable')),
                ADD CONSTRAINT ck_order_items_identity_shape CHECK (
                    (identity_status = 'legacy' AND sellable_unit_id IS NULL) OR
                    (identity_status = 'linked_legacy' AND sellable_unit_id IS NOT NULL) OR
                    (identity_status = 'stable' AND sellable_unit_id IS NOT NULL AND unit_snapshot IS NOT NULL)
                );
            CREATE INDEX ix_order_items_sellable_unit_id ON {q}.order_items (sellable_unit_id);
            """
    # asyncpg rejects multi-command prepared statements, so execute each DDL
    # unit separately while retaining Alembic's enclosing transaction.
    for statement in script.split(";\n"):
        if statement.strip():
            bind.execute(sa.text(statement))


def upgrade() -> None:
    bind = op.get_bind()
    schemas = _registered_tenants(bind)
    if not schemas:
        return

    def _preflight_all() -> None:
        for schema in schemas:
            _preflight_tenant(bind, schema)

    _tenant_ddl_authority_window(
        bind, schemas, "038 preflight tenant reads", _preflight_all)
    for schema in schemas:
        _tenant_ddl_authority_window(
            bind, [schema], f"038 tenant upgrade {schema}",
            lambda schema=schema: _upgrade_tenant(bind, schema),
        )


def downgrade() -> None:
    raise RuntimeError(
        "038_catalog_identity_vertical_slice is forward-only; restore the database from backup"
    )
