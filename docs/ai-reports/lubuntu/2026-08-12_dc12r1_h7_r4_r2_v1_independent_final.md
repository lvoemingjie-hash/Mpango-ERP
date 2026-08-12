# DC-12R1-H7-R4-R2-V1 — Independent Linux Installation & Runtime Final Gate

**Date:** 2026-08-12
**Verdict:** `STOP_AND_REPORT_CTO`

**Verifying agent:** Independent Linux install/runtime gate (opencode, glm-5.2) on a clean
Lubuntu host. Fresh full clone (independent object store, not a linked worktree) at the exact
candidate `0982eec8`. Host: 4 vCPU / 11 GiB RAM; Docker 29.1.3, `docker-compose` 1.29.2
(both present), Python 3.12.3, Node 22 / npm 10, git 2.43. No candidate source was modified.
No dependency/source correction was performed during verification.

---

## 0. References

| Role | Value |
|------|-------|
| Root base | `a6ef3aac0ab03615e9d70e08e504b9858baf61c5` |
| **Freeze candidate** | **`0982eec8477a5fba19a8deb162d4e7ea9d07134a`** |
| Candidate branch | `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12` |
| `origin/product-dev-recovered` | `a6ef3aac0ab03615e9d70e08e504b9858baf61c5` (unchanged) |
| Accepted review evidence | Kilo R2 STOP `ea3baf41`, comprehensive STOP `c5385565`, bounded closure `36e24fa2`; CTO final-wording closure = candidate `0982eec8` one-file diff |

---

## STOP summary (exact failure)

**Failed phase: Phase 5 — Native `setup.sh` Linux gate (mandatory install gate).**
**Command (run unmodified from repo root):** `bash backend/scripts/setup.sh`
**Decisive failing sub-step:** `backend/scripts/setup.sh:48` →
`alembic upgrade head -x tenant_schema=t_dev`
**Exit code of that sub-step:** **`2`**
**Error:** `alembic: error: unrecognized arguments: -x tenant_schema=t_dev`

**Source-vs-environment classification: SOURCE/SCRIPT defect.**
The Alembic global option `-x` must precede the subcommand
(`alembic -x tenant_schema=t_dev upgrade head`). Placed after `upgrade`,
Alembic rejects it in every version and exits 2, so **migrations never run**.
Reproduced cleanly in isolation:

```
$ alembic upgrade head -x tenant_schema=t_dev   # as written in setup.sh
alembic: error: unrecognized arguments: -x tenant_schema=t_dev   # exit 2
$ alembic -x tenant_schema=t_dev upgrade head    # corrected placement
# -x parsed OK; then fails later on DB connect (separate matter)
```

