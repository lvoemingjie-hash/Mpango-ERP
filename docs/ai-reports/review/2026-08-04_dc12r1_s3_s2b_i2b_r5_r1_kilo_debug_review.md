# DC-12R1-S3-S2B-I2B-R5-R1-K1 Independent Adversarial Source Review (Kilo Debug Mode)

## Verdict

`PASS_FOR_CTO_DC12R1_S3_S2B_I2B_R5_R1_KILO_DEBUG_FINAL_REVIEW`

No P0/P1/P2 finding, no STOP condition triggered. Five INFO-grade observations
documented (test-precision and dead-code notes only); none affects the reviewed
runtime's correctness. Verdict permits CTO advancement of the candidate
`c65c87cb0b9fd5a46ed55a2554988e00ebff9764` toward merge decision.

## Reviewer, Role, and Hard-Rule Compliance

Independent adversarial source reviewer in **Kilo Debug Mode** (read-only).
The candidate worktree was never modified; no commit, merge, tag, force-push, or
remote mutation was performed on any branch other than the dedicated report
branch `reports/dc12r1-s3-s2b-i2b-r5-r1-kilo-debug-review-2026-08-04`.

1. Base proof gate passed before any review statement 鈥?PASS
2. Candidate/baseline/report SHAs match the task constants exactly 鈥?PASS
3. Exact 31-file manifest recorded; scope-screened 鈥?PASS
4. Review evidence mapped to file:line on the detached candidate worktree 鈥?PASS
5. Test authenticity reviewed, no skip/xfail/mock-pass/DDL-copy/FLUSHDB 鈥?PASS
6. Matrix A鈥揋 verified against source, tests, and migration contract 鈥?PASS
7. Runtime execution **NOT re-run on the Kilo host** (source review only);
   runtime claims are carried exclusively from the accepted Lubuntu report
   `34220d0fa8901ccaefecf307288a31b048105cbc` 鈥?PASS (documented)
8. No confirmed financial-integrity defect 鈥?confirmed (no STOP condition)

## SHAs Verified (post `git fetch --all --prune`)

| Ref | Expected | Actual | Match |
|---|---|---|---|
| Candidate `origin/codex/dc12r1-s3-s2b-i2b-r5-r1-test-evidence-integrity-2026-08-04` | `c65c87cb0b9fd5a46ed55a2554988e00ebff9764` | `c65c87cb0b9fd5a46ed55a2554988e00ebff9764` | EXACT |
| Baseline `origin/product-dev-recovered` | `76fb345c9054530cb0e6abccf35f0cc1863d2bef` | `76fb345c9054530cb0e6abccf35f0cc1863d2bef` | EXACT |
| Runtime report `origin/reports/dc12r1-s3-s2b-i2b-r5-r1-v1-lubuntu-independent-final-2026-08-04` | `34220d0fa8901ccaefecf307288a31b048105cbc` | `34220d0fa8901ccaefecf307288a31b048105cbc` | EXACT |

Ancestry gate: `git merge-base --is-ancestor 76fb345c c65c87cb` exited 0 鈥?baseline
is a strict ancestor of the candidate. Proof gate PASS, no STOP.

## Scope and Isolation

- Review worktree (detached, read-only): `worktrees/_kilo_dc12r1_s3_s2b_i2b_r5_r1_final_2026-08-04`
- Candidate changed-file manifest: exactly **31 files** (8 ai-ledger docs,
  14 backend product files, 4 backend test files, 5 frontend files). No
  migration other than pre-existing `037_payment_declarations_schema.py`, no
  dependency/lockfile/env/deployment change. Suspicious matches: 0.
- GitNexus index rebuilt against the candidate tip (`_kilo_dc12r1_s3_s2b_i2b_r5_r1_final_2026-08-04`,
  14,539 symbols / 45,235 edges / 300 flows) and used for caller/impact
  verification of all 11 required symbols.
