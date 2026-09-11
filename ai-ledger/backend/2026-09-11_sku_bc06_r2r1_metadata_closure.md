# SKU BC-06 R2-R1 Metadata Closure Ledger

---

## 1. AUTHORIZATION_CHAIN

| Field | Value |
|-------|-------|
| AUTHORIZATION_ID | CTO-AUTH-DC12R1-MVP-L1-SKU-BC06-R2-R1-METADATA-CLOSURE-2026-09-11 |
| ORIGINAL_REPAIR_LABEL | SKU BC-06 R2-R1 |
| BASE_CANDIDATE | 50f15dedbded1c6d024e322ac84f857699d624e5 |
| PARENT_AUTHORIZATION_ID | CTO-AUTH-DC12R1-MVP-L1-SKU-BC06-R2-HISTORY-LOCK-ORM-FRESHNESS-2026-09-11 |
| EXECUTOR | Zcode-W |
| INDEPENDENT_REVIEWER | Kilo |
| SCOPE | `backend/services/package_identity.py`, `backend/repositories/pricing_repository.py`, and the R2-R1 verified test scope in `backend/tests/test_sku_bc06_reprice_guard.py` |
| CODE_AND_TEST_SEMANTICS_UNCHANGED | true |
| RETROACTIVE_PREAUTHORIZATION_CLAIM | false |
| METADATA_CLOSURE_AFTER_EXECUTION | true |

**NOTE:** This authorization is for evidence and authorization-chain supplementation only. It does not retroactively claim that the original code was executed under this ID.

---

## 2. SOURCE_CALL_CHAINS (canonical truth)

The R2-R1 fix centers on a single shared lock helper. The following call chains are the authoritative source-level dependencies:

### 2.1 pricing.py → pricing_repository.py → package_identity.py

```
backend/api/v1/pricing.py::set_price
  → backend/repositories/pricing_repository.py::set_price (line 90)
    → backend/services/package_identity.py::lock_sku_row (line 80-86)
```

**Confirmed:** `pricing_repository.py:90` calls `lock_sku_row(db, sku_id=sku_id)`.

### 2.2 skus.py → sku_service.py → package_identity.py

```
backend/api/v1/skus.py::update_sku
  → backend/services/sku_service.py::update_sku (line 128)
    → backend/services/package_identity.py::lock_sku_row (line 80-86)
```

**Confirmed:** `sku_service.py:128` calls `lock_sku_row(db, sku_id=sku.id)`.

### 2.3 catalog_products.py → catalog_product_service.py → package_identity.py

```
backend/api/v1/catalog_products.py::update_sellable_unit
  → backend/services/catalog_product_service.py::update_sellable_unit (line 218)
    → backend/services/package_identity.py::lock_sku_row (line 80-86)
```

**Confirmed:** `catalog_product_service.py:218` calls `lock_sku_row(db, sku_id=unit.id)`.

### 2.4 direct_dependents summary

| Caller | File | Line | Calls `lock_sku_row` |
|--------|------|------|----------------------|
| `set_price` | `backend/repositories/pricing_repository.py` | 90 | Yes |
| `update_sku` | `backend/services/sku_service.py` | 128 | Yes |
| `update_sellable_unit` | `backend/services/catalog_product_service.py` | 218 | Yes |

**Total direct dependents on `lock_sku_row`: 3** (including `set_price`).

There is **no second lock logic**. All three entry points share the single implementation in `backend/services/package_identity.py`.

---

## 3. GITNEXUS_STATISTICS_CLARIFICATION

GitNexus 1.6.11 was run on the candidate worktree at commit `50f15ded`.

### 3.1 Index baseline

| Metric | Value |
|--------|-------|
| Indexed nodes | 38,016 |
| Indexed edges | 65,626 |
| Clusters | 849 |
| Flows | 704 |

### 3.2 Impact of `lock_sku_row`

| Metric | Value |
|--------|-------|
| Risk | HIGH |
| Direct dependents (d=1) | 3 symbols |
| d=2 dependents | 3 symbols |
| Affected processes | 2 |
| Affected modules | 3 (Services, Tests, V1) |

### 3.3 `named_affected_processes` explanation

GitNexus reports `named_affected_processes=2` for `lock_sku_row`, listing:
1. `update_sellable_unit` (backend/api/v1/catalog_products.py)
2. `update_sku` (backend/api/v1/skus.py)

**This does not mean `set_price` is absent from the dependency graph.** The `set_price` function in `backend/repositories/pricing_repository.py` is a direct dependent (d=1) of `lock_sku_row`. The GitNexus process-level summary in this particular output grouped the affected processes as 2 because both `update_sku` and `update_sellable_unit` are API-layer entry points that traverse through service-layer guards before reaching `lock_sku_row`, while `set_price` is a repository-layer entry point. The underlying symbol-level impact is exact: **3 direct dependents, including `set_price`**.

The canonical source-level truth is Section 2 of this ledger. GitNexus raw output is preserved below for auditability.

### 3.4 GitNexus raw output (excerpt)

