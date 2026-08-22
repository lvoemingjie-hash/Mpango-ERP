# DC-12R1-MVP-L1-J1-H2-A-R2-V4-E1-V1 — Kilo Final Evidence Review

- **Review date:** 2026-08-22
- **Mode:** Independent adversarial evidence review
- **E1 tip:** `26cad662ea398eb2afc4ee69741715dbae890b8c`
- **V4 base report:** `8617b1132f78d499fe17ae2f2466ba7c4c0feb9c`
- **Accepted source review:** `573a288d346fb78b26ccd0636028148c0f39ecad` (R2)
- **Freeze commit:** `e2be88257c368bc2ddf088c9684715ea803ceb52`
- **Candidate:** `bf574cf9b061f7897eb68cbe92a82ce1201e49f0`
- **Protected baseline:** `c5b66d26b83a0cc6170282de1e2fe281e448b2a8`
- **Superseded V3:** `45b100604f3d14a9c0c1aa862ab29e5589020b67`
- **Report branch:** `reports/dc12r1-mvp-l1-j1-h2-a-r2-v4-e1-v1-kilo-final-evidence-review-2026-08-22`

## VERDICT

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_A_R2_V4_E1_V1_KILO_FINAL_EVIDENCE_REVIEW**

All seven required review items passed with independent adversarial verification. No product/source/evidence modification, no merge, no browser rerun. The E1 truth correction accurately supersedes the two overbroad frozen comments **without rewriting the frozen spec/config artifacts**. All frozen refs are unchanged. Scope, manifest, machine evidence, UI authenticity, packaging/security, and cleanup are all verified.

---

## 1. Proof Gate

| Check | Result |
|---|---|
| `git fetch --all --prune` | OK |
| Detached worktree at exact E1 tip | OK |
| E1 parent == 8617b113 | OK (`26cad662^` = `8617b113`) |
| Candidate bf574cf is ancestor of E1 | OK (`git merge-base --is-ancestor` exit 0) |
| Report-branch chain linear | OK — `8617b113..26cad662` = 1 commit (E1 correction), no merges |
| Protected c5b66d26 unchanged | OK |
| Candidate bf574cf unchanged | OK |
| V3 45b10060 preserved | OK |
| Accepted source review 573a288 unchanged | OK |

Note: the earlier apparent 252-merge output was a diagnostic artifact from using two-ref `git log --merges A B`; the correct range form `8617b113..26cad662` yields exactly 1 commit, confirming a linear chain.

---

## 2. Scope

- **E1 delta (8617b113..26cad662) = exactly 3 files:**
  1. `docs/ai-reports/review/j1-h2a-r2-v4-frozen-ui-browser-final.md` — V4 report modification
  2. `docs/ai-reports/review/evidence/j1-h2a-r2-v4/E1_EVIDENCE_TRUTH_CORRECTION.md` — E1 correction document
  3. `manifest_sha256_h2a_r2_v4.txt` — manifest rebuild