- The candidate commit message `test(i2b-r5-r1): evidence integrity 鈥?sequential
  UUIDs + fail-closed H5 cleanup` matches the observed delta: sequential-UUID
  frontend mock (`DeclarePaymentPage.test.tsx`), H5 prepared-statement-cache
  isolation harness (`test_dc12r1_h5_prepared_statement_cache_isolation.py`),
  rate-limiter exact-key cleanup, and S1/S2 route-allowlist extensions. No
  discrepancy between message and content.

## Findings

All five findings are INFO severity. Zero P0鈥揚2. See the findings CSV
(`2026-08-04_dc12r1_s3_s2b_i2b_r5_r1_kilo_debug_review_findings.csv`) for the
full machine-readable records.

### FIND-01 (INFO): `test_unrelated_integrityerror_not_reclassified_as_409` never reaches the DB

- File/line: `backend/tests/test_dc12r1_s3_s2b_i2b_payment_declarations.py:1363-1389`
- The test submits `method: "invalid_method"` and asserts the response is not
  409. However `PaymentDeclarationService.submit_declaration` rejects the method
  at `backend/services/payment_declaration_service.py:92-97`
  (`DECLARATION_METHOD_INVALID`, 400) **before any SQL**. The request never
  triggers an IntegrityError, so the test cannot detect a regression in the
  `_extract_constraint_name` / reclassification path
  (`backend/api/v1/client/orders.py:398-426`, `:511-549`).
- Impact: coverage gap only. The shipped reclassification logic is correct
  (exact-name match on `ux_payment_declarations_retailer_idem`, which equals
  the constraint created by `037_payment_declarations_schema.py:77`; unrelated
  constraints re-raise; `raise` propagates to the structured exception
  boundary). No product defect.
- Recommendation: replace with a genuine IntegrityError trigger (e.g. seed a
  conflicting row with a foreign key violation, or call the repository layer
  directly) so the 409-reclassification boundary is actually exercised.

### FIND-02 (INFO): Name/assertion mismatch in `test_malformed_replay_receipt_returns_409`

- File/line: `backend/tests/test_dc12r1_s3_s2b_i2b_payment_declarations.py:1267-1303`
- The test name requires a controlled 409, but the assertion is
  `assert r.status_code in (HTTPStatus.OK, HTTPStatus.CONFLICT)` (line 1303).
  The reviewed code fails closed with 409
  `DECLARATION_CONFIRMATION_KEY_CONFLICT` (`payment_declaration_service.py:350-356`),
  so current behavior is correct 鈥?but the loose assertion would mask a future
  regression that returns 200 for a confirmed declaration whose linked payment
  lacks a valid receipt.
- Recommendation: narrow to `assert r.status_code == HTTPStatus.CONFLICT` plus
  the exact error code.

### FIND-03 (INFO): Receipt format not pinned by runtime assertions

- File/line: `backend/tests/test_dc12r1_s3_s2b_i2b_payment_declarations.py:750, 780, 1464`
- Runtime tests assert only `receipt_number.startswith("RCT-")`. The exact
  contract `^RCT-[0-9]{8}-[0-9]{6}$` is enforced in source
  (`canonical_payment_service.py:62`) and the 000001 start / per-day reset is
  enforced by `receipt_sequences.next_seq DEFAULT 1`
  (`037_payment_declarations_schema.py:713`) and the atomic UPSERT allocator
  (`payment_repository.py:336-363`). Code is correct; tests under-specify.
- Recommendation: assert the full `RCT-YYYYMMDD-NNNNNN` shape and first
  allocation `000001` in the confirmation tests.

### FIND-04 (INFO): Frontend success-path response handling not asserted

- File/line: `frontend/src/tests/DeclarePaymentPage.test.tsx:73`
- `submitDeclaration` is mocked with `mockResolvedValue({} as never)`. The
  tests prove the idempotency-key lifecycle (no rotation on failure, rotation
  on success), the in-flight mutex, single navigation, and storage
  non-touch 鈥?but not how the component processes a successful response body
  (`res.data.status`/`receipt_number`) before navigating.
