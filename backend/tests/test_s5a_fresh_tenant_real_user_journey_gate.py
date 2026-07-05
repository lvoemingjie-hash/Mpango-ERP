"""S5-A fresh tenant real user journey gate.

This file starts with a strict fresh-bootstrap audit because the real user
journey cannot safely pass if a newly bootstrapped tenant cannot persist the
``returned`` order status used by the return endpoint.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import event, text

from api.v1.auth import login, select_tenant
from api.v1.orders import confirm_order, create_order, fulfill_order, pay_order, return_order
from api.v1.pricing import SetPriceRequest, set_retailer_price
from core.config import get_settings
from core.security import TokenPayload, decode_token, hash_password
from database.session import AsyncSessionLocal, async_engine
from schemas.auth import LoginRequest, SelectTenantRequest
from schemas.order import PayOrderRequest, WholesalerOrderCreateRequest
from scripts.bootstrap_tenant_schema import bootstrap
from services.import_service import ImportService
from services.inventory_service import InventoryService


ADMIN_PERMISSION_CODES = [
    ("products", "skus:read"),
    ("stock", "inventory:read"),
    ("orders", "orders:read"),
    ("payments", "payments:read"),
    ("customers", "retailers:read"),
    ("pricing", "pricing:read"),
    ("reports", "reports:read"),
]

ALL_PERMISSION_CODES = sorted(
    {
        "dashboards:read",
        "inventory:read",
        "inventory:update",
        "orders:create",
        "orders:read",
        "orders:update",
        "payments:create",
        "payments:read",
        "pricing:read",
        "pricing:write",
        "reports:analyze",
        "reports:read",
        "retailers:read",
        "skus:create",
        "skus:import",
        "skus:read",
        "skus:update",
    }
)


def _tenant_schema(tenant_id: uuid.UUID) -> str:
    return f"t_{str(tenant_id).replace('-', '')}"


@asynccontextmanager
async def _tenant_session(schema: str, tenant_id: uuid.UUID):
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = schema
        session.info["tenant_id"] = str(tenant_id)
        await session.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
        sync_session = session.sync_session

        @event.listens_for(sync_session, "after_begin")
        def _after_begin(sess, transaction, connection):
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))

        try:
            yield session
        finally:
            event.remove(sync_session, "after_begin", _after_begin)


async def _enum_labels(schema: str) -> list[str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT enumlabel "
                "FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = :schema "
                "AND t.typname = 'order_status' "
                "ORDER BY e.enumsortorder"
            ),
            {"schema": schema},
        )
        return list(result.scalars().all())


async def _run_import_runs_migration(session, schema: str) -> None:
    import importlib.util
    from pathlib import Path

    from alembic import op
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    await session.execute(text(f'SET search_path TO "{schema}", public'))
    await session.commit()

    migration_file = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "022_import_runs.py"
    spec = importlib.util.spec_from_file_location("migration_022", migration_file)
    migration_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration_mod)

    def _run_upgrade_sync(sync_conn):
        migration_context = MigrationContext.configure(sync_conn)
        operations = Operations(migration_context)
        saved = {name: getattr(op, name, None) for name in ("create_table", "create_index", "drop_table", "get_bind")}
        op.get_bind = lambda: sync_conn
        op.create_table = operations.create_table
        op.create_index = operations.create_index
        op.drop_table = operations.drop_table
        try:
            migration_mod.upgrade()
        finally:
            for name, original in saved.items():
                if original is not None:
                    setattr(op, name, original)

    connection = await session.connection()
    await connection.run_sync(_run_upgrade_sync)
    await session.commit()


async def _seed_public_tenant_and_retailer(
    *, tenant_id: uuid.UUID, code: str, retailer_id: uuid.UUID
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "INSERT INTO public.wholesalers (id, code, name, contact, plan_type) "
                "VALUES (:id, :code, :name, :contact, :plan_type)"
            ),
            {
                "id": tenant_id,
                "code": code,
                "name": f"S5A Wholesaler {code}",
                "contact": "+254700555001",
                "plan_type": "test",
            },
        )
        await session.execute(
            text(
                "INSERT INTO public.retailers (id, phone, name, email, address) "
                "VALUES (:id, :phone, :name, :email, :address)"
            ),
            {
                "id": retailer_id,
                "phone": f"+2547{str(retailer_id).replace('-', '')[:8]}",
                "name": "S5A Retailer",
                "email": "s5a-retailer@example.com",
                "address": "S5A test address",
            },
        )
        await session.execute(
            text(
                "INSERT INTO public.wholesaler_retailer_bindings "
                "(wholesaler_id, retailer_id, status, outstanding_balance) "
                "VALUES (:wholesaler_id, :retailer_id, 'active', 0.00)"
            ),
            {"wholesaler_id": tenant_id, "retailer_id": retailer_id},
        )
        await session.commit()


async def _seed_admin(schema: str, admin_id: uuid.UUID, email: str, password: str) -> None:
    async with _tenant_session(schema, uuid.UUID(schema[2:])) as session:
        await session.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, is_active) "
                "VALUES (:id, :email, :password_hash, 'S5A Admin', true)"
            ),
            {"id": admin_id, "email": email, "password_hash": hash_password(password)},
        )
        role_id = (
            await session.execute(
                text(
                    "INSERT INTO roles (name, description) "
                    "VALUES ('admin', 'S5A full access admin') RETURNING id"
                )
            )
        ).scalar_one()
        for code in ALL_PERMISSION_CODES:
            permission_id = (
                await session.execute(
                    text(
                        "INSERT INTO permissions (code, description) "
                        "VALUES (:code, :description) RETURNING id"
                    ),
                    {"code": code, "description": f"S5A {code}"},
                )
            ).scalar_one()
            await session.execute(
                text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)"),
                {"role_id": role_id, "permission_id": permission_id},
            )
        await session.execute(
            text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)"),
            {"user_id": admin_id, "role_id": role_id},
        )
        await session.commit()


async def _stock_snapshot(session, sku_code: str) -> tuple[Decimal, Decimal, Decimal]:
    row = (
        await session.execute(
            text(
                "SELECT i.quantity_on_hand, i.quantity_reserved, "
                "i.quantity_on_hand - i.quantity_reserved AS available "
                "FROM skus s JOIN inventory_stocks i ON i.sku_id = s.id "
                "WHERE s.sku_code = :sku_code"
            ),
            {"sku_code": sku_code},
        )
    ).one()
    return row.quantity_on_hand, row.quantity_reserved, row.available


async def _order_status(session, order_id: str) -> str:
    return (
        await session.execute(text("SELECT status::text FROM orders WHERE id = :order_id"), {"order_id": order_id})
    ).scalar_one()


async def _reservation_statuses(session, order_id: str) -> list[str]:
    result = await session.execute(
        text("SELECT status FROM inventory_reservations WHERE order_id = :order_id ORDER BY created_at, id"),
        {"order_id": order_id},
    )
    return list(result.scalars().all())


async def _order_movement_rows(session, order_id: str) -> list[tuple[str, Decimal, Decimal, Decimal]]:
    result = await session.execute(
        text(
            "SELECT movement_type, quantity, quantity_before, quantity_after "
            "FROM inventory_movements WHERE reference_id = :order_id ORDER BY created_at, id"
        ),
        {"order_id": order_id},
    )
    return [(row.movement_type, row.quantity, row.quantity_before, row.quantity_after) for row in result.fetchall()]


async def _ledger_amounts(session, *, reference_type: str, order_id: str) -> dict[str, Decimal]:
    result = await session.execute(
        text(
            "SELECT account_type::text, amount FROM ledger_entries "
            "WHERE reference_type = :reference_type AND reference_id = :order_id"
        ),
        {"reference_type": reference_type, "order_id": order_id},
    )
    return {row[0]: row[1] for row in result.fetchall()}


@pytest.mark.asyncio
async def test_fresh_tenant_bootstrap_supports_returned_order_status_for_real_return_journey():
    """Fresh tenants must support the returned status used by return_order.

    S5-A requires a real fulfilled-order return path. A tenant bootstrapped from
    scratch must therefore have ``returned`` in its tenant-local order_status
    enum before the end-to-end journey can be promoted to a passing gate.
    """
    schema = f"t_s5a_return_audit_{uuid.uuid4().hex[:12]}"

    try:
        await bootstrap(schema, get_settings().DATABASE_URL)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    "SELECT enumlabel "
                    "FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = :schema "
                    "AND t.typname = 'order_status' "
                    "ORDER BY e.enumsortorder"
                ),
                {"schema": schema},
            )
            enum_labels = list(result.scalars().all())

        assert "returned" in enum_labels, (
            "STOP_AND_REPORT_CTO: fresh tenant bootstrap creates order_status "
            f"without 'returned'. labels={enum_labels!r}. The real return "
            "journey cannot persist OrderStatus.RETURNED until bootstrap or "
            "migration reconciliation is fixed."
        )
    finally:
        async with AsyncSessionLocal() as cleanup:
            await cleanup.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await cleanup.commit()


@pytest.mark.asyncio
async def test_existing_tenant_bootstrap_reconciles_missing_returned_order_status():
    """Re-running bootstrap must repair existing tenant enums missing returned."""
    schema = f"t_s5a_return_reconcile_{uuid.uuid4().hex[:12]}"

    try:
        async with AsyncSessionLocal() as setup:
            await setup.execute(text(f'CREATE SCHEMA "{schema}"'))
            await setup.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            await setup.execute(
                text(
                    "CREATE TYPE order_status AS ENUM ("
                    "'draft','confirmed','partially_paid','paid',"
                    "'fulfilled','cancelled','voided')"
                )
            )
            await setup.commit()

        await bootstrap(schema, get_settings().DATABASE_URL)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    "SELECT enumlabel "
                    "FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = :schema "
                    "AND t.typname = 'order_status' "
                    "ORDER BY e.enumsortorder"
                ),
                {"schema": schema},
            )
            enum_labels = list(result.scalars().all())

        assert "returned" in enum_labels
    finally:
        async with AsyncSessionLocal() as cleanup:
            await cleanup.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await cleanup.commit()


@pytest.mark.asyncio
async def test_s5a_fresh_tenant_real_user_journey_gate():
    """Fresh tenant supports the MVP user journey against real PostgreSQL."""
    await async_engine.dispose()
    tenant_id = uuid.uuid4()
    tenant_schema = _tenant_schema(tenant_id)
    tenant_code = f"S5A{tenant_id.hex[:12].upper()}"
    admin_id = uuid.uuid4()
    admin_email = f"s5a-admin-{tenant_id.hex[:10]}@example.com"
    admin_password = "S5aAdminPass2026!"  # pragma: allowlist secret  # test-only credential
    retailer_id = uuid.uuid4()
    isolation_tenant_id = uuid.uuid4()
    isolation_schema = _tenant_schema(isolation_tenant_id)

    try:
        await bootstrap(tenant_schema, get_settings().DATABASE_URL)
        await _seed_public_tenant_and_retailer(
            tenant_id=tenant_id, code=tenant_code, retailer_id=retailer_id
        )
        await _seed_admin(tenant_schema, admin_id, admin_email, admin_password)

        async with _tenant_session(tenant_schema, tenant_id) as session:
            await _run_import_runs_migration(session, tenant_schema)

        async with AsyncSessionLocal() as public_session:
            login_response = await login(
                LoginRequest(email=admin_email, password=admin_password),
                db=public_session,
            )
            assert login_response.success is True
            assert [tenant.id for tenant in login_response.data.available_tenants] == [str(tenant_id)]

            identity_token = decode_token(login_response.data.access_token)
            selected_response = await select_tenant(
                SelectTenantRequest(tenant_id=str(tenant_id)),
                token=identity_token,
                db=public_session,
            )
            admin_token = decode_token(selected_response.data.access_token)
            assert admin_token.tenant_id == str(tenant_id)
            assert admin_token.tenant_schema == tenant_schema
            assert admin_token.roles == ["admin"]

        async with _tenant_session(tenant_schema, tenant_id) as session:
            permission_rows = await session.execute(
                text(
                    "SELECT p.code FROM users u "
                    "JOIN user_roles ur ON ur.user_id = u.id "
                    "JOIN role_permissions rp ON rp.role_id = ur.role_id "
                    "JOIN permissions p ON p.id = rp.permission_id "
                    "WHERE u.id = :admin_id"
                ),
                {"admin_id": admin_id},
            )
            admin_permissions = set(permission_rows.scalars().all())
            for page_name, permission_code in ADMIN_PERMISSION_CODES:
                assert permission_code in admin_permissions, page_name

            import_service = ImportService()
            preview = await import_service.preview(
                session,
                tenant_id=tenant_id,
                filename="s5a-products.csv",
                file_bytes=b"sku_code,name,unit\nS5A-SKU-001,S5A Test SKU,piece\n",
            )
            await session.commit()
            assert preview.source.row_count == 1

            validate = await import_service.validate(
                session,
                import_id=preview.import_id,
                mapping={"sku_code": "sku_code", "name": "name", "unit": "unit"},
            )
            await session.commit()
            assert validate.status == "validated"
            assert validate.valid_rows == 1
            assert validate.error_rows == 0

            apply = await import_service.apply(
                session,
                import_id=preview.import_id,
                on_conflict="fail",
                applied_by=admin_id,
            )
            await session.commit()
            assert apply.status == "completed"
            assert apply.created == 1

            sku_id = (
                await session.execute(
                    text("SELECT id FROM skus WHERE sku_code = 'S5A-SKU-001'")
                )
            ).scalar_one()
            await set_retailer_price(
                SetPriceRequest(retailer_id=str(retailer_id), sku_id=str(sku_id), price=Decimal("25.00")),
                token=admin_token,
                db=session,
            )
            await session.commit()

            await InventoryService().adjust_stock(
                session,
                sku_code="S5A-SKU-001",
                quantity=Decimal("10.00"),
                reason="S5-A opening stock",
                adjusted_by=str(admin_id),
            )
            await session.commit()
            assert await _stock_snapshot(session, "S5A-SKU-001") == (
                Decimal("10.00"),
                Decimal("0.00"),
                Decimal("10.00"),
            )

            stock_before_failed_confirm = await _stock_snapshot(session, "S5A-SKU-001")
            with pytest.raises(HTTPException) as failed_create:
                await create_order(
                    WholesalerOrderCreateRequest(
                        retailer_id=str(retailer_id),
                        items=[{"sku_code": "S5A-SKU-001", "quantity": 11}],
                        notes="S5-A rollback probe",
                    ),
                    token=admin_token,
                    db=session,
                )
            assert failed_create.value.status_code == 400
            leaked_orders = (
                await session.execute(
                    text("SELECT count(*) FROM orders WHERE notes = 'S5-A rollback probe'")
                )
            ).scalar_one()
            leaked_reservations = (
                await session.execute(text("SELECT count(*) FROM inventory_reservations"))
            ).scalar_one()
            assert leaked_orders == 0
            assert leaked_reservations == 0
            assert await _stock_snapshot(session, "S5A-SKU-001") == stock_before_failed_confirm

            order = await create_order(
                WholesalerOrderCreateRequest(
                    retailer_id=str(retailer_id),
                    items=[{"sku_code": "S5A-SKU-001", "quantity": 3}],
                    notes="S5-A real user journey",
                ),
                token=admin_token,
                db=session,
            )
            await session.commit()
            order_id = order.data.id
            assert order.data.status.value == "draft"

            confirmed = await confirm_order(order_id, token=admin_token, db=session)
            await session.commit()
            assert confirmed.data["status"] == "confirmed"
            assert await _reservation_statuses(session, order_id) == ["reserved"]
            assert await _stock_snapshot(session, "S5A-SKU-001") == (
                Decimal("10.00"),
                Decimal("3.00"),
                Decimal("7.00"),
            )

            paid = await pay_order(
                order_id,
                token=admin_token,
                db=session,
                payment_input=PayOrderRequest(method="cash", amount=Decimal("75.00")),
            )
            await session.commit()
            assert paid.data["status"] == "paid"

            fulfilled = await fulfill_order(order_id, token=admin_token, db=session)
            await session.commit()
            assert fulfilled.data["status"] == "fulfilled"
            assert await _reservation_statuses(session, order_id) == ["consumed"]
            assert await _stock_snapshot(session, "S5A-SKU-001") == (
                Decimal("7.00"),
                Decimal("0.00"),
                Decimal("7.00"),
            )
            assert await _order_movement_rows(session, order_id) == [
                ("deduction", Decimal("-3.00"), Decimal("10.00"), Decimal("7.00"))
            ]

            returned = await return_order(order_id, token=admin_token, db=session)
            await session.commit()
            assert returned.data["status"] == "returned"
            assert await _order_status(session, order_id) == "returned"
            assert await _stock_snapshot(session, "S5A-SKU-001") == (
                Decimal("10.00"),
                Decimal("0.00"),
                Decimal("10.00"),
            )
            assert await _order_movement_rows(session, order_id) == [
                ("deduction", Decimal("-3.00"), Decimal("10.00"), Decimal("7.00")),
                ("restock", Decimal("3.00"), Decimal("7.00"), Decimal("10.00")),
            ]
            assert await _ledger_amounts(session, reference_type="refund", order_id=order_id) == {
                "cash": Decimal("-75.0000"),
                "revenue": Decimal("75.0000"),
            }

        await bootstrap(isolation_schema, get_settings().DATABASE_URL)
        async with _tenant_session(isolation_schema, isolation_tenant_id) as other_session:
            other_sku_id = (
                await other_session.execute(
                    text(
                        "INSERT INTO skus (sku_code, name, unit, is_active) "
                        "VALUES ('S5A-SKU-001', 'Other Tenant SKU', 'piece', true) RETURNING id"
                    )
                )
            ).scalar_one()
            await other_session.execute(
                text(
                    "INSERT INTO inventory_stocks (sku_id, quantity_on_hand, quantity_reserved) "
                    "VALUES (:sku_id, 20.00, 0.00)"
                ),
                {"sku_id": other_sku_id},
            )
            other_order_id = (
                await other_session.execute(
                    text(
                        "INSERT INTO orders (wholesaler_id, retailer_id, total_amount, notes) "
                        "VALUES (:wholesaler_id, :retailer_id, 100.00, 'S5-A isolation') RETURNING id"
                    ),
                    {"wholesaler_id": isolation_tenant_id, "retailer_id": uuid.uuid4()},
                )
            ).scalar_one()
            await other_session.execute(
                text(
                    "INSERT INTO order_items (order_id, product_name, sku_code, quantity, unit_price, subtotal) "
                    "VALUES (:order_id, 'Other Tenant SKU', 'S5A-SKU-001', 4, 25.00, 100.00)"
                ),
                {"order_id": other_order_id},
            )
            await other_session.commit()
            other_token = TokenPayload(
                user_id=str(uuid.uuid4()),
                tenant_id=str(isolation_tenant_id),
                tenant_schema=isolation_schema,
                roles=["admin"],
            )
            try:
                await confirm_order(str(other_order_id), token=other_token, db=other_session)
            except Exception as exc:
                if "InvalidCachedStatementError" not in str(exc):
                    raise
                await other_session.rollback()
                await other_session.execute(text(f'SET LOCAL search_path TO "{isolation_schema}", public'))
                await confirm_order(str(other_order_id), token=other_token, db=other_session)
            await other_session.commit()
            assert await _stock_snapshot(other_session, "S5A-SKU-001") == (
                Decimal("20.00"),
                Decimal("4.00"),
                Decimal("16.00"),
            )

        async with _tenant_session(tenant_schema, tenant_id) as session:
            assert await _stock_snapshot(session, "S5A-SKU-001") == (
                Decimal("10.00"),
                Decimal("0.00"),
                Decimal("10.00"),
            )
    finally:
        async with AsyncSessionLocal() as cleanup:
            await cleanup.execute(text(f'DROP SCHEMA IF EXISTS "{isolation_schema}" CASCADE'))
            await cleanup.execute(text(f'DROP SCHEMA IF EXISTS "{tenant_schema}" CASCADE'))
            await cleanup.execute(
                text("DELETE FROM public.wholesaler_retailer_bindings WHERE wholesaler_id = :tenant_id"),
                {"tenant_id": tenant_id},
            )
            await cleanup.execute(text("DELETE FROM public.retailers WHERE id = :retailer_id"), {"retailer_id": retailer_id})
            await cleanup.execute(text("DELETE FROM public.wholesalers WHERE id = :tenant_id"), {"tenant_id": tenant_id})
            await cleanup.commit()
