# DC-12R1-H7-R14-V1 — Kilo Final Bounded Source Review

**Verdict:** `PASS_FOR_CTO_DC12R1_H7_R14_V1_KILO_FINAL_REVIEW`

> This is a **source-review approval only**. It is not native Linux verification,
> deployment approval, or merge approval. The program-level gate
> (`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`) in
> `docs/ai/CTO_CURRENT_OPS.md` remains in force; Lubuntu native V4 zero-red is
> still required before any CTO merge consideration.

## 1. Exact reviewed SHAs

| Role | SHA |
|---|---|
| Protected baseline (`origin/product-dev-recovered`) | `a6ef3aac0ab03615e9d70e08e504b9858baf61c5` |
| R13 direct predecessor | `5a27e56ddcd1dff79b9cba780e34cdd5b71bdfe7` |
| **Frozen R14 candidate** | `b2b08ab01b072b7296e5c38dafda5ecfae76f9ad` |
| Source branch (`origin/zcode/...-2026-08-12`) tip | `b2b08ab0...` (== candidate) |
| Lubuntu R13-V2 STOP report | `bb930c9e` |
| Corrected Kilo R13 review | `cf04a51fc170b38c91a853b175ef6e0aaf424c63` |

Proof gate (Phase 1): all pass.
- `git fetch --all --prune` — clean.
- Candidate detached worktree created at `b2b08ab0`, tree clean (no modifications, no untracked).
- Candidate == source-branch tip (`b2b08ab0` == `b2b08ab0`). ✓
- `origin/product-dev-recovered` == `a6ef3aac` (unchanged). ✓
- Candidate direct parent == `5a27e56d` (R13). ✓
- Protected baseline is an ancestor (`git merge-base --is-ancestor` exit 0). ✓

## 2. Exact five-file R14 scope (R13 `5a27e56d` → R14 `b2b08ab0`)

`git diff --name-status 5a27e56d..b2b08ab0` → exactly 5 files, all `M`:

1. `backend/scripts/setup.sh`
2. `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`
3. `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`
4. `docs/ai/PROJECT.md`
5. `docs/ai/CTO_CURRENT_OPS.md`

No additions/deletions; no forbidden path in the delta. ✅

## 3. Immutable-file proof (byte-identical R13 → R14)

`git diff --quiet R13 R14 -- <path>` exit 0 (EQUAL) for every path below; blob
hashes confirmed identical:

| Path | Blob |
|---|---|
| `backend/scripts/setup_preflight.py` | `76ead580be3fea5231ef67e4d660d4faf8447844` |
| `backend/tests/test_dc12r1_h7_setup_preflight.py` | `e79328cecf852ba9fee8703eae158d4ebdb9e076` |
| `backend/alembic.ini` | `34798ccaf845e9cd5fe830fbc700fc696492888c` |
| `backend/alembic/env.py` | `1c71de789e803edff495950fb95edc93b900dfe7` |
| `backend/alembic/**` | (no diff) |
| `backend/api/**`, `core/**`, `models/**`, `schemas/**`, `services/**` | (no diff) |
| `backend/requirements.txt` | `ca999e85486c35318ec7f7a8ae84b25624ee310b` |
| `backend/pyproject.toml` | `422935cb72ae7bac53a91e521dc4af690568a089` |
| `backend/poetry.lock` | `d93314ce8ed569ffb80d66ba522e294afe955dbb` |
| `backend/Dockerfile` | `c75f9fdc7386cd0a9b522a05b2c9a88b6d7b5ca7` |
| `docker-compose.yml` | `2cc2dd5743b7ad26c82816df06af6e02a8d440b4` |
| `docker-compose.override.yml` | `1b632b391ae68a4e6fa851eb333e0299ab111401` |
| `docker-compose.prod.yml` | `f5f11ee572c61b557fd012d93bc83db666264dd3` |
| `backend/tests/test_token_properties.py` | `ae6322eeb00bb0cf8dc366f679fb0f2cebd1e864` |
| `.gitattributes` | `58cc52523243c1550ee5f6fe701b96a16663b3b0` |
| `backend/.env.example` | `cb6976e8ec5e9525b2e86098f2d0534df3384456` |

Changed files correctly DIFFER: `setup.sh` `f1acbcb6…`→`2e799d6f…`; parity test
`16b1602d…`→`0c080eff…`. ✅

## 4. Setup-path analysis (`backend/scripts/setup.sh`, 146 lines)

