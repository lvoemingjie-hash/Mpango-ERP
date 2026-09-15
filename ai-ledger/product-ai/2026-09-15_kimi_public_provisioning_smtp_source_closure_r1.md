# Kimi R1 — public provisioning + SMTP source closure (test layering, DB identity guard, zero-connection evidence)

- DATE=2026-09-15
- AUTHORIZATION_ID=CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-R1-2026-09-15
  (successor of CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-V1-2026-09-15)
- EXECUTOR=Kimi (ZCode session), Windows host, Git Bash
- BRANCH=`kimi/public-provisioning-smtp-source-closure-2026-09-15` (same branch)
- VERIFICATION_TIER=V3_SOURCE_AND_PREPARATION
- CLAIM_CEILING=PUBLIC_PROVISIONING_AND_SMTP_SOURCE_CLOSURE_ONLY
- FORMAL_SKU_IMPORT_INVOCATIONS=0 ; MERGE=PROHIBITED ; DEPLOYMENT=PROHIBITED ;
  BROWSER_RUNTIME=PROHIBITED ; FULL_SUITE=PROHIBITED (not run)
- NEXT_GATE=`CTO_REVIEW_OF_R1_SUCCEEDOR_COMMIT` (then Kilo source review)

SHA ledger (exact):

- R0_BASE=1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e
- R0_CANDIDATE=e88fa8f7d77eaeec61193ffe236fef160bb65608 (delta commit, hooks
  bypassed with `--no-verify` — record preserved, history not rewritten)
- R0_MANIFEST=4f1f8e04fdaba309cb14ec33a461fc9f1df2ec79 (recorded the R0 SHA)
- R1_SUCCESSOR=<recorded by the R1 successor commit that introduces this
  report; exact SHA is stated in the CTO handoff message and equals
  `git rev-parse HEAD` on the branch above>
- Content digests of the R1 test files (sha256, byte-level identity binding):
  - `test_smtp_auth_mode_guard_config.py`
    `cbc326bcd1aea45c120a328d45fdaf5c906d68ff38b637b31a6a2d9ead3bc6da`
  - `test_smtp_loopback_noauth_contract.py`
    `3ba5ed188e82633ef1033f669d7cee86a331799365b17d5ebe858510e1e30f87`
- PRIOR_EVIDENCE=Kilo Revision B `4e4e07aaf68571c24ac02de9a7a86e9f86e22934`
  remains evidence-only, absent from this repository, and is **not** cited as
  proof of the public provisioning lifecycle or the runtime-mode requirement.

## 1. R1 item 1 — pure tests fully separated from database fixtures

New file `backend/tests/test_smtp_auth_mode_guard_config.py` (33 nodes) imports
only `core.config`, `services.email_delivery`, stdlib, `pytest` and `pydantic`.
It requests no database fixture, never imports `api.app`, `database.*`, or
`models.*`, and contains the auth-mode policy, loopback-detection,
config-completeness and zero-connection guard tests.

Separation proof (command in §9): the pure file runs against an **unreachable**
database URL (`postgresql://127.0.0.1:1/unreachable` -- loopback port 1, no listener, no
  credentials in the value, no
`KIMI_SMTP_TASK_DATABASE_URL`):

```
33 passed in 0.48s
```

A database touch would have failed or hung; the file is therefore proven
database-free by construction and by execution.

The database-backed file keeps only the public API / lifecycle tests that
genuinely need PostgreSQL (signup delivery, 503 matrix through the API,
verify-email → owner setup lifecycle, login-mode real-server authentication):
8 nodes.

## 2. R1 item 2 — DB tests prove task-database identity before any write

`test_smtp_loopback_noauth_contract.py` now enforces, in this order:

1. **Explicit task URL, no fallback** — `KIMI_SMTP_TASK_DATABASE_URL` must be
   set; the resolver refuses `DATABASE_URL`, test defaults, or any other
   source. The URL must be loopback-hosted and its database name must start
   with `kimi_smtp_`.
2. **Live identity proof** (module-scoped autouse fixture, a declared
   dependency of the per-test write fixture, so it always runs first):
   - engine URL host/port/database compared against the declared task URL;
   - `SELECT current_database()` through `async_engine.connect()`;
   - `SELECT current_database()` through `AsyncSessionLocal()`;
   - all three must agree and equal the task database name.
3. Only then does any write happen (table `checkfirst` creation, role
   bootstrap, or row/schema writes).