- Recommendation: resolve the mock with a minimal shaped `ApiResponse` for the
  success-path tests.

### FIND-05 (INFO): Unreachable `else` branch in the declare route

- File/line: `backend/api/v1/client/orders.py:546-549`
- After `if existing is None: raise` (527-529) the subsequent
  `if existing is not None:` block's `else: raise` is dead code. No behavioral
  impact; purely a readability note.
- Recommendation: collapse the nested condition.

## Matrix A 鈥?Submission (`POST /client/orders/{order_id}/declare`)

| Check | Result |
|---|---|
| A1. Retailer/wholesaler ids server-derived from JWT claims only (`resolve_client_identity`; `dependencies.py`) | PASS |
| A2. No request field selects another retailer/supplier; order bound to (retailer, wholesaler) before write (`payment_declaration_service.py:120-130`) | PASS |
| A3. Deleted/inactive order fails closed with neutral 404 (`payment_declaration_service.py:391-410`) | PASS |
| A4. Amount validated before any SQL 鈥?NaN/Inf/zero/negative 鈫?400 `INVALID_DECLARED_AMOUNT` (`payment_declaration_service.py:53-56,85-90`) | PASS |
| A5. Transfer reference validated: required for transfer, trimmed, 鈮?28, NULL for cash (`payment_declaration_service.py:100-118`) | PASS |
| A6. Reserved `decl-confirm-` namespace rejected at both boundaries 鈫?400 `RESERVED_IDEMPOTENCY_KEY` (`api/v1/orders.py:110-115`, `api/v1/client/orders.py:448-452`) | PASS |
| A7. 201 create / 200 replay / 409 conflict semantics (`api/v1/client/orders.py:563-564`; replay vs payload-mismatch in service) | PASS |
| A8. Concurrent duplicate unique conflict 鈫?constraint-name traversal (no message parsing), replay or exact 409; never faked (`api/v1/client/orders.py:511-549`) | PASS |
| A9. IntegrityError boundaries: rollback + tenant search-path restore first; unrelated FK/CHECK/UNIQUE re-raised (`api/v1/client/orders.py:511-521`; `_restore_tenant_search_path_after_rollback`) | PASS |

## Matrix B 鈥?Confirm (`POST /declarations/{id}/confirm`)

| Check | Result |
|---|---|
| B1. Permission `payments:confirm_declaration`; retailer_operator provably 403 (I2B `test_retailer_operator_lacks_confirm_permission`) | PASS |
| B2. Ownership inside the row lock: `get_for_update_by_wholesaler` + order/binding check with `FOR UPDATE`; cross-wholesaler neutral 404 (`payment_declaration_service.py:177-204,307-321`; I2B S7 test) | PASS |
| B3. Pending-only; confirmed 鈫?replay, rejected 鈫?409 `DECLARATION_NOT_PENDING` (`payment_declaration_service.py:187-196`) | PASS |
| B4. Exact `CanonicalPaymentService.confirm_payment` contract: `skip_prechecks=False, force_completed=True, allocate_receipt=True`, canonical key `decl-confirm-{declaration_id.hex}` (`payment_declaration_service.py:207-221`) | PASS |
| B5. Single caller-owned transaction; service never commits/rolls back (`canonical_payment_service.py` has no commit/rollback; I2A commit-guard test raises on both) | PASS |
| B6. Fail-closed rowcount/state handling: post-mutation dual-key re-read (`payment_declaration_service.py:223-234`); replay fails closed on missing/malformed receipt link 鈫?409 `DECLARATION_CONFIRMATION_KEY_CONFLICT` (`:335-381`) | PASS |
| B7. Overpayment 鈫?400 `PAYMENT_EXCEEDS_REMAINING`, zero residue (canonical `:266-272`; I2B snapshot tests) | PASS |
| B8. Replay returns same payment + receipt with zero writes (canonical `_replay_result`; I2B S7 replay test) | PASS |
| B9. Malformed replay receipt 鈫?controlled 409, never reused (`canonical_payment_service.py:82-88` `_enforce_receipt_on_replay`; I2B S7 test) | PASS |

