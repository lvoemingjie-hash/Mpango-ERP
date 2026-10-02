"""P21 fixture-only PG16 supply; exact ownership, private inputs, stop-only."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

import psycopg2
from psycopg2 import sql

OWNER = "zcode-mvp-invariants-codex-c91-fr3-20261002"
TASK = "c91-gap-closure-r3-20261002"
BACKEND = Path(__file__).resolve().parents[1]
DURABLE_TABLES = (
    "durable_approval_requests", "durable_approval_decisions",
    "durable_approval_audit_events", "durable_approval_idempotency_keys",
    "durable_approval_retention_jobs",
)


def _save(path, data):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(data, indent=2) + "\n")
        stream.flush()
        os.fchmod(stream.fileno(), 0o600)
        os.fsync(stream.fileno())


def _native(root, name, argv, *, env=None, timeout=180):
    _save(root / (name + "-intent.json"), {"argv": argv, "timeout": timeout})
    with (root / (name + "-stdout.txt")).open("xb") as out, (root / (name + "-stderr.txt")).open("xb") as err:
        os.fchmod(out.fileno(), 0o600)
        os.fchmod(err.fileno(), 0o600)
        process = subprocess.Popen(argv, cwd=BACKEND, env=env, stdout=out, stderr=err)
        _save(root / (name + "-spawn.json"), {"pid": process.pid})
        try:
            rc = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            _save(root / (name + "-timeout.json"), {"native_rc": process.returncode})
            raise RuntimeError("TASK_PG_COMMAND_TIMEOUT") from None
    _save(root / (name + "-result.json"), {"rc": rc, "stdout_sha256": hashlib.sha256((root / (name + "-stdout.txt")).read_bytes()).hexdigest(),
                                          "stderr_sha256": hashlib.sha256((root / (name + "-stderr.txt")).read_bytes()).hexdigest()})
    if rc:
        raise RuntimeError("TASK_PG_COMMAND_FAILED:" + name)
    return (root / (name + "-stdout.txt")).read_text().strip()


def _inspect(cid):
    raw = subprocess.run(["docker", "inspect", cid], capture_output=True, check=True, timeout=20)
    values = json.loads(raw.stdout)
    if len(values) != 1:
        raise RuntimeError("TASK_PG_INSPECT_CARDINALITY")
    return values[0]


def validate_owned_postgres(record, info):
    cid = record["id"]
    if len(cid) != 64 or any(c not in "0123456789abcdef" for c in cid) or info.get("Id") != cid:
        raise RuntimeError("TASK_PG_ID_MISMATCH")
    labels = info.get("Config", {}).get("Labels", {}) or {}
    if labels.get("mpango.owner") != OWNER or labels.get("mpango.task") != TASK:
        raise RuntimeError("TASK_PG_LABEL_MISMATCH")
    if info.get("Image") != record["image"]:
        raise RuntimeError("TASK_PG_IMAGE_MISMATCH")
    mounts = info.get("Mounts", [])
    if len(mounts) != 1 or mounts[0].get("Type") != "volume" or mounts[0].get("Name") != record["volume"] or mounts[0].get("Destination") != "/var/lib/postgresql/data":
        raise RuntimeError("TASK_PG_MOUNT_MISMATCH")


def stop_owned_postgres(record, *, inspect=None, stop=None):
    inspect = inspect or _inspect
    stop = stop or (lambda cid: subprocess.run(["docker", "stop", "--time", "30", cid],
                                             capture_output=True, check=True, timeout=45))
    validate_owned_postgres(record, inspect(record["id"]))
    stop(record["id"])
    if inspect(record["id"]).get("State", {}).get("Running"):
        raise RuntimeError("TASK_PG_STOP_NOT_CONFIRMED")


def _assert_identity(url, user, database, *, runtime=False):
    connection = psycopg2.connect(url, connect_timeout=3)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user,current_database(),rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user")
            row = cursor.fetchone()
            if row[:2] != (user, database) or (runtime and any(row[2:])):
                raise RuntimeError("TASK_PG_LIVE_IDENTITY_MISMATCH")
    finally:
        connection.close()


def _authority_snapshot(url):
    connection = psycopg2.connect(url, connect_timeout=3)
    try:
        with connection.cursor() as cursor:
            queries = {
                "head": "SELECT version_num FROM public.alembic_version ORDER BY version_num",
                "roles": "SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolreplication,rolbypassrls FROM pg_roles WHERE rolname IN ('mpango_app','mpango_migrate','reporting_user') ORDER BY rolname",
                "memberships": "SELECT r.rolname,m.rolname,a.admin_option,a.inherit_option,a.set_option FROM pg_auth_members a JOIN pg_roles r ON r.oid=a.roleid JOIN pg_roles m ON m.oid=a.member ORDER BY 1,2",
                "guard": "SELECT pg_get_userbyid(p.proowner),md5(pg_get_functiondef(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='prevent_ledger_modification'",
                "runtime_public_create": "SELECT has_schema_privilege('mpango_app','public','CREATE')",
            }
            result = {}
            for name, query in queries.items():
                cursor.execute(query)
                result[name] = cursor.fetchall()
            return result
    finally:
        connection.close()


@contextmanager
def route_deadline(urls):
    """Bound only the current native route node; retain read-only blockers."""
    previous = signal.getsignal(signal.SIGALRM)
    if signal.getitimer(signal.ITIMER_REAL)[0]:
        raise RuntimeError("TASK_PG_ROUTE_TIMER_ALREADY_OWNED")

    def timeout(signum, frame):
        connection = psycopg2.connect(urls["mig_sync"], connect_timeout=3)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pid,wait_event_type,wait_event,pg_blocking_pids(pid) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()")
                rows = cursor.fetchall()
            _save(Path(urls["private_root"]) / "route-timeout-blockers.json", {"rows": rows, "limit_seconds": 120})
        finally:
            connection.close()
        raise RuntimeError("TASK_PG_ROUTE_DEADLINE_120S")

    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, 120)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@contextmanager
def task_postgres(module, *, bare=False, shell=False):
    parent = Path(os.environ["C91_R3_RESOURCE_ROOT"])
    if not parent.is_absolute() or parent.is_symlink() or parent.stat().st_mode & 0o777 != 0o700:
        raise RuntimeError("TASK_PG_PRIVATE_ROOT_REFUSED")
    root = parent / (module + "-" + secrets.token_hex(8))
    root.mkdir(mode=0o700)
    passwords = {u: secrets.token_urlsafe(30) for u in ("postgres", "mpango_migrate", "mpango_app", "reporting_user")}
    _save(root / "credential-input.json", passwords)
    name = "c91-fr3-" + module + "-" + secrets.token_hex(8)
    labels = ["--label", "mpango.owner=" + OWNER, "--label", "mpango.task=" + TASK]
    _native(root, "volume", ["docker", "volume", "create"] + labels + [name])
    env = dict(os.environ)
    env.update(POSTGRES_PASSWORD=passwords["postgres"], POSTGRES_USER="postgres", POSTGRES_DB="postgres")
    cid = _native(root, "container", ["docker", "run", "--pull=never", "-d", "--name", name] + labels + [
        "-p", "127.0.0.1::5432", "-v", name + ":/var/lib/postgresql/data",
        "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_USER", "-e", "POSTGRES_DB", "postgres:16"], env=env)
    info = _inspect(cid)
    record = {"id": cid, "image": info["Image"], "volume": name, "owner": OWNER, "task": TASK}
    _save(root / "resource-created.json", record)
    previous = {k: os.environ.get(k) for k in ("DATABASE_URL", "REPORTING_USER_PASSWORD")}
    try:
        validate_owned_postgres(record, info)
        mapping = info["NetworkSettings"]["Ports"]["5432/tcp"]
        if len(mapping) != 1 or mapping[0]["HostIp"] != "127.0.0.1":
            raise RuntimeError("TASK_PG_LOOPBACK_MAPPING_REFUSED")
        port = int(mapping[0]["HostPort"])
        def url(user, database):
            return f"postgresql://{user}:{passwords[user]}@127.0.0.1:{port}/{database}"
        admin = url("postgres", "postgres")
        deadline = time.monotonic() + 60
        while True:
            try:
                _assert_identity(admin, "postgres", "postgres")
                break
            except psycopg2.OperationalError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("TASK_PG_TCP_READINESS_TIMEOUT") from None
                time.sleep(0.5)
        database = "test_c91_" + module
        setup = dict(os.environ)
        setup.update(MPANGO_DB_ADMIN_URL=admin, MPANGO_DB_MIGRATE_URL=url("mpango_migrate", database),
                     MPANGO_DB_APP_URL=url("mpango_app", database), MPANGO_DB_MIGRATE_ROLE="mpango_migrate",
                     MPANGO_DB_APP_ROLE="mpango_app", MPANGO_DB_MIGRATE_PASSWORD=passwords["mpango_migrate"],
                     MPANGO_DB_APP_PASSWORD=passwords["mpango_app"], REPORTING_USER_PASSWORD=passwords["reporting_user"])
        command = [sys.executable, "-B", "scripts/provision_runtime_db_roles.py"]
        _native(root, "provision", command + ["--provision"], env=setup)
        migration = dict(setup, DATABASE_URL=url("mpango_migrate", database))
        _native(root, "migration", [sys.executable, "-B", "-m", "alembic", "upgrade", "head"], env=migration)
        _native(root, "grants", command + ["--apply-grants"], env=setup)
        _native(root, "verify-before", command + ["--verify"], env=setup)
        _assert_identity(url("mpango_app", database), "mpango_app", database, runtime=True)
        urls = {"mig_async": url("mpango_app", database).replace("postgresql://", "postgresql+asyncpg://"),
                "mig_sync": url("mpango_app", database), "container": cid,
                "migration_async": url("mpango_migrate", database).replace("postgresql://", "postgresql+asyncpg://"),
                "private_root": str(root)}
        # Negative databases keep missing-table / wrong-column shapes. The
        # production provisioner still owns role supply; no full migration.
        for kind, enabled in (("bare", bare), ("shell", shell)):
            if not enabled:
                continue
            target = database + "_" + kind
            se = dict(setup, MPANGO_DB_MIGRATE_URL=url("mpango_migrate", target), MPANGO_DB_APP_URL=url("mpango_app", target))
            _native(root, "provision-" + kind, command + ["--provision"], env=se)
            connection = psycopg2.connect(url("mpango_migrate", target))
            try:
                with connection.cursor() as cursor:
                    if kind == "shell":
                        for table in DURABLE_TABLES:
                            cursor.execute(sql.SQL("CREATE TABLE public.{}(x integer)").format(sql.Identifier(table)))
                    # The failed-readiness topology contains no ledger function;
                    # use only the product's applicable object grants, not fake DDL.
                    from scripts.provision_runtime_db_roles import render_minimum_grant_statements
                    for statement in render_minimum_grant_statements("mpango_app", target):
                        if not statement.startswith("GRANT EXECUTE ON FUNCTION "):
                            cursor.execute(statement)
                connection.commit()
            finally:
                connection.close()
            _assert_identity(url("mpango_app", target), "mpango_app", target, runtime=True)
            urls[kind + "_async"] = url("mpango_app", target).replace("postgresql://", "postgresql+asyncpg://")
        os.environ["DATABASE_URL"] = urls["mig_async"]
        os.environ["REPORTING_USER_PASSWORD"] = passwords["reporting_user"]
        before = _authority_snapshot(url("mpango_migrate", database))
        _save(root / "authority-before.json", before)
        _save(root / "topology.json", {"container": cid, "port": port, "database": database,
                                     "business_user": "mpango_app", "negative_databases": [k for k in urls if k.endswith("_async")]})
        yield urls
        _native(root, "verify-after", command + ["--verify"], env=setup)
        after = _authority_snapshot(url("mpango_migrate", database))
        _save(root / "authority-after.json", after)
        if before != after:
            raise RuntimeError("TASK_PG_AUTHORITY_DRIFT")
        connection = psycopg2.connect(admin)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT datname,count(*) FROM pg_stat_activity WHERE datname=ANY(%s) GROUP BY datname", ([database, database + "_bare", database + "_shell"],))
                remaining = cursor.fetchall()
                _save(root / "connection-close-proof.json", {"remaining": remaining})
                if remaining:
                    raise RuntimeError("TASK_PG_CONNECTIONS_REMAIN_BEFORE_STOP")
        finally:
            connection.close()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        stop_owned_postgres(record)
        _save(root / "stopped.json", {"id": cid, "stopped": True, "deleted": False})
