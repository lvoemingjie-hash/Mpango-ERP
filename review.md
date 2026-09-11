# Independent Review: SKU BC-06 R2-R1 — lock_sku_row liveness + set_price fail-closed

**Review Level:** V3
**Candidate:** `50f15dedbded1c6d024e322ac84f857699d624e5`
**Parent:** `3e831384ffd067633b9324deec728b7b1370d739`
**Branch:** `zcode/dc-12r1-mvp-l1-sku-bc06-r2r1-lock-liveness-404-2026-09-11`
**Review Branch:** `review/sku-bc06-r2r1-lock-liveness-404-2026-09-11`
**Reviewer:** Kilo (independent)
**Date:** 2026-09-11

---

## 1. Verification of Candidate Identity

| Check | Result |
|-------|--------|
| Fetched from remote | `origin/zcode/dc-12r1-mvp-l1-sku-bc06-r2r1-lock-liveness-404-2026-09-11` |
| Remote tip | `50f15ded` (matches candidate) |
| Worktree HEAD | `50f15dedbded1c6d024e322ac84f857699d624e5` |
| Worktree status | Clean, detached → branch `review/sku-bc06-r2r1-lock-liveness-404-2026-09-11` |
| Diff `3e831384..50f15ded` | Exactly **4 files** |
| Cumulative R1-R2 diff | NOT substituted for round diff |

### Changed files (exact)

1. `ai-ledger/backend/2026-09-11_sku_bc06_r2r1_lock_liveness_404.md`
2. `backend/repositories/pricing_repository.py`
3. `backend/services/package_identity.py`
4. `backend/tests/test_sku_bc06_reprice_guard.py`

---

## 2. Source Review: `lock_sku_row`

**File:** `backend/services/package_identity.py` (lines 65–86)

```python
async def lock_sku_row(db: AsyncSession, *, sku_id) -> SKU | None:
    result = await db.execute(
        select(SKU)
        .where(SKU.id == sku_id, SKU.is_deleted.is_(False))   # <-- is_deleted=false confirmed
        .execution_options(populate_existing=True)             # <-- populate_existing=True confirmed
        .with_for_update()                                     # <-- FOR UPDATE confirmed
    )
    return result.scalar_one_or_none()
```

**Confirmation:**
- `is_deleted.is_(False)` filter is present in the lock query.
- `FOR UPDATE` is present via `.with_for_update()`.
- `populate_existing=True` is present via `.execution_options(populate_existing=True)`.
- Concurrent soft-delete after the precheck but before lock acquisition causes the query to return `None`; the function returns `None`, never a dead row.

**Verdict:** PASS — query shape and semantics match the R2-R1 contract.

---

## 3. Source Review: Three Entry Points

### 3.1 `update_sku` (`backend/services/sku_service.py`, lines 104–167)

```python
locked = await lock_sku_row(db, sku_id=sku.id)
if locked is None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "SKU_NOT_FOUND", "message": f"SKU '{sku_code}' not found"},
    )
sku = locked
# ... change decision and write from locked instance ...
```

**Confirmation:**
- Uses lock result (`locked`) for change decision.
- On `None`, raises structured 404 (`SKU_NOT_FOUND`).
- Failure path writes nothing: the `raise` occurs before any mutation of `name`, `package_quantity`, `is_active`, etc.

### 3.2 `update_sellable_unit` (`backend/services/catalog_product_service.py`, lines 196–231)

```python
locked = await lock_sku_row(db, sku_id=unit.id)
if locked is None:
    raise HTTPException(status_code=404, detail={"code": "SELLABLE_UNIT_NOT_FOUND", "message": "Sellable unit not found"})
unit = locked
# ... change decision and write from locked instance ...
```

**Confirmation:**
- Uses lock result (`locked`) for change decision.
- On `None`, raises structured 404 (`SELLABLE_UNIT_NOT_FOUND`).
- Failure path writes nothing: the `raise` occurs before any `setattr` or `flush`.

### 3.3 `set_price` (`backend/repositories/pricing_repository.py`, lines 68–124)

```python
locked = await lock_sku_row(db, sku_id=sku_id)
if locked is None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "SKU_NOT_FOUND", "message": f"SKU '{sku_id}' not found"},
    )
# ... only then read existing price and upsert ...
```

