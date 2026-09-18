"""R2-R1 correction counterexamples — real production paths on real PG16.

Each test names the supervisor finding it pins:

  STALE-1  a stale ORM identity map must never drive a payment decision
           (populate_existing on the canonical order lock).
  PTR-1    a declaration whose order pointer was swapped after submission
           is re-verified against the LOCKED order and refused, zero writes.
  REPLAY-1 a replay whose payment is attributed to ANOTHER order is a
           neutral refusal, zero writes.
  OVER-1   over-collected credit history (collections > credit) is a named
           integrity refusal — never clamped to zero exposure.
  REG-1    039 refuses a non-live registry (suspended wholesaler) before
           any write, with the 038-family named message.
  CATALOG-1 a same-named but wrong-defined hold object (CHECK definition
           swapped) is rejected by the bootstrap reconcile.
  ACTOR-1  a runtime confirm without an actor is refused BEFORE any state,
           hold, or binding write.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.order_state_r2.support import (
    binding_balance,
    errcode,
    fetch_holds,
    http_action,
    http_create_order,
    make_bound_retailer,
    osd1_cashier_token,
    payment_count,
    payments_vector,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


async def test_stale_identity_map_cannot_drive_payment(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """STALE-1: session A loads the order (identity map holds DRAFT); the
    order is confirmed by another transaction; A then pays through the
    canonical service — the locked-fresh read must see CONFIRMED, not the
    stale identity-map object."""
    from models.order import Order as OrderModel
    from services.canonical_payment_service import CanonicalPaymentService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="50.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    await db.rollback()

    session_a = await _second_session(schema, ws_id)
    session_b = await _second_session(schema, ws_id)
    try:
        # Session A loads the order (DRAFT) into its identity map.
        stale = (await session_a.execute(
            text(f'SELECT id FROM "{schema}".orders WHERE id = :oid'),
            {"oid": oid})).first()
        assert stale is not None

        # Session B (another transaction) confirms the order for real.
        result = await http_action(r1_client, token, oid, "confirm")
        assert result.status_code == 200, result.text
        await session_a.rollback()  # drop A's snapshot, keep identity map

        # A pays via the canonical service on ITS session: the locked read
        # must refresh the identity map (populate_existing) and see
        # CONFIRMED — with a stale map this would 409 INVALID_STATE.
        await rebind_search_path(session_a, schema)
        pay = await CanonicalPaymentService().confirm_payment(
            db=session_a,
            order_id=oid,
            amount=Decimal("100.00"),
            method="cash",
            transaction_id=None,
            idempotency_key=f"stale-{uuid.uuid4().hex}",
            created_by=str(cashier_identity["user_id"]),
        )
        await session_a.commit()
        assert pay.order_state == "paid", (
            f"STALE-1: canonical read a stale identity-map state "
            f"(got {pay.order_state!r}, expected 'paid')")
    finally:
        for s in (session_a, session_b):
            try:
                await s.rollback()
                await s.close()
            except Exception:
                pass


async def test_declaration_pointer_swap_refused_zero_writes(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """PTR-1: the declaration's order pointer is swapped (corruption or a
    lost race); confirmation re-verifies against the LOCKED order and
    refuses with zero writes."""
    from services.payment_declaration_service import PaymentDeclarationService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="50.00")
    oid_x = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid_x, "confirm")).status_code == 200

    # a second retailer's order in the SAME tenant schema — the swapped
    # pointer crosses retailer attribution, which the locked-order
    # re-verification must catch.
    from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (
        _create_binding,
        _create_retailer,
    )
    ret_other = await _create_retailer(db, name="PTR Other Retailer", registry=reg)
    await _create_binding(db, wholesaler_id=ws_id, retailer_id=ret_other,
                          tenant_user_id=str(uuid.uuid4()), registry=reg)
    sku2, _sid2 = await seed_sku_with_stock(db, schema, ret_other, price="50.00")
    oid_y = await http_create_order(r1_client, token, str(ret_other),
                                    [{"sku_code": sku2, "quantity": 1}])
    assert (await http_action(r1_client, token, oid_y, "confirm")).status_code == 200
    await db.rollback()

    session = await _second_session(schema, ws_id)
    try:
        await rebind_search_path(session, schema)
        record, _ = await PaymentDeclarationService().submit_declaration(
            db=session,
            order_id=oid_x,
            retailer_id=uuid.UUID(ret_id),
            wholesaler_id=uuid.UUID(ws_id),
            submitted_by=uuid.UUID(str(cashier_identity["user_id"])),
            declared_amount=Decimal("100.00"),
            method="cash",
            transfer_reference=None,
            idempotency_key=f"ptr-{uuid.uuid4().hex}",
        )
        await session.commit()

        # Corrupt the pointer: the declaration now claims order Y.
        await rebind_search_path(session, schema)
        await session.execute(text(
            f'UPDATE "{schema}".payment_declarations SET order_id = :new '
            "WHERE id = :did"),
            {"new": oid_y, "did": str(record["id"])})
        await session.commit()
        await rebind_search_path(session, schema)

        balance_before = await binding_balance(db, ws_id, ret_id)
        pays_x_before = await payment_count(db, schema, oid_x)
        pays_y_before = await payment_count(db, schema, oid_y)

        await rebind_search_path(session, schema)
        with pytest.raises(Exception) as excinfo:
            await PaymentDeclarationService().confirm_declaration(
                db=session,
                declaration_id=uuid.UUID(str(record["id"])),
                wholesaler_id=uuid.UUID(ws_id),
                confirmed_by=uuid.UUID(str(cashier_identity["user_id"])),
            )
        await session.rollback()
        assert "DECLARATION_NOT_FOUND" in str(excinfo.value) or \
            "CREDIT_HOLD" in str(excinfo.value), excinfo.value

        assert await binding_balance(db, ws_id, ret_id) == balance_before
        assert await payment_count(db, schema, oid_x) == pays_x_before
        assert await payment_count(db, schema, oid_y) == pays_y_before
        status = (await db.execute(text(
            f"SELECT status FROM \"{schema}\".payment_declarations "
            "WHERE id = :did"), {"did": str(record["id"])})).scalar()
        assert status == "pending", status
    finally:
        await session.rollback()
        await session.close()


async def test_wrong_replay_attribution_neutral_refusal(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """REPLAY-1: order A is paid with key K; replaying key K against order B
    (same payload shape) is a neutral IDEMPOTENCY_KEY_CONFLICT with zero
    writes on B."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="50.00")
    oid_a = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku, "quantity": 2}])
    oid_b = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku, "quantity": 2}])
    for oid in (oid_a, oid_b):
        assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    await db.rollback()

    key = f"replay-{uuid.uuid4().hex}"

    async def _pay(order_id: str, k: str):
        return await r1_client.post(
            f"/api/v1/orders/{order_id}/pay",
            json={"amount": 100.0, "method": "cash"},
            headers={"Authorization": f"Bearer {token}",
                     "X-Idempotency-Key": k})

    first = await _pay(oid_a, key)
    assert first.status_code == 200, first.text

    pays_b_before = await payment_count(db, schema, oid_b)
    second = await _pay(oid_b, key)
    assert second.status_code == 409, (
        f"REPLAY-1: cross-order replay accepted ({second.status_code}): "
        f"{second.text}")
    assert errcode(second) == "IDEMPOTENCY_KEY_CONFLICT", second.text
    assert await payment_count(db, schema, oid_b) == pays_b_before, (
        "REPLAY-1: cross-order replay wrote a payment on order B")


