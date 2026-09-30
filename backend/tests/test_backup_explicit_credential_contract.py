"""Offline contract tests for the explicit-credential backup entry point.

S-02 R1R1 (CTO-AUTH-MPANGO-PROMOTION-S02-SCOPE-HOOK-R1R1-20260930):
``ai-ledger/ops/backup_postgres.sh`` must carry NO versioned or placeholder
password default. ``DB_PASSWORD`` is a required explicit input:

* missing / empty / all-whitespace ``DB_PASSWORD`` -> the script refuses
  with a fixed named error and a non-zero exit code BEFORE any directory
  creation, log write, docker/pg_dump invocation, copy, or retention
  cleanup; the value is never printed;
* a valid ``DB_PASSWORD`` travels ONLY through the environment channel of
  the pg_dump ``docker exec`` (name-only ``-e PGPASSWORD`` pass-through):
  byte-equal at the receiving side, never present in argv, stdout, stderr,
  or the backup log; shell metacharacters in the value stay data;
* a simulated docker/pg_dump failure propagates non-zero and no
  downstream copy or retention cleanup happens.

These nodes execute the REAL candidate script through Git Bash (resolved
to an explicit absolute path, never the System32/WSL shim) inside a
per-test temporary sandbox. Every docker call is intercepted by a
recording stub; no real container, database, network, cron, or host
backup operation is reachable. All credentials are runtime synthetic
canaries; no inherited or historical value is used. Published assertions
are booleans, command categories, and byte-equality results only.
"""
import os
import shutil
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "ai-ledger" / "ops" / "backup_postgres.sh"

_GIT_BASH_CANDIDATES = (
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
    r"C:\Program Files\Git\bin\bash.exe",
)
_SYS_SHIM_MARKERS = ("system32", "windowsapps")

_DOCKER_STUB = """#!/bin/sh
# S-02 R1R1 sandbox stub: records categories/argv/env-channel only.
case "$1" in
  exec)
    printf '%s\\n' "$@" >> "$CAPDIR/argv_exec_all"
    shift
    while [ "$#" -gt 0 ]; do
      case "$1" in
        -e) shift 2 ;;
        -*) shift ;;
        *) break ;;
      esac
    done
    CMD="$2"
    shift 2
    case "$CMD" in
      pg_dump)
        printf '%s\\n' "$@" > "$CAPDIR/argv_pg_dump"
        if [ -n "${PGPASSWORD:-}" ]; then
          printf '%s' "$PGPASSWORD" > "$CAPDIR/env_pgpassword"
        else
          : > "$CAPDIR/env_pgpassword"
        fi
        echo exec_pg_dump >> "$CAPDIR/categories"
        if [ -f "$CAPDIR/rc_pg_dump" ]; then
          exit "$(cat "$CAPDIR/rc_pg_dump")"
        fi
        exit 0
        ;;
      rm)
        echo exec_rm >> "$CAPDIR/categories"
        exit 0
        ;;
      *)
        echo exec_other >> "$CAPDIR/categories"
        exit 0
        ;;
    esac
    ;;
  cp)
    echo cp >> "$CAPDIR/categories"
    for _last do :; done
    printf 'sandbox-dump-payload\\n' > "$_last"
    exit 0
    ;;
  *)
    echo other >> "$CAPDIR/categories"
    exit 0
    ;;
esac
"""


def _resolve_git_bash() -> str:
    for candidate in _GIT_BASH_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    found = shutil.which("bash") or shutil.which("bash.exe")
    if found and not any(m in found.lower() for m in _SYS_SHIM_MARKERS):
        return found
    pytest.skip("Git Bash not resolvable on this host")


_BASH = _resolve_git_bash()
_BASH_VERSION = subprocess.run(
    [_BASH, "--version"], capture_output=True, text=True, check=True
).stdout.splitlines()[0]


@pytest.fixture(autouse=True)
def _block_network_outlets(monkeypatch):
    """Any non-loopback connection attempt fails the node immediately."""

    def _refuse(*_args, **_kwargs):
        raise AssertionError(
            "network outlet reached during offline backup contract test")

    monkeypatch.setattr(socket, "create_connection", _refuse)


