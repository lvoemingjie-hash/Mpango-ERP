# DC12R1-H7-R13-V2 — Lubuntu Native Setup and Zero-Red Final Gate

**Date:** 2026-08-13 | **Host:** Lubuntu (Linux x86_64, Ubuntu 24.04 docker.io) | **Verdict: STOP_AND_REPORT_CTO**

## Verdict summary

Native setup failed deterministically at `backend/scripts/setup.sh:110` (`alembic upgrade head`), exit 1, first (real) run.
Per hard rule "Any native setup failure is a hard STOP" → Phases 3-run2 … 8 halted. Exact failed/error accounting in §6.

## 1. Phase 1 — Proof gate (ALL PASS)

| Proof | Result |
|---|---|
| Protected baseline SHA | `a6ef3aac0ab03615e9d70e08e504b9858baf61c5` = commit "Merge DC-12R1 MVP R0-R1 readiness debt closure" ✓ |
| Frozen candidate SHA | `5a27e56ddcd1dff79b9cba780e34cdd5b71bdfe7` = commit "DC-12R1-H7-R13: standalone harness exec-bit closure (NO PASS)" ✓ |
| Corrected Kilo report SHA | `cf04a51fc170b38c91a853b175ef6e0aaf424c63` = commit "docs(review): correct DC-12R1 H7 R13 V1 Kilo review evidence" ✓ |
| Baseline ancestry | `git merge-base --is-ancestor a6ef3aac 5a27e56d` → ancestor ✓ |
| R13 direct parent | `git rev-list --parents -n1 5a27e56d` → parent = `db166b773389604d49ca2682a8e24ec715f3e1f7` ("DC-12R1-H7-R12: standalone Compose probe repair (NO PASS)") ✓ |
| R13 delta exactly 4 files | `M ai-ledger/product-ai/2026-08-12_dc12r1_h7_bcrypt_dependency_manifest_reconciliation.md`, `M backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py`, `M docs/ai/CTO_CURRENT_OPS.md`, `M docs/ai/PROJECT.md` (count = 4) ✓ |
| Quartet byte-identical (db166b77 ↔ 5a27e56d, blob-SHA equality) | `backend/scripts/setup.sh` = blob `f1acbcb6…` ✓; `backend/scripts/setup_preflight.py` = blob `76ead580…` ✓; `backend/tests/test_dc12r1_h7_setup_preflight.py` = blob `e79328ce…` ✓; `docker-compose.yml` = blob `2cc2dd57…` ✓ |
| Fresh disposable full clone | `git clone` from canonical remote (HTTP/1.1), checkout detached at `5a27e56d`, `git status --porcelain` empty ✓ |
| Source branch ref before work | `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12` → `5a27e56d…` (recorded) ✓ |

## 2. Phase 2 — Host isolation (PASS)

- Host-owner running container set recorded BEFORE work (9 containers, ID+name):
  `dc2t0c_redis/dc2t0c_postgres` (project dc2t0c_independent_worktree), `mpango_postgres/mpango_redis` (project validation-target), `mpango_prod_gateway/backend/postgres/redis/frontend` (project mpango_staging_rehearsal) — all Up 3 days (healthy).