**Confirmation:**
- Uses lock result (`locked`) for liveness backstop.
- On `None`, raises structured 404 (`SKU_NOT_FOUND`).
- Failure path writes ZERO price rows: the `raise` occurs before `select(RetailerPrice)` and before `db.add(record)`.

**Verdict:** PASS — all three entry points honor the lock result and fail closed with structured 404, zero business writes on the failure path.

---

## 4. Test Environment & Execution

- **Database:** PostgreSQL 16.15 (Docker container `sku_bc06_r1_pg16` on `127.0.0.1:17755`)
- **Test runner:** `pytest 9.0.3`, `pytest-asyncio 1.3.0`, `SQLAlchemy 2.0.45`, `asyncpg 0.31.0`
- **Focused suite:** `backend/tests/test_sku_bc06_reprice_guard.py`
- **Collected nodes:** exactly **30**
- **Execution:** real PostgreSQL 16, real tenant schemas, real async connections, event barriers (no `sleep`, no mocks)
- **Environment override:** parent `.env` loaded `DATABASE_URL=postgresql://mpango:...@postgres:5432/mpango_erp` via `conftest.py`; tests run with `TEST_DATABASE_URL=postgresql://bc06r1:bc06r1-Tx9vQm4pWn7k@127.0.0.1:17755/test_bc06_backend` to honor the task-specific container

---

## 5. Falsification / Mutation Testing

All mutations were applied to the working tree, relevant tests run, then bytes restored and SHA-256 verified.

| Mutation | Change | Expected | Result | SHA-256 restore |
|----------|--------|----------|--------|-----------------|
| **M-A** | Removed `SKU.is_deleted.is_(False)` from `lock_sku_row` | `test_concurrent_soft_delete_wins_updater_returns_structured_404[sku]`, `[unit]`, `[set_price]` RED | **3 FAILED** | `F294FFF22D2829384644063ECFA1E94ACD879267FEDE48367CA35D7BE2A82FBF` ✓ |
| **M-B** | Removed `if locked is None: raise 404` from `set_price` | `test_set_price_fail_closed_on_missing_or_soft_deleted_sku` RED + concurrent set_price RED | **2 FAILED** | `09AC19D5B234082E340F42076462D6D780BA00586EFA3A6323A919F6D247022F` ✓ |
| **M-C** | Changed reservation query to `status = 'reserved'` only | `test_reservation_status_locks_repackage[released]` RED | **1 FAILED** | `F294FFF22D2829384644063ECFA1E94ACD879267FEDE48367CA35D7BE2A82FBF` ✓ |

After each mutation restore, the full 30-node suite was re-run and passed 30/30.

---

## 6. Scenario Confirmation (Independent Runtime)

| Scenario | Test(s) | Result |
|----------|---------|--------|
| Updater reads active first; deleter commits soft-delete first; all 3 entries return structured 404 + zero writes | `test_concurrent_soft_delete_wins_updater_returns_structured_404[sku]`, `[unit]`, `[set_price]` | 30/30 PASSED |
| Update commits first; soft-delete commits second; both writes persist in explicit linearized order | `test_reverse_linearization_update_wins_then_soft_delete[sku]`, `[unit]` | PASSED |
| Missing SKU and soft-deleted SKU `set_price` both fail-closed with SKU_NOT_FOUND + zero price rows | `test_set_price_fail_closed_on_missing_or_soft_deleted_sku` | PASSED |
| `reserved`, `consumed`, `released` reservations all block repackaging | `test_reservation_status_locks_repackage[reserved]`, `[consumed]`, `[released]` | PASSED |
| R2 locked-fresh ORM reads still pass | `test_locked_fresh_read_after_concurrent_commit[sku]`, `[unit]` | PASSED |

---

## 7. Static Checks

| Check | Command | Result |
|-------|---------|--------|
| `git diff --check` | `git diff --check 3e831384..50f15ded` | Clean (no whitespace errors) |
| UTF-8/LF | Blob inspection of all 4 changed files | All blobs: UTF-8, LF-only (CRLF=0) |
| `detect-secrets-hook` | `detect-secrets-hook --baseline .secrets.baseline` | rc=0, no new secrets |
| `.secrets.baseline` SHA-256 | Before/after hook | `03D01ADE9A61E4322E405550139EE26AE75A8A2577F717218081CAFF37DDF4C2` (unchanged) |

