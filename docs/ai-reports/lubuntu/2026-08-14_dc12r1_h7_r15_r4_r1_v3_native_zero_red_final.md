# DC12R1-H7-R15-R4-R1-V3 — Lubuntu Native Zero-Red Final

**Date:** 2026-08-14 | **Host:** Lubuntu (Linux x86_64, Ubuntu 24.04) | **Verdict: STOP_AND_REPORT_CTO**

## Verdict summary

Phase 3 (native setup) **PASSES** for the first time in the R13→R14→R15
chain — the R15 fix exports both `DATABASE_URL` and `REPORTING_USER_PASSWORD`
from `backend/.env` before `alembic upgrade head`, resolving both the R13
alembic.ini fallback and the R14 REPORTING_USER_PASSWORD defect. All 37
migrations run, tenant bootstrap completes, and idempotency is proven.

However, **Phase 4 (focused zero-red tests) FAILS**: 3 tests fail in natural
order, 2 in reverse order. Two failures are platform-specific (Windows WSL
bash detection and CRLF mutation on Linux); one is a test-isolation issue
(Hypothesis node fails when preceded by other tests but passes alone).

## 1. Phase 1 — Proof gate (ALL PASS)

| Proof | Result |
|---|---|
| Source branch tip | `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12` = `fd7727f8` ✓ |
| Frozen candidate | `fd7727f83e30338ccabcf5cb459a093a0a766e05` = commit "DC-12R1-H7-R15-R4-R1: current-truth documentation correction (NO PASS)" ✓ |
| Direct parent | `git rev-list --parents -n1 fd7727f8` → parent = `1291d87a3f33e839e4d5e2610423535211393080` ✓ |
| R14 base ancestor | `git merge-base --is-ancestor b2b08ab0 fd7727f8` → ancestor ✓ |
| Protected baseline | `a6ef3aac0ab03615e9d70e08e504b9858baf61c5` = commit ✓ |
| Kilo review | `e9303476dcd46e870ea1d445589cb62752fdf1cf` = commit ✓ |
| R15-R4-R1 delta (`1291d87a..fd7727f8`) | Exactly 3 docs: `ai-ledger/...reconciliation.md`, `docs/ai/CTO_CURRENT_OPS.md`, `docs/ai/PROJECT.md` ✓ |
| Cumulative delta (`b2b08ab0..fd7727f8`) | Exactly 7 files: the 3 docs + `backend/scripts/setup.sh`, `backend/scripts/setup_preflight.py`, `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`, `backend/tests/test_dc12r1_h7_setup_preflight.py` ✓ |
| Clean detached checkout | `git checkout --detach fd7727f8`, `git status --porcelain` empty ✓ |

## 2. Phase 2 — Isolated native environment (PASS)

- **Host-owner set BEFORE:** 9 containers (all Up 4 days, healthy), recorded.
- **Unique project:** `h7_r15_v3_82c44f95`.
- **Loopback ports (verified free):** PostgreSQL `127.0.0.1:55441`, Redis `127.0.0.1:56389`.
- **Python venv:** 3.12.3.
- **Compose implementation:** Docker Compose **v2.32.4** (official GitHub release, statically-linked Go ELF, 64,694,701 bytes, task-owned CLI plugin). No fake executables.
- **backend/.env** (mode 600, ASCII, LF, 36 lines, no CHANGE_ME): DATABASE_URL uses `127.0.0.1:55441`; REDIS_URL uses `127.0.0.1:56389`; POSTGRES_USER/PASSWORD/DB match URL; POSTGRES_PUBLISHED_PORT=55441; REDIS_PUBLISHED_PORT=56389; strong SECRET_KEY (64 chars); CORS_ORIGINS valid JSON list; EMAIL_DELIVERY_MODE=dev_sink; REPORTING_USER_PASSWORD present. `.env` sha256: `74bcbeb2c30843cdc3500505d68cf43fcc3d81ffda81d319ccc7a57f865262fc`.
- DATABASE_URL/REDIS_URL cleared from shell; `.env` not sourced/exported.
- Compose config `--quiet` exit 0. Preflight: `OK`.

## 3. Phase 3 — Native setup run 1 + run 2 (BOTH PASS)