| # | Requirement | Evidence | Result |
|---|---|---|---|
| 1 | Compose preflight before side effects | L54-71 preflight; side effects start L76 | PASS |
| 2 | Post-install preflight before export | L106-107 post-install; export L119 | PASS |
| 3 | `DATABASE_URL` via `parse_env_file()` | L116 `python -c "...from setup_preflight import parse_env_file..."` | PASS |
| 4 | No second handwritten parser | only `parse_env_file` reads `.env`; `grep CHANGE_ME` is a sentinel check, not a value parser | PASS |
| 5 | No `source`/`.`/`set -a`/broad export | `set -Eeuo pipefail` (L3); only `export DATABASE_URL` (L119) | PASS |
| 6 | Captured in a quoted variable | `_NATIVE_DB_URL="$(...)"` (L116) | PASS |
| 7 | Non-empty before export | L118 `[ -n "$_NATIVE_DB_URL" ] \|\| exit 1` | PASS |
| 8 | Exported before `alembic upgrade head` | export L119; `alembic upgrade head` L122 | PASS |
| 9 | Alembic overrides `alembic.ini` via env | `backend/alembic/env.py` L30-38 `os.environ.get("DATABASE_URL")` → `set_main_option` | PASS |
| 10 | Bootstrap after Alembic, same value | L122 alembic, L125 bootstrap; same `DATABASE_URL` env | PASS |
| 11 | No intermediate reassignment | no reassignment between L119 and L125 | PASS |
| 12 | Unset after bootstrap | L129 `unset DATABASE_URL _NATIVE_DB_URL` | PASS |
| 13 | Exact Alembic/bootstrap failure exit | `set -e` + `ERR` trap → `_on_err` → `exit`; no `\|\|` on alembic/bootstrap | PASS |
| 14 | No URL/password/.env line printed | no `echo` of the variables (L7/24/117/118 only print status text) | PASS |
| 15 | `DATABASE_URL` not on argv | alembic L122, bootstrap L125 carry no URL; value is env-only | PASS |
| 16 | Compose isolation / `--env-file` intact | `COMPOSE=(... --env-file "$BACKEND_ENV")` (L48); used for config/up/exec; `COMPOSE_PROJECT_NAME` never assigned | PASS |

## 5. Secret / process-boundary analysis

- `setup.sh` does **not** enable `xtrace` (no `set -x`). ✅
- Python receives only script/import text + path args: L15 (CRLF self-check),
  L67-68 (`setup_preflight.py --env-file <path>`), L106 (`--post-install`),
  L116 (`-c "<script>" "$SCRIPT_DIR"` — path only, no URL),
  L125 (`bootstrap_tenant_schema.py <schema>`). ✅
- Command-substitution output is captured (`_NATIVE_DB_URL="$(...)"`), not printed. ✅
- Alembic and bootstrap receive `DATABASE_URL` only through the process
  environment. ✅
- Failure of Alembic/bootstrap terminates the process (non-zero) and the setup
  shell (`set -e` + `ERR` trap). ✅
- `unset` after bootstrap removes both variables from the setup process. ✅
- Sentinel tests inspect argv (command log), stdout and stderr independently
  (`test_unique_sentinel_absent_from_all_captures`, `test_no_secret_in_output`,
  `test_alembic_and_bootstrap_use_validated_env_url`). ✅
- **No credential disclosure; no secret-bearing argv.** ✅

## 6. Test authenticity — R14 executable harness

New block `native Alembic connection context (R14)` (test file L1525-1618).
Each mutation uses `_run_mutated`/`_run_mutated_standalone`, which:
- reads the REAL `SETUP_SH`, asserts `mutated != original` (proves the statement
  changed), writes mutated bytes, then runs the REAL `setup.sh` via subprocess;
- the enforcing fakes (`alembic`/`python`→bootstrap) compare `$DATABASE_URL`
  against `grep '^DATABASE_URL=' .env` — identity enforced from `.env`, NOT
  source text; neither fake merely inspects source.

