# DC12R1-H7-R10V2 — Native Staging Setup Gate — Lubuntu host

**Date:** 2026-08-13 | **Host:** Lubuntu (Linux, x86_64) | **Result: HARD FAIL → STOP_AND_REPORT_CTO**

**Candidate commit:** `6be4c27906eb99ce693d9515152725167dba3c5b` (clean checkout, branch `dc12r1-h7-r10-v2-gate`, no local modifications — verified `git status --short` empty at gate start).

## 1. Task summary

- Phase 1: Static review of candidate (LF/UTF-8, `bash -n`, git integrity) — **PASS**
- Phase 2: Prepare task-owned resources (venv, `backend/.env` test credentials, Docker Compose v2) + preflight validation — **PASS** (preflight initial mode: `OK`)
- Phase 3: Run native setup `bash backend/scripts/setup.sh` — **FAIL** at line 73, exit 1
- Phase 4–5 (service verification, integration): **NOT EXECUTED** — gate halted at Phase 3 per rules ("Any native setup failure is a hard STOP. Do not patch on Lubuntu.")
- Phase 6–7: Residue cleanup (performed) + this report (branch `reports/dc12r1-h7-r10-v2-lubuntu-native-zero-red-2026-08-13`)

## 2. Environment facts (evidence)

| Item | Finding |
|---|---|
| Docker CLI | `Docker version 29.1.3` (docker.io, Ubuntu pkg) |
| Compose v2 | Absent from host; acquired by task: GitHub release `docker-compose-linux-x86_64` v2.32.4 installed to `~/.docker/cli-plugins/docker-compose` → `Docker Compose version v2.32.4` |
| Host-owner containers (name conflict) | `mpango_postgres` (postgres:15-alpine) **Up 3 days, healthy**, compose project `validation-target`; `mpango_redis` (redis) **Up 3 days, healthy**, project `validation-target`. Also `mpango_prod_*` set (project `mpango_staging_rehearsal`), Up 3 days, healthy |
| Host port bindings | `0.0.0.0:5432`, `0.0.0.0:6379` (plus `[::]:5432/6379`) already bound by docker-proxy of host-owner containers; `127.0.0.1:55432`, `127.0.0.1:56379` occupied |
| Python | Host has `python3` (3.12.3) only; `python` provided via task venv (`.venv`) |
| Candidate source | Repo cloned by task to `/home/ivy/dc12r1-h7-r10v2-gate/repo`; commit `6be4c279`; working tree clean |

## 3. Phase 1 — static review (PASS)

- `setup.sh`: 130 lines, LF (0 CRLF), UTF-8, `bash -n` OK. `set -Eeuo pipefail` + ERR trap (lines 3, 10).
- `setup_preflight.py`: 297 lines, LF, UTF-8, stdlib-only.
- Git integrity: clean checkout at `6be4c27906eb99ce693d9515152725167dba3c5b`.

## 4. Phase 2 — resource preparation & preflight (PASS)

- Created `backend/.env` (34 keys, 0 CRLF, utf-8; `sha256 e590815a5ecfef210ecade492a9496c4c227139df3e706d7a044b918b945d96c`; chmod 600; contains no `CHANGE_ME` placeholders). DATABASE_URL/REDIS_URL loopback-only, ports matching Compose published ports.
- Created repo-local venv (Python 3.12.3).
- Compose render: `docker compose config --format json` — exit 0; services `backend, frontend, gateway, postgres, redis`; postgres/redis port entries rendered as object form `{mode: ingress, host_ip: 127.0.0.1, target: 5432/6379, published: "5432"/"6379", protocol: tcp}` (satisfies `setup_preflight.py` object-form contract).
- Preflight initial mode (pipeline exactly as `setup.sh` line 56):
  `docker compose config --format json | python backend/scripts/setup_preflight.py --env-file backend/.env` → **`OK`** (exit 0).

## 5. Phase 3 — native setup runs (ALL RUNS, verbatim)

