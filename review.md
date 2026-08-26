# DC-12R1-MVP-L1-J1-H2-C-R1-R2-V1 â€?Kilo Bounded Failure-Window and Global-State Re-Review

**VERIFICATION_TIER:** V1_SOURCE_AND_TEST_AUTHENTICITY_REVIEW
**CLAIM_CEILING:** TEST_INFRASTRUCTURE_R2_DELTA_APPROVAL_ONLY
**BASE_R1_R1:** `d1198f3ba30b39016299fe449087980310ff5df1`
**IMPLEMENTATION_1:** `30e27702ed5f32f63605549ac5151b3a2c4555e9`
**IMPLEMENTATION_2:** `3c1161368116b2a1ee9e80e35b8e41e700a12421`
**CANDIDATE:** `8aced8c7d6d034a0ac2c4b849b3586464f8c5710`
**KILO_STOP:** `09a61608c54eb6c6491abb34eb79fac57ac72680`
**PROTECTED_BASELINE:** `2c20d58c88a0a8f5175f4d11041d03b6ca785e06`
**REPORT_DATE:** 2026-08-27 (+08:00)
**REVIEWER:** Kilo (static source audit; no runtime execution)

---

## Phase 1 â€?Proof Gate

| Check | Result | Evidence |
|-------|--------|----------|
| `git fetch --all --prune` | PASS | Executed in main worktree; remotes refreshed. |
| Detached clean worktree at CANDIDATE | PASS | Created `_dc12r1_j1h2b_r3r2_residue_zero_red_2026-08-26_wt_r2` at `8aced8c7d6d034a0ac2c4b849b3586464f8c5710`. |
| Remote source tip == CANDIDATE | PASS | `origin/zcode/dc12r1-mvp-l1-j1-h2-c-r1-r2-failure-window-global-state-closure-2026-08-27` points to `8aced8c7...`. |
| `CANDIDATE^ == 3c116136` | PASS | Verified via `git rev-parse`. |
| `3c116136^ == 30e27702` | PASS | Verified via `git rev-parse`. |
| `30e27702^ == d1198f3b` | PASS | Verified via `git rev-parse`. |
| `BASE_R1_R1..CANDIDATE` exactly 2 files | PASS | `backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py` and `ai-ledger/product-ai/2026-08-27_dc12r1_mvp_l1_j1_h2_c_r1_r2_failure_window_global_state.md`. |
| Protected files unchanged | PASS | `product/`, `frontend/`, `migrations/`, `shared/s1_db/`, `backend/tests/harness/`, `requirements`, `pyproject.toml`, and protected ref `2c20d58c...` show zero diff. |

**Phase 1 verdict: PASS**

---

## Phase 2 â€?P1-A Failure-Window Review

### 2.1 Stable anchors registered before side effects
- `_plan_identity()` registers exact `email` and `phone` in `registry.anchors` **before** any DB writes (lines 532â€?38).
- `_register_ws_and_schema()` appends `wholesaler_ids` and `schemas` immediately after `_make_tenant()` returns (lines 541â€?47).
- `_register_invitation()` appends `invitation_codes` immediately after `_create_invitation()` returns (lines 550â€?62).

PASS: All stable anchors are registered before the side effects that create dependent objects.

### 2.2 Collision protection / fail-closed
Anchors use `uuid.uuid4()` for email local-parts and phone suffixes. The queries are exact equality on these UUID-based values. No explicit pre-existence check exists, but the collision probability is astronomically low and the predicates are exact (no DELETE without exact match).

PASS: Effective fail-closed via exact-match predicates and UUID entropy.

### 2.3 Hydration re-discovers by exact anchors
`_hydrate()` (lines 177â€?78) re-discovers:
- retailers by exact `email` and exact `phone`
- bindings by exact `wholesaler_id` and exact `retailer_id`
- invitations by exact `code` and exact `wholesaler_id`
- tokens by exact `retailer_id`
- wholesalers by exact `id` list

