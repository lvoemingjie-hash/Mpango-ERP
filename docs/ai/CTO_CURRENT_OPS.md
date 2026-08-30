# CTO Current Ops

**Last updated:** 2026-08-30
**Owner:** Codex acting as CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Current reviewed product-code baseline:** `d9dc2e4130ea87a57d433dfadeb2f2736576fac6` (the accepted DC-12R1-MVP-L1-HE2-ET1-R3-A1-M1 controlled governance merge; before new controlled work, fetch the live protected tip, require this baseline to be its ancestor, then freeze that live tip)
**HE2 R3+A1 status: MERGED_AND_INDEPENDENTLY_RUNTIME_VERIFIED** - controlled merge `d9dc2e41` has parents `cdb39e96` and `483b8ab0`; its tree is identical to source `483b8ab0`. Accepted evidence: Kilo cumulative governance review `db87f0d3`, Lubuntu fresh-runtime authority-profile final `6fb1e31e`, and merge report `1017be0c`. The authority runner now binds backend CWD/temp-DB inputs and profile-authorized Alembic head/parent lineage; it does not merge migration `038` or any SKU product code.
**H2-B status: MERGED_AND_BROWSER_VERIFIED** - controlled merge `436d61e2` has parents `6e9470a1` and `25626f4d`; its tree is identical to the reviewed source `25626f4d`. Accepted evidence: source `25626f4d`, Kilo review `d6289a6b`, backend authority `90f96e3f` (3773 collected / 3710 passed / 48 skipped / 15 xfailed / zero red), browser E1 `04134016` (24/24 browser PASS, 29-node inventory gap=0), and merge report `c400b7c5`.
**Accepted J1-H2-A-R2 merge:** `6e9470a1daa5d6eece29724316fdd8aef6b737c1` - parents `c5b66d26` and `bf574cf9`; it is now an ancestor of the current tip, not the tip itself.
**Accepted R4-C1-R1 merge:** `a29f8db02365737c64d0d8d442e8ef48a8a19d6d` - parents `9067e38f` and `f51c109`; merge tree identical to the independently reviewed source; fresh-runtime browser matrix `162/162`; now an ancestor, not the current tip.
**Accepted H7 merge:** `ea9908263d57737e434d7d61e06e5f0ee941aa81` - parents `a6ef3aac` and `a0a14e4d`; merge tree identical to the independently reviewed source.
**Accepted readiness-debt merge:** `a6ef3aac0ab03615e9d70e08e504b9858baf61c5` - DC-12R1-MVP-R0-R1 P2/P3 readiness-debt closure and direct parent of the H7 source lineage; it is now an ancestor, not the current tip.
**Accepted product code merge:** `adcc7f281c661897ad050a8278686375b611edb5` (accepted Contract D merge; an ancestor of the current tip, NOT the tip itself)
**Current migration head:** `037_payment_declarations_schema` (the merged authority profile can authorize a future exact successor `038_catalog_identity_vertical_slice` with parent `037`; that migration is not in the baseline)
**Delivery state:** Pre-pilot MVP hardening; not approved for customer delivery

This is the short operating picture for Mpango agents. Read
`docs/ai/PROJECT.md` for the full status and roadmap. Detailed evidence belongs
in `ai-ledger/`.

## Current Truth

- `d9dc2e41` is the current reviewed baseline. It carries accepted
  Contracts A-D, H7 setup/dependency reconciliation, PW1 auth/rate-limit/cache/
  permission closures, the R4-C1-R1 responsive MainLayout closure, the J1
  friction-audit merge lineage, the J1-H2-A-R2 credential closure, and the
  H2-B password-recovery/test-hygiene closure, plus the merged HE2 authority
  controls through R3+A1. New controlled work must fetch and verify the live
  protected tip exactly; do not silently branch from an older ancestor.
- The earlier merges `6e9470a1`, `c5b66d26`, `a29f8db0`, `9067e38f`,
  `ea990826`, `a6ef3aac`, `d796dcb0`, and `adcc7f28` are ANCESTORS of the
  current tip, not the tip itself. Do not branch from or reference them as the
  current baseline.
- `origin/main@134ea59e` and `origin/platform-dev@12c5ee55` remain unchanged.
- All controlled work begins from a fetched, clean, isolated worktree.
- The wholesaler is the primary customer and value owner.
- Retailers operate inside one selected supplier relationship at a time.
- Mpango is not a cross-supplier price-comparison marketplace.
- Retailer finance reads are relationship-scoped. Retailers may submit
  non-authoritative declarations, but only supplier cashier confirmation can
  invoke the canonical financial write path.
- Merged code is not considered deployed without exact-SHA runtime proof.

## What Is Closed

- Tenant isolation and contextual JWT-derived supplier scope.
- Wholesaler credential setup/reset and terminal-token boundaries.
- Retailer identity, invitation, verified email, credentials, mapping, and
  `retailer_operator` foundation through migration `036`.
- Supplier-scoped retailer login with no `available_tenants`.
- Structured HTTP error and rate-limit 429 boundaries.
- Retailer catalog/order ownership hardening and exact client route contracts.
- Read-only retailer payment history:
  `GET /api/v1/client/payments`.
- Server-authoritative relationship balance:
  `GET /api/v1/client/finance/balance`.
- Retailer payment and finance reads use both authoritative supplier and
  retailer identities.
- No retailer route currently settles payments, writes ledger entries, or
  changes receivables.
- I1 financial schema foundation is merged at `9528cb6d`.
- H4 post-merge test-contract forensics closed at `45899145`: event-loop pool
  isolation regression suite added, migration-preflight contract pinned to
  `036`, evidence ledger corrected.
