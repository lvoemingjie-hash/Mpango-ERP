# DC-12R1-H2 (R1) Structured HTTP Error Serialization Boundary

Date: Tuesday, July 28, 2026 (R1 revision)
Branch: `zcode/dc12r1-h2-structured-http-error-contract-2026-07-28`
H2 tip continued: `d346f2ad00bb1076db75218749706bd33196dff8`
Created from: `origin/product-dev-recovered`
Expected base: `bb1b39f137fc7fc1de721b7131e80e5d89b1e2bc` (verified)
S2 freeze checkpoint (untouched): `zcode/dc12r1-s2-supplier-scoped-retailer-login-2026-07-28` @ `5b51f06ba46703df36f64345ffd658649779c831`

## Verdict

`PASS_FOR_CTO_DC12R1_H2_R1_MERGE_REVIEW`

R1 hardens the public-detail JSON-safety boundary and tightens the public code
contract, with the production `http_exception_handler` **never raising** and
**never creating a repr by stringifying a non-string detail**. Evidence is split
into two clearly distinguished families — **real RBAC dependency** tests (the
actual `RequirePermission` / `RequirePlatformAdmin` executed over HTTP) and
**raw-shape** (detail-normalization) tests. Two full backend gates on separate
fresh PG16/Redis7 environments passed with zero failures, zero errors and zero
exclusions.

## Narrowed Claim

The guarantee is stated precisely (not over-broadly):

> The `http_exception_handler` **never creates a Python `repr` by stringifying
> a non-string `detail`**. Non-string details (dict / list / int / None /
> object) are *normalized* into the flat `{code, message, request_id}`
> envelope — a dict's string `code`/`message` are extracted, never the whole
> dict rendered via `str()`. The malformed detail is never surfaced; the
> handler itself never raises.

This does **not** claim the handler sanitizes arbitrary attacker-controlled
string *messages* (a genuine human string message is preserved verbatim,
subject only to the `_sanitize_message` repr-marker guard).

## R1 Product Change

Changed file (3-file scope total for H2 — see "Files Touched"):

- `backend/core/error_codes.py`

### 1. Public `details` is now genuinely JSON-safe

`_is_json_safe` / `_is_json_safe_value` (recursive) now require, at every level:

- **string dictionary keys** (top-level AND nested); any non-string key fails
  closed → details omitted
- leaf values restricted to `None`, `bool`, `int`, `str`, and **finite**
  `float`
- **NaN / +Infinity / -Infinity rejected** (`math.isfinite`)
- **bytes / bytearray / set / frozenset / tuple** explicitly rejected before
  the generic dict/list handling
- arbitrary objects / callables / custom classes rejected

Unsafe `details` are **omitted** (never surfaced) while the original HTTP
status, sanitized code, sanitized message and `request_id` survive — no 500.

### 2. Public error codes tightened

`_is_safe_code` now enforces `^[A-Z][A-Z0-9_]{0,63}$` (UPPER_SNAKE, 1–64
chars). Malformed / oversized / lowercase / dash / quote / space codes fall
back to the **status-derived** `ErrorCode` (the string `message` is still
preserved).

### 3. The exception handler itself never raises

`http_exception_handler` wraps normalization in `try/except Exception`
(fail-closed): any unexpected error while normalizing a pathological detail
yields the standard envelope with the original HTTP status preserved. Pure
normalization lives in `_build_error_body`.

No permission / RBAC / tenant-context / platform-identity logic was modified;
`RequirePermission`, `RequirePlatformAdmin`, `attach/get_auth_context`,
`attach/get_tenant_context` are byte-identical to base. The fix is in the
**shared** handler — not a special-case for the three RBAC raises.

## Evidence — Two Distinct Families

The H2 suite deliberately separates **real RBAC dependency** evidence from
**raw-shape** (detail-normalization) evidence.

### Family A — Real RBAC dependency evidence (`TestRealRBACDependencies`)

A deterministic test **middleware** attaches auth/tenant context per route
*before* the route dependencies resolve, so the REAL `RequirePermission` /
`RequirePlatformAdmin` execute against controlled identities over actual HTTP:

| Route | Attached identity | Result |
|-------|-------------------|--------|
| `/rbac/perm` | contextual token + tenant ctx, **no permissions** | `403` `PERMISSION_DENIED` |
| `/rbac/perm_no_tenant` | contextual token, **no tenant ctx** | `403` `TENANT_CONTEXT_REQUIRED` |
| `/rbac/platform` | identity-only token, **not super admin** | `403` `PLATFORM_ADMIN_REQUIRED` |

Asserted: exact HTTP `403`, exact codes, **no permission bypass** (no route
ever returns 200), no dict repr in response or logs.

### Family B — Raw-shape (detail-normalization) evidence

`HTTPException(detail=...)` shapes that mirror the RBAC raises, plus the R1
JSON-safety / code-validation contract — exercises the handler directly
(`TestHandlerLevelContract`-style `_HandlerProbe`) and over HTTP. Covers:
NaN/±Infinity omission, non-string top-level **and** nested keys, bytes/set/
frozenset/tuple/bytearray/arbitrary-object omission, unsafe-details-omitted
with no 500, valid nested JSON details preserved, invalid/oversized code
fallback, max-length (64) valid code preserved, handler-never-raises across
pathological inputs, and ordinary string-detail compatibility.

## Test Changes

Changed file:

- `backend/tests/test_dc12r1_h2_structured_http_error_contract.py` (44 tests)

Coverage (R1 additions marked):

