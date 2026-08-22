# DC-12R1-MVP-L1-J1-H2-A-R2-V1 — Kilo Final Bounded Cumulative Source + Runtime Review

- **Review date:** 2026-08-22
- **Mode:** Kilo Final Bounded Cumulative Source + Runtime Review
- **Candidate:** `bf574cf9b061f7897eb68cbe92a82ce1201e49f0`
- **Direct parent:** `78f888759df85be52ba0ec7e6f5cbbaa190d4ef3` (R1 candidate, prior STOP)
- **Cumulative baseline:** `c5b66d26b83a0cc6170282de1e2fe281e448b2a8`
- **Source branch:** `origin/zcode/dc12r1-mvp-l1-j1-h2-a-r2-kilo-closure-2026-08-22`
- **Prior Kilo STOP:** `61ada4e` (R1 report)
- **Report branch:** `reports/dc12r1-mvp-l1-j1-h2-a-r2-v1-kilo-final-review-2026-08-22`

## VERDICT

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_A_R2_V1_KILO_FINAL_REVIEW**

All nine phases passed with **independent runtime proof** on a fresh `PG16@15436 + Redis7@16379` stack (Alembic head 037). The four prior R1 findings (F1–F4) are each **closed by runtime execution**, and no new P0/P1/P2/P3 candidate defect was found. Scope/manifest accounting is exact.

---

## 1. P1 — Proof Gate

| Check | Result |
|---|---|
| `git fetch --all --prune` | OK |
| Detached worktree at exact candidate | OK |
| `source tip == candidate` | OK (`origin/zcode/...` = `bf574cf…`) |
| `candidate^ == 78f88875` | OK |
| Baseline `c5b66d26` is ancestor | OK (`git merge-base --is-ancestor` exit 0) |
| `origin/product-dev-recovered == c5b66d26` | OK |
| **R2 delta == 8 Git files** | OK — `git diff --name-only 78f88875..bf574cf` = 8 |
| **Cumulative == 41 Git files** | OK — `git diff --name-only c5b66d26..bf574cf` = 41 |
| Candidate tree clean | OK |

Scope accounting (deliberate): R2 delta = **8** files; cumulative baseline delta = **41** files (R1 was 39; R2 adds 2 new files — `manifest_sha256_h2a_r2.txt` and one re-touched ledger — while re-modifying 6 already-in-scope files → 39 + 2 = 41). The R2 manifest lists **40** entries (the 41 cumulative files minus the manifest file itself). This is **not** reported as merely "40 files".

## 2. P2 — Manifest and Evidence Accounting

- `manifest_sha256_h2a_r2.txt`: **42 lines = 2 comment lines + 40 sorted (by path) hash entries**, excluding itself — matches the contract exactly.
- Recompute SHA-256 from raw committed blob bytes (Python `subprocess`, not stdout-transcoded): `entries=40, is_sorted_by_path=True, ok=40, mismatch=0, missing=0`. Set diff vs cumulative: extra_in_manifest = ∅; missing_from_manifest = {`manifest_sha256_h2a_r2.txt` only}.
- Ledger wording inspected (`ai-ledger/.../dual_entry_self_join.md`): it **retracts** the original "random UUID containing 1000" attribution ("该原始事件的确切 request_id 值**无留档证据，不成立为已证**" — no archival evidence, not proven). It attributes the failure to the echoed `X-Request-ID`. No incorrect claims of "9 R2 files / 40 cumulative Git files / 7 source-test files" were found; the ledger's scope enumeration (8 authorized items) matches the independently resolved 8-file R2 delta.
- Decisive F1/F2 behavior verified by changing only tests/ledger/manifest + the two F2 source files; **no Contract D production code changed** (statement_http.py / print_service.py absent from the 8-file R2 delta).

## 3. P3 — F1 Contract D Truth (RUNTIME)

Environment: `docker` PG16-alpine on `:15436`, existing `redis:7` on `:16379`, Alembic upgraded to head 037, venv `.venv_deploy` (pytest 8.4.2 / sqlalchemy 2.0.45).

- **Contract D `TestRangeCap`: 8 passed** (including `test_range_cap_deterministic_request_id_repro_h2a_r2_f1`).
- The repro node injects `X-Request-ID: h2a-r2-repro-1000-cap` over the real request path and asserts:
  - `status == 400`, `body["code"] == "STATEMENT_RANGE_TOO_LARGE"`, `"data" not in body`;
  - fixed business message `“Statement range is too large. Choose a shorter date range.”`;
  - `"1000" not in body["message"]` and `"1001" not in body["message"]` (and same for `details`);
  - `"1000" in r.text` **exactly once** and `body["request_id"] == "h2a-r2-repro-1000-cap"` — i.e. the only `1000` is the echoed request_id.
- Chain confirmed: `print_service` 1000-line cap → `StatementRangeTooLarge` → `statement_http` fixed mapper → global `http_exception_handler` flat `{code,message,request_id}` → `request_logging` middleware echoes caller `X-Request-ID`.
- **Old whole-response assertion (`"1000" not in r.text`) is deterministically False** precisely when request_id contains `1000` (the repro test explicitly demonstrates this; the docstring retracts the original random-UUID attribution). The fix replaces it with a business-surface-scoped assertion. **1000/1001 are excluded from the business message/details, not from request_id** — confirmed.
- Conclusion: F1 from R1 is **resolved**; the red node is benign and now deterministically reproduced and fixed.

## 4. P4 — F2 Active-Wholesaler Contract (RUNTIME)

