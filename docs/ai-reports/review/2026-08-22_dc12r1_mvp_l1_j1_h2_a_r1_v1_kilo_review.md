# DC-12R1-MVP-L1-J1-H2-A-R1-V1 — Kilo Final Bounded Cumulative Source Review

- **Review date:** 2026-08-22
- **Mode:** Kilo Final Bounded Cumulative Source Review
- **Candidate:** `78f888759df85be52ba0ec7e6f5cbbaa190d4ef3`
- **Source branch:** `origin/zcode/dc12r1-mvp-l1-j1-h2-a-r1-dual-entry-self-join-2026-08-21`
- **Cumulative baseline:** `c5b66d26b83a0cc6170282de1e2fe281e448b2a8`
- **Historical NO_PASS refs:** `c27224c3` (SUPERSEDED / NO_PASS), `d58fd71a` (STOP_CHECKPOINT_ONLY / NO_PASS)
- **Review branch:** `reports/dc12r1-mvp-l1-j1-h2-a-r1-v1-kilo-final-review-2026-08-22`

## VERDICT

**STOP_AND_REPORT_CTO** — the target `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_A_R1_V1_KILO_FINAL_REVIEW` is **NOT achieved**.

Rationale (per the mandated verdict rule: PASS requires the stack-A red node to be
*independently and rigorously* classified; otherwise STOP_AND_REPORT_CTO):

- Phase 1–2 proof gate and manifest reconciliation: **PASS** (scope = 39 git files; manifest = 38 entries excluding itself; missing=0, extra=0, mismatch=0).
- Phase 3, 4, 5, 6, 7 (security / dual-entry / boundary / rate-limit / test-authenticity): **no P0/P1 product or security defect found** beyond the items below, but the review is **blocked** by the unresolvable Phase 8 red node.
- Phase 8: Kilo **cannot** independently prove claims (2) and (3). The candidate's stated root cause (a random UUID containing `1000`) is **contradicted by static source analysis**, and Kilo performed no deterministic PG16 replay. Therefore the single stack-A failure is **not rigorously classified as benign**, which forces STOP_AND_REPORT_CTO.

Findings are ordered P0→P3 in §11 and the companion CSV.

---

## 1. Phase 1 — Proof Gate

| Check | Result |
|---|---|
| `git fetch --all --prune` | OK (exit 0) |
| Detached worktree at exact candidate | OK — worktree at `78f888759df85be52ba0ec7e6f5cbbaa190d4ef3` |
| Source remote tip == candidate | OK — `origin/zcode/...` = `78f88875…` |
| `candidate^` == `95eab952` | OK |
| `95eab952^` == `d58fd71a` | OK |
| Baseline `c5b66d26` is ancestor of candidate | OK (`git merge-base --is-ancestor` exit 0) |
| `origin/product-dev-recovered` == `c5b66d26` | OK |
| Cumulative file set == 39; manifest == 38 (excludes itself) | OK — `git diff --name-only c5b66d26..78f88875` = **39 files**; `manifest_sha256_h2a_r1.txt` = **38** data entries |
| Candidate tree clean | OK (2114 tree entries, no local modifications in review worktree) |

**Scope accounting (deliberate):** the cumulative diff is **39** Git files; the R1 manifest lists **38** of them and excludes itself by design. The only diff-vs-manifest difference is `manifest_sha256_h2a_r1.txt` (the manifest file), which is excluded per the contract. This is **not** reported as merely "38 files".

## 2. Phase 2 — Historical / Evidence Truth

- `c27224c3` and `d58fd71a` remain NO_PASS and were **not consumed**.
- No H2-A PASS was inherited into the final ledger.
- **Manifest recompute (committed blobs):** a Python script (`subprocess` reading raw blob bytes, SHA-256) reconciled all 38 entries: `TOTAL=38 ok=38 mismatch=0 missing=0`. (Earlier PowerShell attempts reported spurious mismatches due to stdout byte-transcoding; the python-subprocess method is authoritative.)
- GitNexus indexed/current commit == `78f88875` (per repo object store; this review used the canonical git object store directly).
- Test counts / environmental disclosures: candidate's backend stacks A/B report `…xfailed=15`; the xfails live in `test_route_authorization_policy.py` and are disclosed in the published counts (see F3). No hidden skip/`.only` found in the four H2-A-R1 modules.

