# DC-11T0-R2/R3 Deterministic Test Gate

Date: 2026-07-15

Current R3 Verdict: **PASS_DC11T0_R3_DETERMINISTIC_FAILURE_GATE**

R3 reason: the deterministic failure-gate comparator matches the two R2 full
runs on exact FAILED/ERROR totals, node sets, and ledger SHA256. All 97 nodes
are classified with gap zero, and canonical-bootstrap rechecks confirmed zero
current product defects.

R2 historical verdict: **STOP_AND_REPORT_CTO**

Reason: the two valid fresh-infrastructure full backend runs produced identical totals and identical failed/error node sets, but the normalized node-ledger SHA256 values differed. The task requires exact ledger determinism; this is a release-blocking deterministic proof failure.

## R3 Addendum

R3 does not repeat the two full backend suites. It uses the existing R2
full-run artifacts and changes the comparator to gate only on exact FAILED and
ERROR node IDs. PASSED parametrized node-ID drift remains diagnostic evidence.

Changed R3 files:

- Modified `backend/scripts/dc11t0_deterministic_gate.py`
- Added `backend/tests/test_dc11t0_deterministic_gate.py`
- Added `ai-ledger/product-ai/2026-07-15_dc11t0_r3_failure_comparison.json`
- Added `ai-ledger/product-ai/2026-07-15_dc11t0_r3_file_rerun_summary.csv`
- Added `ai-ledger/product-ai/2026-07-15_dc11t0_r3_remaining_node_classification.csv`
- Added `ai-ledger/product-ai/2026-07-15_dc11t0_r3_product_defect_nodes.csv`
- Added `ai-ledger/product-ai/2026-07-15_dc11t0_r3_durable_approval_decision_reproduction.csv`
- Added `ai-ledger/product-ai/2026-07-15_dc11t0_r3_canonical_bootstrap_recheck.csv`

Comparator regression tests:

- `poetry run pytest tests/test_dc11t0_deterministic_gate.py -q`
- Result: `5 passed`

R3 failed/error ledger comparison from R2 artifacts:

| Run | Failed/Error Nodes | Failed/Error Ledger SHA256 | All-Node SHA256 |
| --- | ---: | --- | --- |
| full-run-1 | 97 | `3a348ff648f3765e65a179adbd45c869f10006034669201c896ea11b547472a8` | `5e0e9f053c9c60391ea3d5ad2bcbd1150a84016425113cd3b1791d358e881ba1` |
| full-run-2 | 97 | `3a348ff648f3765e65a179adbd45c869f10006034669201c896ea11b547472a8` | `a74b710105e716b6e18252c98788715490895ce0c1ec5d9e9cdbd170ede38478` |

R3 comparator result:

- Failed/error totals match: yes
- Failed node set match: yes
- Error node set match: yes
- Failed/error ledger SHA256 match: yes
- Gating mismatches: none
- Diagnostic mismatches: `normalized_node_ledger_sha256 differs`

Independent reruns covered every file containing the 97 R2 remaining nodes.
All 24 file reruns had `accounting_gap=0`.

R2 remaining-node status in isolated file reruns:

- Failed: 66
- Errors: 18
- Passed: 13
- Accounting gap: 0

R3 classifications using the required four-category vocabulary:

- `TEST_INFRASTRUCTURE`: 24
- `STALE_TEST_CONTRACT`: 41
- `CURRENT_PRODUCT_DEFECT`: 0
- `ENVIRONMENT_GATED`: 32
- Total: 97
- Accounting gap: 0

Exact classification evidence is in
`ai-ledger/product-ai/2026-07-15_dc11t0_r3_remaining_node_classification.csv`.

### R3 Classification Correction

The first R3 pass overclassified 25 nodes as product defects because isolated
file reruns did not recreate each file's required tenant bootstrap context.
The correction used a fresh PostgreSQL 16 database at Alembic head 034 and ran
the canonical tenant bootstrap before repeating the disputed assertions.

Correction evidence is in
`ai-ledger/product-ai/2026-07-15_dc11t0_r3_canonical_bootstrap_recheck.csv`.
The product-defect CSV is intentionally header-only because no current product
defect remained after the corrected reproduction.

