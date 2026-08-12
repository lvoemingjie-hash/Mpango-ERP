# DC-12R1-H7-R2-V1 Adversarial Dependency Manifest Source Review

**Verdict:** `STOP_AND_REPORT_CTO`

## Scope

- Review only. No candidate edits performed.
- Base: `a6ef3aac0ab03615e9d70e08e504b9858baf61c5`
- Frozen candidate: `d1aa5d0a778e919587bd9e25e485e90a9c3cf5a1`
- Candidate branch: `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`
- Report branch: `reports/dc12r1-h7-r2-v1-kilo-review-2026-08-12`

Evidence labels:

- **EXECUTED** — run independently on this host.
- **STATIC** — verified directly from source.
- **GITNEXUS** — verified with GitNexus analyze/context/impact/status where available.
- **HISTORICAL-AUTH** — reconciled against committed ledger/docs.
- **ENV-GATED** — not independently runnable here; not fabricated.

## 1. Required proof gate

### 1.1 Isolated detached exact-candidate worktree — EXECUTED

I created a detached isolated worktree at:

`C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1_h7_r2_v1_review`

`git worktree add --detach ... d1aa5d0a778e919587bd9e25e485e90a9c3cf5a1`

Detached worktree status was clean: `## HEAD (no branch)`.

### 1.2 Candidate parent equals base — EXECUTED

`git rev-list --parents -n 1 d1aa5d0a778e919587bd9e25e485e90a9c3cf5a1` returned exactly:

- child: `d1aa5d0a778e919587bd9e25e485e90a9c3cf5a1`
- parent: `a6ef3aac0ab03615e9d70e08e504b9858baf61c5`

This passes.

### 1.3 Candidate delta is exactly five allowed files — EXECUTED

`git diff --name-only a6ef3aac..d1aa5d0a` returned exactly 5 files:

1. `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`
2. `backend/requirements.txt`
3. `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`
4. `docs/ai/CTO_CURRENT_OPS.md`
5. `docs/ai/PROJECT.md`

This passes.

### 1.4 Protected branch remains the base — EXECUTED

`git show-ref refs/remotes/origin/product-dev-recovered` returned:

- `a6ef3aac0ab03615e9d70e08e504b9858baf61c5 refs/remotes/origin/product-dev-recovered`

This passes.

### 1.5 `pyproject.toml` and `poetry.lock` byte-identity to base — EXECUTED

I diffed the candidate worktree copies against the protected-base workspace copies:

- `backend/pyproject.toml` — empty diff
- `backend/poetry.lock` — empty diff

This passes.

## 2. Overall review outcome

The candidate satisfies the authorized-file scope and the three-line `requirements.txt` edit. However, the committed fail-closed manifest gate is **not authentic**: its parsers silently overwrite duplicates and normalized-name collisions instead of failing closed. That allows false-green outcomes for exactly the governed package class this task is meant to protect.

This is a merge blocker.

## 3. Authorized delta review

### 3.1 Requirements authorized lines — EXECUTED + STATIC

`backend/requirements.txt` candidate exact lines:

- `bcrypt==4.0.1 ; python_version >= "3.11" and python_version < "4.0"` — line 8
- `cryptography==46.0.5 ; python_version >= "3.11" and python_version < "4.0"` — line 20
- `openpyxl==3.1.5 ; python_version >= "3.11" and python_version < "4.0"` — line 35
- `passlib==1.7.4 ; python_version >= "3.11" and python_version < "4.0"` — line 37

The diff against base confirms exactly three authorized changes in `requirements.txt`:

- bcrypt `5.0.0 -> 4.0.1`
- cryptography `46.0.4 -> 46.0.5`
- new openpyxl line inserted alphabetically between `markupsafe` and `packaging`

No fourth `requirements.txt` line changed.

### 3.2 Duplicate normalized package names in the committed file — EXECUTED

I independently recomputed normalized names across the actual committed `requirements.txt` and found no duplicates in the **candidate file as committed**.

This means the candidate file content is clean; the blocker is in the **test gate’s parser behavior**, not in the current manifest contents.

## 4. Manifest parser authenticity — merge blocker

### 4.1 False-green overwrite in `_parse_requirements` — STATIC + EXECUTED

Parser code:

- `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py:55-64`

Exact behavior:

- `_parse_requirements()` stores entries into `out[_norm(name)] = version`
- duplicate names are silently overwritten by the last occurrence
- no duplicate detection exists

Independent mutation demonstration on the parser logic produced:

- duplicate governed package lines:
  - input: `bcrypt==5.0.0` then `bcrypt==4.0.1`
  - parser result: `{"bcrypt": "4.0.1"}`