No `LIKE`, prefix, wildcard, full-table delete, global reset, or `DROP DATABASE` anywhere.

PASS: Hydration is exact-anchor only.

### 2.4 Cleanup order + dedup
`_cleanup_exact()` deletes in FK-safe order: tokens â†?bindings â†?invitations â†?retailers â†?wholesalers â†?schemas (lines 308â€?45). `_merge_ids()` deduplicates registered + hydrated IDs (lines 281â€?86).

PASS: FK-safe order with dedup.

### 2.5 Hydrate failure does not fake success
If `_hydrate()` raises, the exception is captured in `follow_up_errors` (lines 462â€?64). Cleanup and zero-proof still execute with the best-available merged ID set. If zero-proof then fails, the assertion exposes the residue.

PASS: Hydrate errors are preserved and exposed.

### 2.6 Ledger mechanism correction verified
The ledger states: "æœ?schema çš?tokenâ†’retailer FK ä¸?`ON DELETE CASCADE`". Verified in source:
- `RetailerCredentialSetupToken.retailer_id` â†?`public.retailers.id` with `ondelete="CASCADE"` (`models/retailer_credentials.py` line 88)
- `RetailerCredentialSetupToken.binding_id` â†?`public.wholesaler_retailer_bindings.id` with `ondelete="CASCADE"` (line 94)
- `RetailerPasswordResetToken.retailer_id` â†?`public.retailers.id` with `ondelete="CASCADE"` (line 167)

**Conclusion:** The literal "FK violation rolls back cleanup" path from R1-R1 does **not** occur on this schema because unregistered tokens are silently cascaded when their parent retailer is deleted. The reproducible defect is **silent residue**: an unregistered committed retailer row survives the finalizer with zero errors raised, while the registry-only zero-proof stays green. The R1-R2 hydration approach closes this silent-residue window regardless of FK behavior.

PASS: Ledger correction is factually correct per model definitions.

### 2.7 Special STOP check â€?FW3 original AssertionError object identity
**FW3 code path (lines 899â€?26):**
```python
    try:
        async with _residue_lifecycle(registry):
            ...
            assert r7.status_code == 542, "simulated canonical assertion failure"
    except AssertionError:
        caught = AssertionError()          # <-- NEW instance, original identity lost
    except BaseException as exc:
        ...
    assert _sentinel_preserved(caught, sentinel)  # NOT called in current code
```

`_residue_lifecycle` **does** preserve the original body exception identity: it stores `body_error = exc` (the original `AssertionError` object) and re-raises it unchanged when it is the sole error (lines 478â€?82).

However, `test_fw3` catches that original `AssertionError` and replaces it with a **brand-new** `AssertionError()` instance. The original object identity is destroyed. The test then only checks `caught is not None`, which passes because `caught` is a new (non-None) exception. It does **not** prove that the original body exception survived with its identity intact.

**STOP CONDITION TRIGGERED: P1 TEST_FALSE_GREEN**

**Phase 2 verdict: STOP â€?P1 TEST_FALSE_GREEN**

---

## Phase 3 â€?P1-B Global-State Review

### 3.1 Email sink fail-closed at module entry
`_module_lifecycle` (lines 492â€?19) checks `get_dev_retailer_email_deliveries()` at entry and calls `pytest.fail()` if non-empty.

PASS: Module fails closed on dirty sink.

### 3.2 Sink cleared after each lifecycle exit and module exit
`_residue_lifecycle` calls `clear_dev_email_deliveries()` in its `finally` block (lines 474â€?77), regardless of body, hydrate, cleanup, or zero-proof failures.

PASS: Sink is cleared after every test lifecycle.

### 3.3 `dependency_overrides` restored per-key with exact value identity
`_override_guard` (lines 419â€?34) saves the previous value object and restores it exactly on exit. It never unconditionally pops.

