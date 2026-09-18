"""E1 source-revision counterexamples — F1/F2/F3 of the V1 static review.

Real production paths on real PG16; every gate names its finding:

  E1-F1   bootstrap reconcile must validate per-order effective-history
          legality and the per-order hold contract BEFORE trusting any
          financial aggregate (catalog isomorphism and summing to the
          "right" total prove nothing).
  E1-F2   credit-sale collection requires EXACTLY ONE effective credit
          payment (a split history summing to the order total is refused)
          on the SAME seam for the direct pay path and the declaration
          confirmation; soft-deleted duplicates are not effective history.
  E1-F3   the binding-cache update is the LAST financial write of the
          cash/transfer settlement path (hold -> payment/receipt/ledger
          -> binding) and a fault at any step rolls the whole settlement
          back inside the one transaction.
"""
from __future__ import annotations

import importlib.util
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.order_state_r1.support import (
    _second_session,
    binding_balance,
    http_action,
    http_create_order,
    make_bound_retailer,
    osd1_cashier_token,
    seed_sku_with_stock,
)
from tests.order_state_r2.support import (
    fetch_holds,
    payment_count,
)

pytestmark = pytest.mark.asyncio


async def _load_bts():
    backend = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "bts_e1", backend / "scripts" / "bootstrap_tenant_schema.py")
    bts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bts)
    return bts


async def _paid_credit_order(r1_client, token, db, pool, reg, total="60.00"):
    """A runtime-legal PAID credit order: converted hold 60/0, binding 60."""
    ret_id, schema, ws_id = await make_bound_retailer(db, pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price=total,
                                          quantity=1)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": float(total), "method": "credit"})
    assert pay.status_code == 200, pay.text
    await db.rollback()
    return oid, ret_id, schema, ws_id


# ---------------------------------------------------------------------------
# E1-F1: bootstrap reconcile — per-order legality before any aggregate
#
# The reconcile is a WHOLE-SCHEMA gate, so these counterexamples live in
# DEDICATED bootstrapped tenant schemas (never the shared fixture schema,
# whose contents other suites mutate). Each scenario is the deterministic
# SQL shape from the V1 finding: catalog-conformant, row CHECKs legal, and
# every FINANCIAL AGGREGATE exactly consistent — only the per-order
# history/hold gates can refuse.
# ---------------------------------------------------------------------------


async def _dedicated_tenant(db, reg, ws_id, label, *, retailers=1):
    """Bootstrap a fresh empty tenant schema; the bootstrap itself runs
    the reconcile (the empty-history positive control). Returns
    (bts, schema, retailer_ids)."""
    import os as _os

    from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (
        _create_binding,
        _create_retailer,
    )

    bts = await _load_bts()
    schema = f"t_e1f1_{label}_{uuid.uuid4().hex[:10]}"
    url = _os.environ["DATABASE_URL"].replace(
        "postgresql://", "postgresql+asyncpg://", 1)
    await bts.bootstrap(schema, url)

    rets = []
    for i in range(retailers):
        ret = await _create_retailer(db, name=f"E1F1 {label} R{i+1}",
                                     registry=reg)
        await _create_binding(db, wholesaler_id=ws_id, retailer_id=ret,
                              tenant_user_id=str(uuid.uuid4()), registry=reg)
        rets.append(str(ret))
    return bts, schema, rets


async def _seed_order(db, schema, ws_id, ret_id, status, total,
                      hold=None, payments=()):
    oid = uuid.uuid4()
    await db.execute(text(
        f'INSERT INTO "{schema}".orders (id, wholesaler_id, retailer_id, '
        "status, total_amount) "
        f'VALUES (:i, :w, :r, CAST(:s AS "{schema}".order_status), :t)'),
        {"i": oid, "w": ws_id, "r": ret_id, "s": status, "t": total})
    for pay_ret, amount, method in payments:
        await db.execute(text(
            f'INSERT INTO "{schema}".payments (order_id, retailer_id, '
            "amount, method, status) VALUES (:o, :r, :a, :m, 'completed')"),
            {"o": oid, "r": pay_ret, "a": amount, "m": method})
    if hold is not None:
        amount, remaining, hold_status = hold
        await db.execute(text(
            f'INSERT INTO "{schema}".order_credit_holds '
            "(order_id, amount, remaining_amount, status) "
            "VALUES (:o, :a, :rm, :s)"),
            {"o": oid, "a": amount, "rm": remaining, "s": hold_status})
    return str(oid)


async def _set_binding_balance(db, ws_id, ret_id, balance):
    await db.execute(text(
        "UPDATE public.wholesaler_retailer_bindings "
        "SET outstanding_balance = :b, updated_at = now() "
        "WHERE wholesaler_id = :w AND retailer_id = :r AND is_deleted IS FALSE"),
        {"b": balance, "w": ws_id, "r": ret_id})


