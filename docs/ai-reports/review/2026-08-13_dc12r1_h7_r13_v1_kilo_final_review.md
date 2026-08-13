# DC-12R1-H7-R13-V1 Kilo Final Bounded Source Review

**Verdict:** `STOP_AND_REPORT_CTO`

This review was bounded to the R13 candidate and the requested closure questions only.

## Reviewed SHAs

- Protected baseline: `a6ef3aac0ab03615e9d70e08e504b9858baf61c5`
- Accepted Kilo R10 review: `7d53d6a5c9dc7fc8a8a44414951c214c7bce4d02`
- R10: `6be4c27906eb99ce693d9515152725167dba3c5b`
- R11: `849f31ca0224fcf485e1055d98d69377b0471284`
- R12 / required parent: `db166b773389604d49ca2682a8e24ec715f3e1f7`
- Frozen R13 candidate: `5a27e56ddcd1dff79b9cba780e34cdd5b71bdfe7`
- Source branch: `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`

## Phase 1 — Proof gate

### EXECUTED proof

Verified:

- fetched/pruned refs successfully
- detached isolated worktree created at exact candidate SHA `5a27e56d...`
- local candidate equals remote source branch SHA
- `origin/product-dev-recovered` remains exactly `a6ef3aac...`
- direct parent of candidate is exactly `db166b773389604d49ca2682a8e24ec715f3e1f7`
- protected baseline is an ancestor of candidate
- detached candidate worktree was clean before review

No proof-gate mismatch occurred.

## Phase 2 — Exact R13 scope

### EXECUTED exact delta proof

`git diff --name-only db166b77..5a27e56d` returned exactly these four files:

1. `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`
2. `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`
3. `docs/ai/PROJECT.md`
4. `docs/ai/CTO_CURRENT_OPS.md`

### FAIL — immutable-file proof

The task required byte-identity to R12 for many files including:

- `backend/scripts/setup.sh`
- `backend/scripts/setup_preflight.py`
- `backend/tests/test_dc12r1_h7_setup_preflight.py`
- `docker-compose.yml`
- `docker-compose.override.yml`
- `docker-compose.prod.yml`
- manifests, lockfiles, Dockerfile, `.gitattributes`, `.env.example`, product directories, and `test_token_properties.py`

R13 preserves byte identity for many of these, including:

- `.gitattributes`
- `backend/.env.example`
- `backend/Dockerfile`
- `backend/alembic/env.py`
- `backend/requirements.txt`
- `backend/pyproject.toml`
- `backend/poetry.lock`
- `backend/tests/test_token_properties.py`
- `docker-compose.override.yml`
- `docker-compose.prod.yml`
- `backend/api/**`, `backend/core/**`, `backend/models/**`, `backend/schemas/**`, `backend/services/**`

But it does **not** preserve byte identity to R12 for these out-of-scope files:

- `backend/scripts/setup.sh`
- `backend/scripts/setup_preflight.py`
- `backend/tests/test_dc12r1_h7_setup_preflight.py`
- `docker-compose.yml`

This is confirmed both by:

- `git diff --name-only 6be4c279..5a27e56d -- <listed paths>`
- git object identity differences between `db166b77` and `5a27e56d`

That is a direct scope violation against the task’s immutable-file requirement.

## Phase 3 — R13 executable-bit closure

### STATIC review of `_build_harness()`

Source: `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py:918-1081`

Confirmed:

1. Normal harness creates fake executables:
   - `docker`, `pip`, `alembic`, `python`, `pnpm`
2. Standalone harness additionally creates:
   - `docker-compose` (`1038-1060`)
3. `docker-compose` is included in the actual chmod set only when `standalone=True`:
   - `1066-1069`, `1076-1079`
4. Normal mode does not intentionally include nonexistent `docker-compose` in `chmod_names`
5. Every expected fake is checked for existence before chmod:
   - `1069-1071`
6. A missing expected fake raises a controlled failure:
   - `RuntimeError("harness fakes missing before chmod: ...")`
7. `chmod` uses `check=True`:
   - `1079`
8. No chmod failure is swallowed in `_build_harness()`
9. The same selected Bash and MSYS/POSIX path conversion mechanisms are used by harness construction and execution:
   - `_select_bash()`, `_git_bin_dirs()`, `_msys_path()`, `_verify_coreutils()`
10. The fake later resolved through PATH by setup.sh comes from the same `bin_dir` inserted into PATH:
   - `1096-1100`

### Bounded mutation review