- I2A canonical payment transaction service extraction is merged at
  `b03a3b5c`, including the fail-closed positive finite amount boundary.
- I2B payment declaration and cashier confirmation runtime is merged at
  `753048f0`, including idempotent declaration submission, confirmation/
  rejection, atomic canonical payment, receipt allocation, and relationship-
  scoped status visibility.
- I2C-I1 Contracts A-C are merged at `e923fd85`: six read-only order,
  declaration, and receipt print-data routes. Receipt eligibility is
  fail-closed; no print request mutates financial state.
- I2C-I2 browser-printable Contracts A-C are merged at `0dc24511`: retailer
  and supplier order, declaration, and eligible receipt views are available;
  money display is string-safe and print actions remain read-only.
- I2C-I2B Contract D is merged at `adcc7f28`: retailer and supplier
  relationship statements use immutable receivable ledger movements, keep
  movement/payment lists independent, and remain read-only.
- H2-B (merged at `436d61e2`, MERGED_AND_BROWSER_VERIFIED) closes:
  - the wholesaler forgot/reset password chain end to end;
  - the anonymous reset 401 path no longer wrongly redirects to login;
  - multi-replica password-reset token atomicity;
  - the user role assignment `MissingGreenlet` async serialization defect;
  - the corresponding test-residue and temporary-database teardown/stability
    fixes behind the authoritative zero-red and browser evidence.
- HE2 R3+A1 (merged at `d9dc2e41`) closes the authority-runner gaps that
  previously allowed an invalid backend CWD/temp-DB environment to reach test
  execution and that hard-coded Alembic head `037`. Authority is now bound to
  protected profile bytes, exact head/declared-parent lineage, runner/child
  cross-checks, and fail-closed drift detection. It authorizes validation of a
  future exact `038 -> 037` SKU migration; it does not add that migration.

## Latest Accepted Evidence

HE2 R3+A1 controlled governance merge and independent authority verification:

`origin/product-dev-recovered@d9dc2e41` is the current reviewed baseline.

- Approved source: `483b8ab0`; merge tree equals the reviewed source tree.
- Kilo cumulative governance review: `db87f0d3` - independently executed
  186/186 governance tests and 102 RED / 9 GREEN mutation controls.
- Lubuntu authority-profile final: `6fb1e31e` - fresh PostgreSQL 16 + Redis 7,
  core chain 8/8, Redis cases 7/7, authority command exactly once on GREEN,
  and 17/17 negative controls VOID with zero command launches.
- Controlled merge report: `1017be0c`.
- Structural validator is green; release remains blocked only by the existing
  `DEBT-AUTH-CRITICAL-TUPLES` and `DEBT-COMMERCE-CRITICAL-TUPLES` debts.
- This is governance/runtime-authority evidence, not product migration `038`,
  SKU-M1, deployment, release, or customer-readiness evidence.

H2-B password-recovery controlled merge and independent verification:

`origin/product-dev-recovered@436d61e2` is the current reviewed product-code
baseline.

- Approved source: `25626f4d`; merge tree equals the reviewed source tree.
- Kilo source review: `d6289a6b`.
- Authoritative backend evidence: `90f96e3f` - 3773 collected, 3710 passed,
  48 skipped, 15 xfailed, zero red (failures/errors/xpassed all zero).
- Authoritative browser evidence (E1): `04134016` - 24/24 browser nodes PASS
  with the 29-node inventory reconciliation gap=0 (24 browser + 5 non-browser).
- Controlled merge report: `c400b7c5`.
- Retained known debt for this lineage: full-suite post-state 4/0/29
  test-hygiene residue (externally attributed; module net contribution zero);
  `RT0` remains `BLOCKED_BY_H2_C`; `REMOTE_ENFORCEMENT_NOT_VERIFIED`; no
  deployment, VPS, or real-device acceptance is claimed.

R4-C1-R1 responsive MainLayout controlled merge and browser verification:

`origin/product-dev-recovered` includes `a29f8db0` as an ancestor; at that
time it was the reviewed product-code baseline.

- Approved source: `f51c109`; merge tree equals the reviewed source tree.
- Kilo source review: `5cff172a`.
- OpenCode fresh-runtime browser evidence: `0e1c7ed8`.
- Kilo final evidence review: `b0b1ff4f`.
- Controlled merge report: `046fe7de`.
- Pre-gates: Auth `27/27`, mobile drawer `25/25`, stability `10/10`, and
  Playwright list `162` nodes in seven files.
- Authoritative browser run: `162 passed`, zero failures/skips/errors, one
  worker, zero retries, accounting gap zero.
- Merge-time frontend gates: R4-C1 `11/11` in both orders, focused `111/111`,
  full frontend `339/339`, and production build exit 0.
- This closes automated local responsive/browser verification. Human business
  acceptance, real-mailbox delivery, VPS, HTTPS, and customer release remain
  unclaimed.

I2C-I2B Contract D controlled merge and independent verification:

`origin/product-dev-recovered` includes `adcc7f28` as an ancestor.

- Approved source: `133ca46b`; merge tree equals the reviewed source tree.
- Kilo final source/test-authenticity review: `a56078c6`.
- Lubuntu independent runtime report: `b652b683`.
- Two independent full-backend runs each reported `3285 passed`, `48 skipped`,
  `15 xfailed`, zero failures, and zero errors.
- Full frontend suite: `270 passed`; production build succeeded.
- Post-merge compile, generator/CSV, frontend, build, pre-commit,
  detect-secrets, diff, and GitNexus gates passed.

I2C-I2 controlled merge and independent verification:

`origin/product-dev-recovered` includes `0dc24511`

