# DC-12R1-H7-R15-R4-R1-V1 — Kilo Final Bounded Cumulative Review

**Verdict:** `PASS_FOR_CTO_DC12R1_H7_R15_R4_R1_V1_KILO_FINAL_REVIEW`
**Scope:** Source, test-authenticity, secret-boundary and evidence-truth review ONLY.
**No native-Linux PASS, no merge approval, no deployment/Playwright/VPS claim is made here.**

---

## 0. Identifiers (immutable proof)

| Item | Value |
|------|-------|
| Protected baseline (`a6ef3aac`) | `a6ef3aac0ab03615e9d70e08e504b9858baf61c5` |
| R15 cumulative base (R14 candidate) | `b2b08ab01b072b7296e5c38dafda5ecfae76f9ad` |
| R15-R4 implementation | `1291d87a3f33e839e4d5e2610423535211393080` |
| **Frozen candidate (this review)** | `fd7727f83e30338ccabcf5cb459a093a0a766e05` |
| Candidate source branch | `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12` (= `fd7727f8` ✅) |
| Accepted prior evidence | Kilo R14-V1 `5c91eb2e`; Lubuntu R14-V2 STOP `d3f34af3` |
| Review worktree | detached `fd7727f8` at `C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1_h7_r15_r4_r1_v1_review` |
| Report branch base | `a6ef3aac` (protected, unchanged) |

---

## 1. Phase 1 — Proof gate (all PASS)

Run against a detached clean worktree at `fd7727f8` (no protected refs modified; only fetch of public refs).

1. **Candidate branch == candidate SHA** — `origin/zcode/.../2026-08-12` resolves to `fd7727f8` ✅
2. **Parent == R15-R4** — `fd7727f8^` == `1291d87a` ✅
3. **Protected baseline is ancestor** — `git merge-base --is-ancestor a6ef3aac fd7727f8` → 0 ✅
4. **R15-R4-R1 delta is exactly 3 docs** — `1291d87a..fd7727f8` =
   - `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`
   - `docs/ai/CTO_CURRENT_OPS.md`
   - `docs/ai/PROJECT.md`
   (count = 3) ✅
5. **Cumulative delta is exactly 7 files** — `b2b08ab0..fd7727f8` =
   - `backend/scripts/setup.sh`
   - `backend/scripts/setup_preflight.py`
   - `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`
   - `backend/tests/test_dc12r1_h7_setup_preflight.py`
   - `docs/ai/PROJECT.md`
   - `docs/ai/CTO_CURRENT_OPS.md`
   - `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`
   (count = 7, matches the mandated list exactly) ✅

Consequence: the 4 code files are **byte-identical between R15-R4 (`1291d87a`) and R15-R4-R1 (`fd7727f8`)** (delta is docs-only). All Phase-2/3/4 code analysis below is therefore identical to the R15-R4 code state, re-verified here.

---

## 2. Phase 2 — Runtime source review (`REPORTING_USER_PASSWORD` strict-parser path)

Source: `backend/scripts/setup.sh` (L116-139) and `backend/scripts/setup_preflight.py`.

- **Required before side effect:** `_NATIVE_RUP` is extracted from the same `parse_env_file('.env')` call that yields `DATABASE_URL` (setup.sh L116), and `REPORTING_USER_PASSWORD` is fail-closed at L124 (`[ -n "$_NATIVE_RUP" ] || exit 1`) **before** it is exported (L126) and **before** `alembic upgrade head` (L129). The Alembic migration is the only side effect that consumes it. ✅
- **Process-env & rendered backend Compose fail closed** (`setup_preflight.py` `run_initial`):
  - absence → `_fail("REPORTING_USER_PASSWORD not found in backend/.env")` (L219-220); rendered backend key missing → `not isinstance(_backend_rup, str)` → `_fail` (L278-280);
  - wrong type → `null/bool/int/list` for rendered `REPORTING_USER_PASSWORD` rejected (L279);
  - empty value → rendered `""` mismatches non-empty file value → `_fail` (L281-285);
  - mismatch → `_backend_rup != file_rup` → `_fail` (L281-285); process-env empty-but-present RUP treated as conflict (L230-231). ✅
- **Same strict parser:** both `DATABASE_URL` and `REPORTING_USER_PASSWORD` come from `setup_preflight.parse_env_file` (setup.sh L116 capture; preflight L211-220 read). No second handwritten parser, no `set -a`, no `.env` source. ✅
- **`_NATIVE_CREDS` split then exactly unset before Alembic:** captured L116, split L118-121, `unset _NATIVE_CREDS` L122, no re-assignment/reference survives between unset (L122) and Alembic (L129). ✅
- **Both exported before Alembic:** L125 `export DATABASE_URL`, L126 `export REPORTING_USER_PASSWORD`; Alembic at L129. ✅
- **RUP unset before tenant bootstrap:** L133 `unset REPORTING_USER_PASSWORD _NATIVE_RUP` before `bootstrap_tenant_schema.py` (L136). ✅
- **DATABASE_URL retained for bootstrap then unset:** exported L125; not unset until L139 (after bootstrap L136); `_NATIVE_DB_URL` also unset L139. ✅
- **No secret in argv/log/stdout/stderr:** credentials captured into a shell variable via `python -c "…print(e.get(…))"` with `2>/dev/null`; output is captured, never echoed; enforcing fakes prove sentinels never reach any channel (see Phase 5 `test_no_secret_in_output` / `test_alembic_and_bootstrap_use_validated_env_url`). ✅
- **No `alembic.ini` credential fallback:** `backend/alembic/env.py` L33-38 overrides `sqlalchemy.url` from `os.environ.get("DATABASE_URL")`; native setup exports `DATABASE_URL` (L125), so the env var wins — no `.ini` credential fallback is used. ✅