- §1 **Real RBAC dependency** evidence (5 tests): exact 403 + the three codes
  via the real deps; no-permission-bypass; real-RBAC logging has no raw
  detail repr (asserts on `logger.warning` via `mock.patch`, robust across the
  full-suite structured-logging reconfiguration)
- §2 Raw-shape denial codes; arbitrary valid code preservation; explicit
  public details preserved; string-detail compatibility; malformed
  (list/int) fail-closed; no repr in any denial response
- §3 **R1 public-details JSON-safety**: NaN/±Infinity omitted (no 500);
  non-string top-level & nested keys omitted; bytes/bytearray/set/frozenset/
  tuple omitted; arbitrary object omitted; valid nested JSON details preserved
- §3 **R1 public-code strictness**: invalid/oversized codes fall back to
  status-derived code (message preserved); 64-char code preserved
- §3 **R1 handler-never-raises**: every pathological detail yields the flat
  envelope, original status preserved
- §3 String-detail / dict-detail / None-detail / nested-extra-keys / all-status
  compatibility

No skip, xfail, deselection, exclusion, assertion weakening, migration edit,
permission change, RBAC change, or S2 work was introduced.

## Test-Safe Environment

Fresh, isolated, single-use infrastructure (no production data, loopback only):

- PostgreSQL 16.14 container `mpango_h2_pg16` on `127.0.0.1:5433`
- Redis 7.4.10 container `mpango_h2_redis7` on `127.0.0.1:6380`
- Python 3.12.10 isolated venv (project-pinned: `fastapi==0.128.0`,
  `bcrypt>=4.0,<4.1`, `pytest==8.4.2`, `httpx==0.28.1`, `openpyxl==3.1.5`, …)
- Main gate DB `mpango_test_s2` dropped + re-migrated from scratch to head
  `036_retailer_mvp_identity` before each run
- Temp-DB migration tests opted in explicitly:
  `MPANGO_ALLOW_TEMP_DB_CREATE=1`, `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`,
  `MPANGO_TEMP_DB_ALLOWED_PORTS=5433`, test-safe source user
  `mpango_test_runner` (never `mpango`, never `prod`) on disposable `test_h2`
- All credentials disposable test-only; Redis flushed between runs

## Validation

Focused H2 suite + RBAC / route-authorization / users-roles / auth /
auth-bypass / permission-registry-drift / first-admin-RBAC / platform-operator
/ platform P0+P10 / security S2.5 / tenant-context-contract / validation-
serialization regression subset: **385 passed**.

## Full Backend Gate (twice, fresh PG16/Redis7, zero exclusions)

Both runs: full suite, no `-k`, no `--deselect`, no skip/xfail introduced,
zero exclusions, zero failures, zero errors.

| Run | Passed | Skipped | XFailed | Failed | Errors | Wall |
|-----|--------|---------|---------|--------|--------|------|
| 1 (fresh PG16 + Redis7) | 2949 | 29 | 15 | 0 | 0 | 8m49s |
| 2 (fresh PG16 + Redis7) | 2949 | 29 | 15 | 0 | 0 | 8m49s |

Pre-existing skips/xfails only (DB-optional / known-incomplete features); no
test was deselected or weakened. The R1 suite added test cases (H2 went from
15 → 44 tests), reflected in the pass count rising from 2920 (H2) → 2949 (R1).

## Quality Gates

- `py_compile` on both changed files — OK
- `git diff --check` — clean (exit 0; LF/CRLF note is a Windows line-ending
  advisory, not a whitespace error)
- `detect-secrets scan` on both files — **0 findings**
- scoped `pre-commit run --files` (trailing-whitespace, end-of-files,
  large-files, detect-secrets `--baseline .secrets.baseline`) — all Passed
- GitNexus impact **before** edit + analyze/status **after** commit — see below

## GitNexus

- **Impact before edit** (`gitnexus impact http_exception_handler -d upstream`,
  indexed at base `bb1b39f`): graph returns **LOW / impactedCount 0** —
  exactly as anticipated. The handler is registered dynamically via
  `app.add_exception_handler` inside `register_exception_handlers`
  (`gitnexus impact register_exception_handlers` confirms it is called by
  `backend/main.py`, the app entry point), so the static call graph cannot see
  its dependants. **Effective blast radius is treated as HIGH** (it serializes
  every `HTTPException` app-wide); the two fresh full-backend gates are the
  real regression proof for that HIGH radius.
- **detect_changes before commit**: changed-scope is exactly the 3 allowed
  files (`backend/core/error_codes.py`,
  `backend/tests/test_dc12r1_h2_structured_http_error_contract.py`, this
  report); `.env.test` is gitignored, `.venv/` untracked+ignored.
- **Analyze / status after commit**: index re-checked against the final commit
  (recorded at the final tip below, not at the base). Because the handler is
  dynamically registered the graph result stays LOW; the conclusion (HIGH
  effective radius, verified by the double gate) is unchanged.

## Files Touched (exactly 3 — the full H2 scope)

- `backend/core/error_codes.py` (modified)
- `backend/tests/test_dc12r1_h2_structured_http_error_contract.py` (modified)
- `ai-ledger/product-ai/2026-07-28_dc12r1_h2_structured_http_error_contract.md` (this report)

No S2 files, permissions, RBAC decisions, migrations, frontend, deployment, or
any other file were modified.

## Push

Only the existing H2 branch `zcode/dc12r1-h2-structured-http-error-contract-2026-07-28`
is pushed. No protected push, merge, deploy, S3 or S4.
