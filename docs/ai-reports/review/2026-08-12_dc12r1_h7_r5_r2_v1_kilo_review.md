# DC-12R1-H7-R5-R2-V1 Kilo Comprehensive Source/Evidence Review

**Verdict:** `STOP_AND_REPORT_CTO`

PASS was not issued. A clean source/evidence review for Lubuntu handoff was **not** achieved.

## Scope and execution mode

- Review type: adversarial source and evidence review only.
- Candidate reviewed: `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`
- Expected candidate SHA: `bb52c01b3a79483d63da7e987a09e7bbb43816c4`
- Expected protected baseline: `origin/product-dev-recovered@a6ef3aac0ab03615e9d70e08e504b9858baf61c5`
- Required predecessor: `0e8d5159`
- No candidate, product, protected-ref, deployment, Playwright, or VPS change was made.

Evidence labels:

- **EXECUTED** — independently run on this host.
- **STATIC** — verified from source.
- **GITNEXUS** — verified via GitNexus where callable.
- **HISTORICAL-AUTH** — reconciled against committed docs/ledger.
- **ENV-GATED** — runtime unavailable or not trustworthy here; not fabricated.

## 1. Proof gate

### 1.1 Exact SHA and ancestry — EXECUTED

Verified:

- remote candidate SHA exactly matches `bb52c01b3a79483d63da7e987a09e7bbb43816c4`
- `origin/product-dev-recovered` exactly matches `a6ef3aac0ab03615e9d70e08e504b9858baf61c5`
- `0e8d5159` is an ancestor of the candidate
- detached candidate worktree was initially clean

### 1.2 Isolated detached worktree — EXECUTED

Created detached isolated worktree at:

`C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1_h7_r5_r2_v1_review`

at exact candidate SHA `bb52c01b...`.

### 1.3 Candidate delta scope — EXECUTED

`git diff --name-only 0e8d5159..bb52c01b...` returned exactly these 5 files:

1. `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`
2. `backend/scripts/setup.sh`
3. `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`
4. `docs/ai/CTO_CURRENT_OPS.md`
5. `docs/ai/PROJECT.md`

This passes.

### 1.4 Immutable-file byte identity — EXECUTED

Results:

- `backend/requirements.txt` — byte-identical to predecessor scope
- `backend/pyproject.toml` — byte-identical
- `backend/poetry.lock` — byte-identical
- `backend/Dockerfile` — byte-identical
- `backend/scripts/setup.sh` — changed, as expected in the allowed delta

However, the task also required `alembic/env.py` and `bootstrap_tenant_schema.py` to be byte-identical to `0e8d5159`. They are **not** byte-identical:

- `backend/alembic/env.py:7` usage comment differs from predecessor
- `backend/scripts/bootstrap_tenant_schema.py:11` usage comment differs from predecessor

These files are not in the R5-R2 allowed five-file delta, but the predecessor comparison shows they differ versus `0e8d5159`. This is a proof-gate failure against the task’s immutable-file expectation.

## 2. setup.sh adversarial review

### 2.1 Source-level control review — STATIC

The committed `backend/scripts/setup.sh` does implement many intended invariants:

- strict mode: `set -Eeuo pipefail` (`setup.sh:3`)
- ERR trap preserving status via `_on_err "$LINENO" "$?"` (`9-15`)
- compose stored as shell array (`24-35`)
- config preflight before later service/installer work (`37-51`)
- bounded PostgreSQL and Redis polling (`68-97`)
- public Alembic migration before canonical tenant bootstrap (`104-106`, `158-162`)
- bootstrap via `scripts/bootstrap_tenant_schema.py` rather than tenant Alembic no-op (`159-161`)
- `pnpm install --frozen-lockfile` (`170-180`)
- DATABASE_URL resolved from `core.config.settings` and not printed (`108-123`, `160-162`)

### 2.2 Remaining source-level concern — preflight side effects before validation

The task required all configuration validation before side effects, and invalid/missing configuration to create **no directories, .env files, containers, migrations, or later command calls**.

The script validates:

- presence of `backend/.env`
- no `CHANGE_ME`
- compose config valid