---

## 3. Phase 3 — AST evidence authenticity

Source: `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py` `_scan_migration_env_vars` (L1759-1847) + `TestMigrationEnvVarScanner` (L1850-1910) + `test_migration_env_dependency_inventory_is_exactly_reporting_user_password` (L1913-1923).

- **Supported forms (parametrized, all expect the exact var):** `os.environ.get`, `os.environ[…]` subscript, `os.getenv`, `from os import environ/getenv` and aliases, assignment chains (`a = os.environ; b = a; b.get`), imported-alias assignment, and **module-qualified `getenv` aliases** (`g = os.getenv`, `import os as _os; g = _os.getenv`, `import os as alias; g = alias.getenv`). 21 supported-form cases, all `{VAR}`. ✅
- **Fail-closed forms (hard `AssertionError`):** dynamic key `os.environ.get(some_var)` (L1819-1820), dynamic subscript `os.environ[some_var]` (L1825-1826), and **unauthorized methods** `setdefault`/`pop`/`update`/`clear`/`copy`/`items` on a tracked environ name, `putenv`, and dynamic key on a `getenv` alias — 13 cases, every one raises `AssertionError`. ✅
- **Non-os module `getenv` negative case:** `import someother; g = someother.getenv; g("VAR")` returns `set()` (L1884-1889) — correctly NOT tracked. ✅
- **Real migrations 001–037:** scan of every `alembic/versions/*.py`, `extra = env_vars - {"DATABASE_URL","REDIS_URL"}`, asserts `extra == {"REPORTING_USER_PASSWORD"}` (L1913-1923). Genuinely executed in Phase 5 (parity file 175 passed, this test included). ✅

---

## 4. Phase 4 — Shell / test authenticity

- **Exact active `unset _NATIVE_CREDS`:** setup.sh L122 is the literal command `unset _NATIVE_CREDS  # R15-R1: clear the combined buffer immediately after split` — an active builtin, not a comment/echo/no-op. ✅
- **Mutation tests execute mutated real setup.sh:** `_run_mutated` (L1630-1639) copies the committed `setup.sh`, applies the mutation to `SETUP_SH.read_text()`, asserts `mutated != original` (prevents inert/no-op mutations), writes the bytes, and runs the real script through `_run`. Confirmed by `test_mutation_remove_rup_export_fails` / `test_mutation_wrong_rup_fails` (L1724-1745). ✅
- **Enforcing fakes compare actual values against `.env`:** the `alembic` fake greps `^DATABASE_URL=`/`^REPORTING_USER_PASSWORD=` from `.env` and exits 2/4 on mismatch (L1100-1113); the `python`/`bootstrap` fake greps `.env` for `DATABASE_URL` and fails (exit 5) if `REPORTING_USER_PASSWORD` survives into bootstrap (L1114-1127). ✅
- **No skip / xfail / conditional pass / weakened assertion:** grep across both test files for `skip`/`xfail`/`conditional` found only prose mentions (line-tracking comment), zero decorators or conditional assertions. ✅

---

## 5. Phase 5 — Runtime (host permits; genuine zero-red)

Environment: Windows host, **Git Bash** `C:\Program Files\Git\usr\bin\bash.exe` (System32/WSL rejected per `_select_bash`), Python 3.12.10 in an **isolated venv built from the repo's exact-pin `requirements.txt`** (incl. `cryptography==46.0.5`, `openpyxl==3.1.5`, `passlib==1.7.4`). This is a Kilo-host execution, **NOT a native-Linux run**.

| Suite | Expected | Result |
|-------|----------|--------|
| Direct preflight (`test_dc12r1_h7_setup_preflight.py`) | 144 | **144 passed** (1.62 s) |
| Executable harness (`TestH7R5R2ExecutableHarness`, subset of parity) | 38 | **38 passed** (97.21 s) |
| Manifest/parity file (`test_dc12r1_h7_bcrypt_manifest_parity.py`) | 175 | **175 passed** (109.21 s) |
| Complete H7 (union of the two H7 test files) | 319 | **319 passed, 0 failed** |

- The 38-harness count is a subset of the 175 parity-file count; `144 + 175 = 319` is the complete H7 suite.
- Each suite was executed once in natural collection order; fixtures are `tmp_path`-isolated with no shared module-level mutable state, so ordering is by construction independent (the docs additionally claim reversed-order; this run confirms natural-order parity only — disclosed honestly).
- **No `HOST_ENVIRONMENT_LIMITATION` was triggered**: dependency drift did not block execution (exact pins installed), so a genuine zero-red result is reported for the Kilo host.

