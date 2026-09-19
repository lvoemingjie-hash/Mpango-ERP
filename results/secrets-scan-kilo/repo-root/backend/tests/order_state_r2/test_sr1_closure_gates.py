"""SR1 closure gates — real production paths on real PG16.

CODEXL-SUPERVISOR-ORDER-STATE-R2-R1-SR1-CLOSURE-2026-09-18. Each test names
the supervisor SR1 finding it pins:

  SR1-F1 the route-level IntegrityError replay fallback is gone; the
         canonical service classifies ONLY the two payment unique
         constraints (idempotency / transaction); every unrelated
         IntegrityError propagates unchanged. A concurrent same-key race
         still yields exactly one economic effect.
  SR1-F2 the canonical service is split into a public entry (locks and
         refreshes the order) and a private locked-order write
         implementation; the declaration confirmation — order already
         locked — calls the private implementation, so the canonical
         service performs ZERO order FOR UPDATE acquisitions inside the
         declaration chain (no public bypass parameter reintroduced).
  SR1-F3 a confirmed-declaration replay binds every element: payment
         order_id, retailer, canonical decl-confirm idempotency key,
         amount, method, transaction reference, receipt and the
         declaration link. Any mismatch is 409 with zero writes.
  SR1-F4 one shared valid-payment-history contract (is_deleted=false,
         positive finite amount, allowed method/status, payment retailer
         == order retailer, order live and correctly owned) is enforced
         by the canonical write path AND both receivables read paths —
         unknown method/status and corrupt rows are named RED, never
         silently aggregated around; 039 preflight rejects Numeric
         NaN/Infinity/-Infinity.
  SR1-F5 the bootstrap hold-catalog gate compares the FULL SET of
         columns/constraints/indexes (PK and UNIQUE auto-indexes
         included); any extra object is RED.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.order_state_r2.support import (
    binding_balance,
    errcode,
    fetch_holds,
    http_action,
    http_create_order,
    make_bound_retailer,
    osd1_cashier_token,
    payment_count,
    receipt_numbers,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio

DECLARATION_KEY_CONFLICT = "DECLARATION_CONFIRMATION_KEY_CONFLICT"
HISTORY_INTEGRITY = "PAYMENT_HISTORY_INTEGRITY"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _FakePgIntegrity(RuntimeError):
    """Deterministic stand-in for an asyncpg IntegrityError origin: carries
    the sqlstate and constraint name the classifier must read."""

    def __init__(self, *, sqlstate: str, constraint_name: str | None):
        super().__init__(
            f'duplicate key value violates unique constraint "{constraint_name}"'
            if sqlstate == "23505"
            else f'integrity violation from "{constraint_name}"')
        self.sqlstate = sqlstate
        self.pgcode = sqlstate
        self.constraint_name = constraint_name


def _forced_integrity_error(*, sqlstate: str, constraint_name: str | None) -> IntegrityError:
    return IntegrityError(
        "INSERT INTO payments (...) VALUES (...)",
        {},
        _FakePgIntegrity(sqlstate=sqlstate, constraint_name=constraint_name),
    )


def _token_payload(ws_id: str, user_id: str):
    from types import SimpleNamespace

    return SimpleNamespace(tenant_id=str(ws_id), user_id=str(user_id),
                           tenant_schema=None)


async def _make_confirmed_order(r1_client, token, db, provisioned_pool, reg,
                                *, price="50.00", quantity=2, retailer=None):
    if retailer is None:
        ret_id, schema, ws_id = await make_bound_retailer(
            db, provisioned_pool, reg)
    else:
        ret_id, schema, ws_id = retailer
    sku, sid = await seed_sku_with_stock(db, schema, ret_id, price=price)
    oid = await http_create_order(
        r1_client, token, ret_id, [{"sku_code": sku, "quantity": quantity}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    return oid, ret_id, schema, ws_id


async def _submit_and_confirm_declaration(session, schema, oid, ret_id, ws_id,
                                          user_id, *, amount="100.00",
                                          method="cash", reference=None):
    from services.payment_declaration_service import PaymentDeclarationService
    from tests.order_state_r1.support import rebind_search_path

    svc = PaymentDeclarationService()
    await rebind_search_path(session, schema)
    record, _ = await svc.submit_declaration(
        db=session,
        order_id=oid,
        retailer_id=uuid.UUID(str(ret_id)),
        wholesaler_id=uuid.UUID(str(ws_id)),
        submitted_by=uuid.UUID(str(user_id)),
        declared_amount=Decimal(amount),
        method=method,
        transfer_reference=reference,
        idempotency_key=f"sr1-sub-{uuid.uuid4().hex}",
    )
    await session.commit()
    await rebind_search_path(session, schema)
    declaration, result = await svc.confirm_declaration(
        db=session,
        declaration_id=uuid.UUID(str(record["id"])),
        wholesaler_id=uuid.UUID(str(ws_id)),
        confirmed_by=uuid.UUID(str(user_id)),
    )
    await session.commit()
    return record["id"], result


async def _receipt_sequence_vector(db, schema) -> list[tuple[str, int]]:
    rows = (await db.execute(text(
        f'SELECT business_date, next_seq FROM "{schema}".receipt_sequences '
        "ORDER BY business_date"))).all()
    return [(str(r[0]), int(r[1])) for r in rows]


async def _schema_payment_count(db, schema) -> int:
    return int((await db.execute(text(
        f'SELECT COUNT(*) FROM "{schema}".payments'))).scalar_one())


METHOD_CHECK_DDL = "CHECK (method IN ('cash', 'transfer', 'credit'))"


async def _set_method_check(db, schema, *, present: bool) -> None:
    """The tenant payments table carries ck_payments_method_canonical; only
    a legacy row predating that contract can hold an unknown method, so the
    gate drops and restores the CHECK around the injection."""
    if present:
        await db.execute(text(
            f'ALTER TABLE "{schema}".payments ADD CONSTRAINT '
            f"ck_payments_method_canonical {METHOD_CHECK_DDL}"))
    else:
        await db.execute(text(
            f'ALTER TABLE "{schema}".payments DROP CONSTRAINT IF EXISTS '
            "ck_payments_method_canonical"))
    await db.commit()


# ---------------------------------------------------------------------------
# SR1-F1 — route fallback removed; canonical classifies precisely
# ---------------------------------------------------------------------------


async def test_sr1_f1_route_unrelated_integrity_error_never_becomes_replay(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """SR1-F1: an unrelated IntegrityError escaping the canonical service
    must propagate through the pay route UNCHANGED — even when a committed
    payment with the same idempotency key and payload exists. The deleted
    route-level fallback turned exactly this into a 200 'Payment replayed'.
    """
    from api.v1.orders import pay_order
    from schemas.order import PayOrderRequest
    from services.canonical_payment_service import CanonicalPaymentService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg)

    key = f"sr1f1-{uuid.uuid4().hex}"
    first = await r1_client.post(
        f"/api/v1/orders/{oid}/pay",
        json={"amount": 100.0, "method": "cash"},
        headers={"Authorization": f"Bearer {token}",
                 "X-Idempotency-Key": key})
    assert first.status_code == 200, first.text
    await db.rollback()
    pays_before = await payment_count(db, schema, oid)

    forced = _forced_integrity_error(
        sqlstate="23514", constraint_name="ck_payments_amount_positive")

    async def _explode(self, **kwargs):
        raise forced

    session = await _second_session(schema, ws_id)
    try:
        await rebind_search_path(session, schema)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(CanonicalPaymentService, "confirm_payment", _explode)
            try:
                response = await pay_order(
                    order_id=oid,
                    token=_token_payload(ws_id, cashier_identity["user_id"]),
                    db=session,
                    payment_input=PayOrderRequest(
                        amount=Decimal("100.00"), method="cash"),
                    x_idempotency_key=key,
                )
            except IntegrityError as exc:
                assert exc is forced, (
                    "SR1-F1: a DIFFERENT error surfaced — the unrelated "
                    "IntegrityError was not propagated as-is")
            else:
                raise AssertionError(
                    "SR1-F1: the route converted an unrelated IntegrityError "
                    f"into a successful response (replayed="
                    f"{getattr(response, 'message', None)!r}) — the "
                    "route-level replay fallback is still present")
        await session.rollback()
    finally:
        await session.rollback()
        await session.close()

    assert await payment_count(db, schema, oid) == pays_before, (
        "SR1-F1: the unrelated IntegrityError produced a payment write")


async def test_sr1_f1_canonical_classifies_only_the_two_unique_constraints(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """SR1-F1: inside the canonical service an INSERT race on EXACTLY
    uq_payments_idempotency_key is classified and replayed, a race on
    EXACTLY uq_payments_transaction_id is the named duplicate-reference
    409, and every other IntegrityError (unknown sqlstate, or a unique
    violation on any other constraint such as the receipt number) is
    re-raised unchanged."""
    from repositories.payment_repository import PaymentRepository
    from services.canonical_payment_service import CanonicalPaymentService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg)

    # Committed same-payload payment with key K (the race winner's row). A
    # PARTIAL cash settlement keeps the order payable so the simulated race
    # request is still admissible against the post-winner state.
    key = f"sr1f1c-{uuid.uuid4().hex}"
    first = await r1_client.post(
        f"/api/v1/orders/{oid}/pay",
        json={"amount": 40.0, "method": "cash"},
        headers={"Authorization": f"Bearer {token}",
                 "X-Idempotency-Key": key})
    assert first.status_code == 200, first.text
    winner_payment_id = first.json()["data"]["payment_id"]

    # A committed transfer row realising the transaction-reference race
    # target for case B.
    tx = "SR1F1-TX-RACE"
    transfer = await r1_client.post(
        f"/api/v1/orders/{oid}/pay",
        json={"amount": 20.0, "method": "transfer", "transaction_id": tx},
        headers={"Authorization": f"Bearer {token}",
                 "X-Idempotency-Key": f"sr1f1tx-{uuid.uuid4().hex}"})
    assert transfer.status_code == 200, transfer.text
    await db.rollback()
    pays_before = await payment_count(db, schema, oid)

    real_by_key = PaymentRepository.get_by_idempotency_key
    real_by_tx = PaymentRepository.get_by_transaction_id
    real_create = PaymentRepository.create

    def _miss_then_real(real, miss_calls):
        state = {"calls": 0}

        async def _wrapped(self, db, **kwargs):
            state["calls"] += 1
            if state["calls"] <= miss_calls:
                return None
            return await real(self, db, **kwargs)

        return _wrapped, state

    def _raise_once(error):
        state = {"calls": 0}

        async def _create(self, db, **kwargs):
            state["calls"] += 1
            if state["calls"] == 1:
                raise error
            return await real_create(self, db, **kwargs)

        return _create, state

    # -- case A: idempotency-key race is classified and replayed ----------
    # Both tenant-schema construction paths name this unique object
    # differently (the alembic unique INDEX vs the bootstrap inline UNIQUE
    # constraint), so both names must classify.
    for idempotency_object in ("payments_idempotency_key_key",
                               "uq_payments_idempotency_key"):
        session = await _second_session(schema, ws_id)
        try:
            await rebind_search_path(session, schema)
            with pytest.MonkeyPatch.context() as mp:
                by_key, _s1 = _miss_then_real(real_by_key, miss_calls=2)
                create, create_state = _raise_once(_forced_integrity_error(
                    sqlstate="23505",
                    constraint_name=idempotency_object))
                mp.setattr(PaymentRepository, "get_by_idempotency_key", by_key)
                mp.setattr(PaymentRepository, "create", create)
                try:
                    result = await CanonicalPaymentService().confirm_payment(
                        db=session,
                        order_id=oid,
                        amount=Decimal("40.00"),
                        method="cash",
                        transaction_id=None,
                        idempotency_key=key,
                        created_by=str(cashier_identity["user_id"]),
                    )
                except IntegrityError as exc:
                    raise AssertionError(
                        "SR1-F1: the idempotency unique-constraint race "
                        f"({idempotency_object}) was NOT classified inside "
                        "the canonical service — the raw IntegrityError "
                        f"escaped ({exc!r})") from exc
                assert result.replayed is True, (
                    "SR1-F1: the classified race did not return a replay")
                assert str(result.payment_record["id"]) == winner_payment_id, (
                    "SR1-F1: the replay returned a different payment")
                assert create_state["calls"] == 1, (
                    "SR1-F1: the INSERT was retried after classification")
            await session.rollback()
        finally:
            await session.rollback()
            await session.close()

    # -- case B: transaction-id race is the named duplicate-reference 409 --
    session = await _second_session(schema, ws_id)
    try:
        await rebind_search_path(session, schema)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(PaymentRepository, "get_by_idempotency_key",
                       _miss_then_real(real_by_key, miss_calls=10**9)[0])
            by_tx, _s2 = _miss_then_real(real_by_tx, miss_calls=1)
            mp.setattr(PaymentRepository, "get_by_transaction_id", by_tx)
            create, _s3 = _raise_once(_forced_integrity_error(
                sqlstate="23505",
                constraint_name="uq_payments_transaction_id"))
            mp.setattr(PaymentRepository, "create", create)
            from fastapi import HTTPException as _HttpExc
            try:
                await CanonicalPaymentService().confirm_payment(
                    db=session,
                    order_id=oid,
                    amount=Decimal("20.00"),
                    method="transfer",
                    transaction_id=tx,
                    idempotency_key=f"sr1f1b-{uuid.uuid4().hex}",
                    created_by=str(cashier_identity["user_id"]),
                )
            except _HttpExc as exc:
                assert exc.status_code == 409 and \
                    exc.detail.get("code") == "DUPLICATE_TRANSFER_REFERENCE", (
                        "SR1-F1: the transaction unique-constraint race was "
                        f"not the named duplicate-reference refusal "
                        f"(got {exc.status_code}: {exc.detail})")
            except IntegrityError as exc:
                raise AssertionError(
                    "SR1-F1: the transaction unique-constraint race escaped "
                    f"as a raw IntegrityError ({exc!r})") from exc
            else:
                raise AssertionError(
                    "SR1-F1: the transaction unique-constraint race was "
                    "accepted as a new payment")
        await session.rollback()
    finally:
        await session.rollback()
        await session.close()

    # -- case C/D: anything else propagates unchanged ----------------------
    for label, error in (
        ("check-violation", _forced_integrity_error(
            sqlstate="23514", constraint_name="ck_payments_amount_positive")),
        ("unknown-unique", _forced_integrity_error(
            sqlstate="23505", constraint_name="payments_pkey")),
    ):
        session = await _second_session(schema, ws_id)
        try:
            await rebind_search_path(session, schema)
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(PaymentRepository, "get_by_idempotency_key",
                           _miss_then_real(real_by_key, miss_calls=10**9)[0])
                create, _s = _raise_once(error)
                mp.setattr(PaymentRepository, "create", create)
                try:
                    await CanonicalPaymentService().confirm_payment(
                        db=session,
                        order_id=oid,
                        amount=Decimal("20.00"),
                        method="cash",
                        transaction_id=None,
                        idempotency_key=f"sr1f1{label}-{uuid.uuid4().hex}",
                        created_by=str(cashier_identity["user_id"]),
                    )
                except IntegrityError as exc:
                    assert exc is error, (
                        f"SR1-F1: the {label} IntegrityError was replaced "
                        "or wrapped instead of propagated as-is")
                else:
                    raise AssertionError(
                        f"SR1-F1: the {label} IntegrityError was swallowed "
                        "into a replay/refusal — only the two payment "
                        "unique constraints may be classified")
            await session.rollback()
        finally:
            await session.rollback()
            await session.close()

    assert await payment_count(db, schema, oid) == pays_before, (
        "SR1-F1: classification probes produced extra payment rows")


async def test_sr1_f1_concurrent_same_key_same_order_single_economic_effect(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """SR1-F1: two real sessions submit the same key and payload for the
    SAME order through the canonical service. Same-order entrants are
    serialised by the order lock, so the loser replays through the
    post-lock idempotency re-check — exactly one payment and one economic
    effect, never a raw IntegrityError."""
    from services.canonical_payment_service import CanonicalPaymentService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg)
    await db.rollback()

    key = f"sr1f1same-{uuid.uuid4().hex}"

    async def _entrant():
        session = await _second_session(schema, ws_id)
        try:
            await rebind_search_path(session, schema)
            result = await CanonicalPaymentService().confirm_payment(
                db=session,
                order_id=oid,
                amount=Decimal("100.00"),
                method="cash",
                transaction_id=None,
                idempotency_key=key,
                created_by=str(cashier_identity["user_id"]),
            )
            await session.commit()
            return ("ok", result)
        except Exception as exc:  # noqa: BLE001 - surfaced by assertions
            await session.rollback()
            return ("err", exc)
        finally:
            await session.close()

    first, second = await asyncio.gather(_entrant(), _entrant())
    for status_tag, payload in (first, second):
        if status_tag != "ok":
            raise AssertionError(
                "SR1-F1: the same-order same-key race loser surfaced a raw "
                f"error instead of a replay: {payload!r}")
    outcomes = [first[1], second[1]]
    replayed_count = sum(1 for r in outcomes if r.replayed)
    assert replayed_count == 1, (
        f"SR1-F1: expected exactly one replay in the same-order race, got "
        f"{replayed_count}")
    assert len({str(r.payment_record["id"]) for r in outcomes}) == 1, (
        "SR1-F1: the same-order race produced two payment identities")

    await db.rollback()
    assert await payment_count(db, schema, oid) == 1, (
        "SR1-F1: the same-key race wrote more than one payment")
    holds = await fetch_holds(db, schema, oid)
    assert len(holds) == 1 and holds[0]["status"] == "settled" \
        and holds[0]["remaining"] == "0.00", (
            f"SR1-F1: race left a non-single economic effect on the hold: "
            f"{holds}")
    assert await binding_balance(db, ws_id, ret_id) == Decimal("0.00"), (
        "SR1-F1: race left the binding cache non-zero (double effect)")


async def test_sr1_f1_concurrent_cross_order_same_key_conflict_classified(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """SR1-F1 / SR1-R1 cross-order race oracle: two DIFFERENT orders under
    the SAME retailer (so no shared order lock, and the retailer check
    cannot mask the order binding) race the same idempotency key and
    payload; an event barrier holds both entrants at the payment INSERT so
    the loser truly hits uq_payments_idempotency_key. Required outcome —
    EXACTLY ONE success, EXACTLY ONE named 409 IDEMPOTENCY_KEY_CONFLICT,
    a replayed loser is always RED, and the loser's order keeps its hold
    and status EXACTLY as at confirm with zero payment rows (the shared
    binding shows only the winner's own settlement)."""
    from repositories.payment_repository import PaymentRepository
    from services.canonical_payment_service import CanonicalPaymentService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    orders = []
    ret_id = schema = ws_id = None
    for _ in range(2):
        # SAME retailer, DIFFERENT orders: no shared order lock, and the
        # retailer check cannot mask the ORDER-ID binding under replay.
        oid, ret_id, schema, ws_id = await _make_confirmed_order(
            r1_client, token, db, provisioned_pool, reg,
            retailer=(ret_id, schema, ws_id) if orders else None)
        orders.append(oid)
    await db.rollback()

    barrier = asyncio.Barrier(2)
    real_create = PaymentRepository.create

    async def gated_create(self, db, **kwargs):
        await asyncio.wait_for(barrier.wait(), timeout=60)
        return await real_create(self, db, **kwargs)

    key = f"sr1f1cross-{uuid.uuid4().hex}"

    async def _entrant(order_id: str):
        session = await _second_session(schema, ws_id)
        try:
            await rebind_search_path(session, schema)
            result = await CanonicalPaymentService().confirm_payment(
                db=session,
                order_id=order_id,
                amount=Decimal("100.00"),
                method="cash",
                transaction_id=None,
                idempotency_key=key,
                created_by=str(cashier_identity["user_id"]),
            )
            await session.commit()
            return ("ok", result)
        except Exception as exc:  # noqa: BLE001 - surfaced by assertions
            await session.rollback()
            return ("err", exc)
        finally:
            await session.close()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PaymentRepository, "create", gated_create)
        outcomes = await asyncio.gather(_entrant(orders[0]),
                                        _entrant(orders[1]))

    from fastapi import HTTPException as _HttpExc

    def _is_named_conflict(payload) -> bool:
        return isinstance(payload, _HttpExc) and payload.status_code == 409 \
            and payload.detail.get("code") == "IDEMPOTENCY_KEY_CONFLICT"

    failures = [
        payload for tag, payload in outcomes
        if tag != "ok" and not _is_named_conflict(payload)
    ]
    assert not failures, (
        "SR1-F1: the cross-order same-key race loser surfaced a raw error "
        f"instead of a classified refusal: {failures!r}")

    winners = [r for tag, r in outcomes if tag == "ok" and not r.replayed]
    assert len(winners) == 1, (
        f"SR1-F1: expected exactly one winning payment, got {len(winners)}")

    await db.rollback()
    total = int((await db.execute(text(
        f'SELECT COUNT(*) FROM "{schema}".payments '
        "WHERE idempotency_key = :k"), {"k": key})).scalar_one())
    assert total == 1, (
        f"SR1-F1: the cross-order same-key race wrote {total} payments "
        "with the raced key")

    # a replayed loser is ALWAYS RED, and the winner order identity decides
    # which order must show zero economic effect
    successes = [r for tag, r in outcomes if tag == "ok"]
    replayed = [r for r in successes if r.replayed]
    assert len(successes) == 1 and not replayed, (
        "SR1-F1: the cross-order same-key race must yield EXACTLY ONE "
        f"success and NEVER a replayed loser (successes={len(successes)}, "
        f"replayed={len(replayed)})")
    conflicts = [payload for tag, payload in outcomes
                 if tag != "ok" and _is_named_conflict(payload)]
    assert len(conflicts) == 1, (
        "SR1-F1: expected EXACTLY ONE named 409 IDEMPOTENCY_KEY_CONFLICT "
        f"loser, got {len(conflicts)}")

    winner_order = str(successes[0].order.id)
    loser_order = next(o for o in orders if o != winner_order)
    meta = {"schema": schema, "ws_id": ws_id, "ret_id": ret_id}

    await db.rollback()
    total = int((await db.execute(text(
        f'SELECT COUNT(*) FROM "{schema}".payments '
        "WHERE idempotency_key = :k"), {"k": key})).scalar_one())
    assert total == 1, (
        f"SR1-F1: the cross-order same-key race wrote {total} payments "
        "with the raced key")
    loser_pays = await payment_count(db, meta["schema"], loser_order)
    assert loser_pays == 0, (
        "SR1-F1: the loser order carried "
        f"{loser_pays} payment row(s) — the cross-order binding failed")

    holds = await fetch_holds(db, meta["schema"], loser_order)
    assert len(holds) == 1 and holds[0]["status"] == "active" \
        and holds[0]["remaining"] == "100.00", (
            "SR1-F1: the loser order's hold moved — the race had an "
            f"economic effect on it: {holds}")
    loser_binding = await binding_balance(db, meta["ws_id"], meta["ret_id"])
    # two confirms reserved 200.00 on the shared binding; the winner's own
    # settlement releases exactly its 100.00 — what remains is the loser's
    # own untouched reservation and nothing from the race loser.
    assert loser_binding == Decimal("100.00"), (
        "SR1-F1: the shared binding must show ONLY the loser's untouched "
        f"reservation (200.00 reserved − 100.00 winner settlement) — got "
        f"{loser_binding}")
    loser_status = (await db.execute(text(
        f'SELECT status::text FROM "{meta["schema"]}".orders '
        "WHERE id = :o"), {"o": loser_order})).scalar()
    assert loser_status == "confirmed", (
        "SR1-F1: the loser order's status moved to "
        f"{loser_status!r} — the race transitioned it")


