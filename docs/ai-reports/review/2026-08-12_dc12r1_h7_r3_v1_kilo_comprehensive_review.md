# DC-12R1-H7-R3-V1 Comprehensive Adversarial Final Source Review

**Verdict:** `STOP_AND_REPORT_CTO`

## Scope

- Review only. No candidate edits performed.
- Root base: `a6ef3aac0ab03615e9d70e08e504b9858baf61c5`
- R2 parent: `d1aa5d0a778e919587bd9e25e485e90a9c3cf5a1`
- Frozen R3 candidate: `6cd37e0339067952e0d21df6d65f19012ba88d70`
- Candidate branch: `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`
- Prior Kilo STOP report: `ea3baf416326be91995b953f8545ae28f14b590a`
- Report branch: `reports/dc12r1-h7-r3-v1-kilo-comprehensive-review-2026-08-12`

Evidence labels:

- **EXECUTED** — independently run on this host.
- **STATIC** — verified from source.
- **GITNEXUS** — verified with GitNexus where callable.
- **HISTORICAL-AUTH** — reconciled against committed docs/ledger.
- **ENV-GATED** — not independently rerun here; not fabricated.

## Phase 1 — Proof gate

### 1. Isolated exact-candidate detached worktree — EXECUTED

Created detached isolated worktree at:

`C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1_h7_r3_v1_review`

with:

`git worktree add --detach ... 6cd37e0339067952e0d21df6d65f19012ba88d70`

Candidate tree remained clean: `## HEAD (no branch)`.

### 2. Direct parent exact — EXECUTED

`git rev-list --parents -n 1 6cd37e0339067952e0d21df6d65f19012ba88d70`
returned exactly:

- child: `6cd37e0339067952e0d21df6d65f19012ba88d70`
- parent: `d1aa5d0a778e919587bd9e25e485e90a9c3cf5a1`

### 3. Root base ancestor — EXECUTED

`git merge-base --is-ancestor a6ef3aac0ab03615e9d70e08e504b9858baf61c5 6cd37e0339067952e0d21df6d65f19012ba88d70`
exited `0`.

### 4. Protected ref unchanged — EXECUTED

`origin/product-dev-recovered` remained:

- `a6ef3aac0ab03615e9d70e08e504b9858baf61c5`

### 5. R3 delta and aggregate delta exact — EXECUTED

Both:

- `git diff --name-only d1aa5d0a..6cd37e03`
- `git diff --name-only a6ef3aac..6cd37e03`

returned exactly the same five files:

1. `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`
2. `backend/requirements.txt`
3. `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`
4. `docs/ai/CTO_CURRENT_OPS.md`
5. `docs/ai/PROJECT.md`

### 6. `pyproject.toml` and `poetry.lock` byte-identical to root base — EXECUTED

- `backend/pyproject.toml` — empty diff
- `backend/poetry.lock` — empty diff

### 7. Proof-gate conclusion

Phase 1 passes.

## Phase 2 — Independent package truth

### Independent recomputation — EXECUTED

I parsed `requirements.txt`, `pyproject.toml`, and `poetry.lock` independently without importing candidate parser helpers.

Results:

- requirements normalized package count: **70**
- Poetry `groups` containing `main` normalized package count: **70**
- missing: **0**
- extra: **0**
- version mismatch: **0**
- duplicate normalized names in requirements: **0**
- duplicate normalized names in Poetry main lock: **0**

Governed versions verified:

- `bcrypt` -> `4.0.1`
- `cryptography` -> `46.0.5`
- `openpyxl` -> `3.1.5`
- `et-xmlfile` -> `2.0.0`
- `passlib` -> `1.7.4`

No fourth package/version drift remains.

### Boundary of what this proves

This proves **name/version parity** between `requirements.txt` and the Poetry main-runtime lock package set.

It does **not** prove:

- marker equivalence
- extras equivalence
- lock hash equivalence
- source/resolver equivalence
- full installer-behavior equivalence

## Phase 3 — Requirements parser adversarial matrix

### Real helper executed — EXECUTED

I executed mutations against the committed `parse_requirements_text()` logic by extracting and executing the real helper implementation from `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`.

### Good news

The helper correctly rejects:

- conflicting duplicate
- identical duplicate
- normalized-name collision
- trailing garbage
- multiple specifiers
- `>=`, `<=`, `~=`, `!=`, `===`
- wildcard pin
- URL/direct reference
- editable/include/constraint/index-option lines
- invalid marker
- duplicate names with different markers
- non-PEP440 version

It correctly accepts empty and comment-only files.

### Material blocker found

It also accepts:

- `uvicorn[standard]==0.40.0` -> result `{'uvicorn': '0.40.0'}`

and `main_runtime_deltas()` reports baseline parity for a **marker-only mutation** of the committed `et-xmlfile==2.0.0` line.

So extras and marker changes can alter installed package-set behavior while the committed parity helpers still report name/version parity.

That is acceptable only if the evidence claims stay strictly scoped to name/version parity. The candidate still uses stronger wording such as “full main-runtime parity” and “same main-runtime packages,” which is materially broader than what the helpers can actually prove.

## Phase 4 — Poetry lock parser adversarial matrix

### Real helper executed — EXECUTED

I executed mutations against the committed `parse_main_lock_packages()` logic.

### Good news

The helper correctly rejects:

- duplicate same/conflicting entries
- normalized-name collision
- missing/null/empty name
- missing/null/empty version
- missing/null groups
- non-mapping package entries
- duplicate package split across dev/main groups

### Merge-blocking contract failures

The stated contract says every entry must have a nonempty `name`, `version`, and `groups`.

Actual behavior does **not** enforce that fully:

- non-string `name` -> uncaught `AttributeError`, not controlled validation failure
- non-string `version` -> silently accepted into parity map
- empty `groups` -> silently accepted/excluded
- `groups` as string -> silently accepted/included
- `groups` as dict -> silently accepted/included
- `groups` list containing non-string values -> silently accepted
- malformed group data `['m','a','i','n']` -> silently accepted/excluded
- malformed top-level non-list input produces an unrelated iteration-driven error path

This violates the file’s own advertised fail-closed parser contract.

## Phase 5 — Parity helper and tests

### 1. `main_runtime_deltas()` mutation coverage — EXECUTED

Independent mutations proved:

- baseline -> `([], [], [])`
- removing each governed package (`bcrypt`, `cryptography`, `openpyxl`, `et-xmlfile`, `passlib`) is detected in `missing`
- mutating `et-xmlfile` version is detected in `mismatch`

### 2. Marker-only mutation — EXECUTED

Changing only the marker on committed `et-xmlfile==2.0.0` preserved `([], [], [])` from `main_runtime_deltas()`.

This confirms marker behavior is intentionally **outside** the committed parity contract. Docs sometimes say that clearly, but not everywhere.

### 3. Helpers are real committed helpers — EXECUTED + STATIC

The mutation work used the real committed helper implementations, not copied substitute logic.

### 4. Actual focused collection count — EXECUTED

AST expansion of parametrize decorators confirmed **44** collected test nodes.

### 5. Order independence, skip/xfail, source-text-only substitute — STATIC + HISTORICAL-AUTH

- no `skip`/`xfail` found in the committed H7-R3 test file
- docs/ledger say natural and reverse order were both run
- no copied parser substitute is present in the committed test module

### 6. Wrong-exception / wrong-reason risk — EXECUTED

This phase fails.

At least one malformed lock case raises an unrelated `AttributeError` (`non-string name`) instead of a controlled parser validation error, and several malformed cases succeed silently. That violates the intended rejection semantics.

## Phase 6 — Install-path authenticity

### Source truth — STATIC

