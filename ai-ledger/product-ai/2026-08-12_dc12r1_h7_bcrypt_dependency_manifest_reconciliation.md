# DC-12R1-H7-R3 — Fail-Closed Parsers + Full Main-Runtime Parity Closure

> Isolated branch: `zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`
> Base candidate: `d1aa5d0a778e919587bd9e25e485e90a9c3cf5a1` (H7-R2)
> Root base: `origin/product-dev-recovered@a6ef3aac...` (accepted R0-R1 readiness-debt merge)
> Objective: close the three Kilo findings on H7-R2 by pinning the one remaining
> main-runtime transitive (`et-xmlfile`) and making the manifest test's parsers
> fail-closed — reaching exact normalized name/version parity between
> `requirements.txt` and Poetry's main-runtime lock set.

> **H7-R2 verdict is `SUPERSEDED_BY_H7_R3`.** Kilo review of R2
> (`reports/dc12r1-h7-r2-v1-kilo-review-2026-08-12`, commit `ea3baf41`) returned
> STOP with three findings, all closed here.

## 0 Verdict Summary

| Dimension | Result |
|---|---|
| Base / resume | ✅ HEAD `d1aa5d0a`; tree clean; local==remote; protected tip unchanged at `a6ef3aac` |
| Scope discipline | ✅ 5 files (all allowed); `pyproject.toml`+`poetry.lock` byte-identical; only `et-xmlfile==2.0.0` added |
| Preflight gate | ✅ complete Poetry main-runtime lock map (70) vs requirements (69): **only et-xmlfile==2.0.0 missing**; 0 extra, 0 mismatch, 0 dup names |
| KILO-H7R2V1-001 (req parser dup overwrite) | ✅ closed — strict `Requirement`-based parser, rejects duplicate/collision/malformed/URL/wildcard/non-exact |
| KILO-H7R2V1-002 (lock parser dup overwrite) | ✅ closed — validates every entry, rejects duplicate names |
| KILO-H7R2V1-003 (parity overclaim / et-xmlfile) | ✅ closed — `et-xmlfile==2.0.0` pinned; full-map equality now holds |
| Manifest/parser suite | ✅ 44 tests, natural **and** reverse order (authentic RED mutations use the real helpers) |
| Full main-runtime parity | ✅ requirements.txt == Poetry main-runtime lock: identical normalized names + exact versions (70==70) |
| Two fresh envs | ✅ pip-path PASS + Poetry-path PASS (bcrypt 4.0.1, cryptography 46.0.5, openpyxl 3.1.5, et-xmlfile 2.0.0, passlib 1.7.4; hash/verify, long-pw, workbook+et_xmlfile, cryptography, FastAPI import) |
| Focused regression | ✅ password/auth/onboarding/provisioning + manifest suite: 247 passed, 0 failed |
| Backend full gate (two stacks) | ⏳ recorded in §9 |
| Docker (Poetry/lock path) | ✅ inherited from R2 (Dockerfile/pyproject/lock byte-identical) — labeled inherited, not an R3 rerun |
| Static / integrity | ✅ py_compile; git diff --check; scoped pre-commit + detect-secrets; mojibake; GitNexus analyze/status |
| Evidence truth | ✅ parity claim narrowed to exact name/version; lock hashes and pip marker behavior NOT claimed equivalent; native setup.sh still Linux-only (Lubuntu) |
| Verdict | **PASS_FOR_CTO_DC12R1_H7_R3_MERGE_REVIEW** |

---

## 1 Kilo findings on H7-R2 (closed by R3)

From `reports/dc12r1-h7-r2-v1-kilo-review-2026-08-12/2026-08-12_dc12r1_h7_r2_v1_kilo_findings.csv`
(commit `ea3baf416326be91995b953f8545ae28f14b590a`):

- **KILO-H7R2V1-001 (P2)** — requirements parser false-green duplicate overwrite:
  `_parse_requirements()` stored by normalized name with no duplicate detection, so
  a conflicting duplicate governed line (e.g. `bcrypt==5.0.0` then `bcrypt==4.0.1`)
  was masked by last-wins overwrite.
- **KILO-H7R2V1-002 (P2)** — lock parser false-green duplicate overwrite:
  `_parse_lock()` used a dict comprehension that silently overwrote duplicate lock
  package entries.
- **KILO-H7R2V1-003 (P3)** — evidence overclaim: `openpyxl 3.1.5` depends on
  `et-xmlfile` (locked at `2.0.0`) but `requirements.txt` had no `et-xmlfile` pin,
  yet the ledger described the two install paths as resolving identical runtime
  versions — stronger than the committed source could prove for the transitive pip
  path.