### Run 1

Command: `COMPOSE_PROJECT_NAME=h7_r15_v3_82c44f95 DEFAULT_TENANT_SCHEMA=t_h7_r15_v3 bash backend/scripts/setup.sh`

- Preflight: `OK` ✓
- Docker services: postgres + redis created, started, healthy ✓
- pip install: all 70 packages installed ✓
- Post-install preflight: `OK` ✓
- `alembic upgrade head`: **all 37 migrations (001–037) ran successfully** ✓
  - Migration 011 (`011_s6_p_reporting_role`) PASSED — `REPORTING_USER_PASSWORD` was exported by setup.sh from `.env` before alembic ✓
  - Migration 037 (`037_payment_declarations_schema`) reached ✓
- Tenant bootstrap: `t_h7_r15_v3` ready (19 tables, reconciled) ✓
- Frontend: pnpm install completed ✓
- **"Setup complete!"** printed ✓
- **Exit 0** ✓

### Run 2 (idempotency)

Same command, same project/ports/.env — nothing deleted.

- Containers reused (same IDs, Running not recreated) ✓
- pip: all "Requirement already satisfied" ✓
- Alembic: no-op (already at head 037) ✓
- Bootstrap: reconciliation path (all "ensured", no "created") ✓
- **"Setup complete!"** printed ✓
- **Exit 0** ✓

**Before/after fingerprint comparison: identical** (alembic=037, tables=21,
roles=1, permissions=9, role_perms=6, user_roles=0, tenant_count=1,
payment_declarations=0 rows, receipt_sequences=0 rows, receipt_number_idx=1).
No duplicate tenant schema, RBAC rows, or migration artifacts.

### Connection-context proof

All 37 migrations executed SQL and completed on the isolated database
(`127.0.0.1:55441`). If alembic had connected to `127.0.0.1:5432` (host-owner),
it would have failed with `InvalidPasswordError` at migration 001. Success
through 037 proves connection to the project-isolated database. The R15
setup.sh exports `DATABASE_URL` from `.env` (port 55441) before
`alembic upgrade head`; no alembic.ini fallback path exercised.

### Database object proof

- `public.alembic_version` = `037_payment_declarations_schema` (sole head) ✓
- Tenant schema `t_h7_r15_v3` exists (1 schema, no unexpected second) ✓
- `payment_declarations` table exists ✓
- `receipt_sequences` table exists ✓
- `payments.receipt_number` column (varchar, nullable) ✓
- `ux_payments_receipt_number` partial unique index ✓
- 21 base tables including RBAC (roles, permissions, role_permissions, user_roles) ✓

### Runtime package proof

`bcrypt==4.0.1`, `cryptography==46.0.5`, `openpyxl==3.1.5`, `et_xmlfile==2.0.0`, `passlib==1.7.4` ✓

## 4. Phase 4 — Focused zero-red (FAIL)

### Natural order (3 files)

`pytest tests/test_dc12r1_h7_setup_preflight.py tests/test_dc12r1_h7_bcrypt_manifest_parity.py tests/test_token_properties.py -q`

**324 collected, 3 failed, 321 passed.**

| # | Failed node | Error | Classification |
|---|---|---|---|
| 1 | `TestH7R5R2ExecutableHarness::test_launcher_fail_closed_when_only_system32_wsl_bash_exists[C:\Users\me\AppData\Local\Microsoft\WindowsApps\bash.exe]` | `Failed: DID NOT RAISE RuntimeError` | Platform-specific: tests Windows WSL bash detection; on Linux system `/usr/bin/bash` is found instead, so no RuntimeError is raised |
| 2 | `TestH7R5R2ExecutableHarness::test_launcher_crlf_mutated_script_fails_before_any_command` | `assert 'CRLF line endings' in stderr` — actual stderr: `set: pipefail\r: invalid option name` | Platform-specific: Linux bash fails at `set -o pipefail\r` before any CRLF detection logic runs |
| 3 | `test_token_properties::test_property_token_roundtrip_integrity` | Hypothesis test failed when preceded by other tests in same process | Test isolation: test passes when run alone (see below) |

### Reverse order (3 files)