class _Sandbox:
    """Per-test sandbox: stub docker on PATH, captures, temp backup dir."""

    def __init__(self, tmp_path: Path):
        self.work = tmp_path / "work"
        self.backup_dir = tmp_path / "backups"
        self.bin = tmp_path / "bin"
        self.cap = tmp_path / "cap"
        for d in (self.work, self.bin, self.cap):
            d.mkdir()
        stub = self.bin / "docker"
        stub.write_text(_DOCKER_STUB, encoding="utf-8", newline="\n")
        stub.chmod(0o755)

    def base_env(self) -> dict:
        # Deliberately NOT a copy of os.environ: no inherited credentials,
        # no inherited PATH shadows. The stub directory is the FIRST PATH
        # entry so `docker` can never resolve to a host Docker CLI.
        return {
            "PATH": os.pathsep.join([
                str(self.bin),
                os.path.dirname(_BASH),
                str(Path(_BASH).parents[1] / "usr" / "bin"),
            ]),
            "CAPDIR": str(self.cap),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", ""),
            "TEMP": str(self.work),
            "TMP": str(self.work),
        }

    def run(self, env: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            [_BASH, str(SCRIPT), str(self.backup_dir)],
            cwd=str(self.work),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    # -- capture accessors (booleans / bytes equality only) --
    def categories(self) -> str:
        p = self.cap / "categories"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def argv_pg_dump(self) -> str:
        p = self.cap / "argv_pg_dump"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def argv_exec_all(self) -> str:
        p = self.cap / "argv_exec_all"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def captured_pgpassword(self) -> bytes:
        p = self.cap / "env_pgpassword"
        return p.read_bytes() if p.exists() else b"<absent>"

    def refused(self, result: subprocess.CompletedProcess) -> None:
        assert result.returncode != 0
        assert "BACKUP_DB_PASSWORD_REQUIRED" in result.stderr
        assert not self.backup_dir.exists(), "no directory may be created"
        assert self.categories() == "", "no command may run"
        assert list(self.work.iterdir()) == [], "no file may be written"


def _canary() -> str:
    return "synthetic-backup-pw-" + uuid.uuid4().hex


# --------------------------------------------------------------------------
# 1-3. missing / empty / blank DB_PASSWORD -> named refusal, zero effects
# --------------------------------------------------------------------------
def test_missing_db_password_refused_before_any_side_effect(tmp_path):
    sb = _Sandbox(tmp_path)
    result = sb.run(sb.base_env())
    sb.refused(result)


def test_empty_db_password_refused_before_any_side_effect(tmp_path):
    sb = _Sandbox(tmp_path)
    env = sb.base_env()
    env["DB_PASSWORD"] = ""
    result = sb.run(env)
    sb.refused(result)


def test_blank_whitespace_db_password_refused_before_any_side_effect(tmp_path):
    sb = _Sandbox(tmp_path)
    env = sb.base_env()
    env["DB_PASSWORD"] = "   \t  "
    result = sb.run(env)
    sb.refused(result)


# --------------------------------------------------------------------------
# 4. valid explicit credential reaches the docker exec env channel only
# --------------------------------------------------------------------------
def test_valid_password_reaches_docker_env_channel_byte_equal(tmp_path):
    sb = _Sandbox(tmp_path)
    canary = _canary()
    env = sb.base_env()
    env["DB_PASSWORD"] = canary
    result = sb.run(env)

    assert result.returncode == 0, result.stderr
    # The stub docker intercepted everything (no host docker involved).
    cats = sb.categories().splitlines()
    assert cats[0] == "exec_pg_dump"
    assert "cp" in cats and "exec_rm" in cats
    # Byte-equal delivery through the environment channel.
    assert sb.captured_pgpassword() == canary.encode("utf-8")
    # Name-only pass-through appears in argv; the value never does.
    argv_all = sb.argv_exec_all()
    argv = sb.argv_pg_dump()
    assert "PGPASSWORD" in argv_all
    assert canary not in argv_all and canary not in argv
    # Never echoed to streams or the backup log.
    assert canary not in result.stdout and canary not in result.stderr
    log = (sb.backup_dir / "backup.log")
    assert log.exists()
    assert canary not in log.read_text(encoding="utf-8", errors="replace")
    # pg_dump keeps its no-prompt contract.
    assert "--no-password" in argv
    assert "postgresql://" not in argv, "no DSN may be assembled into argv"


# --------------------------------------------------------------------------
# 5. shell metacharacters in the credential stay data, never execute
# --------------------------------------------------------------------------
def test_metacharacter_password_stays_data(tmp_path):
    sb = _Sandbox(tmp_path)
    canary = "p'\"$(touch PWNED)w;`echo x`;&|<>~#%^!*?" + uuid.uuid4().hex[:8]
    env = sb.base_env()
    env["DB_PASSWORD"] = canary
    result = sb.run(env)

    assert result.returncode == 0, result.stderr
    assert sb.captured_pgpassword() == canary.encode("utf-8")
    assert not (sb.work / "PWNED").exists(), "payload must not execute"
    assert canary not in sb.argv_pg_dump()


# --------------------------------------------------------------------------
# 6. simulated docker failure propagates; no copy / retention afterwards
# --------------------------------------------------------------------------
def test_docker_failure_propagates_without_downstream_steps(tmp_path):
    sb = _Sandbox(tmp_path)
    (sb.cap / "rc_pg_dump").write_text("9", encoding="utf-8")
    # Pre-create an old backup: retention must not run after the failure.
    sb.backup_dir.mkdir()
    old_backup = sb.backup_dir / "mpango_backup_20200101_000000.sql"
    old_backup.write_text("old-backup", encoding="utf-8")

    env = sb.base_env()
    env["DB_PASSWORD"] = _canary()
    result = sb.run(env)

    assert result.returncode != 0
    cats = sb.categories().splitlines()
    assert cats == ["exec_pg_dump"], "no copy/cleanup may follow a failure"
    assert old_backup.exists(), "retention cleanup must not run"
    new_backups = [p for p in sb.backup_dir.glob("mpango_backup_*.sql")
                   if p != old_backup]
    assert new_backups == [], "no new backup file may be produced"


# --------------------------------------------------------------------------
# harness disclosure: the resolved shell identity is part of the evidence
# --------------------------------------------------------------------------
def test_git_bash_identity_is_explicit_and_recorded():
    assert "git" in _BASH.lower(), _BASH
    assert not any(m in _BASH.lower() for m in _SYS_SHIM_MARKERS)
    assert "version" in _BASH_VERSION.lower()
