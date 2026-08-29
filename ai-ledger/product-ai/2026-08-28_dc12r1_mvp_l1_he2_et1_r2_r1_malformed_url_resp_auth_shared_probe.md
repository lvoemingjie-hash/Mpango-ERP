# DC-12R1-MVP-L1-HE2-ET1-R2-R1 — Malformed Redis URL, RESP AUTH and Shared-Probe Closure

- Date: 2026-08-28 (+08:00); Executor: Zcode
- Task: DC-12R1-MVP-L1-HE2-ET1-R2-R1
- Verification tier: V3_GOVERNANCE_AUTHORITY_SECURITY
- Claim ceiling: CANDIDATE_READY_FOR_KILO_REVIEW_ONLY
- Base: 30e3e48f9ebc707223e43734a0c4357346b6e2da
- Forbidden: no product source/dependencies/migrations, no protected refs,
  no merge re-execution, no Kilo start. Candidate readiness only.

## 1. Confirmed defects → forced fixes

- **A. `redis://127.0.0.1:notaport/15` raised a raw ValueError.** All
  URL/port/IPv6 parse failures now map to the fixed sanitized category
  `url_malformed` inside the shared module's `_parse_url`; out-of-range
  ports and malformed bracketed IPv6 included. Wrappers re-raise as the
  registered trap with `from None`, so no traceback text reaches any
  published surface (unit-proven over evidence + exception text).
- **B. percent-encoded credentials sent literally.** `unquote` on username
  and password; `urlsplit`'s EMPTY-STRING credentials (from `://:pwd@host`
  and `://user:@host`) normalize to absent so the AUTH shape is decided by
  genuinely present credentials.
- **C. ACL username ignored.** username+password → `AUTH <username>
  <password>`; username without password → fail closed
  (`auth_misconfigured`).
- **D. inline encoder injectable.** The shared module speaks formal RESP
  arrays of bulk strings (`*N` / `$len` framing) — credentials containing
  spaces, CR/LF, and non-ASCII travel as ONE binary-safe argument and
  cannot inject commands (unit-proven with a password embedding
  `\r\nINJECT007\r\nSET x y\r\né`; the URL layer additionally strips raw
  CR/LF, and the RESP layer keeps the percent-decoded bytes intact).
- **E. duplicated probe.** New shared stdlib module
  `harness-governance/validator/redis_authority.py` holds the ENTIRE live
  authority (URL parsing, RESP codec, connect/AUTH/PING/SELECT/DBSIZE,
  sentinel probe, category set). The runner and the child plugin each load
  it under the FIXED `sys.modules` key `et1_redis_authority` via a
  file-relative loader — both sides resolve to the SAME module object
  (asserted by test). The runner keeps thin TrapFired-translating
  delegators (`redis_live_check`, `eval_redis`); the child keeps the
  `_redis_recheck_problems` label wrapper. No protocol primitive exists in
  either consumer (source-asserted).
- **F. whole-file registry reformat.** `execution-traps.json` restored to
  the pre-R2 compact format (BASE 2582750d bytes) and re-edited
  surgically: exactly 8 changed lines, ALL inside the Redis trap block
  (evaluator `EVAL_REDIS_LIVE`, applies_to `runner.preflight` +
  `child.sessionstart`, live-probe required_evidence incl. RESP-array +
  shared-module + credential-never-published clauses, updated
  remediation). Diff verified: no other line moved.

Additional hardening: `rediss://` is REJECTED fail-closed
(`tls_unsupported_fail_closed`) — R2's wrap_socket path was never proven
against a real TLS deployment, so this round claims no unverified
support. The legacy evaluator name `EVAL_REDIS` is REMOVED from the
runner's and the validator's whitelists — the registry cannot roll back
to the pre-live URL-string semantics.

## 2. Sanitization contract