- INFO findings (positive controls) confirmed SHA/lineage, the authorized 3-file
  requirements delta, direct-main-dependency parity, and install-path wiring. One
  INFO note: on the Kilo host, detached-worktree `gitnexus analyze` succeeded while
  `gitnexus status` still reported "not indexed", so the R2 "up-to-date status"
  narration was not reproduced there (host-specific GitNexus behavior).

## 2 Authorization and preflight

The CTO authorized exactly one additional `requirements.txt` pin, `et-xmlfile==2.0.0`,
**conditional on proving it is the only remaining main-runtime package-set/version
drift**. Preflight recomputed the complete Poetry lock package map whose `groups`
include `"main"` (70 packages) and compared it against every normalized
`requirements.txt` package (69):

- **Missing from requirements:** `et-xmlfile==2.0.0` (count 1) — the only delta.
- **Extra in requirements:** 0.
- **Version mismatches:** 0.
- **Duplicate normalized names (requirements or lock):** 0.

The conditional was satisfied; no other drift exists. Proceeding (no STOP).

## 3 Corrections

### A. Full runtime parity — `et-xmlfile==2.0.0`
Added in alphabetical position (between `email-validator` and `fastapi`) with the
existing marker style. The four previously governed versions are unchanged:
bcrypt `4.0.1`, cryptography `46.0.5`, openpyxl `3.1.5`, passlib `1.7.4`.
`pyproject.toml` and `poetry.lock` remain byte-identical to `a6ef3aac`. After the
edit, the full-map comparison reports **0 missing / 0 extra / 0 mismatch** (70==70).

### B. Requirements parser fail-closed (KILO-H7R2V1-001)
`parse_requirements_text()` parses every non-blank/non-comment line with
`packaging.requirements.Requirement` (no prefix regex); requires exactly one
non-wildcard `==` specifier; rejects URL requirements, non-exact/wildcard specs,
trailing garbage, and **any duplicate normalized name** (via
`packaging.utils.canonicalize_name`) — including identical duplicates, conflicting
duplicates, and `et_xmlfile` vs `et-xmlfile` collisions. Last-wins overwrite is
impossible.

### C. Lock parser fail-closed (KILO-H7R2V1-002)
`parse_main_lock_packages()` validates that every entry has a nonempty `name`,
`version` and `groups`, normalizes via `canonicalize_name`, rejects any duplicate
name before insertion (no dict-comprehension overwrite), and builds the map only
for packages whose `groups` include `"main"`.

### D. Authentic mutation tests (call the real committed helpers)
`TestH7R3RequirementsParserFailClosed`: conflicting duplicate; identical
duplicate; normalized-name collision; trailing-garbage malformed; non-exact `>=`;
wildcard `==4.0.*`; URL requirement.
`TestH7R3LockParserFailClosed`: duplicate lock entries; malformed lock package
(missing groups / version / name).
`TestH7R3ParityFailClosed`: missing main-runtime package; extra package; version
mismatch; et-xmlfile removal; et-xmlfile version mutation.
Plus the GREEN `test_requirements_equal_poetry_main_runtime_lock` proving complete
map equality. No parser logic is copied into tests; no skip/xfail/conditional pass.

## 4 Evidence truth (narrowed claims)

- After full-map equality, the supported claim is: **"requirements.txt and Poetry's
  main-runtime lock package set have identical normalized package names and exact
  versions."** This is name/version parity only.
- Poetry **lock hashes** are NOT claimed equivalent to anything in
  `requirements.txt` (requirements.txt carries no hashes).
- **pip marker behavior** is NOT claimed equivalent to Poetry marker resolution
  (requirements.txt and the lock express markers differently); only name+version are
  compared.
- **Native `setup.sh` has still not run on Linux** — it remains a mandatory Lubuntu
  independent gate (this Zcode host is Windows). The fresh pip-venv proof is the
  Zcode-side install-path evidence.

## 5 Manifest/parser suite (order-independent)

`pytest tests/test_dc12r1_h7_bcrypt_manifest_parity.py`: **44 passed** in natural
order AND in reverse order (node IDs reversed), proving no order-dependent state.

## 6 Two-venv runtime proof (both fresh install paths)

Fresh task-owned envs (Python 3.12.10) — `runtime_proof.py` reported
**RESULT: PASS** in both:

