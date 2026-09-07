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
- Assertion-logic controls (R1 acceptance effectiveness; R2 per CTO F2):
  the concurrent return invariants are fed synthetic CORRECT outcomes —
  both valid fix shapes (serialize the duplicate, or reject it with the
  documented 409) and a correct single-effect economics snapshot — and must
  ACCEPT them; broken shapes must be REJECTED. The adjustment invariant is
  validated through the REAL shared assert_adjustment_chain helper (the same
  function the concurrent RED test runs against database rows): legal
  B→A and A→A→… serial orders accepted (B→A: 10→17→22; A→B: 10→15→22);
  duplicate-reason rows, dict-collapsed duplicates, unknown reasons, missing
  movements, wrong finals, wrong single-row algebra and the lost-update
  journal all REJECTED. Test-level controls only — not a product-fix proof.

No product code is imported beyond auth.factory / the guard function; no
database connection is opened.
"""
from __future__ import annotations

from decimal import Decimal

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
    """[ASSERTION CONTROL] (CTO F2 false-green) Three raw rows, A duplicated.

    The CTO diagnostic shape: raw delta sum 17, dict-by-reason would collapse
    this to two rows and wrongly accept. The shared helper must reject on the
    RAW row count before any algebra.
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


def test_r0_assertion_chain_rejects_duplicate_collapsed_to_two():
    """[ASSERTION CONTROL] (CTO F2) Exact diagnostic rows: A(10→15), A(15→20),
    B(20→27). A {reason: row} dict collapses these to A(15→20) + B(20→27) —
    two plausible-looking rows whose deltas still sum with the initial to the
    observed final. The shared helper rejects the collapsed snapshot anyway:
    no row starts at the initial value, so the order-free chain check fails
    (INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA). Feeding the helper the RAW three
    rows instead rejects even earlier on INVARIANT_R0_STOCK_MOVEMENT_SET.
    """
    from tests.mpango_invariants_r0_support import assert_adjustment_chain

    rows = [
        _row(_REASON_A, 5, 10, 15),
        _row(_REASON_A, 5, 15, 20),
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