Fixed categories only: `url_absent / url_malformed / wrong_db /
auth_misconfigured / connect_failed / auth_failed / ping_failed /
select_failed / db_nonempty / sentinel_reachable /
tls_unsupported_fail_closed / protocol_error / ok`. Redis reply TEXT is
dropped at parse time (servers may echo request bytes); URL, host, port,
username, password never appear in evidence, proofs, logs, or exception
text (unit-proven including the port number and server address).

## 3. Tests

- `test_authority_runner_r2.py` (15, R2) — unchanged bodies; its
  FakeRedis upgraded to parse standard RESP arrays (bulk-string args)
  with an inline fallback, plus an exact-args recorder. All 15 still
  green.
- `test_authority_runner_r2r1.py` (14, new) — invalid port, out-of-range
  port, malformed IPv6, well-formed bracketed IPv6 NOT rejected as
  malformed, rediss fail-closed, username-without-password, exact percent
  decode (server-validated), ACL two-argument array (server-validated),
  CR/LF/space/non-ASCII injection resistance, protocol break
  (`ping_failed`), mid-session close (`auth_failed`/`protocol_error`),
  no-traceback/no-secret/no-host surface proof, runner-and-child
  same-module-object proof, no-duplicated-protocol source proof.

Suite: **145/145 OK** (131 prior + 14 new).

## 4. Mutations

`et1_r2_mutations.py` rewritten: R201–R205 retargeted onto the shared
module (the protocol moved; intents unchanged — connect deleted, PING
skipped, DBSIZE skipped, connection errors swallowed, child recheck
deleted) and five NEW defect mutations R211–R215 (inline encoder
restored with a CR/LF-injection probe, percent decode deleted,
username ignored, invalid-port escape, child bypasses the shared probe).
Child probes now exercise the recheck path with a configured unreachable
URL (an empty URL would early-return before the patched line). Gate:
**76 RED / 9 GREEN**, pristine control RG-C01 green, tree byte-identical.

## 5. Live cases (fresh throwaway PG16 + redis7)

`run_e2e_redis_cases.py` gains **RL7 invalid port** (`:notaport` → rc 14
VOID, sentinel 0, no traceback in output). Full set: RL1 green fresh
DB15, RL2 wrong db, RL7 invalid port, RL4 db15 non-empty, RL5
preflight-then-gone (child fail-closed with recorded `redis:*` problems,
command launches = 0), RL3 unreachable, RL6 sentinel-26379 reachable —
7/7 live, plus the 8-case authority core chain 8/8 on the same fresh
stack.

## 6. Final gate table

- 145/145 unittests; self-test OK.
- Mutation gate 76 RED / 9 GREEN, tree integrity OK.
- structural validator exit 0; release validator exit 3 (pre-existing
  P0/P1 debt only).
- `git diff --check` clean; detect-secrets vs baseline NONE (baseline
  snapshot-protected and byte-restored); strict UTF-8/no-BOM/no-NUL/
  no-U+FFFD/no-raw-0x97 over changed files clean.
- Dual autocrlf: LF and re-smudged CRLF checkouts both green
  (self-test + 145 tests + 76/9 gate + 7/7 + 8/8); restore proven
  byte-identical.
- GitNexus: pre-edit `impact` and post-commit `detect_changes` BOTH
  attempted. `impact` fails closed on the index/CLI storage-version skew
  (index 42 vs CLI 40 — same as R1/R2; re-analysis would downgrade a
  shared index). `detect_changes` does not exist as a subcommand in the
  installed CLI (v—; `gitnexus --help` lists setup/analyze/index/serve/
  mcp/list/status/clean only). `gitnexus status` confirms the index is
  stale at this commit. DISCLOSED, not silently skipped; consumer-census
  substitute documented.
- All task resources removed: fresh containers + volumes deleted, ports
  freed, CRLF worktree removed.

## 7. Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R2_R1_CANDIDATE_READY_FOR_KILO_REVIEW**

STOP. No Kilo start, no merge re-execution.