# ---------------------------------------------------------------------------
# SR1-F2 — canonical split; no second order lock in the declaration chain
# ---------------------------------------------------------------------------


async def test_sr1_f2_exact_order_lock_counts_declaration_and_public_pay(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """SR1-F2 / SR1-R1 final lock seam: the REAL SQL oracle counts every
    ``FROM orders ... FOR UPDATE`` statement issued in the window and the
    total must be EXACTLY ONE for each whole payment chain — the
    declaration confirmation (the declaration service's own lock; the
    canonical service and the command service reuse it) and the canonical
    public payment entry (its own lock). A method-level spy is never the
    authority here."""
    from services.canonical_payment_service import CanonicalPaymentService
    from services.payment_declaration_service import PaymentDeclarationService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg)
    oid_pay, ret_pay, schema_pay, ws_pay = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg,
        retailer=(ret_id, schema, ws_id))
    await db.rollback()

    session = await _second_session(schema, ws_id)
    engine = session.get_bind()
    counted = {"n": 0}

    def _count_order_locks(conn, cursor, statement, parameters,
                           context, executemany):
        if re.search(r"\bFROM orders\b", statement) and "FOR UPDATE" in statement:
            counted["n"] += 1

    from sqlalchemy import event as _sa_event

    try:
        await rebind_search_path(session, schema)
        record, _ = await PaymentDeclarationService().submit_declaration(
            db=session,
            order_id=oid,
            retailer_id=uuid.UUID(ret_id),
            wholesaler_id=uuid.UUID(ws_id),
            submitted_by=uuid.UUID(str(cashier_identity["user_id"])),
            declared_amount=Decimal("100.00"),
            method="cash",
            transfer_reference=None,
            idempotency_key=f"sr1f2-{uuid.uuid4().hex}",
        )
        await session.commit()

        # -- chain 1: declaration confirmation — exactly ONE order lock ----
        await rebind_search_path(session, schema)
        counted["n"] = 0
        _sa_event.listen(engine, "before_cursor_execute", _count_order_locks)
        try:
            declaration, result = await PaymentDeclarationService(
            ).confirm_declaration(
                db=session,
                declaration_id=uuid.UUID(str(record["id"])),
                wholesaler_id=uuid.UUID(ws_id),
                confirmed_by=uuid.UUID(str(cashier_identity["user_id"])),
            )
        finally:
            _sa_event.remove(engine, "before_cursor_execute",
                             _count_order_locks)
        await session.commit()

        assert counted["n"] == 1, (
            "SR1-F2: the declaration confirmation chain issued "
            f"{counted['n']} order FOR UPDATE statements (expected "
            "EXACTLY 1 — the declaration service's own lock; canonical "
            "and the command service must reuse the locked order)")
        assert declaration["status"] == "confirmed", declaration
        assert result.replayed is False
        assert str(result.order_state) == "paid", result.order_state

        # -- chain 2: canonical public payment — exactly ONE order lock ----
        pay_session = await _second_session(schema_pay, ws_pay)
        try:
            await rebind_search_path(pay_session, schema_pay)
            counted["n"] = 0
            _sa_event.listen(engine, "before_cursor_execute",
                             _count_order_locks)
            try:
                pay_result = await CanonicalPaymentService().confirm_payment(
                    db=pay_session,
                    order_id=oid_pay,
                    amount=Decimal("100.00"),
                    method="cash",
                    transaction_id=None,
                    idempotency_key=f"sr1f2pub-{uuid.uuid4().hex}",
                    created_by=str(cashier_identity["user_id"]),
                )
            finally:
                _sa_event.remove(engine, "before_cursor_execute",
                                 _count_order_locks)
            await pay_session.commit()

            assert counted["n"] == 1, (
                "SR1-F2: the canonical public payment chain issued "
                f"{counted['n']} order FOR UPDATE statements (expected "
                "EXACTLY 1 — the public entry's own lock)")
            assert pay_result.replayed is False
            assert str(pay_result.order_state) == "paid", pay_result.order_state
        finally:
            await pay_session.rollback()
            await pay_session.close()
    finally:
        await session.rollback()
        await session.close()

    await db.rollback()
    assert await payment_count(db, schema, oid) == 1
    receipts = await receipt_numbers(db, schema, oid)
    assert len(receipts) == 1 and receipts[0].startswith("RCT-"), receipts