Therefore a bad earlier governed line can be hidden by a later good line and the committed test still goes green. That is not fail-closed.

### 4.2 Normalized-name collision false green — STATIC + EXECUTED

Normalizer code:

- `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py:51-52`

It collapses `-`, `_`, and `.` to `-` and lowercases.

Independent mutation demonstration:

- input lines:
  - `et_xmlfile==1.1.0`
  - `et-xmlfile==2.0.0`
- parser result: `{"et-xmlfile": "2.0.0"}`

So normalized-name collisions are also silently overwritten instead of rejected. That is another false-green path.

### 4.3 Malformed/non-exact requirement parsing is not fail-closed — STATIC + EXECUTED

Regex:

- `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py:61`
  - `^([A-Za-z0-9_.\-]+)==([^;\s]+)`

Independent mutation demonstration:

- input: `bcrypt===4.0.1`
- parser result: `{"bcrypt": "=4.0.1"}`

This is not an exact pinned requirement parse. The malformed line is partially accepted rather than rejected.

### 4.4 False-green overwrite in `_parse_lock` — STATIC + EXECUTED

Lock parser code:

- `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py:67-69`

It returns a dict comprehension keyed by normalized name. Duplicate lock package names would silently overwrite rather than fail closed.

Independent mutation demonstration:

- entries: `bcrypt 5.0.0`, then `bcrypt 4.0.1`
- result: `{"bcrypt": "4.0.1"}`

So duplicate package entries in `poetry.lock` would also be hidden by last-wins overwrite.

### 4.5 Severity assessment

This is not a theoretical style issue. The committed gate claims to be a fail-closed authoritative manifest-parity test, but duplicate governed package lines, duplicate lock entries, and normalized-name collisions can be masked by dict overwrite.

Because this can hide one of the governed packages (`bcrypt`, `cryptography`, `openpyxl`, `passlib`) from the authoritative gate, this is a **merge blocker**.

## 5. Full runtime dependency truth

### 5.1 Direct main dependency parity — EXECUTED

I independently recomputed every direct `tool.poetry.dependencies` main dependency (excluding `python`) against both `requirements.txt` and `poetry.lock`.

Result:

- direct main dependency count: **24**
- all 24 are present in both `requirements.txt` and `poetry.lock`
- no direct main dependency version drift remains
- no fourth direct-runtime drift exists

This supports the narrow claim of **direct-manifest parity**.

### 5.2 `openpyxl` transitive lock dependency — EXECUTED + STATIC

`poetry.lock` shows:

- `et-xmlfile` package entry at `backend/poetry.lock:1235-1243`
- `openpyxl` package entry at `backend/poetry.lock:2280-2292`
- `openpyxl` dependency declaration: `et-xmlfile = "*"` at line 2292

The candidate `requirements.txt` does **not** carry an exact `et-xmlfile` pin.

### 5.3 Reproducibility / parity distinction

This means:

- **Direct-manifest parity:** yes, reconciled.
- **Complete transitive lock parity for the pip path:** no, not proven by source.

Without an exact `et-xmlfile` requirement in the pip manifest, the pip path is not source-pinned to the lock’s exact transitive package set. It may currently resolve `et-xmlfile 2.0.0`, but that is runtime resolution behavior, not committed complete-installation-path lock parity.

### 5.4 Overclaim in the candidate evidence — STATIC

The ledger repeatedly claims broader parity than the source warrants, e.g. “install paths must resolve identical runtime versions” and “two backend install paths must resolve the same runtime versions,” while the actual source change reconciles only direct runtime dependencies and leaves the pip path without an exact transitive `et-xmlfile` pin.

That is an evidence overclaim.

## 6. Install-path wiring authenticity

### 6.1 `setup.sh` active executable pip path — STATIC

`backend/scripts/setup.sh` contains an active command, not a comment:

- `cd backend` — line 43
- `pip install -r requirements.txt` — line 44
- followed by active migration commands

This passes the install-path wiring check.

### 6.2 Dockerfile active Poetry/lock path — STATIC

`backend/Dockerfile` contains active lock-bound install steps:

- `COPY pyproject.toml poetry.lock ./` — line 29
- `RUN poetry install --no-root --only main --no-ansi` — line 36

This is active executable wiring, not comment-only evidence.

### 6.3 Mutation-check note

The committed H7 test only checks substring presence for these install paths:

- `test_setup_sh_consumes_requirements` — lines 160-164
- `test_dockerfile_consumes_poetry_and_lock` — lines 166-172

