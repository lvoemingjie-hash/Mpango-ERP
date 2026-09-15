"""Published generator (see the R3 evidence README).

Same logic as the task-local script that produced the R3 evidence, with
absolute paths replaced by environment lookups so it runs from a checkout:

  KIMI_SMTP_BACKEND_DIR     backend/ directory of the checkout (required)
  KIMI_SMTP_EVIDENCE_DIR    where evidence files are written (default .)
  python                    sys.executable is used for subprocesses
"""
import os
import sys

BACKEND = os.environ["KIMI_SMTP_BACKEND_DIR"]
WORKTREE = os.path.dirname(os.path.abspath(BACKEND))
PYTHON = sys.executable
SCRATCH = os.environ.get("KIMI_SMTP_EVIDENCE_DIR") or os.getcwd()


import asyncio
import json
import os
import re
import subprocess
import sys

import asyncpg

DB_SUITE = "tests/test_smtp_loopback_noauth_contract.py"
EVIDENCE = os.path.join(SCRATCH, "guard_negatives_r3.json")
UNPREPARED_DB = "kimi_smtp_unprepared_20260915"

ADMIN_DSN = os.environ["KIMI_SMTP_ADMIN_URL"]
TASK_DSN = os.environ["KIMI_SMTP_TASK_DATABASE_URL"]
CLUSTER = os.environ["KIMI_SMTP_TASK_CLUSTER_ID"]


def run_suite(env_overrides: dict, unset: tuple[str, ...] = ()) -> tuple[int, str]:
    env = dict(os.environ)
    for key in unset:
        env.pop(key, None)
    env.update(env_overrides)
    result = subprocess.run(
        [PYTHON, "-m", "pytest", DB_SUITE, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=env,
    )
    output = (result.stdout or "") + (result.stderr or "")
    lines = [line for line in output.splitlines() if line.strip()]
    interesting = [line for line in lines if re.search(r"RuntimeError|AssertionError|error", line)][:2]
    summary = lines[-1][:160] if lines else ""
    return result.returncode, " | ".join(interesting) or summary


async def empty_db_probe(dbname: str) -> dict:
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        tables = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' "
            "AND table_catalog = $1",
            dbname,
        )
        schemas = await conn.fetchval(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 't_test'"
        )
        return {"public_tables": tables, "t_test_schema_present": bool(schemas)}
    finally:
        await conn.close()


async def main() -> int:
    evidence: dict = {"negatives": [], "verdict": {}}

    wrong_db_dsn = re.sub(r"/[^/]+$", "/mpango_test_s2", TASK_DSN)
    other_db_dsn = re.sub(r"/[^/]+$", "/kimi_smtp_other_20260915", TASK_DSN)

    cases = [
        ("G1_task_db_url_missing", {"TEST_DATABASE_URL": TASK_DSN, "KIMI_SMTP_TASK_CLUSTER_ID": CLUSTER},
         ("KIMI_SMTP_TASK_DATABASE_URL",), "must be set explicitly"),
        ("G2_database_name_not_task_owned", {"TEST_DATABASE_URL": wrong_db_dsn, "KIMI_SMTP_TASK_DATABASE_URL": wrong_db_dsn,
                                             "KIMI_SMTP_TASK_CLUSTER_ID": CLUSTER}, (), "task-owned database"),
        ("G3_engine_vs_declared_mismatch", {"TEST_DATABASE_URL": TASK_DSN, "KIMI_SMTP_TASK_DATABASE_URL": other_db_dsn,
                                            "KIMI_SMTP_TASK_CLUSTER_ID": CLUSTER}, (), "!= task database"),
        ("G4_declared_cluster_wrong", {"TEST_DATABASE_URL": TASK_DSN, "KIMI_SMTP_TASK_DATABASE_URL": TASK_DSN,
                                       "KIMI_SMTP_TASK_CLUSTER_ID": "0"}, (), "cluster mismatch"),
        ("G5_declared_cluster_missing", {"TEST_DATABASE_URL": TASK_DSN, "KIMI_SMTP_TASK_DATABASE_URL": TASK_DSN},
         ("KIMI_SMTP_TASK_CLUSTER_ID",), "must be set explicitly"),
    ]
    for case_id, overrides, unset, expected in cases:
        code, detail = run_suite(overrides, unset)
        evidence["negatives"].append(
            {
                "id": case_id,
                "exit_code": code,
                "refused": code != 0,
                "expected_marker": expected,
                "marker_present": expected in detail,
                "detail": detail,
            }
        )

    # G6: task-named but unprepared database must be refused without any DDL.
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid()",
            UNPREPARED_DB,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{UNPREPARED_DB}"')
        await admin.execute(f'CREATE DATABASE "{UNPREPARED_DB}"')
        before = await empty_db_probe(UNPREPARED_DB)
        unprepared_dsn = re.sub(r"/[^/]+$", f"/{UNPREPARED_DB}", TASK_DSN)
        code, detail = run_suite(
            {"TEST_DATABASE_URL": unprepared_dsn, "KIMI_SMTP_TASK_DATABASE_URL": unprepared_dsn,
             "KIMI_SMTP_TASK_CLUSTER_ID": CLUSTER}
        )
        after = await empty_db_probe(UNPREPARED_DB)
        evidence["negatives"].append(
            {
                "id": "G6_task_named_unprepared_database",
                "database": UNPREPARED_DB,
                "exit_code": code,
                "refused": code != 0,
                "marker_present": "not prepared" in detail or "no public.alembic_version" in detail,
                "detail": detail,
                "objects_before": before,
                "objects_after": after,
                "zero_ddl": before == after and after["public_tables"] == 0,
            }
        )
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid()",
            UNPREPARED_DB,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{UNPREPARED_DB}"')
        evidence["g6_database_removed"] = True
    finally:
        await admin.close()

    evidence["verdict"] = {
        "all_refused": all(case["refused"] for case in evidence["negatives"]),
        "all_markers_present": all(case["marker_present"] for case in evidence["negatives"]),
        "g6_zero_ddl": next(
            case for case in evidence["negatives"] if case["id"] == "G6_task_named_unprepared_database"
        )["zero_ddl"],
    }
    with open(EVIDENCE, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(evidence, handle, indent=2)
    print(json.dumps(evidence["verdict"], indent=2))
    for case in evidence["negatives"]:
        print(f"{case['id']:38s} exit={case['exit_code']} refused={case['refused']} marker={case['marker_present']}")
    print("evidence:", EVIDENCE)
    return 0 if all(evidence["verdict"].values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