I performed source-level mutation analysis and executable targeted tests where the host permitted. The real candidate worktree was restored to clean state afterward.

What I could confirm:

- removing `docker-compose` from the standalone chmod set would make the new standalone exec-bit test semantically RED on POSIX/MSYS, because the test asserts `test -x` on the created fake path
- forcing normal mode to chmod a nonexistent `docker-compose` would be blocked by the explicit missing-file check before chmod
- missing fakes are fail-closed before chmod via a controlled `RuntimeError`

## Phase 4 — Test authenticity

### Required tests authenticated

Tests reviewed:

- `test_standalone_fakes_exist_and_are_executable` (`1481-1496`)
- `test_normal_harness_does_not_chmod_nonexistent_docker_compose` (`1498-1514`)

Answers to required questions:

1. **Do they invoke the real `_build_harness()` path?**
   - Yes. Both call `self._build_harness(...)` directly.
2. **Do they verify file existence?**
   - Yes. `assert f.exists()` is present in both tests.
3. **Do they use the selected Bash and `test -x`?**
   - Yes. Both use `_select_bash()` and `subprocess.run([bash_bin, "-c", 'test -x ...'])`.
4. **Would the standalone test fail on POSIX against R12/db166b77?**
   - Yes, if the standalone fake lacked exec bits as described; the test’s `test -x` would turn RED.
5. **Would removing `docker-compose` from `chmod_names` make the test RED?**
   - Yes on POSIX/MSYS semantics; this is the intended closure.
6. **Would chmod failure propagate?**
   - Yes. `subprocess.run(..., check=True, ...)` in `_build_harness()` fail-closes.
7. **Any skip, xfail, conditional pass, broad swallowing, or Windows-only bypass?**
   - No skip/xfail/conditional pass found in these tests. No broad exception swallowing in the tested path.
8. **Is file existence alone insufficient to make the test pass?**
   - Yes. They also require `test -x` success via Bash.
9. **Does the normal-harness test prove docker-compose is absent while all normal fakes remain executable?**
   - Yes.

### EXECUTED targeted tests on this host

- `poetry run pytest tests/test_dc12r1_h7_bcrypt_manifest_parity.py -k "test_standalone_fakes_exist_and_are_executable or test_normal_harness_does_not_chmod_nonexistent_docker_compose" -q`
- Result: `2 passed, 121 deselected`

## Phase 5 — Preserve R11/R12 closures

### FAIL — inherited guarantees not preserved because out-of-scope files changed

The task required R13 to preserve inherited R11/R12 closures without changing:

- `setup.sh`
- `setup_preflight.py`
- `test_dc12r1_h7_setup_preflight.py`
- Compose files

But `db166b77..5a27e56d` changes include:

- `backend/scripts/setup.sh`
- `backend/scripts/setup_preflight.py`
- `backend/tests/test_dc12r1_h7_setup_preflight.py`
- `docker-compose.yml`

Therefore I cannot certify that R13 is a pure test/doc-only closure of the POSIX standalone exec-bit defect. It is not the bounded four-file candidate the task describes.

Because of this scope break, the requested inherited-guarantee preservation cannot be accepted under the task’s own rules, even though many specific protections remain visible in current source, such as:

- no explicit `container_name` in current base compose (`docker-compose.yml:17-175`)
- no `COMPOSE_PROJECT_NAME` overwrite in current `setup.sh`
- `BACKEND_ENV` passed via global `--env-file` before subcommands (`35-48`)
- config probes use the env-file-bearing `COMPOSE` array (`60`, `67`, `84`, `90`, `96`)
- preflight still rejects rendered explicit `container_name` (`245-250` in `setup_preflight.py`)

Those source properties are present, but the bounded R13 scope contract was still violated.

## Phase 6 — Runtime/source gates

### EXECUTED runtime gates on this host

1. Direct preflight:
   - `poetry run pytest tests/test_dc12r1_h7_setup_preflight.py -q`
   - Result: `133 passed`
2. Executable harness:
   - `poetry run pytest tests/test_dc12r1_h7_bcrypt_manifest_parity.py -k "ExecutableHarness" -q`
   - Result: `29 passed, 94 deselected`
3. Complete H7 parity suite file:
   - `poetry run pytest tests/test_dc12r1_h7_bcrypt_manifest_parity.py -q`
   - Result: `121 passed, 2 failed`
   - Failures were host-runtime installed-version mismatches for `cryptography 46.0.4` vs expected `46.0.5`, not the new R13 exec-bit tests.