That is weaker than actual executable-branch proof. My independent source review confirms the current candidate files are active, but the committed gate itself is not robust against some dead-command/comment-only mutations.

## 7. Runtime-gate source review

### 7.1 Wrong-venv risk

`TestH7R2InstalledRuntime` reads versions from `importlib.metadata.version()` via `_version()` at lines 181-185, which is the correct package-metadata source **for the current interpreter**.

However, nothing in the committed test itself proves it is running inside the intended venv. That is normal for a Python test, but it means the “cannot accidentally inspect the wrong venv” claim is stronger than the source can prove on its own.

### 7.2 Four-version metadata reads — STATIC

All four governed package versions are asserted through `importlib.metadata.version()` in `test_installed_version_matches_manifest` — lines 187-191.

That portion is meaningful.

### 7.3 Meaningfulness of behavior checks — STATIC

Meaningful checks present:

- passlib bcrypt round-trip — lines 193-201
- `core.security` hash/verify including long input — lines 203-214
- openpyxl workbook create/write/read — lines 215-221
- cryptography import + version match — lines 223-226
- FastAPI app import type assertion — lines 228-233

These are real source-level checks, not pure smoke placeholders.

### 7.4 30-node count authenticity — STATIC

Collected structure of the committed file implies 30 tests:

- 4x `test_requirements_txt_resolves_expected`
- 4x `test_poetry_lock_resolves_expected`
- 4x `test_requirements_and_lock_agree`
- 1x bcrypt spec gate
- 1x cryptography floor gate
- 4x `test_resolved_versions_satisfy_pyproject`
- 1x passlib unchanged
- 1x setup.sh wiring
- 1x Dockerfile wiring
- 4x installed versions
- 1x passlib round-trip
- 1x core.security round-trip
- 1x openpyxl workbook
- 1x cryptography import
- 1x FastAPI import

Total: **30**

So the 30-test count claim is structurally plausible.

### 7.5 Hypothesis flake disclosure — STATIC + HISTORICAL-AUTH

The candidate ledger discloses a single Hypothesis flake in a focused bundle and explicitly says the authoritative evidence is the later full gate. I found no sign in the committed source that the H7 manifest test itself uses reruns, hidden deselection, or local skip weakening.

That disclosure appears honest.

## 8. Evidence truth review

### 8.1 H7-R1 stop and H7-R2 authorization — STATIC

`docs/ai/CTO_CURRENT_OPS.md:193-205` accurately states:

- H7-R1 stopped because bcrypt was not the only material drift
- H7-R2 was CTO-authorized for exactly three corrections

This is consistent with the candidate ledger.

### 8.2 No forbidden deployment/VPS/Playwright/native-pass claim — STATIC

The candidate docs/ledger do **not** claim:

- local deployment success
n- Playwright validation
- VPS deployment validation
- native Linux `setup.sh` PASS on this Windows host

In fact the ledger explicitly says native `setup.sh` execution on Linux awaits independent verification.

### 8.3 29-vs-48 skip difference disclosure — STATIC

The candidate ledger explicitly discloses the 29-vs-48 skip-set difference in §9 and attributes it to environment, not code. That disclosure exists and is not hidden.

### 8.4 GitNexus status overclaim in ledger — STATIC + EXECUTED

The candidate ledger claims `GitNexus status: up-to-date` at `a6ef3aa`. On this host, after `npx gitnexus analyze` in the detached worktree, `npx gitnexus status` still returned `Repository not indexed.`

So I could independently execute `analyze`, but not obtain a working `status` confirmation in that detached review worktree. I therefore cannot authenticate the ledger’s GitNexus status claim from this host.

This is not the primary blocker, but it reduces confidence in the evidence narration.

## 9. Quality checks run for this review

- `git diff --check` — clean
- scoped `detect-secrets` on the two report files — clean
- UTF-8 read check — clean
- mojibake scan — clean
- GitNexus `analyze` — executed in detached candidate worktree
- `detect_changes` — unavailable in this CLI; exact git diff evidence used instead
- candidate detached worktree left clean

## 10. Finding accounting

- P0: 0
- P1: 0
- P2: 2
- P3: 1
- INFO: 4
- NEEDS_PROOF: 0
- Reviewed findings = mapped findings: 7
- accounting gap = 0

## 11. Final verdict

`STOP_AND_REPORT_CTO`

Reason: the committed authoritative fail-closed manifest gate is not actually fail-closed. Duplicate governed requirement lines, normalized-name collisions, malformed exact pins, and duplicate `poetry.lock` package entries can be silently masked by parser overwrite. That is a merge blocker for a dependency-manifest reconciliation slice whose safety depends on trustworthy manifest validation.