# ---------------------------------------------------------------------------
# SR1-F3 — confirmed-declaration replay binds every element
# ---------------------------------------------------------------------------


async def test_sr1_f3_confirmed_declaration_replay_binds_every_element(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """SR1-F3: replaying an already-confirmed declaration must re-bind the
    linked payment on order_id, retailer, canonical decl-confirm key,
    amount, method, transaction reference, receipt and the declaration
    link. Each tampered element is a named 409 with zero writes; the
    untampered control replays cleanly."""
    from fastapi import HTTPException as _HttpExc
    from services.payment_declaration_service import PaymentDeclarationService
    from tests.order_state_r1.support import _second_session, rebind_search_path
    from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (
        _create_retailer,
    )

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)

    scenarios = [
        ("retailer_id", "cash", None),
        ("idempotency_key", "cash", None),
        ("amount", "cash", None),
        ("method", "cash", None),
        ("transaction_id", "transfer", "SR1F3-REF-1"),
        ("receipt_number", "cash", None),
        ("order_id", "cash", None),
        (None, "cash", None),
    ]

    red_failures: list[str] = []

    for tamper, method, reference in scenarios:
        oid, ret_id, schema, ws_id = await _make_confirmed_order(
            r1_client, token, db, provisioned_pool, reg)
        await db.rollback()

        session = await _second_session(schema, ws_id)
        try:
            decl_id, result = await _submit_and_confirm_declaration(
                session, schema, oid, ret_id, ws_id,
                cashier_identity["user_id"],
                amount="100.00", method=method, reference=reference)
            payment_id = str(result.payment_record["id"])

            other_retailer = None
            other_order = None
            if tamper == "retailer_id":
                other_retailer = await _create_retailer(
                    db, name="SR1F3 Other Retailer", registry=reg)
            if tamper == "order_id":
                oid2, _r2, _s2, _w2 = await _make_confirmed_order(
                    r1_client, token, db, provisioned_pool, reg,
                    retailer=(ret_id, schema, ws_id))
                other_order = oid2
            await db.rollback()

            pays_before = await _schema_payment_count(db, schema)
            receipts_before = await _receipt_sequence_vector(db, schema)

            original_value = None
            if tamper is not None:
                original_value = (await db.execute(text(
                    f'SELECT {tamper} FROM "{schema}".payments WHERE id = :pid'),
                    {"pid": payment_id})).scalar()
                set_clause, params = {
                    "retailer_id": ("retailer_id = :v",
                                    {"v": str(other_retailer)}),
                    "idempotency_key": ("idempotency_key = :v",
                                        {"v": f"decl-confirm-{uuid.uuid4().hex}"}),
                    "amount": ("amount = amount + 1", {}),
                    "method": ("method = 'transfer'", {}),
                    "transaction_id": ("transaction_id = :v",
                                       {"v": "SR1F3-REF-TAMPERED"}),
                    "receipt_number": ("receipt_number = NULL", {}),
                    "order_id": ("order_id = :v", {"v": other_order}),
                }[tamper]
                params["pid"] = payment_id
                await db.execute(text(
                    f'UPDATE "{schema}".payments SET {set_clause} '
                    "WHERE id = :pid"), params)
                await db.commit()
                await db.rollback()

            await rebind_search_path(session, schema)
            try:
                declaration, replay = await PaymentDeclarationService(
                ).confirm_declaration(
                    db=session,
                    declaration_id=uuid.UUID(str(decl_id)),
                    wholesaler_id=uuid.UUID(ws_id),
                    confirmed_by=uuid.UUID(str(cashier_identity["user_id"])),
                )
            except _HttpExc as exc:
                if tamper is None:
                    raise AssertionError(
                        "SR1-F3: the untampered control replay was refused "
                        f"({exc.status_code}: {exc.detail})")
                assert exc.status_code == 409 and \
                    exc.detail.get("code") == DECLARATION_KEY_CONFLICT, (
                        f"SR1-F3[{tamper}]: the refusal was not the named "
                        f"409 binding conflict (got {exc.status_code}: "
                        f"{exc.detail})")
            else:
                if tamper is not None:
                    red_failures.append(tamper)
                    await session.rollback()
                    continue
                assert replay.replayed is True
                assert str(replay.payment_record["id"]) == payment_id, (
                    "SR1-F3: the control replay returned a different "
                    "payment")
            await session.rollback()

            assert await _schema_payment_count(db, schema) == pays_before, (
                f"SR1-F3[{tamper}]: the replay wrote payment rows")
            assert await _receipt_sequence_vector(db, schema) == \
                receipts_before, (
                    f"SR1-F3[{tamper}]: the replay allocated a receipt")
            link = (await db.execute(text(
                f'SELECT status, confirmation_payment_id '
                f'FROM "{schema}".payment_declarations WHERE id = :d'),
                {"d": str(decl_id)})).first()
            assert link is not None and link[0] == "confirmed" and \
                str(link[1]) == payment_id, (
                    f"SR1-F3[{tamper}]: the declaration link drifted: {link}")
            if tamper is not None:
                # Restore the tampered column: the module's later gates read
                # the same tenant schema, and an unrestored tamper would be
                # real corrupt history for them (which is exactly what the
                # shared contract then refuses).
                await db.rollback()
                await db.execute(text(
                    f'UPDATE "{schema}".payments SET {tamper} = :v '
                    "WHERE id = :pid"), {"v": original_value, "pid": payment_id})
                await db.commit()
        finally:
            await session.rollback()
            await session.close()

    assert not red_failures, (
        "SR1-F3: confirmed-declaration replay accepted tampered binding "
        f"element(s) {red_failures} — the replay does not bind "
        "order/retailer/key/amount/method/reference/receipt/link")