---

## 6. Phase 6 — Evidence truth

- **PROJECT.md (L7) and CTO_CURRENT_OPS.md (L448)** both state `Direct 144/144; harness 38/38; parity 175/175; complete H7 319/319` and verdict `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`. These counts **match the genuine runtime in Phase 5** exactly. ✅
- **Next-step order** in both docs: `Kilo bounded cumulative R15 review → Lubuntu native setup.sh twice → focused zero-red gate → CTO merge decision`. This review is the first step; the docs correctly do **not** claim native-Linux PASS, merge approval, or deployment. ✅
- **Ledger supersede chain:** `## R15-R4 evidence (SUPERSEDED_BY_H7_R15_R4_R1_DOCS_ONLY)` (ledger L28) is accurate — R15-R4-R1 (`fd7727f8`) is a **docs-only** increment over R15-R4 (`1291d87a`); the 4 code files are byte-identical across `1291d87a..fd7727f8` (Phase 1 check 4). **True severity: INFORMATIONAL/LOW** — a documentation-statement bookkeeping tag with **no source, secret-boundary, or behavioral impact**. It does not block this source-review PASS. ✅
- No doc in scope claims native-Linux PASS / merge / deployment / Playwright / VPS readiness. ✅

---

## 7. Quality gates

| Gate | Result |
|------|--------|
| `bash -n backend/scripts/setup.sh` | OK (rc=0) |
| `py_compile` (setup_preflight.py, both test files, alembic/env.py) | OK (rc=0) |
| `git diff --check` (R15-R4-R1 delta, 3 docs) | clean (rc=0) |
| `git diff --check` (cumulative delta, 7 files) | clean (rc=0) |
| scoped `detect-secrets scan --baseline .secrets.baseline` (7 files) | clean (rc=0); baseline restored after scan |
| UTF-8 strict decode (7 files) | all OK, no mojibake |
| GitNexus `analyze`/`status` | indexed 15,095 nodes; worktree up-to-date at `fd7727f8` |

Note: `detect-secrets scan` transiently rewrote `.secrets.baseline` in the worktree; it was restored via `git restore --worktree --staged` and the candidate tree is byte-identical (`git status` clean).

---

## 8. Finding accounting

16 findings, **0 defects**, accounting gap = 0.

| ID | Phase | Finding | Result | Severity |
|----|-------|---------|--------|----------|
| F1 | P1 | Candidate branch == candidate SHA | PASS | — |
| F2 | P1 | Parent == R15-R4 (`1291d87a`) | PASS | — |
| F3 | P1 | Protected baseline is ancestor | PASS | — |
| F4 | P1 | R15-R4-R1 delta == exactly 3 docs | PASS | — |
| F5 | P1 | Cumulative delta == exactly 7 files (mandated list) | PASS | — |
| F6 | P2 | RUP required fail-closed before Alembic side effect | PASS | — |
| F7 | P2 | Process-env & rendered Compose RUP fail closed (absent/type/empty/mismatch) | PASS | — |
| F8 | P2 | Same parser; both exported before Alembic; RUP unset before bootstrap; DB_URL retained then unset | PASS | — |
| F9 | P2 | Secrets never in argv/log/stdout/stderr; no `.ini` credential fallback | PASS | — |
| F10 | P3 | AST scanner supports all forms + aliases; hard-fails dynamic/unauthorized | PASS | — |
| F11 | P3 | Migrations 001–037 non-connection env set exactly `{REPORTING_USER_PASSWORD}` | PASS | — |
| F12 | P4 | Active `unset _NATIVE_CREDS`; mutation edits real setup.sh; fakes vs `.env`; no skip/xfail | PASS | — |
| F13 | P5 | Direct 144 / harness 38 / parity 175 / complete 319 — genuine zero-red (Kilo host) | PASS | — |
| F14 | P6 | PROJECT/CTO counts & STOP next-step order accurate; no overclaim | PASS | — |
| F15 | P6 | Ledger `SUPERSEDED_BY_H7_R15_R4_R1_DOCS_ONLY` tag accurate (docs-only increment) | PASS | INFORMATIONAL |
| F16 | Q | bash -n / py_compile / diff --check / detect-secrets / UTF-8 / GitNexus all OK | PASS | — |

---

## 9. Conclusion

All nine phases pass. The frozen candidate `fd7727f8` (R15-R4-R1) is a **docs-only** correction over R15-R4 (`1291d87a`); the secret-boundary code (`setup.sh`, `setup_preflight.py`), the AST evidence scanner, and the mutation/enforcing-fake harness are unchanged and re-verified; the complete H7 suite (319 tests) passes zero-red on the Kilo host via genuine execution. No native-Linux, merge, deployment, Playwright, or VPS claim is made.

**Verdict: `PASS_FOR_CTO_DC12R1_H7_R15_R4_R1_V1_KILO_FINAL_REVIEW`** — source-review approval only.
**Next gate (unchanged):** Lubuntu native `setup.sh` execution (twice) → focused zero-red gate → CTO merge decision.