**No fallback. No prefix-based bulk deletion.** Cleanup deletes only rows for
the exact e-mail addresses created by this module's tests (exact-match
`= ANY(:emails)`), re-derives their registration/wholesaler/schema identity
from the database, drops only those schemas, and then asserts that zero rows
remain for those exact e-mails. A source scan shows no `LIKE`-based deletion
anywhere in either file (the only `LIKE` mentions are the docstrings that
promise it is not used).

Guard-negative proofs (each run against the real suite; all fail closed before
any write):

| Case | Injected configuration | Observed |
|---|---|---|
| G1 | `KIMI_SMTP_TASK_DATABASE_URL` unset | `RuntimeError: KIMI_SMTP_TASK_DATABASE_URL must be set explicitly … refuses to fall back to DATABASE_URL, test defaults, or any other database.` |
| G2 | task URL naming `mpango_test_s2` | `RuntimeError: … must name the task-owned database (prefix 'kimi_smtp_'), got 'mpango_test_s2'.` |
| G3 | task URL naming `kimi_smtp_other_20260915` while the engine points at `kimi_smtp_src_20260915` | `AssertionError: engine database 'kimi_smtp_src_20260915' != task database 'kimi_smtp_other_20260915'` |

## 3. R1 item 3 — SMTP/SMTP_SSL zero-connection assertions + RED proof

Both the pure file and the database file install tripwire spies on
`email_delivery.smtplib.SMTP` **and** `email_delivery.smtplib.SMTP_SSL`. The
tripwires record any construction attempt and raise; guard-rejection paths
assert the recorded list stays empty (zero connections), including the
implicit-TLS variant (`SMTP_USE_TLS=true` with `SMTP_AUTH_MODE=none`
off-loopback).

Covered rejection paths: unknown auth mode, `none` off-loopback,
`none` off-loopback + implicit TLS (pure, parameterised), plus the API-level
pre-transport matrix (missing host, missing login credentials, unknown mode,
`none` off-loopback) which additionally asserts the real capture sink accepts
no new TCP connection.

**Guard-removal RED proof (mutation M4/M5)** — with the send-layer guard
deleted, the zero-connection assertions fail:

- M4 (loopback guard removed) → `FAILED test_delivery_layer_guard_blocks_offloopback_noauth_before_transport`
- M5 (unknown-mode guard removed) → `FAILED test_send_layer_unknown_mode_guard_blocks_before_transport`

M5 initially **survived** on the first harness run: the config-completeness
gate shielded the API path, so the send-layer unknown-mode guard had no direct
detector. A direct test was added (this is exactly the coverage gap the
exercise was meant to find) and M5 is now detected.

## 4. R1 item 5 — evidence

### 4a. Per-node results (source/preparation evidence)

Focused regression, task venv (Python 3.12.10, pinned: bcrypt 4.0.1,
pytest 8.4.2, pytest-asyncio 0.26.0) against the task database
`kimi_smtp_src_20260915` at migration head `038_catalog_identity_vertical_slice`:

```
315 passed, 353 warnings in 670.56s (0:11:10)     # 28 files, 0 failed/skipped errors
```

Per-file node counts (verbatim from the `-v` log; 315 nodes, 0 unparsed):

| nodes | file |
|---|---|
| 33 | tests/test_smtp_auth_mode_guard_config.py (new, pure) |
| 8 | tests/test_smtp_loopback_noauth_contract.py (DB, rewritten) |
| 5 | test_u6k_production_smtp_email_delivery.py |
| 7 | test_u6l_email_verified_onboarding_orchestration.py |
| 16 / 8 / 13 / 7 | test_u6c / test_u6d / test_u6e / test_u6f |
| 11 / 7 / 10 / 14 / 8 | test_u6b / test_u6g / test_u6h1 / test_u6h2 / test_u6h3 |
| 15 / 12 / 9 / 13 / 1 | test_u6i2 / test_u6i3 / test_u6i4 / test_u6i5 / test_u6i6 |
| 3 | test_dc2h_production_smtp_compose_wiring.py |
| 14 | test_dc12a_r2_credential_email_links.py |
| 30 | test_security_s2_5.py |
| 14 / 8 / 4 / 6 | test_dc12r1_s1_retailer_identity / _r1_corrections / _r2_strict_mapping / _h1_verification_token_terminal_state |
| 12 / 11 | test_dc12r1_j1_h2b_forgot_password_runtime_closure / _j1_h2c_retailer_recovery_discovery |
| 16 | test_dc3b_credential_recovery_backend.py |

