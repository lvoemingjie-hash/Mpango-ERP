# DC-12R1-H7-R4-R1-V1 Existing-Findings Final Closure Review

**Verdict:** `STOP_AND_REPORT_CTO`

## Scope

Bounded closure review only for:

- `KILO-H7R3V1-001`
- `KILO-H7R3V1-002`
- `KILO-H7R3V1-003`
- `KILO-H7R3V1-004`
- the two CTO-confirmed R4 false-green paths

No candidate edits were made.

## Phase 1 — Proof

### Detached exact-candidate worktree — EXECUTED

Created isolated detached worktree at:

`C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1_h7_r4_r1_v1_review`

at exact candidate:

`7adcd54ca9b7c89cf8be71b243cf94541d6cd6a9`

### Parent / baseline / scope — EXECUTED

- direct parent of candidate is exactly `fc8168207ac8703d9c3142072c939b3b44ad724c`
- `origin/product-dev-recovered` remains exactly `a6ef3aac0ab03615e9d70e08e504b9858baf61c5`
- R4-R1 delta is exactly 4 files:
  1. `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`
  2. `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`
  3. `docs/ai/CTO_CURRENT_OPS.md`
  4. `docs/ai/PROJECT.md`
- aggregate H7 delta is exactly 5 files:
  1. `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`
  2. `backend/requirements.txt`
  3. `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`
  4. `docs/ai/CTO_CURRENT_OPS.md`
  5. `docs/ai/PROJECT.md`

### Byte-identity checks — EXECUTED

Byte-identical to R4 / protected base where required:

- `backend/requirements.txt` == R4
- `backend/pyproject.toml` == protected base
- `backend/poetry.lock` == protected base
- `backend/Dockerfile` == R4
- `backend/scripts/setup.sh` == R4

### Candidate cleanliness — EXECUTED

Detached candidate worktree remained clean: `## HEAD (no branch)`.

## Phase 2 — `KILO-H7R3V1-001` closure

### Real helper executed — EXECUTED

I executed the committed `parse_main_lock_packages()` helper against the required malformed inputs.

All bounded mutations raised controlled `ValueError` with intended diagnostics:

- non-list top-level packages
- non-dict package entry
- name missing / null / non-string / empty / whitespace
- version missing / null / non-string / empty / whitespace
- groups missing / null / string / dict / empty list
- groups containing null / non-string / empty / whitespace
- duplicate groups
- normalized duplicate names across same and different groups

No `AttributeError`, no silent inclusion, and no silent exclusion were reproduced.

Conclusion: `KILO-H7R3V1-001` is closed.

## Phase 3 — `KILO-H7R3V1-002` closure

### Real requirements helper executed — EXECUTED

Confirmed on the real helper:

- extras are rejected
- invalid markers are rejected
- duplicate names with different markers are rejected
- marker-only mutations preserve the same parsed inventory
- baseline inventory remains `70/70`, zero delta

### Remaining issue — bounded wording contract not fully closed

The required strongest permitted claim was:

> `requirements.txt and Poetry's main-group lock inventory have identical canonical package names and exact versions.`

The candidate does include that exact phrase in the test module and ledger, but `docs/ai/CTO_CURRENT_OPS.md:178-180` still says:

- `Before any local deployment, the two backend install paths must resolve the same main-runtime packages.`

That wording is broader than the allowed exact claim because it states install-path resolution equivalence rather than only inventory name/version parity.

This is a bounded remaining evidence-overclaim within the requested closure scope.

Conclusion: `KILO-H7R3V1-002` is **not fully closed**.

## Phase 4 — `KILO-H7R3V1-003` and CTO mutation closure

### Real `check_setup_sh_wiring()` helper — EXECUTED

All required mutations turned RED for the intended reason:

- comment-only
- echo/printf
- quoted/inert
- variable assignment
- same-line if
- multiline if false
- multiline for / while / until / case / function block
- `false &&`
- `true ||`
- `pip ... || true`
- suffix / redirection
- command after unconditional exit
- missing / wrong sequence
- unbalanced blocks

The real unchanged `setup.sh` passed.

### Real `check_dockerfile_wiring()` helper — EXECUTED

All required mutations turned RED for the intended reason:

- comment-only
- `RUN echo "poetry install"`
- `RUN false && poetry install ...`
- `RUN poetry install ... || true`
- `ENV` / `LABEL` / `ARG` text carriers
- wrong order
- earlier-stage-only
- duplicate instructions
- continuation-based inert form
- non-exact `COPY` / `RUN`

The real unchanged `Dockerfile` passed.

### Source-execution claim boundary — STATIC

The test file and docs correctly describe these as source-shape guards and do not claim native execution proof.

Conclusion: `KILO-H7R3V1-003` and the two CTO-confirmed R4 false-green paths are closed.

## Phase 5 — `KILO-H7R3V1-004` closure

Confirmed in changed evidence/docs:

- GitNexus status is stated as host-specific evidence
- both Zcode-host and Kilo-host outcomes are recorded
- GitNexus status is not treated as a portable product invariant

Conclusion: `KILO-H7R3V1-004` is closed.

## Phase 6 — Test authenticity

### Structural count — EXECUTED

AST expansion of the committed test file produced exactly **92** tests.

### Runtime subset execution

Not independently rerun here. This host review was limited to bounded source/mutation closure. I did not fabricate runtime results.

### Authenticity checks — STATIC + EXECUTED

- no `skip` / `xfail` / conditional pass found in the committed test file
- closure mutations were executed against the real committed helpers, not copied logic
- the bounded lock-parser and wiring failures now fail with controlled `ValueError`

## Phase 7 — Quality

### Executed

- `git diff --check` — clean
- scoped `detect-secrets` — clean
- UTF-8 read check — clean
- mojibake scan — clean
- `npx gitnexus analyze` — succeeded in detached candidate worktree
- `npx gitnexus status` — still returned `Repository not indexed.` on this host
- `detect_changes` — not callable in this CLI; exact diff proof used instead
- final detached candidate worktree cleanliness — preserved

## Findings summary

### Closed

- `KILO-H7R3V1-001`
- `KILO-H7R3V1-003`
- `KILO-H7R3V1-004`
- CTO R4 false-green path A (`setup.sh` guard)
- CTO R4 false-green path B (`Dockerfile` guard)

### Remaining

- `KILO-H7R3V1-002` remains reproducible as a bounded evidence wording issue in `docs/ai/CTO_CURRENT_OPS.md`.

## Accounting

- P0: 0
- P1: 0
- P2: 1
- P3: 0
- INFO: 5
- NEEDS_PROOF: 0
- accounting gap = 0

## Final verdict

`STOP_AND_REPORT_CTO`

Reason: one bounded finding remains open. The candidate source/test logic closes the parser and install-path false-green paths, but `docs/ai/CTO_CURRENT_OPS.md:178-180` still makes a broader install-path resolution claim than the permitted exact inventory-parity wording.
