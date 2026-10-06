"""MPANGO-MVP-INVARIANTS-R0-R1 — guard & assertion-logic unit controls (no DB).

These tests validate the RUNTIME GUARDS and the RED tests' assertion logic
themselves, so their verdicts are evidence, not assumption:

- Ownership guard negatives: missing config, disagreeing targets and wrong
  owner labels must be refused BEFORE any write. (The positive ownership path
  is exercised implicitly by every DB test through the r0_task_database
  session fixture.)
- Auth-factory controls, mirroring the product's own normalization
  (strip().lower()): every 'test'-normalizing variant — including 'TEST' and
  whitespace variants — must yield MockAuthStrategy, and staging variants
  must yield JwtAuthStrategy. This is what makes the revocation suite's
  "we exercised real JWT" claim checkable instead of an env-string guess.
- Assertion-logic controls (R1 acceptance effectiveness; R2 per CTO F2;
  wording corrected in R1 per CTO O1 2026-09-08): the concurrent return
  invariants are fed synthetic CORRECT outcomes — both valid fix shapes
  (serialize the duplicate, or reject it with the documented 409) and a
  correct single-effect economics snapshot — and must ACCEPT them; broken
  shapes must be REJECTED. The adjustment invariant is validated through
  the REAL shared assert_adjustment_chain helper (the same function the
  concurrent RED test runs against database rows): legal B→A and A→B serial
  orders accepted (B→A: 10→17→22; A→B: 10→15→22); duplicate-reason rows,
  unknown reasons, missing movements, wrong finals, wrong single-row algebra
  and the lost-update journal all REJECTED. CTO O1 correction: the PRECISE
  original three-row counterexample A(17→22)×2 + B(10→17) has its own
  control — raw rows rejected on the movement-set check, while its
  dict-folded snapshot is identical to the legal B→A chain and MUST be
  accepted (once folded, the duplicate is unrecoverable — which is exactly
  why the read helper must preserve raw rows). The R2-invented chained
  duplicate snapshot A(10→15)/A(15→20)/B(20→27) is kept as an extra bad
  snapshot under a corrected name. Test-level controls only — not a
  product-fix proof.

No product code is imported beyond auth.factory / the guard function and
the sku-list cache key builder (api.v1.skus._skus_list_cache_key, pure key
construction with no Redis/DB access); no database connection is opened.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import re

import pytest
from fastapi import HTTPException

from tests.mpango_invariants_r0_support import (
    CONTAINER_ENV_VAR,
    OWNER_LABEL_ENV_VAR,
    GuardRefused,
    verify_task_database_ownership_sync,
)

import pytest

from tests.mpango_invariants_r0_support import (
    CONTAINER_ENV_VAR,
    OWNER_LABEL_ENV_VAR,
    GuardRefused,
    verify_task_database_ownership_sync,
)


# ---------------------------------------------------------------------------
# Ownership guard negatives (pre-write refusals)
# ---------------------------------------------------------------------------

def _clear_ownership_env(monkeypatch):
    for name in (CONTAINER_ENV_VAR, OWNER_LABEL_ENV_VAR, "TEST_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_r0_guard_refuses_missing_ownership_config(monkeypatch):
    """[GUARD CONTROL] No container/owner/URL declared → refuse before any write."""
    _clear_ownership_env(monkeypatch)
    with pytest.raises(GuardRefused, match="GUARD_REFUSED_DATABASE_OWNERSHIP"):
        verify_task_database_ownership_sync()


def test_r0_guard_refuses_disagreeing_targets(monkeypatch):
    """[GUARD CONTROL] TEST_DATABASE_URL != DATABASE_URL → refuse (one target only)."""
    monkeypatch.setenv(CONTAINER_ENV_VAR, "mpango-zcode-inv-r0r1-20260907-pg")
    monkeypatch.setenv(OWNER_LABEL_ENV_VAR, "zcode-mvp-invariants-r0-r1")
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql://u:p@127.0.0.1:52639/inv_r0r1_lab"
    )
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://u:p@127.0.0.1:9999/some_other_db"
    )
    with pytest.raises(GuardRefused, match="different targets"):
        verify_task_database_ownership_sync()


def test_r0_guard_refuses_non_task_owner_label(monkeypatch, tmp_path):
    """[GUARD CONTROL] A declared owner label outside the task namespace → refuse."""
    monkeypatch.setenv(CONTAINER_ENV_VAR, "some-container")
    monkeypatch.setenv(OWNER_LABEL_ENV_VAR, "someone-elses-task")
    url = "postgresql://u:p@127.0.0.1:52639/inv_r0r1_lab"
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(GuardRefused, match="owner label"):
        verify_task_database_ownership_sync()


# ---------------------------------------------------------------------------
# Auth-factory controls (product normalization parity)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("env_value", ["test", "TEST", " test ", "\tTest", "TeSt "])
def test_r0_guard_factory_mock_for_every_test_variant(monkeypatch, env_value):
    """[GUARD CONTROL] Every 'test'-normalizing env value must select MockAuthStrategy.

    Mirrors auth.factory's os.getenv(...).strip().lower() exactly, so a Mock
    run can never be misreported as real-JWT evidence via case/whitespace
    tricks.
    """
    import importlib

    from auth.strategies.mock import MockAuthStrategy

    monkeypatch.setenv("MPANGO_ENV", env_value)
    factory = importlib.import_module("auth.factory")
    strategy = factory.get_auth_strategy()
    assert isinstance(strategy, MockAuthStrategy), (
        f"GUARD CONTROL: MPANGO_ENV={env_value!r} must normalize to 'test' and "
        f"select MockAuthStrategy, got {type(strategy).__name__}"
    )


@pytest.mark.parametrize("env_value", ["staging", " STAGING ", "production", "Production"])
def test_r0_guard_factory_jwt_for_non_test_variants(monkeypatch, env_value):
    """[GUARD CONTROL] Non-test variants must select the real JwtAuthStrategy."""
    import importlib

    from auth.strategies.jwt import JwtAuthStrategy

    monkeypatch.setenv("MPANGO_ENV", env_value)
    factory = importlib.import_module("auth.factory")
    strategy = factory.get_auth_strategy()
    assert type(strategy).__name__ == "JwtAuthStrategy", (
        f"GUARD CONTROL: MPANGO_ENV={env_value!r} must select JwtAuthStrategy, "
        f"got {type(strategy).__name__}"
    )


# ---------------------------------------------------------------------------
# Assertion-logic controls: the RED assertions must accept correct outcomes
# ---------------------------------------------------------------------------

def _rejection_409() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "INVALID_STATE_TRANSITION", "message": "duplicate return"},
    )


class _Resp:
    """Minimal stand-in for a successful route response (only truthiness used)."""


def test_r0_assertion_logic_accepts_serialized_duplicate_return():
    """[ASSERTION CONTROL] Fix shape 'second return serializes behind the first'."""
    from tests.test_mpango_mvp_invariants_r0_concurrency import (
        _assert_outcomes_contractual,
        _assert_single_economic_effect,
    )

    outcomes = [("success", _Resp()), ("success", _Resp())]
    _assert_outcomes_contractual(outcomes)  # must not raise
    snap = {
        "refund_by_account": {"cash": "-100.0000", "revenue": "100.0000"},
        "refund_cash": Decimal("-100.0000"),
        "refund_revenue": Decimal("100.0000"),
        "restock_movement_count": 1,
        "order_status": "returned",
    }
    _assert_single_economic_effect(
        snap, final_stock=Decimal("10.00"), context="assertion-control serialized"
    )


def test_r0_assertion_logic_accepts_rejected_duplicate_return():
    """[ASSERTION CONTROL] Fix shape 'duplicate return rejected 409' — accepted.

    The documented 409 rejection must satisfy the outcome contract AND still
    leave the single-effect economics to be checked (which pass here), proving
    an expected 409 never skips or suppresses the economic assertions.
    """
    from tests.test_mpango_mvp_invariants_r0_concurrency import (
        _assert_outcomes_contractual,
        _assert_single_economic_effect,
    )

    outcomes = [("success", _Resp()), ("http_rejected", _rejection_409())]
    _assert_outcomes_contractual(outcomes)  # must not raise
    snap = {
        "refund_by_account": {"cash": "-100.0000", "revenue": "100.0000"},
        "refund_cash": Decimal("-100.0000"),
        "refund_revenue": Decimal("100.0000"),
        "restock_movement_count": 1,
        "order_status": "returned",
    }
    _assert_single_economic_effect(
        snap, final_stock=Decimal("10.00"), context="assertion-control rejected"
    )


def test_r0_assertion_logic_rejects_arbitrary_error_outcome():
    """[ASSERTION CONTROL] A non-contract failure (e.g. 500) must be rejected."""
    from tests.test_mpango_mvp_invariants_r0_concurrency import (
        _assert_outcomes_contractual,
    )

    outcomes = [
        ("success", _Resp()),
        ("http_rejected", HTTPException(status_code=500, detail={"code": "BOOM"})),
    ]
    with pytest.raises(AssertionError, match="OUTCOME_CONTRACT"):
        _assert_outcomes_contractual(outcomes)


def test_r0_assertion_logic_rejects_double_economic_effect():
    """[ASSERTION CONTROL] The baseline's double-effect shape must be rejected."""
    from tests.test_mpango_mvp_invariants_r0_concurrency import (
        _assert_single_economic_effect,
    )

    snap = {
        "refund_by_account": {"cash": "-200.0000", "revenue": "200.0000"},
        "refund_cash": Decimal("-200.0000"),
        "refund_revenue": Decimal("200.0000"),
        "restock_movement_count": 2,
        "order_status": "returned",
    }
    with pytest.raises(AssertionError, match="exactly 100.00 once"):
        _assert_single_economic_effect(
            snap, final_stock=Decimal("11.00"), context="assertion-control double"
        )


