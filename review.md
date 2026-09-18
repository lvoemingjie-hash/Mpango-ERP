# Kilo Targeted Review — MPANGO-TENANT-BOOTSTRAP-R1-R5-R1-AST-SENTINEL-CLOSURE

**AUTHORIZATION_ID:** CTO-AUTH-TENANT-BOOTSTRAP-R1-R5-R1-KILO-TARGETED-2026-09-18
**EXECUTOR:** FRESH_KILO_CONTEXT_NOT_AUTHOR
**ENVIRONMENT:** WINDOWS_LOCAL_CP936
**VERIFICATION_TIER:** V3_TARGETED_VERIFICATION_TOOL_CLOSURE
**CLAIM_CEILING:** UTF8_SOURCE_READER_AND_LOCAL_F1_CHECKER_REPAIR_ONLY
**FROZEN_BASE:** 4057808df5b0811e3c16cc682d5c1a8337bf64b8
**IMPLEMENTATION:** f440bfc856e021684e0772cb01cf579e938aae1e
**EVIDENCE_COMMIT:** 1e4228f75884620f77047ede8ecf0523179d162d
**REVIEW_TIP:** 47b9c8d46f53f2cbdfbac9e73c2a74cf29465cdf
**SOURCE_REF:** zcode/tenant-bootstrap-r1r5-r1-ast-sentinel-closure-2026-09-17

## 1. Scope and Identity

This review covers **exactly seven paths** changed between FROZEN_BASE and REVIEW_TIP:

1. `backend/tests/test_tenant_bootstrap_db_authority.py`
2. `ai-ledger/product-ai/2026-09-17_zcode_tenant_bootstrap_r1r5_r1_ast_sentinel_closure.md`
3. `ai-ledger/product-ai/evidence/2026-09-17_zcode_tenant_bootstrap_r1r5r1_ast_sentinel/README.md`
4. `ai-ledger/product-ai/evidence/2026-09-17_zcode_tenant_bootstrap_r1r5r1_ast_sentinel/environment.txt`
5. `ai-ledger/product-ai/evidence/2026-09-17_zcode_tenant_bootstrap_r1r5r1_ast_sentinel/impact_analysis.txt`
6. `ai-ledger/product-ai/evidence/2026-09-17_zcode_tenant_bootstrap_r1r5r1_ast_sentinel/old_check_vs_repaired_checker.txt`
7. `ai-ledger/product-ai/evidence/2026-09-17_zcode_tenant_bootstrap_r1r5r1_ast_sentinel/pytest_focused_acceptance.txt`

Successor parent chain verified:
- FROZEN_BASE (4057808d) → IMPLEMENTATION (f440bfc8) → EVIDENCE_COMMIT (1e4228f7) → REVIEW_TIP (47b9c8d4)

## 2. Zero Drift Verification

**Old evidence / logs / scripts / fixtures / baseline:** Zero drift confirmed.
- `backend/scripts/` — ZERO_DRIFT
- `backend/tests/_fixtures/` — ZERO_DRIFT
- `.secrets.baseline` — ZERO_DRIFT
- `ai-ledger/` old content — ZERO_DRIFT

## 3. _candidate_source Blob Invariant

The `_candidate_source` function body is **byte-identical** between FROZEN_BASE and REVIEW_TIP.

```
FROZEN_BASE blob: af0605a9741953145e05addf4ef5edd85abd5d21 (file-level)
REVIEW_TIP blob: 4eea7bb5fe6344a0afba3f6387918129c0555830 (file-level)
```

File-level blob differs because `_helper_node_from_source` and `_assert_helper_reads_only_committed_candidate` were rewritten in R1-R5-R1. The `_candidate_source` function itself is unchanged.

## 4. Helper Function Review

### `_helper_node_from_source`
- Parses source with `ast.parse`
- Finds exactly one `FunctionDef` named `_candidate_source`
- Returns the AST node

### `_assert_helper_reads_only_committed_candidate`
- Inspects real `ast.Call` nodes for `open()` and `builtins.open()`
- Inspects `ast.ExceptHandler` for bare `except:`, `except Exception`, `except BaseException`, and tuples containing them
- Detects the `utf-8` argument on the `.decode()` call; strictness is proven by the behavioral test, not by this bounded checker alone

**Key finding:** The structural checker is **bounded** — it does not prove general dataflow or all indirect reads. This is by design and documented in the docstring.

## 5. _candidate_source Git Capture and UTF-8 Decode

- Uses `subprocess.run` with `capture_output=True`, **no `text=True`**
- Raw bytes captured in `result.stdout`
- Strict decode: `result.stdout.decode("utf-8")` — no `errors` parameter
- Bounded except: `(OSError, subprocess.SubprocessError)`
- Non-zero rc → RuntimeError with stderr decoded as `errors="replace"` (diagnostic only, not source decode)
- Empty stdout → RuntimeError
- Invalid UTF-8 → RuntimeError
- **No working-tree fallback**

## 6. Windows Targeted Pytest Run

**Environment:**
- Python 3.12.10
- PYTHONUTF8=0
- utf8_mode=0
- locale=cp936
- DATABASE_URL / TEST_DATABASE_URL: unreachable loopback
- REDIS_URL: unreachable
- MPANGO_DB_AUTHORITY_MANIFEST / SCENARIO: not set

**Results:**
```
16 passed, 36 deselected in 1.47s
rc=0
No skip / failure / error
```