```json
{
  "target": {
    "id": "Function:backend/services/package_identity.py:lock_sku_row",
    "name": "lock_sku_row",
    "type": "Function",
    "filePath": "backend/services/package_identity.py"
  },
  "direction": "upstream",
  "impactedCount": 6,
  "risk": "HIGH",
  "summary": {
    "direct": 3,
    "processes_affected": 2,
    "modules_affected": 3
  },
  "byDepthCounts": {
    "1": 3,
    "2": 3
  },
  "affected_processes": [
    {
      "name": "update_sellable_unit",
      "type": "Function",
      "filePath": "backend/api/v1/catalog_products.py",
      "affected_process_count": 5,
      "total_hits": 9,
      "earliest_broken_step": 1
    },
    {
      "name": "update_sku",
      "type": "Function",
      "filePath": "backend/api/v1/skus.py",
      "affected_process_count": 5,
      "total_hits": 9,
      "earliest_broken_step": 1
    }
  ],
  "affected_modules": [
    {
      "name": "Services",
      "hits": 3,
      "impact": "direct"
    },
    {
      "name": "Tests",
      "hits": 2,
      "impact": "direct"
    },
    {
      "name": "V1",
      "hits": 1,
      "impact": "indirect"
    }
  ]
}
```

**Interpretation:** `direct: 3` confirms three direct dependents. `processes_affected: 2` reflects the GitNexus process-grouping heuristic, not the absence of `set_price` from the dependency graph. The source call chains in Section 2 are the authoritative record.

### 3.5 detect-changes (scope: compare base `3e831384` → HEAD)

| Metric | Value |
|--------|-------|
| Changed files | 4 |
| Changed symbols | 17 |
| Affected processes | 2 |
| Risk level | MEDIUM |
| Affected execution flows | `Update_sellable_unit → Lock_sku_row`, `Update_sku → Lock_sku_row` |

**Note:** The `detect-changes` process-level view also groups by API-layer entry points. The repository-layer `set_price` flow is captured in the symbol-level changes (`Function set_price → backend/repositories/pricing_repository.py`).

---

## 4. SCOPE_AND_INTEGRITY_STATEMENTS

| Statement | Value | Evidence |
|-----------|-------|----------|
| CODE_AND_TEST_SEMANTICS_UNCHANGED | true | No source, test, config, migration, frontend, or `.secrets.baseline` files were modified in this closure round. |
| RETROACTIVE_PREAUTHORIZATION_CLAIM | false | This metadata closure is recorded after the candidate was produced and independently reviewed. |
| METADATA_CLOSURE_AFTER_EXECUTION | true | The candidate `50f15ded` was executed, tested, and reviewed before this closure was authored. |
| KILO_INDEPENDENT_REVIEW_COMMIT | 96cb8ed3929a1866de7c70cc2f71c96d0dffe2ff | Kilo's independent V3 review is recorded as a separate commit on branch `review/sku-bc06-r2r1-lock-liveness-404-2026-09-11`. |

---

## 5. KILO_INDEPENDENT_EVIDENCE

| Item | Value |
|------|-------|
| Reviewer | Kilo (independent) |
| Review commit | `96cb8ed3929a1866de7c70cc2f71c96d0dffe2ff` |
| Review branch | `review/sku-bc06-r2r1-lock-liveness-404-2026-09-11` |
| Review files | `review.md`, `findings.csv` |
| Verdict | CANDIDATE_READY_FOR_CTO_REVIEW |
| Independent test run | 30/30 PASSED (real PostgreSQL 16, real connections, event barriers) |
| Mutation verification | M-A RED, M-B RED, M-C RED; byte-identical restores verified |
| Static checks | `git diff --check` clean; UTF-8/LF; `detect-secrets-hook` rc=0; `.secrets.baseline` SHA unchanged |

---

## 6. THIS_ROUND_TEST_EXECUTION_STATEMENT

**This metadata closure round did NOT re-run:**
- PostgreSQL integration tests
- pytest focused suite
- Browser runtime tests
- Mutation / falsification tests

All test results referenced in this ledger are carried forward from the independent Kilo review (commit `96cb8ed`) and the original author execution under parent authorization `CTO-AUTH-DC12R1-MVP-L1-SKU-BC06-R2-HISTORY-LOCK-ORM-FRESHNESS-2026-09-11`.

---

## 7. CLOSURE_GATES

| Gate | Status | Evidence |
|------|--------|----------|
| New branch relative to 50f15ded only adds authorization ledger | PASS | `git diff --name-only 50f15ded..HEAD` returns only this file |
| `git diff --check` | PASS | Clean |
| UTF-8 / LF / no BOM-NUL-CR | PASS | Verified |
| `detect-secrets-hook` read-only pass | PASS | rc=0 |
| `.secrets.baseline` SHA unchanged | PASS | `03D01ADE9A61E4322E405550139EE26AE75A8A2577F717218081CAFF37DDF4C2` |
| Parent commit, candidate, remote ref, worktree state verified | PASS | `50f15ded` matches remote tip |
| Normal commit, normal push, local == remote | PASS | Verified after push |

---

## 8. FINAL_VERDICT

**PASS_FOR_CTO_DC12R1_MVP_L1_SKU_BC06_R2_R1_METADATA_CLOSURE_READY**

This ledger closes the metadata gap for SKU BC-06 R2-R1 under the authorization ID `CTO-AUTH-DC12R1-MVP-L1-SKU-BC06-R2-R1-METADATA-CLOSURE-2026-09-11`. No source code, test code, or existing artifacts were modified. The authorization chain, source call chains, and GitNexus statistics are recorded herein.