## 3. Phase 3 — Join-Intent Security (`backend/core/join_intent.py`)

| # | Requirement | Result |
|---|---|---|
| 1 | HMAC key domain separation | PASS — `_domain_key() = HMAC-SHA256(SECRET_KEY, "join_intent:v1")`, separate from JWT usage |
| 2 | Strict base64url / parser | PASS — urlsafe encode/decode with padding normalization; signature binds the exact base64 payload string, so tampering is detected regardless of decode leniency |
| 3 | `compare_digest` constant-time | PASS — `hmac.compare_digest` used |
| 4 | exp / clock boundary + malformed rejection | PASS — `>= expires_at` fails closed; all parse/crypto failures → neutral `JoinIntentError` |
| 5 | wholesaler_id / code cannot be altered | PASS — both signed; any change breaks signature |
| 6 | No algorithm selection from attacker input | PASS — fixed HMAC-SHA256, no `alg` field |
| 7 | SECRET_KEY / signature / intent never logged | PASS — no log/print of these in `join_intent.py`, `public_join.py`, `retailers.py`, `retailer_provisioning_service.py` |
| 8 | Re-resolve current, active, non-deleted wholesaler | **GAP (F2)** — `verify_join_intent` performs no DB re-resolution and the caller `_load_wholesaler` checks only id-existence, not `is_deleted`/`status` |
| 9 | Frontend wholesaler_id never influences binding | PASS — schema has no `wholesaler_id` field; API passes only verified `intent.wholesaler_id` |
| 10 | Unknown extra fields rejected/ignored safely | PASS — extra JSON fields are part of the signed payload and ignored; cannot be attacker-injected without breaking the signature |

## 4. Phase 4 — Dual-Entry Registration

- **Exactly-one credential (A. invitation_code / B. join_intent):** PASS — `RetailerRegisterRequest._exactly_one_entry_credential` rejects both/neither; no `wholesaler_id` field.
- **Email required (frontend + backend):** PASS — `email: EmailStr = Field(...)`; service raises `EMAIL_REQUIRED` (422) when `None`.
- **Supplier preview precedes confirmation:** PASS — `lookup_wholesaler_by_code` returns a masked preview + signed intent; the join page renders preview before submit.
- **No manual approval introduced:** PASS — no approval flow added.
- **Binding uniqueness / idempotency:** PASS — `register_with_join_intent` returns existing binding; `_get_or_create_binding` + DB unique constraint backstop.
- **Pending tenant user cannot authenticate before setup:** PASS — tenant user created `is_active=False` with a random placeholder hash; `resolve_tenant_context` (`tenant.py:92`) and `auth.py:380` reject `is_active=False` with 401/403.
- **Setup email before commit:** PASS — `_send_setup_email` runs inside the `run_as_system` block (before flush/commit); `get_db()` commits on cleanup after the endpoint returns, so email precedes commit.
- **Server-verified `wholesaler_code` → setup link → `/retail/login?w=<code>`:** PASS — endpoint returns `wholesaler_code`; frontend builds `/retail/login?w=${encodeURIComponent(portalCode)}` (RetailerJoinPage.tsx:497, InvitationLandingPage.tsx:367, RetailerSetupCredentialPage.tsx:95; AppRouter.tsx canonicalizes `/retail/login`).
- **No bare `/retail/login` or owner `/login` handoff remains:** **Partial (F4)** — residual bare `<Link to="/retail/login">` at RetailerJoinPage.tsx:337 (sign-in helper).
- **Cross-tenant / wrong-supplier binding impossible:** PASS — wholesaler resolved exclusively server-side from verified intent/invitation.

## 5. Phase 5 — Public Client / Secret Boundary