- Approved source: `10c9158d`; merge tree equals the reviewed source tree.
- Kilo final source/test-authenticity closure: `d1e5f518`.
- Lubuntu independent runtime report: `12460e0c`.
- Focused printable-workspace suite: `63 passed` across repeated runs.
- Full frontend suite: `223 passed`; production build succeeded.
- Eight adversarial mutations went RED and were restored byte-identically.
- Post-merge scoped pre-commit, detect-secrets, diff, mojibake, build, and
  GitNexus gates passed.

I2C-I1 controlled merge and independent verification:

`origin/product-dev-recovered` includes `e923fd85`

- Approved implementation tree: `4c322c2a`; merge tree equals the reviewed
  source tree.
- Lubuntu full-clone backend Run A: `3216 passed`, `48 skipped`, `15 xfailed`,
  zero failures and zero errors.
- Lubuntu full-clone backend Run B: identical totals.
- I2C-I1 printable-record suite: `36 passed`; reversed focused order:
  `44 passed`.
- The validation environment used disposable PostgreSQL 16 and Redis 7. It is
  runtime evidence for the merged source, not a customer deployment claim.

I2B-R5-R1 controlled merge:

`origin/product-dev-recovered` includes `753048f0`

- Approved source: `c65c87cb`; merge tree equals source tree.
- Independent backend Run A: `3180 passed`, `48 skipped`, `15 xfailed`, zero
  failures and zero errors.
- Independent backend Run B: identical totals.
- I2A/I2B/H5 bundle: `64 passed` in both orders.
- Post-merge lifecycle regressions: `30 passed`.
- Frontend: `160 passed`; production build succeeded.
- Alembic sole head: `037_payment_declarations_schema`.
- Lubuntu independent runtime report: `34220d0f`.
- OpenCode independent source review: five INFO findings, zero blockers,
  accounting gap zero, report `df25e67b`.

Earlier accepted evidence:

S3-S2 source candidate:

`kilo/dc12r1-s3-s2-read-only-retailer-finance-2026-07-30@b56ae841`

Source validation:

- Backend Run A: `3030 passed`, `48 skipped`, `15 xfailed`, zero red.
- Backend Run B: `3030 passed`, `48 skipped`, `15 xfailed`, zero red.
- Frontend: 16 files and 148 tests passed; production build passed.

Controlled merge:

`0f9d259b4a6c20584721c53b59ba94c510d1970d`

S2B-I1 source candidate:

`codex/dc12r1-s3-s2b-i1-financial-schema-foundation-2026-08-01@9528cb6d`

Controlled merge:

`9528cb6de5f668ed09feb7a1eaa9aafaa537987d`

Post-merge validation:

- Fresh PostgreSQL 16 and Redis 7.
- Alembic sole head `036_retailer_mvp_identity`.
- S3-S1/S3-S2 backend bundle: `50 passed`.
- Focused frontend bundle: `6 passed`.
- Production frontend build, scoped pre-commit, and secret detection passed.

## What Is Not Closed

- Full-suite post-state test-hygiene debt stands at 4 wholesalers /
  0 registrations / 29 uuid-named schemas (4/0/29): attributed to other test
  files that run after the closed module; the module's net contribution is
  zero and replaying it on a dirty database restores 0/0/0. It remains
  unfixed and is now a pre-delivery evidence blocker under `CQ-TEST-001`.
- `RT0` remains `BLOCKED_BY_H2_C` (retailer discovery layer missing); no API
  bypass of the missing retailer UI is permitted.
- H2-C integration candidate `42c5d328` is not merged. Its Lubuntu run was
  corrected by `31adf492` to `VOID_ENVIRONMENT_PRECHECK`; browser execution
  was NOT_RUN. It requires a new baseline integration and valid authority run.
- SKU-R0-M1 is an authorized parallel V3 work line on baseline `d9dc2e41`, but
  it currently has no frozen candidate. Migration `038`, three-layer catalog
  product code, full-suite evidence, browser evidence, and independent final
  review all remain unaccepted.
- `REMOTE_ENFORCEMENT_NOT_VERIFIED`: remote/server-side enforcement has not
  been verified. `CQ-CI-001` requires the actual integration/PR path to run
  product and read-only security gates before final MVP delivery.
- The 2026-08-30 source-quality review recorded pre-delivery blockers for
  dual order-lifecycle authority (`CQ-ORD-001`), stable order-line identity
  (`CQ-SKU-001`), real-branch CI (`CQ-CI-001`), test residue
  (`CQ-TEST-001`), duplicate `jsdom` declarations (`CQ-DEP-001`), and the
  existing HE2 release debts (`CQ-HE2-001`). Canonical register:
  `docs/planning/2026-08-30_mvp_code_quality_debt_register.md`.
- Nothing is deployed: no VPS deployment and no real-device acceptance have
  been performed on the current baseline. No customer-ready or
  release-approved claim is made.
- Human real-business-journey acceptance and adoption-friction prioritization
  remain; responsive wholesaler navigation itself is merged and browser-green.
- Retailer/relationship branding and residual workspace polish remain.
- Transactional outbox/event emission and SMS/WhatsApp delivery are deferred
  outside the current MVP and remain unimplemented.
- Real-mailbox and real-browser end-to-end proof on the latest deployed SHA
  remains.
- Non-mainland customer HTTPS hosting, formal DB-OPS, platform operator runtime,
  tenant branding, and user manuals remain.

## Completed Deployment Prerequisite - H7 Manifest Reconciliation

