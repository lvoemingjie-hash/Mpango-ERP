# Gate 6B — DB-Capable Promotion Gate Rerun

| Field | Value |
|---|---|
| **Date** | 2026-05-13 |
| **Gate** | 6B — DB-Capable Promotion Rerun |
| **Operator** | Claude (automated) |
| **Predecessor** | Gate 6 (verdict: `BLOCKED_BY_ENVIRONMENT`) |

---

## 1. Branch & Commit Identifiers

| Item | Value |
|---|---|
| Source branch | `origin/ops/integration-rehearsal-clean-2026-05-08` |
| Candidate commit | `803634b` — `fix(tenant): reconcile retailer prices in bootstrapped schemas` |
| Target branch | `origin/product-dev-recovered` (HEAD: `6a92a29`) |
| Worktree branch | `ops/promotion-exec-6b-2026-05-13` |

## 2. Clean Worktree

| Item | Value |
|---|---|
| Path | `C:\Users\Jeff0\MPANGO ERP\promotion-exec-6b-2026-05-13` |
| Created from | `origin/product-dev-recovered` |
| Initial `git status --short` | Empty (clean) |
| HEAD after creation | `6a92a29dd00459cd9337351989d61cbd6a2e5e94` |

## 3. Merge Result

| Item | Value |
|---|---|
| Command | `git merge --no-ff --no-commit origin/ops/integration-rehearsal-clean-2026-05-08` |
| Conflicts | **None** |
| Files staged | 67 |
| Merge commit created | **No** (stopped before commit as requested) |

## 4. Environment Setup

| Resource | Status | Details |
|---|---|---|
| PostgreSQL | Reachable | Docker container `mpango_postgres` (postgres:15-alpine), port 5432 |
| Redis | Reachable | Docker container `mpango_redis` (redis:7-alpine), port 6379 |
| DATABASE_URL | Set | `postgresql://mpango:MpangoDBV0.1.4@localhost:5432/mpango_erp` |
| REPORTING_USER_PASSWORD | Set | `ReportingPass_staging_2026` |
| SECRET_KEY | Set | Cryptographically secure random key (generated) |
| Poetry deps | Installed | 114 packages installed in fresh venv |

### Database Migration State

| Item | Value |
|---|---|
| Pre-test alembic version | `017_retailer_prices` (recorded) |
| Actual DB schema level | ~021 (drifted: 018-020 changes already applied outside alembic) |
| Action taken | `alembic stamp 021` to reconcile alembic_version with actual state |
| Bootstrap reconciliation | Ran `bootstrap_tenant_schema.py t_dev` — created `t_dev.retailer_prices`, reconciled payments, reporting views |

### Bootstrap reconciliation output

```
[reconcile] t_dev.payments: ensured ix_payments_order_id
[reconcile] t_dev.payments: ensured uq_payments_transaction_id
[reconcile] t_dev.retailer_prices: contract validated, indexes ensured
[reconcile] t_dev: granted schema USAGE to reporting_role
[reconcile] t_dev: created mv_sales_daily
[reconcile] t_dev: ensured idx_mv_sales_daily_u1
[reconcile] t_dev: ensured reporting_role table privileges
[bootstrap] Tenant schema 't_dev' ready (13 tables, reconciled).
```

## 5. Targeted Gate Tests

### Group 1 — Payments Schema Contract

```
poetry run pytest tests/test_payments_schema_contract.py -q --tb=short
```

| Result | Count |
|---|---|
| Passed | 40 |
| Skipped | 0 |
| Failed | 0 |
| Errors | 0 |

**Verdict: PASS** (all 40 tests pass, including live `t_dev` schema contract checks)

### Group 2 — Phase 3 + Phase 4 Pricing

```
poetry run pytest tests/test_phase3_pricing.py tests/test_phase4_pricing_safe_orders.py -q --tb=short
```

| Result | Count |
|---|---|
| Passed | 34 (16 phase3 + 18 phase4) |
| Skipped | 0 |
| Failed | 0 |
| Errors | 0 |

**Verdict: PASS**

### Group 3 — Payments API + Atomicity + Phase 5 Order Payment

```
poetry run pytest tests/test_payments_api.py tests/test_payment_atomicity.py tests/test_phase5_order_payment.py -q --tb=short
```

| Result | Count |
|---|---|
| Passed | 53 |
| Skipped | 0 |
| Failed | 0 |
| Xfailed | 1 |
| Errors | 0 |

**Verdict: PASS** (the 3 `TestRouteLevelOrderPaymentMonkeypatch` failures from Gate 6 are resolved by setting `REPORTING_USER_PASSWORD`)

## 6. Summary

| Check | Result |
|---|---|
| Clean worktree created | Yes |
| Merge conflicts | None |
| Group 1 (schema contract) | 40 passed, 0 skipped |
| Group 2 (pricing) | 34 passed, 0 errors |
| Group 3 (payments/order) | 53 passed, 1 xfailed |
| **Total targeted tests** | **127 passed, 1 xfailed, 0 failed, 0 errors** |
| Merge commit created | **No** |
| Push performed | **No** |
| `resolve_conflict.py` committed | N/A (none used) |

## 7. Gate 6 vs Gate 6B Comparison

| Issue | Gate 6 | Gate 6B |
|---|---|---|
| PostgreSQL reachability | `socket.gaierror` (unreachable) | Reachable via Docker localhost |
| `REPORTING_USER_PASSWORD` | Unset | Set (`ReportingPass_staging_2026`) |
| `t_dev.retailer_prices` | Skipped (no DB) | Created via bootstrap reconciliation |
| Live schema contract tests | 19 skipped | 19 now run and pass |
| Phase3 DB tests | 10 errors | 16 pass (no errors) |
| Route-level payment tests | 3 failed (env) | All pass |

## 8. Verdict

```
READY_FOR_FINAL_PROMOTION_COMMIT
```

### Rationale

- **Merge is clean** — 67 files staged, zero conflicts.
- **127 of 128 targeted tests pass** — the single xfailed test is expected (pre-existing).
- **All Gate 6 environment blockers resolved**: PostgreSQL reachable, `REPORTING_USER_PASSWORD` set, `t_dev` schema reconciled.
- **No code regressions detected**.
- Merge commit not yet created. Push not performed.