| Required case | Test | Result |
|---|---|---|
| 1. Validated URL reaches Alembic & bootstrap | `test_alembic_and_bootstrap_use_validated_env_url` | GREEN (rc 0) |
| 2. Remove export → Alembic fails | `test_mutation_remove_db_url_export_fails` | RED (rc≠0) |
| 3. Export after Alembic → Alembic fails | `test_mutation_db_url_export_after_alembic_fails` | RED (rc≠0) |
| 4. Wrong URL → Alembic fails | `test_mutation_wrong_db_url_alembic_fails` | RED (rc≠0) |
| 5. Wrong URL between Alembic & bootstrap → bootstrap fails | `test_mutation_wrong_db_url_bootstrap_fails` | RED (rc≠0) |
| 6. `DATABASE_URL` removed from `.env` → fails before Alembic | `test_missing_db_url_in_env_fails_before_alembic` | RED (rc≠0) |
| 7. Exit 42/43/44 preservation | `test_alembic_exit_42_preserved`, `test_bootstrap_exit_43_preserved_no_pnpm`, `test_pnpm_exit_44_preserved` | GREEN |
| 8. Sentinel absent from argv/log/stdout/stderr | `test_unique_sentinel_absent_from_all_captures` + others | GREEN |

No `skip`/`xfail`/conditional pass/assertion weakening (grep: only legitimate
`try/except` in parser code). ✅

## 7. Inherited closures preserved

Verified unchanged from R13: all 19 immutable paths byte-identical (§3);
`docker-compose.yml` has **no** `container_name`; `COMPOSE_PROJECT_NAME` never
assigned (caller-controlled preserved); all `config` operations run **after** the
`--env-file`-bearing `COMPOSE` array (L48) is constructed; `set -Eeuo pipefail`
+ `ERR` trap fail-closed; pinned dependency parity intact
(`requirements.txt`/`poetry.lock` unchanged, `cryptography==46.0.5`); Hypothesis
test and health-check handling not touched by R14 scope. ✅

## 8. Commands actually executed

```
git fetch --all --prune
git worktree add --detach <wt> b2b08ab0
git rev-parse <candidate/source/protected/parent/ancestor checks>
git diff --name-status 5a27e56d..b2b08ab0
git diff --quiet 5a27e56d b2b08ab0 -- <19 immutable paths>   # all exit 0
git rev-parse <blob hashes for changed + immutable files>
Select-String backend/alembic/env.py, setup.sh, parity test   # parser/secret checks
bash -n backend/scripts/setup.sh                             # exit 0
detect-secrets scan --baseline .secrets.baseline <5 files>   # exit 0
git diff --check 5a27e56d b2b08ab0                          # exit 0
python -m py_compile backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py  # exit 0
gitnexus status; gitnexus analyze; gitnexus status          # up-to-date
UTF-8/mojibake scan of 5 files                              # clean
pre-commit run --files <5 files>                            # Passed (baseline restored)
poetry run pytest tests/test_dc12r1_h7_setup_preflight.py -q            # 133 passed
poetry run pytest ...::TestH7R5R2ExecutableHarness -q                  # 35 passed
poetry run pytest preflight + parity -q                              # 260 passed / 2 failed
poetry run pytest parity + preflight -q                              # 260 passed / 2 failed
```

## 9. Runtime counts and host limitations

| Gate | Expected | Kilo result | Classification |
|---|---|---|---|
| Direct preflight (`test_dc12r1_h7_setup_preflight.py`) | 133 passed | **133 passed** | GENUINE GREEN |
| Executable harness (`TestH7R5R2ExecutableHarness`) | 35 passed, 0 skip/xfail | **35 passed, 0 skip/xfail** | GENUINE GREEN |
| Complete H7 (preflight first) | 262 passed | **260 passed, 2 failed** | HOST_ENVIRONMENT_LIMITATION |
| Complete H7 (parity first) | 262 passed | **260 passed, 2 failed** | HOST_ENVIRONMENT_LIMITATION |

The 2 failures are **`TestH7R4InstalledRuntime::test_installed_version_matches_manifest[cryptography-46.0.5]`** and
**`test_cryptography_import_and_version`** — they assert the *installed*
`cryptography == 46.0.5`, but the Kilo poetry venv provisioned **46.0.4**
(`AssertionError: assert '46.0.4' == '46.0.5'`). This is the documented Kilo
host limitation (`cryptography 46.0.4` vs pinned `46.0.5`). **R14 did not
change any dependency** (`requirements.txt`/`poetry.lock` byte-identical), so
this is **not an R14 defect** and must **not** be read as a zero-red result. On
the Lubuntu host (correctly provisioned with `46.0.5`) the candidate expects
262/262, consistent with the candidate doc's stated count.

Git Bash (`C:\Program Files\Git\usr\bin\bash.exe`) is present on this host, so
the executable harness ran for real (not fail-closed on missing bash).

## 10. GitNexus result

`gitnexus status` was **stale** (indexed `872250b`, current `cf04a51`);
`gitnexus analyze` re-indexed successfully (`15029 nodes`, `cf04a51`,
**up-to-date**). No `detect_changes`/`diff` subcommand exists, so exact
`git diff` (§2/§3) is the authoritative scope evidence. ✅