`pytest tests/test_token_properties.py tests/test_dc12r1_h7_bcrypt_manifest_parity.py tests/test_dc12r1_h7_setup_preflight.py -q`

**324 collected, 2 failed, 322 passed.** Same failures #1 and #2 (WSL + CRLF).
Failure #3 (Hypothesis) PASSED in reverse order — confirming test isolation issue.

Collected totals identical (324) in both orders ✓. But failed ≠ 0 in either order.

### Hypothesis node — separate processes

`test_property_token_roundtrip_integrity`:

| Run | Result |
|---|---|
| Unseeded run 1 | **passed** (1.42s) |
| Unseeded run 2 | **passed** (1.43s) |
| Unseeded run 3 | **passed** (1.67s) |
| Unseeded run 4 | **passed** (1.45s) |
| Unseeded run 5 | **passed** (1.71s) |
| Seeded (303296478269760642762159842520761126666) | **passed** (1.33s) |

All 6 separate runs pass. No health-check suppression, deadline change, rerun, or test edit.

### Classification summary

The Hypothesis node is green in isolation but red in the natural order due to
test-isolation contamination from preceding tests. The two launcher tests
(`TestH7R5R2ExecutableHarness`) are Windows-platform tests that fail
deterministically on Linux because they test WSL bash detection and CRLF
mutation behavior without platform guards (`@pytest.mark.skipif`).

## 5. Phase 5 — Quality gates + cleanup

### Quality gates (PASS)

- `bash -n backend/scripts/setup.sh`: OK ✓
- `py_compile` (setup_preflight.py, test_setup_preflight.py, test_bcrypt_manifest_parity.py): all OK ✓
- `git diff --check`: no whitespace errors ✓
- Candidate tree: `git status --porcelain` empty, HEAD = `fd7727f8` ✓

### Secret hygiene

- Run 1 log scanned against every secret-bearing `.env` value: **zero matches** ✓
- Run 2 log scanned: **zero matches** ✓
- No credentials in report ✓

### Cleanup

- `docker compose --env-file backend/.env -p h7_r15_v3_82c44f95 down -v --remove-orphans`: all containers/volumes/networks removed ✓
- Task-owned clone, venv, Compose plugin, `.env`, logs removed ✓
- **Zero task-owned residue:** containers 0, networks 0, volumes 0 ✓
- **Host-owner set unchanged:** all 9 original containers present with same IDs and uptime ✓
- **Refs unchanged:** source branch = `fd7727f8` before and after ✓

## 6. Exact failed/error accounting

| Phase | Node | Error | Classification |
|---|---|---|---|
| 4 natural | `test_launcher_fail_closed_when_only_system32_wsl_bash_exists[...bash.exe]` | `DID NOT RAISE RuntimeError` | Platform-specific (Windows WSL test on Linux) |
| 4 natural | `test_launcher_crlf_mutated_script_fails_before_any_command` | `'CRLF line endings' not in stderr` | Platform-specific (Linux bash CRLF handling) |
| 4 natural | `test_property_token_roundtrip_integrity` | Hypothesis failure in-process | Test isolation (passes alone) |
| 4 reverse | `test_launcher_fail_closed_when_only_system32_wsl_bash_exists[...bash.exe]` | same | same |
| 4 reverse | `test_launcher_crlf_mutated_script_fails_before_any_command` | same | same |

## 7. Recommendation

The R15 candidate resolves both the R13 (alembic.ini fallback) and R14
(REPORTING_USER_PASSWORD) native-setup defects. Phase 3 is fully green.

The Phase 4 failures require two upstream fixes:
1. **Platform guards:** `TestH7R5R2ExecutableHarness` WSL and CRLF tests
   need `@pytest.mark.skipif(sys.platform != 'win32', ...)` or equivalent
   Linux-compatible assertions.
2. **Test isolation:** `test_property_token_roundtrip_integrity` needs
   investigation of why preceding tests contaminate its Hypothesis state.
   The test passes consistently when run in a fresh process.

After these fixes, the candidate should achieve a fully green Phase 4.

## 8. Verification

Report branch `reports/dc12r1-h7-r15-r4-r1-v3-lubuntu-native-zero-red-2026-08-14`; local and remote HEAD SHA identical (verified post-push).