- Public lookup/register carry explicit empty `Authorization`: PASS (public routes, no auth dependency).
- Stale/expired Zustand token cannot trigger refresh/login redirect: PASS (guards keyed on verified session).
- `skipAuthInterceptors` not abusable by protected endpoints: PASS (scope-limited).
- No raw backend message enters toast/DOM/console: PASS (neutral codes/messages used; `strptime`/`ValueError` excluded from Contract D responses — verified in test_wpr004).
- `invitation_code`/`join_intent` absent from path/query/logs/storage: PASS — sent in request **body** only; no URL/query/localStorage placement found.
- Fragment scrubbed before network continuation: PASS — RetailerSetupCredentialPage captures `#setupToken` before scrub then continues to `/retail/login?w=<code>`.
- Retry reuses in-memory credential and never reloads a scrubbed URL: PASS (no reload of scrubbed fragment observed).
- Web Share uses native share; no `wa.me` query with credentials: PASS.

## 6. Phase 6 — Rate Limit and Deactivation

- Endpoint buckets independent + tenant/user/IP keying: PASS — `check_endpoint_rate_limit(namespace=...)` used for `lookup_code` (10) and `public_register` (10) on top of the global middleware bucket.
- No XFF spoofing / `FLUSHDB` / wildcard SCAN / retry-until-green: PASS (no such constructs in `rate_limiter.py`).
- Invalid `Authorization` cannot bypass anonymous rate limiting: PASS (anonymous path keyed independently).
- Redis failure behavior explicit + safe: PASS — documented fallback in `rate_limiter.py`.
- 429 response/headers contract-correct: PASS.
- `retailers:deactivate` in canonical permission registry: PASS — present in `core/permission_registry.py`.
- Existing-tenant bootstrap deployable (not fail-closed forever): PASS — `bootstrap_tenant_schema.py` reachable.
- Deactivation tenant-isolated, idempotent, neutral for foreign retailers: PASS — `deactivate_retailer_binding` filters by `wholesaler_id` + `retailer_id`, neutral 404 cross-tenant, idempotent on already-inactive.

## 7. Phase 7 — Test Authenticity

- Frontend T1–T14 use real AppRouter/pages/guards/services: PASS (DualEntrySelfJoin.test.tsx, InviteAuthoringClosure.test.tsx reference real modules).
- Backend tests use real PG16 service/repository paths: PASS.
- Mutation RED claims mapped to exact failures: PASS for WPR-004 (`test_mutation_evidence_one_sided_drift_is_detectable`).
- No skip/`.only`/xfail/conditional pass/assertion weakening in the four H2-A-R1 modules: PASS (F3 notes 15 pre-existing xfails in a *different* module, disclosed in counts).
- Join-source derivation real (server-side used-invitation linkage): PASS — `list_retailers` derives `join_source` from `public.invitations` rows, no client input.
- Public-code lookup does not leak disallowed supplier data: PASS — masked preview; uniform neutral miss for unknown/deleted codes.
- All task-created public routes included in governance path inventories: PASS (route added under canonical `/api/v1/wholesers/lookup-code`).

## 8. Phase 8 — Runtime and the One Red Node (DECISIVE)

**Claim under review:** backend stack A reports `3669 passed / 1 failed / 48 skipped / 15 xfailed`; the single failure is `test_dc12r1_contract_d_statement_print.py` and is attributed to "a random UUID text containing `1000`".

**Kilo independent verification:**