---

## 8. GitNexus Impact / Context

**Analyzed:** 38,016 nodes | 65,626 edges | 849 clusters | 704 flows

### Impact of `lock_sku_row`

- **Risk:** HIGH
- **Direct dependents (d=1):** 3 symbols
- **Affected processes (d=1):** 2
  - `update_sellable_unit` (backend/api/v1/catalog_products.py)
  - `update_sku` (backend/api/v1/skus.py)
- **Affected modules:** Services (direct), Tests (direct), V1 (indirect)
- **Depth breakdown:** d=1: 3 symbols, d=2: 3 symbols

### `detect-changes` (scope: compare base `3e831384` → HEAD)

- **Changed files:** 4
- **Changed symbols:** 17
- **Affected processes:** 2
- **Risk level:** MEDIUM
- **Affected execution flows:**
  - `Update_sellable_unit → Lock_sku_row` (3 steps)
  - `Update_sku → Lock_sku_row` (3 steps)

---

## 9. Required Report Sections

### 9.1 `CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS`

| Test | Nodes | Path Covered |
|------|-------|--------------|
| `test_concurrent_soft_delete_wins_updater_returns_structured_404` | 3 (`sku`, `unit`, `set_price`) | Concurrent soft-delete wins linearization; lock query excludes dead rows; all 3 entry points fail closed with structured 404 + zero writes |
| `test_reverse_linearization_update_wins_then_soft_delete` | 2 (`sku`, `unit`) | Reverse linearization; update commits first, delete second; both writes durable in explicit order |
| `test_set_price_fail_closed_on_missing_or_soft_deleted_sku` | 1 | Missing SKU + soft-deleted SKU both produce SKU_NOT_FOUND + zero price rows |
| `test_reservation_status_locks_repackage` | 3 (`reserved`, `consumed`, `released`) | All three reservation statuses block repackaging (R2 no-exception rule) |

### 9.2 `CODE_PATH_TO_TEST_MATRIX`

| Code Path | Test(s) |
|-----------|---------|
| `lock_sku_row` → `is_deleted=false` + `FOR UPDATE` + `populate_existing=True` | `test_locked_fresh_read_after_concurrent_commit[sku]`, `[unit]` |
| `update_sku` → lock result → structured 404 on `None` | `test_concurrent_soft_delete_wins_updater_returns_structured_404[sku]` |
| `update_sellable_unit` → lock result → structured 404 on `None` | `test_concurrent_soft_delete_wins_updater_returns_structured_404[unit]` |
| `set_price` → lock result → structured 404 on `None` + zero price writes | `test_concurrent_soft_delete_wins_updater_returns_structured_404[set_price]`, `test_set_price_fail_closed_on_missing_or_soft_deleted_sku` |
| `update_sku` / `update_sellable_unit` → reverse linearization durability | `test_reverse_linearization_update_wins_then_soft_delete[sku]`, `[unit]` |
| `has_identity_use_history` → `reserved`/`consumed`/`released` all block | `test_reservation_status_locks_repackage[reserved]`, `[consumed]`, `[released]` |

### 9.3 `NEGATIVE_AND_FAILURE_PATHS`

| Path | Expected Behavior | Verified By |
|------|-------------------|-------------|
| `lock_sku_row` on soft-deleted SKU | Returns `None` | M-A mutation (removing filter) turns concurrent-soft-delete tests RED |
| `update_sku` with `locked is None` | HTTP 404 `SKU_NOT_FOUND`, zero writes | `test_concurrent_soft_delete_wins_updater_returns_structured_404[sku]` |
| `update_sellable_unit` with `locked is None` | HTTP 404 `SELLABLE_UNIT_NOT_FOUND`, zero writes | `test_concurrent_soft_delete_wins_updater_returns_structured_404[unit]` |
| `set_price` with `locked is None` | HTTP 404 `SKU_NOT_FOUND`, zero price rows | `test_concurrent_soft_delete_wins_updater_returns_structured_404[set_price]`, `test_set_price_fail_closed_on_missing_or_soft_deleted_sku` |
| `set_price` on never-existing SKU | HTTP 404 `SKU_NOT_FOUND`, zero price rows | `test_set_price_fail_closed_on_missing_or_soft_deleted_sku` (ghost UUID) |
| `has_identity_use_history` with `released` reservation | Blocks repackaging (no exception) | `test_reservation_status_locks_repackage[released]` |
| M-B: `set_price` ignoring lock result | Zero-price write test RED | Verified by mutation |
| M-C: `released` reservation excluded | Released parametrized test RED | Verified by mutation |

