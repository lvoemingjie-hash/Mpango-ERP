"""Real PostgreSQL 16 evidence for the SKU-M1 tenant migration."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from scripts.bootstrap_tenant_schema import bootstrap
from tests.async_test_utils import (
    run_alembic_upgrade,
    run_coroutine,
    temporary_database_url,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"
REV_037 = "037_payment_declarations_schema"
REV_038 = "038_catalog_identity_vertical_slice"


def _async_url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _sync_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", _async_url(url))
    return config


@contextmanager
def _database_url_env(url: str):
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _register_tenant(connection, *, prefix: str) -> tuple[uuid.UUID, str]:
    wholesaler_id = uuid.uuid4()
    schema = f"t_{wholesaler_id.hex}"
    connection.execute(
        text(
            "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
            "VALUES (:id, :code, :name, 'active', false)"
        ),
        {
            "id": wholesaler_id,
            "code": f"{prefix}{uuid.uuid4().hex[:8]}".upper()[:32],
            "name": f"SKU M1 {prefix}",
        },
    )
    connection.execute(
        text(
            "INSERT INTO public.tenant_registrations ("
            "id, company_name, tenant_code, country, owner_email, status, "
            "email_verified_at, provisioning_started_at, password_hash_cleared_at, "
            "wholesaler_id, tenant_schema, expires_at, is_deleted"
            ") VALUES ("
            ":id, :company_name, :tenant_code, 'ZA', :owner_email, 'provisioning', "
            "now(), now(), now(), "
            ":wholesaler_id, :tenant_schema, now() + interval '7 days', false"
            ")"
        ),
        {
            "id": uuid.uuid4(),
            "company_name": f"SKU M1 {prefix}",
            "tenant_code": f"{prefix}{uuid.uuid4().hex[:8]}".lower()[:32],
            "owner_email": f"{prefix.lower()}_{uuid.uuid4().hex[:8]}@example.com",
            "wholesaler_id": wholesaler_id,
            "tenant_schema": schema,
        },
    )
    return wholesaler_id, schema


def _strip_sku_m1_schema(connection, schema: str) -> None:
    q = f'"{schema}"'
    connection.execute(
        text(
            f"ALTER TABLE {q}.order_items "
            "DROP COLUMN sellable_unit_id CASCADE, "
            "DROP COLUMN identity_status CASCADE, "
            "DROP COLUMN unit_snapshot CASCADE"
        )
    )
    connection.execute(
        text(
            f"ALTER TABLE {q}.skus "
            "DROP COLUMN catalog_product_id CASCADE, "
            "DROP COLUMN package_quantity CASCADE"
        )
    )
    connection.execute(text(f"DROP TABLE {q}.catalog_products CASCADE"))


def _prepare_old_tenant(connection, db_url: str, *, prefix: str) -> tuple[uuid.UUID, str]:
    wholesaler_id, schema = _register_tenant(connection, prefix=prefix)
    connection.commit()
    run_coroutine(bootstrap(schema, _async_url(db_url)))
    connection.rollback()
    _strip_sku_m1_schema(connection, schema)
    connection.commit()
    return wholesaler_id, schema


def _insert_sku(connection, schema: str, *, code: str, with_stock: bool) -> uuid.UUID:
    sku_id = uuid.uuid4()
    connection.execute(
        text(
            f'INSERT INTO "{schema}".skus '
            "(id, sku_code, name, unit, category, is_active, is_deleted) "
            "VALUES (:id, :code, :name, 'case', 'Staples', true, false)"
        ),
        {"id": sku_id, "code": code, "name": f"Product {code}"},
    )
    if with_stock:
        connection.execute(
            text(
                f'INSERT INTO "{schema}".inventory_stocks '
                "(sku_id, quantity_on_hand, quantity_reserved, is_deleted) "
                "VALUES (:sku_id, 17, 3, false)"
            ),
            {"sku_id": sku_id},
        )
    return sku_id


def _insert_order(connection, schema: str, wholesaler_id: uuid.UUID) -> uuid.UUID:
    order_id = uuid.uuid4()
    connection.execute(
        text(
            f'INSERT INTO "{schema}".orders '
            "(id, wholesaler_id, retailer_id, status, total_amount, is_deleted) "
            "VALUES (:id, :wholesaler_id, :retailer_id, 'draft', 105, false)"
        ),
        {
            "id": order_id,
            "wholesaler_id": wholesaler_id,
            "retailer_id": uuid.uuid4(),
        },
    )
    return order_id


def _insert_order_item(connection, schema: str, order_id: uuid.UUID, *, code: str) -> uuid.UUID:
    item_id = uuid.uuid4()
    connection.execute(
        text(
            f'INSERT INTO "{schema}".order_items '
            "(id, order_id, product_name, sku_code, quantity, unit_price, subtotal, is_deleted) "
            "VALUES (:id, :order_id, :name, :code, 3, 35, 105, false)"
        ),
        {"id": item_id, "order_id": order_id, "name": f"Snapshot {code}", "code": code},
    )
    return item_id


def _insert_reservation(
    connection,
    schema: str,
    *,
    order_id: uuid.UUID,
    order_item_id: uuid.UUID,
    sku_id: uuid.UUID,
    sku_code: str,
    status: str,
) -> None:
    connection.execute(
        text(
            f'INSERT INTO "{schema}".inventory_reservations '
            "(order_id, order_item_id, sku_id, sku_code, quantity, status, "
            "reference_type, reference_id, is_deleted) "
            "VALUES (:order_id, :order_item_id, :sku_id, :sku_code, 3, :status, "
            "'order', :order_id, false)"
        ),
        {
            "order_id": order_id,
            "order_item_id": order_item_id,
            "sku_id": sku_id,
            "sku_code": sku_code,
            "status": status,
        },
    )


def _item_snapshots(connection, schema: str) -> list[tuple]:
    return list(
        connection.execute(
            text(
                f'SELECT id, product_name, sku_code, quantity, unit_price, subtotal '
                f'FROM "{schema}".order_items ORDER BY id'
            )
        ).all()
    )


def _sku_m1_schema_contract(connection, schema: str) -> dict[str, list[tuple]]:
    selected_columns = {
        "catalog_products": None,
        "skus": {"catalog_product_id", "package_quantity"},
        "order_items": {"sellable_unit_id", "identity_status", "unit_snapshot"},
    }
    columns = []
    for row in connection.execute(
        text(
            "SELECT table_name, column_name, data_type, udt_name, "
            "character_maximum_length, numeric_precision, numeric_scale, "
            "is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema=:schema "
            "AND table_name IN ('catalog_products', 'skus', 'order_items') "
            "ORDER BY table_name, ordinal_position"
        ),
        {"schema": schema},
    ).all():
        allowed = selected_columns[row.table_name]
        if allowed is None or row.column_name in allowed:
            columns.append(tuple(row))

    constraints = []
    for row in connection.execute(
        text(
            "SELECT t.relname AS table_name, c.conname AS constraint_name, "
            "c.contype AS constraint_type, "
            "pg_get_constraintdef(c.oid, true) AS definition "
            "FROM pg_constraint c "
            "JOIN pg_class t ON t.oid=c.conrelid "
            "JOIN pg_namespace n ON n.oid=t.relnamespace "
            "WHERE n.nspname=:schema "
            "AND t.relname IN ('catalog_products', 'skus', 'order_items') "
            "ORDER BY t.relname, c.conname"
        ),
        {"schema": schema},
    ).all():
        definition = row.definition
        relevant = row.table_name == "catalog_products" or any(
            field in definition
            for field in (
                "catalog_product_id",
                "package_quantity",
                "sellable_unit_id",
                "identity_status",
                "unit_snapshot",
            )
        )
        if relevant:
            normalized = definition.replace(f'"{schema}".', "<tenant>.").replace(
                f"{schema}.", "<tenant>."
            )
            constraints.append(
                (
                    row.table_name,
                    row.constraint_name,
                    row.constraint_type,
                    re.sub(r"\s+", " ", normalized),
                )
            )

    indexes = []
    for row in connection.execute(
        text(
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname=:schema "
            "AND (tablename='catalog_products' "
            "OR indexname IN ('ix_skus_catalog_product_id', "
            "'ix_order_items_sellable_unit_id')) "
            "ORDER BY tablename, indexname"
        ),
        {"schema": schema},
    ).all():
        normalized = row.indexdef.replace(f'"{schema}".', "<tenant>.").replace(
            f"{schema}.", "<tenant>."
        )
        indexes.append((row.tablename, row.indexname, re.sub(r"\s+", " ", normalized)))
    return {
        "columns": sorted(columns),
        "constraints": sorted(constraints),
        "indexes": sorted(indexes),
    }


def test_real_pg16_two_tenant_upgrade_preserves_identity_snapshots_and_stock() -> None:
    source_url = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source_url, "skum1r1") as db_url:
        config = _alembic_config(db_url)
        with _database_url_env(db_url):
            run_alembic_upgrade(config, REV_037)
            engine = create_engine(_sync_url(db_url), future=True)
            try:
                with engine.connect() as connection:
                    wholesaler_id, existing_schema = _prepare_old_tenant(
                        connection, db_url, prefix="existing"
                    )
                    _, fresh_schema = _prepare_old_tenant(
                        connection, db_url, prefix="fresh"
                    )

                    unique_sku = _insert_sku(
                        connection, existing_schema, code="UNIQUE-EVIDENCE", with_stock=True
                    )
                    ambiguous_a = _insert_sku(
                        connection, existing_schema, code="AMBIGUOUS-A", with_stock=True
                    )
                    ambiguous_b = _insert_sku(
                        connection, existing_schema, code="AMBIGUOUS-B", with_stock=True
                    )
                    safe_zero_sku = _insert_sku(
                        connection, existing_schema, code="SAFE-ZERO", with_stock=False
                    )
                    order_id = _insert_order(connection, existing_schema, wholesaler_id)
                    unique_item = _insert_order_item(
                        connection, existing_schema, order_id, code="UNIQUE-EVIDENCE"
                    )
                    ambiguous_item = _insert_order_item(
                        connection, existing_schema, order_id, code="AMBIGUOUS-A"
                    )
                    no_evidence_item = _insert_order_item(
                        connection, existing_schema, order_id, code="SAFE-ZERO"
                    )
                    _insert_reservation(
                        connection,
                        existing_schema,
                        order_id=order_id,
                        order_item_id=unique_item,
                        sku_id=unique_sku,
                        sku_code="UNIQUE-EVIDENCE",
                        status="reserved",
                    )
                    _insert_reservation(
                        connection,
                        existing_schema,
                        order_id=order_id,
                        order_item_id=ambiguous_item,
                        sku_id=ambiguous_a,
                        sku_code="AMBIGUOUS-A",
                        status="consumed",
                    )
                    _insert_reservation(
                        connection,
                        existing_schema,
                        order_id=order_id,
                        order_item_id=ambiguous_item,
                        sku_id=ambiguous_b,
                        sku_code="AMBIGUOUS-B",
                        status="released",
                    )
                    before_snapshots = _item_snapshots(connection, existing_schema)
                    connection.commit()

                run_alembic_upgrade(config, REV_038)

                reference_schema = f"t_{uuid.uuid4().hex}"
                run_coroutine(bootstrap(reference_schema, _async_url(db_url)))

                with engine.connect() as connection:
                    assert connection.execute(
                        text("SELECT version_num FROM public.alembic_version")
                    ).scalar_one() == REV_038
                    assert _sku_m1_schema_contract(
                        connection, existing_schema
                    ) == _sku_m1_schema_contract(connection, reference_schema)
                    for schema in (existing_schema, fresh_schema):
                        assert connection.execute(
                            text(
                                "SELECT 1 FROM information_schema.tables "
                                "WHERE table_schema=:schema AND table_name='catalog_products'"
                            ),
                            {"schema": schema},
                        ).scalar_one() == 1

                    identities = dict(
                        connection.execute(
                            text(
                                f'SELECT id, catalog_product_id FROM "{existing_schema}".skus'
                            )
                        ).all()
                    )
                    assert identities[unique_sku] == unique_sku
                    assert identities[safe_zero_sku] == safe_zero_sku
                    assert _item_snapshots(connection, existing_schema) == before_snapshots

                    item_identities = dict(
                        connection.execute(
                            text(
                                f'SELECT id, identity_status FROM "{existing_schema}".order_items'
                            )
                        ).all()
                    )
                    assert item_identities[unique_item] == "linked_legacy"
                    assert item_identities[ambiguous_item] == "legacy"
                    assert item_identities[no_evidence_item] == "legacy"
                    assert connection.execute(
                        text(
                            f'SELECT sellable_unit_id FROM "{existing_schema}".order_items '
                            "WHERE id=:item_id"
                        ),
                        {"item_id": unique_item},
                    ).scalar_one() == unique_sku
                    assert connection.execute(
                        text(
                            f'SELECT sellable_unit_id FROM "{existing_schema}".order_items '
                            "WHERE id=:item_id"
                        ),
                        {"item_id": ambiguous_item},
                    ).scalar_one_or_none() is None

                    existing_stock = connection.execute(
                        text(
                            f'SELECT quantity_on_hand, quantity_reserved '
                            f'FROM "{existing_schema}".inventory_stocks WHERE sku_id=:sku_id'
                        ),
                        {"sku_id": unique_sku},
                    ).one()
                    assert existing_stock == (Decimal("17.00"), Decimal("3.00"))
                    safe_stock = connection.execute(
                        text(
                            f'SELECT quantity_on_hand, quantity_reserved '
                            f'FROM "{existing_schema}".inventory_stocks WHERE sku_id=:sku_id'
                        ),
                        {"sku_id": safe_zero_sku},
                    ).one()
                    assert safe_stock == (Decimal("0.00"), Decimal("0.00"))
            finally:
                engine.dispose()


def test_real_pg16_preflight_failure_causes_global_zero_tenant_mutation() -> None:
    source_url = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source_url, "skum1rollback") as db_url:
        config = _alembic_config(db_url)
        with _database_url_env(db_url):
            run_alembic_upgrade(config, REV_037)
            engine = create_engine(_sync_url(db_url), future=True)
            try:
                with engine.connect() as connection:
                    _, valid_schema = _prepare_old_tenant(connection, db_url, prefix="valid")
                    _, invalid_schema = _prepare_old_tenant(connection, db_url, prefix="invalid")
                    connection.execute(
                        text(f'DROP TABLE "{invalid_schema}".inventory_movements')
                    )
                    connection.commit()

                with pytest.raises(RuntimeError) as error:
                    run_alembic_upgrade(config, REV_038)
                assert error.value.__class__.__name__ == "PreflightFailure"
                assert "inventory_movements is missing" in str(error.value)

                with engine.connect() as connection:
                    assert connection.execute(
                        text("SELECT version_num FROM public.alembic_version")
                    ).scalar_one() == REV_037
                    for schema in (valid_schema, invalid_schema):
                        assert connection.execute(
                            text(
                                "SELECT count(*) FROM information_schema.tables "
                                "WHERE table_schema=:schema AND table_name='catalog_products'"
                            ),
                            {"schema": schema},
                        ).scalar_one() == 0
                        assert connection.execute(
                            text(
                                "SELECT count(*) FROM information_schema.columns "
                                "WHERE table_schema=:schema AND table_name='skus' "
                                "AND column_name='catalog_product_id'"
                            ),
                            {"schema": schema},
                        ).scalar_one() == 0
            finally:
                engine.dispose()


def test_real_pg16_bootstrap_reconciles_unregistered_pre038_tenant() -> None:
    source_url = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source_url, "skum1bootstrap") as db_url:
        config = _alembic_config(db_url)
        with _database_url_env(db_url):
            run_alembic_upgrade(config, REV_037)
            engine = create_engine(_sync_url(db_url), future=True)
            schema = "t_dev"
            try:
                run_coroutine(bootstrap(schema, _async_url(db_url)))
                with engine.connect() as connection:
                    _strip_sku_m1_schema(connection, schema)
                    sku_id = _insert_sku(
                        connection, schema, code="UNREGISTERED-BOOTSTRAP", with_stock=False
                    )
                    connection.commit()
                    assert connection.execute(
                        text(
                            "SELECT count(*) FROM public.tenant_registrations "
                            "WHERE tenant_schema=:schema"
                        ),
                        {"schema": schema},
                    ).scalar_one() == 0

                run_coroutine(bootstrap(schema, _async_url(db_url)))

                with engine.connect() as connection:
                    assert connection.execute(
                        text(f'SELECT catalog_product_id FROM "{schema}".skus WHERE id=:id'),
                        {"id": sku_id},
                    ).scalar_one() == sku_id
                    assert connection.execute(
                        text(f'SELECT count(*) FROM "{schema}".inventory_stocks WHERE sku_id=:id'),
                        {"id": sku_id},
                    ).scalar_one() == 1
                    constraint_names = set(
                        connection.execute(
                            text(
                                "SELECT c.conname FROM pg_constraint c "
                                "JOIN pg_class t ON t.oid=c.conrelid "
                                "JOIN pg_namespace n ON n.oid=t.relnamespace "
                                "WHERE n.nspname=:schema "
                                "AND c.conname IN ("
                                "'fk_skus_catalog_product', "
                                "'ck_skus_package_quantity_positive', "
                                "'fk_order_items_sellable_unit', "
                                "'ck_order_items_identity_status', "
                                "'ck_order_items_identity_shape')"
                            ),
                            {"schema": schema},
                        ).scalars()
                    )
                    assert constraint_names == {
                        "fk_skus_catalog_product",
                        "ck_skus_package_quantity_positive",
                        "fk_order_items_sellable_unit",
                        "ck_order_items_identity_status",
                        "ck_order_items_identity_shape",
                    }
            finally:
                engine.dispose()


def test_real_pg16_bootstrap_rolls_back_unsafe_missing_stock_reconciliation() -> None:
    source_url = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source_url, "skum1bootstrapfail") as db_url:
        config = _alembic_config(db_url)
        with _database_url_env(db_url):
            run_alembic_upgrade(config, REV_037)
            engine = create_engine(_sync_url(db_url), future=True)
            schema = "t_dev"
            try:
                run_coroutine(bootstrap(schema, _async_url(db_url)))
                with engine.connect() as connection:
                    _strip_sku_m1_schema(connection, schema)
                    sku_id = _insert_sku(
                        connection, schema, code="UNSAFE-MISSING-STOCK", with_stock=False
                    )
                    connection.execute(
                        text(
                            f'INSERT INTO "{schema}".inventory_movements '
                            "(sku_id, movement_type, quantity, quantity_before, "
                            "quantity_after, is_deleted) "
                            "VALUES (:sku_id, 'adjustment', 4, 0, 4, false)"
                        ),
                        {"sku_id": sku_id},
                    )
                    connection.commit()

                with pytest.raises(RuntimeError, match="inventory evidence but no stock row"):
                    run_coroutine(bootstrap(schema, _async_url(db_url)))

                with engine.connect() as connection:
                    assert connection.execute(
                        text(
                            "SELECT count(*) FROM information_schema.tables "
                            "WHERE table_schema=:schema AND table_name='catalog_products'"
                        ),
                        {"schema": schema},
                    ).scalar_one() == 0
                    assert connection.execute(
                        text(
                            "SELECT count(*) FROM information_schema.columns "
                            "WHERE table_schema=:schema AND table_name='skus' "
                            "AND column_name='catalog_product_id'"
                        ),
                        {"schema": schema},
                    ).scalar_one() == 0
                    assert connection.execute(
                        text(f'SELECT count(*) FROM "{schema}".inventory_stocks WHERE sku_id=:id'),
                        {"id": sku_id},
                    ).scalar_one() == 0
            finally:
                engine.dispose()


def test_real_pg16_demo_seeder_uses_canonical_catalog_identity() -> None:
    source_url = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source_url, "skum1demoseed") as db_url:
        config = _alembic_config(db_url)
        with _database_url_env(db_url):
            run_alembic_upgrade(config, REV_038)

        env = os.environ.copy()
        env["DATABASE_URL"] = db_url
        env["MPANGO_ENV"] = "test"
        result = subprocess.run(
            [sys.executable, "scripts/seed_demo_data.py"],
            cwd=BACKEND_DIR,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0, "demo seeder failed in the throwaway database"

        engine = create_engine(_sync_url(db_url), future=True)
        schema = "t_a0000000000040008000000000000001"
        try:
            with engine.connect() as connection:
                assert connection.execute(
                    text(f'SELECT count(*) FROM "{schema}".catalog_products')
                ).scalar_one() == 10
                assert connection.execute(
                    text(
                        f'SELECT count(*) FROM "{schema}".skus '
                        "WHERE catalog_product_id IS NOT NULL"
                    )
                ).scalar_one() == 10
                assert connection.execute(
                    text(f'SELECT count(*) FROM "{schema}".inventory_stocks')
                ).scalar_one() == 10
                assert connection.execute(
                    text(
                        f'SELECT count(*) FROM "{schema}".order_items '
                        "WHERE identity_status='stable' "
                        "AND sellable_unit_id IS NOT NULL AND unit_snapshot IS NOT NULL"
                    )
                ).scalar_one() == 10
        finally:
            engine.dispose()


def test_real_pg16_non_live_registered_tenant_fails_before_any_mutation() -> None:
    source_url = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source_url, "skum1status") as db_url:
        config = _alembic_config(db_url)
        with _database_url_env(db_url):
            run_alembic_upgrade(config, REV_037)
            engine = create_engine(_sync_url(db_url), future=True)
            try:
                with engine.connect() as connection:
                    active_id, active_schema = _prepare_old_tenant(
                        connection, db_url, prefix="statusactive"
                    )
                    suspended_id, suspended_schema = _prepare_old_tenant(
                        connection, db_url, prefix="statussuspended"
                    )
                    connection.execute(
                        text("UPDATE public.wholesalers SET status='suspended' WHERE id=:id"),
                        {"id": suspended_id},
                    )
                    connection.commit()

                with pytest.raises(RuntimeError) as error:
                    run_alembic_upgrade(config, REV_038)
                assert error.value.__class__.__name__ == "PreflightFailure"
                assert "outside SKU-M1 live migration statuses" in str(error.value)

                with engine.connect() as connection:
                    assert connection.execute(
                        text("SELECT version_num FROM public.alembic_version")
                    ).scalar_one() == REV_037
                    for schema in (active_schema, suspended_schema):
                        assert connection.execute(
                            text(
                                "SELECT count(*) FROM information_schema.tables "
                                "WHERE table_schema=:schema AND table_name='catalog_products'"
                            ),
                            {"schema": schema},
                        ).scalar_one() == 0
            finally:
                engine.dispose()