Before any local deployment, requirements.txt and Poetry's main-group lock
inventory must have identical canonical package names and exact versions. This
is a committed inventory comparison only; it does not prove that pip and Poetry
produce identical installed environments. H7 closes that drift. This is
name/version parity only: Poetry lock hashes and sources are not compared;
markers are not compared; extras are rejected in requirements.txt; resolver
behavior is not compared. It is a **completed pre-deployment prerequisite**, not
a deployed capability. Native `setup.sh` ran twice successfully on Lubuntu, but
no local application deployment, Playwright acceptance, VPS validation, or
customer delivery is claimed here.

**Original three-package drift (RED, pre-H7-R2):** `backend/requirements.txt`
(the `scripts/setup.sh` pip path) diverged from `pyproject.toml` +
`poetry.lock` (the Dockerfile Poetry path) on three direct runtime dependencies:

| Package | `pyproject.toml` | `poetry.lock` | `requirements.txt` (pre) | Impact |
|---|---|---|---|---|
| bcrypt | `>=4.0,<4.1` | `4.0.1` | `5.0.0` | breaks passlib 1.7.4 password hashing |
| cryptography | `>=46.0.5` (S8-SEC, CVE-2026-26007) | `46.0.5` | `46.0.4` | below the security floor |
| openpyxl | `3.1.5` | `3.1.5` | *(absent)* | `ModuleNotFoundError` on the pip path |

