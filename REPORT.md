# REPORT.md — DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R5-R4-R1-V2-D1
## HC06 First-Red Forensic Classification (existing-evidence only)

- Date: 2026-08-31 (+08:00); Executor: OpenCode2 (Lubuntu-H2C-D1); Supervisor: Codex-L
- RUN_UNDER_REVIEW: the existing single-authority TEST_RED run of R5-R4-R1-V2 (2026-08-31)
- CANDIDATE: `ba9153ecdbfa38f8cfd0eccb8bce8e70656f0c3a` (this branch's parent, exact)
- VERIFICATION_TIER: `V0_FORENSIC_EVIDENCE_CLASSIFICATION`
- CLAIM_CEILING: `EXISTING_EVIDENCE_CAUSAL_CLASSIFICATION_ONLY`

## 0. Required declarations

```text
ORIGINAL_RUN_VERDICT=TEST_RED_REAL_COMMAND_NONZERO
PLAYWRIGHT_INVOCATION_COUNT=1
RERUN_COUNT=0
PRODUCT_CAUSE=EXECUTOR_ENVIRONMENT_DEFECT
MERGE_READY=NO
DEPLOYMENT_READY=NO
```

No runtime probe of any kind was performed for this classification (no PG/Redis/
backend/frontend/SMTP start, no Playwright/pytest/curl/API/browser probe). All
findings derive from the preserved task-private evidence set
(`/tmp/j1h2c-task/`, left in place un-cleaned per directive) plus provenance-
tagged read-only imports of the run's backend/dev-server logs and backend env
file (`evidence/raw-evidence-manifest.sha256` lists every raw file and SHA-256).
No candidate, harness, product, test, or existing-evidence byte was modified.

## 1. Evidence integrity (phases 1–4)

- Evidence set present, owned exclusively by the task user (uid 1000), zero
  non-owner files, zero world-writable files. Raw tree set read-only after
  manifesting; a value-redacted sanitized copy was made separately.
- Stable-sorted SHA-256 manifest of all 18 raw files:
  `evidence/raw-evidence-manifest.sha256`.
- Control-plane audit ledger: 2 records, `prev_sha→event_sha` chain linked
  (genesis `0000…` → `9bdecc1a…` → `70ab5014…`); terminal seal proven by the
  runner's own evidence contract (`evidence()` refuses to output without
  `hasTerminalSeal()`, and it returned `ledger_sealed=true`).
- `evidence/authority-evidence.json` (runner-published, labels/booleans only):
  `state=TEST_RED`, `preflight_invocations=1`, `launch_starts=1`,
  `input_materialized=true`, `candidate_sha_live_resolved=true`,
  `argv_authorized=true` — invocation count 1, rerun count 0, candidate
  binding live-resolved at the canonical repo root.

## 2. HC06 timeline (phase 5; all timestamps UTC, backend access log)

| t (UTC) | Event | Source |
|---|---|---|
| 10:31:20.2 | `POST /api/v1/retailers/register` → **201** (established retailer, precondition) | backend log L149–151 |
| 10:31:20.7 | `POST /api/v1/retailers/setup-credential` → **200** | L152–154 |
| 10:31:21.2 | `POST /api/v1/client/auth/login` → **200** (established login proof) | L155–157 |
| 10:31:21.6 | `POST /api/v1/retailers/register` → **201** (unverified retailer) | L158–160 |
| 10:31:22.1 | `POST /api/v1/client/auth/login` → **401 INVALID_CREDENTIALS** (unverified stop-proof — expected neutral failure) | L162–164 |
| 10:31:22.2 | `POST /api/v1/client/auth/login` → **401** (W2 wrong-supplier stop-proof — expected neutral failure) | L166–168 |
| ~10:31:34.3 | HC06 begins; genuine double-click submitted (node result `startTime=2026-08-31T10:31:34.309Z`) | results.json |
| (same second) | browser CORS **preflight** `OPTIONS /api/v1/client/auth/forgot-password` → **400 Bad Request** — exactly **1** occurrence | backend log L169 |
| — | actual `POST /api/v1/client/auth/forgot-password` reaching backend: **0 occurrences** | log census |
| +120052 ms | `expectNeutralResultShown` → locator timeout waiting for `getByTestId('forgot-neutral-result')`; node `timedOut`; fail-stop (`maxFailures=1`) | results.json; run console |
| close | reconciliation published in `afterAll`; write order: reconciliation.json → results.json → results-junit.xml (mtime-ordered) | artifact mtimes |

