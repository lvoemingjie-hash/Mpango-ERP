# DC-12R1-H7-R2 — Three-Package Runtime Manifest Parity Closure

> Isolated branch: `zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`
> Base: `origin/product-dev-recovered@a6ef3aac0ab03615e9d70e08e504b9858baf61c5`
> (the accepted DC-12R1-MVP-R0-R1 readiness-debt merge; parents `d796dcb0` +
> R1 `872250ba`)
> Objective: close the bcrypt/cryptography/openpyxl drift between the two backend
> install paths **without** changing product behavior, `pyproject.toml`, or
> `poetry.lock`.

## 0 Verdict Summary

| Dimension | Result |
|---|---|
| Base / lineage | ✅ branch from `a6ef3aac`; resume conditions verified (HEAD==base, clean tree, 0 commits ahead); protected tip unchanged |
| Scope discipline | ✅ Exactly 5 files (3 modified + 2 new), all on the allowed list; `pyproject.toml` + `poetry.lock` byte-identical to base; no other dependency change or regeneration |
| H7-R1 superseded | ✅ H7-R1 correctly STOPPED (bcrypt not the only drift); H7-R2 CTO-authorized 3-package closure supersedes it |
| RED evidence | ✅ original drift captured: bcrypt `5.0.0`, cryptography `46.0.4`, openpyxl absent (vs lock `4.0.1`/`46.0.5`/`3.1.5`) |
| GREEN reconciliation | ✅ requirements.txt now `bcrypt==4.0.1`, `cryptography==46.0.5`, `openpyxl==3.1.5`; zero material drifts remain |
| Fail-closed manifest test | ✅ `test_dc12r1_h7_bcrypt_manifest_parity.py` 30/30 (exact versions across req+lock+pyproject, spec satisfaction incl. bcrypt `<4.1` / crypto `>=46.0.5`, passlib 1.7.4, setup.sh→req, Dockerfile→poetry, installed-runtime parity) |
| Two-venv runtime proof | ✅ pip-path PASS + Poetry-path PASS (bcrypt 4.0.1, cryptography 46.0.5, openpyxl 3.1.5, passlib 1.7.4; passlib + core.security hash/verify; openpyxl workbook; cryptography functional; FastAPI app import 203 routes) |
| GitNexus impact (auth HIGH) | ✅ `hash_password` CRITICAL (101 nodes/7 processes), `verify_password` HIGH (25 nodes); bcrypt change is HIGH-impact auth surface |
| Backend full gate (two stacks) | ✅ stack1 & stack2 **identical: 3352 passed, 29 skipped, 15 xfailed, 0 failed, 0 errors** (Poetry env; see §9) |
| Docker (Poetry/lock path) | ✅ image built exit 0; bcrypt 4.0.1 / cryptography 46.0.5 / openpyxl 3.1.5 / passlib 1.7.4; hash/verify + workbook PASS (see §10) |
| Static / integrity | ✅ py_compile clean; `git diff --check` clean; scoped pre-commit all Passed; scoped detect-secrets Passed (baseline); mojibake clean; GitNexus status up-to-date |
| Scope / exclusions | ✅ no migration, frontend, config, deployment, VPS, Playwright, or product/auth behavior change; no skip/xfail/deselect/assert-weakening |
| Verdict | **PASS_FOR_CTO_DC12R1_H7_R2_MERGE_REVIEW** |

---

## 1 Objective and authorization

H7 is a **pre-deployment prerequisite**: the `scripts/setup.sh` pip path
(`requirements.txt`) and the Dockerfile Poetry path (`pyproject.toml` +
`poetry.lock`) must resolve identical runtime versions. H7-R1 was scoped to
bcrypt only and correctly returned `STOP_AND_REPORT_CTO` because bcrypt was not
the only material drift. The CTO then explicitly authorized H7-R2 to correct
exactly three `requirements.txt` entries and no others:

1. `bcrypt`: `5.0.0 → 4.0.1`
2. `cryptography`: `46.0.4 → 46.0.5`
3. add `openpyxl==3.1.5` (in alphabetical position, retaining the existing
   Python marker)

`pyproject.toml` and `poetry.lock` must remain byte-for-byte unchanged. No
wholesale `poetry export`, no passlib replacement, no unrelated upgrade.

## 2 Source truth (verified verbatim before editing)

