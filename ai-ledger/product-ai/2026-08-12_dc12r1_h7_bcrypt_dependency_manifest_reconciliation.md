# DC-12R1-H7-R14 — Native Alembic Connection Context Closure (NO PASS)

> **Status: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.** This is
> an evidence checkpoint, NOT a merge-review PASS. **H7-R13 is
> `SUPERSEDED_BY_H7_R14`.** Accepted external evidence: Kilo R10-V1 =
> `7d53d6a5c9dc7fc8a8a44414951c214c7bce4d02`; Lubuntu R10-V2 STOP =
> `e073ded80c479a90732b19efedd6e45afbf08bc2`. Earlier records superseded.

> Isolated branch: `zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`
> Base candidate: `db166b77` (H7-R12)
> Root base: `origin/product-dev-recovered@a6ef3aac`

## R14 evidence (current checkpoint)

Narrow correction to setup.sh and the manifest-parity test (setup_preflight.py,
direct preflight test, and all product/Compose/migration files untouched).

- **Native Alembic connection context.** setup.sh now resolves DATABASE_URL
  from backend/.env via the SAME strict `parse_env_file()` the preflight uses
  (no second handwritten parser, no `set -a`, no sourcing). The value is
  captured into a temporary shell variable and never printed. It is exported
  BEFORE `alembic upgrade head` and kept for
  `python scripts/bootstrap_tenant_schema.py`; both unset afterwards. No
  alembic.ini fallback — Alembic and bootstrap connect to the exact URL
  already validated against the rendered Compose config.
- **Enforcing harness fakes.** The fake `alembic` and `bootstrap` now require
  `$DATABASE_URL` to be present AND equal to the `.env` value (grep-verified);
  missing/mismatched → exit 2/3 fail-closed.
- **Authentic RED/GREEN:** GREEN (setup completes with the validated URL;
  sentinel never in argv/log/stdout/stderr); RED mutations — removing the
  export, moving it after Alembic, exporting a wrong URL (alembic and
  bootstrap independently), and a .env missing DATABASE_URL all fail before
  completion. Existing exit 42/43/44, Compose isolation, standalone harness,
  and all R5-R13 tests remain green.
- **Test gates:** direct 133/133 nat+rev; harness **35/35** nat+rev zero
  skip/xfail; complete H7 suite **262/262** both file orders nat+rev.
- **Deterministic gates:** bash -n OK; py_compile OK (no SyntaxWarning);
  diff-check clean; pre-commit incl. detect-secrets Passed; UTF-8/mojibake OK;
  GitNexus detect_changes vs `5a27e56d` = exactly the in-scope files;
  immutable blobs unchanged (env.py=`1c71de78`, bootstrap=`ca7d91f`);
  protected baseline `a6ef3aac` unchanged.
- **Hypothesis red node** (`HealthCheck.too_slow`): classified, UNRESOLVED,
  environment-gated; NOT suppressed or edited.

**Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.** No PASS
is claimed. After R14: Kilo bounded review; Lubuntu V4 repeats native setup
twice + focused zero-red; only then CTO merge consideration.

---

## R13 evidence (SUPERSEDED_BY_H7_R14)

Narrow test-only correction; setup.sh and all product files remain byte-
identical to R12.

- **Defect closed — standalone fake never chmod'd.** In R12 the standalone
  harness wrote a `docker-compose` fake but the `chmod +x` loop only covered
  `_FAKE_NAMES` (docker/pip/alembic/python/pnpm). On MSYS/Windows this was
  masked (the exec bit is not enforced there); on POSIX the standalone fake
  would not be executable and the standalone tests would fail.
  R13 adds `docker-compose` to the chmod set ONLY when `standalone=True`, and
  the normal harness never attempts to chmod a file it does not create
  (existence-filtered; a missing fake raises fail-closed).
- **Fail-closed executability assertions (new):**
  `test_standalone_fakes_exist_and_are_executable` (docker + docker-compose
  exist and pass the selected Bash's `test -x` — the POSIX/MSYS executability
  proof; Windows `os.stat` does not expose exec bits, so `test -x` is the
  authentic cross-platform check) and
  `test_normal_harness_does_not_chmod_nonexistent_docker_compose`.
- **Test gates (counts updated truthfully):** direct preflight **133/133**
  natural+reverse; executable harness **29/29** natural+reverse zero skip/xfail
  (27 previous + 2 R13); complete H7 suite **256/256** natural+reverse in both
  file orders.
- **Deterministic gates:** py_compile OK (no SyntaxWarning); `bash -n` OK
  (setup.sh untouched); `git diff --check` clean; scoped pre-commit incl.
  detect-secrets Passed; strict UTF-8/mojibake OK; GitNexus `detect_changes`
  vs `db166b77` = exactly the in-scope files (manifest-parity test + three
  evidence docs); immutable blobs unchanged (env.py=`1c71de78`,
  bootstrap=`ca7d91f`); protected baseline `a6ef3aac` unchanged.
- **GitNexus note:** `gitnexus status` is up-to-date at `db166b7`, but the
  local MCP `compare` misreports many historical files; the authoritative R12
  scope is therefore the precise `git diff` result (5 files). Recorded as
  host-specific GitNexus non-reproducibility.
- **Hypothesis red node** (`HealthCheck.too_slow`): classified, UNRESOLVED,
  environment-gated; NOT suppressed or edited.

**Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.** No PASS
is claimed. R13 is the STOP checkpoint before Kilo bounded review; only after
Kilo passes does Lubuntu run native setup.sh + focused zero-red. No
deployment, Playwright or merge.

---

## R12 evidence (SUPERSEDED_BY_H7_R13)

- **Defect closed — premature standalone config probe.** R11's candidate
  selection ran `docker-compose config --format json` as a capability probe
  BEFORE the `--env-file "$BACKEND_ENV"` array existed. That config operation
  ran without `--env-file`, failed interpolation (`POSTGRES_PASSWORD must be
  set`), and silently rejected an otherwise-valid standalone Compose v2.
  R12 selects candidates with `version` probes ONLY, then runs the real
  capability checks (`config --quiet`, `config --format json`) through the
  same `COMPOSE=(<candidate> --env-file "$BACKEND_ENV")` array.
- **Structural guard:** `check_setup_sh_wiring` now rejects any `config`
  occurrence before the `COMPOSE=(` array line (fixed wording; a false
  positive on the "Setting **up**" echo line was caught and the check was
  narrowed to `\bconfig\b`).
- **Authentic standalone harness (new):** the `docker compose` plugin is
  hidden (any `docker` call fails) and only a standalone Compose v2 fake
  exists; its `config`/`up`/`exec` succeed ONLY when `--env-file <path>` is
  carried BEFORE the subcommand.
  - GREEN `test_standalone_compose_env_file_enforced`: setup completes through
    the standalone path; every logged operation starts with
    `docker-compose --env-file`.
  - RED `test_standalone_mutation_remove_env_file_fails`: removing
    `--env-file` from the array → `docker-compose configuration is invalid`,
    no completion.
  - RED `test_standalone_mutation_env_file_after_subcommand_fails`: moving
    `--env-file` after `config` → rejected, no completion.
  - RED `test_standalone_mutation_premature_config_probe_fails`: restoring the
    premature `docker-compose config --format json` probe → selection fails
    closed (`Docker Compose v2 is required`).
  - Mutation copies are written as LF bytes so the CRLF self-check does not
    mask the intended mutation path.
- **Test gates (re-run, counts updated truthfully):** direct preflight
  **133/133** natural+reverse; executable harness **27/27** natural+reverse
  zero skip/xfail (23 previous + 4 standalone); complete H7 suite **254/254**
  natural+reverse in both file orders.
- **Deterministic gates:** `bash -n` OK; py_compile OK (no SyntaxWarning);
  `git diff --check` clean; scoped pre-commit incl. detect-secrets Passed;
  strict UTF-8/mojibake OK; GitNexus `detect_changes` vs `849f31ca` = exactly
  the in-scope files (setup.sh, manifest-parity test, this ledger, PROJECT.md,
  CTO_CURRENT_OPS.md); everything else byte-identical to R11 (setup_preflight.py,
  direct preflight test, docker-compose files, manifests, migrations, product
  code, lockfiles, Hypothesis test); immutable blobs unchanged
  (env.py=`1c71de78`, bootstrap=`ca7d91f`); protected baseline `a6ef3aac`
  unchanged.
- **Hypothesis red node** (`HealthCheck.too_slow`): classified, UNRESOLVED,
  environment-gated; NOT suppressed or edited.

**Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.** No PASS
is claimed. R12 is a STOP checkpoint: Kilo bounded review is next; only after
Kilo passes does Lubuntu V3 run. No deployment, Playwright or merge.

---

## R11 evidence (SUPERSEDED_BY_H7_R12)

R11 closes two source defects surfaced by the Lubuntu V2 native failure on the
occupied host (report SHA `e073ded8`):

- **Source defect A — fixed container names.** `docker-compose.yml` pinned
  `container_name` on every service (`mpango_postgres`, `mpango_redis`,
  `mpango_backend`, `mpango_frontend`, `mpango_gateway`, `mpango_prometheus`).
  Fixed names collide with the host-owner's pre-existing containers no matter
  which Compose project name is used. R11 removes ALL `container_name` lines
  from the base file (services, DNS, volumes, networks, health checks and
  semantics preserved; docker-compose.prod.yml untouched). Compose now
  namespaces containers/networks/volumes from the caller's
  `COMPOSE_PROJECT_NAME`, which setup.sh honours unchanged.
- **Source defect B — missing Compose env-file wiring.** setup.sh ran
  `docker compose` with the DEFAULT env-file (repo-root `.env`) and relied on
  the caller's exported variables, so `bash backend/scripts/setup.sh` failed
  interpolation when `backend/.env` existed but was not exported. R11 passes
  `backend/.env` explicitly through Compose's global option
  `docker compose --env-file <absolute backend/.env> ...` — same array for
  config/up/exec, `--env-file` before the subcommand, no `source`/export of
  `.env`, no secrets printed. The exact native command remains
  `bash backend/scripts/setup.sh`.
- **Fail-closed preflight rule:** any rendered service declaring an explicit
  `container_name` is rejected with a fixed neutral error
  (`<service> declares an explicit container_name`; the name value is never
  echoed). Direct unit matrix (postgres/redis/backend mutations + multi-service
  GREEN) covers it.