Additional run-scope facts:

- **POST count**: exactly the preconditions' calls above; the journey's forgot
  POST count at the backend is **0** (the browser never sent it — the
  preflight was rejected first). No reset-password POST exists anywhere in the
  log.
- **Response to the page**: none reached page JavaScript (blocked at
  preflight); the page-side fetch could therefore never settle successfully.
- **Console/pageerror/CORS browser categories**: NOT CAPTURED — the frozen
  config runs trace/screenshot/video off and HC06 installs no console capture;
  recorded as evidence-absent, not evidence-negative.
- **Final DOM state**: the only DOM fact on disk is the 120 s absence of the
  `forgot-neutral-result` element (locator wait timeout). No richer DOM
  capture exists (hygiene contract).
- **Maildir before/after**: run-start contract held — maildir empty (mode 700,
  0 files) before the run; after the run exactly **2** delivery files exist,
  both precondition retailer setup emails; **zero** forgot/reset deliveries —
  consistent with the backend never processing a forgot request (the in-memory
  sink mirror writes exactly one file per real backend emission, 1:1).
- **Reconciliation write order**: single `afterAll` write, ordering-truthful:
  `preconditionOutcome=PRECONDITION_PASS`; outcomes pass=5 / fail=1 (HC06) /
  notRun=11 / pending=0; browser 5/15, static 0/2, gap=0 accounting,
  incomplete=[HC06, HC07–HC10, HC12–HC16, HC11, HC17]
  (`evidence/reconciliation.json`, `.csv`).

## 3. Actual CORS_ORIGINS (phase 6)

Three mutually independent raw-evidence proofs establish the effective backend
allowlist:

1. `raw-import/backend.env` line 26 (the pydantic-settings env-file source of
   the running process): `CORS_ORIGINS=["http://localhost:5173"]`.
2. `backend-uvicorn.log` contains
   `error parsing value for field "CORS_ORIGINS"` — the strict-JSON validation
   gate was ACTIVE (any non-JSON or wrong-shape value crashed startup; two
   such failed launches are in the same log).
3. The same log ends with `Application startup complete` — the final effective
   value passed strict validation.

⇒ Effective allowlist == `["http://localhost:5173"]` exactly (this public
origin string is reported per directive; no credential, token, email, or
database URL is disclosed anywhere in this report).

The page origin is separately proven: `J1H2C_BASE_URL=http://127.0.0.1:5173`
(raw materialized-input record, consumed as the Playwright `baseURL`) and the
dev server bound `127.0.0.1:5173` (vite log). For CORS, `http://127.0.0.1:5173`
and `http://localhost:5173` are **distinct origins** (host form differs).

## 4. PG/Redis ownership (phase 7; metadata only, runtime untouched)

`docker inspect` metadata (read-only): both containers were created
2026-06-21 on network `validation-target_mpango_network` with host port
bindings on default ports 5432/6379. They are therefore the **shared host dev
stack, not a task-exclusive stack** (unlike the B1-R4 precedent's fresh
per-task containers). This round's run bound those default host ports; sibling
task stacks use separate containers/ports. Recorded as an environment
topology fact; no runtime was queried or changed.

## 5. Executor trap register (phase 8)

`EXECUTOR_TRAP_PKILL_SELF_MATCH`: `pkill -f "uvicorn main:app"` matches the
invoking shell's own command line (pattern text appears in the `bash -c`
argv), so the launcher repeatedly killed its own shell — observed as
"no output + tool timeout". Registered as a **pre-authority provisioning-phase
executor trap**. It is NOT the HC06 root cause: it occurred before the single
authorized browser invocation, and the HC06 causal chain below is complete
without it.