# ---------------------------------------------------------------------------
# SR1-F4 — shared valid-payment-history contract on all three paths
# ---------------------------------------------------------------------------


async def _inject_payment(db, schema, oid, ret_id, **overrides) -> str:
    values = {
        "amount": "10.00", "method": "cash", "status": "completed",
        "is_deleted": "FALSE", "retailer_id": f"'{ret_id}'",
    }
    values.update(overrides)
    row = (await db.execute(text(
        f'INSERT INTO "{schema}".payments '
        "(order_id, retailer_id, amount, method, status, is_deleted) "
        f"VALUES (:o, {values['retailer_id']}, {values['amount']}, "
        f"'{values['method']}', '{values['status']}', {values['is_deleted']}) "
        "RETURNING id"),
        {"o": oid})).first()
    await db.commit()
    return str(row[0])


async def _assert_history_refusal_on_all_paths(
    db, schema, ws_id, oid, ret_id, cashier_user_id, *, label,
):
    from fastapi import HTTPException as _HttpExc
    from services.canonical_payment_service import CanonicalPaymentService
    from services.receivables_service import ReceivablesService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    missed: list[str] = []

    session = await _second_session(schema, ws_id)
    try:
        await rebind_search_path(session, schema)
        try:
            await CanonicalPaymentService().confirm_payment(
                db=session,
                order_id=oid,
                amount=Decimal("60.00"),
                method="cash",
                transaction_id=None,
                idempotency_key=f"sr1f4-{label}-{uuid.uuid4().hex}",
                created_by=str(cashier_user_id),
            )
        except _HttpExc as exc:
            assert exc.status_code == 409 and \
                exc.detail.get("code") == HISTORY_INTEGRITY, (
                    f"SR1-F4[{label}] canonical: refusal was not the named "
                    f"history integrity 409 (got {exc.status_code}: "
                    f"{exc.detail})")
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                f"SR1-F4[{label}] canonical: corrupt history surfaced as "
                f"{type(exc).__name__} instead of the named 409: {exc!r}")
        else:
            missed.append("canonical")
    finally:
        await session.rollback()
        await session.close()

    for path_name, call in (
        ("receivables.summary",
         lambda s: ReceivablesService().get_receivables_summary(
             tenant_db=s, wholesaler_id=ws_id)),
        ("receivables.list",
         lambda s: ReceivablesService().list_receivable_orders(
             tenant_db=s, wholesaler_id=ws_id)),
    ):
        reader = await _second_session(schema, ws_id)
        try:
            await rebind_search_path(reader, schema)
            try:
                await call(reader)
            except _HttpExc as exc:
                assert exc.status_code == 409 and \
                    exc.detail.get("code") == HISTORY_INTEGRITY, (
                        f"SR1-F4[{label}] {path_name}: refusal was not the "
                        f"named history integrity 409 (got "
                        f"{exc.status_code}: {exc.detail})")
            except Exception as exc:  # noqa: BLE001
                raise AssertionError(
                    f"SR1-F4[{label}] {path_name}: corrupt history "
                    f"surfaced as {type(exc).__name__} instead of the "
                    f"named 409: {exc!r}")
            else:
                missed.append(path_name)
        finally:
            await reader.rollback()
            await reader.close()

    assert not missed, (
        f"SR1-F4[{label}]: corrupt payment history was silently accepted "
        f"by {missed} — the shared valid-history contract is not "
        "enforced on every path")