- **Authentic RED proofs against `6be4c279` (this host, occupied):**
  1. R10 `compose up -d redis` under a unique project name FAILED with
     `Conflict. The container name "/mpango_redis" is already in use by
     container 722add54…` — the pre-existing host-owner `mpango_redis` (up
     12h, healthy) blocked it; partial task resources were removed.
  2. R10-style invocation (`docker compose config --quiet` without
     `--env-file`, no exports) failed with `POSTGRES_PASSWORD must be set`;
     the R11 `--env-file` invocation succeeds.
  3. R10 preflight has no `container_name` rule (grep count 0) and the R10
     compose renders 5 fixed container_names; the R11 preflight rejects that
     exact rendered JSON (`backend declares an explicit container_name`).
- **Authentic GREEN proofs (this host, task-owned disposable resources):**
  - `docker compose -p h7_r11_a|b --env-file backend/.env config --format
    json` — both renders contain ZERO explicit `container_name`; networks
    (`h7_r11_a_mpango_network` vs `h7_r11_b_mpango_network`) and volumes
    (`h7_r11_a_*_data` vs `h7_r11_b_*_data`) are disjoint.
  - Sentinel coexistence: `-p h7_r11_green up -d redis` created and started
    `h7_r11_green-redis-1` while the host-owner `mpango_redis` kept running
    untouched (verified before/after `docker ps` identical; project fully
    `down -v`'d; zero leftovers).
  - Harness: every Compose operation carries `--env-file` before the
    subcommand (`test_compose_invocations_carry_env_file_before_subcommand`).
  - Port isolation: caller-selected `POSTGRES_PUBLISHED_PORT=15432` /
    `REDIS_PUBLISHED_PORT=16379` with matching URLs → `OK`; URL 15432 vs
    published 15433 → `postgres port published mismatch` (exit 1) before any
    side effect.
- **Test gates:** direct preflight **133/133** natural+reverse; executable
  harness **23/23** natural+reverse zero skip/xfail; complete H7 suite
  **250/250** natural+reverse in both file orders. Existing exit-status,
  timeout, secret, CRLF, idempotency and command-order assertions intact.
- **Deterministic gates:** `bash -n` OK; py_compile OK (no SyntaxWarning);
  `git diff --check` clean; scoped pre-commit incl. detect-secrets Passed;
  strict UTF-8/mojibake OK; GitNexus `detect_changes` vs `6be4c279` = exactly
  the eight allowed files; every file outside the allowlist byte-identical to
  R10 (setup.sh changed in-scope; manifests, migrations, product code,
  Dockerfile, docker-compose.prod.yml, lockfiles, Hypothesis test unchanged);
  immutable blobs unchanged (env.py=`1c71de78`, bootstrap=`ca7d91f`);
  protected baseline unchanged at `a6ef3aac`.
- **Host-owner non-interference proof:** before/after `docker ps` name sets
  identical (9 host-owner containers); no host-owner container was stopped,
  renamed, or inspected; only a doomed create attempt (failed at name
  registration) and task-owned `h7_r11_green`/`h7_r11_red` projects were
  involved, all cleaned (`no task containers/networks/volumes` after).
- **Hypothesis red node** (`test_property_token_roundtrip_integrity`
  `HealthCheck.too_slow`): classified, UNRESOLVED, environment-gated; NOT
  suppressed or edited.

**Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.** No PASS
is claimed; no native-Linux success, merge readiness or deployment claim.
After R11: (1) Kilo bounded source review; (2) Lubuntu V3 native setup on the
same occupied host with a unique project name and free loopback ports;
(3) focused Hypothesis zero-red gate; only then CTO merge consideration.

---

## R10 evidence (SUPERSEDED_BY_H7_R11)

## R10 evidence (current checkpoint)

R10 is an extremely narrow correction: only the manifest-parity test and the
three evidence docs change. `setup_preflight.py`, the direct preflight test,
setup.sh, dependency manifests, product code, migrations, Compose config,
lockfiles and the Hypothesis test are all byte-identical to R9.

- **Defect closed — non-zero probe test was host-fragile.** R9's
  `test_verify_coreutils_fails_when_probe_returns_nonzero` used
  `shutil.which("false")`. On hosts where the `false` coreutil is not on PATH
  the leading `assert false_exe` fails, so that one test errors → the suite is
  **244 passed / 1 failed** (the R9 host-fragility reproduction). On this
  Windows host `false` resolves (`C:\\Program Files\\Git\\usr\\bin\\false.EXE`)
  so R9 reads 245/0 here — but the `false` dependency is a latent single point
  of failure.
- **R10 fix (deterministic).** The test now uses `sys.executable`: it is
  guaranteed to exist (`os.path.isfile(sys.executable)` asserted) and launches
  successfully, but it receives the shell coreutils probe as Python code →
  `SyntaxError` → non-zero exit. `_verify_coreutils(sys.executable, [])` raises
  **exactly** `RuntimeError("coreutils probe failed")` (assertion uses
  `str(exc.value) == "coreutils probe failed"`). No reliance on `false` or any
  PATH-resolved coreutil.
- **Three independent coreutils tests retained unchanged:** OSError /
  non-executable probe (`/definitely/not/a/real/bash`), missing real coreutil
  (emptied PATH), and successful cross-host resolution. The non-zero test is
  the fourth.
- **Evidence (re-run after the change):** direct preflight **129/129** natural;
  executable harness **22/22** natural; complete H7 suite **245/245** natural
  AND reverse in both file orderings (preflight-first and parity-first); and
  **245/245 under a Git-Bash-stripped PATH** — proving R10 is host-independent
  (R9's `false`-dependency removed). `py_compile`, `bash -n`, `git diff --check`,
  pre-commit incl. detect-secrets, strict UTF-8/mojibake all clean; GitNexus
  `detect_changes` vs `b495eb4a` = exactly the in-scope files; all files
  outside the four-file R10 allowlist byte-identical to R9; immutable blobs
  unchanged (env.py=`1c71de78`, bootstrap=`ca7d91f`).
- **Hypothesis red node** (`test_property_token_roundtrip_integrity`
  `HealthCheck.too_slow`): classified, UNRESOLVED, environment-gated; NOT
  suppressed or edited.

**Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.** No PASS
is claimed; this is an evidence checkpoint only. R10 source corrections are
complete; this is not merge approval. Kilo bounded source review is next; only
after Kilo closure may Lubuntu run native setup.sh and the focused zero-red
gate; H7 cannot merge until both gates pass.

---

## R9 evidence (SUPERSEDED_BY_H7_R10)

R9 closes two bounded R8 source/evidence defects. setup.sh, dependency
manifests, product code, migrations, Compose configuration, lockfiles,
deployment behavior and the unresolved Hypothesis test are all unchanged.

- **Defect 1 — published-port trailing-newline false-acceptance (closed).**
  R8 used `_PUBLISHED_RE.match(value)` with pattern `^[0-9]+$`; Python's `$`
  matches before a final newline, so `_published_int("5432\n", "postgres")
  == 5432` was accepted — violating the "complete ASCII `[0-9]+` string"
  contract. **RED proof against `9f06d4a7`:** `_PUBLISHED_RE.match("5432\n")`
  → `True`; `_PUBLISHED_RE.fullmatch("5432\n")` → `False`. Fix:
  `_PUBLISHED_RE.fullmatch(value)` (no `.strip()`/`int()`-before-validate/
  `isdigit()`/coercive parsing). `target` unchanged (exact int only).
  Mandatory GREEN/RED matrix proven directly (`TestPublishedInt`: `5432` and
  `"5432"` accepted; `"5432\n"`, `"5432\r"`, `"5432 "`, `" 5432"`, `"\t5432"`,
  `"5432\t"`, `"５４３２"`, `True`, `5432.0`, `"abc"`, `[5432]`, `None`
  rejected with `port published must be an integer`) AND via the complete
  `run_initial()` path with real Compose-shaped JSON
  (`test_published_trailing_newline_rejected_via_run_initial`). `target="5432"`
  remains rejected.
- **Defect 2 — coreutils non-zero-return branch evidence (closed).** R8's
  `_verify_coreutils` checked `res.returncode != 0` but no test exercised it.
  New `test_verify_coreutils_fails_when_probe_returns_nonzero` uses the real
  `false` executable (starts successfully, exits non-zero) →
  `_verify_coreutils` raises exactly `RuntimeError("coreutils probe failed")`;
  it does not rely on a missing executable (the OSError/non-executable test
  remains). **Mutation evidence:** with the return-code guard removed,
  `_verify_coreutils(false_exe, [])` does NOT raise → the new test goes RED;
  with the guard it raises → GREEN. The committed source has the guard.
- **Documentation truth:** the `test_dc12r1_h7_setup_preflight.py` module
  header now describes the asymmetric contract accurately (target exact int;
  published exact int or complete ASCII digit string; bool/float/Unicode
  digits/whitespace/structured values rejected).
- **Evidence:** direct preflight **129 passed** natural AND reverse; executable
  harness **22 passed** natural AND reverse, zero skip/xfail; complete H7
  suite **245 passed** natural AND reverse in both file orderings (preflight
  129 + parity 116); full manifest-parity file 116/116; exact direct probes
  (21) for trailing-newline published, invalid-UTF-8 (direct+CLI), missing
  coreutil, non-executable probe, non-zero-return probe, unique sentinel.
  `bash -n`, `py_compile` (no SyntaxWarning), `git diff --check`, pre-commit
  incl. detect-secrets, strict UTF-8/mojibake — all clean; GitNexus
  `detect_changes` vs `9f06d4a7` = exactly the in-scope files; all files
  outside the six-file allowlist byte-identical to R8 (setup.sh,
  requirements.txt, pyproject.toml, poetry.lock, Dockerfile, docker-compose,
  migrations, product code, Hypothesis tests); immutable blobs unchanged
  (env.py=`1c71de78`, bootstrap=`ca7d91f`).
- **Hypothesis red node** (`test_property_token_roundtrip_integrity`
  `HealthCheck.too_slow`): classified, UNRESOLVED, environment-gated; NOT
  suppressed or edited.

**Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.** No PASS
is claimed; this is an evidence checkpoint only. R9 source corrections are
complete; this is not merge approval. Kilo bounded source review is next; only
after Kilo closure may Lubuntu run native setup.sh and the focused zero-red
gate; H7 cannot merge until both gates pass.

---

## R8 evidence (SUPERSEDED_BY_H7_R9)

- **setup.sh byte-identical to `0eb24d88`** — `git diff --exit-code 0eb24d88 --
  backend/scripts/setup.sh` is empty; no source defect required a change.
- **Coreutils evidence:** `_REQUIRED_COREUTILS` now covers exactly the external
  commands setup.sh actually invokes — `dirname, grep, mkdir, seq, sleep` — plus
  `chmod` used by harness preparation; obsolete `tr/cat/mktemp` removed.
  `_verify_coreutils` fails closed if the Bash probe cannot execute OR returns
  non-zero OR any required coreutil is unresolvable. RED: missing real
  dependency (emptied PATH → dirname/grep/... unresolvable) and probe-execution
  failure (non-existent bash → `coreutils probe failed`); GREEN: this host.
- **.env fail-closed:** `parse_env_file` catches `UnicodeDecodeError` during
  iteration and emits one fixed neutral error (`backend/.env is not valid
  UTF-8`) with no path, bytes or secret content. Direct + CLI tests cover an
  invalid-UTF-8 `.env`.
- **Precise asymmetric port contract:** `target` must be an exact int (bool,
  float, string, Unicode digits, structures rejected); `published` must be an
  exact int OR an ASCII `[0-9]+` string (the form Compose v2 emits for
  env-substituted published ports). Module, tests and this report use the same
  wording. Real `docker compose config --format json` (target=int,
  published=string) passes.
- **Evidence integrity:** a genuinely unique sentinel
  (`H7R8HarnessSentinel123`) is placed in the harness `.env` AND the fake
  Compose output and proven absent from every captured argv/log/stdout/stderr
  (`test_unique_sentinel_absent_from_all_captures`).
- **Evidence:** direct preflight matrix **114 passed** natural AND reverse;
  executable harness **21 passed** natural AND reverse, zero skip/xfail;
  complete H7 suite **229 passed** natural AND reverse (parity 115 + preflight
  114); real Compose pipeline = `OK`; `bash -n`, py_compile, `git diff --check`,
  pre-commit incl. detect-secrets, UTF-8 all clean; GitNexus `detect_changes`
  vs `0eb24d88` = exactly the in-scope files (setup.sh unchanged); immutable
  files byte-identical (env.py=`1c71de78`, bootstrap=`ca7d91f`).
- **Hypothesis red node** (classified, UNRESOLVED, environment-gated):
  unchanged; NOT suppressed or edited.

**Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.** No PASS
is claimed; this is an evidence checkpoint only. After R8 freezes: Kilo
bounded review, then Lubuntu native setup.sh + focused zero-red verification.

---

## R7 evidence (superseded by R8)

- **Secret hygiene:** `--process-db` / `--process-redis` removed; no
  secret-bearing argv. setup_preflight.py reads DATABASE_URL / REDIS_URL from
  `os.environ` (process vs file conflict checked in memory). A unique sentinel
  is proven absent from argv, the captured command log, and all output
  (direct `TestSecretHygiene` + harness `test_no_secret_in_argv_or_log`).
- **Hardened setup_preflight.py:** env keys strictly `[A-Za-z_][A-Za-z0-9_]*`;
  exact DB scheme parse (postgresql / postgresql+asyncpg only — no global
  string replacement); blank DB passwords rejected; integer-valued port
  fields only (int or decimal-digit string as real Compose emits for
  env-substituted `published`; bool / float / non-numeric string / structured
  types rejected); Compose root must be a dict; malformed URL / file / JSON →
  fixed neutral errors; Redis credentials rejected (no-auth Compose Redis).
- **Cross-host harness repair:** the selected Git Bash `/usr/bin` and
  `/mingw64/bin` are explicitly provided on the run PATH; required coreutils
  (`chmod grep tr cat mktemp seq`) are verified before running and the harness
  fails closed (RuntimeError) if any is unresolvable. `_select_bash` rejects
  System32/WSL/WindowsApps. This closes the CTO 187/174/13 cross-host
  failure mode (authentic RED: `test_cross_host_fails_closed_when_required_coreutil_missing`).
- **setup.sh:** pipes `compose config --format json | python
  scripts/setup_preflight.py --env-file backend/.env` under
  `set -Eeuo pipefail` (no secret on argv); `--post-install` after pip and
  before Alembic / bootstrap; CRLF fail-closed self-check (python raw-byte).
- **Evidence:** direct preflight matrix **104 passed** natural AND reverse
  (fixed neutral errors; file-wide no-secret invariant); executable harness
  **20 passed** natural AND reverse, zero skip/xfail (System32/WSL
  fail-closed, CRLF runtime, cross-host coreutils verify + fail-closed,
  post-install order/mismatch, sentinel-argv proof); complete H7 suite
  **218 passed** natural AND reverse (parity 114 + preflight 104); real
  `docker compose config --format json` (v2.40.3) through the committed
  helper = `OK`; negatives (blank DB password, Redis credentials) = exit 1
  with fixed neutral messages.
- **Deterministic gates:** `bash -n` OK; py_compile OK; `git diff --check`
  clean; scoped pre-commit incl. detect-secrets Passed; UTF-8 strict OK;
  GitNexus `detect_changes` vs `4746e180` = exactly the 7 in-scope files;
  immutable files byte-identical (env.py=`1c71de78`, bootstrap=`ca7d91f`);
  manifests, migrations, product code, lockfiles and protected refs untouched.
- **Aggregate scope:** exactly 7 files (setup.sh, setup_preflight.py, both
  H7 test files, PROJECT.md, CTO_CURRENT_OPS.md, this ledger).
- **Hypothesis red node** (classified, UNRESOLVED, environment-gated):
  unchanged from the R5-R5 record; NOT suppressed or edited.

**Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.** No
PASS is claimed; this is an evidence checkpoint only.

---

## R5-R6 evidence (superseded by R7)

- **Extracted preflight module** `backend/scripts/setup_preflight.py`
  (stdlib-only): initial mode reads rendered Compose JSON from stdin and
  backend/.env by path; validates process/file URL conflicts, strict .env
  syntax (export/duplicate/malformed/unclosed/mismatched quotes/invalid
  keys), postgresql/postgresql+asyncpg and redis schemes, URL-decoded
  credentials compared **in memory** against Compose POSTGRES_* values,
  loopback hosts and exact ports. Post-install mode imports core.config
  (only after pip) and compares settings.DATABASE_URL/REDIS_URL. Output is
  only `OK`; errors are fixed neutral strings — URLs, passwords and Compose
  JSON are never emitted. No temporary secret-bearing Compose or Python files.
- **Compose truth enforced exactly:** postgres environment must be a dict with
  exact required credential values; redis environment may be absent or a dict;
  exactly one object-form port mapping per service (host_ip=127.0.0.1,
  protocol=tcp, mode=ingress, exact target/published). String ports,
  duplicates, extra entries, missing fields, booleans, floats and unknown
  structures are rejected.
- **setup.sh:** pipes `compose config --format json | python
  scripts/setup_preflight.py --env-file backend/.env --process-db ...
  --process-redis ...` under `set -Eeuo pipefail`; `--post-install` runs after
  pip and before `alembic upgrade head` and tenant bootstrap; CRLF fail-closed
  self-check via python raw-byte read (MSYS text-mode file reads make shell
  CR detection unreliable — verified empirically).
- **Direct preflight matrix** `tests/test_dc12r1_h7_setup_preflight.py`:
  **76 passed** natural AND reverse; every DB/Redis URL, .env and Compose
  shape failure asserts the exact fixed neutral error; a file-wide invariant
  asserts no secret substring in any error; redis-env-absent mutation does
  not fail; the real rendered redis shape passes.
- **Executable harness:** **17 passed** natural AND reverse, zero skip/xfail —
  strict command ordering incl. initial-preflight-pipe-before-compose-up and
  post-install-between-pip-and-alembic; exit 42/43/44 preserved; pg/redis
  timeouts; invalid compose → zero side effects; no secret in output;
  idempotency; System32/WSL/WindowsApps bash fail-closed (monkeypatched);
  CRLF-mutated setup.sh exits non-zero before any fake command (committed LF
  copy GREEN; committed blob has zero CR bytes via .gitattributes eol=lf).
  Fake executables are LF bytes; chmod uses MSYS-converted paths with
  check=True; `_select_bash` is module-scope and used by build+run.
- **Real pipeline:** actual `docker compose config --format json` (Compose
  v2.40.3) piped through the committed helper = `OK` (exit 0); negative
  process-DB conflict = exit 1 with the fixed neutral message.
- **Complete H7 suite:** **187 passed** natural AND reverse (parity 111 +
  preflight 76), zero skip/xfail.
- **Deterministic gates:** `bash -n` OK; py_compile OK; `git diff --check`
  clean; scoped pre-commit incl. detect-secrets Passed; UTF-8 strict OK;
  GitNexus index refreshed (status up-to-date at abbbe32f) and impact query
  recorded (cross-links only to the frozen migration versions module).
- **Changed files (exactly 4):** `backend/scripts/setup.sh`,
  `backend/scripts/setup_preflight.py` (new),
  `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`,
  `backend/tests/test_dc12r1_h7_setup_preflight.py` (new).
  Immutable files byte-identical (env.py=`1c71de78`, bootstrap=`ca7d91f`);
  protected tip unchanged at `a6ef3aac`; dependency manifests, migrations,
  product code and Hypothesis tests untouched.
- **Hypothesis red node** (classified, UNRESOLVED, environment-gated):
  unchanged from R5-R5 record below; NOT suppressed or edited.

**Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.** No
PASS is claimed; this is an evidence checkpoint only.

## Exact commands and counts (R5-R2)

- setup.sh: config preflight (backend/.env present, no CHANGE_ME, `compose
  config` valid) before any side effect; `set -Eeuo pipefail`; `_on_err
  "$LINENO" "$?"` preserving exact status; Compose stored as a shell array;
  Compose-scoped `exec -T` pg/redis readiness with container-owned
  `POSTGRES_USER`/`POSTGRES_DB`; `pip install -r requirements.txt`; `alembic
  upgrade head` (public); DATABASE_URL resolved from `core.config.settings`
  (never printed) and verified tuple-vs-Compose (username, database,
  host=localhost, port=5432); canonical bootstrap via exported DATABASE_URL
  (never in argv); `pnpm install --frozen-lockfile`.
- Executable harness (fake executables in a temp fake-bin dir prepended to
  PATH, MSYS-style, UNMODIFIED setup.sh copy): **9/9 PASS** — strict ordered
  command indexes; alembic exit 42 / bootstrap exit 43 / pnpm exit 44
  preserved; pg and redis timeouts non-zero with no later steps; invalid
  compose config → zero filesystem/service side effects; no secret in output;
  idempotent second run with no duplicate config or file mutation.
- H7 suite: **103 passed / 0 failed in natural order AND reverse order**.
- Deterministic gates: `bash -n` OK; py_compile OK; `git diff --check` clean;
  scoped pre-commit + detect-secrets Passed; mojibake clean; all immutable
  files (requirements.txt, pyproject.toml, poetry.lock, Dockerfile,
  alembic/env.py, bootstrap_tenant_schema.py) byte-identical to `0e8d5159`.

## Hypothesis red node (classified, UNRESOLVED, environment-gated)

`tests/test_token_properties.py::test_property_token_roundtrip_integrity`
(line 46): `hypothesis.errors.FailedHealthCheck` / `HealthCheck.too_slow`
("Input generation is slow: only 2 valid inputs after 1.09 s"), reproducible
with `--hypothesis-seed=303296478269760642762159842520761126666`, intermittent
in the 16-file focused bundle (4/5 runs) on this heavily loaded Windows host
(concurrent ChatGPT/opencode/ZCode/WeChat/kilo processes), passing on
isolation/replay (3/3). It is a timing health check, NOT an assertion failure,
and NOT an H7 defect: the Poetry test env is lock-governed and byte-identical
since R3; no H7 slice touches this test.

**Verdict: `STOP_AND_REPORT_CTO_AWAITING_LUBUNTU_ZERO_RED`.** No PASS is
claimed. The current zero-red focused gate can only be satisfied on a
low-load (Lubuntu) host; the R3 full-gate evidence (3366/29/15/0/0) is
inherited for runtime, NOT as satisfaction of this slice's focused gate.

---

## Historical record (R5-R5 and earlier, superseded)

R4-R1 closed two remaining uncovered false-green paths in the source-shape
guards: (A) the
setup.sh guard used only same-line block detection and loose command matching;
(B) the Dockerfile guard did not join continuations or detect inert/dead-branch
forms on RUN lines (echo-wrapper, ``false &&``, ``|| true``, ``ENV``/``LABEL``/
``ARG`` carriers). R4-R1 closes both.

> Isolated branch: `zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`
> Base candidate: `fc816820` (H7-R4)
> Root base: `origin/product-dev-recovered@a6ef3aac`

## 0 Verdict Summary

| Dimension | Result |
|---|---|
| Base / resume | ✅ HEAD `6cd37e03`; tree clean; local==remote; protected a6ef3aac unchanged |
| Scope | ✅ exactly 4 files (test + docs + ledger); requirements.txt / pyproject.toml / poetry.lock / Dockerfile / setup.sh / all product code **byte-identical** to 6cd37e03 |
| KILO-H7R3V1-001 (lock parser edge cases) | ✅ closed — 10+ malformed-entry validations, controlled ValueError for every form, specific diagnostic fragments |
| KILO-H7R3V1-002 (extras / overclaim wording) | ✅ closed — extras rejected; marker-only mutation proven neutral; contract narrowed to exact wording |
| KILO-H7R3V1-003 (substring-only wire guards) | ✅ closed — structural source-shape guards for setup.sh and Dockerfile + RED mutation tests |
| KILO-H7R3V1-004 (GitNexus reproducibility) | ✅ closed — Zcode host result recorded; Kilo host non-reproducibility acknowledged as host-specific |
| Manifest suite | ✅ 75 tests natural order (reverse CLI-length limited on Windows; tests are deterministic, order-independent) |
| Focused regression | ✅ password/auth/onboarding/provisioning + manifest: 277 passed; 1 known hypothesis flake (same transient token-property seed as R2/R3 — not an R4 regression; R3 full gates 0/0) |
| Full backend gates | ⏸️ **inherited from R3** (dependencies + product code byte-identical; not rerun in R4) |
| Docker | ⏸️ inherited from R2 (Dockerfile/pyproject/poetry.lock byte-identical) |
| Quality gates | ✅ py_compile, git diff --check, scoped pre-commit + detect-secrets, mojibake, GitNexus all clean; 4-file delta confirmed; manifests byte-identical |
| Verdict | **PASS_FOR_CTO_DC12R1_H7_R4_FINAL_SOURCE_REVIEW** |

---

## 1 Kilo findings on H7-R3 (closed by R4)

From `reports/dc12r1-h7-r3-v1-kilo-comprehensive-review-2026-08-12/` (commit `c5385565`):

- **KILO-H7R3V1-001 (P2)** — Lock parser silently accepted/excluded malformed entries
  or raised unrelated exceptions for non-string name. The committed parser now
  validates type/shape/content of name, version and groups explicitly with 13
  controlled `ValueError` raises and matching diagnostic-fragment tests.
- **KILO-H7R3V1-002 (P2)** — Extras (e.g. `[standard]`) silently dropped; broader
  wording overclaimed parity. Extras are now rejected in `requirements.txt`; all
  contract language narrowed to the exact phrase below. Marker-only variants
  provably do not alter the name/version inventory.
- **KILO-H7R3V1-003 (P2)** — Install-path tests used raw substring-only checks
  allowing comment / dead-branch / inert-string false greens. Replaced with
  structural source-shape guards (sequence + context) for both `setup.sh` and
  `Dockerfile`, each with RED mutation tests.
- **KILO-H7R3V1-004 (P3)** — GitNexus status reproducibility remained unreproduced
  on the Kilo review host. Recorded as host-specific; the Zcode-host result is
  documented explicitly.

INFO findings confirmed lineage, 70/70 inventory parity, requirements-parser closure,
and evidence boundaries were already present.

## 2 The exact contract (narrowed, R4)

The only parity claim supported by the committed gate is:

> **requirements.txt and Poetry's main-group lock inventory have identical
> canonical package names and exact versions.**

Explicitly NOT compared by this gate:
- markers (marker-only mutations produce the same name/version inventory);
- extras (rejected in `requirements.txt`);
- Poetry lock hashes and lock sources;
- actual installer execution (native `setup.sh` is a mandatory Lubuntu gate).

## 3 R4 corrections

### A. Lock parser fail-closed (KILO-H7R3V1-001)

`parse_main_lock_packages` now rejects with controlled `ValueError`:
1. packages not a list.
2. package entry not a dict.
3–6. name: missing, non-string, empty, surrounding whitespace.
7–10. version: missing, non-string, empty, surrounding whitespace.
11–14. groups: missing, not a list, empty, contains non-string / empty /
      whitespace-only / None.
15. groups has duplicate string values.
16. normalized duplicate canonical names (cross-group or not).
`canonicalize_name` is called only after structural validation (never on
non-string). No broad exception swallowing. 18 authentic mutation tests assert
`ValueError` with the intended diagnostic fragment.

### B. Requirements parser (KILO-H7R3V1-002)

- Extras (e.g. `uvicorn[standard]==0.40.0`) now raise `ValueError` ("extras are
  not allowed in the inventory contract").
- A new GREEN test proves marker-only mutations produce the same name/version
  inventory (markers are NOT part of the gate contract).
- Duplicate name with different markers still raises (pre-existing).
- Invalid marker raises `InvalidRequirement` → `ValueError`.
- The `test_requirements_inventory_equals_lock_inventory` test uses the
  narrowed container name.

### C. Install-path source-shape guards (KILO-H7R3V1-003)

**`check_setup_sh_wiring`**: requires a bare `pip install -r requirements.txt`
line, rejects it inside `if`/`for`/`while`/`until`/`case` blocks, as echoed
output, behind `false &&`/`true ||` short-circuit, in variable assignments, or
inside quotes. Additionally requires `cd … backend` before and `alembic upgrade
head` after the pip line, and rejects a bare `exit`/`return` outside `if … fi`
before the pip line.

**`check_dockerfile_wiring`**: requires a `COPY pyproject.toml poetry.lock`
instruction textually before an active `RUN poetry install` line in the same
(final) build stage, rejecting missing instructions, wrong ordering, or
cross-stage separation.

Both guards accept the real committed files. RED mutation tests prove the
guards catch commented, dead-branch, inert, unordered, and missing forms.

These are **source-shape guards only** — they do not prove `setup.sh` or the
Dockerfile executed successfully. Native execution remains a Lubuntu gate.

### D. GitNexus (KILO-H7R3V1-004)

On this (Zcode) host, `npx gitnexus status` correctly reported an indexed
repository after `npx gitnexus analyze --force`. On the Kilo review host, the
same sequence produced "Repository not indexed." This is host-specific behaviour;
GitNexus status is not a portable product invariant.

## 4 Manifest / parser suite (R4)

`pytest tests/test_dc12r1_h7_bcrypt_manifest_parity.py`: **75 passed** in natural
order (R3 was 44). The manifest suite grew by 31 R4 tests (enhanced lock-parser
validation, extras rejection, marker neutral test, 2 source-shape guards + GREEN
acceptance + 10 RED wireless mutations, 1 inventory-delta test). Reverse-order
execution is blocked by the Windows command-line length limit when passing
explicit node IDs; the individual tests are deterministic pure functions with no
shared mutable state, so order-independence is inherent (R3 already proved
reverse order for the core parsers).

## 5 Focused regression (the only R4 runtime gate)

Stack1 (`contractd_pg16:5433` / `contractd_redis7:6380`, fresh Poetry env): 16
focused files + the manifest suite → **277 passed**, 1 known hypothesis seed
flake (`test_property_token_roundtrip_integrity` — the same transient token-
property seed artifact from R2/R3; the R3 full gates were 0/0, so this is not
an R4 regression). No full backend gate rerun — R3 runtime evidence (3366/29/15/
0/0 on two independent stacks) is inherited because **all dependencies, product
code, Dockerfile, and setup.sh are byte-identical to R3**.

## 6 Static / integrity gates

- `python -m py_compile tests/test_dc12r1_h7_bcrypt_manifest_parity.py`: clean.
- `git diff --check`: clean.
- scoped `pre-commit` on the 4 changed files: all Passed (incl. detect-secrets).
- mojibake / UTF-8 scan on the 4 changed files: clean.
- GitNexus: `analyze --force`/`status` on the Zcode host: **up-to-date at
  6cd37e03**; noted host-specific (Kilo host cannot reproduce).

## 7 Changed-file proof

Exactly **four** files (the allowed-list subset; `backend/requirements.txt`,
`backend/pyproject.toml`, `backend/poetry.lock`, all product code, `Dockerfile`
and `setup.sh` are **byte-identical** to `6cd37e03`):

```
 M backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py        (R4 fail-closed)
 M docs/ai/CTO_CURRENT_OPS.md                                    (R3->R4 supersession, contract wording)
 M docs/ai/PROJECT.md                                            (R3->R4 supersession, contract wording)
 M ai-ledger/..._dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md  (this ledger)
```

## 8 Scope / exclusions honored

No `requirements.txt`, `pyproject.toml`, `poetry.lock`, `Dockerfile`, `setup.sh`
or product-code change. No migration, deployment, Playwright, or VPS change. No
skip/xfail/deselect/assertion-weakening. No full gate rerun (R3 inherited). No
claim of native `setup.sh` / Docker execution, local deployment, Playwright, or
VPS validation. No protected push or merge.

## 9 After push: STOP

After the isolated H7 branch is pushed and the SHA frozen, **STOP**. Await Kilo
re-review, Lubuntu independent verification (including native `setup.sh` + Docker
build on Linux), and CTO merge. Do not begin Playwright, local deployment, or
VPS work.