# ---------------------------------------------------------------------------
# Adjustment-algebra controls (R2, CTO F2): ALL call the real shared helper
# assert_adjustment_chain (the exact function the concurrent RED test uses)
# with synthetic row shapes — no parallel assertion implementation.
# ---------------------------------------------------------------------------

_REASON_A = "r0-race-A-delta-5"
_REASON_B = "r0-race-B-delta-7"
_EXPECTED = [(_REASON_A, Decimal("5")), (_REASON_B, Decimal("7"))]


def _row(reason, qty, before, after):
    return {"reason": reason, "qty": str(qty), "q_before": str(before), "q_after": str(after)}


def test_r0_assertion_chain_accepts_b_then_a_serial_order():
    """[ASSERTION CONTROL] Legal B→A chain (10→17→22, final 22) accepted."""
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [_row(_REASON_B, 7, 10, 17), _row(_REASON_A, 5, 17, 22)]
    assert_adjustment_chain(
        rows, initial=Decimal("10"), final_observed=Decimal("22"), expected=_EXPECTED
    )


def test_r0_assertion_chain_accepts_a_then_b_serial_order():
    """[ASSERTION CONTROL] Legal A→B chain (10→15→22, final 22) also accepted.

    R2: the barrier test schedules B first, but the shared helper must not
    bake that schedule in — the reverse legal order is accepted too.
    """
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [_row(_REASON_A, 5, 10, 15), _row(_REASON_B, 7, 15, 22)]
    assert_adjustment_chain(
        rows, initial=Decimal("10"), final_observed=Decimal("22"), expected=_EXPECTED
    )


def test_r0_assertion_chain_rejects_duplicate_reason_rows():
    """[ASSERTION CONTROL] Three raw rows with a duplicated reason are
    rejected on the row-count check before any algebra (duplicate identity =
    duplicate economic effect). The R2 shape (chained duplicate values) —
    NOT the CTO's original counterexample, whose exact rows have their own
    control since the R1/CTO-O1 wording correction.
    """
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [
        _row(_REASON_A, 5, 10, 15),
        _row(_REASON_A, 5, 15, 20),  # duplicate identity — must be rejected
        _row(_REASON_B, 7, 20, 27),
    ]
    with pytest.raises(AssertionError, match="INVARIANT_R0_STOCK_MOVEMENT_SET"):
        assert_adjustment_chain(
            rows, initial=Decimal("10"), final_observed=Decimal("27"), expected=_EXPECTED
        )


def test_r0_assertion_chain_rejects_chained_duplicate_reason_rows():
    """[ASSERTION CONTROL] (R2 synthetic bad snapshot; wording corrected in
    R1 per CTO O1) Chained duplicate rows: A(10→15), A(15→20), B(20→27).

    These three rows are an R2-invented EXTRA bad snapshot, NOT the CTO's
    original counterexample (see test_r0_assertion_chain_exact_cto_counterexample_rows
    for the precise original). Their distinctive property: the old
    {reason: row} dict collapse leaves A(15→20) + B(20→27) — no row starts at
    the initial value 10 — so the collapsed snapshot happens to be rejected
    by the order-free chain check (INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA). This
    rejection is a property of THIS shape only and must not be cited as
    proof that folding is harmless in general: the CTO's original counterexample
    folds into a shape the invariant MUST accept (see the exact-counterexample
    control). Raw rows are rejected earlier on INVARIANT_R0_STOCK_MOVEMENT_SET.
    """
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [
        _row(_REASON_A, 5, 10, 15),
        _row(_REASON_A, 5, 15, 20),  # duplicate identity — must be rejected
        _row(_REASON_B, 7, 20, 27),
    ]
    # Simulate the old dict collapse: what a {reason: row} snapshot held.
    collapsed = {r["reason"]: r for r in rows}
    assert len(collapsed) == 2 and len(rows) == 3  # the blind spot, documented
    with pytest.raises(AssertionError, match="INVARIANT_R0_STOCK_MOVEMENT"):
        assert_adjustment_chain(
            list(collapsed.values()),
            initial=Decimal("10"),
            final_observed=Decimal("27"),
            expected=_EXPECTED,
        )
    # Raw rows are rejected even earlier, on the movement-set check.
    with pytest.raises(AssertionError, match="INVARIANT_R0_STOCK_MOVEMENT_SET"):
        assert_adjustment_chain(
            rows, initial=Decimal("10"), final_observed=Decimal("27"), expected=_EXPECTED
        )


def test_r0_assertion_chain_exact_cto_counterexample_rows():
    """[ASSERTION CONTROL] (CTO O1, 2026-09-08 review) The PRECISE original
    three-row counterexample: A(17→22, +5), duplicate A(17→22, +5),
    B(10→17, +7), final observed 22.

    Two properties, both asserted:

    1. The RAW three rows are rejected on INVARIANT_R0_STOCK_MOVEMENT_SET
       (row count / duplicate reason) — duplicate economic effects must be
       caught before any algebra.
    2. If the rows are first FOLDED into a {reason: row} dict — the exact
       information loss the R1 read helper used to perform — the surviving
       snapshot A(17→22) + B(10→17) is INDISTINGUISHABLE from the legal B→A
       serial chain and the shared helper MUST ACCEPT it. This is not a
       helper defect: once the third row is destroyed no assertion can
       recover it. It is precisely why adjustment_movements returns raw
       rows (and why test_r1_control_adjustment_read_helper_preserves_duplicate_rows
       pins that property against the real database).

    Economic expectation unchanged (initial 10, deltas {5,7}, final 22).
    """
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [
        _row(_REASON_A, 5, 17, 22),
        _row(_REASON_A, 5, 17, 22),  # duplicate — same stale post-B value
        _row(_REASON_B, 7, 10, 17),
    ]
    with pytest.raises(AssertionError, match="INVARIANT_R0_STOCK_MOVEMENT_SET"):
        assert_adjustment_chain(
            rows, initial=Decimal("10"), final_observed=Decimal("22"), expected=_EXPECTED
        )

    # The folded snapshot is exactly the legal B→A chain (10→17→22): the
    # helper must accept it — documenting that folding defeats the invariant.
    folded = {r["reason"]: r for r in rows}
    assert len(folded) == 2, "fixture self-check: folding must lose one row"
    assert_adjustment_chain(
        list(folded.values()),
        initial=Decimal("10"),
        final_observed=Decimal("22"),
        expected=_EXPECTED,
    )


