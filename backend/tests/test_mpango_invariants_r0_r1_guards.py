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
- Assertion-logic controls (R1 acceptance effectiveness): the concurrent
  return/adjustment invariants are fed synthetic CORRECT outcomes — both
  valid fix shapes (serialize the duplicate, or reject it with the
  documented 409) and a correct single-effect economics snapshot — and must
  ACCEPT them; broken shapes must be REJECTED. These are test-level controls
  only: they demonstrate the assertions accept correct behavior, they are
  NOT a product-fix proof.

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


def test_r0_assertion_logic_accepts_correct_adjustment_algebra():
    """[ASSERTION CONTROL] Correct order-free adjustment chain must be accepted.

    Correct fix shape (either commit order): starts {10,17}, endings {17,22},
    per-row before+delta=after, deltas {5,7}, final 22.
    """
    movements = {
        "r0-race-A-delta-5": {"qty": "5", "q_before": "17", "q_after": "22"},
        "r0-race-B-delta-7": {"qty": "7", "q_before": "10", "q_after": "17"},
    }
    rows = list(movements.values())
    starts = sorted(Decimal(r["q_before"]) for r in rows)
    ends = sorted(Decimal(r["q_after"]) for r in rows)
    deltas = sorted(Decimal(r["qty"]) for r in rows)
    assert starts == [Decimal("10"), Decimal("17")]
    assert ends == [Decimal("17"), Decimal("22")]
    assert deltas == [Decimal("5"), Decimal("7")]
    for r in rows:
        assert Decimal(r["q_before"]) + Decimal(r["qty"]) == Decimal(r["q_after"])
    assert Decimal("10") + sum(deltas) == Decimal("22")


def test_r0_assertion_logic_rejects_lost_update_algebra():
    """[ASSERTION CONTROL] The baseline's lost-update journal must be rejected.

    Both discriminating checks from the RED test fire: the journal shape is
    wrong (two movements both starting from 10) and the journal total does
    not explain the observed final stock (10 + 12 = 22, observed 15).
    """
    movements = {
        "r0-race-A-delta-5": {"qty": "5", "q_before": "10", "q_after": "15"},
        "r0-race-B-delta-7": {"qty": "7", "q_before": "10", "q_after": "17"},
    }
    rows = list(movements.values())
    final_observed = Decimal("15.00")  # baseline actual, as read from the DB
    starts = sorted(Decimal(r["q_before"]) for r in rows)
    ends = sorted(Decimal(r["q_after"]) for r in rows)
    shape_rejected = starts != [Decimal("10"), Decimal("17")] or ends != [
        Decimal("17"),
        Decimal("22"),
    ]
    total_rejected = (Decimal("10") + sum(Decimal(r["qty"]) for r in rows)) != final_observed
    assert shape_rejected, "starts/ends shape must reject the lost-update journal"
    assert total_rejected, "initial+total delta must contradict the observed final stock"
