# DC-12R1-H7-R5-R2 — Evidence Checkpoint (NO PASS)

> **Status: `STOP_AND_REPORT_CTO_AWAITING_LUBUNTU_ZERO_RED`.** This is an
> evidence checkpoint, NOT a merge-review PASS. R5-R1 is superseded. All
> deterministic/source gates are green; the focused regression retains one
> environment-gated unresolved Hypothesis red node (see below). The inherited
> R3 full-gate evidence does NOT satisfy the current zero-red focused gate.

> Isolated branch: `zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`
> Base candidate: `0e8d5159` (H7-R5-R1)
> Root base: `origin/product-dev-recovered@a6ef3aac`

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

## Historical record (R4-R1, superseded)

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