Raw `-v` logs (`per_node_focused_r1.txt`, `per_node_focused_r1_final.txt`),
the pure-file unreachable-DB run, the mutation evidence JSON and the cleanup
inspection output are retained task-locally as scratch artifacts; the tables
in this report are the committed form.

### 4b. Mutation evidence (all detected, sources restored byte-identically)

| Mutation | Target guard | Mapped detector test | Verdict | sha256 restored |
|---|---|---|---|---|
| M1 | `Settings.validate_smtp_auth_mode` condition disabled | pure `…rejected_for_non_loopback_host` | DETECTED (FAILED) | exact |
| M2 | `SMTP_AUTH_MODE` default flipped to `none` | pure `…login_remains_the_default_auth_mode` | DETECTED (collection ImportError — `core.config` fails fast at import) | exact |
| M3 | `_smtp_config_complete` loopback guard removed | pure `…config_completeness_rejects_offloopback_noauth` | DETECTED (FAILED) | exact |
| M4 | `_send_smtp_email` loopback guard removed | pure `…blocks_offloopback_noauth_before_transport` | DETECTED (FAILED) | exact |
| M5 | `_send_smtp_email` unknown-mode guard removed | pure `…unknown_mode_guard_blocks_before_transport` | DETECTED (FAILED) | exact |

Restore discipline: the harness snapshots each source file in memory, records
`sha256` before mutation, restores from memory afterwards, and re-hashes; every
restoration compared equal (`restored_exact=true` in the JSON evidence).
`git status` after the harness shows only the intended test-file changes.

M2's RED is a collection-time failure by design: with the default flipped to
`none`, `core.config`'s module-level `Settings()` instantiation raises in the
validator, so the suite cannot even load. That is the strongest possible
fail-fast signal and is reported as such, not as a per-node assertion failure.

### 4c. Scan evidence

- `detect-secrets` pre-commit hook (v1.5.0, repo `.secrets.baseline`) on the
  R1 files: **exit 0, no findings**, `.secrets.baseline` unmodified. One
  placeholder URL that carried a literal user:password pair was introduced during
  drafting was removed in favour of a credential-free value rather than
  allowlisted.
- Forbidden-pattern scan on both files: no `LIKE`-based deletion, no
  `DATABASE_URL` fallback in the database suite, no database imports in the
  pure suite.
- The R0-era findings (three pre-existing false positives in
  `backend/.env.example:19,23` and `backend/core/config.py`'s dev
  `DATABASE_URL` default) are untouched by R1: those files are not modified in
  this round and the hook passes on the R1 file set.

### 4d. Cleanup evidence

In-suite: teardown deletes only the exact recorded e-mails' rows (tokens →
registrations → wholesalers) and drops only their schemas, then asserts
`SELECT count(*) … WHERE owner_email = ANY(:emails) = 0`.

Post-run inspection of the task database (read-only; prefix matching used
**only** for inspection, never for deletion):

| Quantity | Value |
|---|---|
| registrations matching `kimi\_smtp\_%` | **0** |
| total registrations / token rows for those registrations | **0 / 0** |
| provisioning-shaped tenant schemas (22-table) | **0** |
| `t_<32hex>` schemas present | 102 (100 × 5 RBAC tables, 2 × 1 table) |
| of those, linked to any registration | 0 (all orphaned) |
| wholesaler rows without registration | 2 |

Attribution of the 102 orphan schemas: their table signature is exactly
`users, roles, permissions, user_roles, role_permissions` (5 tables), which is
the RBAC fixture pattern of **other pre-existing suites**, e.g.
`tests/test_dc12r1_s1_r2_strict_mapping.py:42-62` (`t_{ws_id.hex}` +
those five tables). The SMTP files create **22-table provisioning schemas**;
zero of those remain. The orphans are therefore environment residue from other
suites' fixtures (and from a regression run that was deliberately terminated
mid-flight at 99 % during this round, which by construction cannot run its
teardown), not from the SMTP contract tests. They were **not** mass-deleted:
a prefix-wide delete is exactly the pattern this round forbids, and the orphan
producing suites are outside this authorization's scope. They are registered
here as residual risk with a proposed mitigation (per-run residue ledger).

The focused regression passed **with** those orphans present, which is
independent evidence that the SMTP tests neither depend on nor damage
pre-existing schema state.

### 4e. Typecheck

`mypy core/config.py services/email_delivery.py`: 3 errors, byte-identical to
the base candidate (same three pre-existing errors, lines shifted by the R0
insertions). **Net-new type errors: 0.** Source files are unchanged by R1.