### Run 1 (void — operator invocation error, disclosed for completeness)
Environment not exported (task-operator mistake): Compose interpolation missing `POSTGRES_PASSWORD`.
Output: `docker-compose configuration is invalid.` then `exit 1` (setup.sh lines 49–51; `if`-guarded, no trap message). Confirms setup.sh fails closed when required env is absent. Corrected by exporting `backend/.env` into the process environment (required by the design: `setup_preflight.py` compares process env vs file env, lines 216–221).

### Run 2 (faithful gate execution — THE FAILURE)
Command: `bash backend/scripts/setup.sh` (env from `backend/.env` exported; venv active). Verbatim output (exit code 1):

```
Setting up Mpango ERP (root: /home/ivy/dc12r1-h7-r10v2-gate/repo)
OK
Preflight OK.
Creating frontend .env
Starting Docker services
 Network repo_mpango_network  Creating
 Network repo_mpango_network  Created
 Volume "repo_postgres_data"  Creating
 Volume "repo_postgres_data"  Created
 Volume "repo_redis_data"  Creating
 Volume "repo_redis_data"  Created
 Container mpango_redis  Creating
 Container mpango_postgres  Creating
Error response from daemon: Conflict. The container name "/mpango_redis" is already in use by container "07a839d34b8103abf0fd633ed4abaa8ee53755495d0890fa04abfa00aff1b30e". You have to remove (or rename) that container to be able to reuse that name.
Setup stopped at line 73 (exit status 1). Partial local artifacts may exist.
```

## 6. Failure classification

- **Failed node (exact):** `backend/scripts/setup.sh:73` → `docker compose up -d postgres redis` (container creation step). ERR trap reported line 73, exit status 1. Hard STOP triggered.
- **Source-side factor:** `docker-compose.yml` hardcodes `container_name: mpango_postgres` (line 23) and `container_name: mpango_redis` (line 45). No environment-variable override exists for container names (only ports are parameterized, via `docker-compose.override.yml`). Compose therefore deterministically requests the exact names already owned by live host-owner containers.
- **Environment-side factor:** host currently runs host-owner (compose project `validation-target`) containers `mpango_postgres` + `mpango_redis` — **Up 3 days, healthy** — which own the names. In addition, `0.0.0.0:5432` and `0.0.0.0:6379` (incl. `[::]`) are already bound by their docker-proxy listeners, so even a renamed container would fail the loopback port publish `127.0.0.1:5432/6379` (secondary constraint; neither was reached).
- **Gate constraints honored:** task forbids patching/copying `setup.sh`; forbids killing/modifying host-owner containers; fake-bin bypass prohibited. No legitimate remediation exists → failure is **unblockable on this host** → per gate rules: native setup failure = hard STOP, report to CTO.

## 7. Residue status & cleanup performed

Created by run 2 (before failure): network `repo_mpango_network`; volumes `repo_postgres_data`, `repo_redis_data`; file `frontend/.env`. Task-owned resources: `backend/.env`, repo venv `.venv`, Compose v2 plugin, downloads.

Cleanup executed (post-report):
- `docker network rm repo_mpango_network`; `docker volume rm repo_postgres_data repo_redis_data`
- Removed task clone `/home/ivy/dc12r1-h7-r10v2-gate` (repo + `.env` + venvs)
- Removed `~/.docker/cli-plugins/docker-compose` (restores host to pre-gate state)
- Removed `/tmp/opencode` gate download/log artifacts (incl. env export file with credentials)
- Host-owner resources **untouched**: `validation-target` and `mpango_staging_rehearsal` containers/networks/volumes remain running.

## 8. Recommendation

Host-owner/legacy containers named `mpango_postgres`/`mpango_redis` (compose project `validation-target`, up 3 days) block every native re-run of this candidate on this machine. Options: (a) CTO authorizes stopping the `validation-target` project containers (owns the names) before re-running the gate; (b) provision a clean host; (c) if container-name parameterization is acceptable as a source change (requires CTO decision — outside current gate scope, which forbids patching). No action taken on this host.

## 9. Verification

- Local branch SHA after push matches remote (verified).
- Report contains no secrets; `backend/.env` credential material was deleted during cleanup.