Corrected findings:

- All 13 `t_dev.retailer_prices` nodes passed after canonical `t_dev`
  bootstrap. A bare Alembic database does not provision an unregistered tenant
  schema, so these nodes are `ENVIRONMENT_GATED`.
- Nine reporting object/query/permission assertions passed after canonical
  `t_test` bootstrap and are `TEST_INFRASTRUCTURE` in the bare fixture.
- The materialized-view staleness test reached cleanup and then attempted a
  forbidden ledger DELETE. The immutability trigger correctly rejected it, so
  the cleanup expectation is a `STALE_TEST_CONTRACT`.
- The direct reporting-user connection uses fixed connection components rather
  than the disposable test port consistently; it is `TEST_INFRASTRUCTURE`.
- The U1R1 dashboard smoke logged `tenant_schema=t_dev` while its fixture had
  bootstrapped `t_u1r1_test`. Its override does not replace the dashboard's
  request-state tenant extraction, so it is a `STALE_TEST_CONTRACT`.

DurableApprovalDecision reproduction:

- `tests/test_platform_p21_durable_approval_adapter_implementation.py`: 23 collected, 23 passed, accounting gap 0.
- `tests/test_platform_p21_durable_approval_models.py`: 26 collected, 26 passed, accounting gap 0.
- No DurableApprovalDecision implementation/model failure was reproduced.

Windows portability check:

- The gate subprocess reader now decodes UTF-8 explicitly with replacement for
  invalid bytes, avoiding host-codepage failures before cleanup.
- A fresh Windows disposable gate run passed all five comparator tests and
  removed its PostgreSQL/Redis containers, volumes, and network.

R3 final verdict: **PASS_DC11T0_R3_DETERMINISTIC_FAILURE_GATE**

## R2 Historical Scope

- Source branch reviewed: `origin/opencode/dc11t0-r1-test-infrastructure-2026-07-15`
- Exact source tip verified: `4c7814f3799f11abc0e1c49447d99e6fbdbe2fc5`
- Required ancestor verified: `d0c7c6f1a754d4ea160547e59a6dfec6ce2b451a`
- Working branch: `codex/dc11t0-r2-deterministic-test-gate-2026-07-15`
- Isolated worktree: `/home/ivy/Desktop/dc11t0-r2-worktree`

## Changed Files

- Added `backend/scripts/dc11t0_deterministic_gate.py`
- Added `ai-ledger/product-ai/2026-07-15_dc11t0_r2_deterministic_test_gate.md`
- Added `ai-ledger/product-ai/2026-07-15_dc11t0_r2_changed_files.txt`
- Added `ai-ledger/product-ai/2026-07-15_dc11t0_r2_remaining_nodes.csv`
- Added `ai-ledger/product-ai/2026-07-15_dc11t0_r2_node_ledger_mismatch.csv`
- Removed tracked generated Hypothesis cache files under `backend/.hypothesis/` (353 files)

The path-level manifest is `ai-ledger/product-ai/2026-07-15_dc11t0_r2_changed_files.txt`.

No product routes, services, models, migrations, frontend, or deploy files were edited.

## Preflight

- The five R1 commits from the required ancestor contain only backend test infrastructure/test-file changes plus deletion of two generated Hypothesis cache files.
- R2 removes the remaining tracked generated Hypothesis cache: `git ls-files backend/.hypothesis` returns `0`.
- `poetry install --sync` completed in the isolated worktree-local virtualenv after rerunning with process-local Poetry keyring disabled.
- Runtime used disposable PostgreSQL 16 and Redis 7 containers per run, unique container/volume/network names, explicit `MPANGO_ENV=test`, dev email sink, UTF-8 environment, and no printed DB URLs.
- Alembic health in both valid full runs: single head/current `034_platform_operators`.

## GitNexus

GitNexus was run before changing fixtures/helpers.

- Analyze: `25,530 nodes | 53,687 edges | 832 clusters | 300 flows`
- Impact target: `Function:backend/tests/conftest.py:run_coroutine`
- Impact count: `35`
- Risk: `CRITICAL`
- Direct impacted tests: `33`
- Affected modules: `Tests` 28 hits, `P17` 2 hits, `P15` 2 hits, `P13` 2 hits
- `impact event_loop` and `impact pytest_configure` returned target-not-found, so no impact set was available for those names.