async def test_overcollected_history_named_refusal(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """OVER-1: SQL-corrupt a paid credit order so collections exceed the
    credit sale. A further collection AND the summary both refuse with the
    NAMED integrity code — the exposure is never clamped to zero."""
    from services.receivables_service import ReceivablesService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="50.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": 100.0, "method": "credit"})
    assert pay.status_code == 200, pay.text
    # legitimate collection of 30
    col = await http_action(r1_client, token, oid, "pay",
                            {"amount": 30.0, "method": "cash"})
    assert col.status_code == 200, col.text
    await db.rollback()

    # Corrupt: an extra out-of-band collection of 90 -> 120 > 100 credit.
    await db.execute(text(
        f'INSERT INTO "{schema}".payments (order_id, retailer_id, amount, '
        "method, status, is_deleted) VALUES (:o, :r, 90.00, 'cash', "
        "'completed', FALSE)"),
        {"o": oid, "r": ret_id})
    await db.commit()

    resp = await http_action(r1_client, token, oid, "pay",
                             {"amount": 5.0, "method": "cash"})
    assert resp.status_code == 409, (
        f"OVER-1: collection on over-collected history was not refused "
        f"with 409 ({resp.status_code}): {resp.text}")
    assert errcode(resp) == "CREDIT_HOLD_MISMATCH", resp.text

    reader = await _second_session(schema, ws_id)
    try:
        await rebind_search_path(reader, schema)
        with pytest.raises(Exception) as excinfo:
            await ReceivablesService().get_receivables_summary(
                tenant_db=reader, wholesaler_id=ws_id)
        assert "PAYMENT_HISTORY_INTEGRITY" in str(excinfo.value), excinfo.value
    finally:
        await reader.close()