def test_r0_assertion_chain_rejects_unknown_reason():
    """[ASSERTION CONTROL] A movement with an unexpected reason is rejected."""
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [_row("r0-unknown-source", 5, 10, 15), _row(_REASON_B, 7, 15, 22)]
    with pytest.raises(AssertionError, match="INVARIANT_R0_STOCK_MOVEMENT_SET"):
        assert_adjustment_chain(
            rows, initial=Decimal("10"), final_observed=Decimal("22"), expected=_EXPECTED
        )


def test_r0_assertion_chain_rejects_missing_movement():
    """[ASSERTION CONTROL] Only one journal row for two adjustments → reject."""
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [_row(_REASON_B, 7, 10, 17)]
    with pytest.raises(AssertionError, match="INVARIANT_R0_STOCK_MOVEMENT_SET"):
        assert_adjustment_chain(
            rows, initial=Decimal("10"), final_observed=Decimal("17"), expected=_EXPECTED
        )


def test_r0_assertion_chain_rejects_wrong_final_value():
    """[ASSERTION CONTROL] Correct journal but wrong observed final → reject."""
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [_row(_REASON_B, 7, 10, 17), _row(_REASON_A, 5, 17, 22)]
    with pytest.raises(AssertionError, match="INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA"):
        assert_adjustment_chain(
            rows, initial=Decimal("10"), final_observed=Decimal("11"), expected=_EXPECTED
        )


def test_r0_assertion_chain_rejects_wrong_single_row_algebra():
    """[ASSERTION CONTROL] A row violating before+delta=after → reject."""
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [_row(_REASON_B, 7, 10, 17), _row(_REASON_A, 5, 17, 21)]  # 17+5 != 21
    with pytest.raises(AssertionError, match="INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA"):
        assert_adjustment_chain(
            rows, initial=Decimal("10"), final_observed=Decimal("21"), expected=_EXPECTED
        )


def test_r0_assertion_chain_rejects_lost_update_journal():
    """[ASSERTION CONTROL] The baseline lost-update journal must be rejected.

    Two rows both starting from the stale initial 10 (10→15 and 10→17) with
    observed final 15: no row chains on the other's result and the journal
    total (12) does not explain the observed final.
    """
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [_row(_REASON_A, 5, 10, 15), _row(_REASON_B, 7, 10, 17)]
    with pytest.raises(AssertionError, match="INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA"):
        assert_adjustment_chain(
            rows, initial=Decimal("10"), final_observed=Decimal("15"), expected=_EXPECTED
        )


# ---------------------------------------------------------------------------
# R1-R1 (CTO F1/F3): semantic counterexamples against the REAL shared
# revocation/isolation assertion helpers.
#
# The helpers are imported from the revocation test module — the EXACT
# functions the real HTTP tests call. Each counterexample feeds a broken
# shape and the shared helper must REJECT it, proving no other condition can
# mask the target branch (no control-only copy of any assertion logic).
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal response stand-in carrying only what the shared helpers read
    (status_code / json() / text) — the helpers' logic is NOT reimplemented."""

    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def test_r1_guard_isolation_assertion_rejects_mixed_tenant_results():
    """[ASSERTION CONTROL] A listing page mixing two tenants' same-code rows
    must be REJECTED by the real shared isolation assertion."""
    from tests.test_mpango_mvp_invariants_r0_revocation import (
        assert_listing_exactly_own_tenant,
    )

    body = {
        "data": {
            "items": [
                {"id": "11111111-1111-1111-1111-111111111111",
                 "sku_code": "R1SHARED", "name": "MARKER-TENANT-A"},
                {"id": "22222222-2222-2222-2222-222222222222",
                 "sku_code": "R1SHARED", "name": "MARKER-TENANT-B"},
            ]
        }
    }
    with pytest.raises(AssertionError, match="CONTROL_R1_ISOLATION"):
        assert_listing_exactly_own_tenant(
            body,
            own_sku_id="11111111-1111-1111-1111-111111111111",
            own_name_marker="MARKER-TENANT-A",
            shared_code="R1SHARED",
            label="guard-mixed",
        )


def test_r1_guard_isolation_assertion_rejects_foreign_tenant_result():
    """[ASSERTION CONTROL] A listing containing ONLY the other tenant's
    same-code record must be REJECTED by the real shared isolation
    assertion (record identity, not the business code, decides)."""
    from tests.test_mpango_mvp_invariants_r0_revocation import (
        assert_listing_exactly_own_tenant,
    )

    body = {
        "data": {
            "items": [
                {"id": "22222222-2222-2222-2222-222222222222",
                 "sku_code": "R1SHARED", "name": "MARKER-TENANT-B"},
            ]
        }
    }
    with pytest.raises(AssertionError, match="CONTROL_R1_ISOLATION"):
        assert_listing_exactly_own_tenant(
            body,
            own_sku_id="11111111-1111-1111-1111-111111111111",
            own_name_marker="MARKER-TENANT-A",
            shared_code="R1SHARED",
            label="guard-foreign",
        )


def test_r1_guard_refresh_refusal_assertion_rejects_masked_code():
    """[ASSERTION CONTROL] A 401 carrying a DIFFERENT rejection code must be
    rejected by the shared decoupled-refusal assertion — a masked target
    branch (e.g. the tenant branch answering instead of the subject branch)
    can never satisfy it."""
    from tests.test_mpango_mvp_invariants_r0_revocation import (
        assert_refresh_refused_with_code,
    )

    with pytest.raises(AssertionError, match="must not mask"):
        assert_refresh_refused_with_code(
            _FakeResponse(401, {"code": "TENANT_NOT_FOUND", "message": "x"}),
            expected_code="PRINCIPAL_NOT_FOUND",
            label="guard-masked-code",
        )


def test_r1_guard_refresh_refusal_assertion_rejects_token_bearing_401():
    """[ASSERTION CONTROL] A 401 whose body carries session material must be
    rejected by the shared decoupled-refusal assertion."""
    from tests.test_mpango_mvp_invariants_r0_revocation import (
        assert_refresh_refused_with_code,
    )

    with pytest.raises(AssertionError, match="session material"):
        assert_refresh_refused_with_code(
            _FakeResponse(
                401,
                {"code": "PRINCIPAL_NOT_FOUND",
                 "data": {"access_token": "forged-but-present"}},
            ),
            expected_code="PRINCIPAL_NOT_FOUND",
            label="guard-token-bearing",
        )


def test_r1_guard_no_issuance_assertion_rejects_issuer_use_and_tokens():
    """[ASSERTION CONTROL] The shared zero-issuance assertion must reject
    BOTH broken shapes: an issuer that was invoked, and a fault response
    that still carries session material."""
    from tests.test_mpango_mvp_invariants_r0_revocation import (
        assert_refresh_fault_carries_no_issuance,
    )

    with pytest.raises(AssertionError, match="must not be invoked"):
        assert_refresh_fault_carries_no_issuance(
            _FakeResponse(500, {"code": "INTERNAL_SERVER_ERROR"}),
            issuer_calls=1,
            label="guard-issuer-called",
        )
    with pytest.raises(AssertionError, match="session material"):
        assert_refresh_fault_carries_no_issuance(
            _FakeResponse(
                500,
                {"code": "INTERNAL_SERVER_ERROR",
                 "data": {"refresh_token": "leaked"}},
            ),
            issuer_calls=0,
            label="guard-token-leak",
        )


