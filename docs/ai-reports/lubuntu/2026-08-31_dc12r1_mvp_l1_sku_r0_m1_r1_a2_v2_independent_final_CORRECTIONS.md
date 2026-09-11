# CORRECTIONS — DC-12R1-MVP-L1-SKU-R0-M1-R1-A2-V2 Lubuntu Independent Final (report 37448b41)

**Date:** 2026-08-31 | **Applies to:** `reports/dc12r1-mvp-l1-sku-r0-m1-r1-a2-v2-lubuntu-independent-final-2026-08-31` @ `37448b41a122e80deef26490ed2b97d7b55247f8`
**Issued under:** DC-12R1-MVP-L1-SKU-R0-M1-R1-A3 (test-contract and backend-authority closure)

## 1. Evidence-truth corrections

The V2 report's terminal verdict
`STOP_AND_REPORT_CTO_BLOCKED_BY_MISSING_AUTHORITATIVE_SKU_BROWSER_HARNESS`
is retained, but four statements in it require correction so the merge-blocking
picture is not under-stated:

1. **The browser harness is not the sole blocker.** The V2 report's §11 decision
   items did list the 61 STALE_TEST_CONTRACT nodes and the runner transport
   defect, but the verdict token names only the browser harness. The accurate
   statement is: controlled merge of `8cef1fff` was blocked by (a) the missing
   authoritative SKU browser harness AND (b) a full backend authority run that
   was TEST_RED (49 failed, 167 errors) pending test-contract reconciliation AND
   (c) a runner that could not bind a full-suite manifest natively.
2. **The full backend authority result was TEST_RED, not merge-green.** The V2
   report reports the authority run honestly (§6: `RUN_VERDICT=TEST_RED_REAL_COMMAND_NONZERO
   exit=1`, 3678 passed / 49 failed / 167 errors / 48 skipped / 15 xfailed), but
   the PASS-shaped phrasing "passed every executable gate this task owns" in the
   summary overstates it: a zero-red authority result did not exist in V2. The
   reds were classified (0 CURRENT_PRODUCT_DEFECT / 155 ENVIRONMENT_GATED /
   61 STALE_TEST_CONTRACT), which is why the browser-harness STOP was chosen —
   but TEST_RED is TEST_RED until a rerun is green.
3. **The full manifest was not runner-bound.** `AUTHORITY_SKU_M1_BACKEND` could
   not carry the 3803-node manifest: `ET1_RUNNER_REQUIRED_NODES` placed the
   entire node list in ONE environment variable (460,335 bytes; joined length
   measured at candidate), exceeding the kernel per-string exec limit
   `MAX_ARG_STRLEN` (131,072 bytes) — the collect child spawn failed
   `OSError: [Errno 7] Argument list too long` before any launch. The authority
   launch therefore ran with the profile's registered 9-node fixture manifest.
4. **Out-of-band node equality is diagnostic evidence only.** The frozen-manifest
   vs JUnit node-set equality (∅ diff, 3803/3803) that V2 reported alongside the
   authority run was produced OUTSIDE the runner (a /tmp collect + post-hoc set
   diff). It is supporting diagnostic evidence, not a runner-bound
   authorization; it must never be presented as `AUTHORITY_SKU_M1_BACKEND`
   node binding.

## 2. "16 files" vs the 11 files actually enumerated

The V2 report states both "The 61 stale nodes live in 16 files" and then
enumerates **11 files**. Reconciliation: the **16** figure is the number of
red **test-class groupings** in the V2 JUnit (class-level entries across
files); the **11** figure is the number of distinct **files**. Both count the
same 61 nodes. The exact file/node table with 61/61 accounting and gap = 0 is
published in §3 below and per-node in the A3 report Phase 1.

## 3. Exact file/node table (61 nodes, gap = 0)

| # | File (11) | Nodes | Red kinds |
|---|---|---|---|
| 1 | `backend/tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py` | 27 (19 TestRealAlembicUpgradeFailClosed + 8 TestExactCatalogShapeBypass + 1 renamed canonical-upgrade node) | failure ×27 |
| 2 | `backend/tests/test_phase3_pricing.py` | 13 (all `seed_products` fixture setup errors) | error ×13 |
| 3 | `backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py` | 12 (all `_seed_sku` failures) | failure ×12 |
| 4 | `backend/tests/test_u3b2_preview_validate.py` | 2 (TestNoSkuInventoryWrites) | failure ×2 |
| 5 | `backend/tests/test_dc11d_payment_replay_concurrency_integrity.py` | 1 | failure ×1 |
| 6 | `backend/tests/test_dc11t4h_receivable_collection_integrity.py` | 1 | failure ×1 |
| 7 | `backend/tests/test_dc12r1_s3_s2b_i1_financial_schema_foundation.py` | 1 | failure ×1 |
| 8 | `backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py` | 1 | failure ×1 |
| 9 | `backend/tests/test_s5a_fresh_tenant_real_user_journey_gate.py` | 1 | failure ×1 |
| 10 | `backend/tests/test_u6f_onboarding_auth_chain_closeout.py` | 1 | failure ×1 |
| 11 | `backend/tests/test_u6i1_owner_credential_setup_schema.py` | 1 | failure ×1 |
| | **Total** | **61** | **48 failures + 13 errors, gap = 0** |

Class-group accounting (16 groupings → same 61): 19 + 8 + 13 + 4 + 4 + 2 + 2 +
1×8 = 61; 48 + 13 = 61; no node double-counted; gap = 0.

## 4. V2 classification preserved

CURRENT_PRODUCT_DEFECT = 0 stands exactly as the V2 classification. Nothing in
this correction upgrades the V2 result into a merge-readiness claim: the V2
authority run remains TEST_RED; the browser harness remained unauthored; the
closure work is executed separately under A3 and must produce its own fresh,
runner-bound, zero-red authority evidence before any readiness statement.

## 5. Disposition of the correction

This correction is published on the A3 branch
`codexl/dc12r1-mvp-l1-sku-r0-m1-r1-a3-test-authority-closure-2026-08-31`.
The original V2 report branch is historical evidence and is not rewritten.
