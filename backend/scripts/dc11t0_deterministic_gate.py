#!/usr/bin/env python3
"""DC-11T0-R2 deterministic backend test gate.

Creates fresh disposable PostgreSQL 16 and Redis 7 containers, verifies
infrastructure health and Alembic state, runs pytest with a node-status ledger,
and removes all containers/volumes for the run before exiting.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import socket
import string
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
EXPECTED_ALEMBIC_HEAD = "034_platform_operators"
POSTGRES_IMAGE = "postgres:16-alpine"
REDIS_IMAGE = "redis:7-alpine"
POSTGRES_USER = "gate_runner"
POSTGRES_DB = "dc11t0_test_gate"
POSTGRES_PASSWORD = "dc11t0_gate_password"
SECRET_KEY = hashlib.sha256(b"dc11t0-r2-deterministic-gate-secret").hexdigest()


SENSITIVE_ENV_KEYS = {
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "POSTGRES_PASSWORD",
    "REPORTING_USER_PASSWORD",
    "REDIS_URL",
    "SECRET_KEY",
    "SMTP_HOST",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "EMAIL_FROM",
}


PLUGIN_SOURCE = r'''
from __future__ import annotations

import json

_COLLECTION_ERRORS = []
_COLLECTED_NODEIDS = []
_REPORTS = {}


def pytest_addoption(parser):
    group = parser.getgroup("dc11t0")
    group.addoption("--dc11t0-ledger", action="store", default=None)
    group.addoption("--dc11t0-collected", action="store", default=None)


def pytest_configure(config):
    global _COLLECTION_ERRORS, _COLLECTED_NODEIDS, _REPORTS
    _COLLECTION_ERRORS = []
    _COLLECTED_NODEIDS = []
    _REPORTS = {}


def pytest_collection_finish(session):
    global _COLLECTED_NODEIDS
    nodeids = [item.nodeid for item in session.items]
    _COLLECTED_NODEIDS = nodeids
    collected_path = session.config.getoption("--dc11t0-collected")
    if collected_path:
        with open(collected_path, "w", encoding="utf-8") as fh:
            json.dump(nodeids, fh, indent=2, sort_keys=True)


def pytest_collectreport(report):
    if report.failed:
        nodeid = getattr(report, "nodeid", None) or getattr(report, "fspath", None) or "collection"
        _COLLECTION_ERRORS.append(str(nodeid))


def pytest_runtest_logreport(report):
    entry = _REPORTS.setdefault(report.nodeid, {"nodeid": report.nodeid, "phases": []})
    phase = {
        "when": report.when,
        "outcome": report.outcome,
    }
    wasxfail = getattr(report, "wasxfail", None)
    if wasxfail:
        phase["wasxfail"] = str(wasxfail)
    entry["phases"].append(phase)


def _status_for_node(entry):
    phases = entry.get("phases", [])
    if any(phase["outcome"] == "failed" and phase["when"] != "call" for phase in phases):
        return "error"
    if any(phase["outcome"] == "failed" and phase["when"] == "call" for phase in phases):
        return "failed"
    if any(phase["outcome"] == "skipped" and phase.get("wasxfail") for phase in phases):
        return "xfailed"
    if any(phase["outcome"] == "skipped" for phase in phases):
        return "skipped"
    if any(phase["outcome"] == "passed" and phase["when"] == "call" for phase in phases):
        return "passed"
    if any(phase["outcome"] == "passed" and phase.get("wasxfail") for phase in phases):
        return "passed"
    return "notrun"


def pytest_sessionfinish(session, exitstatus):
    ledger_path = session.config.getoption("--dc11t0-ledger")
    if not ledger_path:
        return

    rows = []
    for nodeid in _COLLECTED_NODEIDS:
        rows.append(
            {
                "nodeid": nodeid,
                "status": _status_for_node(_REPORTS.get(nodeid, {"nodeid": nodeid, "phases": []})),
            }
        )
    for nodeid in sorted(set(_COLLECTION_ERRORS)):
        rows.append({"nodeid": nodeid, "status": "error"})

    with open(ledger_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "exitstatus": int(exitstatus),
                "collected": _COLLECTED_NODEIDS,
                "collection_errors": sorted(set(_COLLECTION_ERRORS)),
                "rows": rows,
            },
            fh,
            indent=2,
            sort_keys=True,
        )
'''


def redact(text: str, secrets: list[str] | None = None) -> str:
    redacted = text
    for value in secrets or []:
        if value:
            redacted = redacted.replace(value, "<redacted>")
    redacted = re.sub(r"postgresql(?:\+asyncpg)?://[^\s'\"<>]+", "postgresql://<redacted>", redacted)
    redacted = re.sub(r"redis://[^\s'\"<>]+", "redis://<redacted>", redacted)
    return redacted


def run(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path = BACKEND_DIR,
    check: bool = True,
    timeout: int | None = None,
    secrets: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        safe_output = redact(proc.stdout or "", secrets)
        safe_cmd = " ".join(cmd[:2] + ["..."]) if len(cmd) > 2 else " ".join(cmd)
        raise RuntimeError(f"command failed ({proc.returncode}): {safe_cmd}\n{safe_output}")
    return proc


def docker(*args: str, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return run(["docker", *args], cwd=REPO_ROOT, check=check, timeout=timeout)


def ensure_docker_available() -> None:
    if not shutil.which("docker"):
        raise RuntimeError("docker CLI is not available")
    docker("version", "--format", "{{.Server.Version}}", timeout=15)


def unique_prefix(label: str) -> str:
    alphabet = string.ascii_lowercase + string.digits
    suffix = "".join(random.choice(alphabet) for _ in range(8))
    timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "-", label).strip("-").lower() or "run"
    return f"dc11t0-r2-{safe_label}-{timestamp}-{suffix}"


def host_port(container: str, internal_port: str) -> str:
    proc = docker("inspect", "-f", f"{{{{(index (index .NetworkSettings.Ports \"{internal_port}/tcp\") 0).HostPort}}}}", container)
    port = proc.stdout.strip()
    if not port:
        raise RuntimeError(f"docker did not expose port {internal_port} for {container}")
    return port


def wait_for_port(host: str, port: int, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"port {host}:{port} did not become reachable: {last_error}")


def wait_for_container_health(pg_name: str, redis_name: str, pg_port: int, redis_port: int) -> dict[str, Any]:
    wait_for_port("127.0.0.1", pg_port)
    wait_for_port("127.0.0.1", redis_port)

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        pg = docker("exec", pg_name, "pg_isready", "-U", POSTGRES_USER, "-d", POSTGRES_DB, check=False)
        redis = docker("exec", redis_name, "redis-cli", "ping", check=False)
        if pg.returncode == 0 and "PONG" in redis.stdout:
            return {
                "postgres_image": POSTGRES_IMAGE,
                "redis_image": REDIS_IMAGE,
                "postgres_pg_isready": "ok",
                "redis_ping": "ok",
                "postgres_host_port": pg_port,
                "redis_host_port": redis_port,
            }
        time.sleep(2)

    raise RuntimeError("container health checks did not pass before timeout")


def create_infrastructure(prefix: str) -> dict[str, Any]:
    pg_name = f"{prefix}-pg"
    redis_name = f"{prefix}-redis"
    network = f"{prefix}-net"
    pg_volume = f"{prefix}-pgdata"
    redis_volume = f"{prefix}-redisdata"

    docker("network", "create", network)
    docker("volume", "create", pg_volume)
    docker("volume", "create", redis_volume)
    docker(
        "run",
        "-d",
        "--name",
        pg_name,
        "--network",
        network,
        "-e",
        f"POSTGRES_USER={POSTGRES_USER}",
        "-e",
        f"POSTGRES_PASSWORD={POSTGRES_PASSWORD}",
        "-e",
        f"POSTGRES_DB={POSTGRES_DB}",
        "-p",
        "127.0.0.1::5432",
        "-v",
        f"{pg_volume}:/var/lib/postgresql/data",
        POSTGRES_IMAGE,
    )
    docker(
        "run",
        "-d",
        "--name",
        redis_name,
        "--network",
        network,
        "-p",
        "127.0.0.1::6379",
        "-v",
        f"{redis_volume}:/data",
        REDIS_IMAGE,
    )

    pg_port = int(host_port(pg_name, "5432"))
    redis_port = int(host_port(redis_name, "6379"))

    return {
        "prefix": prefix,
        "postgres_container": pg_name,
        "redis_container": redis_name,
        "network": network,
        "postgres_volume": pg_volume,
        "redis_volume": redis_volume,
        "postgres_port": pg_port,
        "redis_port": redis_port,
    }


def cleanup_infrastructure(infra: dict[str, Any]) -> dict[str, Any]:
    cleanup: dict[str, Any] = {"commands": [], "remaining": {}}
    for container_key in ("postgres_container", "redis_container"):
        name = infra.get(container_key)
        if name:
            proc = docker("rm", "-f", name, check=False)
            cleanup["commands"].append({"target": name, "returncode": proc.returncode})
    for volume_key in ("postgres_volume", "redis_volume"):
        name = infra.get(volume_key)
        if name:
            proc = docker("volume", "rm", "-f", name, check=False)
            cleanup["commands"].append({"target": name, "returncode": proc.returncode})
    network = infra.get("network")
    if network:
        proc = docker("network", "rm", network, check=False)
        cleanup["commands"].append({"target": network, "returncode": proc.returncode})

    prefix = infra.get("prefix", "")
    ps = docker("ps", "-a", "--filter", f"name={prefix}", "--format", "{{.Names}}", check=False)
    volumes = docker("volume", "ls", "--filter", f"name={prefix}", "--format", "{{.Name}}", check=False)
    networks = docker("network", "ls", "--filter", f"name={prefix}", "--format", "{{.Name}}", check=False)
    cleanup["remaining"] = {
        "containers": [line for line in ps.stdout.splitlines() if line.strip()],
        "volumes": [line for line in volumes.stdout.splitlines() if line.strip()],
        "networks": [line for line in networks.stdout.splitlines() if line.strip()],
    }
    cleanup["complete"] = not any(cleanup["remaining"].values())
    return cleanup


def clean_test_env(pg_port: int, redis_port: int, plugin_dir: Path, ledger_path: Path, collected_path: Path) -> dict[str, str]:
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@127.0.0.1:{pg_port}/{POSTGRES_DB}"
    redis_url = f"redis://127.0.0.1:{redis_port}/0"

    env = os.environ.copy()
    for key in SENSITIVE_ENV_KEYS:
        env.pop(key, None)

    env.update(
        {
            "MPANGO_ENV": "test",
            "TEST_DATABASE_URL": db_url,
            "DATABASE_URL": db_url,
            "POSTGRES_USER": POSTGRES_USER,
            "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
            "POSTGRES_DB": POSTGRES_DB,
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": str(pg_port),
            "REPORTING_USER_PASSWORD": POSTGRES_PASSWORD,
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": str(redis_port),
            "REDIS_URL": redis_url,
            "SECRET_KEY": SECRET_KEY,
            "EMAIL_PROVIDER": "dev_sink",
            "EMAIL_DELIVERY_MODE": "dev_sink",
            "SMTP_HOST": "",
            "SMTP_USER": "",
            "SMTP_PASSWORD": "",
            "EMAIL_FROM": "",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "PYTHONPATH": f"{plugin_dir}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep),
            "DC11T0_LEDGER_PATH": str(ledger_path),
            "DC11T0_COLLECTED_PATH": str(collected_path),
        }
    )
    return env


def write_plugin(plugin_dir: Path) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "dc11t0_gate_plugin.py").write_text(PLUGIN_SOURCE, encoding="utf-8")


def run_alembic_checks(env: dict[str, str], artifacts_dir: Path, secrets: list[str]) -> dict[str, Any]:
    heads = run(["poetry", "run", "alembic", "heads"], env=env, secrets=secrets, timeout=120)
    heads_output = redact(heads.stdout, secrets).strip()
    head_lines = [line.strip() for line in heads_output.splitlines() if line.strip()]
    if len(head_lines) != 1 or EXPECTED_ALEMBIC_HEAD not in head_lines[0]:
        raise RuntimeError(f"unexpected Alembic heads: {heads_output}")

    upgrade = run(["poetry", "run", "alembic", "upgrade", "head"], env=env, secrets=secrets, timeout=240)
    (artifacts_dir / "alembic_upgrade_output.txt").write_text(redact(upgrade.stdout, secrets), encoding="utf-8")

    current = run(["poetry", "run", "alembic", "current"], env=env, secrets=secrets, timeout=120)
    current_output = redact(current.stdout, secrets).strip()
    if EXPECTED_ALEMBIC_HEAD not in current_output:
        raise RuntimeError(f"unexpected Alembic current: {current_output}")

    return {
        "heads": head_lines,
        "current": current_output,
        "expected_head": EXPECTED_ALEMBIC_HEAD,
    }


def summarize_ledger(ledger_path: Path, collected_path: Path, pytest_exit_code: int) -> dict[str, Any]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    collected = json.loads(collected_path.read_text(encoding="utf-8"))
    rows = ledger.get("rows", [])
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "xfailed": 0, "notrun": 0}
    failed_nodes: list[str] = []
    error_nodes: list[str] = []
    skipped_nodes: list[str] = []
    xfailed_nodes: list[str] = []

    normalized_rows: list[tuple[str, str]] = []
    for row in rows:
        nodeid = str(row["nodeid"])
        status = str(row["status"])
        if status == "error":
            counts["errors"] += 1
            error_nodes.append(nodeid)
        elif status == "failed":
            counts["failed"] += 1
            failed_nodes.append(nodeid)
        elif status == "skipped":
            counts["skipped"] += 1
            skipped_nodes.append(nodeid)
        elif status == "xfailed":
            counts["xfailed"] += 1
            xfailed_nodes.append(nodeid)
        elif status == "passed":
            counts["passed"] += 1
        else:
            counts["notrun"] += 1
        normalized_rows.append((nodeid, status))

    normalized_text = "\n".join(f"{nodeid},{status}" for nodeid, status in sorted(normalized_rows)) + "\n"
    ledger_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    collected_count = len(collected)
    accounted = counts["passed"] + counts["failed"] + counts["errors"] + counts["skipped"] + counts["xfailed"]
    accounting_gap = collected_count - accounted

    return {
        "collected": collected_count,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "errors": counts["errors"],
        "skipped": counts["skipped"],
        "xfailed": counts["xfailed"],
        "notrun": counts["notrun"],
        "accounting_gap": accounting_gap,
        "pytest_exit_code": pytest_exit_code,
        "failed_nodes": sorted(failed_nodes),
        "error_nodes": sorted(error_nodes),
        "skipped_nodes": sorted(skipped_nodes),
        "xfailed_nodes": sorted(xfailed_nodes),
        "normalized_node_ledger_sha256": ledger_hash,
    }


def write_remaining_csv(summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["status", "nodeid"])
        writer.writeheader()
        for nodeid in summary.get("failed_nodes", []):
            writer.writerow({"status": "failed", "nodeid": nodeid})
        for nodeid in summary.get("error_nodes", []):
            writer.writerow({"status": "error", "nodeid": nodeid})


def run_pytest(env: dict[str, str], artifacts_dir: Path, targets: list[str], secrets: list[str]) -> dict[str, Any]:
    plugin_dir = artifacts_dir / "pytest_plugin"
    ledger_path = artifacts_dir / "pytest_ledger.json"
    collected_path = artifacts_dir / "pytest_collected.json"
    write_plugin(plugin_dir)
    env = env.copy()
    env["PYTHONPATH"] = f"{plugin_dir}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)

    cmd = [
        "poetry",
        "run",
        "pytest",
        "-p",
        "dc11t0_gate_plugin",
        "--dc11t0-ledger",
        str(ledger_path),
        "--dc11t0-collected",
        str(collected_path),
        *targets,
    ]
    proc = run(cmd, env=env, check=False, timeout=None, secrets=secrets)
    safe_output = redact(proc.stdout, secrets)
    (artifacts_dir / "pytest_output.txt").write_text(safe_output, encoding="utf-8")
    if not ledger_path.exists() or not collected_path.exists():
        raise RuntimeError("pytest did not produce the required ledger artifacts")

    summary = summarize_ledger(ledger_path, collected_path, proc.returncode)
    (artifacts_dir / "normalized_node_ledger.csv").write_text(
        "\n".join(
            f"{row['nodeid']},{row['status']}"
            for row in sorted(json.loads(ledger_path.read_text(encoding="utf-8"))["rows"], key=lambda item: item["nodeid"])
        )
        + "\n",
        encoding="utf-8",
    )
    write_remaining_csv(summary, artifacts_dir / "remaining_nodes.csv")
    return summary


def command_run(args: argparse.Namespace) -> int:
    artifacts_dir = Path(args.artifacts_dir).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    prefix = unique_prefix(args.run_label)
    infra: dict[str, Any] = {"prefix": prefix}
    cleanup: dict[str, Any] | None = None
    summary: dict[str, Any] = {
        "run_label": args.run_label,
        "artifacts_dir": str(artifacts_dir),
        "status": "started",
        "targets": args.pytest_target or ["tests"],
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        ensure_docker_available()
        infra = create_infrastructure(prefix)
        summary["infrastructure"] = {
            "postgres_image": POSTGRES_IMAGE,
            "redis_image": REDIS_IMAGE,
            "prefix": prefix,
        }

        plugin_dir = artifacts_dir / "pytest_plugin"
        ledger_path = artifacts_dir / "pytest_ledger.json"
        collected_path = artifacts_dir / "pytest_collected.json"
        env = clean_test_env(infra["postgres_port"], infra["redis_port"], plugin_dir, ledger_path, collected_path)
        secrets = [
            env["TEST_DATABASE_URL"],
            env["DATABASE_URL"],
            env["REDIS_URL"],
            POSTGRES_PASSWORD,
            SECRET_KEY,
        ]

        health = wait_for_container_health(
            infra["postgres_container"],
            infra["redis_container"],
            infra["postgres_port"],
            infra["redis_port"],
        )
        summary["health"] = {
            **{key: value for key, value in health.items() if not key.endswith("_host_port")},
            "postgres_host_port_recorded": True,
            "redis_host_port_recorded": True,
        }

        summary["alembic"] = run_alembic_checks(env, artifacts_dir, secrets)
        pytest_summary = run_pytest(env, artifacts_dir, args.pytest_target or ["tests"], secrets)
        summary.update(pytest_summary)
        summary["status"] = "completed"
    except Exception as exc:
        summary["status"] = "invalid"
        summary["error"] = redact(str(exc))
        print(f"INVALID_RUN: {summary['error']}", file=sys.stderr)
    finally:
        cleanup = cleanup_infrastructure(infra)
        summary["cleanup"] = {
            "complete": cleanup.get("complete", False),
            "remaining": cleanup.get("remaining", {}),
        }
        summary["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (artifacts_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    printable = {
        key: summary.get(key)
        for key in (
            "run_label",
            "status",
            "collected",
            "passed",
            "failed",
            "errors",
            "skipped",
            "xfailed",
            "accounting_gap",
            "normalized_node_ledger_sha256",
        )
        if key in summary
    }
    print(json.dumps(printable, indent=2, sort_keys=True))

    if summary.get("status") != "completed":
        return 2
    if summary.get("accounting_gap") != 0:
        return 3
    if not summary.get("cleanup", {}).get("complete"):
        return 4
    if args.strict_pytest_exit and summary.get("pytest_exit_code") != 0:
        return int(summary["pytest_exit_code"])
    return 0


def command_compare(args: argparse.Namespace) -> int:
    left = json.loads(Path(args.left).read_text(encoding="utf-8"))
    right = json.loads(Path(args.right).read_text(encoding="utf-8"))
    compared_keys = ["collected", "passed", "failed", "errors", "skipped", "xfailed", "accounting_gap"]
    mismatches: list[str] = []
    for key in compared_keys:
        if left.get(key) != right.get(key):
            mismatches.append(f"{key}: {left.get(key)} != {right.get(key)}")
    for key in ("failed_nodes", "error_nodes"):
        if sorted(left.get(key, [])) != sorted(right.get(key, [])):
            mismatches.append(f"{key} differs")
    if left.get("normalized_node_ledger_sha256") != right.get("normalized_node_ledger_sha256"):
        mismatches.append("normalized_node_ledger_sha256 differs")

    result = {
        "left": str(Path(args.left).resolve()),
        "right": str(Path(args.right).resolve()),
        "match": not mismatches,
        "mismatches": mismatches,
        "left_hash": left.get("normalized_node_ledger_sha256"),
        "right_hash": right.get("normalized_node_ledger_sha256"),
    }
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not mismatches else 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              poetry run python scripts/dc11t0_deterministic_gate.py run --run-label full-run-1 --artifacts-dir /tmp/dc11t0/full-run-1
              poetry run python scripts/dc11t0_deterministic_gate.py compare --left /tmp/dc11t0/full-run-1/summary.json --right /tmp/dc11t0/full-run-2/summary.json
            """
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run one fresh-infrastructure pytest gate")
    run_parser.add_argument("--run-label", required=True)
    run_parser.add_argument("--artifacts-dir", required=True)
    run_parser.add_argument("--pytest-target", action="append")
    run_parser.add_argument("--strict-pytest-exit", action="store_true")
    run_parser.set_defaults(func=command_run)

    compare_parser = subparsers.add_parser("compare", help="compare two gate summaries")
    compare_parser.add_argument("--left", required=True)
    compare_parser.add_argument("--right", required=True)
    compare_parser.add_argument("--output")
    compare_parser.set_defaults(func=command_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