- `_load_wholesaler` (retailer_provisioning_service.py:338-359) requires **matching id AND `is_deleted=false` AND `status=='active'`** (all three), else `INVITATION_NOT_FOUND`/404 — a single uniform neutral error (zero lifecycle disclosure).
- `lookup-code` (public_join.py) gates identically on active + non-deleted.
- `reissue_setup_token` (line 846) calls the same guard → credential reissue inherits the active contract.
- Join path resolves the wholesaler **first** (line 235, "a rejected supplier leaves nothing staged") → zero staged side effects on rejection.
- **H2-A dual-entry self-join suite: 19 passed**, including `test_lookup_code_neutral_for_every_non_active_lifecycle`, `test_join_intent_fails_closed_when_wholesaler_deactivates`, `test_soft_deleted_wholesaler_join_intent_fails_closed`, `test_invitation_registration_inherits_active_guard`, `test_register_tampered_intent_binds_nothing`.
- **Mutation proof:** removing the `is_deleted`/`status` guard made 3 lifecycle tests RED; reverted. No inactive supplier can issue or consume join credentials.

## 5. P5 — F4 Portal Login (RUNTIME)

- `RetailerJoinPage.tsx` renders **no bare `/retail/login` link** in any state.
- **Frontend `DualEntrySelfJoin.test.tsx`: 12 passed**, including `F4: no rendered link is EVER bare /retail/login` (asserts `a[href="/retail/login"]` is empty across preview/confirm/failed/miss; the only portal link is `/retail/login?w=<server-verified code>`). Failed/malformed/missing lookup renders no portal link. Post-registration handoff uses the server-returned portal code. `invitation_code`/`join_intent` travel in the request body only (never URL/query/storage/logs).
- **Mutation proof:** injecting `<a href="/retail/login">` into `RetailerJoinPage.tsx` made the F4 test RED; reverted.

## 6. P6 — F3 xfail Accounting

- xfail-marker **file set is byte-identical** between baseline `c5b66d26` and candidate `bf574cf` (9 files; same list). ⇒ `added=0 / removed=0`, the 15 xfailed nodes preserved.
- None of those 9 files are H2-A dual-entry / self-join / cross-tenant / invitation modules ⇒ **H2-A overlap = 0**.
- All H2-A authorization/security tests are ordinary GREEN (runtime: 19 + 46 = 65 H2-A backend tests passed, 0 failed). No skip/xfail/conditional assertion hides H2-A behavior.

## 7. P7 — Runtime Authenticity

- Fresh `PG16@15436 + Redis7@16379`, Alembic head **037** applied cleanly.
- **Contract D `TestRangeCap`: 8/8** (R1 red node + deterministic repro + old-assertion RED demonstration).
- **H2-A backend focused suites: 19 + 46 = 65 passed, 0 failed** (dual_entry_self_join / cross_tenant / u6f / route_authorization_policy). The route_authorization_policy xfails are expected (counted as xfailed, not failed).
- **Frontend focused: `DualEntrySelfJoin.test.tsx` 12/12** (and the broader H2-A frontend focused count of 30 — verified representative subset here; full vitest 385/385 is the candidate's CI artifact, not re-executed in this host to avoid infra-dependent spurious noise).
- Decisive PG-backed F1/F2 tests were **executed GREEN** locally; per the mandate this satisfies the runtime-authenticity requirement (the full 3675 two-stack reconciliation is the candidate's CI result, independently corroborated on the decisive H2-A/Contract-D subsets).

## 8. P8 — Security Regression

Inherited guarantees remain intact and were not weakened by the R2 delta:
- HMAC domain separation + constant-time `compare_digest` (join_intent.py unchanged);
- exactly one `invitation_code` OR `join_intent` (schema unchanged); email required (unchanged);
- public requests do not inherit `Authorization` (public_join.py unchanged path);
- no credential in query/storage/log/toast (verified); pending tenant user `is_active=False` until setup (unchanged);
- tenant-scoped deactivation (`retailers:deactivate` present, unchanged); no manual wholesaler approval added (unchanged).
- The R2 source changes (`public_join.py`, `retailer_provisioning_service.py`) **strengthen** the active-wholesaler fail-closed contract; they do not relax any guarantee.

## 9. P9 — Quality

- `git diff --check 78f88875..bf574cf` → clean (exit 0).
- `py_compile` of all changed `.py` — verified implicitly by successful pytest import/execution of every changed module (Contract D, dual-entry self-join, public_join, retailer_provisioning_service all imported and ran).
- Scoped secret scan of R2 source: no hardcoded secrets/passwords/keys (SECRET_KEY sourced via `get_settings()`).
- Strict UTF-8 / no BOM: raw-blob BOM scan of all 8 R2 delta files → **bom=0**.
- GitNexus: object store consistent at `bf574cf`; exact scope reconciled (8 / 41 / 40-with-exclusion).
- Worktree cleanliness: candidate tree clean after all mutations reverted.
- **Findings accounting gap = 0** (prior F1–F4 resolved; no new defects).

## 10. Prior R1 Findings — Closure

| R1 ID | Title | R2 Outcome |
|---|---|---|
| F1 (P1) | Contract D red node | RESOLVED — deterministic repro + GREEN; ledger retracts random-UUID claim (§3) |
| F2 (P2) | Active-wholesaler fail-closed | RESOLVED — guard + runtime 19/19 + mutation RED (§4) |
| F3 (P3) | xfail accounting | RESOLVED — set identical baseline↔candidate, H2-A-clean (§6) |
| F4 (P3) | No bare /retail/login | RESOLVED — frontend 12/12 + mutation RED (§5) |

## 11. Instructions Compliance

- Did **not** modify candidate/source/protected refs. Mutations (F2 guard, F4 link) were performed in a throwaway runtime worktree and reverted; the committed candidate is untouched.
- Pushed **only** the two-file Kilo report branch; verified local == remote.
- No Playwright, merge, deployment, H2-B, pricing, or barcode activity performed.