### 9.4 `FALSIFICATION_RESULT`

All three mandated falsifications were executed against the **live candidate bytes** and turned the target nodes RED:

1. **M-A** (remove soft-delete filter): 3 concurrent-soft-delete tests RED
   → Restored, SHA-256 verified byte-identical.
2. **M-B** (ignore `set_price` lock result): 2 zero-price-write tests RED
   → Restored, SHA-256 verified byte-identical.
3. **M-C** (exclude `released` reservation): 1 released-parametrized test RED
   → Restored, SHA-256 verified byte-identical.

Post-restore full suite: **30/30 PASSED**.

### 9.5 `UNCOVERED_NEW_PATHS`

No new uncovered paths were identified in this round. The R2-R1 additions are fully exercised by the 30-node focused suite. The broader `test_sku_bc06_reprice_guard.py` file contains the complete R1+R2 coverage; no paths are left untested within the scope of this candidate.

### 9.6 `FULL_SUITE_RESULT`

```
======================== 30 passed in 74.64s (0:01:14) ========================
```

All 30 collected nodes passed on real PostgreSQL 16 with real connections and event barriers.

### 9.7 `BROWSER_RUNTIME`

Browser runtime is **NOT APPLICABLE** for this backend-only SKU lock-liveness candidate. No frontend or Playwright tests are in scope.

### 9.8 Independent vs. Author Results

| Metric | Author Report | Independent Verification |
|--------|---------------|--------------------------|
| Focused suite | 30 nodes | 30 nodes (exact match) |
| Pass/fail | 30 PASSED | 30 PASSED |
| M-A falsification | RED | RED (3 failed) |
| M-B falsification | RED | RED (2 failed) |
| M-C falsification | RED | RED (1 failed) |
| Post-restore suite | 30 PASSED | 30 PASSED |
| `detect-secrets` baseline | unchanged | `03D01ADE...` unchanged |
| `git diff --check` | clean | clean |

### 9.9 GitNexus Measured Numbers

| Metric | Value |
|--------|-------|
| Indexed nodes | 38,016 |
| Indexed edges | 65,626 |
| Clusters | 849 |
| Flows | 704 |
| Changed files (detect-changes) | 4 |
| Changed symbols (detect-changes) | 17 |
| Affected processes (detect-changes) | 2 |
| `lock_sku_row` risk | HIGH |
| `lock_sku_row` d=1 dependents | 3 |
| `lock_sku_row` affected processes | 2 (`update_sellable_unit`, `update_sku`) |

---

## 10. Final Verdict

**CANDIDATE_READY_FOR_CTO_REVIEW**

The candidate `50f15ded` satisfies all V3 requirements:
- Exact 4-file diff verified against parent `3e831384`.
- `lock_sku_row` correctly excludes soft-deleted rows with `FOR UPDATE` + `populate_existing=True`.
- All three entry points (`update_sku`, `update_sellable_unit`, `set_price`) use the lock result and fail closed with structured 404.
- 30-node focused suite passes on real PostgreSQL 16 with real connections and event barriers.
- All mandated falsifications (M-A, M-B, M-C) turned RED; byte-identical restores verified by SHA-256; post-restore suite 30/30 GREEN.
- Static checks pass: `git diff --check` clean, committed blobs are UTF-8/LF, `detect-secrets-hook` rc=0 with baseline unchanged.
- GitNexus impact: HIGH risk on `lock_sku_row` (3 direct dependents, 2 processes), MEDIUM overall change risk.

**Next step:** CTO decision required. This review does not grant merge or deployment authority.