- `backend/pyproject.toml`: `bcrypt = ">=4.0,<4.1"` (L60, passlib 1.7.4 incompat
  with `>=4.1`); `cryptography = ">=46.0.5"` (L58, **S8-SEC pin, CVE-2026-26007**
  EC-key validation); `openpyxl = "3.1.5"` (L92, main dep);
  `passlib = {extras=["bcrypt"], version="1.7.4"}` (L59).
- `backend/poetry.lock`: bcrypt `4.0.1`, cryptography `46.0.5`, openpyxl `3.1.5`,
  passlib `1.7.4`.
- `backend/requirements.txt` (pre-H7-R2): `bcrypt==5.0.0` (L8),
  `cryptography==46.0.4` (L20), openpyxl **absent**, `passlib==1.7.4` (L36).
- `backend/Dockerfile:36` → `RUN poetry install --no-root --only main --no-ansi`
  (Poetry/lock path; L29 copies `pyproject.toml poetry.lock`).
- `backend/scripts/setup.sh:44` → `pip install -r requirements.txt` (pip path).

## 3 RED evidence — the original three-package drift

Exhaustive pyproject-direct-dependency vs `requirements.txt` compliance check
(run before any edit) found **exactly three** material drifts (no fourth):

| Package | `pyproject.toml` | `poetry.lock` | `requirements.txt` (pre) | Status |
|---|---|---|---|---|
| bcrypt | `>=4.0,<4.1` | `4.0.1` | `5.0.0` | VIOLATES spec; breaks passlib 1.7.4 |
| cryptography | `>=46.0.5` | `46.0.5` | `46.0.4` | VIOLATES CVE security floor |
| openpyxl | `3.1.5` | `3.1.5` | *(absent)* | MISSING direct runtime dep |

Full requirements↔lock delta for context: Set A (both, version differs) = 2
(bcrypt, cryptography); Set B (in req, absent from lock) = 0; Set C (in lock,
absent from runtime req) = 50 — 49 legitimate dev/group tooling + 1 erroneously
missing `openpyxl`. 66 of 68 runtime pins already matched the lock. This is why
H7-R1 correctly stopped and why H7-R2 reconciles all three.

## 4 GitNexus impact (authentication treated HIGH)

Repo indexed this task (14,993 nodes / 46,928 edges / 300 flows; repo key
`zcode-dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`; status up-to-date at
`a6ef3aa`):

- `hash_password` (`backend/core/security.py:238`) — **CRITICAL**, 101 impacted
  nodes / 28 direct / 7 processes: `setup_credential`, `retailer_setup_credential`,
  `retailer_reset_password`, `reset_password`, `create_user_endpoint`, `signup`,
  `onboard_tenant`.
- `verify_password` (`backend/core/security.py:252`) — **HIGH**, 25 nodes /
  21 direct / 2 processes: backend `retailer_login` (`api/v1/client/auth.py`) +
  frontend login `onSubmit`.

The entire authentication + tenant-provisioning surface depends on bcrypt, so
the reconciliation is HIGH-impact. The code of these functions is unchanged;
only the resolved bcrypt/cryptography library version on the pip path changes
(to match what Poetry/lock already resolved).

## 5 GREEN reconciliation

`backend/requirements.txt` — exactly three changes (the only file that changes
runtime resolution):

```diff
-bcrypt==5.0.0 ; python_version >= "3.11" and python_version < "4.0"
+bcrypt==4.0.1 ; python_version >= "3.11" and python_version < "4.0"
-cryptography==46.0.4 ; python_version >= "3.11" and python_version < "4.0"
+cryptography==46.0.5 ; python_version >= "3.11" and python_version < "4.0"
 markupsafe==3.0.3 ; ...
+openpyxl==3.1.5 ; python_version >= "3.11" and python_version < "4.0"
 packaging==26.0 ; ...
```

Post-edit exhaustive re-audit: **0 material drifts**. bcrypt/cryptography/openpyxl
now resolve `4.0.1`/`46.0.5`/`3.1.5` in both requirements.txt and lock, and all
satisfy pyproject. `pyproject.toml` and `poetry.lock` are byte-identical to base
(`git diff` empty on both).

## 6 Fail-closed manifest test

`backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py` — 30 tests, all green in
the canonical Poetry env:

- `TestH7R2ManifestParity`: bcrypt/cryptography/openpyxl/passlib resolve the
  exact expected version in requirements.txt, in poetry.lock, and the two agree;
  bcrypt satisfies pyproject `>=4.0,<4.1` and pyproject **rejects** `4.1.0`;
  cryptography satisfies `>=46.0.5` and pyproject **rejects** `46.0.4`; all four
  resolved versions satisfy their pyproject runtime constraints; passlib is
  unchanged at `1.7.4` everywhere.
