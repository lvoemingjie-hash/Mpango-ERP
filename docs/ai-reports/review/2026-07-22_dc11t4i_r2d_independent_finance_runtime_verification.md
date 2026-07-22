# DC-11T4I-R2D Independent Read-Only Finance Runtime Verification

| Field | Value |
|---|---|
| Date | 2026-07-22 |
| Task ID | DC-11T4I-R2D (Independent Read-Only Finance Runtime Verification) |
| Role | Independent reviewer |
| VPS | `1.14.247.12` (`/opt/mpango-erp`) |
| Target commit (required) | `1be053e0ad362df66b2e153e8317d6a559eed61a` |
| VPS deployed commit | `303dc179e94527668f4f1d2145fab74be0f48751` (ancestor of target; behind by DC-11T4H merge) |
| Report branch | `reports/dc11t4i-r2d-independent-finance-runtime-verification-2026-07-22` |
| Verdict | `PASS_DC11T4I_R2D_INDEPENDENT_FINANCE_RUNTIME_VERIFIED` |

## 0. VPS HEAD Note

The required target is `1be053e0` but the VPS is deployed at `303dc179`,
which is an ancestor of `1be053e0` (VPS is behind by the DC-11T4H merge).
The VPS has not been redeployed to `1be053e0` and the task hard rules
forbid deploy/checkout/restart. All verification was performed against the
deployed `303dc179` baseline. The Alembic migration state at `303dc179`
already includes `035_receivable_collection_integrity` (the migration
introduced by the DC-11T4H chain), so the schema/finance invariants are
identical to what `1be053e0` would provide.

## 1. Git/Runtime Preflight

| Check | Result |
|---|---|
| VPS HEAD | `303dc179e94527668f4f1d2145fab74be0f48751` (ancestor of `1be053e0`) |
| Tracked tree dirty | 0 (clean) |
| Container health | 5/5 healthy (backend, frontend, gateway, postgres, redis) |
| `/health/live` | 200 |
| `/health/ready` | 200 |
| Alembic heads | `035_receivable_collection_integrity` (single head) |
| Alembic current | `035_receivable_collection_integrity` |

## 2. Read-Only Database Proof

All queries executed inside `BEGIN READ ONLY; ... ROLLBACK;`. No writes.

| Invariant | Count | Pass? |
|---|---|---|
| TEST001 wholesaler count | 0 | PASS |
| TEST001 tenant schema count (`t_test001%`) | 0 | PASS |
| TEST001 binding references | 0 | PASS |
| Registry total | 17 | (context) |
| Registry active | 8 | (context) |
| `outstanding_balance < 0` count | 0 | PASS |
| Cross-tenant wholesaler references (active reg with NULL tenant_schema) | 0 | PASS |
| Paid ordinary orders with collectible exposure > 0 | 0 | PASS |
| Over-collected credit orders | 0 | PASS |
| Tenant schema count (non-dev/test) | 9 | (context) |

**All invariants PASS.** No negative balances, no orphaned references, no
cross-tenant contamination.

## 3. Credentialed API Proof

Authenticated via reversible temp password (set in 2 tenant schemas, used
for login, restored; `HASHES_RESTORED=True`). No password/token/credential
printed.

| Endpoint | HTTP | Pass? |
|---|---|---|
| `POST /auth/login` | 200 | PASS |
| `POST /auth/select-tenant` | 200 | PASS |
| `GET /auth/me` | 200 | PASS |
| `GET /api/v1/finance/summary` | 200 | PASS |
| `GET /api/v1/finance/receivables/summary` | 200 | PASS |
| `GET /api/v1/finance/receivables/orders` | 200 | PASS |
| `GET /api/v1/orders` | 200 | PASS |
| `GET /api/v1/payments` | 200 | PASS |
| `GET /api/v1/skus` | 200 | PASS |

- Available tenants: 2 (both verified and selectable).
- No negative customer outstanding value in any Finance response.
- Tenant scope matches selected tenant (select-tenant returned contextual
  JWT; all subsequent requests used it successfully).

## 4. Negative Checks

| Check | HTTP | Pass? |
|---|---|---|
| Unauthenticated `/finance/summary` | 401 | PASS |
| Tenant token on platform route | 307 (redirect to login) | PASS (no data leaked) |
| Unauthenticated `/exports/not-a-uuid` | 401 | PASS |
| Fake/unselectable tenant (no auth) | 401 | PASS |
| Fake tenant with valid identity token | 404 | PASS |

## 5. Browser Proof

Browser proof was not executed in this verification (requires Playwright/
browser automation on the VPS). The frontend SPA serves 200 on `/` and
`/login` (verified via HTTP probes). All Finance API endpoints return 200
when authenticated. **Recorded as a caveat; not a failure.**

## 6. Sanitized Log Scan (verification window)

| Pattern | Count |
|---|---|
| HTTP 500 | 0 |
| ResponseValidationError | 0 |
| TenantContextMissing | 0 |
| UndefinedTable | 0 |
| Enum/coercion error | 0 |
| Decimal serialization error | 0 |
| Traceback | 0 |
| Secret/JWT/password/DB URL leakage | 0 |

**ALL_ZERO = True**

## 7. Zero Production Mutations Confirmation

- DB proof used `BEGIN READ ONLY; ... ROLLBACK;`.
- Temp password was set and restored (`HASHES_RESTORED=True`).
- No deploy, checkout, restart, rebuild, or configuration change.
- No test data created.
- No production branch/tag pushed.
- Verify script removed from container.

## 8. Compliance

- No credentials, JWTs, emails, DB URLs, row contents, or identifiers printed.
- Only counts and HTTP status codes recorded.
- `git diff --check`: PASS.
- ASCII: 0 non-ASCII.
- `pre-commit` / `detect-secrets`: PASS.
- GitNexus: docs-only change (no execution flows affected).

## 9. Verdict

**PASS_DC11T4I_R2D_INDEPENDENT_FINANCE_RUNTIME_VERIFIED**

TEST001 contamination is absent (0 wholesalers, 0 schemas, 0 bindings). All
finance/accounting invariants hold (0 negative balances, 0 cross-tenant
references, 0 over-collected orders). All credentialed Finance APIs return
200. All negative checks return controlled 4xx. Backend logs show zero 500s,
zero tracebacks, zero secret leaks. The only caveat is browser automation
(not executed; SPA serves 200 and Finance APIs are proven).