## 6. Classification (phases 9–10): `EXECUTOR_ENVIRONMENT_DEFECT`

Complete causal chain, every link on disk:

1. The launcher (executor) supplied the page origin in host-form `127.0.0.1`
   (`J1H2C_BASE_URL=http://127.0.0.1:5173`, raw materialized input) while the
   backend allowlist was in host-form `localhost`
   (`CORS_ORIGINS=["http://localhost:5173"]`, proven in §3).
2. HC06's genuine double-click made the page request
   `POST /client/auth/forgot-password` cross-origin; the browser sent the
   CORS preflight `OPTIONS` (exactly once, backend log L169).
3. The backend's CORS middleware — operating exactly as its validated
   configuration dictates — rejected the non-allowlisted origin with
   **400 Bad Request** (route-level mismatch would be 405; an origin-rejected
   preflight is a bare 400).
4. The browser therefore blocked the actual POST: **0** forgot POSTs at the
   backend, **0** forgot deliveries in the mirrored maildir.
5. The page's fetch could never settle successfully, so the neutral-result
   element was never rendered; `getByTestId('forgot-neutral-result')` timed
   out at 120052 ms → HC06 FAIL → fail-stop → 11 nodes NOT_RUN →
   reconciliation TEST_RED → control-plane classification
   `TEST_RED` (rc≠0, reconciliation incomplete).

Why the other classifications are excluded:

- **PRODUCT_DEFECT** — excluded: every backend behavior in the window is the
  documented, correctly-configured one (201/200 precondition lifecycle, two
  expected neutral 401 stop-proofs, policy-correct CORS preflight rejection);
  there is no backend malfunction to attribute.
- **HARNESS_DEFECT** — excluded as root cause: the harness drove the real UI
  and timed out only because a lawful response could never arrive. (A
  non-causal observation is registered as F-002: the spec's
  `waitForRequest(urlFragment)` can resolve on the preflight `OPTIONS` rather
  than the blocked POST, so the "request observed" step under-discriminates
  method. A stricter wait would still end in the same DOM timeout — the
  response was environment-blocked, not harness-lost.)
- **INSUFFICIENT_EVIDENCE** — not required: every link from trigger to DOM
  timeout is on-disk raw evidence (§2, §3, §6).

Scope statement: the defect is in the **executor's launcher configuration**
(origin host-form mismatch between the two task-supplied values), not in the
candidate product and not in the frozen harness. The candidate product remains
unadjudicated by this round.

## 7. Files in this publication (delta vs CANDIDATE)

D1-E1 metadata correction (publication-path accounting only): the D1 commit's
Git delta is exactly **9 new files**; the `evidence/` directory contributes
exactly **6** of them (the backend log extract remained a task-private
evidence import and is accounted by the published raw-evidence manifest, not
as a committed file). Root cause, evidence content, findings and verdict are
unchanged.

| Path | Kind |
|---|---|
| `REPORT.md` | this report |
| `findings.csv` | findings register (5-column schema, F-001…F-003) |
| `evidence/…` | sanitized, values-free evidence (**6 files**: reconciliation.json, reconciliation.csv, authority-evidence.json, env-names-only.json, ledger-shapes.jsonl, raw-evidence-manifest.sha256) |
| `committed-blob-manifest.csv` | committed-blob SHA-256 manifest of this tree, self-excluding |
| **Total** | **9 new files** |

Sanitization: every published evidence file carries labels/categories/counts/
hashes only. A values-scan (emails, password labels, canonical-code prefixes,
Bearer shapes, token query parameters) over the publication delta precedes
commit; no values are present.

## 8. STOP

`ORIGINAL_RUN_VERDICT=TEST_RED_REAL_COMMAND_NONZERO`; rerun count 0; this
round publishes classification only. No fix, no rerun, no merge, no deploy.
Raw evidence stays in place un-cleaned pending CTO acceptance.