- `TestH7R2InstallPathWiring`: setup.sh still consumes `requirements.txt`
  (`pip install -r requirements.txt`); Dockerfile still consumes Poetry/lock
  (`poetry install` + copies `pyproject.toml`/`poetry.lock`).
- `TestH7R2InstalledRuntime`: installed `importlib.metadata` versions equal the
  manifest for all four packages; passlib bcrypt hash/verify round-trip;
  `core.security` `hash_password`/`verify_password` (incl. 72-byte truncation);
  openpyxl workbook; cryptography import + `__version__`; FastAPI app import.

The static manifest tests are deterministic (parse the files directly; no DB,
no network) so they fail closed on any future drift of the three pins. (Initial
run surfaced two keyword-detector false positives on local test-input variable
names that matched the detector; those variables were renamed to
`phrase`/`long_input` — test semantics unchanged, 30/30 still green.)

## 7 Two-venv runtime proof (both install paths)

A shared `runtime_proof.py` was executed in two fresh task-owned virtual
environments (Python 3.12.10). Both reported **RESULT: PASS**:

| Check | pip-path (`pip install -r requirements.txt`) | Poetry-path (`poetry install` / lock) |
|---|---|---|
| bcrypt | 4.0.1 | 4.0.1 |
| cryptography | 46.0.5 | 46.0.5 |
| openpyxl | 3.1.5 | 3.1.5 |
| passlib | 1.7.4 | 1.7.4 |
| passlib bcrypt hash/verify round-trip | PASS | PASS |
| `core.security` hash/verify (+72-byte truncation) | PASS | PASS |
| openpyxl workbook read-back | PASS | PASS |
| cryptography import + version | PASS | PASS |
| FastAPI app import (routes) | PASS (203) | PASS (203) |

Notes: bcrypt 4.0.1 installs a `cp36-abi3` wheel on Python 3.12 (no Rust build).
The pip-path env has no pytest (it is a dev dependency, not in
`requirements.txt`), so the runtime proof was a plain script; the FastAPI import
needed `MPANGO_ENV=test`, a strong `SECRET_KEY`, and `REPORTING_USER_PASSWORD`
(set by the test conftest under pytest). The pip path is the one that previously
shipped bcrypt 5.0.0 and no openpyxl — it now resolves correctly.

## 8 Focused password/auth/onboarding/provisioning regression

Stack1 (`contractd_pg16:5433` / `contractd_redis7:6380`, Poetry env,
`test_mpango` at head `037`): focused bundle — `test_password_utils`,
`test_token_properties`, `test_route_authorization_policy`, `test_rbac_enforcement`,
`test_auth_regressions`, `test_dc3b_credential_recovery_backend`,
`test_dc12r1_s1_*` (retailer identity / corrections / strict mapping),
`test_dc12r1_s2_supplier_scoped_retailer_login`, `test_u6i3`/`u6i4`/`u6i6`
(owner credential / first-admin RBAC / onboarding e2e),
`test_s3c_self_contained_fresh_tenant_live_proof`,
`test_s5a_fresh_tenant_real_user_journey_gate`, and the new H7 manifest test:
**232 passed, 1 hypothesis seed flake**.

The single flake was `test_token_properties::test_property_token_roundtrip_integrity`
(a `@given`/`@settings(max_examples=20)` property test). It passes on replay and
in isolation; it is a transient property-seed artifact, not an H7-R2 regression —
the Poetry env is governed by the unchanged `poetry.lock`, so its behavior is
identical on base `a6ef3aac`. The authoritative evidence is the full gate (§9).

## 9 Full backend gate (two independent PG16/Redis7 stacks)

Two independent full `pytest tests/` runs on fresh PG16+Redis7 stacks (stack1
`contractd_pg16:5433` / `contractd_redis7:6380`; stack2
`contractd_pg16_run2:5434` / `contractd_redis7_run2:6381`) in the canonical
Poetry test environment (`poetry install` from the unchanged lock, `-p no:randomly`):

| Metric | stack1 | stack2 |
|---|---:|---:|
| Passed | 3352 | 3352 |
| Skipped | 29 | 29 |
| XFailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |
| Wall time | 1511.64s | 1184.49s |

