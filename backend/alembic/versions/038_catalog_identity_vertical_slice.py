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


def _table_exists(bind, schema: str, table: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=:schema AND table_name=:table"
            ),
            {"schema": schema, "table": table},
        ).scalar()
    )


def _column_exists(bind, schema: str, table: str, column: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema=:schema AND table_name=:table AND column_name=:column"
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
    for schema in schemas:
        _preflight_tenant(bind, schema)
    for schema in schemas:
        _upgrade_tenant(bind, schema)


def downgrade() -> None:
    raise RuntimeError(
        "038_catalog_identity_vertical_slice is forward-only; restore the database from backup"
    )