## Static Review

- `run_coroutine()` call sites in `backend/tests`: 35
- `run_coroutine()` calls inside async tests: 0
- Residual `asyncio.run()` calls in `backend/tests`: 2, both standalone helper entry points:
  - `backend/tests/drop_test_schema.py:25`
  - `backend/tests/setup_test_schema.py:204`
- Full test-tree hardcoded scan covered DB URLs, Redis URLs, hostnames, local ports, password words, and SMTP words. Hits were confined to test fixtures, local/disposable defaults, and expected SMTP composition tests; no production credential value was printed or used.

## Gate Script

`backend/scripts/dc11t0_deterministic_gate.py` now provides the repository-owned backend gate:

- `run`: creates fresh PostgreSQL 16 and Redis 7 containers and volumes, validates health, validates Alembic head/current, runs pytest with a node-status ledger plugin, writes summary artifacts, and destroys containers/volumes/networks.
- `compare`: compares two run summaries for totals, failed/error node sets, and normalized node-ledger hash.
- The script redacts DB/Redis URLs and known runtime secrets from captured output.

An initial full-run attempt was invalid because the script's first disposable DB name contained a production-name substring rejected by `tests/test_dc11p1_platform_operator_schema.py`. The script was corrected to use a neutral disposable test DB name, and a targeted DC-11P1 smoke passed before the two valid full runs.

## Full-Run Evidence

| Run | Collected | Passed | Failed | Errors | Skipped | XFailed | Accounting Gap | Ledger SHA256 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| full-run-1 | 2785 | 2657 | 79 | 18 | 16 | 15 | 0 | `5e0e9f053c9c60391ea3d5ad2bcbd1150a84016425113cd3b1791d358e881ba1` |
| full-run-2 | 2785 | 2657 | 79 | 18 | 16 | 15 | 0 | `a74b710105e716b6e18252c98788715490895ce0c1ec5d9e9cdbd170ede38478` |

Both runs reported cleanup complete with no remaining run-prefix containers, volumes, or networks.

Comparator result:

- Totals matched.
- Failed node set matched.
- Error node set matched.
- Normalized node-ledger SHA256 differed.

## Exact Mismatch

Raw node IDs for this mismatch contain large generated XLSX byte payloads and one token-like parameter. To avoid printing binary payloads or token-like values, exact raw node IDs are represented by SHA256 fingerprints in `ai-ledger/product-ai/2026-07-15_dc11t0_r2_node_ledger_mismatch.csv`.

Mismatch shape:

- Run 1 only: 4 passed node IDs
- Run 2 only: 4 passed node IDs
- Status changes among common node IDs: 0

Affected bases:

- `backend/tests/test_u4d_intake_parser_preview.py:121` `test_parser_rejects_csv_and_xlsx_column_limit`
- `backend/tests/test_u4d_intake_parser_preview.py:132` `test_parser_rejects_csv_and_xlsx_header_length`
- `backend/tests/test_u4d_intake_parser_preview.py:143` `test_parser_rejects_csv_and_xlsx_cell_length`
- `backend/tests/test_u6i3_owner_credential_setup_consume.py:249` `test_invalid_or_missing_raw_token_fails_neutrally`

Inference from the ledger diff: parametrized node IDs include generated XLSX bytes and a generated token-like parameter, so exact node IDs differ across otherwise equivalent runs. Because the required normalized node-ledger hashes differ, determinism is not proven.

## Remaining Nodes

Remaining failed/error nodes are recorded in:

- `ai-ledger/product-ai/2026-07-15_dc11t0_r2_remaining_nodes.csv`

Counts:

- Failed: 79
- Errors: 18
- Total remaining failed/error nodes: 97

I did not independently rerun each remaining failed/error file or DurableApprovalDecision candidates after the two-run comparison failed. The task says to stop and report if results differ, so the deterministic mismatch is the controlling failure. These remaining nodes are not classified as product defects in this report.

## R2 Historical Final Verdict

**STOP_AND_REPORT_CTO**
