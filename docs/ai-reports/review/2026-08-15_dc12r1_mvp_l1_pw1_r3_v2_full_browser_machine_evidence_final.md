# DC-12R1 MVP L1 PW1-R3-V2 — Full Browser Machine-Evidence Final (Independent Local Acceptance)

- **Date**: 2026-08-15 (executor: opencode, independent local browser run)
- **Candidate (frozen)**: `2b7b959815a8f2454811303ca1bd13c64c413bb4` (repo HEAD verified unchanged pre/post execution; `git status` clean; no source changes made)
- **Canonical harness**: `d787c58` (byte-identical verification completed in Phase 4; unmodified)
- **Runtime**: fresh isolated stack, task-owned Docker project `pw1r3_runtime_155243` (PG16 :25432 / Redis7 :26379), alembic head `037_payment_declarations_schema`, `t_dev` bootstrap 19 tables, backend 127.0.0.1:8000, frontend 5175
- **Provisioning**: 27 evidence steps, 0 non-ok; canonical identities (W1/W2 wholesale admins, RA dual-tenant retailer_operator, RB single-tenant retailer_operator); setup tokens single-use state verified in PG (0 unused actionable)

## VERDICT

**`STOP_AND_REPORT_CTO`**

29 of 162 browser nodes are red. Per the R3-V2 spec: *"Any red node requires STOP_AND_REPORT_CTO; do not split projects, wait-and-retry, mutate Redis, or reinterpret it as infrastructure."* No retry, splitting, or reinterpretation was performed; both full runs' evidence is published.

## Phase gates

| Phase | Gate | Result |
|---|---|---|
| 1-2 | Lineage + fresh runtime + formal provisioning | PASS (27/0) |
| 3 | HTTP pre-gates (200s; anon 401 `X-RateLimit-Limit=100`; contextual `/auth/me` 200 `Limit=1000/Remaining=999`; `tenant_id`+`tenant_schema`+46 permissions; no tokens recorded) | PASS |
| 3 | Auth matrix (desktop, real JWT) | **9/9 PASS** |
| 4 | Harness byte-identical to `d787c58`; `--list` = 162 nodes (desktop/tablet/mobile × 54) | PASS |
| 5 | ONE full Playwright invocation (started `2026-08-15T08:59:23Z`, 207.5s) | **133 passed / 29 failed / 0 skipped / 0 flaky** |
| 6 | Reconciliation | 162 executed / 162 accounted / 0 infra / 29 product-or-harness findings (below) |

## Phase 6 — Reconciliation of the 29 red nodes (5 deterministic classes)

### F1 — Order create 400 `ORDER_VALIDATION_FAILED "Some items cannot be ordered"` (18 nodes)
- Nodes: phase4:45,62,110,155 + phase5:15,96 × 3 projects
- Root cause: `backend/api/v1/client/orders.py` requires `quantity_on_hand >= qty` **and** a `retailer_prices.price` row; the harness journey setup creates only the SKU (`backend/services/sku_service.py` → `ensure_stock_row` qty-0, no price row). Server-side P0 pricing validation (present at baseline).
- Diff proof: `orders.py` / `skus.py` **unchanged** d2e7e44 → 2b7b959 (pre-existing, deterministic harness-vs-product mismatch).
- Backend log: 18 `ORDER_VALIDATION_FAILED` occurrences (matches 18 nodes 1:1).

### F2 — 500 on `GET /client/orders` (W2 context) via `InvalidCachedStatementError` (3 nodes)
- Nodes: phase5:54 × 3 projects (Expected 200, received 500)
- Root cause: asyncpg prepared-statement cache invalidated by tenant `search_path` switching → `asyncpg.exceptions.InvalidCachedStatementError` → SQLAlchemy `NotSupportedError` unhandled → 500. `backend/database/session.py:28` `create_async_engine` does not set `statement_cache_size=0`.
- Repo acknowledges the concern (`backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py`) but runtime config leaves the cache enabled.
- Backend log: `Request failed: NotSupportedError` + full traceback (excerpt in evidence).

### F3 — Malformed token returns 401 `INVALID_TOKEN` vs expected `UNAUTHENTICATED` (3 nodes)
- Nodes: phase5:80 × 3 (`apiGet('/orders', 'not-a-real-token')`; status 401 OK, structured code differs)
- Root cause: candidate auth strategy taxonomy distinguishes malformed-token (`INVALID_TOKEN`) from missing-token (`UNAUTHENTICATED`); harness (d787c58, d2e7e44-era) expects `UNAUTHENTICATED` for both. Product error-code taxonomy change; structured 401, no leak.

### F4 — Strict-mode locator resolves 2 elements on login page (3 nodes)
- Nodes: phase1:42 × 3
- Root cause: `locator('button[type="submit"], form')` matches both the form and its submit button under Playwright 1.62.1 strict mode. Harness-side defect; identical failure present in the R2 baseline run.

### F5 — Mobile (390px) horizontal overflow, wholesaler dashboard/orders (2 nodes)
- Nodes: phase6:17 (374px), phase6:25 (346px) — mobile project only
- Root cause: candidate frontend layout exceeds viewport on mobile breakpoints.

## Execution-integrity note

Run #1 (superseded, evidence retained in `superseded_run1/`) recorded 130/32; 3 of its failures (phase5:43 × 3) were **task-induced** — provisioning had used non-canonical display names ("PW1R3 Retailer A") vs harness-hardcoded `'PW1R1 Retailer A'`. Provisioning was corrected to canonical names on a **fresh** stack and the authoritative run #2 executed: those 3 nodes now PASS; the remaining 29 failures are all candidate-product or canonical-harness findings, none task-attributable. Task-side corrections were limited to environment/naming only (shared `.env` SECRET_KEY loading; canonical identity names); zero source changes to candidate or harness.

## Historical baselines (no green precedent exists)

- R1: `STOP_AND_REPORT_CTO_WITH_REPRODUCIBLE_PRODUCT_DEFECT` (workspace-selector defect PW1R1-D1); junit shows phase tests blocked at auth gate (9 ran, 2 failed).
- R2 (invalidated): 162 cases, 82 unexpected, 56 non-429 failures **including the same deterministic classes** (strict locator, "Some items cannot be ordered", …) plus auth-cascade failures.
- No historical 162/162 green run exists to reconcile against; R3-V2 was the first run to reach the full node set with a green auth gate (9/9).

## Evidence manifest (SHA256 first 16 hex)

```
FAB929C0B3518C6C  auth_matrix_desktop_pre_gate.json
9EDF51B5575E5F58  auth_matrix_desktop_pre_gate_junit.xml
7B1DB8D69588EB7D  backend_log_excerpt_final_run.txt
2F8A2E796C1B64FA  final_run_failure_details.txt
9E781D0E09CB47FE  pw1r3_v2_full_browser_final.json
33B6F7F5769EF87D  pw1r3_v2_full_browser_final_junit.xml
9FDD38102D879607  pw1r3_v2_run_console_final.txt
11F8CFDB431D3355  test_list_pre_run.txt
C56FC3932AAD739D  superseded_run1/pw1r3_v2_full_browser.json
74C96A3437B2F55A  superseded_run1/pw1r3_v2_full_browser_junit.xml
4F0A22339A0F1D45  superseded_run1/pw1r3_v2_run_console.txt
```

All evidence lives in `docs/ai-reports/review/2026-08-15_pw1-r3-v2-full-browser-evidence/`. No token values, credentials, or secrets are recorded in any evidence file (scanned pre-commit). Playwright traces (which contain network headers) were deliberately excluded.