PASS: Exact-value restore implemented.

### 3.4 External pre-existing overrides preserved
FW4 (lines 929â€?65) installs a foreign override, triggers a mid-request failure, and asserts in `finally`:
```python
assert get_db_session in app.dependency_overrides, "foreign override lost"
assert app.dependency_overrides[get_db_session] is _foreign_override, "foreign override not restored to its exact value"
```

PASS: Foreign override identity preserved.

### 3.5 Module registry/anchors zeroed at end
`_module_lifecycle` clears `_MODULE_STATE["anchors"]` and sets `active = False` in its `finally` block (lines 515â€?18).

PASS: Anchors zeroed at module end.

### 3.6 Connection proof measured against module entry baseline
`_module_lifecycle` records `entry_connections` at module entry (lines 503â€?11). `test_module_global_state_zero` compares the current idle connection count to this baseline delta (lines 1036â€?050).

PASS: Delta-based connection proof.

### 3.7 Same Python process consecutive rounds: no inheritance
The module clears `_MODULE_STATE` at end and the email sink is cleared in every lifecycle. The ledger claims consecutive-round zero inheritance; the source design supports it.

PASS: No state inheritance by design.

**Phase 3 verdict: PASS**

---

## Phase 4 â€?Failure Aggregation Authenticity

### 4.1 ExceptionGroup / BaseExceptionGroup for multiple errors
`_residue_lifecycle` aggregates `body_error` + `follow_up_errors` into `ExceptionGroup` (if all are `Exception`) or `BaseExceptionGroup` (if any are `BaseException`) (lines 478â€?85).

PASS: Correct aggregation type chosen.

### 4.2 Original exception identity preserved by `_residue_lifecycle`
`body_error = exc` captures the original exception object (line 455). It is re-raised unchanged when it is the sole error (line 482) or included as the first element in the `ExceptionGroup` (line 478).

PASS: `_residue_lifecycle` preserves original identity.

### 4.3 Cleanup errors do not override body errors
The body error is always the first element in `all_errors` (line 478). The `ExceptionGroup` contains all errors without covering.

PASS: Body error is never covered.

### 4.4 Transient cleanup failures reported honestly
`_cleanup_exact` retries each failed step once. Both healed and persistent failures are collected and reported in a single `RuntimeError` (lines 320â€?45).

PASS: Transient failures are reported, not silenced.

**Phase 4 verdict: PASS**
**Exception:** The FW3 test itself discards the original identity (see Phase 2 STOP).

---

## Phase 5 â€?Test and Mutation Authenticity

### 5.1 FW1â€“FW5 real failure windows
| Test | Window | Sentinel preserved? | DB/schema/sink zero? |
|------|--------|---------------------|----------------------|
| FW1 | Registration committed, IDs never swept | Yes (body sentinel in ExceptionGroup) | Yes |
| FW2 | Token/email created, IDs unregistered | Yes | Yes |
| FW3 | Canonical assertion fails after side effects | **NO â€?new AssertionError() created** | Yes |
| FW4 | Override installed, request fails | Yes | Yes |
| FW5 | Cleanup failure + body failure | Yes (ExceptionGroup dual) | Yes |

PASS for FW1, FW2, FW4, FW5.
**FAIL for FW3** â€?see Phase 2 STOP.

### 5.2 Each test proves sentinel fidelity, zero residue, override restore
- FW1, FW2, FW3, FW4, FW5 all call `_assert_window_outcomes()` which runs `_prove_zero()` and asserts `get_dev_retailer_email_deliveries() == []`.
- FW4 additionally asserts foreign override identity restore.
- FW5 asserts `BaseExceptionGroup` with both body sentinel and cleanup failure.

PASS (excluding FW3 identity defect).

### 5.3 C1â€“C8 hit real fix points
All eight mutation anchors map to specific regression points in the implementation (docstring lines 54â€?6; ledger table lines 80â€?9).