async def test_sr1_f4_unknown_method_named_red_all_paths(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg)
    await _set_method_check(db, schema, present=False)
    try:
        pid = await _inject_payment(db, schema, oid, ret_id, method="crypto")
        await _assert_history_refusal_on_all_paths(
            db, schema, ws_id, oid, ret_id, cashier_identity["user_id"],
            label="unknown-method")
    finally:
        await db.rollback()
        await db.execute(text(
            f'DELETE FROM "{schema}".payments WHERE method = :m '
            "AND order_id = :o"), {"m": "crypto", "o": oid})
        await db.commit()
        await _set_method_check(db, schema, present=True)


async def test_sr1_f4_unknown_status_named_red_all_paths(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg)
    pid = await _inject_payment(db, schema, oid, ret_id, status="refunded")
    try:
        await _assert_history_refusal_on_all_paths(
            db, schema, ws_id, oid, ret_id, cashier_identity["user_id"],
            label="unknown-status")
    finally:
        await db.execute(text(
            f'DELETE FROM "{schema}".payments WHERE id = :p'), {"p": pid})
        await db.commit()


async def test_sr1_f4_non_positive_amount_named_red_all_paths(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg)
    pid = await _inject_payment(db, schema, oid, ret_id, amount="0.00")
    try:
        await _assert_history_refusal_on_all_paths(
            db, schema, ws_id, oid, ret_id, cashier_identity["user_id"],
            label="non-positive")
    finally:
        await db.execute(text(
            f'DELETE FROM "{schema}".payments WHERE id = :p'), {"p": pid})
        await db.commit()