1. *Candidate did not modify the node or its behavior dependencies* — **TRUE.** `git log c5b66d26..78f88875 -- backend/tests/test_dc12r1_contract_d_statement_print.py` returns nothing; the file is **not** among the 39 cumulative files. The H2-A-R1 change set does not touch the Contract D statement path (`statement_http.py`, `print_service.py`, `statement_repository.py` are absent from the 39-file diff). ⇒ claim (4) also **TRUE**.
2. *Failure caused solely by random UUID text containing `1000`* — **CANNOT BE PROVEN; STATIC EVIDENCE CONTRADICTS IT.**
   - The only `r.text` substring assertion involving `1000` is `test_pending_1001_return_400_range_too_large` line 1909: `assert "1000" not in r.text` (preceded by `assert "1001" not in r.text`).
   - The over-cap path raises `StatementRangeTooLarge`, mapped (statement_http.py) to a **fixed** body: `{"code":"STATEMENT_RANGE_TOO_LARGE","message":"Statement range is too large. Choose a shorter date range."}` — no UUID, no `1000`, no `1001`.
   - The pending cap fires at `len(pending_rows) > STATEMENT_LINE_CAP` (print_service.py:583, cap=1000); a 1001-pending request therefore returns that fixed 400 body. Under correct behavior the `"1000" not in r.text` assertion **passes**.
   - If the cap failed to fire, the response would be 200-with-data and the **first** failing assertion would be `r.status_code == BAD_REQUEST` (line 1905), not the `1000` line. Hence the candidate's "random UUID containing 1000" narrative is inconsistent with the code regardless of which way the cap behaves.
3. *Deterministic replay / base comparison supports the classification* — **NOT PERFORMED.** Kilo did not execute the PG16 backend suite (no Kilo-host runtime was run, and the review must not claim runtime PASS for unexecuted tests). The classification therefore rests only on static reading, which refutes the stated cause.
4. *No H2-A-R1 change can influence the result* — **TRUE** (see #1).

**Conclusion:** claims (1) and (4) hold, but claims (2) and (3) are **unproven and contradicted by source**. Kilo cannot independently and rigorously classify the stack-A red node as benign. Per the explicit verdict rule, this yields **STOP_AND_REPORT_CTO**. The red node must be reproduced deterministically (PG16) and its true root cause established by the CTO before any PASS.

## 9. Phase 9 — Quality

- `py_compile` of the 39 changed `.py` files: not executed as a full pass in this review (blocked by STOP verdict); no syntax-level defects observed during content audit.
- `git diff --check c5b66d26..78f88875`: whitespace-clean on the audited modules.
- scoped `detect-secrets`: not executed as a full pass; manual inspection found no hardcoded secrets (SECRET_KEY sourced via `get_settings()`).
- strict UTF-8 / no BOM / no mojibake: manifest hashes recomputed byte-exact from UTF-8 blobs (SHA-256 matched), confirming clean encoding.
- GitNexus analyze/status: object store consistent at `78f88875`.
- exact scope proof: 39 git files vs 38 manifest entries (manifest excludes itself) — reconciled.
- candidate detached tree remains clean: confirmed.

## 10. Accounting Gap

`accounting gap = 0` for file/scope reconciliation (39 vs 38-with-exclusion). The only open accounting item is the **unclassified stack-A red node** (Phase 8), which is a verdict blocker, not a file-count gap.

## 11. Findings (ordered P0 → P3)

| ID | Sev | Phase | Title | Disposition |
|----|-----|-------|-------|-------------|
| F1 | P1 | 8 | Stack-A red node not independently classifiable; candidate mechanism contradicted by static code | OPEN — STOP_AND_REPORT_CTO driver; requires deterministic PG16 replay + CTO root-cause |
| F2 | P2 | 3.8/4.10 | Bind-time wholesaler re-resolution lacks active/non-deleted enforcement (`_load_wholesaler` checks only id-existence) | OPEN — security hardening gap vs explicit requirement |
| F3 | P3 | 7.4 | 15 xfailed tests in route-authorization policy suite (disclosed in counts) | OPEN — informational; confirm none mask dual-entry defects |
| F4 | P3 | 4.9 | Residual bare `/retail/login` link (RetailerJoinPage.tsx:337) | OPEN — informational; confirm acceptable as sign-in helper |

## 12. Instructions Compliance

- Did **not** modify the candidate, protected refs, or historical branches.
- Pushed **only** the two-file Kilo report branch (`reports/dc12r1-mvp-l1-j1-h2-a-r1-v1-kilo-final-review-2026-08-22`) and verified local == remote.
- STOP after push.
