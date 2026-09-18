"""Independent verification of negative examples and O1 boundary."""
import ast
import sys
import os
from unittest.mock import patch

backend_tests = r"C:\Users\Jeff0\MPANGO ERP\worktrees\kilo_tenant_bootstrap_r1r5r1_review_20260918\backend\tests"
sys.path.insert(0, backend_tests)

from test_tenant_bootstrap_db_authority import (
    _assert_helper_reads_only_committed_candidate,
    _helper_node_from_source,
    _candidate_source,
    _fake_run,
)


def main():
    test_file = os.path.join(backend_tests, "test_tenant_bootstrap_db_authority.py")
    with open(test_file, encoding="utf-8") as f:
        source = f.read()

    # 1. Unmodified source accepted
    _assert_helper_reads_only_committed_candidate(source)
    print("PASS: unmodified source accepted")

    # 2. Legitimate open() injection rejected
    violating = source.replace(
        'return result.stdout.decode("utf-8")',
        'with open(rel_path, encoding="utf-8") as handle:\n            return handle.read()\n        return result.stdout.decode("utf-8")',
        1,
    )
    try:
        _assert_helper_reads_only_committed_candidate(violating)
        print("FAIL: open() injection should be rejected")
        sys.exit(1)
    except AssertionError as e:
        if "calls open()" in str(e):
            print('PASS: open() injection rejected with correct message')
        else:
            print("FAIL: wrong AssertionError message:", e)
            sys.exit(1)

    # 3. builtins.open() injection rejected
    violating2 = source.replace(
        'return result.stdout.decode("utf-8")',
        'import builtins\n        with builtins.open(rel_path, encoding="utf-8") as handle:\n            return handle.read()\n        return result.stdout.decode("utf-8")',
        1,
    )
    try:
        _assert_helper_reads_only_committed_candidate(violating2)
        print("FAIL: builtins.open() injection should be rejected")
        sys.exit(1)
    except AssertionError as e:
        if "builtins.open()" in str(e):
            print('PASS: builtins.open() injection rejected with correct message')
        else:
            print("FAIL: wrong AssertionError message:", e)
            sys.exit(1)

    # 4. Old text predicate accepts violating helper
    violating_helper = _helper_node_from_source(violating)
    old_text_search_predicate_accepts = (
        "open(" not in ast.dump(violating_helper)
        and "except Exception" not in ast.unparse(violating_helper)
    )
    if old_text_search_predicate_accepts:
        print("PASS: old text predicate accepts violating helper (documented blind spot)")
    else:
        print("FAIL: old text predicate should accept violating helper")
        sys.exit(1)

    # 5. O1: has_strict_utf8_decode accepts errors=replace
    degraded = source.replace(
        'result.stdout.decode("utf-8")', 'result.stdout.decode("utf-8", errors="replace")'
    )
    _assert_helper_reads_only_committed_candidate(degraded)
    print("PASS: structural checker accepts errors=replace (O1 confirmed)")

    # 6. But real _candidate_source still refuses invalid UTF-8
    with patch("subprocess.run", _fake_run(b"\xff\xfe not-valid-utf8")):
        try:
            _candidate_source("dummy")
            print("FAIL: _candidate_source should refuse invalid UTF-8")
            sys.exit(1)
        except RuntimeError as e:
            if "not valid UTF-8" in str(e):
                print("PASS: _candidate_source refuses invalid UTF-8 (O1: full behavior test still strict)")
            else:
                print("FAIL: wrong RuntimeError:", e)
                sys.exit(1)

    print("ALL INDEPENDENT CHECKS PASSED")


if __name__ == "__main__":
    main()