**16 selected nodeids (case-sensitive):**
1. `tests.test_tenant_bootstrap_db_authority::test_mutation_validator_rejects_two_expected_one_hit`
2. `tests.test_tenant_bootstrap_db_authority::test_mutation_validator_rejects_extra_and_undeclared_reds`
3. `tests.test_tenant_bootstrap_db_authority::test_mutation_validator_rejects_empty_declaration`
4. `tests.test_tenant_bootstrap_db_authority::test_mutation_validator_rejects_named_red_that_never_fired`
5. `tests.test_tenant_bootstrap_db_authority::test_mutation_validator_accepts_exact_and_tolerated_sets`
6. `tests.test_tenant_bootstrap_db_authority::test_formal_gate_declares_its_own_negative_cases_and_they_fail_closed`
7. `tests.test_tenant_bootstrap_db_authority::test_static_formal_gate_uses_the_exact_set_validator`
8. `tests.test_tenant_bootstrap_db_authority::test_mutation_apply_gate_refuses_unparseable_mutation`
9. `tests.test_tenant_bootstrap_db_authority::test_static_every_mutation_is_parseable_and_fully_declared`
10. `tests.test_tenant_bootstrap_db_authority::test_candidate_source_reads_non_ascii_utf8_from_committed_candidate`
11. `tests.test_tenant_bootstrap_db_authority::test_candidate_source_refuses_invalid_utf8`
12. `tests.test_tenant_bootstrap_db_authority::test_candidate_source_refuses_git_failure`
13. `tests.test_tenant_bootstrap_db_authority::test_candidate_source_refuses_empty_output`
14. `tests.test_tenant_bootstrap_db_authority::test_candidate_source_refuses_subprocess_exception`
15. `tests.test_tenant_bootstrap_db_authority::test_static_candidate_source_has_no_working_tree_fallback`
16. `tests.test_tenant_bootstrap_db_authority::test_structural_checker_rejects_injected_file_read_call`

Original 15 nodes retained. One new legitimate injected negative example (`test_structural_checker_rejects_injected_file_read_call`) added.

## 7. Independent Negative Examples and O1 Boundary

All probes use **in-memory source replacement** — no worktree mutation.

| Probe | Result |
|-------|--------|
| Unmodified source accepted | PASS |
| `open()` injection rejected with `AssertionError("calls open()...")` | PASS |
| `builtins.open()` injection rejected with `AssertionError("builtins.open()...")` | PASS |
| Old text-search predicate (`"open(" not in ast.dump(...)`) accepts violating helper | PASS (documented blind spot) |
| Structural checker accepts `errors="replace"` | PASS (O1 confirmed) |
| Real `_candidate_source` refuses invalid UTF-8 | PASS (O1: full behavior test still strict) |

**O1 Assessment (CTO registered, non-blocking):**
- `has_strict_utf8_decode` only verifies the first argument is the constant string `"utf-8"`. It does not exclude `errors=replace`/`ignore`, nor does it track stdout specifically.
- Structural checker alone would accept a memory source changing `result.stdout.decode("utf-8")` to `result.stdout.decode("utf-8", errors="replace")`.
- However, the real behavioral test `test_candidate_source_refuses_invalid_utf8` proves `_candidate_source` still strictly decodes and refuses invalid UTF-8.
- **No current actual regression found.** The bounded limitation is known and does not violate the freeze scope. Retained as O1.

## 8. detect-secrets-hook Verification

- Baseline SHA-256 before scan: `03D01ADE9A61E4322E405550139EE26AE75A8A2577F717218081CAFF37DDF4C2`
- Baseline SHA-256 after scan: `03D01ADE9A61E4322E405550139EE26AE75A8A2577F717218081CAFF37DDF4C2`
- **Baseline unchanged.**
- All seven candidate diff paths scanned clean (exit 0).
- Safe synthetic negative control (AWS key pattern) correctly detected (exit 1).

## 9. git diff --check / UTF-8 / BOM / NUL / Line Endings

- `git diff --check`: clean (no whitespace errors)
- BOM: none
- NUL bytes: none
- Line endings: LF (all seven files)

## 10. Unauthorized Gates

Per task constraints, the following were **NOT RUN**:
- FULL_DB_AUTHORITY_RUNTIME=NOT_RUN
- PG_SCENARIOS=NOT_RUN
- REGRESSION_104=NOT_RUN
- NINE_RUNTIME_MUTATIONS=NOT_RUN
- SKU_ACCEPTANCE=NO

No product symbol edits were made. No merge, deployment, or container changes were performed.

## 11. Material Correction Note (2026-09-18)

This section is appended per CTO directive CTO-AUTH-TENANT-BOOTSTRAP-R1-R5-R1-KILO-REPORT-CORRECTION-2026-09-18.

The original report incorrectly stated that "all bounded conditions satisfied" at the material layer. This claim is withdrawn. The technical result (16-node focused pytest pass, real AST.Call detection, strict UTF-8 decode, zero drift on old evidence/fixtures) is accepted. The material package had the following defects:

- **F-01:** `evidence_manifest.md` listed 40-character Git blob object IDs under "Blob SHA-256 Manifests" instead of actual SHA-256 content hashes.
- **F-02:** `findings.csv` had three rows (`open() injection`, `builtins.open() injection`, `old text predicate`) with only five columns instead of the required six.
- **F-03:** Original evidence artifacts (JUnit XML, O1 verification script) were not included in the report tree.

These material defects do not affect the underlying 16-node pytest result or the technical acceptance of the source-reader repair. They are corrected in this amendment.

## 12. Verdict

**PASS_FOR_CTO_TENANT_BOOTSTRAP_R1R5R1_KILO_TARGETED_REVIEW** (material package corrected)

Technical repair accepted. O1 retained as known bounded limitation.
