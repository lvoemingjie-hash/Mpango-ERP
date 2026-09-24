"""F1/F2 directive: pure classifier tests — no DB, no app. The classify()
function must ONLY accept rc==1 + exactly the named FAILED node + the named
assertion marker + zero errors; any setup/teardown/collection error, wrong
rc or wrong node is VOID/FAIL."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_classify():
    path = Path(__file__).parent / "run_mutations.py"
    spec = importlib.util.spec_from_file_location("osr1_runner", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.classify


NODE = "tests/order_state_r1/test_x.py::test_the_oracle"


def test_clean_failure_is_semantic_red():
    classify = _load_classify()
    out = (f"FAILED {NODE} - AssertionError: CREDIT HOLD face\n"
           "1 failed, 2 passed")
    assert classify(1, out, NODE, "CREDIT HOLD") == "SEMANTIC_RED"


def test_failure_with_setup_error_is_void():
    classify = _load_classify()
    out = ("ERROR at setup of tests/order_state_r1/test_x.py::test_the_oracle\n"
           "AttributeError: something\n"
           f"ERROR tests/order_state_r1/test_x.py::test_the_oracle\n"
           "1 error")
    assert "VOID" in classify(1, out, NODE, "CREDIT HOLD")


def test_failure_with_teardown_error_is_void():
    classify = _load_classify()
    out = (f"FAILED {NODE} - AssertionError: face\n"
           "ERROR at teardown of tests/order_state_r1/test_x.py::other\n"
           "2 warnings, 1 error in 3s")
    assert "VOID" in classify(1, out, NODE, "face")


def test_collection_error_is_void():
    classify = _load_classify()
    out = "ERROR collecting tests/order_state_r1/test_x.py\n4 errors in 1.2s"
    rc4 = classify(4, out, NODE, "x")
    assert rc4.startswith("VOID_COLLECTION") or "VOID" in rc4


def test_realistic_failure_plus_teardown_error_is_void():
    """Actual pytest -q shape: the oracle node FAILS with the expected
    assertion marker AND its teardown errors — the output carries a
    FAILURES section, an ERRORS section header ('ERROR at teardown of'),
    and short-summary lines 'FAILED ...' + 'ERROR ...'. The run must be
    VOID, never SEMANTIC_RED."""
    classify = _load_classify()
    test_name = NODE.split("::")[1]
    out = (
        "=================================== FAILURES "
        "===================================\n"
        f"____________________________ {test_name} "
        "____________________________\n"
        "tests/order_state_r1/test_x.py:42: in test_the_oracle\n"
        "    assert facts == expected, 'face'\n"
        "E   AssertionError: face\n"
        "==================================== ERRORS "
        "====================================\n"
        f"__________ ERROR at teardown of {NODE} __________\n"
        "RuntimeError: pooled connection leaked\n"
        "--------------------------- short test summary info "
        "---------------------------\n"
        f"FAILED {NODE} - AssertionError: face\n"
        f"ERROR {NODE} - RuntimeError: pooled connection leaked\n"
        "1 failed, 1 error in 2.34s\n"
    )
    assert "VOID" in classify(1, out, NODE, "face")


def test_short_summary_error_line_alone_is_void():
    """A short-summary line beginning 'ERROR ' (no FAILED line at all)
    voids the run even at rc==1."""
    classify = _load_classify()
    out = ("--------------------------- short test summary info "
           "---------------------------\n"
           f"ERROR {NODE} - RuntimeError: fixture blew up\n"
           "1 error in 1.00s\n")
    assert classify(1, out, NODE, "face").startswith("VOID")


def test_rc0_is_not_red():
    classify = _load_classify()
    out = "1 passed"
    assert classify(0, out, NODE, "x") == "NOT_RED"


def test_rc2_is_void():
    classify = _load_classify()
    assert "VOID" in classify(2, "usage error", NODE, "x")


def test_wrong_node_is_not_accepted():
    classify = _load_classify()
    out = "FAILED tests/other.py::test_other - AssertionError: face"
    verdict = classify(1, out, NODE, "face")
    assert verdict != "SEMANTIC_RED"


def test_marker_must_be_present():
    classify = _load_classify()
    out = f"FAILED {NODE} - AssertionError: unrelated"
    assert classify(1, out, NODE, "CREDIT HOLD") == "MARKER_MISSING"


# ---------------------------------------------------------------------------
# F3-R1 pure regressions: the F3 oracle attribution helper must convert
# ONLY the exact NULL-identity UUID failure; everything else propagates
# untouched and never gains an OSR1 marker.
# ---------------------------------------------------------------------------

_UUID_NONE_TEXT = "badly formed hexadecimal UUID string"


def _load_oracle_helper():
    from tests.order_state_r1.test_f3_legacy_faces import (
        null_identity_failure_or_raise,
    )
    return null_identity_failure_or_raise


def test_helper_converts_exact_null_identity_valueerror_with_marker():
    helper = _load_oracle_helper()
    err = helper("cancel", "OSR1-F3-LEGACY-RESV-CANCEL-OK",
                 ValueError(_UUID_NONE_TEXT))
    assert isinstance(err, AssertionError)
    assert "OSR1-F3-LEGACY-RESV-CANCEL-OK" in str(err)
    assert "cancel" in str(err)


def test_helper_reraises_valueerror_with_other_text_untouched():
    helper = _load_oracle_helper()
    original = ValueError("invalid literal for int() with base 10: 'x'")
    with pytest.raises(ValueError) as caught:
        helper("fulfill", "OSR1-F3-FULFILL-NULL-409", original)
    assert caught.value is original
    assert "OSR1" not in str(caught.value)


def test_helper_reraises_non_valueerror_untouched():
    helper = _load_oracle_helper()
    boom = RuntimeError("connection reset by peer")
    with pytest.raises(RuntimeError) as caught:
        helper("return", "OSR1-F3-RETURN-NULL-409", boom)
    assert caught.value is boom
    assert "OSR1" not in str(caught.value)


def test_f3_oracle_file_has_no_broad_exception_capture():
    """The P1 fix must hold structurally: no broad handler may reappear
    in the F3 oracle file (a broad catch would let ANY runtime fault
    gain an OSR1 marker and be miscounted as a semantic RED)."""
    src = (Path(__file__).parent / "test_f3_legacy_faces.py").read_text(
        encoding="utf-8")
    assert "except Exception" not in src
    assert "except BaseException" not in src


# ---------------------------------------------------------------------------
# R2-final governance closure: the mutation runner must target the two
# unique product call seams with narrow anchors, contain no git-restore
# code path at all, and never write the authoritative tree even when a
# mutation is interrupted before its restore step.
# ---------------------------------------------------------------------------


def _load_runner_module():
    path = Path(__file__).parent / "run_mutations.py"
    spec = importlib.util.spec_from_file_location("osr1_runner_full", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _product_source() -> str:
    return (Path(__file__).resolve().parents[2] / "services"
            / "order_command_service.py").read_text(encoding="utf-8")


def test_m3_anchor_targets_unique_release_reservations_call():
    """M3's anchor must be the narrow, UNIQUE _release_reservations call
    site — not a multi-statement block that later refactors can break."""
    runner = _load_runner_module()
    m3 = next(x for x in runner.MUTATIONS
              if x.mid == "M3_STALE_CANCEL_RELEASE_DECISION")
    src = _product_source()
    assert src.count(m3.old) == 1, (
        f"M3 anchor must occur exactly once in the product file "
        f"(count={src.count(m3.old)})")
    assert m3.old.startswith(
        "        released = await self._release_reservations(")


def test_m4_anchor_targets_unique_open_credit_hold_call():
    """M4's anchor must be the narrow, UNIQUE _open_credit_hold call
    site — the R2 confirm-path seam the rollback oracle faults on."""
    runner = _load_runner_module()
    m4 = next(x for x in runner.MUTATIONS
              if x.mid == "M4_RESTORE_PRE_COMMIT_NOTIFICATION")
    src = _product_source()
    assert src.count(m4.old) == 1, (
        f"M4 anchor must occur exactly once in the product file "
        f"(count={src.count(m4.old)})")
    assert m4.old.startswith(
        "        credit_reserved = await self._open_credit_hold(")


def test_runner_source_has_no_git_restore_path():
    """The runner must restore mutated bytes ONLY from its in-memory
    backup — no git-restore verb may exist anywhere in the file, so an
    interruption can never be 'fixed' by rewriting the tree from git."""
    src = (Path(__file__).parent / "run_mutations.py").read_text(
        encoding="utf-8")
    assert "checkout" not in src
    assert "git restore" not in src


def test_interrupted_mutation_leaves_authoritative_tree_byte_identical():
    """Simulated interruption: a mutation applied inside the disposable
    detached worktree is never restored — the authoritative product file
    must stay byte-identical throughout, and the disposable copy (left
    dirty on purpose) must be discardable wholesale."""
    runner = _load_runner_module()
    m3 = next(x for x in runner.MUTATIONS
              if x.mid == "M3_STALE_CANCEL_RELEASE_DECISION")
    authoritative = (Path(__file__).resolve().parents[2] / "services"
                     / "order_command_service.py")
    before = authoritative.read_bytes()

    repo_root, backend_dir = runner.make_disposable_worktree()
    try:
        disposable_path = backend_dir / m3.rel_path
        runner.apply_mutation(disposable_path, m3.old, m3.new)
        # interruption: NO restore runs — the disposable copy stays dirty
        assert runner.sha(disposable_path.read_bytes()) != runner.sha(before)
        # the authoritative tree was never a write target
        assert authoritative.read_bytes() == before
        dirt = runner.authoritative_clean()
        assert "services/order_command_service.py" not in dirt, dirt
    finally:
        runner.drop_disposable_worktree(repo_root)
    assert authoritative.read_bytes() == before