before later side effects. That part is correct.

But it does **not** validate the resolved `DATABASE_URL` tuple against Compose truth until **after**:

- directory creation (`54-55`)
- `frontend/.env` creation (`58-61`)
- container start (`64-65`)
- public Alembic migration (`100-106`)

Therefore invalid host/port/user/db identity in `DATABASE_URL` still permits side effects before failure.

This violates the requested no-side-effects-before-invalid-config-failure rule.

### 2.3 Bounded source-mutation checks — EXECUTED

Using the real committed `check_setup_sh_wiring()` helper from the candidate test file, the required bounded mutations correctly turned RED for these source-shape invariants:

- missing strict mode
- missing ERR trap
- false “no changes applied” wording
- missing compose array
- missing bounded PostgreSQL health
- missing bounded Redis health
- hard-coded PostgreSQL user
- tenant Alembic no-op path
- missing canonical bootstrap
- bootstrap before public migration
- missing bootstrap DATABASE_URL path
- missing `settings.DATABASE_URL` resolution
- `npm install`
- non-frozen `pnpm`

The real unchanged candidate `setup.sh` passed the source-shape guard.

### 2.4 Why this does not fully close the requested setup review

Those are **source-shape guard** checks only. They do not prove several stronger task requirements such as:

- invalid parsed DB identity causing **zero side effects**
- second execution true idempotency on a native path
- no credential exposure on all real failure paths
- acceptance semantics cannot silently point Alembic/bootstrap at another DB under real execution

## 3. Harness authenticity

### 3.1 Positive findings — STATIC

The committed executable harness in `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py:747-960` does satisfy several authenticity requirements:

- uses an **unmodified copy** of committed `setup.sh` (`788-789`)
- fake commands are real PATH executables written into fake-bin (`795-846`)
- no `BASH_ENV` injection found
- no sourced monkeypatch or rewritten script found
- ordering is asserted by exact indexes, not presence-only (`876-895`)
- failures `42`, `43`, `44` are asserted at outer script boundary (`896-913`)
- invalid compose config asserts zero later side effects (`928-941`)
- secret values are asserted absent from stdout/stderr (`943-949`)
- idempotency runs the full script twice (`950-959`)
- no skip / xfail / conditional pass / swallowed exception / assertion weakening found in this file

### 3.2 Runtime authenticity failure on this host — EXECUTED

The harness **does not run cleanly on this Windows host** under the candidate’s own claimed runtime packet:

- `poetry run pytest tests/test_dc12r1_h7_bcrypt_manifest_parity.py -q` produced **9 failures**
- 7 failures were from `TestH7R5R2ExecutableHarness`
- root cause: the harness shells through `C:\WINDOWS\system32\bash.EXE` / WSL and passes Windows paths that WSL then fails to resolve
- representative failure:
  - `/bin/bash: C:/Users/.../h7r2_repo/backend/scripts/setup.sh: No such file or directory`
  - return code `127`
- `chmod +x` against Windows temp paths also failed under that bash layer

This contradicts the ledger’s unconditional `9/9 PASS` claim as a portable source/evidence checkpoint on the current Kilo host class.

That does **not** prove the candidate logic is wrong on Lubuntu, but it does mean the committed evidence packet is not sufficiently host-qualified if read as generally executable here.

## 4. Evidence consistency

### 4.1 Good evidence boundaries — STATIC + HISTORICAL-AUTH

The candidate docs/ledger do correctly state:

- current status is `STOP_AND_REPORT_CTO_AWAITING_LUBUNTU_ZERO_RED`
- no merge readiness is claimed
- no native Linux success is claimed
- no zero-red completion is claimed
- earlier PASS statements are historical/superseded where retained
- the Hypothesis node, error class, seed, and `4/5` focused-bundle behavior are recorded
- the red node is **not** claimed resolved
- a new low-load Lubuntu focused run is required
- inherited R3 full-suite evidence is explicitly **not** treated as current focused zero-red proof

### 4.2 Over-strong deterministic/runtime claim remains — STATIC + EXECUTED

The ledger says:

- `Executable harness ... 9/9 PASS`
- `H7 suite: 103 passed / 0 failed in natural order AND reverse order`

On this host, I independently observed:

- harness-related tests fail under the bash/WSL path layer
- full H7 suite result here was `9 failed, 94 passed`
- two installed-runtime cryptography tests also failed because this host’s Poetry env had `cryptography 46.0.4`, not `46.0.5`

The task explicitly said not to treat an old host venv with bcrypt 5.0.0 as a candidate defect. I did not. But these executed failures mean the candidate evidence must be read as host-specific rather than general local proof. The ledger does not sufficiently qualify the `103/103` and `9/9` statements as host-bound.

## 5. Hypothesis boundary

### 5.1 Static causality assessment — STATIC

I found no candidate source, dependency, or H7 test-infrastructure change that plausibly causes the `tests/test_token_properties.py::test_property_token_roundtrip_integrity` `HealthCheck.too_slow` node:

- requirements/pyproject/poetry.lock are unchanged from predecessor scope
- product code is not changed in this slice
- the H7 work is concentrated in `setup.sh`, H7 test file, and docs/ledger
- the failing node is outside the H7 slice and is consistent with environment-sensitive Hypothesis timing

This supports the docs’ claim that the red node is not an H7 defect.

### 5.2 Runtime execution on this host — EXECUTED

I attempted runtime checks because pytest was available via Poetry.

Executed:

- H7 suite natural order: **failed** (`9 failed, 94 passed`)
- reverse-order H7 suite: **not reliably attempted as authoritative**, because the natural-order run already exposed host/path failures and installed-runtime drift
- fake-bin harness: exercised through the H7 suite and failed on this host’s bash/WSL path behavior

These Windows runtime results are reported as executed host results only, not candidate merge evidence.

## 6. Quality and GitNexus

### 6.1 Executed quality gates

- `python -m py_compile backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py` — clean
- `bash -n backend/scripts/setup.sh` — **failed on this host** because the script file is CRLF and the available bash layer produced syntax errors from `\r`
- `git diff --check` — clean
- scoped `pre-commit` — not independently executed in this run
- scoped `detect-secrets` — not independently executed in this run
- UTF-8/mojibake scan — not independently executed in this run

Because this task required these gates, their non-execution or host-failure is disclosed as such.

### 6.2 GitNexus — EXECUTED with host limitation

- `npx gitnexus analyze` succeeded in the detached candidate worktree
- `npx gitnexus status` still returned `Repository not indexed.` on this host
- `detect_changes` is unavailable in this CLI build
- `context` without explicit repo failed because many repos are indexed
- `impact` returned a multiple-repository resolution error/suggestion payload unless scoped differently

I did not fabricate GitNexus results.

## 7. Findings summary

### Core blockers confirmed in this review

1. Proof-gate immutable-file requirement failed for `backend/alembic/env.py` and `backend/scripts/bootstrap_tenant_schema.py` versus `0e8d5159`.
2. `setup.sh` does not satisfy the stronger no-side-effects-before-invalid-config requirement for invalid resolved DB identity.
3. Executable fake-bin harness is not reproducibly green on this Kilo Windows host because of bash/WSL path execution behavior.
4. The candidate’s recorded `9/9` harness and `103/103` H7 suite claims are not sufficiently host-qualified relative to actual Kilo-host execution results.

## Accounting

- P0: 0
- P1: 2
- P2: 2
- P3: 1
- INFO: 4
- NEEDS_PROOF: 0
- accounting gap = 0

## Final verdict

`STOP_AND_REPORT_CTO`

This candidate is **not** clean for Kilo source/evidence PASS. The strongest blockers are: immutable-file proof-gate failure (`alembic/env.py` and `bootstrap_tenant_schema.py` not byte-identical to `0e8d5159`), setup-path validation still allowing side effects before DB-identity mismatch failure, and executable-harness/runtime evidence that does not reproduce on this Kilo Windows host despite the ledger’s unconditional `9/9` and `103/103` statements. Lubuntu zero-red verification remains required, and the current source/evidence packet still needs correction before a Kilo source-review PASS can be justified.