async def test_e1f1_retailer_mismatched_payment_with_consistent_totals_rejected(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """E1-F1 counterexample 1: a PAID credit order whose single credit
    payment is attributed to ANOTHER retailer. The four-way aggregate
    never reads payment.retailer_id, so every total still agrees — only
    the per-order history gate can refuse it."""
    db, reg = s2_clean_db
    ws_id = provisioned_pool.tenants["a"]["ws_id"]
    bts, schema, (ret_a, ret_b) = await _dedicated_tenant(
        db, reg, ws_id, "mismatch", retailers=2)
    try:
        await _seed_order(db, schema, ws_id, ret_a, "paid", "60.00",
                          hold=("60.00", "0.00", "converted"),
                          payments=[(ret_b, "60.00", "credit")])
        await _set_binding_balance(db, ws_id, ret_a, "60.00")  # exposure 60
        await _set_binding_balance(db, ws_id, ret_b, "0.00")
        await db.commit()

        with pytest.raises(RuntimeError) as excinfo:
            await bts._reconcile_credit_holds(db, schema)
        assert "illegal history" in str(excinfo.value), excinfo.value
        await db.rollback()
    finally:
        await db.rollback()
        await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await db.commit()


async def test_e1f1_hold_snapshot_inconsistent_with_lifecycle_rejected(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """E1-F1 counterexample 2: a CONFIRMED order whose active hold carries
    remaining=5 with binding=5 — row CHECKs legal, aggregate exactly
    consistent, and 55 of reserved exposure silently lost. The per-order
    hold contract (want remaining = total - effective paid = 60) refuses."""
    db, reg = s2_clean_db
    ws_id = provisioned_pool.tenants["a"]["ws_id"]
    bts, schema, (ret_a,) = await _dedicated_tenant(
        db, reg, ws_id, "snapshot")
    try:
        await _seed_order(db, schema, ws_id, ret_a, "confirmed", "60.00",
                          hold=("60.00", "5.00", "active"))
        await _set_binding_balance(db, ws_id, ret_a, "5.00")  # holds sum 5
        await db.commit()

        with pytest.raises(RuntimeError) as excinfo:
            await bts._reconcile_credit_holds(db, schema)
        assert "inconsistent with the order's own history" in str(excinfo.value), (
            excinfo.value)
        await db.rollback()
    finally:
        await db.rollback()
        await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await db.commit()


async def test_e1f1_legal_history_reconcile_positive_controls(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """E1-F1 positive controls: (a) a freshly bootstrapped empty tenant
    reconciles GREEN inside bootstrap itself; (b) a seeded tenant whose
    shapes mirror legal runtime lifecycles — confirmed active hold, a
    converted credit sale, a settled full-cash order — reconciles GREEN.
    The new gates refuse corruption, never legal lifecycles."""
    db, reg = s2_clean_db
    ws_id = provisioned_pool.tenants["a"]["ws_id"]
    bts, schema, (ret_a,) = await _dedicated_tenant(db, reg, ws_id, "legal")
    try:
        await _seed_order(db, schema, ws_id, ret_a, "confirmed", "60.00",
                          hold=("60.00", "60.00", "active"))
        await _seed_order(db, schema, ws_id, ret_a, "paid", "60.00",
                          hold=("60.00", "0.00", "converted"),
                          payments=[(ret_a, "60.00", "credit")])
        await _seed_order(db, schema, ws_id, ret_a, "paid", "30.00",
                          hold=("30.00", "0.00", "settled"),
                          payments=[(ret_a, "30.00", "cash")])
        # active 60 + exposure (credit 60 - cash 0) = 120
        await _set_binding_balance(db, ws_id, ret_a, "120.00")
        await db.commit()

        await bts._reconcile_credit_holds(db, schema)  # GREEN
        await db.rollback()
    finally:
        await db.rollback()
        await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await db.commit()


# ---------------------------------------------------------------------------
# E1-F2: exactly one effective credit before credit-sale collection
# ---------------------------------------------------------------------------


async def _split_credit_history(db, schema, oid, half="30.00"):
    """SQL-corrupt the single credit payment into TWO effective rows that
    keep the effective credit total unchanged (split credit history)."""
    await db.execute(text(
        f'UPDATE "{schema}".payments SET amount = :half '
        "WHERE order_id = :o AND method = 'credit' AND is_deleted IS FALSE"),
        {"half": half, "o": oid})
    row = (await db.execute(text(
        f'SELECT retailer_id FROM "{schema}".payments '
        "WHERE order_id = :o AND method = 'credit' LIMIT 1"),
        {"o": oid})).scalar()
    await db.execute(text(
        f'INSERT INTO "{schema}".payments '
        "(order_id, retailer_id, amount, method, status, is_deleted) "
        "VALUES (:o, :r, :half, 'credit', 'completed', FALSE)"),
        {"o": oid, "r": row, "half": half})
    await db.commit()


async def test_e1f2_split_credit_rejected_on_direct_collection(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """E1-F2: two effective credit rows of 30 each (total still 60) must be
    refused on a DIRECT cash collection with the named contract refusal —
    the total check alone cannot legalize a split history."""
    from fastapi import HTTPException as _HttpExc
    from services.canonical_payment_service import CanonicalPaymentService
    from tests.order_state_r1.support import rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _paid_credit_order(
        r1_client, token, db, provisioned_pool, reg)
    await _split_credit_history(db, schema, oid)

    session = await _second_session(schema, ws_id)
    try:
        await rebind_search_path(session, schema)
        with pytest.raises(_HttpExc) as excinfo:
            await CanonicalPaymentService().confirm_payment(
                db=session, order_id=oid, amount=Decimal("10.00"),
                method="cash", transaction_id=None,
                idempotency_key=f"e1f2d-{uuid.uuid4().hex}",
                created_by=str(cashier_identity["user_id"]))
        detail = str(excinfo.value.detail)
        assert "CREDIT_HOLD_MISMATCH" in detail, excinfo.value.detail
        assert "exactly one effective credit" in detail, excinfo.value.detail
    finally:
        await session.rollback()
        await session.close()


async def test_e1f2_split_credit_rejected_on_declaration_confirm(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """E1-F2: the SAME refusal must fire through the declaration
    confirmation — both entries reuse the canonical hold-contract seam."""
    from fastapi import HTTPException as _HttpExc
    from services.payment_declaration_service import PaymentDeclarationService
    from tests.order_state_r1.support import rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="60.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    # declare cash BEFORE the corruption, pay the credit, then split the
    # history — the confirmation lands on the corrupted PAID order
    session = await _second_session(schema, ws_id)
    try:
        await rebind_search_path(session, schema)
        record, _ = await PaymentDeclarationService().submit_declaration(
            db=session, order_id=oid, retailer_id=uuid.UUID(ret_id),
            wholesaler_id=uuid.UUID(ws_id),
            submitted_by=uuid.UUID(str(cashier_identity["user_id"])),
            declared_amount=Decimal("10.00"), method="cash",
            transfer_reference=None,
            idempotency_key=f"e1f2n-{uuid.uuid4().hex}",
        )
        await session.commit()

        pay = await http_action(r1_client, token, oid, "pay",
                                {"amount": 60.0, "method": "credit"})
        assert pay.status_code == 200, pay.text
        await _split_credit_history(db, schema, oid)

        await rebind_search_path(session, schema)
        with pytest.raises(_HttpExc) as excinfo:
            await PaymentDeclarationService().confirm_declaration(
                db=session, declaration_id=uuid.UUID(str(record["id"])),
                wholesaler_id=uuid.UUID(ws_id),
                confirmed_by=uuid.UUID(str(cashier_identity["user_id"])))
        detail = str(excinfo.value.detail)
        assert "CREDIT_HOLD_MISMATCH" in detail, excinfo.value.detail
        assert "exactly one effective credit" in detail, excinfo.value.detail
    finally:
        await session.rollback()
        await session.close()


async def test_e1f2_soft_deleted_duplicate_credit_is_legal(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """E1-F2 positive control: a soft-deleted duplicate credit row is NOT
    effective history — the effective single credit sale of 60 remains
    collectable and the collection succeeds."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _paid_credit_order(
        r1_client, token, db, provisioned_pool, reg)

    await db.execute(text(
        f'INSERT INTO "{schema}".payments '
        "(order_id, retailer_id, amount, method, status, is_deleted) "
        "VALUES (:o, :r, 60.00, 'credit', 'completed', TRUE)"),
        {"o": oid, "r": ret_id})
    await db.commit()

    col = await http_action(r1_client, token, oid, "pay",
                            {"amount": 10.0, "method": "cash"})
    assert col.status_code == 200, col.text
    # payment_count counts ALL rows: the effective credit + the soft-deleted
    # duplicate + the successful collection
    assert await payment_count(db, schema, oid) == 3


# ---------------------------------------------------------------------------
# E1-F3: binding cache is the LAST settlement write; whole-path rollback
# ---------------------------------------------------------------------------

_SPY_CLASSES = (
    ("hold", re.compile(r"\bUPDATE\s+(?:\"[^\"]+\"\.)?order_credit_holds\b", re.I)),
    ("payment_insert", re.compile(r"\bINSERT INTO\s+(?:\"[^\"]+\"\.)?payments\b", re.I)),
    ("ledger_insert", re.compile(r"\bINSERT INTO\s+(?:\"[^\"]+\"\.)?ledger_entries\b", re.I)),
    ("payments_update", re.compile(r"\bUPDATE\s+(?:\"[^\"]+\"\.)?payments\b", re.I)),
    ("binding_update", re.compile(
        r"\bUPDATE\s+(?:public\.)?wholesaler_retailer_bindings\b", re.I)),
)


async def test_e1f3_settlement_binding_write_is_last_real_sql_order(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """E1-F3: real-SQL write-order oracle over a full cash settlement —
    every payment-side write (payment row, ledger posting, cash/transfer
    batch settle) and the hold reduction must precede the binding-cache
    UPDATE; the binding write is strictly the LAST of them."""
    from sqlalchemy import event as _sa_event
    from services.canonical_payment_service import CanonicalPaymentService
    from tests.order_state_r1.support import rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="60.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    await db.rollback()

    session = await _second_session(schema, ws_id)
    engine = session.get_bind()
    sequence: list[str] = []

    def _spy(conn, cursor, statement, parameters, context, executemany):
        for label, pattern in _SPY_CLASSES:
            if pattern.search(statement):
                sequence.append(label)
                return

    try:
        await rebind_search_path(session, schema)
        _sa_event.listen(engine, "before_cursor_execute", _spy)
        try:
            result = await CanonicalPaymentService().confirm_payment(
                db=session, order_id=oid, amount=Decimal("60.00"),
                method="cash", transaction_id=None,
                idempotency_key=f"e1f3-{uuid.uuid4().hex}",
                created_by=str(cashier_identity["user_id"]))
        finally:
            _sa_event.remove(engine, "before_cursor_execute", _spy)
        await session.commit()
        assert str(result.order_state) == "paid", result.order_state

        assert sequence.count("binding_update") == 1, sequence
        binding_idx = sequence.index("binding_update")
        payment_side = [
            (label, i) for i, label in enumerate(sequence)
            if label in ("payment_insert", "ledger_insert", "payments_update")
        ]
        assert payment_side, sequence
        assert sequence.count("hold") >= 1, sequence
        first_hold = sequence.index("hold")
        last_payment_side = max(i for _, i in payment_side)
        assert binding_idx > last_payment_side, (
            f"E1-F3: the binding-cache update must be the LAST financial "
            f"write of the settlement path (sequence={sequence}; binding "
            f"at {binding_idx}, last payment/ledger write at "
            f"{last_payment_side})")
        assert binding_idx > first_hold, sequence
    finally:
        await session.rollback()
        await session.close()


async def test_e1f3_fault_at_binding_step_rolls_back_whole_settlement(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, monkeypatch
):
    """E1-F3: a fault at the (now final) binding write must roll the ENTIRE
    settlement back inside the one transaction — payment row, hold
    reduction, status transition and ledger posting all vanish."""
    from services import payment_service as ps_mod
    from services.canonical_payment_service import CanonicalPaymentService
    from tests.order_state_r1.support import rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="60.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    await db.rollback()

    before_balance = await binding_balance(db, ws_id, ret_id)
    before_holds = await fetch_holds(db, schema, oid)
    before_payments = await payment_count(db, schema, oid)
    assert before_balance == Decimal("60.00"), before_balance

    real_delta = ps_mod.PaymentService._apply_outstanding_balance_delta

    async def exploding_delta(self, tenant_db, *, wholesaler_id, retailer_id,
                              delta):
        raise RuntimeError("E1-F3 injected fault at the binding write")

    session = await _second_session(schema, ws_id)
    try:
        await rebind_search_path(session, schema)
        monkeypatch.setattr(ps_mod.PaymentService, "_apply_outstanding_balance_delta",
                            exploding_delta)
        with pytest.raises(RuntimeError, match="E1-F3 injected fault"):
            await CanonicalPaymentService().confirm_payment(
                db=session, order_id=oid, amount=Decimal("60.00"),
                method="cash", transaction_id=None,
                idempotency_key=f"e1f3f-{uuid.uuid4().hex}",
                created_by=str(cashier_identity["user_id"]))
    finally:
        monkeypatch.setattr(ps_mod.PaymentService,
                            "_apply_outstanding_balance_delta", real_delta)
        await session.rollback()
        await session.close()

    assert await payment_count(db, schema, oid) == before_payments, (
        "E1-F3: the payment row survived a failed settlement")
    holds = await fetch_holds(db, schema, oid)
    assert len(holds) == 1 and holds[0]["status"] == "active" \
        and holds[0]["remaining"] == "60.00", holds
    assert await binding_balance(db, ws_id, ret_id) == before_balance, (
        "E1-F3: the binding cache moved despite the settlement failing")
    status = (await db.execute(text(
        f'SELECT status::text FROM "{schema}".orders WHERE id = :o'),
        {"o": oid})).scalar()
    assert status == "confirmed", (
        f"E1-F3: the order left confirmed during a failed settlement "
        f"({status})")