## 5. R1 item 4 — commit hygiene

- R0's `--no-verify` bypass is **preserved as history**; no amend, rebase or
  force was used, and the R0 report records the bypass and its justification
  (three findings proven present in the pristine base blobs).
- The R1 successor commit is created **with the normal pre-commit hooks
  enabled** — no `--no-verify`. The R1 file set (two test files + this report)
  passes `detect-secrets`, trailing-whitespace, end-of-file and
  large-file hooks.

## 6. Evidence classification (required distinction)

| Evidence | Class | Notes |
|---|---|---|
| 315-node focused regression, per-node log | SOURCE_PREPARATION | Real modules, real socket sinks, real PostgreSQL in a task-owned loopback database; executed on the Windows authoring host |
| Pure-file run with unreachable DB URL | SOURCE_PREPARATION | Proves DB-free test layering |
| Task-DB identity guard + G1/G2/G3 negatives | SOURCE_PREPARATION | Proves the guard fails closed |
| Mutation/restore-SHA evidence | SOURCE_PREPARATION | Guards are behaviorally covered |
| detect-secrets / pattern scans / mypy | SOURCE_PREPARATION | Static checks |
| Cleanup inspection | SOURCE_PREPARATION | Read-only post-run observation |
| Official public API + SMTP lifecycle on a fresh independent VPS root, Redis DB 15, exact server-side `JwtAuthStrategy` proof | **LIVE_RUNTIME — NOT PERFORMED, NOT CLAIMED** | Must be executed by the later independent V4 task after source review |

Nothing in this report demonstrates SKU delivery acceptance, and the formal SKU
import command was not invoked.

## 7. Residual risks

1. **Crashed-run residue**: a terminated process cannot run teardown, and the
   suite deliberately refuses prefix deletion. Mitigation proposal for a later
   round: an append-only per-run residue ledger (exact ids/schema names) that a
   subsequent run can consume for exact-identity cleanup. Not implemented here
   to keep the R1 delta within scope.
2. **Foreign-suite residue** (102 RBAC-shaped schemas, 2 wholesalers) stays in
   the task database; it is documented and attributable, not cleaned, because
   both a prefix delete and edits to other suites are outside this
   authorization.
3. `SMTP_USE_TLS` (implicit TLS) still has no real TLS sink end-to-end test;
   the tripwire covers its guard-rejection path only.
4. Zero-connection assertions protect the guard paths, not the transport
   itself: a future refactor that moves mode resolution out of
   `_smtp_auth_mode` would need the guard tests updated (M4/M5 pin the current
   structure).
5. The send-layer guards are reachable only through loosely constructed
   settings objects in tests; the API path is shielded by the
   config-completeness gate first. Both layers are covered, but this ordering
   must be preserved deliberately.

## 8. Stop point

STOP for CTO review of the R1 successor commit, then Kilo bounded source
review (`KILO_BOUNDED_SOURCE_REVIEW_PUBLIC_PROVISIONING_SMTP`). The later
independent V4 execution (new root, label-proven resources, Redis DB 15,
exact server-side `JwtAuthStrategy` proof, official public API + SMTP
lifecycle) remains outstanding and is **not** performed by Kimi. No formal SKU
invocation, no merge, no deployment, no history rewrite.

## 9. Commands (reproducible)

```bash
# pure file — no database needed (unreachable URL proves the separation)
TEST_DATABASE_URL=postgresql://127.0.0.1:1/unreachable \
  python -m pytest tests/test_smtp_auth_mode_guard_config.py -q      # 33 passed

# database file — explicit task URL required, no fallback
TEST_DATABASE_URL=postgresql://127.0.0.1:5432/kimi_smtp_src_20260915  # credentials from env \
KIMI_SMTP_TASK_DATABASE_URL=<same URL> \
  python -m pytest tests/test_smtp_loopback_noauth_contract.py -q    # 8 passed

# guard negatives G1/G2/G3: unset the env var / point it at a foreign database
#   -> RuntimeError / RuntimeError / AssertionError (see §2)

# focused regression with per-node evidence
python -m pytest -v <28 files> > per_node_focused_r1_final.txt        # 315 passed

# mutation + restore-SHA evidence
python mutation_harness_r1.py                                          # all DETECTED

# scans
python -m detect_secrets.pre_commit_hook --baseline .secrets.baseline <files>
python -m mypy core/config.py services/email_delivery.py               # 3 pre-existing

# cleanup inspection (read-only)
python cleanup_evidence.py
```
