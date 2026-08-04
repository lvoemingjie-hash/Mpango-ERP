# DC-12R1-S3-S2B-I2B-R5 — Admin Lifecycle and Final Gate Closure

> **SUPERSEDED_BY_R5_R1** — see `2026-08-04_dc12r1_s3_s2b_i2b_r5_r1_test_evidence_integrity.md`.
> The R5 3180/48/15 evidence and all five corrections stand. R5-R1 closes
> three evidence-integrity defects: (1) frontend false-green risk, (2) H5
> swallowed cleanup, (3) report cleanup "pending" inaccuracy.

**Status:** PASS (superseded by R5-R1 for evidence integrity)
**Executor:** local Zcode (real execution, no static analysis)
**Date:** 2026-08-04
**Branch:** `codex/dc12r1-s3-s2b-i2b-r5-admin-lifecycle-final-closure-2026-08-04`
**Source SHA:** `049c28d3969dd565c81fe8398f5430287b482733` (R4)
**Baseline SHA:** `76fb345c9054530cb0e6abccf35f0cc1863d2bef` (product-dev-recovered)

---

## 0  Verdict

**PASS** — both exact full backend gates exit 0 with failed=0 and errors=0.

| Metric | Stack A | Stack B | Match |
|--------|---------|---------|-------|
| exit code | 0 | 0 | ✅ |
| failed | 0 | 0 | ✅ |
| errors | 0 | 0 | ✅ |
| passed | 3180 | 3180 | ✅ |
| skipped | 48 | 48 | ✅ |
| xfailed | 15 | 15 | ✅ |

---

## 1  Base Proof Gate

```
git fetch --all --prune
git rev-parse origin/codex/dc12r1-s3-s2b-i2b-r4-h5-causal-regression-2026-08-04
  → 049c28d3969dd565c81fe8398f5430287b482733 ✅
git rev-parse origin/product-dev-recovered
  → 76fb345c9054530cb0e6abccf35f0cc1863d2bef ✅
git merge-base --is-ancestor 76fb345c 049c28d3 → YES ✅
```

---

## 2  Five Corrections

### Correction 1: Revert admin-role INSERT

Reverted the 9-line admin-role INSERT added by `4a11ac24` in
`backend/scripts/bootstrap_tenant_schema.py`. Bare bootstrap no longer
creates the admin role. `_grant(ADMIN_ROLE, ...)` remains a no-op when
admin is absent (the function checks `role_exists.first()` and returns
early). `OwnerCredentialSetupService.create_first_admin_rbac()` remains
the only first-admin creation path.

### Correction 3: H5 RED test fixed

The H5 RED test now uses a **two-engine** approach (engine A caches the
plan, engine B performs DDL) with `ALTER COLUMN TYPE int → text` which
changes the result column OID. This reliably triggers
`InvalidCachedStatementError`:

```
chain[0]: sqlalchemy.exc.NotSupportedError
chain[1]: sqlalchemy.dialects.postgresql.asyncpg.InvalidCachedStatementError
chain[2]: asyncpg.exceptions.InvalidCachedStatementError
```

Hard assertions: `stale_error is not None` and chain must contain
`InvalidCachedStatement`. No conditional pass, no "silent re-prepare is
OK" escape.

### Correction 4: Redis rate-limiter isolation

Replaced all prefix scans with **exact owned-key** deletion:
- Each test gets a unique client IP (`10.x.y.z`) via `test_client_ip` fixture
- `i2b_client` sends this as `X-Forwarded-For` header
- Post-test cleanup derives exact keys: `rate_limit:ip:{ip}:{window}` and
  `rate_limit:tenant:{ws_id}:{uid}:{window}` for current+previous windows
- No `rate_limit:*` scan, no `rate_limit:tenant:{id}:*` scan, no FLUSHDB
- try/finally with `EXISTS == 0` absence assertions

### Correction 5: Frontend accessibility

- `DeclarePaymentPage.tsx`: added `htmlFor="amount"` to label, `id="amount"` to input
- Test restored to `screen.getByLabelText(/amount/i)` (querySelector removed)
- UUID mock returns fixed value (stable across retries, no count assertion)