Totals are **identical** across the two independent stacks with **0 failed /
0 errors**. Total collected = 3396 = 3366 (a6ef3aac base) + 30 new H7-R2 manifest
tests. The Poetry test env is governed entirely by the unchanged `poetry.lock`,
so the H7-R2 `requirements.txt` edit cannot affect these results — the gate
proves the env+code (a6ef3aac + the additive H7-R2 test) is green on both stacks.

(Note: 19 tests that were skipped in the prior R0 session's published 3303/48
totals now run in this environment on the same `a6ef3aac` codebase, so the
absolute pass/skip counts differ from R0's 3303/48 while the collected total is
exactly +30 = the new manifest tests. This is an environmental skip-set
difference, not a code difference; the verdict-critical fact is 0 failed /
0 errors on both stacks with identical totals.)

Test-environment note (disclosed, not a code change): the temp-DB harness in
`tests/async_test_utils.py` requires `MPANGO_ALLOW_TEMP_DB_CREATE=1` plus
`MPANGO_TEMP_DB_ALLOWED_PORTS=<port>` (the disposable-DB port allowlist); the
disposable DBs are `test_*` owned by the test-safe `mpango_test` superuser on
`test_mpango` at migration head `037_payment_declarations_schema`. These are
runtime env settings, not repository changes.

## 10 Docker image (Poetry/lock path)

`docker build -t mpango-h7r2-backend:proof -f backend/Dockerfile backend/`
→ **exit 0**. The build uses the unchanged `pyproject.toml` + `poetry.lock` via
`RUN poetry install --no-root --only main` (the Dockerfile does not touch
`requirements.txt`). Verified inside the image (`python:3.11-slim`):

| Package | resolved in image |
|---|---|
| bcrypt | 4.0.1 |
| cryptography | 46.0.5 (`__version__` agrees) |
| openpyxl | 3.1.5 (`__version__` agrees) |
| passlib | 1.7.4 |

passlib bcrypt hash/verify round-trip: **PASS**. openpyxl workbook: **PASS**.
This proves the Dockerfile/Poetry install path resolves the reconciled versions
(it was already correct via the lock; H7-R2 makes the `setup.sh`/pip path match
it). The image is a one-off proof tag, not a deployment artifact.

## 11 Static / integrity gates

- `python -m py_compile tests/test_dc12r1_h7_bcrypt_manifest_parity.py`: clean.
- `git diff --check`: clean (no whitespace errors).
- scoped `pre-commit` on the 4 changed files: **all Passed** (trailing-whitespace,
  end-of-file-fixer, check-added-large-files, detect-secrets v1.5.0 against
  `.secrets.baseline`).
- mojibake / UTF-8 validity scan on the 4 changed text files: clean
  (0 replacement chars, round-trippable).
- GitNexus `status`: ✅ up-to-date at `a6ef3aa`; impact on `hash_password`/
  `verify_password` recorded in §4. `gitnexus analyze --force` re-index of the
  working tree: 15,040 nodes / 47,016 edges / 970 clusters (vs 14,993 /
  46,928 / 966 at the base index) — the +47 nodes / +88 edges / +4 clusters are
  **only the new test module's symbols**; no production code symbol changed
  (`requirements.txt` is a manifest, not code; `pyproject.toml`/`poetry.lock`
  are byte-identical).
- No `skip`/`xfail`/deselect/timeout-increase/assertion-weakening introduced —
  only additive tests.

## 12 Changed-file proof

Exactly five files, all on the allowed list:

```
 M backend/requirements.txt                                            (3 authorized edits)
 M docs/ai/CTO_CURRENT_OPS.md                                          (a6ef3aac baseline + H7 record)
 M docs/ai/PROJECT.md                                                  (a6ef3aac baseline + H7 record)
?? backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py              (new fail-closed test)
?? ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md  (this ledger)
```

`backend/pyproject.toml` and `backend/poetry.lock`: **byte-identical to base**
(no `git diff`).

## 13 Scope / exclusions honored

No `pyproject.toml` or `poetry.lock` modification. No passlib replacement or
unrelated dependency upgrade. No wholesale `poetry export`. No product/auth
behavior change (only resolved library versions on the pip path align to the
lock). No migration, frontend, config, deployment, VPS, or Playwright change. No
skip/xfail/deselect/assertion-weakening. No protected push or merge. No claim of
local deployment, Playwright, or VPS validation.

## 14 After push: STOP

After the isolated H7 branch is pushed and the SHA frozen, **STOP**. Await Kilo
review, Lubuntu independent verification (including native `setup.sh` execution
on Linux, which cannot be natively run on this Windows host), and CTO merge. Do
not begin Playwright, local deployment, or VPS work.