Active commands exist in source:

- `backend/scripts/setup.sh:43-48`
  - `cd backend`
  - `pip install -r requirements.txt`
  - `alembic upgrade ...`
- `backend/Dockerfile:29-36`
  - `COPY pyproject.toml poetry.lock ./`
  - `RUN poetry install --no-root --only main --no-ansi`

### Committed test weakness — STATIC

Install-path tests only assert substring presence:

- `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py:215-221`

They do not distinguish:

- commented command vs active command
- dead branch vs executable branch
- inert string literal vs executed instruction

So the committed install-path authenticity tests are not robust against comment-only/dead-branch false greens.

## Phase 7 — Runtime and security evidence review

### What I could independently verify from source/evidence

- runtime evidence is described as two fresh envs and two full backend gates
- Docker evidence is explicitly marked inherited from R2, not claimed as R3 rerun
- 29-vs-48 skip differences are narrowed away for this slice because R3 reports 29/29 and compares against R2 3396 totals, not the older 48-skip historical sessions
- Hypothesis flake is disclosed as R2 focused-bundle transient evidence and explicitly not used as authoritative full-gate proof

### What I did not independently rerun

- fresh venv runtime proof
- focused 247-node run
- full 3366/3366 backend gates
- Docker image build/run

These remain **ENV-GATED** here. I did not fabricate runtime execution.

### Source-level assessment

The committed runtime assertions are substantive in the test module:

- `importlib.metadata` version checks for all five governed packages
- passlib round-trip
- `core.security` hash/verify with long input
- openpyxl + `et_xmlfile` import/workbook
- cryptography import/version
- FastAPI app import

## Phase 8 — Evidence truth

### Confirmed

- all three prior Kilo findings are explicitly named as closed in the R3 ledger
- H7-R2 PASS is explicitly marked `SUPERSEDED_BY_H7_R3`
- docs deny deployment / Playwright / VPS / native `setup.sh` PASS claims
- SHAs, five-file scope, and 70/70 parity counts match executed source evidence

### Material overclaim still present

The candidate still uses stronger phrases such as:

- `Full Main-Runtime Parity Closure`
- `full main-runtime parity`
- `the two backend install paths must resolve the same main-runtime packages`

But the committed helpers demonstrably ignore marker-only behavior and accept extras exact pins while reducing them to canonical name/version parity. So the strongest safe claim is only:

- identical normalized package names
- exact versions

Anything stronger is an evidence overclaim.

## Phase 9 — Quality and GitNexus

### Quality — EXECUTED

- `git diff --check` — clean
- detached candidate worktree remained clean
- scoped `detect-secrets` for review artifacts — clean
- UTF-8 / mojibake checks for review artifacts — clean

### GitNexus — EXECUTED

- `npx gitnexus analyze` succeeded in detached candidate worktree
- `npx gitnexus status` still returned `Repository not indexed.` on this host
- `detect_changes` is not exposed by this CLI build; exact diff evidence used instead

So GitNexus analyze was runnable, but status was not independently reproducible on this host.

## Findings summary

### Stop conditions hit

Triggered stop conditions:

- malformed entry silently included/excluded
- test passing/failing for wrong exception/reason
- material evidence overclaim

## Accounting

- P0: 0
- P1: 0
- P2: 3
- P3: 1
- INFO: 4
- NEEDS_PROOF: 0
- reviewed findings = mapped findings: 8
- accounting gap = 0

## Final verdict

`STOP_AND_REPORT_CTO`

The candidate fixes the original R2 duplicate-overwrite problems and closes the missing `et-xmlfile` package/version drift. However, the R3 lock parser is still not genuinely fail-closed for malformed input, the parity helpers still allow extras/marker-driven package-set false greens while some docs use stronger-than-proven parity wording, and the install-path authenticity tests remain substring-only. These are authoritative-gate authenticity defects in the committed candidate and block approval.