# ---------------------------------------------------------------------------
# R1-R2 (CTO remediation): task-Redis ownership guard negatives for the
# precise cache-key deletion helper. Refusals happen BEFORE any docker call
# or any deletion, so these unit controls need no Redis and no docker.
# ---------------------------------------------------------------------------

def _clear_redis_ownership_env(monkeypatch):
    for name in (
        "MPANGO_INVARIANTS_R0_REDIS_CONTAINER",
        "MPANGO_INVARIANTS_R0_PG_OWNER",
        "REDIS_URL",
    ):
        monkeypatch.delenv(name, raising=False)


class _FakeRedisClient:
    def __init__(
        self,
        *,
        host="127.0.0.1",
        port=60212,
        db=15,
        ssl=None,
        connection_class_name="Connection",
        include_connection_kwargs=True,
        ping_exc=None,
        delete_result=1,
    ):
        self.ping_calls = 0
        self.delete_calls = 0
        self.delete_args = None
        self.scan_calls = 0
        self.scan_iter_calls = 0
        self.keys_calls = 0
        self._ping_exc = ping_exc
        self._delete_result = delete_result
        self.connection_pool = SimpleNamespace()
        if include_connection_kwargs:
            kwargs = {}
            if host is not None:
                kwargs["host"] = host
            if port is not None:
                kwargs["port"] = port
            if db is not None:
                kwargs["db"] = db
            if ssl is not None:
                kwargs["ssl"] = ssl
            self.connection_pool.connection_kwargs = kwargs
        self.connection_pool.connection_class = type(connection_class_name, (), {})

    async def ping(self):
        self.ping_calls += 1
        if self._ping_exc is not None:
            raise self._ping_exc
        return True

    async def delete(self, *keys):
        self.delete_calls += 1
        self.delete_args = keys
        if callable(self._delete_result):
            return self._delete_result(*keys)
        return self._delete_result

    def scan(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.scan_calls += 1
        return 0, []

    def scan_iter(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.scan_iter_calls += 1
        return iter(())

    def keys(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.keys_calls += 1
        return []


def _redis_docker_inspect(
    *,
    owner_label: str,
    image: str = "redis:7-alpine",
    host_ip: str = "127.0.0.1",
    host_port: str = "60212",
):
    return {
        "Config": {
            "Labels": {"mpango.owner": owner_label},
            "Image": image,
        },
        "NetworkSettings": {
            "Ports": {
                "6379/tcp": [
                    {"HostIp": host_ip, "HostPort": host_port},
                ]
            }
        },
    }


def _bind_redis_guard_env(monkeypatch, *, redis_url: str = "redis://127.0.0.1:60212/15"):
    monkeypatch.setenv("MPANGO_INVARIANTS_R0_REDIS_CONTAINER", "mpango-r1-redis")
    monkeypatch.setenv("MPANGO_INVARIANTS_R0_PG_OWNER", "zcode-mvp-invariants-r1-r1")
    monkeypatch.setenv("REDIS_URL", redis_url)


def test_r1_guard_redis_eviction_guard_refuses_missing_config(monkeypatch):
    """[GUARD CONTROL] No declared Redis container / owner / URL → refuse
    before any deletion."""
    from tests.mpango_invariants_r0_support import (
        GuardRefused,
        verify_task_redis_ownership_sync,
    )

    _clear_redis_ownership_env(monkeypatch)
    client = object()
    with pytest.raises(GuardRefused, match="GUARD_REFUSED_REDIS_OWNERSHIP"):
        verify_task_redis_ownership_sync(client)


def test_r1_guard_redis_eviction_guard_refuses_non_task_owner_label(monkeypatch):
    """[GUARD CONTROL] An owner label outside the task namespace → refuse."""
    from tests.mpango_invariants_r0_support import (
        GuardRefused,
        verify_task_redis_ownership_sync,
    )

    _clear_redis_ownership_env(monkeypatch)
    monkeypatch.setenv("MPANGO_INVARIANTS_R0_REDIS_CONTAINER", "some-redis")
    monkeypatch.setenv("MPANGO_INVARIANTS_R0_PG_OWNER", "someone-elses-task")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/15")
    client = _FakeRedisClient(port=6379, db=15)
    from tests import mpango_invariants_r0_support as support

    monkeypatch.setattr(
        support,
        "_docker_inspect",
        lambda container: _redis_docker_inspect(
            owner_label="someone-elses-task",
            host_port="6379",
        ),
    )
    with pytest.raises(GuardRefused, match="owner label"):
        verify_task_redis_ownership_sync(client)


def test_r1_guard_redis_eviction_guard_refuses_non_loopback_url(monkeypatch):
    """[GUARD CONTROL] A non-loopback REDIS_URL → refuse (never delete on a
    remote/shared instance)."""
    from tests.mpango_invariants_r0_support import (
        GuardRefused,
        verify_task_redis_ownership_sync,
    )

    _clear_redis_ownership_env(monkeypatch)
    monkeypatch.setenv("MPANGO_INVARIANTS_R0_REDIS_CONTAINER", "some-redis")
    monkeypatch.setenv("MPANGO_INVARIANTS_R0_PG_OWNER", "zcode-mvp-invariants-r1-r1")
    monkeypatch.setenv("REDIS_URL", "redis://shared-cache.internal:6379/15")
    client = _FakeRedisClient()
    with pytest.raises(GuardRefused, match="not loopback"):
        verify_task_redis_ownership_sync(client)


def test_r1_guard_sku_list_cache_key_shape_is_exact():
    """[GUARD CONTROL] The precise-key deletion targets exactly the keys
    `_list_skus_cached` builds — the tenant-scoped shape
    skus_list:{tenant_schema}:{page}:{size}:{is_active}:{q} (default listing:
    page 1, size 10, is_active None, query q). The test-side helper and the
    PRODUCT key builder (api.v1.skus._skus_list_cache_key) must agree on the
    exact bytes, so precise-key eviction can never drift from what the
    product actually writes."""
    from api.v1.skus import _skus_list_cache_key as product_key_builder

    from tests.test_mpango_mvp_invariants_r0_revocation import _sku_list_cache_key

    schema = "t_ab12cd34ef"
    q = "R1ISOSHAREDAB12CD34"
    expected = f"skus_list:{schema}:1:10:None:{q}"
    assert _sku_list_cache_key(q, tenant_schema=schema) == expected
    session = SimpleNamespace(info={"tenant_schema": schema})
    # core/cache.py composes key = f"{key_prefix}:{key_builder(...)}" with
    # key_prefix="skus_list": the product builder yields the tenant-first
    # suffix, so the composed key is exactly the eviction target.
    assert f"skus_list:{product_key_builder(session, 1, 10, None, q)}" == expected
    assert product_key_builder(session, 1, 10, None, q) == (
        f"{schema}:1:10:None:{q}"
    )


def test_r1_guard_sku_list_cache_key_differs_per_tenant_and_is_stable():
    """[GUARD CONTROL] Identical listing parameters under two tenant schemas
    must produce DIFFERENT cache keys, and the same tenant schema with the
    same parameters must produce a STABLE identical key (the R1 SKU-cache
    tenant-isolation contract)."""
    from api.v1.skus import _skus_list_cache_key as product_key_builder

    def session_for(schema: str) -> SimpleNamespace:
        return SimpleNamespace(info={"tenant_schema": schema})

    key_a1 = "skus_list:" + product_key_builder(session_for("t_aaaa1111"), 2, 25, True, "probe")
    key_a2 = "skus_list:" + product_key_builder(session_for("t_aaaa1111"), 2, 25, True, "probe")
    key_b = "skus_list:" + product_key_builder(session_for("t_bbbb2222"), 2, 25, True, "probe")

    assert key_a1 == key_a2, (
        "the same tenant schema with identical parameters must build the "
        "same key (normal cache hits depend on key stability)"
    )
    assert key_a1 != key_b, (
        "identical query parameters under different tenant schemas must "
        "address different cache keys (tenant isolation)"
    )
    assert key_a1.startswith("skus_list:t_aaaa1111:2:25:True:probe"), (
        f"unexpected tenant-scoped key shape: {key_a1!r}"
    )


@pytest.mark.parametrize(
    "session_factory, case",
    [
        (lambda: SimpleNamespace(), "no-info-attribute"),
        (lambda: SimpleNamespace(info={}), "missing-tenant-schema"),
        (lambda: SimpleNamespace(info={"tenant_schema": None}), "none-tenant-schema"),
        (lambda: SimpleNamespace(info={"tenant_schema": ""}), "empty-tenant-schema"),
        (lambda: SimpleNamespace(info={"tenant_schema": 123}), "non-string-tenant-schema"),
        (lambda: SimpleNamespace(info={"tenant_schema": "t_evil:drop"}), "colon-injection"),
        (lambda: SimpleNamespace(info={"tenant_schema": "t-evil"}), "dash-invalid"),
        (lambda: SimpleNamespace(info={"tenant_schema": "t evil"}), "space-invalid"),
    ],
)
def test_r1_guard_sku_list_cache_key_fail_closed_named_rejection(session_factory, case):
    """[GUARD CONTROL] A session whose tenant_schema is missing, empty,
    non-string or an invalid identifier must be rejected by a NAMED error
    carrying the invariant — never degraded to a global, None-namespaced or
    pre-R1 cache key (fail-closed contract)."""
    from api.v1.skus import SkuListCacheTenantContextError
    from api.v1.skus import _skus_list_cache_key as product_key_builder

    with pytest.raises(SkuListCacheTenantContextError) as raised:
        product_key_builder(session_factory(), 1, 10, None, "probe")
    assert "INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED" in str(raised.value), (
        f"[{case}] the rejection must be NAMED after the invariant, got "
        f"{str(raised.value)[:200]!r}"
    )


def test_r1_guard_redis_ownership_accepts_normalized_loopback_binding(monkeypatch):
    """[GUARD CONTROL] The real ownership helper accepts the bound client
    when the declared URL and the actual client pool resolve to the same
    loopback target, even if one side uses localhost and the other uses
    127.0.0.1."""
    from tests import mpango_invariants_r0_support as support

    _clear_redis_ownership_env(monkeypatch)
    _bind_redis_guard_env(monkeypatch, redis_url="redis://localhost:60212/15")
    monkeypatch.setattr(
        support,
        "_docker_inspect",
        lambda container: _redis_docker_inspect(
            owner_label="zcode-mvp-invariants-r1-r1",
            host_port="60212",
        ),
    )
    client = _FakeRedisClient(host="127.0.0.1", port=60212, db=15)

    verified = support.verify_task_redis_ownership_sync(client)

    assert verified == "127.0.0.1:60212"
    assert client.ping_calls == 0
    assert client.delete_calls == 0


@pytest.mark.parametrize(
    "client_kwargs, expected_fragment",
    [
        ({"port": 60213}, "port"),
        ({"db": 14}, "db"),
        ({"ssl": True}, "scheme"),
    ],
)
def test_r1_guard_redis_ownership_refuses_client_binding_mismatches(
    monkeypatch, client_kwargs, expected_fragment
):
    """[GUARD CONTROL] A cached client that binds to the wrong host/port/db
    or TLS mode must be refused before any network I/O."""
    from tests import mpango_invariants_r0_support as support

    _clear_redis_ownership_env(monkeypatch)
    _bind_redis_guard_env(monkeypatch)
    monkeypatch.setattr(
        support,
        "_docker_inspect",
        lambda container: _redis_docker_inspect(
            owner_label="zcode-mvp-invariants-r1-r1",
            host_port="60212",
        ),
    )
    client = _FakeRedisClient(**client_kwargs)

    with pytest.raises(GuardRefused, match=expected_fragment):
        support.verify_task_redis_ownership_sync(client)


@pytest.mark.parametrize(
    "client_kwargs, expected_fragment",
    [
        ({"host": None, "port": 60212, "db": 15}, "missing host"),
        ({"host": "127.0.0.1", "port": None, "db": 15}, "missing port"),
        ({"host": "127.0.0.1", "port": 60212, "db": None}, "missing db"),
    ],
)
def test_r1_guard_redis_ownership_refuses_incomplete_client_binding(
    monkeypatch, client_kwargs, expected_fragment
):
    """[GUARD CONTROL] A client pool that cannot resolve host/port/db must
    be rejected before the helper can proceed to any ping/delete."""
    from tests import mpango_invariants_r0_support as support

    _clear_redis_ownership_env(monkeypatch)
    _bind_redis_guard_env(monkeypatch)
    monkeypatch.setattr(
        support,
        "_docker_inspect",
        lambda container: _redis_docker_inspect(
            owner_label="zcode-mvp-invariants-r1-r1",
            host_port="60212",
        ),
    )
    client = _FakeRedisClient(**client_kwargs)

    with pytest.raises(GuardRefused, match=expected_fragment):
        support.verify_task_redis_ownership_sync(client)


def test_r1_guard_redis_ownership_refuses_missing_connection_pool(monkeypatch):
    """[GUARD CONTROL] A client with no connection_pool attribute must be
    rejected before any cache I/O."""
    from tests import mpango_invariants_r0_support as support

    _clear_redis_ownership_env(monkeypatch)
    _bind_redis_guard_env(monkeypatch)
    monkeypatch.setattr(
        support,
        "_docker_inspect",
        lambda container: _redis_docker_inspect(
            owner_label="zcode-mvp-invariants-r1-r1",
            host_port="60212",
        ),
    )
    client = object()

    with pytest.raises(GuardRefused, match="no connection_pool"):
        support.verify_task_redis_ownership_sync(client)


def test_r1_guard_redis_ownership_refuses_missing_connection_kwargs(monkeypatch):
    """[GUARD CONTROL] A pool with no readable connection_kwargs must be
    rejected before any cache I/O."""
    from tests import mpango_invariants_r0_support as support

    _clear_redis_ownership_env(monkeypatch)
    _bind_redis_guard_env(monkeypatch)
    monkeypatch.setattr(
        support,
        "_docker_inspect",
        lambda container: _redis_docker_inspect(
            owner_label="zcode-mvp-invariants-r1-r1",
            host_port="60212",
        ),
    )
    client = _FakeRedisClient(include_connection_kwargs=False)

    with pytest.raises(GuardRefused, match="connection_kwargs"):
        support.verify_task_redis_ownership_sync(client)


@pytest.mark.parametrize(
    "inspect_kwargs, expected_fragment",
    [
        ({"owner_label": "someone-elses-task"}, "does not match declared owner"),
        ({"image": "postgres:16-alpine"}, "is not redis:*"),
        ({"host_port": "60213"}, "does not match REDIS_URL host/port"),
    ],
)
def test_r1_guard_redis_ownership_refuses_docker_metadata_mismatches(
    monkeypatch, inspect_kwargs, expected_fragment
):
    """[GUARD CONTROL] Label/image/loopback mapping mismatches on the task
    container must refuse after the client binding matches."""
    from tests import mpango_invariants_r0_support as support

    _clear_redis_ownership_env(monkeypatch)
    _bind_redis_guard_env(monkeypatch)

    def _inspect(container):  # noqa: ANN001
        payload = {"owner_label": "zcode-mvp-invariants-r1-r1"}
        payload.update(inspect_kwargs)
        return _redis_docker_inspect(**payload)

    monkeypatch.setattr(
        support,
        "_docker_inspect",
        _inspect,
    )
    client = _FakeRedisClient()

    with pytest.raises(GuardRefused, match=expected_fragment):
        support.verify_task_redis_ownership_sync(client)


@pytest.mark.asyncio
async def test_r1_guard_redis_eviction_delete_helper_accepts_bound_client_and_exact_key(
    monkeypatch,
):
    """[GUARD CONTROL] The real deletion helper accepts a bound client,
    pings once after ownership proof, deletes exactly the computed key, and
    never touches scan-style APIs."""
    from tests import mpango_invariants_r0_support as support
    from tests.test_mpango_mvp_invariants_r0_revocation import (
        _delete_sku_list_cache_keys,
    )

    _clear_redis_ownership_env(monkeypatch)
    _bind_redis_guard_env(monkeypatch, redis_url="redis://localhost:60212/15")
    monkeypatch.setattr(
        support,
        "_docker_inspect",
        lambda container: _redis_docker_inspect(
            owner_label="zcode-mvp-invariants-r1-r1",
            host_port="60212",
        ),
    )
    client = _FakeRedisClient(host="127.0.0.1", port=60212, db=15)
    async def fake_get_redis_client():
        return client

    monkeypatch.setattr("core.cache.get_redis_client", fake_get_redis_client)
    key = "skus_list:1:10:None:R1ISOSHAREDAB12CD34"

    premise = await _delete_sku_list_cache_keys([key])

    assert premise == "deleted=1"
    assert client.ping_calls == 1
    assert client.delete_calls == 1
    assert client.delete_args == (key,)
    assert client.scan_calls == 0
    assert client.scan_iter_calls == 0
    assert client.keys_calls == 0


@pytest.mark.asyncio
async def test_r1_guard_redis_eviction_delete_helper_refuses_cached_client_binding_mismatch_before_ping(
    monkeypatch,
):
    """[GUARD CONTROL] The actual deletion helper must refuse a cached
    client whose pool points at the wrong Redis target before ping/delete."""
    from tests import mpango_invariants_r0_support as support
    from tests.test_mpango_mvp_invariants_r0_revocation import (
        _delete_sku_list_cache_keys,
    )

    _clear_redis_ownership_env(monkeypatch)
    _bind_redis_guard_env(monkeypatch)
    monkeypatch.setattr(
        support,
        "_docker_inspect",
        lambda container: _redis_docker_inspect(
            owner_label="zcode-mvp-invariants-r1-r1",
            host_port="60212",
        ),
    )
    client = _FakeRedisClient(port=60213)
    async def fake_get_redis_client():
        return client

    monkeypatch.setattr("core.cache.get_redis_client", fake_get_redis_client)

    premise = await _delete_sku_list_cache_keys(["skus_list:1:10:None:R1ISOSHAREDAB12CD34"])

    assert premise.startswith("refused-ownership(")
    assert "port" in premise
    assert client.ping_calls == 0
    assert client.delete_calls == 0
    assert client.scan_calls == 0
    assert client.scan_iter_calls == 0
    assert client.keys_calls == 0


@pytest.mark.asyncio
async def test_r1_guard_redis_eviction_delete_helper_reports_unreachable_after_proven_binding(
    monkeypatch,
):
    """[GUARD CONTROL] Once ownership is proven, a ping failure is reported
    as cache-unreachable and still performs zero deletions."""
    from tests import mpango_invariants_r0_support as support
    from tests.test_mpango_mvp_invariants_r0_revocation import (
        _delete_sku_list_cache_keys,
    )

    _clear_redis_ownership_env(monkeypatch)
    _bind_redis_guard_env(monkeypatch)
    monkeypatch.setattr(
        support,
        "_docker_inspect",
        lambda container: _redis_docker_inspect(
            owner_label="zcode-mvp-invariants-r1-r1",
            host_port="60212",
        ),
    )
    client = _FakeRedisClient(ping_exc=ConnectionError("boom"))
    async def fake_get_redis_client():
        return client

    monkeypatch.setattr("core.cache.get_redis_client", fake_get_redis_client)

    premise = await _delete_sku_list_cache_keys(["skus_list:1:10:None:R1ISOSHAREDAB12CD34"])

    assert premise == "cache-unreachable(ConnectionError)"
    assert client.ping_calls == 1
    assert client.delete_calls == 0
    assert client.scan_calls == 0
    assert client.scan_iter_calls == 0
    assert client.keys_calls == 0


@pytest.mark.asyncio
async def test_r1_guard_redis_eviction_delete_helper_refuses_missing_pool_before_ping(
    monkeypatch,
):
    """[GUARD CONTROL] If the cached client cannot expose a pool binding,
    the helper refuses before ping/delete and reports ownership failure."""
    from tests import mpango_invariants_r0_support as support
    from tests.test_mpango_mvp_invariants_r0_revocation import (
        _delete_sku_list_cache_keys,
    )

    _clear_redis_ownership_env(monkeypatch)
    _bind_redis_guard_env(monkeypatch)
    monkeypatch.setattr(
        support,
        "_docker_inspect",
        lambda container: _redis_docker_inspect(
            owner_label="zcode-mvp-invariants-r1-r1",
            host_port="60212",
        ),
    )
    client = object()
    async def fake_get_redis_client():
        return client

    monkeypatch.setattr("core.cache.get_redis_client", fake_get_redis_client)

    premise = await _delete_sku_list_cache_keys(["skus_list:1:10:None:R1ISOSHAREDAB12CD34"])

    assert premise.startswith("refused-ownership(")
    assert "connection_pool" in premise


# ---------------------------------------------------------------------------
# F1 role closure (CTO-AUTH-...-F1-DB-FIXTURE-ROLE-CLOSURE-2026-09-08):
# declaration-level negatives for the migration-identity contract. All three
# exercise the REAL verify_task_database_ownership_sync and refuse BEFORE any
# docker inspect or subprocess work (no Redis/DB needed).
# ---------------------------------------------------------------------------

def _f1_declare_base_env(monkeypatch, *, migration_url):
    from tests.mpango_invariants_r0_support import (
        ADMIN_URL_ENV_VAR,
        MIGRATION_URL_ENV_VAR,
    )

    monkeypatch.setenv(CONTAINER_ENV_VAR, "any-task-container")
    monkeypatch.setenv(OWNER_LABEL_ENV_VAR, "zcode-mvp-invariants-f1-role-closure")
    run_url = "postgresql://inv_run@127.0.0.1:52639/inv_f1_lab"
    monkeypatch.setenv("TEST_DATABASE_URL", run_url)
    monkeypatch.setenv("DATABASE_URL", run_url)
    monkeypatch.delenv(MIGRATION_URL_ENV_VAR, raising=False)
    if migration_url:
        monkeypatch.setenv(MIGRATION_URL_ENV_VAR, migration_url)
    # R1 correction (CTO F3): the container bootstrap user is declared as the
    # ADMINISTRATOR on the same task endpoint (the guard checks the
    # admin==migration separation before any docker/subprocess work).
    monkeypatch.setenv(
        ADMIN_URL_ENV_VAR, "postgresql://inv_admin@127.0.0.1:52639/inv_f1_lab"
    )


def test_f1_guard_refuses_missing_migration_url(monkeypatch):
    """[GUARD CONTROL] No declared migration identity URL → refuse before
    docker/subprocess (never fall back to the run session or alembic.ini)."""
    from tests.mpango_invariants_r0_support import (
        MIGRATION_URL_ENV_VAR,
        verify_task_database_ownership_sync,
    )

    assert MIGRATION_URL_ENV_VAR == "MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL"
    _f1_declare_base_env(monkeypatch, migration_url=None)
    with pytest.raises(GuardRefused, match=MIGRATION_URL_ENV_VAR):
        verify_task_database_ownership_sync()


def test_f1_guard_refuses_migration_target_mismatch(monkeypatch):
    """[GUARD CONTROL] Migration URL bound to a different database than the
    run session → refuse (same container/port/database is mandatory)."""
    from tests.mpango_invariants_r0_support import (
        verify_task_database_ownership_sync,
    )

    _f1_declare_base_env(
        monkeypatch,
        migration_url="postgresql://inv_boot@127.0.0.1:52639/other_db",
    )
    with pytest.raises(GuardRefused, match="SAME task container"):
        verify_task_database_ownership_sync()


def test_f1_guard_refuses_run_user_equal_to_bootstrap(monkeypatch):
    """[GUARD CONTROL] Test-session user equal to the migration/bootstrap
    user → refuse (the run identity must be a separate role)."""
    from tests.mpango_invariants_r0_support import (
        MIGRATION_URL_ENV_VAR,
        verify_task_database_ownership_sync,
    )

    run_url = "postgresql://inv_boot@127.0.0.1:52639/inv_f1_lab"
    monkeypatch.setenv(CONTAINER_ENV_VAR, "any-task-container")
    monkeypatch.setenv(OWNER_LABEL_ENV_VAR, "zcode-mvp-invariants-f1-role-closure")
    monkeypatch.setenv("TEST_DATABASE_URL", run_url)
    monkeypatch.setenv("DATABASE_URL", run_url)
    monkeypatch.setenv(
        MIGRATION_URL_ENV_VAR,
        "postgresql://inv_boot@127.0.0.1:52639/inv_f1_lab",
    )
    with pytest.raises(GuardRefused, match="migration/bootstrap user"):
        verify_task_database_ownership_sync()


def test_f1_guard_refuses_migration_equal_to_container_admin(monkeypatch):
    """[GUARD CONTROL, R1 correction CTO F3] The migration authority user
    equal to the container bootstrap ADMINISTRATOR → refuse before any
    docker/subprocess work: migration must run under its own dedicated role
    created by the product provisioner, never the container bootstrap user."""
    from tests.mpango_invariants_r0_support import (
        ADMIN_URL_ENV_VAR,
        MIGRATION_URL_ENV_VAR,
        verify_task_database_ownership_sync,
    )

    run_url = "postgresql://inv_run@127.0.0.1:52639/inv_f1_lab"
    monkeypatch.setenv(CONTAINER_ENV_VAR, "any-task-container")
    monkeypatch.setenv(OWNER_LABEL_ENV_VAR, "zcode-mvp-invariants-f1-role-closure")
    monkeypatch.setenv("TEST_DATABASE_URL", run_url)
    monkeypatch.setenv("DATABASE_URL", run_url)
    monkeypatch.setenv(
        ADMIN_URL_ENV_VAR,
        "postgresql://inv_admin@127.0.0.1:52639/inv_f1_lab",
    )
    monkeypatch.setenv(
        MIGRATION_URL_ENV_VAR,
        "postgresql://inv_admin@127.0.0.1:52639/inv_f1_lab",
    )
    with pytest.raises(
        GuardRefused, match="bootstrap ADMINISTRATOR"
    ):
        verify_task_database_ownership_sync()


# ---------------------------------------------------------------------------
# R3 ownership-admission controls (CTO-C91-CI-EXECUTABLE-CONTRACT-R3): the
# container's POSTGRES_DB names the INIT/maintenance database only; ownership
# of the product-provisioned application database is proven LIVE and
# read-only before any write. Positive + negative unit controls below mock
# ONLY docker inspect, the two live connections and the engine binding —
# every static declaration check before them still executes for real.
# ---------------------------------------------------------------------------
class _R3FakeCursor:
    """SQL-semantic fake cursor (R3R1 F-03): fetchone() derives from the
    EXECUTED statement, not from a positional result queue — consumption
    order across cursors and connections can never misalign rows. execute()
    also records any DDL so the read-only controls can prove the live proof
    issues none."""

    _DDL_RE = re.compile(
        r"\b(CREATE|ALTER|DROP|GRANT|REVOKE|TRUNCATE|INSERT|UPDATE|DELETE)\b", re.I
    )

    def __init__(self, conn):
        self._conn = conn
        self._query = ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self._query = query
        self._conn.executed.append(query)
        if self._DDL_RE.search(query):
            self._conn.ddl_seen = True

    def fetchone(self):
        query = self._query
        if "current_database()" in query:
            return self._conn.identity
        if "system_identifier" in query:
            return (self._conn.system_id,)
        if "pg_database" in query:
            return self._conn.owner_row
        return None


class _R3FakeConn:
    def __init__(self, *, identity, system_id, owner_row):
        self.identity = identity
        self.system_id = system_id
        self.owner_row = owner_row
        self.executed = []
        self.ddl_seen = False
        self.closed = False

    def cursor(self):
        return _R3FakeCursor(self)

    def close(self):
        self.closed = True


def _r3_bind_ownership_env(monkeypatch, *, port="52639"):
    from tests.mpango_invariants_r0_support import (  # noqa: F401 (rebind locals)
        ADMIN_URL_ENV_VAR,
        MIGRATION_URL_ENV_VAR,
    )
    globals()["ADMIN_URL_ENV_VAR"] = ADMIN_URL_ENV_VAR
    globals()["MIGRATION_URL_ENV_VAR"] = MIGRATION_URL_ENV_VAR
    run_url = f"postgresql://inv_run@127.0.0.1:{port}/inv_r3_lab"
    monkeypatch.setenv(CONTAINER_ENV_VAR, "inv-r3-container")
    monkeypatch.setenv(OWNER_LABEL_ENV_VAR, "zcode-mvp-invariants-r3-executable")
    monkeypatch.setenv("TEST_DATABASE_URL", run_url)
    monkeypatch.setenv("DATABASE_URL", run_url)
    monkeypatch.setenv(ADMIN_URL_ENV_VAR, "postgresql://inv_admin@127.0.0.1:" + port + "/postgres")
    monkeypatch.setenv(
        MIGRATION_URL_ENV_VAR, "postgresql://inv_migrate@127.0.0.1:" + port + "/inv_r3_lab"
    )
    return run_url


def _r3_docker_inspect():
    # POSTGRES_DB deliberately names the maintenance/init database (postgres),
    # DIFFERENT from the provisioned target inv_r3_lab: under the R3 contract
    # that difference must be accepted — ownership is proven live instead.
    return {
        "Config": {
            "Labels": {"mpango.owner": "zcode-mvp-invariants-r3-executable"},
            "Image": "postgres:16-alpine",
            "Env": ["POSTGRES_USER=inv_admin", "POSTGRES_DB=postgres"],
        },
        "NetworkSettings": {
            "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "52639"}]}
        },
    }


def _r3_live_connections(*, current=("inv_r3_lab", "inv_run"), owner="inv_migrate",
                         catalog_row=True, same_cluster=True):
    run = _R3FakeConn(identity=current, system_id=12345, owner_row=None)
    admin = _R3FakeConn(
        identity=("postgres", "inv_admin"),
        system_id=12345 if same_cluster else 99999,
        owner_row=(owner,) if catalog_row else None,
    )
    return run, admin


def test_r3_guard_accepts_live_provisioned_target_with_distinct_init_db(monkeypatch):
    """[R3 POSITIVE CONTROL] A container whose POSTGRES_DB is the maintenance
    database (different from the URL database) is ACCEPTED when the live
    read-only proof lands on the declared target as the run user, the target
    is migration-owned in the catalog and both connections bind one cluster.
    Both live connections must be closed."""
    from tests import mpango_invariants_r0_support as support
    from tests.mpango_invariants_r0_support import verify_task_database_ownership_sync

    run_url = _r3_bind_ownership_env(monkeypatch)
    monkeypatch.setattr(support, "_docker_inspect", lambda container: _r3_docker_inspect())
    run_conn, admin_conn = _r3_live_connections()
    connect_urls = []

    def fake_connect(url, **kwargs):
        connect_urls.append(url)
        return run_conn if url.startswith("postgresql://inv_run") else admin_conn

    monkeypatch.setattr("psycopg2.connect", fake_connect)
    engine_bindings = []
    monkeypatch.setattr(
        support, "_assert_engine_binding", lambda *a, **k: engine_bindings.append(1)
    )
    assert verify_task_database_ownership_sync() == run_url
    assert engine_bindings, "engine binding must still run after the live proof"
    assert run_conn.closed and admin_conn.closed
    assert len(connect_urls) == 2
    # the live proof is read-only: no DDL ever executes on either connection
    assert not run_conn.ddl_seen and not admin_conn.ddl_seen
    assert any("pg_database" in q for q in admin_conn.executed), (
        "the catalog ownership probe must actually run on the admin connection"
    )

    # R3R1-01 closeout: prove the FAKE's own DDL detector discriminates.
    # Positive: on a fresh connection each DDL verb must set ddl_seen.
    # Negative: on another fresh connection the REAL guard's SELECT set must
    # leave ddl_seen false. These are fake.execute calls only — no database
    # is contacted and no statement of either kind actually runs.
    for verb in (
        "CREATE TABLE probe (x int)",
        "ALTER TABLE probe ADD COLUMN y int",
        "DROP TABLE probe",
        "GRANT SELECT ON t TO someone",
        "REVOKE SELECT ON t FROM someone",
        "TRUNCATE TABLE probe",
        "INSERT INTO probe VALUES (1)",
        "UPDATE probe SET x = 2",
        "DELETE FROM probe",
    ):
        ddl_conn = _R3FakeConn(
            identity=("inv_r3_lab", "inv_run"), system_id=12345, owner_row=None
        )
        with ddl_conn.cursor() as cursor:
            cursor.execute(verb)
        assert ddl_conn.ddl_seen, f"detector must flag: {verb}"

    select_conn = _R3FakeConn(
        identity=("inv_r3_lab", "inv_run"), system_id=12345, owner_row=("inv_migrate",)
    )
    with select_conn.cursor() as cursor:
        cursor.execute("SELECT current_database(), current_user")
        cursor.fetchone()
        cursor.execute("SELECT system_identifier FROM pg_control_system()")
        cursor.fetchone()
        cursor.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s",
            ("inv_r3_lab",),
        )
        cursor.fetchone()
    assert not select_conn.ddl_seen, (
        "the real guard's read-only SELECT set must never trip the DDL detector"
    )


def test_r3_guard_refuses_live_target_mismatch(monkeypatch):
    """[R3 NEGATIVE CONTROL] The run connection landing on the wrong database
    or user refuses before any write."""
    from tests import mpango_invariants_r0_support as support
    from tests.mpango_invariants_r0_support import GuardRefused, verify_task_database_ownership_sync

    _r3_bind_ownership_env(monkeypatch)
    monkeypatch.setattr(support, "_docker_inspect", lambda container: _r3_docker_inspect())
    run_conn, admin_conn = _r3_live_connections(current=("other_db", "inv_run"))
    monkeypatch.setattr("psycopg2.connect", lambda url, **kw: run_conn)
    monkeypatch.setattr(support, "_assert_engine_binding", lambda *a, **k: None)
    with pytest.raises(GuardRefused, match="LIVE_TARGET_MISMATCH"):
        verify_task_database_ownership_sync()
    assert run_conn.closed


def test_r3_guard_refuses_live_target_missing_from_catalog(monkeypatch):
    """[R3 NEGATIVE CONTROL] A target database absent from pg_database
    refuses with a named LIVE_TARGET_NOT_IN_CATALOG error."""
    from tests import mpango_invariants_r0_support as support
    from tests.mpango_invariants_r0_support import GuardRefused, verify_task_database_ownership_sync

    _r3_bind_ownership_env(monkeypatch)
    monkeypatch.setattr(support, "_docker_inspect", lambda container: _r3_docker_inspect())
    run_conn, admin_conn = _r3_live_connections(catalog_row=False)
    monkeypatch.setattr(
        "psycopg2.connect",
        lambda url, **kw: run_conn if url.startswith("postgresql://inv_run") else admin_conn,
    )
    with pytest.raises(GuardRefused, match="LIVE_TARGET_NOT_IN_CATALOG"):
        verify_task_database_ownership_sync()
    assert run_conn.closed and admin_conn.closed


def test_r3_guard_refuses_live_target_owner_mismatch(monkeypatch):
    """[R3 NEGATIVE CONTROL] A provisioned-looking database owned by anyone
    other than the declared migration authority refuses."""
    from tests import mpango_invariants_r0_support as support
    from tests.mpango_invariants_r0_support import GuardRefused, verify_task_database_ownership_sync

    _r3_bind_ownership_env(monkeypatch)
    monkeypatch.setattr(support, "_docker_inspect", lambda container: _r3_docker_inspect())
    run_conn, admin_conn = _r3_live_connections(owner="someone_else")
    monkeypatch.setattr(
        "psycopg2.connect",
        lambda url, **kw: run_conn if url.startswith("postgresql://inv_run") else admin_conn,
    )
    with pytest.raises(GuardRefused, match="LIVE_TARGET_OWNER_MISMATCH"):
        verify_task_database_ownership_sync()


def test_r3_guard_refuses_live_cluster_mismatch(monkeypatch):
    """[R3 NEGATIVE CONTROL] Run and administrator connections resolving to
    different cluster system identifiers refuse (not one task cluster)."""
    from tests import mpango_invariants_r0_support as support
    from tests.mpango_invariants_r0_support import GuardRefused, verify_task_database_ownership_sync

    _r3_bind_ownership_env(monkeypatch)
    monkeypatch.setattr(support, "_docker_inspect", lambda container: _r3_docker_inspect())
    run_conn, admin_conn = _r3_live_connections(same_cluster=False)
    monkeypatch.setattr(
        "psycopg2.connect",
        lambda url, **kw: run_conn if url.startswith("postgresql://inv_run") else admin_conn,
    )
    with pytest.raises(GuardRefused, match="LIVE_TARGET_CLUSTER_MISMATCH"):
        verify_task_database_ownership_sync()


def test_r3_guard_refuses_live_connect_failure_without_dsn_echo(monkeypatch):
    """[R3 NEGATIVE CONTROL] A failing run connection refuses with a named
    error that contains neither the DSN nor the password."""
    import psycopg2 as real_psycopg2
    from tests import mpango_invariants_r0_support as support
    from tests.mpango_invariants_r0_support import GuardRefused, verify_task_database_ownership_sync

    _r3_bind_ownership_env(monkeypatch)
    monkeypatch.setattr(support, "_docker_inspect", lambda container: _r3_docker_inspect())

    def failing_connect(url, **kwargs):
        raise real_psycopg2.OperationalError("connection refused with secret material")

    monkeypatch.setattr("psycopg2.connect", failing_connect)
    with pytest.raises(GuardRefused, match="LIVE_TARGET_RUN_CONNECT_FAILED") as exc_info:
        verify_task_database_ownership_sync()
    message = str(exc_info.value)
    assert "inv_run@" not in message and "postgresql://" not in message