Consequence: Phase 5.9 ("Alembic reached sole head 037") is impossible via `setup.sh`.
The script also has **no `set -e`**, so it masks both the `docker-compose` failure and the
Alembic failure and would still print `✅ Setup complete!` — i.e. its exit status does not
reflect the install failure. Per the hard rule ("any source/runtime/install failure triggers
STOP_AND_REPORT_CTO") and Phase 5.10 ("do not patch around it"), verification stops here.

**Secondary blockers observed (classification noted):**
- `docker-compose up -d postgres redis` → container-name conflict: the compose file
  hardcodes `container_name: mpango_postgres` / `mpango_redis`, which already exist on this
  host as **pre-existing, unrelated containers** (`Up 2 days (healthy)`, created 2026-06-22 —
  the host owner's own Mpango stack). Per Phase 10 these were **not** removed. This is a
  source choice (hardcoded container names) compounded by host state.
- Latent wiring (not reached due to the above): host-side Alembic reads
  `backend/.env.example` → `DATABASE_URL=…@localhost:5432`, but the compose `postgres`
  service publishes **no host port** (internal `mpango_network` only), so on a clean host
  without a pre-existing published Postgres the host-side migration could not connect
  (Phase 5.10 wiring defect).

**Installation accounting (what `setup.sh` did before stopping):**
- `pip install -r backend/requirements.txt` into the activated task venv: **SUCCESS**, 68
  packages (70 specs − 2 marker-excluded on Linux/CPython 3.12), all 5 H7 governed versions
  exact (`bcrypt 4.0.1`, `cryptography 46.0.5`, `openpyxl 3.1.5`, `et-xmlfile 2.0.0`,
  `passlib 1.7.4`).
- `docker-compose up -d postgres redis`: **FAILED** (container-name conflict, above).
- `alembic upgrade head -x tenant_schema=t_dev`: **FAILED, exit 2** (source defect, above).
- `npm install` (frontend): started; the capturing process reached the 30-minute wall during
  this step. (Moot re: verdict — install already failed upstream.)

---

## Phases completed before the STOP

### Phase 1 — Proof gate: PASS
- Candidate `0982eec8` exact. Parent chain verified link-by-link:
  `0982eec8`→`7adcd54c`→`fc816820`→`6cd37e03`→`d1aa5d0a`→`a6ef3aac` (all OK).
- Root base `a6ef3aac` is an ancestor of the candidate. `origin/product-dev-recovered` ==
  `a6ef3aac`.
- **Aggregate delta `a6ef3aac..0982eec8` = exactly 5 files** (1 new ai-ledger doc,
  `backend/requirements.txt` [the H7 reconciliation target], 1 new H7 parity test, 2 modified
  docs). **R4-R2 delta = exactly 1 docs file** (`docs/ai/CTO_CURRENT_OPS.md`).
- No migration / product-source / frontend / deployment / config changes (the one grep hit was
  a false positive on the docs path `ai-ledger/product-ai/`).
- **req/lock parity:** `requirements.txt` = 70 specs; Poetry main-group lock = 70;
  duplicates = 0, missing = 0, extra = 0, version mismatch = 0.
- **Governed versions exact in both req and lock:** bcrypt 4.0.1, cryptography 46.0.5,
  openpyxl 3.1.5, et-xmlfile 2.0.0, passlib 1.7.4.

### Phase 2 — H7 source/test gate: PASS
- Fresh Poetry/lock venv (`poetry install --no-root`, exit 0); runtime `bcrypt == 4.0.1`.
- **Exactly 92 H7 tests collected** (`tests/test_dc12r1_h7_bcrypt_manifest_parity.py`).
- Natural order: **92 passed**, 0 skip / 0 xfail. Reverse order (nodeid-reversed, plugin-free):
  **92 passed**, 0 skip / 0 xfail. Zero conditional passes.
- Bounded parser + source-shape mutation matrix included and green
  (`TestH7R4RequirementsParserFailClosed` 10, `TestH7R4LockParserFailClosed` 19,
  `TestH7R4InventoryFailClosed` 5, `TestH7R4InstallPathWiring` 29).
- Real `setup.sh` & `Dockerfile` source-shape guards pass explicitly
  (`test_setup_sh_passes_structural_guard`, `test_dockerfile_passes_structural_guard` PASSED).
  (These are *static source-shape* guards; they do not execute `setup.sh` — which is exactly
  what Phase 5 does and where the defect surfaces.)
- Per-class node accounting: InventoryParity 19, InstallPathWiring 29, InstalledRuntime 10,
  RequirementsParserFailClosed 10, LockParserFailClosed 19, InventoryFailClosed 5 = **92**.

### Phase 3 — Fresh pip requirements environment: PASS
- Separate empty task venv; `python -m pip install -r backend/requirements.txt` → **exit 0**;
  full freeze recorded (68 packages).
- Marker accounting: 70 specs → **68 applicable on Linux/CPython 3.12**, 2 correctly
  marker-excluded (`async-timeout` `python_full_version < "3.11.3"`; `colorama`
  Windows-only). missing = 0, extra = 0, exact-version mismatch = 0.
- 5 H7 versions verified via `importlib.metadata` (all exact).
- Runtime proofs all PASS: passlib bcrypt hash/verify; `core.security`
  hash_password/verify_password; 200-character password behavior; openpyxl workbook save/load;
  `et_xmlfile` import; `cryptography` 46.0.5 import/version; **FastAPI app import OK, 203
  routes**. No package manually installed after the requirements install.

### Phase 4 — Fresh Poetry environment: PASS
- Second independent empty Poetry venv; `poetry install --no-root` (pyproject+lock) →
  **exit 0**; freeze recorded (115 packages = main + dev/test + bootstrap).
- All Phase-3 runtime proofs repeated in the Poetry venv: **7/7 PASS** (incl. FastAPI 203 routes).
- Honest inventory comparison pip vs Poetry: 68 name-common packages with **0 version
  mismatch**; 0 only-in-pip; 47 only-in-Poetry (dev/test/bootstrap extras, e.g. black, ruff,
  mypy, pytest, hypothesis, locust, flask). Markers/lock-hashes/sources explicitly **not**
  claimed equivalent. **All 5 H7 packages match exactly across both environments.**

### Phase 5 — Native `setup.sh` Linux gate: **FAIL (SOURCE DEFECT) → STOP** (see summary above)

### Phases 6–8: not executed
Per the hard rule, verification stops at the Phase 5 source/install failure. Native Docker
build (6), focused runtime regression (7), and the two full backend gates (8) were not run —
the mandatory native-install gate already fails, so the overall verdict cannot be PASS
regardless of their outcome.

### Phase 9 — Quality & evidence (candidate delta; partial, for context)
- `py_compile` of the new H7 test: OK. `git diff --check a6ef3aac..0982eec8`: clean.
- `detect-secrets` over the 5 delta files: **0 findings**. UTF-8/mojibake: all 5 valid, no BOM,
  no U+FFFD.
- The candidate's own H7 parity suite (Phase 2) already enforces the manifest reconciliation
  invariant; the defect is confined to the **`setup.sh` install path** (line 48 Alembic
  invocation), not the reconciled manifests or the H7 tests.

### Phase 10 — Cleanup
Task-owned resources removed: the disposable `repo-setup` clone, all task venvs
(pip-env, setup-env, the two Poetry venvs), the `h7setup_*` compose network/volumes, the
generated `backend/.env` / `frontend/.env`, partial `node_modules`, logs and artifacts.
**Pre-existing unrelated host containers `mpango_postgres` / `mpango_redis` (the host owner's
own stack) were intentionally left in place.** Protected refs unchanged (candidate, kilo,
main, product-dev-recovered object names identical before/after).

---

## Verdict

`STOP_AND_REPORT_CTO`

- **Failed phase:** Phase 5 (Native `setup.sh` Linux gate) — mandatory install gate.
- **Command:** `bash backend/scripts/setup.sh` (run unmodified from repo root).
- **Decisive failing step / exit code:** `backend/scripts/setup.sh:48`
  `alembic upgrade head -x tenant_schema=t_dev` → **exit 2**
  ("unrecognized arguments: -x tenant_schema=t_dev").
- **Classification:** **SOURCE/SCRIPT defect** (Alembic `-x` option misplaced after the
  subcommand; migrations never run). Secondary: hardcoded compose `container_name` collides
  with pre-existing host containers; latent host-side-Alembic port wiring absent.
- **Recommended CTO remediation (for the CTO to authorize — not performed here):** move `-x`
  before the subcommand in `setup.sh` (`alembic -x tenant_schema=t_dev upgrade head`); add
  `set -euo pipefail` so install/migration failures fail the script; reconcile host-side
  Alembic reachability with the compose Postgres port wiring (or run Alembic inside the
  backend container); avoid hardcoded `container_name` collisions for disposable installs.

Phases 1–4 PASS; Phase 5 FAILS on a source defect; the gate therefore cannot PASS.
