# S3-B Live DB Environment Governance

| Field | Value |
|-------|-------|
| Date | 2026-06-22 |
| Branch | `opencode/s3b-live-db-env-governance-2026-06-22` |
| Base | `origin/product-dev-recovered` @ `3b156242042022f67a0dec135785ca3a28a79c8c` |
| Commit | `908cf5c` |
| Status | MERGE READY - no P0/P1 blockers found |

---

## Objective

Govern the legacy S3-B prepared live DB test so it no longer depends on hardcoded local credentials or Docker/host-specific connection defaults.

The goal is test hygiene, not product behavior change:

- Keep S3-B available as a prepared-live proof when explicitly configured.
- Prevent silent or noisy broad-selector behavior when no live DB is configured.
- Avoid leaking DB URLs in skip/fail output.
- Preserve strict CI behavior when `S3B_REQUIRE_LIVE_DB=1`.

---

## Change Summary

Changed file:

- `backend/tests/test_s3b_fresh_tenant_live_runtime_proof.py`

Behavior changes:

- Removed the hardcoded S3-B DB credential/default URL.
- Resolved live DB URL explicitly from `S3B_LIVE_DB_URL`, `TEST_DATABASE_URL`, then `DATABASE_URL`.
- Normalized plain `postgresql://` URLs to `postgresql+asyncpg://` for async engine use.
- Treated the `tests/conftest.py` Docker-internal fallback URL as unconfigured unless explicitly supplied by `S3B_LIVE_DB_URL`.
- Sanitized unreachable-DB skip/fail messages so they do not print the DB URL.
- Renamed the legacy live endpoint test from `test_inventory_stocks` to `test_stock_list_endpoint` so broad `-k inventory` selectors do not pick up the old prepared-live S3-B test.

No production code changed.

---

## Review Result

Reviewer conclusion:

- No P0/P1 blockers found.
- Fix direction is correct.
- `S3B_REQUIRE_LIVE_DB=1` with no DB URL hard-fails as expected, so the live DB gate cannot silently pass.
- Code is merge-ready.

Only P2 suggestion was to add this ledger file to preserve audit cadence.

---

## Verification Evidence

Targeted S3-B test:

```text
pytest tests/test_s3b_fresh_tenant_live_runtime_proof.py -q -rs
3 passed, 19 skipped
```

Strict live DB gate behavior:

```text
S3B_REQUIRE_LIVE_DB=1 with no DB URL
Expected result: fail
Actual result: fail
```

S3-B exclusion from broad inventory selector:

```text
pytest tests/test_s3b_fresh_tenant_live_runtime_proof.py -q -k inventory -rs --tb=short
22 deselected / 0 selected
```

Broad inventory selector with environment supplied:

```text
pytest tests -q -k "inventory and not frontend" --tb=short
19 passed, 1178 deselected, 1 xfailed
```

Hygiene checks:

```text
git diff --check
PASS
```

GitNexus:

```text
worktree compare / staged detect_changes
LOW risk, 1 changed file, 0 affected processes
```

---

## Residual Notes

- S3-B remains a prepared-live proof, not the fresh tenant proof. S3-C is still the self-contained fresh tenant gate.
- When a real S3-B prepared-live validation is desired, callers must explicitly configure `S3B_LIVE_DB_URL` or an accepted DB URL env var.
- This branch is intentionally test-governance only and should be reviewed separately from product feature work.