**Why H7-R1 correctly stopped:** H7-R1 was scoped to bcrypt only. Its exhaustive
manifest audit found bcrypt was **not** the only material drift — cryptography
(violating the `>=46.0.5` security floor) and openpyxl (a missing direct
dependency) also diverged. Per its step-5 guardrail ("if bcrypt is not the only
material drift, STOP"), H7-R1 returned `STOP_AND_REPORT_CTO` with the exact
delta, having made no edit. That stop was correct: a bcrypt-only edit could not
achieve install-path parity and was forbidden from touching the other two.

**H7-R2 (CTO-authorized, superseded by H7-R3):** the CTO overrode the bcrypt-only
restriction for exactly three `requirements.txt` corrections — bcrypt
`5.0.0 → 4.0.1`, cryptography `46.0.4 → 46.0.5`, add `openpyxl==3.1.5`. Kilo
review (`reports/dc12r1-h7-r2-v1-kilo-review-2026-08-12`, commit `ea3baf41`)
then returned STOP with three findings: (001) the requirements parser silently
overwrote duplicate governed lines; (002) the lock parser dict-comprehension
silently overwrote duplicate entries; (003) `openpyxl 3.1.5` depends on
`et-xmlfile` (locked at `2.0.0`) but `requirements.txt` had no `et-xmlfile` pin,
so the "complete install-path parity" claim was an overclaim. H7-R2's PASS is
**SUPERSEDED_BY_H7_R3**.

**H7-R3 (CTO-authorized, superseded by H7-R4):** recomputed the complete
Poetry main-runtime lock map (70 packages) vs `requirements.txt` and found the
**only** remaining drift was the missing transitive `et-xmlfile==2.0.0` (no
extras, no version mismatches, no duplicate names). R3 adds `et-xmlfile==2.0.0`
and rewrites the manifest test's parsers to be fail-closed:
`parse_requirements_text` uses `packaging.requirements.Requirement` (exact `==`
only; rejects malformed/URL/wildcard/non-exact/duplicates/normalized-name
collisions) and `parse_main_lock_packages` validates every lock entry and
rejects duplicate names. The suite (44 tests) proves full-map equality
(requirements.txt == Poetry main-runtime lock, identical normalized names and
exact versions) and includes authentic RED mutation tests for each parser
failure mode. `pyproject.toml` and `poetry.lock` remain byte-identical. Evidence
in
`ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`.

**H7-R4 (CTO-authorized, superseded by H7-R4-R1):** closes four Kilo findings
on R3: (001) the lock parser silently accepted/excluded malformed entries or
raised unrelated exceptions — now validates name/version/groups exhaustively
with controlled `ValueError` for 13+ malformed forms; (002) the requirements
parser silently dropped extras and the broader wording overclaimed parity —
extras are now rejected, all contract language uses the exact phrase
"requirements.txt and Poetry's main-group lock inventory have identical
canonical package names and exact versions," and markers/hashes/sources/
installer execution are explicitly excluded; (003) install-path tests used
raw substrings — replaced with structural source-shape guards for setup.sh
and Dockerfile with RED mutation tests; (004) GitNexus status reproducibility
is host-specific. The test suite grew to 75 tests. Dependencies, product
code, Dockerfile, setup.sh, pyproject.toml and poetry.lock remain
byte-identical to R3; full backend gates are inherited from R3. Evidence in
the same ledger path.

**H7-R4-R1 (CTO-authorized, superseded by H7-R5):** corrects two remaining uncovered false-green
paths found by CTO review: (A) the setup.sh guard now tracks multi-line shell block
depth (if/fi, for/do/done, while/do/done, until/do/done, case/esac, functions) and
requires the pip line to be exactly ``pip install -r requirements.txt`` with no
suffix/redirect/chain; (B) the Dockerfile guard now joins continuations, locates the
final build stage, and detects inert/dead-branch forms (echo-wrapper, ``false &&``,
``|| true``, ``ENV``/``LABEL``/``ARG`` carriers) on RUN lines. The test suite grew
to 92 tests; all manifests, product code, Dockerfile and setup.sh remain byte-
identical; full backend gates are inherited from R3. Evidence in the same ledger.

**H7-R5 (CTO-authorized, superseded by H7-R5-R1):** repairs the native Linux setup path:
``set -Eeuo pipefail`` + ERR trap; bounded PostgreSQL/Redis health polling
replaces fixed sleep; migration uses valid ``alembic -x tenant_schema=... upgrade
head`` order (public first); ``pnpm install --frozen-lockfile`` replaces
``npm install``; ``docker compose`` before ``docker-compose`` fallback; repo
root resolved from script location. Command examples in ``alembic/env.py`` and
``bootstrap_tenant_schema.py`` corrected. The test suite grew to 97 tests with
RED mutations for every setup failure mode. All H7 manifest versions and 70==70
parity preserved; requirements/pyproject/lock/Dockerfile/Compose unchanged.
Evidence in the same ledger.

**H7-R5-R1 (CTO-authorized, superseded by H7-R5-R2):** replaces the ineffective post-public
``alembic -x tenant_schema=... upgrade head`` (a no-op per the project's
shared-version-table design) with the canonical tenant path:
``python scripts/bootstrap_tenant_schema.py "$DEFAULT_TENANT_SCHEMA" --database-url
"$RESOLVED_DATABASE_URL"`` where the URL is resolved from
``core.config.settings`` and never printed. The ERR trap is rewritten to
truthfully state partial-artifact risk (no false "no changes applied" or
rollback claim). Compose invocation stored as a shell array with Compose-scoped
``exec -T`` health checks (no hard-coded container IDs or users). The test
suite (94 tests) uses the real committed setup.sh as the mutation base for every
RED case. All manifests, Dockerfile, Compose, and product code unchanged.
Native Linux execution remains a Lubuntu gate — not claimed here.

**H7-R5-R2 (evidence checkpoint, superseded by H7-R5-R3):** the setup path now
verifies the safely parsed DATABASE_URL tuple (username, database, host,
port) against the running Compose postgres identity (container-owned
`POSTGRES_USER`/`POSTGRES_DB` via `exec -T ... sh -ec`), never printing the
password. The executable harness uses task-owned fake executables in a
temporary fake-bin directory prepended to PATH (MSYS-style) against an
UNMODIFIED copy of setup.sh: strict ordered command indexes, exit-status
preservation (42/43/44), pg/redis timeouts, invalid-Compose zero side
effects, no-secret output, and idempotency are all proven (9/9). H7 suite
103/103 in natural and reverse order; `bash -n`, py_compile, pre-commit,
detect-secrets, mojibake clean.

**Focused-regression red node (unresolved, environment-gated):**
`tests/test_token_properties.py::test_property_token_roundtrip_integrity`
fails intermittently with `hypothesis.errors.FailedHealthCheck` /
`HealthCheck.too_slow` (input generation > 1 s) under this host's heavy
concurrent load (seed
`303296478269760642762159842520761126666`); it passes on isolation/replay.
This node is **classified but unresolved** — it is an environment-gated
Hypothesis timing health check, not an H7 defect (the Poetry test env is
lock-governed and byte-identical since R3). The R5-R2 verdict is therefore
`STOP_AND_REPORT_CTO_AWAITING_LUBUNTU_ZERO_RED`: the inherited R3 full-gate
evidence (3366/0/0) does **not** satisfy the current zero-red focused gate,
and the zero-red focused run must be obtained on the Lubuntu host.

**H7-R5-R3 (evidence checkpoint, superseded by H7-R5-R4):** adds complete preflight
before side effects (rendered Compose config validation, DATABASE_URL tuple
verification against container identity, re-resolution after pip install);
loopback-only Compose port bindings (`127.0.0.1`); `.gitattributes` LF
enforcement for setup.sh; and the KILO-001 hash-disproof record
(env.py=`1c71de7` / bootstrap=`ca7d91f`, both verified unchanged). H7 suite
103/103 natural+reverse; executable harness 9/9; all deterministic gates
clean; immutable files byte-identical to `bb52c01b`. The Hypothesis
`HealthCheck.too_slow` focused-regression red node remains unresolved and
environment-gated. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.

**H7-R5-R4 (evidence checkpoint, superseded by H7-R5-R5):** PostgreSQL/Redis published
ports moved from base docker-compose.yml to docker-compose.override.yml
(loopback-only `127.0.0.1:${PORT:-5432}:5432`). setup.sh preflight is now
dependency-free before pip (stdlib .env parser, no core.config import), with
rendered Compose v2 JSON port-object validation and in-memory credential
identity comparison (password never printed). Fake Python harness delegates
JSON/URL/file parsing to the real interpreter (`$REAL_PYTHON`). H7 suite
103/103 natural+reverse; all deterministic gates clean; immutable files
byte-identical to `f18761b1`. Hypothesis `HealthCheck.too_slow` focused-
regression red node remains unresolved and environment-gated. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.

**H7-R5-R5 (evidence checkpoint, superseded by H7-R5-R6):** consolidated preflight
into one secret-safe Python process via heredoc temp file (all parsing,
credential comparison, and Compose v2 port-object validation inside one
stdlib process; secrets never emitted). Added tested Bash selector
(explicit Git Bash path, rejects System32/WSL). Harness now 11 nodes
(9 existing + bash-selector + CRLF-blob-proof). Fake Python delegates all
JSON/URL/.env parsing to the real interpreter. R5-R4 actual delta was 7
files; Windows CTO reproduction at c8060644 = 2 passed / 7 failed — the
previous 9/9 claim is host-specific and superseded. H7 suite 105/105 natural
+reverse; all deterministic gates clean; immutable files byte-identical.
Hypothesis node remains unresolved. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.
CTO reproduction at `abbbe32f` (Windows): **11 collected / 4 passed / 7 failed** —
preserved as the superseded host-specific record.

**H7-R5-R6 (evidence checkpoint, superseded by H7-R7):** preflight extracted from
setup.sh into a stdlib-only `backend/scripts/setup_preflight.py` (initial mode
reads rendered Compose JSON from stdin + backend/.env by path; post-install
mode imports core.config only after pip; outputs only `OK`; never emits URLs,
passwords, or Compose JSON; no temporary secret-bearing files). setup.sh
pipes `compose config --format json | python scripts/setup_preflight.py ...`
under `pipefail` and runs `--post-install` before Alembic/bootstrap. CRLF
fail-closed self-check via python raw-byte read (MSYS text-mode reads make
shell CR detection unreliable). H7 suite 187/187 natural+reverse; harness
17/17; direct preflight 76/76; immutable files byte-identical. Hypothesis
node remains unresolved and environment-gated. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.

**H7-R7 (evidence checkpoint, superseded by H7-R8):** secret-argv removed
(`--process-db`/`--process-redis` deleted; setup_preflight.py reads
DATABASE_URL/REDIS_URL from `os.environ`); env keys, exact DB scheme,
blank-password and Redis-creds hardening; cross-host harness repair with
coreutils verify. H7 suite 218/218 natural+reverse; direct preflight 104/104;
harness 20/20; immutable files byte-identical. Hypothesis node unresolved and
environment-gated. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.

**H7-R8 (evidence checkpoint, SUPERSEDED_BY_H7_R9):** four precision corrections
on top of R7 (coreutils evidence set; `.env` UTF-8 fail-closed; asymmetric port
contract; unique sentinel). setup.sh byte-identical to `0eb24d88`. H7 suite
229/229 natural+reverse; direct preflight 114/114; harness 21/21; immutable
files byte-identical. Carried two bounded defects into R9: (a) `_published_int`
used `re.match` whose `$` accepts a trailing newline; (b) the coreutils
non-zero-return guard had no direct test. Hypothesis node unresolved and
environment-gated. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.

**H7-R9 (evidence checkpoint, SUPERSEDED_BY_H7_R10):** closed the two R8
defects (`_published_int` `.match`→`.fullmatch`; coreutils non-zero-return
guard test). H7 suite 245/245 natural+reverse both orderings; direct preflight
129/129; harness 22/22. Carried one bounded defect into R10: the non-zero probe
test used `shutil.which("false")`, which is host-fragile (244/1 where `false`
is absent). Hypothesis node unresolved and environment-gated. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.

**H7-R10 (evidence checkpoint, SUPERSEDED_BY_H7_R11):** extremely narrow
correction — non-zero coreutils probe test switched from `shutil.which("false")`
to `sys.executable` (deterministic, host-independent); direct preflight 129/129;
harness 22/22; H7 suite 245/245 both orders. Hypothesis node unresolved and
environment-gated. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.

**H7-R11 (evidence checkpoint, SUPERSEDED_BY_H7_R12):** Compose project
isolation (all fixed `container_name` removed; fail-closed preflight rule) and
native env-file wiring (`docker compose --env-file <backend/.env>`). Authentic
RED/GREEN proofs on the occupied host (sentinel collision vs coexistence;
disjoint renders; port isolation). Direct 133/133; harness 23/23; H7 250/250.
Hypothesis node unresolved. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.

**H7-R12 (evidence checkpoint, SUPERSEDED_BY_H7_R13):** standalone Compose
probe repair (version-only candidate selection; real capability checks through
the `--env-file` array; structural guard; authentic standalone harness with 1
GREEN + 3 mutation REDs). Direct 133/133; harness 27/27; H7 254/254. Hypothesis
node unresolved. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`.

**H7-R13 (historical checkpoint, SUPERSEDED_BY_H7_R14):** narrow test-only correction
— setup.sh and all product files byte-identical to R12. Defect closed: the R12
standalone harness wrote a `docker-compose` fake but the `chmod +x` set only
covered `_FAKE_NAMES`; masked on MSYS but fatal on POSIX (the fake would not
be executable). R13 chmods `docker-compose` only when `standalone=True` and the
normal harness never attempts to chmod a file it does not create (fail-closed
if a fake is missing). New fail-closed assertions prove the standalone fakes
exist and pass the selected Bash's `test -x` (POSIX/MSYS executability; Windows
`os.stat` lacks exec bits), and that the normal harness builds only its own
fakes. Evidence: direct preflight 133/133 natural+reverse; harness 29/29
natural+reverse zero skip/xfail (27 + 2 R13); complete H7 suite 256/256
natural+reverse in both file orders; py_compile, bash -n (setup.sh untouched),
diff-check, pre-commit incl. detect-secrets, UTF-8/mojibake all clean;
GitNexus detect_changes vs `db166b77` = in-scope files only (manifest-parity
test + three evidence docs); immutable blobs unchanged (env.py=`1c71de78`,
bootstrap=`ca7d91f`); protected baseline `a6ef3aac` unchanged. GitNexus note:
`status` is up-to-date at `db166b7` but the local MCP `compare` misreports many
historical files; the precise `git diff` result (R12 = 5 files) is the
authoritative scope record. Hypothesis node remains unresolved and
environment-gated. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`. R13 is the STOP
checkpoint before Kilo bounded review; only after Kilo passes does Lubuntu run
native setup.sh + focused zero-red; no deployment, Playwright or merge.

**H7-R14 (evidence checkpoint, SUPERSEDED_BY_H7_R15):** native Alembic connection
context closure. setup.sh resolves DATABASE_URL from backend/.env via the same
strict `parse_env_file()` the preflight uses (no second handwritten parser, no
`set -a`, no sourcing); the value is captured (never printed), exported BEFORE
`alembic upgrade head`, kept for tenant bootstrap, and unset afterwards — no
alembic.ini fallback. Enforcing harness fakes (alembic/bootstrap) require
`$DATABASE_URL` present and equal to the .env value; authentic RED/GREEN
mutations (remove export, move after alembic, wrong URL for alembic and
bootstrap independently, missing DATABASE_URL) all fail closed. Direct 133/133;
harness 35/35; H7 262/262 both orders. setup_preflight.py, direct preflight
test, and all product/Compose/migration files untouched. Verdict:
`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`. After R14: Kilo
bounded review; Lubuntu V4 repeats native setup twice + focused zero-red;
only then CTO merge consideration.

**H7-R15 through R15-R4 (historical checkpoint, SUPERSEDED_BY_H7_R16):** R15 added `REPORTING_USER_PASSWORD` as a required migration env var (setup_preflight.py enforces it; setup.sh exports it before Alembic and unsets it before bootstrap). R15-R1 fixed three CTO P1 blockers (`_NATIVE_CREDS` lifecycle, backend RUP fail-open, AST coverage). R15-R2/R15-R3/R15-R4 tightened the shell guard to an exact `unset _NATIVE_CREDS` command (no inert bypass) and the AST scanner to fixed-point alias tracking covering all `os.environ`/`os.getenv` forms including module-qualified assignment aliases. Final SHA `1291d87a`; only tests and docs changed relative to R15-R3; source 3 files byte-identical. Direct 144/144; harness 38/38; parity 175/175; complete H7 319/319 both orders. Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_ZERO_RED`. Next: Kilo bounded cumulative R15 review → Lubuntu native setup.sh twice → focused zero-red gate → CTO merge decision. NO native Linux PASS, NO merge approval, NO deployment/Playwright/VPS claim.

**H7-R16 (historical checkpoint, SUPERSEDED_BY_H7_R16_R2_FINAL_CLOSURE):** test-only cross-host portability + Hypothesis isolation. `_select_bash` accepts `platform_name` (deterministic cross-host, no monkeypatch); CRLF test handles nonexistent log + either rejection form; Hypothesis uses `st.uuids()`/`st.binary(16)` instead of slow regex. Accepted evidence: Kilo `e9303476`; Lubuntu native `189852da` (setup twice PASS). Phase 4 baseline 324/321/3 nat, 324/322/2 rev — now **324/324** both orders locally; Lubuntu must rerun to confirm zero-red. Verdict: `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_R16_R2_ZERO_RED`. Next: Kilo bounded R16/R16-R1 review -> Lubuntu reruns Phase 4 only -> focused zero-red gate -> CTO merge decision.

**H7-R16-R2 final closure (MERGED_AND_CLOSED):** source `a0a14e4d` passed Kilo
review `8b04a92b`, Lubuntu native setup `189852da`, and Lubuntu Phase-4
zero-red `4fa13dac`. Controlled merge `ea990826` has parents `a6ef3aac` and
`a0a14e4d`; its tree is identical to the source. Post-merge evidence closed
with H7 bundle 325/325, scoped pre-commit/detect-secrets, exact 15-file scope,
and GitNexus 15,106 nodes / 45,321 edges / 300 flows indexed and current at
`ea990826`. Historical STOP and SUPERSEDED entries above remain evidence of the
review path, not the current gate state.

## Active Phase

**Active gate:** dual-line pre-delivery execution (see
`docs/planning/2026-08-26_mvp_pre_delivery_execution_queue.md`).

The current product-code baseline is `d9dc2e41`. Two bounded product lines may
progress in parallel. A cross-cutting lifecycle contract must also close before
the pricing implementation chain begins:

1. `H2-C` closure: re-integrate the retailer discovery candidate on the current
   baseline, pass a valid backend authority run, then execute its reviewed
   browser inventory. `RT0` remains blocked until this line merges.
2. `SKU-R0-M1-R1`: Codex-L leads the customer-centered
   `CatalogProduct -> SellableUnit -> CatalogOffer boundary` vertical slice;
   OpenCode2 supplies independent source/runtime/browser review. No candidate
   exists yet and no pricing semantics are authorized.
3. `ORDER-LIFECYCLE-R0` / `CQ-ORD-001`: select one state-transition authority,
   route all state writes through it, and freeze draft void versus confirmed/
   paid cancellation semantics before pricing or timeout work.
4. `PRICING-R0` (freeze base/special-price/order-price/reorder contracts after
   H2-C, stable catalog identity, and the lifecycle contract are accepted)
5. `PRICING-R1` (SKU base price + per-retailer special price)
6. `ORDER-PRICE-R1` (one-shot wholesaler price adjustment + retailer
   confirm/reject/24h timeout)
7. `REORDER-R1` (reorder from history with current-price re-resolution)
8. First-use onboarding (首次使用引导)
9. Close the remaining `MVP_REQUIRED` quality gates, then run the full business
   journey / VPS / real-device final acceptance.

Standing boundaries:

- `FINANCE_LOCALIZATION_R0 = AUDIT_ONLY_NON_BLOCKING`: Uganda/UGX and
  multi-currency questions do not block the MVP queue.
- Custom SKU fields remain `POST_MVP_DISCOVERY`; SKU-M1 is limited to stable
  product/package identity and immutable order snapshots.
- New pricing/order/reorder code must follow `CQ-MOD-001` and
  `CQ-WARN-001`: do not enlarge the existing order route monolith, add
  `datetime.utcnow()`, or add blanket warning suppression.
- This queue is planning truth, not implementation authorization; each entry
  still requires its own CTO-authorized gate before product code changes.
- A local rehearsal or merged browser gate is not a VPS, HTTPS,
  customer-delivery, or production approval. Nothing is deployed.

## Ordered Delivery Plan

1. **S3-S2B-I2A (completed):** reusable canonical payment mutation service,
   behavior-preserving parity, amount-integrity guard, and independent review.
2. **S3-S2B-I2B (completed):** declaration submission, cashier confirmation/
   rejection, atomic canonical payment, receipt allocation, and relationship-
   scoped status visibility.
3. **S3-S2B-I2C-I1 (completed):** read-only backend Contracts A-C for order,
   declaration, and receipt print data.
4. **S3-S2B-I2C-I2 (completed):** browser-printable frontend for Contracts A-C;
   no Contract D, events, outbox, provider delivery, or financial writes.
5. **S3-S2B-I2C-I2B (completed):** read-only backend and browser-print Contract D
   relationship statement using immutable-ledger arithmetic and two independent
   movement/payment lists.
6. **H7 (completed):** manifest parity, fail-closed native setup, Compose
   isolation, cross-host harness portability, and independent zero-red closure.
7. **MVP-L1 automated browser rehearsal (completed):** source `f51c109` passed
   the fresh-runtime `162/162` gate and was merged as `a29f8db0`.
8. **MVP-L1-J1 (completed):** friction-audit lineage merged through
   `c5b66d26` and the J1-H2-A-R2 credential closure merged as `6e9470a1`.
9. **MVP-L1-J1-H2-B (completed):** wholesaler password recovery and
   test-hygiene closure merged and browser-verified as `436d61e2`.
10. **Pre-delivery queue (active dual line plus quality gate):** `H2-C` and
    `SKU-R0-M1-R1` run as separately gated parallel lines. Before pricing,
    close `ORDER-LIFECYCLE-R0`; then continue with `PRICING-R0` → `PRICING-R1`
    → `ORDER-PRICE-R1` → `REORDER-R1` → first-use onboarding → remaining
    `MVP_REQUIRED` quality closures → full business journey / VPS / real-device
    final acceptance.
    Details and frozen pricing inputs live in
    `docs/planning/2026-08-26_mvp_pre_delivery_execution_queue.md`.
    `FINANCE_LOCALIZATION_R0 = AUDIT_ONLY_NON_BLOCKING`; custom SKU fields
    remain `POST_MVP_DISCOVERY`. Quality dispositions are frozen in
    `docs/planning/2026-08-30_mvp_code_quality_debt_register.md`.
11. **S3-S2B-I2C-I3 (deferred post-MVP):** transactional outbox, event emission,
    and provider delivery require separate CTO authorization.
12. **DB-OPS:** access, backups, restore, monitoring, retention, and incident
    package before pilot operation.
13. **Tenant branding and manuals:** legal profile, logo, dual branding, and
    current user/operator documentation.

## Agent Assignment

- **Zcode/Windows product line:** close H2-C baseline integration and bounded
  corrections under explicit CTO gates.
- **Codex-L SKU supervisor:** own SKU-M1 architecture, implementation, internal
  review and candidate evidence within the frozen product/package boundary.
- **OpenCode2:** independently review SKU source, migration, tests, fresh
  runtime and browser evidence; it must not inherit Codex-L's PASS claims.
- **All product agents:** start from a fetched, clean, isolated worktree at
  current baseline `d9dc2e41`; no self-reported PASS is merge authority.
- **Journey observer:** for the onboarding and final-acceptance queue entries,
  record workflow time, clicks, assistance, API-only steps, dead ends, and
  abandonment risk without coaching away product friction.
- **Playwright agent:** retained for regression reproduction and per-entry
  browser evidence; the accepted H2-B harness matrix (24/24) is closed.
- **Codex CTO:** own scope, environment/source classification, and acceptance
  decision.
- **Independent reviewer:** review any correction candidate before it can alter
  the accepted baseline.
- **Lubuntu Codex:** provide independent cross-host runtime verification when a
  source correction or VPS candidate is frozen.
- **OPS:** begin VPS/DNS/TLS work only at the final-acceptance queue entry,
  after the local gates are accepted.
- **Human owner:** perform acceptance and approve credentials, domains,
  business/legal data, and any production action.

## Stop Conditions

Stop and report to the CTO if:

- fetched `origin/product-dev-recovered` is not exactly the authorized task
  base or does not descend from reviewed baseline
  `d9dc2e4130ea87a57d433dfadeb2f2736576fac6`, or that
  baseline does not descend from the J1-H2-A-R2 merge
  `6e9470a1daa5d6eece29724316fdd8aef6b737c1`, the R4-C1-R1 merge
  `a29f8db02365737c64d0d8d442e8ef48a8a19d6d`, or accepted Contract D merge
  `adcc7f281c661897ad050a8278686375b611edb5`;
- statement data is accepted from client-calculated financial fields;
- supplier or retailer authority comes from request-supplied IDs;
- ledger movements and settled payments are correlated without a persisted key;
- a soft-deleted order loses historical movements, an orphan ledger reference
  is silently omitted, or inconsistent arithmetic renders a document;
- printing or event generation can mutate a payment, ledger, order, receivable,
  settlement, declaration, or receipt;
- an event may be emitted before the related transaction is committed;
- the slice adds external SMS/WhatsApp delivery, provider credentials, an
  event/outbox, a new migration, permission, dependency, or financial write;
- S3-S3-D edits product code instead of remaining a design/audit gate;
- the task changes deployment or protected refs;
- a SKU task changes pricing, order lifecycle, payment, or customer-special-
  price semantics; migration `038` has the wrong parent, creates multiple
  heads, guesses legacy identity by code/name, or partially mutates tenants;
- an authority run starts after CWD, temp-DB, profile, Alembic, PG, Redis, or
  child-proof preflight has failed;
- evidence relies on skip, xfail, deselection, or assertion weakening.

## Update Protocol

Update this file after every meaningful merge, blocker, deployment, or phase
transition. Keep it current and concise. Move durable strategy to
`PROJECT_MEMORY.md`, full status to `PROJECT.md`, and detailed evidence to
`ai-ledger/`.