async def test_sr1_f4_non_finite_amount_named_red_all_paths(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg)
    pid = await _inject_payment(
        db, schema, oid, ret_id, amount="'NaN'::numeric")
    try:
        await _assert_history_refusal_on_all_paths(
            db, schema, ws_id, oid, ret_id, cashier_identity["user_id"],
            label="non-finite")
    finally:
        await db.execute(text(
            f'DELETE FROM "{schema}".payments WHERE id = :p'), {"p": pid})
        await db.commit()


async def test_sr1_f4_retailer_mismatch_named_red_all_paths(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (
        _create_retailer,
    )

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg)
    other = await _create_retailer(db, name="SR1F4 Other", registry=reg)
    pid = await _inject_payment(
        db, schema, oid, ret_id, retailer_id=f"'{other}'")
    try:
        await _assert_history_refusal_on_all_paths(
            db, schema, ws_id, oid, ret_id, cashier_identity["user_id"],
            label="retailer-mismatch")
    finally:
        await db.execute(text(
            f'DELETE FROM "{schema}".payments WHERE id = :p'), {"p": pid})
        await db.commit()


async def test_sr1_f4_soft_deleted_invalid_row_is_not_history(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """Control: the same corrupt shapes with is_deleted=TRUE are NOT
    history — payment proceeds and both reads compute (the contract only
    governs live rows)."""
    from services.receivables_service import ReceivablesService
    from tests.order_state_r1.support import _second_session, rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    oid, ret_id, schema, ws_id = await _make_confirmed_order(
        r1_client, token, db, provisioned_pool, reg)
    await _set_method_check(db, schema, present=False)
    try:
        await _inject_payment(
            db, schema, oid, ret_id, method="crypto", status="refunded",
            amount="'NaN'::numeric", is_deleted="TRUE")
        pay = await http_action(r1_client, token, oid, "pay",
                                {"amount": 60.0, "method": "cash"})
        assert pay.status_code == 200, (
            f"SR1-F4 control: soft-deleted non-history blocked payment "
            f"({pay.status_code}): {pay.text}")
        reader = await _second_session(schema, ws_id)
        try:
            await rebind_search_path(reader, schema)
            summary = await ReceivablesService().get_receivables_summary(
                tenant_db=reader, wholesaler_id=ws_id)
            assert isinstance(summary, dict)
            listing = await ReceivablesService().list_receivable_orders(
                tenant_db=reader, wholesaler_id=ws_id)
            assert isinstance(listing, dict)
        finally:
            await reader.rollback()
            await reader.close()
    finally:
        await db.rollback()
        await db.execute(text(
            f'DELETE FROM "{schema}".payments WHERE method = :m '
            "AND order_id = :o"), {"m": "crypto", "o": oid})
        await db.commit()
        await _set_method_check(db, schema, present=True)


def test_sr1_f4_039_preflight_rejects_non_finite_amounts():
    """SR1-F4 (migration, real alembic on a disposable PG16 database):
    Numeric NaN, Infinity AND -Infinity in effective payment history are
    each refused by the 039 preflight with the named invalid-history
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
        _engine,
        _register_tenant,
    )

    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "r2sr1f4") as db_url:
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

        ws = uuid.uuid4()
        schema = _register_tenant(engine, ws)
        retailer = uuid.uuid4()
        _add_order(engine, schema, ws, retailer, "confirmed", "50.00")
        _add_binding(engine, ws, retailer, "0.00")

        # The tenant column is numeric(12,2), which cannot STORE an infinite
        # value at all; the disposable pre-039 database therefore relaxes
        # the precision so a storable Infinity/-Infinity row can exist and
        # the preflight predicate is exercised for all three literals.
        with engine.begin() as conn:
            conn.execute(text(
                f'ALTER TABLE "{schema}".payments '
                "ALTER COLUMN amount TYPE numeric"))

        spec = importlib.util.spec_from_file_location(
            "m039_sr1f4", "alembic/versions/039_order_credit_holds.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        for bad in ("NaN", "Infinity", "-Infinity"):
            with engine.begin() as conn:
                conn.execute(text(
                    f'INSERT INTO "{schema}".payments '
                    "(order_id, retailer_id, amount, method, status, "
                    "is_deleted) SELECT id, :r, CAST(:bad AS numeric), "
                    f"'cash', 'completed', FALSE FROM \"{schema}\".orders"),
                    {"r": retailer, "bad": bad})
            try:
                with engine.begin() as conn:
                    module.op = Operations(MigrationContext.configure(conn))
                    module.upgrade()
            except Exception as exc:
                assert "invalid effective payment" in str(exc), (
                    f"SR1-F4[039 {bad}]: refusal lacks the named "
                    f"invalid-history message: {exc}")
            else:
                raise AssertionError(
                    f"SR1-F4[039 {bad}]: a {bad} payment amount was "
                    "accepted by the 039 preflight")
            version = engine.connect().execute(text(
                "SELECT version_num FROM public.alembic_version")).scalar()
            assert version == "038_catalog_identity_vertical_slice", (
                f"SR1-F4[039 {bad}]: the failed preflight still wrote")
            with engine.begin() as conn:
                conn.execute(text(
                    f'DELETE FROM "{schema}".payments'))


# ---------------------------------------------------------------------------
# SR1-F5 — bootstrap hold-catalog full-set gate
# ---------------------------------------------------------------------------


async def _load_bts():
    import importlib.util
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "bts_sr1f5", backend / "scripts" / "bootstrap_tenant_schema.py")
    bts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bts)
    return bts


async def _sr1_f5_conforming_control(db, bts) -> None:
    """SR1-F5 GREEN control on a CONFORMING tenant. Runs on a dedicated
    fresh schema: the shared fixture schema intentionally carries other
    gates' corruption fixtures (e.g. soft-deleted bindings with live
    exposure), which the strengthened schema-wide reconcile must keep
    refusing — only an isolated conforming tenant proves the GREEN
    side."""
    import os as _os
    import uuid as _uuid

    control_schema = f"t_sr1f5ctl_{_uuid.uuid4().hex[:10]}"
    await bts.bootstrap(
        control_schema,
        _os.environ["DATABASE_URL"].replace(
            "postgresql://", "postgresql+asyncpg://", 1))
    try:
        await bts._reconcile_credit_holds(db, control_schema)
    finally:
        await db.rollback()
        await db.execute(text(
            f'DROP SCHEMA IF EXISTS "{control_schema}" CASCADE'))
        await db.commit()


async def test_sr1_f5_extra_constraint_on_hold_table_rejected(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """SR1-F5: an EXTRA constraint on order_credit_holds (present in the
    catalog, absent from the frozen contract) must turn the bootstrap
    reconcile RED, naming the extra object."""
    bts = await _load_bts()
    db, reg = s2_clean_db
    _token = await osd1_cashier_token(r1_client, cashier_identity)
    _ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    await db.rollback()

    await db.execute(text(
        f'ALTER TABLE "{schema}".order_credit_holds '
        "ADD CONSTRAINT ck_sr1_f5_extra CHECK (amount > -1)"))
    await db.commit()
    try:
        with pytest.raises(RuntimeError) as excinfo:
            await bts._reconcile_credit_holds(db, schema)
        assert "ck_sr1_f5_extra" in str(excinfo.value), (
            "SR1-F5: the extra constraint was not named by the set gate: "
            f"{excinfo.value}")
    finally:
        await db.rollback()
        await db.execute(text(
            f'ALTER TABLE "{schema}".order_credit_holds '
            "DROP CONSTRAINT IF EXISTS ck_sr1_f5_extra"))
        await db.commit()

    await _sr1_f5_conforming_control(db, bts)
    await db.rollback()


async def test_sr1_f5_extra_index_on_hold_table_rejected(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """SR1-F5: an EXTRA index on order_credit_holds must turn the
    bootstrap reconcile RED, naming the extra object (the expected set
    explicitly includes the PK and UNIQUE auto-indexes — a conforming
    table stays GREEN, proven by the control)."""
    bts = await _load_bts()
    db, reg = s2_clean_db
    _token = await osd1_cashier_token(r1_client, cashier_identity)
    _ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    await db.rollback()

    await db.execute(text(
        f'CREATE INDEX ix_sr1_f5_extra ON "{schema}".order_credit_holds '
        "(status)"))
    await db.commit()
    try:
        with pytest.raises(RuntimeError) as excinfo:
            await bts._reconcile_credit_holds(db, schema)
        assert "ix_sr1_f5_extra" in str(excinfo.value), (
            "SR1-F5: the extra index was not named by the set gate: "
            f"{excinfo.value}")
    finally:
        await db.rollback()
        await db.execute(text(
            f'DROP INDEX IF EXISTS "{schema}".ix_sr1_f5_extra'))
        await db.commit()

    await _sr1_f5_conforming_control(db, bts)
    await db.rollback()
