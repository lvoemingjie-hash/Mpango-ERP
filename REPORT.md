# REPORT — DC-12R1-MVP-L1-J1-H2-C-I1-R1-V1
## Lubuntu OpenCode2 Independent Fresh-Runtime Backend and Browser Authority Final

> **E1 EVIDENCE-TRUTH CORRECTION APPLIED (this revision).**
> **ORIGINAL_RUNTIME_VERDICT:** `STOP_AND_REPORT_CTO_WITH_FIRST_AUTHENTIC_RED` (preserved verbatim below and in the base report `0f6f790b…`, which remains byte-identical and published).
> **EFFECTIVE_VERDICT: `VOID_ENVIRONMENT_PRECHECK`** — every one of the 88 red nodes is deterministically attributable to executor-environment omissions (CWD=25, `MPANGO_TEMP_DB_ALLOWED_PORTS`=57, unsafe test DB name=6; gap=0); none is a product defect. The "Phase 2 Preflight PASS" and the "Phase 4 Authoritative Backend Run" are WITHDRAWN as authoritative results. The 3784-executed fact is retained but carries **no product-attribution validity**. Full forensic basis: `E1_EVIDENCE_TRUTH_CORRECTION.md`. The expected PASS verdict
> (`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I1_R1_V1_LUBUNTU_OPENCODE_INDEPENDENT_BACKEND_AND_BROWSER_FINAL`)
> remains **NOT** awarded. VOID does not constitute a product, candidate, or test RED; the browser authority run was **NOT** executed, nothing was rerun, nothing was retried, the candidate was never modified.
>
> Sections below are the ORIGINAL report retained for evidence truth; superseded labels are annotated in place.

**ORIGINAL VERDICT LINE (preserved): `STOP_AND_REPORT_CTO_WITH_FIRST_AUTHENTIC_RED`**

- **CANDIDATE:** `42c5d3286cacaf48604550eecd881e379cc76818` (remote tip
  `origin/zcode/dc12r1-mvp-l1-j1-h2-c-i1-r1-actual-current-baseline-integration-2026-08-29`)
- **PARENTS:** P1 `cdb39e96a50b308aff91d4e94fd8526e7540d921` (= `origin/product-dev-recovered`), P2 `e2274af7816b80d0efb83a8294b2c6503e246b19` (harness source)
- **TREE:** `b89bf1dfe522506fc3084f53b48b27e5094614bb` (exact match)
- **SCOPE DELTA:** product-dev-recovered..CANDIDATE = exactly 49 paths
- **KILO REFS (undrifted at open and close):** product `f5fdf187fab88f628a6b2f3aca80d03d3be60054`; harness source `e2274af7…`; harness Kilo `1d1d4f22ccb30088d188b23a4b55e4254541e253` (parent = harness source)
- **EXECUTOR:** OpenCode2 (Lubuntu host, independent), 2026-08-29
- **VERIFICATION_TIER:** `V4_INDEPENDENT_LINUX_AUTHORITY`
- **CLAIM_CEILING:** `INDEPENDENT_FRESH_RUNTIME_BACKEND_AND_BROWSER_EVIDENCE_ONLY`

---

## Phase 1 — Proof Gate: PASS

`git fetch --all --prune` rc=0. Remote candidate tip equals
`42c5d328…` exactly (one branch). Parents, tree SHA, 49-path scope set,
`origin/product-dev-recovered == cdb39e96…`, product Kilo `f5fdf187…`,
harness source `e2274af7…`, harness Kilo `1d1d4f22…` (report-only delta
`findings.csv`+`review.md` over the harness source) — all present and
byte-identical local==remote at open and at close. Fresh detached
worktree created from CANDIDATE; `git status --porcelain` = 0 before,
during (runtime debris removed) and after.

## Phase 2 — Fail-Closed Preflight: PASS **[WITHDRAWN BY E1 — see §3 of E1_EVIDENCE_TRUTH_CORRECTION.md]**

Task-exclusive fresh stack (pre-gate `dc12r1i1f-*`, authority
`dc12r1i1a-*`; both destroyed at close):

