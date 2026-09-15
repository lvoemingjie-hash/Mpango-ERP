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
DB_SUITE_PATH = os.path.join(BACKEND, "tests", "test_smtp_loopback_noauth_contract.py")


import asyncio
import hashlib
import io
import json
import os
import re
import subprocess
import sys

import asyncpg

DB_SUITE = "tests/test_smtp_loopback_noauth_contract.py"
EVIDENCE = os.path.join(SCRATCH, "cluster_identity_counterexample_r3.json")

CLUSTER_ASSERTION = (
    "    assert cluster_identifier == declared_cluster, (\n"
    '        f"cluster mismatch: live system_identifier {cluster_identifier!r} != "\n'
    '        f"declared {TASK_CLUSTER_ENV} {declared_cluster!r}; refusing before any write"\n'
    "    )\n"
)


def _dsn() -> str:
    url = os.environ["KIMI_SMTP_TASK_DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def snapshot() -> dict:
    conn = await asyncpg.connect(_dsn())
    try:
        db = await conn.fetchval("SELECT current_database()")
        return {
            "database": db,
            "roles": sorted(r["rolname"] for r in await conn.fetch("SELECT rolname FROM pg_roles")),
            "databases": sorted(r["datname"] for r in await conn.fetch("SELECT datname FROM pg_database")),
            "extensions": sorted(r["extname"] for r in await conn.fetch("SELECT extname FROM pg_extension")),
            "write_counters": dict(
                await conn.fetchrow(
                    "SELECT tup_inserted, tup_updated, tup_deleted "
                    "FROM pg_stat_database WHERE datname = current_database()"
                )
            ),
            "registration_rows": await conn.fetchval("SELECT count(*) FROM public.tenant_registrations"),
        }
    finally:
        await conn.close()


def run_suite(cluster_id: str | None, extra: list[str] | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    if cluster_id is None:
        env.pop("KIMI_SMTP_TASK_CLUSTER_ID", None)
    else:
        env["KIMI_SMTP_TASK_CLUSTER_ID"] = cluster_id
    result = subprocess.run(
        [PYTHON, "-m", "pytest", DB_SUITE, "-q", "--no-header", "-p", "no:cacheprovider", *(extra or [])],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=env,
    )
    output = (result.stdout or "") + (result.stderr or "")
    verdict = re.search(r"(?P<n>\d+) (passed|failed|error)", output)
    return result.returncode, output.strip().splitlines()[-1][:160] if output.strip() else ""


def summarized(output: str) -> dict:
    return {
        "passed": len(re.findall(r"PASSED", output)),
        "cluster_refusal": "cluster mismatch" in output,
        "db_url_refusal": "must be set explicitly" in output,
        "tests_collected_error": "error" in output.lower() and "passed" not in output,
    }


async def main() -> int:
    evidence: dict = {"cases": []}
    before = await snapshot()
    evidence["snapshot_before"] = before

    # Case C1: database name matches, declared cluster is wrong.
    code_wrong, _ = run_suite("0")
    after_wrong = await snapshot()
    # Case C2: database name matches, cluster identity not declared at all.
    code_unset, _ = run_suite(None)
    after_unset = await snapshot()

    def deltas(after: dict) -> dict:
        return {
            "roles_added": sorted(set(after["roles"]) - set(before["roles"])),
            "databases_added": sorted(set(after["databases"]) - set(before["databases"])),
            "extensions_added": sorted(set(after["extensions"]) - set(before["extensions"])),
            "tuples_inserted": after["write_counters"]["tup_inserted"] - before["write_counters"]["tup_inserted"],
            "tuples_updated": after["write_counters"]["tup_updated"] - before["write_counters"]["tup_updated"],
            "tuples_deleted": after["write_counters"]["tup_deleted"] - before["write_counters"]["tup_deleted"],
            "registration_rows_delta": after["registration_rows"] - before["registration_rows"],
        }

    d_wrong = deltas(after_wrong)
    d_unset = deltas(after_unset)
    evidence["cases"].append(
        {
            "id": "C1_matching_db_name_wrong_cluster",
            "cluster_id": "0",
            "exit_code": code_wrong,
            "refused": code_wrong != 0,
            "deltas": d_wrong,
            "zero_writes": all(
                value == 0
                for key, value in d_wrong.items()
                if key != "roles_added" and isinstance(value, int)
            )
            and not d_wrong["roles_added"]
            and not d_wrong["databases_added"]
            and not d_wrong["extensions_added"],
        }
    )
    evidence["cases"].append(
        {
            "id": "C2_matching_db_name_cluster_undeclared",
            "cluster_id": None,
            "exit_code": code_unset,
            "refused": code_unset != 0,
            "deltas": d_unset,
            "zero_writes": all(
                value == 0
                for key, value in d_unset.items()
                if key != "roles_added" and isinstance(value, int)
            )
            and not d_unset["roles_added"]
            and not d_unset["databases_added"]
            and not d_unset["extensions_added"],
        }
    )

    # Case X1: prove the cluster assertion is what enforces the refusal.
    with io.open(DB_SUITE_PATH, encoding="utf-8", newline="") as handle:
        original = handle.read()
    digest_before = hashlib.sha256(original.encode()).hexdigest()
    newline = "\r\n" if "\r\n" in original else "\n"
    assertion = CLUSTER_ASSERTION.replace("\n", newline)
    assert original.count(assertion) == 1, "cluster assertion anchor not found"
    try:
        with io.open(DB_SUITE_PATH, "w", encoding="utf-8", newline="") as handle:
            handle.write(original.replace(assertion, ""))
        code_mutated, tail_mutated = run_suite("0")
    finally:
        with io.open(DB_SUITE_PATH, "w", encoding="utf-8", newline="") as handle:
            handle.write(original)
    digest_after = hashlib.sha256(io.open(DB_SUITE_PATH, encoding="utf-8", newline="").read().encode()).hexdigest()
    evidence["cases"].append(
        {
            "id": "X1_cluster_assertion_removed_run_no_longer_refuses",
            "exit_code_after_removal": code_mutated,
            "no_longer_refuses": code_mutated == 0,
            "tail": tail_mutated,
            "restored_exact": digest_after == digest_before,
            "sha256_before": digest_before,
            "sha256_after_restore": digest_after,
        }
    )

    evidence["verdict"] = {
        "c1_refused_and_zero_writes": evidence["cases"][0]["refused"] and evidence["cases"][0]["zero_writes"],
        "c2_refused_and_zero_writes": evidence["cases"][1]["refused"] and evidence["cases"][1]["zero_writes"],
        "x1_cluster_assertion_load_bearing": evidence["cases"][2]["no_longer_refuses"]
        and evidence["cases"][2]["restored_exact"],
    }
    with io.open(EVIDENCE, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(evidence, handle, indent=2)

    print(json.dumps(evidence["verdict"], indent=2))
    print("evidence:", EVIDENCE)
    return 0 if all(evidence["verdict"].values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
