# DC12R1-H7-R16-R2-V2 — Lubuntu Phase-4 Zero-Red Final

**Date:** 2026-08-14 | **Host:** Lubuntu (Linux x86_64, Ubuntu 24.04) | **Verdict: PASS_DC12R1_H7_R16_R2_V2_LUBUNTU_PHASE4_ZERO_RED_FINAL**

## Verdict summary

All Phase 4 zero-red requirements met: 325/325 passed in both natural and
reverse file order, 6/6 Hypothesis executions green, all quality gates clean.
The R16-R2 candidate resolves the three R15-R4-R1 failures (two
platform-specific launcher tests + one Hypothesis test-isolation issue) with
changes confined to 2 test files and 3 doc files — all product code,
setup.sh, manifests, migrations and lockfiles are byte-identical to R15.

## 1. Phase 1 — Proof gate (ALL PASS)

| Proof | Result |
|---|---|
| Source branch tip | `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12` = `a0a14e4d` ✓ |
| Frozen candidate | `a0a14e4d7bbfdc2aef154810202c3ba93b633c50` = commit "DC-12R1-H7-R16-R2: CRLF guard fail-closed authenticity (NO PASS)" ✓ |
| Direct parent | `git rev-list --parents -n1 a0a14e4d` → parent = `cb4fab66e587017893d790877d381e006e1aaf5c` ✓ |
| R15 candidate ancestor | `fd7727f8` is ancestor of `a0a14e4d` ✓ |
| Protected baseline | `a6ef3aac0ab03615e9d70e08e504b9858baf61c5` = commit, ancestor of `a0a14e4d` ✓ |
| Kilo review | `8b04a92bf6c58597d105f743b3105e37b5fabc32` = commit ✓ |
| Accepted native Phase 3 | `189852dae83e5d76fed6141e2375d1b37023d2ec` (R15-R4-R1-V3 report) ✓ |

### Aggregate delta `fd7727f8..a0a14e4d` — exactly 5 authorized files

| # | File | Lines |
|---|---|---|
| 1 | `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md` | +47 |
| 2 | `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py` | +168 −19 |
| 3 | `backend/tests/test_token_properties.py` | +12 −3 |
| 4 | `docs/ai/CTO_CURRENT_OPS.md` | +3 −1 |
| 5 | `docs/ai/PROJECT.md` | +2 −1 |

### Byte-identity proof (fd7727f8 → a0a14e4d)

All governed paths are byte-identical (blob-SHA equality):

`backend/scripts/setup.sh` ✓ | `backend/scripts/setup_preflight.py` ✓ |
`docker-compose.yml` ✓ | `docker-compose.override.yml` ✓ |
`backend/alembic.ini` ✓ | `backend/alembic/env.py` ✓ |
`backend/requirements.txt` ✓ | `backend/.env.example` ✓ |
`frontend/package.json` ✓ | `frontend/pnpm-lock.yaml` ✓

Clean detached checkout at `a0a14e4d`, `git status --porcelain` empty.

## 2. Phase 2 — Clean test environment (PASS)

- **Python venv:** 3.12.3, task-owned.
- **Install:** `pip install -r requirements.txt` (all 70 packages) + test tooling (pytest 9.1.1, hypothesis 6.165.6, pytest-asyncio 1.4.0).
- **No Docker/PostgreSQL/Redis started** — test-only gate.
- **Governed dependency versions:**

| Package | Required | Installed |
|---|---|---|
| bcrypt | 4.0.1 | 4.0.1 ✓ |
| cryptography | 46.0.5 | 46.0.5 ✓ |
| openpyxl | 3.1.5 | 3.1.5 ✓ |
| et-xmlfile | 2.0.0 | 2.0.0 ✓ |
| passlib | 1.7.4 | 1.7.4 ✓ |

## 3. Phase 3 — Natural order (PASS)

```
python -m pytest \
  tests/test_dc12r1_h7_setup_preflight.py \
  tests/test_dc12r1_h7_bcrypt_manifest_parity.py \
  tests/test_token_properties.py -q
```

| Metric | Required | Actual |
|---|---|---|
| collected | 325 | **325** ✓ |
| passed | 325 | **325** ✓ |
| failed | 0 | **0** ✓ |
| errors | 0 | **0** ✓ |
| skipped | 0 | **0** ✓ |
| xfailed | 0 | **0** ✓ |
| exit | 0 | **0** ✓ |

Duration: 86.96s. No health-check suppression, no rerun plugin.

## 4. Phase 4 — Reverse order (PASS)

```
python -m pytest \
  tests/test_token_properties.py \
  tests/test_dc12r1_h7_bcrypt_manifest_parity.py \
  tests/test_dc12r1_h7_setup_preflight.py -q
```

| Metric | Required | Actual |
|---|---|---|
| collected | 325 | **325** ✓ |
| passed | 325 | **325** ✓ |
| failed | 0 | **0** ✓ |
| errors | 0 | **0** ✓ |
| skipped | 0 | **0** ✓ |
| xfailed | 0 | **0** ✓ |
| exit | 0 | **0** ✓ |

Duration: 85.84s. Totals identical to natural order.

## 5. Phase 5 — Hypothesis closure (ALL PASS)

Node: `test_property_token_roundtrip_integrity`

| Run | Mode | Result | Duration |
|---|---|---|---|
| 1 | unseeded | **1 passed** | 0.56s |
| 2 | unseeded | **1 passed** | 0.57s |
| 3 | unseeded | **1 passed** | 0.70s |
| 4 | unseeded | **1 passed** | 0.69s |
| 5 | unseeded | **1 passed** | 0.69s |
| 6 | seed=303296478269760642762159842520761126666 | **1 passed** | 0.47s |

All 6/6 green. No `HealthCheck.too_slow`, no deadline/health-check suppression, no rerun plugin.

## 6. Phase 6 — Quality gates (ALL PASS)

| Gate | Result |
|---|---|
| `py_compile test_dc12r1_h7_bcrypt_manifest_parity.py` | OK ✓ |
| `py_compile test_token_properties.py` | OK ✓ |
| `bash -n backend/scripts/setup.sh` | OK ✓ |
| `git diff --check` | no whitespace errors ✓ |
| UTF-8 encoding (both changed files) | utf-8 ✓ |
| Candidate tree identity | HEAD = `a0a14e4d`, `git status --porcelain` empty ✓ |
| Source branch ref unchanged | `a0a14e4d` before == after ✓ |

## 7. Phase 7 — Cleanup (PASS)

- Clone + venv removed.
- No Docker interaction (test-only gate — no containers, networks, or volumes created).
- Zero task residue.
- Source/protected refs unchanged: source branch = `a0a14e4d` before and after.

## 8. R15 → R16-R2 failure resolution

The R15-R4-R1-V3 gate reported 3 Phase 4 failures. The R16-R2 candidate
resolves all three:

| R15 failure | R16-R2 status |
|---|---|
| `test_launcher_fail_closed_when_only_system32_wsl_bash_exists` (platform-specific) | **PASS** — CRLF guard fail-closed authenticity fix |
| `test_launcher_crlf_mutated_script_fails_before_any_command` (platform-specific) | **PASS** — same fix |
| `test_property_token_roundtrip_integrity` (test isolation in natural order) | **PASS** — passes in both orders and all 6 separate runs |

## 9. Verification

Report branch `reports/dc12r1-h7-r16-r2-v2-lubuntu-phase4-zero-red-2026-08-14`; local and remote HEAD SHA identical (verified post-push).