## Matrix C 鈥?Receipt allocation

| Check | Result |
|---|---|
| C1. Format `RCT-YYYYMMDD-NNNNNN` (`canonical_payment_service.py:62`; repository `payment_repository.py:363`) | PASS |
| C2. Starts at 000001 per business date (`037_payment_declarations_schema.py:713` DEFAULT 1; UPSERT insert branch `payment_repository.py:353-354`) | PASS |
| C3. Atomic unique allocation: single `INSERT 鈥?ON CONFLICT DO UPDATE 鈥?RETURNING` in the caller transaction | PASS |
| C4. Failed confirmation does not consume a receipt 鈥?increment rolls back with the transaction; proven by I2B `test_rollback_leaves_sequence_transactionally_reusable` | PASS |
| C5. `pay_order` unchanged: `allocate_receipt` defaults False; I2A parity (11 original + 7 R3 tests) green on Lubuntu | PASS |
| C6. UTC business date, consistent with migration 037 (`datetime.now(timezone.utc).strftime("%Y%m%d")`; schema `character(8)` PK) | PASS |

## Matrix D 鈥?Reject (`POST /declarations/{id}/reject`)

| Check | Result |
|---|---|
| D1. Permission `payments:confirm_declaration`; retailer 403 (I2B test) | PASS |
| D2. Ownership-scoped lookup `get_for_update_by_wholesaler` (never any other tenant's row) | PASS |
| D3. Terminal-only: non-pending 鈫?409 `DECLARATION_NOT_PENDING` (service `:258-264`); confirm-after-reject 409 (I2B test) | PASS |
| D4. Zero financial mutation; I2B snapshot-equality tests incl. non-latest rejection (S4) | PASS |
| D5. Reason validation: required, 1鈥?56, HTML-forbidden, route-validated 400 `INVALID_REJECTION_REASON` (`api/v1/declarations.py:222-242`; I2B missing/oversized/HTML tests) | PASS |
| D6. Version isolation: row lock + post-write dual-key re-read (`payment_declaration_service.py:266-276`) | PASS |

## Matrix E 鈥?Tenant isolation and information leaks

| Check | Result |
|---|---|
| E1. Wholesaler list/get scoped via `_tenant_wholesaler_id(token)` (`api/v1/declarations.py:71-108,120-148`) | PASS |
| E2. Client list/get scoped via JWT retailer claims; cross-wholesaler confirm 鈫?neutral 404 `DECLARATION_NOT_FOUND` (I2B S7 test) | PASS |
| E3. `ClientDeclarationView` omits internal cashier user ids and payment row id (`schemas/declaration.py:84-104`) | PASS |
| E4. No request field selects another retailer/supplier anywhere in the declaration flow | PASS |
| E5. Error messages are envelope codes, not internal details; tenant context missing 鈫?neutral 403 (`api/v1/declarations.py:71-83`) | PASS |

## Matrix F 鈥?Frontend

| Check | Result |
|---|---|
| F1. Idempotency key generated once per form mount (`useRef(crypto.randomUUID())`) | PASS |
| F2. Failed retries reuse the same key (I2B frontend test with sequential-UUID mock, false-green guarded) | PASS |
| F3. Success rotates the key (`DeclarePaymentPage.tsx`; frontend test) | PASS |
| F4. In-flight duplicate submit blocked (`submittingRef` mutex; double-submit test 鈫?exactly 1 call) | PASS |
| F5. No key stored in localStorage/sessionStorage/URL (storage-spy test) | PASS |
| F6. Amount input label-associated (`htmlFor="amount"` + `id="amount"`) | PASS |
| F7. Per-row rejection state in `rejectReasons` record; queue re-check scoped per row | PASS |
| F8. No duplicate in-flight confirm/reject: per-row `actionId` disables that row's buttons | PASS |
| F9. Rejection reason/receipt rendered as React-escaped text (no `dangerouslySetInnerHTML`) | PASS |
| F10. Route guards: `/declarations` under `WholesalerRoute`; `/client/declarations` + `/client/orders/:orderId/declare` under `RetailerRoute` (`AppRouter.tsx`) | PASS |

## Matrix G 鈥?Structured errors

| Check | Result |
|---|---|
| G1. All declaration/payment errors are structured `{code, message}` envelopes | PASS |
| G2. JSON-safe sanitization; dict `repr` never leaked (`core/error_codes.py`; `_is_json_safe_value`) | PASS |
| G3. HTML-injection guard on rejection reason (`validate_no_html_tags`, `api/v1/declarations.py:230`) | PASS |
| G4. Neutral 404s for cross-tenant/cross-ownership probes; no existence oracle | PASS |

## Test Authenticity (C-matrix)

- C1. **No skip/xfail/deselect** anywhere in the 7 reviewed suites (grep-verified;
  the single `pass` token is a no-op branch in the H5 URL parser).
- C2. **No FLUSHDB / wildcard Redis cleanup**: I2B rate-limiter cleanup deletes
  only exact derived keys and asserts their absence after cleanup
  (`test_dc12r1_s3_s2b_i2b_payment_declarations.py:75-117`).
- C3. **No broad exception swallowing**: I2B has no bare `except`; H5 cleanup is
  fail-closed with `pg_namespace` residue assertions.
- C4. **No mock-pass**: I2B and H5 use zero result mocks (the only `mock.patch`
  forces the real `JwtAuthStrategy` through the authentic auth path); I2A has
  one route-wiring mock test (`test_route_uses_canonical_payment_service鈥)
  plus genuine real-DB stage-rollback proofs.
- C5. **No copied migration DDL**: I2B parity gate verifies provisioned objects
  via `to_regclass`/`information_schema`; tenants bootstrapped by
  `TenantProvisioningService`.
- C6. **Fail-closed cleanup**: per-test exact-key Redis cleanup with absence
  assertions; per-suite engine dispose; schema drops in `finally` with
  `pg_namespace` assertions.
- C7. **Sequential-UUID evidence integrity (R5)**: frontend mock returns
  distinct sequential UUIDs with an explicit false-green guard test
  (`DeclarePaymentPage.test.tsx:187-195`); fixed-value mock defect removed.
- C8. **Runtime evidence** is carried exclusively from the accepted Lubuntu
  report (3134 full-suite passed, I2B gate passed). Not re-executed on the
  Kilo host (source-only review) 鈥?documented, no claim made to the contrary.

## Quality Gates

| Gate | Command | Result |
|---|---|---|
| Whitespace/EOF | `git diff --check` | PASS |
| Scoped pre-commit | `pre-commit run --files <2 report files>` | PASS |
| Secret scan | pre-commit detect-secrets hook | PASS |
| Mojibake scan | byte-level review of deliverables (UTF-8) | PASS |
| Adversarial self-review | findings re-derived from file:line evidence | PASS |
| Accounting | 5 findings = 5 CSV rows; gap = 0 | PASS |

## Deliverables (on this report branch only)

- `docs/ai-reports/review/2026-08-04_dc12r1_s3_s2b_i2b_r5_r1_kilo_debug_review.md`
- `docs/ai-reports/review/2026-08-04_dc12r1_s3_s2b_i2b_r5_r1_kilo_debug_review_findings.csv`

## Final Verdict

`PASS_FOR_CTO_DC12R1_S3_S2B_I2B_R5_R1_KILO_DEBUG_FINAL_REVIEW`

- Base proof gate: all three SHAs exact, ancestry proven.
- Full candidate delta reviewed against Matrices A鈥揋 on the detached worktree;
  zero P0鈥揚2 findings.
- All 31 changed files accounted for; no scope anomalies; no hidden migration.
- Test suites authentic; R5 evidence-integrity improvement genuine and causal.
- Five INFO observations are non-blocking and carry no financial-integrity risk.