## 11. Quality gates

| Gate | Result |
|---|---|
| `bash -n setup.sh` | exit 0 (syntax valid; LF-only blob confirmed by `test_launcher_crlf_enforcement`) |
| `py_compile` changed test | exit 0 |
| `git diff --check` (R13→R14) | exit 0 (no whitespace errors) |
| `detect-secrets` (scoped, baseline) | exit 0 (sentinels allowlisted) |
| `pre-commit` (scoped, 5 files) | Passed; `.secrets.baseline` auto-edit restored, tree byte-identical after |
| UTF-8 / mojibake scan | clean (no `U+FFFD`, no CRLF in setup.sh) |
| GitNexus analyze/status | up-to-date |

## 12. Final adversarial self-review (Phase 9)

1. **Alembic fallback to `alembic.ini`?** No — `env.py` (`os.environ.get("DATABASE_URL")`) overrides `sqlalchemy.url`; setup exports `DATABASE_URL` before `alembic upgrade head`. ✅
2. **Alembic/bootstrap different URLs?** No — both read the single exported `DATABASE_URL`; fakes enforce equality with `.env`. ✅
3. **Quoted/special-char password breaks assignment?** No — value is captured in double quotes (`_NATIVE_DB_URL="$(...)"`) and passed only via env; no word-splitting. ✅
4. **URL enters argv/logs?** No — argv carries paths only; sentinel absent from log/stdout/stderr (proven by tests + runtime). ✅
5. **Missing `DATABASE_URL` reaches Alembic?** No — non-empty check (L118) and `.env`/post-install preflight stop before Alembic. ✅
6. **Parse failure swallowed?** No — `parse_env_file` raises; `_NATIVE_DB_URL` empty → exit. ✅
7. **Alembic failure continues to bootstrap?** No — `set -e` + `ERR` trap. ✅
8. **Bootstrap failure continues to frontend?** No — `set -e` propagates. ✅
9. **Successful setup retains `DATABASE_URL`?** No — `unset DATABASE_URL _NATIVE_DB_URL` (L129). ✅
10. **Forbidden file modified?** No — all 19 immutable paths byte-identical. ✅
11. **Five mutation tests genuinely RED?** Yes — each mutates the real script, runs it, and the enforcing fake fails; verified rc≠0. ✅
12. **Document overclaim (native Linux/deploy/Playwright/VPS/merge)?** No — R14 docs state **NO PASS** and `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`; merge deferred to Lubuntu V4. The doc's "262/262" reflects the Lubuntu-expected count; Kilo measured 260/262 solely due to cryptography 46.0.4 (host limit). ✅
13. **Candidate tree clean & byte-identical after review?** Yes — `git diff --quiet HEAD` exit 0; pre-commit baseline restored. ✅

## 13. Finding accounting (gap = 0)

15 findings recorded (see `2026-08-13_dc12r1_h7_r14_v1_kilo_findings.csv`).
14 PASS/verification, **0 defect**, **1 HOST_ENVIRONMENT_LIMITATION** (not an
R14 defect). Accounting gap = 0.

## 14. Worktree cleanup proof

Detached candidate worktree at
`C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1_h7_r14_v1_review`:
- After review + pre-commit restore: `git status --porcelain` empty,
  `git diff --quiet HEAD` exit 0, HEAD = `b2b08ab0`.
- Worktree removed via `git worktree remove --force`; `git worktree prune`.
- No temp/orphaned review directories remain.

## 15. Report-branch & protected-ref proof

- Branch `reports/dc12r1-h7-r14-v1-kilo-final-review-2026-08-13` created from
  `a6ef3aac` and contains exactly the two deliverable files
  (`git diff a6ef3aac..<branch>` = 2 files only).
- Pushed to `origin`; local SHA == remote SHA (verified).
- `origin/product-dev-recovered` remains `a6ef3aac` (untouched).
- Source candidate `b2b08ab0` and all protected refs were **not** modified or
  pushed.

---

**Conclusion:** R14 safely provides the validated `backend/.env` `DATABASE_URL`
to both public Alembic migration and tenant bootstrap, with no second `.env`
parser, no credential exposure (URL is env-only, never on argv/log/stdout/stderr),
no weakening of failure behavior, and no change to forbidden files.
`PASS_FOR_CTO_DC12R1_H7_R14_V1_KILO_FINAL_REVIEW` (source-review approval only).