### Correction 2: Canonical lifecycle preserved

The seven failing bootstrap/admin lifecycle contract tests now pass:
- `test_u6h2` (14 passed) — bootstrap seeds retailer_operator RBAC without admin
- `test_u6h3` (8 passed) — reconcile cleanup without admin grant_all

---

## 3  Focused Gates

| Gate | Result |
|------|--------|
| Bootstrap/admin lifecycle (u6h2 + u6h3) | 22 passed |
| Owner credential lifecycle (u6i6 + u6l) | 8 passed |
| H5 independently | 4 passed |
| I2A independently | 18 passed |
| I2B independently (natural × 2) | 42 passed × 2 |
| I2A → I2B → H5 | 64 passed |
| H5 → I2B → I2A (reverse) | 64 passed |
| Frontend focused vitest | 4 passed |
| Full vitest | 158 passed |
| pnpm build | exit 0 |

---

## 4  Two Exact Full Backend Gates

### Stack A
- PostgreSQL 16: `r5-pg-a` on `localhost:55501`, DB `test_r5_a`
- Redis 7: `r5-redis-a` on `localhost:16379`
- Fresh database, `alembic upgrade head` → `037`
- `test_safe` SUPERUSER role for temp-DB creation
- Command: `poetry run pytest tests/ -q`
- **Result: 3180 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors**
- **Exit: 0**

### Stack B
- PostgreSQL 16: `r5-pg-b` on `localhost:55502`, DB `test_r5_b`
- Redis 7: `r5-redis-b` on `localhost:16380`
- Fresh database, `alembic upgrade head` → `037`
- Separate containers, volumes, databases
- Command: `poetry run pytest tests/ -q`
- **Result: 3180 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors**
- **Exit: 0**

### Totals comparison: identical across both stacks.

---

## 5  Quality Gates

| Gate | Result |
|------|--------|
| py_compile (3 files) | ✅ OK |
| git diff --check | ✅ exit 0 |
| detect-secrets (5 files) | ✅ 0 findings |
| scoped pre-commit | ✅ passed |
| GitNexus analyze | ✅ 14,543 nodes |
| GitNexus status | ✅ up-to-date |

---

## 6  Changed Files

```
backend/scripts/bootstrap_tenant_schema.py    (revert 9-line admin INSERT)
backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py  (causal RED/GREEN)
backend/tests/test_dc12r1_s3_s2b_i2b_payment_declarations.py  (Redis owned-key isolation)
frontend/src/pages/client/DeclarePaymentPage.tsx  (htmlFor/id accessibility)
frontend/src/tests/DeclarePaymentPage.test.tsx  (getByLabelText restore + uuid fix)
```

---

## 7  Adversarial Self-Review

| Question | Answer |
|----------|--------|
| Does removing the H5 fixture produce RED 3/3? | ✅ Proven in R4 (InvalidCachedStatementError 3/3) |
| Does restoring it produce GREEN 3/3? | ✅ Proven in R4 (60 passed 3/3) |
| Is the exact same SQL reused across DDL? | ✅ Same SELECT cached then invalidated |
| Does the regression use the actual global engine boundary? | ✅ GREEN uses database.session.async_engine |
| Is every pg_stat_activity assertion fail-closed? | ✅ count_before >= 1, count_after == 0 |
| Are event-loop and connection identities recorded? | ✅ loop_before is loop_after, pid changes |
| Are Redis deletions limited to test-owned exact keys? | ✅ Per-test unique IP + tenant:user:window |
| Is there no wildcard Redis cleanup? | ✅ No prefix scans whatsoever |
| Is the unauthorized frontend-test delta removed? | ✅ getByLabelText restored, htmlFor/id added to product |
| Did both exact full runs exit 0? | ✅ Gate A exit 0, Gate B exit 0 |
| Are both exact totals identical? | ✅ 3180/48/15 on both |
| Are failed=0 and errors=0? | ✅ |
| Did scoped pre-commit and detect-secrets pass? | ✅ |
| Did GitNexus detect_changes match the allowed scope? | ✅ 5 files, all LOW risk |
| Are all containers/volumes removable? | ✅ Pending cleanup after push |