- **Unique project:** `COMPOSE_PROJECT_NAME=h7_r13_v2_6ec8f2f4`.
- **Loopback ports (verified free at run time):** PostgreSQL `127.0.0.1:55435`, Redis `127.0.0.1:56383` (avoided occupied 5432/6379/54432/55432/56379).
- Task-owned venv: Python 3.12.3 at gate dir `venv/` (activated for run; setup's `python`/`pip`/`alembic` resolve to it).
- **Compose implementation selected:** real Docker Compose **v2.32.4** — official GitHub release binary `docker-compose-linux-x86_64` (statically-linked Go ELF, 64,694,701 bytes), installed as task-owned CLI plugin `~/.docker/cli-plugins/docker-compose`; host had no Compose v2 beforehand. No fake executables anywhere. `docker compose version` → `Docker Compose version v2.32.4`. Host `docker-compose` v1 (python) unused.
- `backend/.env` generated with task-only credentials (chmod 600, LF, UTF-8); DATABASE_URL=`postgresql://mpango:<task-pw>@127.0.0.1:55435/mpango_erp`; REDIS_URL=`redis://127.0.0.1:56383/0`; POSTGRES_USER/PASSWORD/DB exactly match URL parts; POSTGRES_PUBLISHED_PORT=55435; REDIS_PUBLISHED_PORT=56383; strong SECRET_KEY (48B urlsafe); MPANGO_ENV=test; no CHANGE_ME placeholders. Credential values never printed/logged/committed (see §7). `.env` SHA history (operator fix steps, see §3): `6dbaf5d4…` → `10b6b7bb…` → `08c3f8fc…`.
- `backend/.env` was **not** sourced or exported; `setup.sh` consumes it natively via `COMPOSE=(docker compose --env-file "$REPO_ROOT/backend/.env")` (setup.sh lines 35–48).
- Preflight (initial mode) via setup's own pipeline: `OK` (exit 0). `docker compose config --format json` exit 0.

## 3. Phase 3 — Native setup

Exact command run (repository root, venv active):

```
COMPOSE_PROJECT_NAME=h7_r13_v2_6ec8f2f4 DEFAULT_TENANT_SCHEMA=t_h7_r13_v2 bash backend/scripts/setup.sh
```

Run history (all disclosed):

1. **Void run (operator .env error):** `CORS_ORIGINS` generated in comma-separated form; pydantic-settings requires JSON list (per backend/.env.example:70). Failed at post-install preflight (`Could not import core.config.settings` — masked by setup_preflight.py; direct import showed `error parsing value for field "CORS_ORIGINS"`). No candidate defect. .env fixed → SHA `10b6b7bb…`.
2. **Void run (operator .env error):** `EMAIL_DELIVERY_MODE=console` is not a valid Literal (`dev_sink`|`smtp`); import failed `Input should be 'dev_sink' or 'smtp'`. No candidate defect. .env fixed → SHA `08c3f8fc…`; `from core.config import settings` → **IMPORT OK**.
3. **FIRST (REAL) RUN — THE FAILURE:**
   - Preflight OK → compose up OK → both services created/started (`h7_r13_v2_6ec8f2f4-postgres-1`, `…-redis-1`, healthy, published `127.0.0.1:55435→5432/tcp` and `127.0.0.1:56383→6379/tcp`) → frontend/.env created → pip install OK (all pinned versions, incl. bcrypt 4.0.1, cryptography 46.0.5, openpyxl 3.1.5, et_xmlfile 2.0.0, passlib 1.7.4) → post-install preflight OK → **`alembic upgrade head` (line 110) FAILED**:
     - `asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "mpango"`
     - trap: `Setup stopped at line 110 (exit status 1). Partial local artifacts may exist.`
     - **exit 1. No "Setup complete!".**
   - Root cause (source-side, deterministic): `backend/alembic.ini:56` hardcodes `sqlalchemy.url = postgresql+asyncpg://mpango:<committed-default-password>@127.0.0.1:5432/mpango_erp`. `backend/alembic/env.py:33-38` uses `os.environ.get("DATABASE_URL")` if present, otherwise the ini value; it never reads backend/.env (verified: no dotenv load in env.py). Under the task-mandated invocation, DATABASE_URL is NOT in the process environment (setup.sh exports it only at line 122, after the alembic step, for bootstrap; the task forbids exporting backend/.env). Therefore alembic connected to `127.0.0.1:5432` — the **host-owner** postgres listener (`0.0.0.0:5432`/`[::]:5432` bound by validation-target's mpango_postgres, verified via `ss -ltn`) — with the committed default password, which that server rejected (failed before any state change; no data touched).
   - Direct sanity checks: asyncpg connect with the .env URL to `127.0.0.1:55435` succeeds ("PostgreSQL 15.17 …"), confirming the isolated server and .env credentials are valid; the failing path is purely the alembic.ini fallback URL.
   - DB-independent migration evidence: `alembic heads` (version-tree only) → sole head `037_payment_declarations_schema`; revision `037_…` down_revision `036_retailer_mvp_identity`. Migrations were NOT applied to any database; tenant schema `t_h7_r13_v2` was NOT bootstrapped.
4. **SECOND run (idempotence):** NOT EXECUTED — hard-stop rule triggered by run 1 failure.

## 4. Phases 4–7 — pytest gates, Hypothesis, focused bundle, quality

NOT EXECUTED (hard STOP at Phase 3). No pytest/Hypothesis/bundle results exist to report; no result can be claimed. `bash -n` equivalently proven by full script execution through line 110.

## 5. Host-owner non-interference (PASS)

- Before/after `docker ps` (ID+name+status) sets are **byte-identical** (diff empty). No host-owner container stopped/restarted/renamed/inspected/exec'd/removed.
- The one network-level interaction: the failed alembic attempt reached `127.0.0.1:5432` (host-owner listener) and was rejected at password authentication — no state change, no query executed.

## 6. Exact failed/error accounting

| Item | Value |
|---|---|
| Failed phase | Phase 3 (native setup), first real run |
| Exact failed node | `backend/scripts/setup.sh:110` — `alembic upgrade head` |
| Error | `asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "mpango"` |
| Trap output | `Setup stopped at line 110 (exit status 1). Partial local artifacts may exist.` |
| Exit code | 1 |
| Source-side cause | `backend/alembic.ini:56` hardcoded sqlalchemy.url (port 5432, committed default password); `alembic/env.py` only honors DATABASE_URL from process env, which the mandated invocation leaves unset (setup.sh:110 runs before the line-122 export; task forbids exporting backend/.env) |
| Environment interaction | 127.0.0.1:5432 is occupied by host-owner listener (validation-target mpango_postgres, 0.0.0.0:5432 + [::]:5432) |
| Classification | **Source-side deterministic failure** (would fail identically with no host-owner postgres present — wrong port/password cannot reach the isolated project database) |
| Phase 3 second run / Phases 4–8 | NOT EXECUTED (hard STOP rule) |

## 7. Secret hygiene

- No credential printed to stdout/stderr in any run. `setup-r13-run1.log` scanned against every long `.env` value → **no leaks** (only non-secret `APP_NAME`/"Mpango ERP" string matched a naive scan; credential-key scan clean).
- `backend/.env` (chmod 600), venv, clone, plugin, logs and downloads deleted in cleanup. This report contains no credential values (the committed default password in alembic.ini is deliberately not reproduced).

## 8. Cleanup & residue proof (Phase 8 executed in STOP mode)

1. `docker compose --env-file backend/.env -p h7_r13_v2_6ec8f2f4 down -v --remove-orphans` — containers `h7_r13_v2_6ec8f2f4-postgres-1`/`-redis-1` removed; volumes `…_postgres_data`/`…_redis_data` removed; network `…_mpango_network` removed.
2. Removed task-owned clone `/home/ivy/dc12r1-h7-r13-v2-gate` (repo+venv+`.env`), Compose plugin `~/.docker/cli-plugins/docker-compose`, downloads/logs (`/tmp/opencode/*`).
3. **Zero task-owned residue:** containers with `h7_r13_v2` prefix: 0; networks: 0; volumes: 0; gate directory gone; plugin gone.
4. **Host-owner set unchanged:** before==after (byte-identical).
5. **Refs unchanged:** source branch `origin/zcode/dc12r1-h7-bcrypt-manifest-reconciliation-2026-08-12` = `5a27e56d…` before and after (live `git ls-remote`); candidate HEAD remained `5a27e56d…`; baseline/kilo commits immutable (content-addressed).

## 9. Required-package versions (observed in task venv after pip install)

`bcrypt==4.0.1`, `cryptography==46.0.5`, `openpyxl==3.1.5`, `et_xmlfile==2.0.0`, `passlib==1.7.4` — all installed exactly as pinned in `backend/requirements.txt`.

## 10. Recommendation

The candidate's own native setup cannot reach its required end-state under the mandated invocation: `alembic upgrade head` cannot address the project-isolated database because `alembic.ini` hardcodes a 5432/committed-password URL and `env.py` never consults `backend/.env`. Upstream must either (a) load DATABASE_URL from `backend/.env` in `alembic/env.py` (or export it in `setup.sh` before the alembic step), or (b) make `alembic.ini` use an env-substituted placeholder. Re-run of this gate should occur only after an upstream fix round; no local patch was applied (prohibited).

## 11. Verification

Report branch `reports/dc12r1-h7-r13-v2-lubuntu-native-zero-red-2026-08-13`; local and remote HEAD SHA identical (verified post-push).
