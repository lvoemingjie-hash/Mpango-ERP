# DC12R1-H7-R14-V2 — Lubuntu Native Setup and Zero-Red Final Gate

**Date:** 2026-08-13 | **Host:** Lubuntu (Linux x86_64, Ubuntu 24.04) | **Verdict: STOP_AND_REPORT_CTO**

## Verdict summary

**Phase 1 STOP on re-issue** — the source branch has moved beyond the frozen
candidate. The original run (documented below) reached Phase 3 and STOPped on
a source-side defect in candidate `b2b08ab0`.

### Re-run attempt (same task, identical spec)

The same gate task was re-issued with the identical specification and the same
frozen candidate SHA `b2b08ab0`. Phase 1.2 requires `source branch = b2b08ab0`,
but the source branch `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12`
has moved to `fd7727f83e30338ccabcf5cb459a093a0a766e05` ("DC-12R1-H7-R15-R4-R1:
current-truth documentation correction (NO PASS)"). Per Phase 1.7 "STOP on any
mismatch," this re-run halts at Phase 1.

The new tip `fd7727f8` is 5 commits ahead of `b2b08ab0` (R15-R1 through
R15-R4-R1). The R15 setup.sh changes resolve the exact R14 defect reported
below: setup.sh now exports BOTH `DATABASE_URL` and `REPORTING_USER_PASSWORD`
from `.env` before `alembic upgrade head`, and unsets
`REPORTING_USER_PASSWORD` before tenant bootstrap. **Recommendation:** update
the task spec to reference `fd7727f8` as the frozen candidate for an R15 gate
re-run.

### Original run result (candidate b2b08ab0)

The R14 connection-context fix (exporting `DATABASE_URL` from `backend/.env`
before `alembic upgrade head`) successfully eliminated the R13 alembic.ini
fallback defect — Alembic connected to the project-isolated PostgreSQL on
`127.0.0.1:55436` and ran migrations 001–010. However, a **new source-side
defect** was exposed at migration `011_s6_p_reporting_role`: setup.sh exports
only `DATABASE_URL` from `.env` and omits `REPORTING_USER_PASSWORD`, which
migration 011 requires from the process environment. `alembic upgrade head`
exited 1 at `setup.sh:122`.

Per hard rule "Any failure in run 1 requires STOP" → Phases 3-run2 … 10
halted.

## 1. Phase 1 — Proof gate (ALL PASS)

| Proof | Result |
|---|---|
| Protected baseline SHA | `a6ef3aac0ab03615e9d70e08e504b9858baf61c5` = commit ✓ |
| Frozen R14 candidate SHA | `b2b08ab01b072b7296e5c38dafda5ecfae76f9ad` = commit "DC-12R1-H7-R14: native Alembic connection context closure (NO PASS)" ✓ |
| Direct parent R13 | `git rev-list --parents -n1 b2b08ab0` → parent = `5a27e56ddcd1dff79b9cba780e34cdd5b71bdfe7` ✓ |
| Accepted Kilo R14 review | `5c91eb2e80f15b00fa51e2bcee3f7d031b19eca8` = commit ✓ |
| Source branch tip | `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12` = `b2b08ab0` ✓ |
| Baseline ancestry | `git merge-base --is-ancestor a6ef3aac b2b08ab0` → ancestor ✓ |
| Exact R14 five-file delta (`5a27e56d..b2b08ab0`) | (1) `ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md` (2) `backend/scripts/setup.sh` (3) `backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py` (4) `docs/ai/CTO_CURRENT_OPS.md` (5) `docs/ai/PROJECT.md` — count = 5 ✓ |
| Forbidden paths byte-identical R13→R14 (blob-SHA equality) | `backend/scripts/setup_preflight.py` = blob `76ead580…` ✓; `backend/tests/test_dc12r1_h7_setup_preflight.py` = blob `e79328ce…` ✓; `docker-compose.yml` = blob `2cc2dd57…` ✓ |
| Clean detached checkout | `git checkout --detach b2b08ab0`, `git status --porcelain` empty ✓ |

## 2. Phase 2 — Isolated native environment (PASS)

- **Host-owner running container set BEFORE work** (9 containers, recorded):
  `dc2t0c_redis`, `dc2t0c_postgres` (dc2t0c_independent_worktree); `mpango_postgres`, `mpango_redis` (validation-target); `mpango_prod_gateway/backend/postgres/redis/frontend` (mpango_staging_rehearsal) — all Up 3 days (healthy).
- **Unique project name:** `h7_r14_v2_cf957a4d`.
- **Loopback ports (verified free):** PostgreSQL `127.0.0.1:55436`, Redis `127.0.0.1:56384` (avoided occupied 5432/6379).
- **Python venv:** 3.12.3 at gate dir `venv/`.
- **Compose implementation:** Docker Compose **v2.32.4** — official GitHub release binary `docker-compose-linux-x86_64` (statically-linked Go ELF, 64,694,701 bytes), installed as task-owned CLI plugin `~/.docker/cli-plugins/docker-compose`. `docker compose version` → `Docker Compose version v2.32.4`. No fake executables.
- **backend/.env** (mode 600, ASCII, LF, 36 lines, no CHANGE_ME): DATABASE_URL uses `127.0.0.1:55436`; REDIS_URL uses `127.0.0.1:56384`; POSTGRES_USER/PASSWORD/DB match DATABASE_URL parts; POSTGRES_PUBLISHED_PORT=55436; REDIS_PUBLISHED_PORT=56384; strong SECRET_KEY (64 chars); CORS_ORIGINS valid JSON list; EMAIL_DELIVERY_MODE=dev_sink; REPORTING_USER_PASSWORD present (31 chars). `.env` sha256: `fb9ad25a3c860e57cf8e8e05e306aeccd08486c628f8ba380694c2ce52ae7199`.
- DATABASE_URL and REDIS_URL cleared from shell. `.env` not sourced/exported.
- Compose config `--quiet` exit 0. Preflight initial mode: `OK`.

## 3. Phase 3 — Native setup run 1 (FAIL at setup.sh:122)

Exact command (repo root, venv active):

```
COMPOSE_PROJECT_NAME=h7_r14_v2_cf957a4d \
DEFAULT_TENANT_SCHEMA=t_h7_r14_v2 \
bash backend/scripts/setup.sh
```

**Run transcript highlights:**

1. Preflight: `OK` ✓
2. Docker services: `h7_r14_v2_cf957a4d-postgres-1` and `…-redis-1` created/started (healthy) ✓
3. `pip install -r requirements.txt`: all packages installed successfully ✓
4. Post-install preflight: `OK` ✓
5. `alembic upgrade head`: migrations **001–010 ran successfully** on the isolated database, proving the R14 connection-context fix works (DATABASE_URL exported from `.env` via `setup_preflight.parse_env_file`). **Migration 011** (`011_s6_p_reporting_role.py:44`) raised:

   ```
   RuntimeError: REPORTING_USER_PASSWORD environment variable must be set before running this migration
   ```

6. ERR trap: `Setup stopped at line 122 (exit status 1)`. **Exit 1. No "Setup complete!".**

**Root cause (source-side):** setup.sh (R14) exports only `DATABASE_URL` from `backend/.env` before `alembic upgrade head` (lines 109–119). It does NOT export `REPORTING_USER_PASSWORD`, which migration 011 (`011_s6_p_reporting_role.py:42-45`) requires from `os.environ.get("REPORTING_USER_PASSWORD")`. The value IS present in `backend/.env` (verified via `parse_env_file`), but it is never loaded into the process environment. `alembic/env.py` does not call `load_dotenv()`, and setup.sh's `parse_env_file` extraction is scoped to DATABASE_URL only.

**Connection-context proof:**

- Migrations 001–010 executed SQL (CREATE TABLE, CREATE INDEX, etc.) and completed successfully. If Alembic had connected to `127.0.0.1:5432` (host-owner), it would have failed with `InvalidPasswordError` at migration 001 (as in R13). The successful execution of 10 migrations proves the connection reached the project-isolated database at `127.0.0.1:55436`.
- No connection attempt to `127.0.0.1:5432`: the R14 fix exports `DATABASE_URL` from `.env` (port 55436) before `alembic upgrade head`. `alembic/env.py:33` reads `os.environ.get("DATABASE_URL")`, which is now set to the `.env` value (55436). No alembic.ini fallback path was exercised.

**Database proof (partial — migration halted at 011):**

- `alembic heads` (DB-independent): sole head `037_payment_declarations_schema` (down_revision `036`) ✓.
- Migrations 001–010 applied to the isolated database; migration 011 NOT applied.
- `public.alembic_version` would contain `010_s5_5_ledger_hardening` (last successful migration), NOT sole head 037.
- Tenant schema `t_h7_r14_v2`: NOT created (bootstrap did not run — alembic failed first).
- Migration-037 objects (payment_declarations, receipt_sequences, payments.receipt_number): NOT created (migration 037 not reached).

**Runtime package proof (all verified from pip freeze):**

`bcrypt==4.0.1`, `cryptography==46.0.5`, `openpyxl==3.1.5`, `et_xmlfile==2.0.0`, `passlib==1.7.4` ✓

## 4. Phases 4–8 — NOT EXECUTED (hard STOP at Phase 3)

Run 2 idempotency, H7 gates (262 tests), Hypothesis seeded+unseeded, focused bundle, quality gates: all halted per hard-stop rule. No results exist.

## 5. Exact failed/error accounting

| Item | Value |
|---|---|
| Failed phase | Phase 3 (native setup run 1) |
| Exact failed node | `backend/scripts/setup.sh:122` — `alembic upgrade head` |
| Error | `RuntimeError: REPORTING_USER_PASSWORD environment variable must be set before running this migration` |
| Error origin | `backend/alembic/versions/011_s6_p_reporting_role.py:44` |
| Trap output | `Setup stopped at line 122 (exit status 1). Partial local artifacts may exist.` |
| Exit code | 1 |
| Source-side cause | setup.sh exports only `DATABASE_URL` from `.env` (R14 lines 109–119); `REPORTING_USER_PASSWORD` (present in `.env`, required by migration 011) is NOT exported; `env.py` does not load dotenv |
| Classification | **Source-side deterministic failure** — the R14 connection-context fix is incomplete; it resolves DATABASE_URL but omits REPORTING_USER_PASSWORD needed by migration 011 |
| R14 connection fix status | **WORKING** — alembic connected to isolated port 55436 and ran migrations 001–010 (R13 fallback to 5432 eliminated) |

## 6. Secret hygiene

- No credential printed to stdout/stderr in run 1 log. Scanned every secret-bearing `.env` value against `/tmp/opencode/r14-setup-run1.log` → **zero matches**.
- `backend/.env` (mode 600), venv, clone, Compose plugin, downloads and logs deleted in cleanup. This report contains no credential values.

## 7. Host-owner non-interference

- Before/after `docker ps` (ID+name+status): **byte-identical** (diff empty after cleanup). No host-owner container stopped/restarted/renamed/inspected/exec'd/removed.
- The failed alembic run connected only to the task-owned PostgreSQL (`127.0.0.1:55436`). No connection to host-owner port 5432 (proven by successful migrations 001–010 on the isolated database).

## 8. Cleanup and residue proof

1. `docker compose --env-file backend/.env -p h7_r14_v2_cf957a4d down -v --remove-orphans` — containers `h7_r14_v2_cf957a4d-postgres-1`/`-redis-1` removed; volumes `…_postgres_data`/`…_redis_data` removed; network `…_mpango_network` removed.
2. Removed: task-owned clone `/home/ivy/dc12r1-h7-r14-v2-gate` (repo+venv+`.env`), Compose plugin `~/.docker/cli-plugins/docker-compose`, downloads/logs (`/tmp/opencode/*`).
3. **Zero task-owned residue:** containers with `h7_r14_v2` prefix: 0; networks: 0; volumes: 0; gate directory gone; plugin gone.
4. **Host-owner set unchanged:** before==after (byte-identical).
5. **Refs unchanged:** source branch `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12` = `b2b08ab0` before and after (live `git ls-remote`); all four authoritative SHAs verified as immutable commits.

## 9. Kilo R14 review reference

Accepted Kilo R14 review SHA: `5c91eb2e80f15b00fa51e2bcee3f7d031b19eca8` — verified as commit in fresh clone during Phase 1.

## 10. Recommendation

The R14 fix correctly resolved the R13 alembic connection defect (DATABASE_URL
export from `.env` before `alembic upgrade head`). The new failure is
complementary: setup.sh must also export `REPORTING_USER_PASSWORD` from
`backend/.env` (or `env.py` must call `load_dotenv()`) so that migration 011
can complete. Alternatively, setup.sh could use `parse_env_file` to export all
migration-required env vars, not just DATABASE_URL. No local patch was applied
(prohibited). Re-run this gate only after an upstream fix round.

## 11. Verification

Report branch `reports/dc12r1-h7-r14-v2-lubuntu-native-zero-red-2026-08-13`; local and remote HEAD SHA identical (verified post-push).