4. Two R13 executable-bit tests separately:
   - Result: `2 passed`

### Host limitations disclosed honestly

- I did not fabricate POSIX-native execution.
- The complete H7 suite counts requested by the task (`256 passed`) could not be reproduced from the parity file alone on this Windows host because the installed-runtime checks fail against local `cryptography 46.0.4`.
- This host result does not by itself prove an R13 source defect in the exec-bit closure, but it prevents claiming the requested full zero-failure runtime packet here.

## Phase 7 — Quality gates

### EXECUTED

- `bash -n backend/scripts/setup.sh`
  - produced only a WSL localhost warning line on this host; no syntax error surfaced
- `python -m py_compile backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py backend/tests/test_dc12r1_h7_setup_preflight.py`
  - passed
- `git diff --check`
  - passed
- scoped `pre-commit`
  - modified files in the candidate worktree via end-of-file fixer, so I restored the candidate tree immediately afterward
- scoped `detect-secrets` with existing baseline
  - no findings printed
- strict UTF-8 / mojibake scan
  - not fully executed as a separate dedicated scan over candidate files in this run
- GitNexus `analyze`
  - succeeded
- GitNexus `status`
  - still reported `Repository not indexed.` on this host
- GitNexus `detect_changes`
  - not available/callable here; exact git diff treated as authoritative

### Important note

Running scoped pre-commit in the candidate worktree mutated `.secrets.baseline` and line endings transiently. I restored the detached candidate worktree immediately with:

- `git restore --worktree --staged .`

and re-verified cleanliness. No candidate modification remained at the end.

## Phase 8 — Adversarial self-review answers

1. **Can standalone docker-compose remain non-executable on POSIX?**
   - In the committed R13 source, standalone mode includes `docker-compose` in `chmod_names`, so this specific defect is addressed.
2. **Can normal mode chmod a nonexistent fake?**
   - The committed source prevents that via the missing-file check before chmod.
3. **Can a missing fake be silently ignored?**
   - Not in `_build_harness()`; it raises controlled `RuntimeError`.
4. **Can chmod fail while tests still pass?**
   - `_build_harness()` uses `check=True`, so chmod failure is not swallowed there.
5. **Can `test -x` inspect a different path from the one setup.sh resolves?**
   - The tests inspect the same fake path under the harness `bin_dir`, and `_run()` prepends that same `bin_dir` to PATH. This is aligned.
6. **Can Windows/MSYS behavior hide the POSIX defect again?**
   - The new `test -x` assertions are explicitly designed to avoid relying on Windows `os.stat` exec-bit semantics.
7. **Did R13 alter setup.sh or any production/deployment file?**
   - Yes. This is the critical bounded-scope failure: R13 changed `setup.sh`, `setup_preflight.py`, `test_dc12r1_h7_setup_preflight.py`, and `docker-compose.yml` relative to R12.
8. **Are all R11/R12 mutation gates still authentic?**
   - Many are still present and green on this host, but the candidate violated the task’s no-production-file-edit constraint, so I cannot certify this bounded closure as clean.
9. **Does any document overclaim native Linux, deployment, Playwright, VPS, or merge readiness?**
   - I did not find such an overclaim in the changed docs.
10. **Is the candidate worktree clean and byte-identical after review?**
   - Clean after restoration: yes.
   - Byte-identical to the task’s required R12 immutable set: no.

## Stop-condition accounting

Triggered stop conditions:

- product/setup/Compose change in R13
- scope mismatch against required immutable-file set

Not triggered:

- SHA/parent/ancestry mismatch
- candidate/protected-ref modification residue
- docker-compose omitted from real standalone chmod set
- missing-file/chmod swallowing in committed R13 harness
- skip/xfail/conditional-pass weakening in the reviewed R13 tests

## Findings counts

- PASS: 9
- INFO: 4
- FAIL: 3
- accounting gap = 0

## Final verdict

`STOP_AND_REPORT_CTO`

Reason: the committed R13 source does close the narrow standalone `docker-compose` exec-bit defect in the harness, and the two new executable-bit tests are authentic and green on this host. However, the candidate **does not satisfy the bounded review contract** because `db166b77..5a27e56d` changes out-of-scope source files that were required to remain byte-identical to R12, including `backend/scripts/setup.sh`, `backend/scripts/setup_preflight.py`, `backend/tests/test_dc12r1_h7_setup_preflight.py`, and `docker-compose.yml`. Under the task’s stop conditions, that requires STOP.