| Item | Value |
|---|---|
| PG16 | `postgres:16-alpine`, `127.0.0.1:17432`, fresh random superuser secret |
| pytest role | `i1run` — live `pg_roles` truth: `rolsuper=false`, `rolcreatedb=true`, `rolreplication=false`, `NOINHERIT`; `rolcreaterole=true` (see role-matrix note below) |
| migration admin | independent bootstrap admin (`i1setup`, container-scoped superuser) created `reporting_role`/`reporting_user` before any suite/pytest contact; pytest role privileges never altered after provisioning |
| Alembic | fresh empty DB → `upgrade head` as `i1run` → unique head `037_payment_declarations_schema` |
| Redis7 | `127.0.0.1:17379`, DB15 `DBSIZE=0` before and after; sentinel `26379` unreachable (ConnectionRefused) throughout |
| Runner env | `TEST_DATABASE_URL` derived inside the runner process (non-empty, presence-proven); `MPANGO_ALLOW_TEMP_DB_CREATE=1` proven in BOTH runner (`authority-preflight.json.presence`) and the child `pytest_sessionstart` proof |
| Task email | `*@task-mail.dc12r1i1.dev` (registrable label non-special-use); offline-validated against the candidate's installed pydantic `SignupRequest` (`EmailStr`): accepted; `localhost` probe rejected |

