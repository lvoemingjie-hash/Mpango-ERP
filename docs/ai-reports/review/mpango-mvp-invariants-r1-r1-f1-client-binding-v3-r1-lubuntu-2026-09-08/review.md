# F1 Lubuntu V3-R1 Stop Report

Status: `STOP_AND_REPORT_CTO_MPANGO_MVP_INVARIANTS_R1_R1_F1_LUBUNTU_V3_R1`
Date: 2026-09-08

## Identity
- Candidate: `76ab895fe6e00c91af09cef7b938be074734b461`
- Candidate parent: `69495712ad408000317d53e9e8e275bc35f5bf78`
- Product base: `a516d2b3257f782ce068e71e8730c05541f08931`
- Product target: `bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f`
- Kilo review: `a83a78275675223f9137e91257851bfce228ee00`
- Prior VOID report: `4fcaf4de3d277e68489d32de1a47d7eda1d7ef20`

## Preflight
`PASS`

Fresh task-owned PostgreSQL 16 and Redis 7 containers were created for this invocation, with:
- owner label `zcode-mvp-invariants-r1-r1-v3-r1`
- PostgreSQL published on `127.0.0.1:60321`
- Redis published on `127.0.0.1:60322`
- runtime PostgreSQL role `mpango_f1_v3r1` verified as `rolcanlogin=true`, `rolsuper=false`, `rolcreaterole=false`, `rolcreatedb=false`, `rolreplication=false`
- separate bootstrap superuser `bootstrap` verified as `rolsuper=true`
- Redis DB `15` reachable and empty at preflight
- real `JwtAuthStrategy` verified for `MPANGO_ENV=staging`

Evidence:
- `evidence/preflight.json` SHA-256 `38a2f1938b7485258804d764f51833f253d9695c4f26ad44799e45556527e938`
- `evidence/manifests/runtime_evidence_manifest.json` SHA-256 `fcda5d5c920296a511995af8fa575679737c78ca9ebd8778bfca53f4358bbcee`

## Matrix Results

### A. Redis reachable + ownership declared
`ERROR`

Command:
`pytest tests/test_mpango_invariants_r0_r1_guards.py tests/test_mpango_mvp_invariants_r0_concurrency.py tests/test_mpango_mvp_invariants_r0_revocation.py --no-header -q -rfE`

Outcome:
- `51 passed, 22 errors, 2 warnings`
- guards file passed
- concurrency and revocation were blocked at `r0_task_database` setup

First authentic error:
- `GUARD_REFUSED_MIGRATION: alembic upgrade head failed against the declared task target`
- root cause: migration `011_s6_p_reporting_role` attempted `CREATE ROLE reporting_role` and failed with `permission denied to create role`
- this is a bootstrap/migration privilege mismatch, not a product RED

### B. Redis unreachable
`NOT_RUN`

### C. Redis reachable but ownership undeclared
`NOT_RUN`

## Path Accounting
- `a516d2b3257f782ce068e71e8730c05541f08931..69495712ad408000317d53e9e8e275bc35f5bf78`: 19 paths
- `69495712ad408000317d53e9e8e275bc35f5bf78..76ab895fe6e00c91af09cef7b938be074734b461`: 4 paths
- cumulative window sum: 23 paths
- net unique candidate delta: 20 paths
- report branch additions: 2 paths

## Secrets Scan
- Canary file was detected by the real `detect-secrets-hook` 1.5.0: `rc=1`
- candidate delta plus report files scan: `rc=0`
- `.secrets.baseline` SHA-256 before and after: `c8f3aa245b94d4f4b0242ae8c5a64fbf1f4716483baae91ad65f78735c0290e6`

## Required Fields

### CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS
`NOT_RUN_DUE_TO_STOP`

The touched coverage surface for this task remains:
- `backend/tests/mpango_invariants_r0_support.py`
- `backend/tests/test_mpango_invariants_r0_r1_guards.py`
- `backend/tests/test_mpango_mvp_invariants_r0_revocation.py`

### CODE_PATH_TO_TEST_MATRIX
`NOT_RUN_DUE_TO_STOP`

Observed matrix-A coverage before setup failure:
- guard helper paths: PASS
- concurrency setup path: ERROR at migration initialization
- revocation setup path: ERROR at migration initialization

### NEGATIVE_AND_FAILURE_PATHS
- migration 011 requires privileged role creation that the runtime role does not have
- the focused suite never reached the concurrency or revocation bodies
- matrix B was not started
- matrix C was not started

### FALSIFICATION_RESULT
`NOT_RUN_THIS_ROUND`

### UNCOVERED_NEW_PATHS
- all runtime paths after `r0_task_database` setup remain uncovered in this round
- matrix B and matrix C remain uncovered

### FULL_SUITE_RESULT
`NOT_RUN_THIS_ROUND`

### BROWSER_RUNTIME
`NOT_RUN_THIS_ROUND`

### GitNexus
`NOT_AVAILABLE`

`gitnexus` is not on PATH in this workspace, so no GitNexus analyze/status result could be produced.

## Evidence Index
The full raw evidence set is listed in:
- `evidence/manifests/runtime_evidence_manifest.json` SHA-256 `fcda5d5c920296a511995af8fa575679737c78ca9ebd8778bfca53f4358bbcee`
- `evidence/manifests/path_manifest.json` SHA-256 `5e049cafe43c5bfe95c1c24c4441da1ec0d4da48c27390ff58d9fc31123eacbd`
- `evidence/logs/detect_secrets_canary.log` SHA-256 `879a73241ce8a1c6d37d6fae93ff6b18881c20bd8b5ed5ca4b16cad39e7c3fc2`
- `evidence/logs/detect_secrets_scan.log` SHA-256 `7057276e350a9ebdbf7d2ad574934ff071d69659dbb94e2f853c90c9bae3a0d3`
- `evidence/logs/baseline_sha_before_after.txt` SHA-256 `40a84e6720e32652d407775eb936ecf47bbb197590a86d2e774193f325139fb4`