| Check | pip-path (fresh `requirements.txt`) | Poetry-path (fresh `poetry install`) |
|---|---|---|
| bcrypt / cryptography / openpyxl / et-xmlfile / passlib | 4.0.1 / 46.0.5 / 3.1.5 / 2.0.0 / 1.7.4 | identical |
| passlib bcrypt hash/verify round-trip | PASS | PASS |
| `core.security` hash/verify + 200-char truncation | PASS | PASS |
| openpyxl workbook + `et_xmlfile` import | PASS | PASS |
| cryptography import + version | PASS | PASS |
| FastAPI app import (routes) | PASS (203) | PASS (203) |

The pip install log explicitly resolves `et-xmlfile-2.0.0` (now pinned; previously
only pulled transitively).

## 7 Focused password/auth/onboarding/provisioning regression

Stack1 (`contractd_pg16:5433` / `contractd_redis7:6380`, fresh Poetry env): 16
focused files + the manifest suite → **247 passed, 0 failed** (the R2 transient
hypothesis seed flake did not recur).

## 8 Docker image (Poetry/lock path) — inherited from R2

The R3 slice does not touch `Dockerfile`, `pyproject.toml`, or `poetry.lock`
(byte-identical to R2). Per the task, the R2 Docker evidence
(`mpango-h7r2-backend:proof`, exit 0; resolves bcrypt 4.0.1 / cryptography 46.0.5 /
openpyxl 3.1.5 / passlib 1.7.4 with hash/verify + workbook PASS) is reused as
**inherited evidence**, not an R3 rerun. The lock also pins `et-xmlfile 2.0.0`, so
the image resolves it transitively.

## 9 Full backend gate (two independent PG16/Redis7 stacks)

Two independent full `pytest tests/` runs (stack1 `contractd_pg16:5433` /
`contractd_redis7:6380`; stack2 `contractd_pg16_run2:5434` /
`contractd_redis7_run2:6381`) in the canonical Poetry env (`-p no:randomly`):

| Metric | stack1 | stack2 |
|---|---:|---:|
| Passed | 3366 | 3366 |
| Skipped | 29 | 29 |
| XFailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |
| Wall time | 1294.43s | 1286.34s |

Totals are **identical** across the two independent stacks with **0 failed /
0 errors**. Total collected 3410 = R2's 3396 + 14 (the manifest suite grew
30→44). The Poetry test env is governed by the unchanged `poetry.lock`, so the
R3 `requirements.txt` edit cannot affect these results; the gate proves the
env+code (d1aa5d0 + the additive R3 test/parser changes) is green on both stacks.

Test-environment note (disclosed, not a code change): the temp-DB harness in
`tests/async_test_utils.py` requires `MPANGO_ALLOW_TEMP_DB_CREATE=1` plus
`MPANGO_TEMP_DB_ALLOWED_PORTS=<port>`; disposable DBs are `test_*` owned by the
test-safe `mpango_test` superuser on `test_mpango` at head
`037_payment_declarations_schema`.

## 10 Static / integrity gates

- `python -m py_compile tests/test_dc12r1_h7_bcrypt_manifest_parity.py`: clean.
- `git diff --check`: clean.
- scoped `pre-commit` on all 5 changed files: all Passed (incl. detect-secrets v1.5.0
  against `.secrets.baseline`).
- mojibake / UTF-8 validity scan on all 5 changed text files: clean.
- GitNexus `analyze`/`status`: repo indexed; impact on auth symbols unchanged
  (`hash_password`/`verify_password`); re-index shows only the test module changed.
- No `skip`/`xfail`/deselect/timeout-increase/assertion-weakening — additive tests only.

## 11 Changed-file proof

Exactly five files (all on the allowed list); `pyproject.toml` and `poetry.lock`
byte-identical to base:

```
 M backend/requirements.txt                                          (+et-xmlfile==2.0.0)
 M backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py            (fail-closed parsers + 44 tests)
 M docs/ai/CTO_CURRENT_OPS.md                                        (R2 superseded by R3; Kilo findings; narrowed parity)
 M docs/ai/PROJECT.md                                                (R3 supersession; name/version parity)
 M ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md  (this ledger)
```

## 12 Scope / exclusions honored

No `pyproject.toml` or `poetry.lock` change. No dependency change beyond the one
authorized `et-xmlfile==2.0.0` pin. No migration, product/auth-behavior,
deployment, Playwright, or VPS change. No skip/xfail/deselect/assertion-weakening.
No protected push or merge. No claim of native `setup.sh`, local deployment,
Playwright, or VPS validation.

## 13 After push: STOP

After the isolated H7 branch is pushed and the SHA frozen, **STOP**. Await Kilo
review, Lubuntu independent verification (including native `setup.sh` on Linux),
and CTO merge. Do not begin Playwright, local deployment, or VPS work.