Role-matrix note (documented provisioning, executed by the setup admin
BEFORE any test contact): PG16 requires `CREATEROLE` **plus** `ADMIN
OPTION` for any role to `ALTER ROLE reporting_role/reporting_user`
(migration 011 steps and the suite's reporting-password alignment). The
pytest role received `CREATEROLE` + `ADMIN OPTION` memberships with
`NOINHERIT` — zero privilege inheritance, zero superuser, live
`rolsuper=false rolcreatedb=true` as required. Empirically verified in
the live PG16 before the round proceeded.

Runner formal preflight (`--preflight-only`, `AUTHORITY_H2C_BACKEND`,
`--baseline-sha e2274af7…`): **PASS**, `state=PREFLIGHT`, rc=0, on the
fresh authority stack. Evidence: `evidence/runner/`.

## Phase 3 — Independent Pre-Gates: ALL GREEN

| Gate | Result |
|---|---|
| Backend H2-C focused bundle, natural order | **49/49 PASS** (103.10s) |
| Backend H2-C focused bundle, file-reverse order (R2-ledger semantic, as adjudicated in the V2 round of this lineage) | **49/49 PASS** (72.35s) |
| Backend bundle, strict whole-list file reversal — executor extra-diagnostic, NOT a gate | 38 passed + 11 errors: the H2-C module's own fail-closed module-entry gate ("dev retailer email sink is not empty at module entry") fires because S1-family modules leave in-process sink residue; identity's last test is the zero-email neutral test, which is exactly why the ledger-defined order ends with it. Recorded for honesty; no rerun performed. |
| Frontend focused bundle (4 files), natural order | **59/59 PASS** |
| Frontend focused bundle, reverse order | **59/59 PASS** |
| `pnpm build` | PASS |
| `j1h2c-retailer-recovery` `pnpm install --frozen-lockfile` | PASS |
| `playwright test --list` | exactly **15 tests / 1 serial spec**, ordered-equal with inventory browser rows |
| `validate:static` | **11/11 PASS** |
| `check:neutrality` G1–G6 | PASS |
| `check:runtime-contracts` | PASS |
| `tsc --noEmit` | PASS |

Environment note (harness gates): `NODE_OPTIONS=--no-experimental-strip-types`
was required — Node 22.23.2's native TS type-stripping preempts Playwright
1.49.1's babel transform and breaks ESM linking of type-only imports.
Frozen harness bytes were never modified.

## Phase 4 — Single Authoritative Backend Run: **AUTHENTIC RED** **[WITHDRAWN BY E1 — reclassified VOID_ENVIRONMENT_PRECHECK; 88/88 red nodes executor-environment-attributed (CWD=25, TEMP_DB_PORTS=57, DB-name=6, gap=0); no product-attribution validity]**

Executor invocation-defect disclosure (VOID, zero tests executed, zero
results farmed):

1. `VOID-launch1-missing-authority-flag.log` — first launcher invocation
   omitted `--authority`; the runner correctly refused to proceed past
   AUTHORIZED and launched pytest **0** times.
2. `VOID-launch2-*` — second invocation ran pytest from the worktree
   root with `tests/` (cwd coupling); pytest collected nothing, ran no
   tests (`tests="0"` in the archived JUnit), exit 4.

Neither invocation executed a single test. Both retained verbatim and
classified `VOID_EXECUTOR_INVOCATION_DEFECT`. The authoritative launch
below is the ONLY invocation in which pytest executed tests.

**The authoritative launch (one and only one):**

- Runner: HE2-ET1 authority runner, `AUTHORITY_H2C_BACKEND` profile,
  `--baseline-sha e2274af7…`, from the candidate worktree root
- `sentinel_calls=1` (published proof, `authority-preflight.json`),
  `collect_child_spawns=1`, nonce cross-match true, candidate/profile/
  manifest SHA bindings all true, `state=FINISHED`
- Product collect-only freeze performed BEFORE the run: **3784 nodes**
  (this candidate's real count; the historical 3773 was never assumed)
- Console summary line (verbatim): `67 failed, 3602 passed, 79
  skipped, 15 xfailed, 12536 warnings, 21 errors in 1523.60s (0:25:23)`
- `RUN_VERDICT=TEST_RED_REAL_COMMAND_NONZERO exit=1` — real test RED;
  environment stays FINISHED, never VOID

### Reconciliation (gap = 0)

| Count | Value |
|---|---|
| collected (frozen baseline) | 3784 |
| executed (JUnit `tests`) | 3784 |
| passed | 3602 |
| failed | 67 |
| errors | 21 |
| skipped | 79 |
| xfailed | 15 |
| xpassed | 0 |
| gap | **0** |

Skip/xfail node+reason sets: `evidence/backend/backend-skip-set.json`,
`evidence/backend/backend-xfail-set.json`. Red node inventory:
`evidence/backend/backend-red-nodes.json`.

### Red-family distribution (node counts by module)

- `TestRealAlembicUpgradeFailClosed` 20, `test_dc12r1_s1_r3_migration_contract` 11,
  `test_dc12r1_s1_r4_exact_catalog` 8, `TestExactCatalogShapeBypass` 8,
  `test_dc11t2_async_test_utils` 6, `test_s4g_migration_infrastructure_hardening` 5,
  `test_dc12r1_s1_r1_corrections` 2, `test_dc12r1_s1_r2_strict_mapping` 2,
  `test_dc10e_export_worker_tenant_context` 1, `test_dc11t4c_reporting_bootstrap_contract` 1,
  `test_dc12r1_s1_r5_migration_preflight_exact_catalog` 1, `TestTwoRegisteredTenantsUpgrade` 1,
  `test_u6i1_owner_credential_setup_schema` 1 — failures
- errors: `test_platform_p17dc_backup_migration` 9,
  `test_dc11t4h_receivable_collection_integrity` 6,
  `test_platform_p21_durable_approval_migration` 6

### DIAGNOSTIC_ONLY root-cause signal (non-authoritative, no rerun)

The retained failure text includes relative-path errors such as
`FileNotFoundError: 'jobs/export_jobs.py'`, which resolve correctly only
when pytest's CWD is `backend/`; the authority runner launches the
product command from the worktree root. The red set is dominated by the
migration/temp-DB family that the V2 round of this lineage already
classified as environment-coupled when a launch variable is wrong.
This signal is recorded for CTO adjudication only. Per the task rules
the round treats the result strictly as
`STOP_AND_REPORT_CTO_WITH_FIRST_AUTHENTIC_RED`: no reclassification
run, no rerun, no browser phase.

## Phase 5 — Single Browser Authoritative Run: **NOT_RUN**

Backend gate RED ⇒ browser phase not entered (task rule 四.8). No
`pnpm exec playwright test` was invoked; no browser stack was built.

## Post-Run Residue Truth

- Redis DB15 `DBSIZE=0`; no keys
- No leftover task databases (only `postgres`, `template0/1`, `mpango_erp_test`)
- No `dc11t2fr_*`/`et1_smoke_*` roles remaining
- `retailer_credential_setup_tokens=0`, `retailer_password_reset_tokens=0`
- Known pre-existing debris family: 33 `t_*` tenant-bootstrap schemas
  created by the suite itself inside the task DB (destroyed with the stack)

## Cleanup (verified)

Pre-gate stack (`dc12r1i1f-*`): containers, volumes, network removed
before the authority stack was built. Authority stack
(`dc12r1i1a-*`): containers + volumes + network removed at close; ports
17432/17379 freed; credentials env file destroyed; worktree removed and
deregistered; frozen refs re-verified byte-identical after all
operations. See `evidence/cleanup/cleanup-evidence.txt`.

## Adjudication

E1 CORRECTION: Phase 4 did NOT produce an authentic product RED; the run is reclassified VOID_ENVIRONMENT_PRECHECK (88/88 red nodes executor-environment-attributed; preflight omissions CWD / MPANGO_TEMP_DB_ALLOWED_PORTS / TEST_DATABASE_URL name-safety / sessionstart non-recheck, §6 of E1_EVIDENCE_TRUTH_CORRECTION.md). The original wording is preserved: Under the task contract this mandates
`STOP_AND_REPORT_CTO_WITH_FIRST_AUTHENTIC_RED`: no browser run, no
rerun, no merge, no deploy, no product work. The CTO must adjudicate
the red family (launcher-CWD environment coupling vs product defects)
and authorize any follow-up round.

**STOP.**