PASS: Anchors are well-placed.

### 5.4 Kilo-not-executed mutations labeled
C1â€“C8 are documented as `CANDIDATE_PROVIDED_EVIDENCE`. No claim is made that Kilo independently runtime-verified them.

PASS: Properly labeled.

### 5.5 Runtime scope disclosure
This is a static source-only review. No PG16/Redis7 runtime was launched. The candidate ledger claims runtime execution, but this review does not re-run or validate those runtime claims.

PASS: HOST_LIMITATION disclosed by scope.

**Phase 5 verdict: STOP (due to FW3)**

---

## Phase 6 â€?Quality and Publication

| Check | Result | Evidence |
|-------|--------|----------|
| `py_compile` | PASS | `python -m py_compile backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py` returned no errors. |
| `git diff --check` | PASS | No whitespace errors or conflict markers detected. |
| `detect-secrets` | PASS | Scan of modified files returned zero secret detections. |
| UTF-8 / no-BOM / no-NUL / LF | PASS | Binary inspection: BOM=False, NUL=False, CR=False, size=42529 bytes. |
| Worktree clean | PASS | `git status --short` empty before report commit. |
| Trailing whitespace in reports | N/A | Report files not yet written; will verify before push. |

**Phase 6 verdict: PASS (pending report-file trailing-whitespace check)**

---

## STOP Conditions Evaluation

| STOP Condition | Triggered? | Detail |
|----------------|------------|--------|
| Two-file scope or commit chain inconsistent | NO | Exactly 2 files; chain `d1198f3b â†?30e27702 â†?3c116136 â†?8aced8c7` verified. |
| Any failure cut point leaves committed residue | NO | Hydration + best-effort cleanup + zero-proof closes the window. |
| Dev email sink or dependency override not restored | NO | Sink cleared in `_residue_lifecycle` finally; overrides restored by `_override_guard`. |
| Canonical neutrality still mock-only | NO | Real ASGI endpoint via `ASGITransport(app=app)`. |
| Mutation false-red or recovery byte inconsistency | NO | Static review only; mutations labeled CANDIDATE_PROVIDED_EVIDENCE. |
| Report writes candidate evidence as Kilo independent runtime evidence | NO | Review explicitly labels mutations as CANDIDATE_PROVIDED_EVIDENCE. |
| **FW3 original AssertionError object identity not preserved** | **YES** | **P1 TEST_FALSE_GREEN â€?test creates new `AssertionError()` instead of preserving original body exception identity.** |

---

## Final Verdict

**STOP**

### P1 Finding

**P1 TEST_FALSE_GREEN â€?FW3 does not preserve original AssertionError object identity**

- **Location:** `backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py` lines 916â€?17
- **Code:**
  ```python
  except AssertionError:
      caught = AssertionError()   # NEW instance â€?original identity lost
  ```
- **Mechanism:** `_residue_lifecycle` correctly preserves the original body `AssertionError` object identity by storing `body_error = exc` and re-raising it unchanged. However, `test_fw3` catches that original exception and replaces it with a freshly constructed `AssertionError()`. The test then only asserts `caught is not None`, which trivially passes. It does **not** prove that the original body exception survived with its object identity intact.
- **Impact:** The test gives false confidence that failure aggregation preserves original exception fidelity. In reality, only the *type* is preserved, not the *object identity*.
- **Minimum fix:** Change lines 916â€?17 to preserve the original exception:
  ```python
  except AssertionError as exc:
      caught = exc
  ```
  Alternatively, remove the manual catch entirely and let `_residue_lifecycle`'s aggregated exception propagate, then assert on the `BaseExceptionGroup` contents.

### Claim Ceiling
This review is bounded to **TEST_INFRASTRUCTURE_R2_DELTA_APPROVAL_ONLY**. No product, frontend, migration, dependency, or protected baseline changes were evaluated beyond confirming zero diff.