- **Candidate..E1 cumulative delta (bf574cf..26cad662) = exactly 15 files**, all under `docs/ai-reports/review/evidence/j1-h2a-r2-v4/` plus the two report markdowns plus the V4 manifest.
- **No backend/**, **no frontend/**, **no .secrets.baseline**, and **no frozen result artifacts** were modified by E1 (they are absent from the 3-file E1 delta).
- **Manifest:** 16 lines total = 2 comment lines + **14 sorted (by path) hash entries**, excluding itself. The E1 correction doc explicitly states: "manifest covers all 13 non-manifest files; manifest excludes itself" and "E1 post cumulative accounting: total delta 15 files, manifest 14 entries."

---

## 3. Frozen Harness

- **Spec blob** `v4-frozen-ui.spec.ts` at freeze commit `e2be882` = `9c2e2bf105eea611eac79c6a9d10974258aa181c` ✓
- **Config blob** `v4-frozen.config.ts` at freeze commit `e2be882` = `74dd70171ce1b103af9556fee6f1799a4c3838e5` ✓
- **Identical at E1 tip `26cad662`:**
  - spec blob = `9c2e2bf105eea611eac79c6a9d10974258aa181c` ✓ (freeze == E1)
  - config blob = `74dd70171ce1b103af9556fee6f1799a4c3838e5` ✓ (freeze == E1)
- **`hash_proof.md`** independently records: pre-run sha256(disk) == sha256(blob) for both spec and config; post-run sha256(disk) == sha256(blob) for both; candidate tree hash constant `83eb1b09...` before/during/after.
- **Frozen blobs were NOT rewritten.** The E1 correction doc explicitly states: "不重写已执行的冻结规格（其 blob 与哈希证明链保持不变——P2 冻结完整性优先于注释措辞）".

---

## 4. Machine Evidence

Independently parsed from the committed authoritative artifacts:

| Artifact | Expected | Unexpected | Skipped | Flaky | Notes |
|---|---|---|---|---|---|
| `authoritative_playwright.json` | 19 | 0 | 0 | 0 | `fullyParallel: false`, `retries: 0`, `actualWorkers: 1`, `grep: {}` |
| `authoritative_junit.xml` | 19 | 0 | 0 | 0 | `<testsuites tests="19" failures="0" skipped="0" errors="0">` |
| `node_report.csv` | 19 rows | — | — | — | 19 unique passed nodes (J00–J18), all `outcome=expected` |
| `reconciliation.json` | 19 | 0 | 0 | 0 | `retries_configured=0`, `workers_configured=1`, `failure_set=[]`, frozen blob IDs match |

- **Node sets reconciled:** JUnit testcases (J00–J18) == Playwright JSON nodes == CSV rows = 19. Accounting gap = 0.
- **No grep/shard/sharding configuration** present in Playwright config (grep is `{}`).

---

## 5. UI Authenticity

Verified from the committed `v4-frozen-ui.spec.ts` and `authoritative_playwright.json`:

- **J01–J18 journey actions use rendered UI:** every step (login, sidebar nav, invitation creation, copy/share, supplier identity, registration form, setup token, portal login, /retail/join code tab, code-entry lifecycle, unknown/malformed code, preview link, stale session, double submit, cross-tenant denial, deactivate, 390px viewport) interacts with real browser-rendered pages via Playwright locators.
- **J14 reaches real registration submission through UI:** test name is "stale contextual session: full code-path registration" — the journey completes registration through the rendered supplier-code form; `expect(registers.length).toBeGreaterThanOrEqual(1)` and `expect(registers.filter(r => r.method === 'POST')).toHaveLength(1)` confirm exactly one register POST originating from UI submission.
- **lookup-code and register requests have Authorization presence=false:** J14 asserts `hasAuthz: Object.keys(req.headers()).some(...)` is false for every public lookup/register call; J12 similarly confirms zero register requests for malformed input.
- **Exactly one register POST and one resulting binding:** J14 and J15 both assert exactly one POST register and the binding count is 1.
- **J14/J15 `APIRequestContext` POST login/select-tenant:** these calls exist solely to obtain a W1 context authorization token for the **read-only GET `/retailers` postcondition**; they do not perform any retailer registration journey action (the E1 truth correction doc explicitly clarifies this and supersedes the overbroad frozen comment "only READ-ONLY GET").
- **J00 credentials are environment-only:** `W1.email/password/code`, `R1_PASSWORD`, `R2_PASSWORD`, `R3_PASSWORD`, `V4_MAILDIR` all read from `process.env`; the test fails closed if any are missing. No credentials are hardcoded in the committed spec.
- **J18 viewport-probe-input:** `viewport-probe-input` is filled into the password field **only** to measure 390px viewport overflow (`assertNoOverflow('portal-login-filled')`); there is **no Sign-In click / form submission**. It is not a runtime credential and cannot authenticate.

---

## 6. Packaging / Security

- **Manifest recompute (raw blob bytes):** entries=14, ok=14, mismatch=0, missing=0. Set diff vs cumulative: extra_in_manifest=∅; missing_from_manifest={`manifest_sha256_h2a_r2_v4.txt` only}.
- **E1 truth corrections accurately supersede the two overbroad frozen comments:**
  1. **Frozen comment overbreadth (v4-frozen-ui.spec.ts lines 17-18):** the comment claimed APIRequestContext use is "only READ-ONLY GET". The E1 correction clarifies J14/J15 also use `POST /auth/login` and `POST /auth/select-tenant`, but strictly for auth-setup (not journey actions). The frozen spec **blob** is untouched (same git blob IDs before/after).
  2. **Credential wording:** "zero real and zero placeholder password literals" is corrected to "zero real or loggable credential literals; all credentials for successful authentication are environment-injected." J00 confirms env-only; J18 confirms viewport-probe-input is never submitted.
- **`git diff --check 8617b113..26cad662`:** clean (exit 0).
- **UTF-8 / no BOM:** raw-blob BOM scan of all 3 E1 delta files → **bom=0**.
- **Scoped detect-secrets / secret scan:** E1 delta is purely documentation; no hardcoded secrets, keys, or PEM material found.
- **JSON/JUnit EOF-newline normalization:** the authoritative artifacts are committed blobs; their line endings are preserved byte-exactly (manifest SHA-256 matches raw blob bytes, confirming content-neutral storage).

---

## 7. Cleanup and Refs

- **Cleanup evidence (`cleanup_closure.md`):** backend uvicorn (port 8000) and frontend vite (port 5173) terminated; Docker containers `h2a_v4_pg16` and `h2a_v4_redis7` removed; volumes and networks cleaned; task ports 15438/6398/8000/5173 released (LISTEN count = 0); runtime directory `_h2a_v4_runtime` and all credentials/env files deleted.
- **Protected / candidate / V3 / source-review refs unchanged:** post-cleanup ref verification in `cleanup_closure.md` confirms candidate `bf574cf9`, Kilo review `573a288d`, V3 diagnostic `45b10060`, and `origin/product-dev-recovered` = `c5b66d26` are all unchanged. Independent re-resolution in this review confirms the same SHAs.

---

## 8. Instructions Compliance

- No browser rerun performed (adversarial evidence review only).
- No product/source/evidence modification.
- No merge.
- Pushed only the two-file Kilo report branch.
- Verified local == remote.
- STOP after push.