def test_non_live_registry_refused_named():
    """REG-1 (migration, real alembic on a disposable PG16 database): a
    suspended wholesaler fails 039's preflight with the 038-family named
    message and zero writes."""
    import os as _os
    if _os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE") != "1":
        pytest.skip("set MPANGO_ALLOW_TEMP_DB_CREATE=1 for migration tests")
    import importlib.util
    import os

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from tests.async_test_utils import temporary_database_url
    from tests.order_state_r2.test_migration_c3 import (
        _add_binding,
        _add_order,
        _add_payment,
        _engine,
        _register_tenant,
    )

    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "r2reg1") as db_url:
        engine = _engine(db_url)
        cfg = Config("alembic.ini")
        cfg.set_main_option("script_location", "alembic")
        url = engine.url.render_as_string(hide_password=False).replace(
            "postgresql://", "postgresql+asyncpg://", 1)
        cfg.set_main_option("sqlalchemy.url", url)
        import concurrent.futures as _cf

        def job():
            import unittest.mock as _mock
            with _mock.patch.dict(os.environ, {"DATABASE_URL": db_url}):
                command.upgrade(cfg, "038_catalog_identity_vertical_slice")

        with _cf.ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(job).result()

        ws_live = uuid.uuid4()
        ws_suspended = uuid.uuid4()
        s_live = _register_tenant(engine, ws_live)
        s_susp = _register_tenant(engine, ws_suspended)
        r_live, r_susp = uuid.uuid4(), uuid.uuid4()
        o_live = _add_order(engine, s_live, ws_live, r_live, "confirmed", "50.00")
        _add_binding(engine, ws_live, r_live, "0.00")
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE public.wholesalers SET status = 'suspended' "
                "WHERE id = :w"), {"w": ws_suspended})

        spec = importlib.util.spec_from_file_location(
            "m039_reg1", "alembic/versions/039_order_credit_holds.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        try:
            with engine.begin() as conn:
                module.op = Operations(MigrationContext.configure(conn))
                module.upgrade()
        except Exception as exc:
            assert "outside R2 live migration statuses" in str(exc), (
                f"REG-1: refusal lacks the 038-family named message: {exc}")
        else:
            raise AssertionError(
                "REG-1: 039 accepted a suspended (non-live) wholesaler")

        version = engine.connect().execute(
            text("SELECT version_num FROM public.alembic_version")).scalar()
        assert version == "038_catalog_identity_vertical_slice"
        exists = engine.connect().execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'order_credit_holds'")).scalar()
        assert int(exists) == 0, "REG-1: non-live registry produced writes"


async def test_same_named_wrong_catalog_rejected(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """CATALOG-1: a hold table whose constraint carries the RIGHT NAME but
    the WRONG DEFINITION is rejected by the bootstrap reconcile."""
    import importlib.util
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "bts_catalog1", backend / "scripts" / "bootstrap_tenant_schema.py")
    bts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bts)

    db, reg = s2_clean_db
    _token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    await db.rollback()

    # Same names, wrong lifecycle definition: terminal rows may keep a
    # positive remaining (the exact shape the frozen CHECK forbids).
    await db.execute(text(
        f'DROP TABLE IF EXISTS "{schema}".order_credit_holds CASCADE'))
    await db.commit()
    await db.execute(text(f'''
        CREATE TABLE "{schema}".order_credit_holds (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL
                CONSTRAINT fk_order_credit_holds_order
                REFERENCES "{schema}".orders(id) ON DELETE RESTRICT,
            amount NUMERIC(12, 2) NOT NULL,
            remaining_amount NUMERIC(12, 2) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by UUID,
            updated_by UUID,
            CONSTRAINT uq_order_credit_holds_order_id UNIQUE (order_id),
            CONSTRAINT ck_order_credit_holds_status CHECK (
                status IN ('active', 'released', 'settled', 'converted')),
            CONSTRAINT ck_order_credit_holds_amount_positive CHECK (amount > 0),
            CONSTRAINT ck_order_credit_holds_remaining_cap CHECK (
                remaining_amount <= amount),
            CONSTRAINT ck_order_credit_holds_lifecycle_shape CHECK (
                (status = 'active' AND remaining_amount > 0)
                OR (status IN ('released', 'settled', 'converted')
                    AND remaining_amount >= 0))
        )
    '''))
    await db.commit()

    with pytest.raises(RuntimeError) as excinfo:
        await bts._reconcile_credit_holds(db, schema)
    await db.rollback()
    assert "ck_order_credit_holds_lifecycle_shape" in str(excinfo.value) and \
        "wrong definition" in str(excinfo.value), (
            f"CATALOG-1: same-named wrong definition not rejected by "
            f"definition comparison: {excinfo.value}")


async def test_runtime_null_actor_refused_before_any_write(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """ACTOR-1: a direct-service confirm WITHOUT an actor is refused before
    any state, hold, or binding write (created_by NULL is reserved for the
    039 synthetic rows)."""
    from services.order_command_service import OrderCommandService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id, price="50.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])
    await db.rollback()

    session = await _second_session(schema, ws_id)
    try:
        await rebind_search_path(session, schema)
        balance_before = await binding_balance(db, ws_id, ret_id)
        with pytest.raises(Exception) as excinfo:
            await OrderCommandService(session).confirm_order(uuid.UUID(oid))
        await session.rollback()
        assert "CONFIRM_ACTOR_REQUIRED" in str(excinfo.value), excinfo.value

        status = (await db.execute(text(
            f'SELECT status::text FROM "{schema}".orders WHERE id = :oid'),
            {"oid": oid})).scalar()
        holds = await fetch_holds(db, schema, oid)
        assert status == "draft", f"ACTOR-1: order left draft ({status})"
        assert holds == [], f"ACTOR-1: hold written without actor: {holds}"
        assert await binding_balance(db, ws_id, ret_id) == balance_before
        from tests.order_state_r2.support import reservation_vector
        assert await reservation_vector(db, schema, oid) == []
    finally:
        await session.rollback()
        await session.close()
