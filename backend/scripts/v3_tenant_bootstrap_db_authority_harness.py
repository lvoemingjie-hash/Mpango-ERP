#!/usr/bin/env python3
"""V3 harness: MPANGO-TENANT-BOOTSTRAP-DB-AUTHORITY-R1.

Orchestrates the full data-integrity-and-provisioning-authority verification
on a FRESH PostgreSQL 16 cluster:

  phase provision  start a throwaway postgres:16 container (fresh cluster),
                   create migration-authority + runtime roles (runtime:
                   NOSUPERUSER NOCREATEDB NOCREATEROLE) and one application
                   database per scenario, owned by the migration authority
  phase migrate    run `alembic upgrade head` AS the migration authority in
                   every database
  phase grants     apply the declared minimum runtime grants AS the migration
                   authority and run the tool's read-only --verify
  phase breakage   induce one authority violation per negative database
                   (missing function / bad signature / runtime-owned function
                   / revoked EXECUTE)
  phase suite      run tests/test_tenant_bootstrap_db_authority.py once per
                   scenario; every run must be GREEN
  phase mutation   M1: reintroduce runtime CREATE OR REPLACE of the public
                       guard -> v3_ok run must go RED on named nodeids;
                   M2: remove the ownership precondition -> v3_wrongown run
                       must go RED on named nodeids;
                   after each mutation the file is restored and proven
                   BYTE-IDENTICAL (sha256) and an unmuted v3_ok run is re-proven
  phase teardown   remove the container (unless --keep)

Every phase emits artifacts into the evidence directory.

Usage (from backend/):
    python scripts/v3_tenant_bootstrap_db_authority_harness.py \
        --evidence-dir ../ai-ledger/product-ai/evidence/2026-09-16_zcode_tenant_bootstrap_db_authority_r1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
BOOTSTRAP_SCRIPT = BACKEND_DIR / "scripts" / "bootstrap_tenant_schema.py"
GRANTS_SCRIPT = BACKEND_DIR / "scripts" / "provision_runtime_db_roles.py"
TEST_FILE = "tests/test_tenant_bootstrap_db_authority.py"

IMAGE_DEFAULT = "postgres:16.15"
MIGRATE_ROLE = "mpango_migrate"
APP_ROLE = "mpango_app"
SCENARIOS = ("v3_ok", "v3_nofunc", "v3_badsig", "v3_wrongown", "v3_nopriv")

MUTATION_M1_ANCHOR = (
    "        await db.execute(text(\n"
    "            f'DROP TRIGGER IF EXISTS prevent_ledger_mod ON "
    '"{ts}".ledger_entries\'\n'
    "        ))"
)
MUTATION_M1_SNIPPET = (
    "        # MUTATION M1: runtime CREATE OR REPLACE of the public guard "
    "reintroduced\n"
    "        await db.execute(text(\n"
    '            "CREATE OR REPLACE FUNCTION '
    'public.prevent_ledger_modification() "\n'
    '            "RETURNS TRIGGER AS $$ BEGIN RETURN OLD; END; '
    '$$ LANGUAGE plpgsql"\n'
    "        ))\n"
)
MUTATION_M2_TARGET = "await _assert_ledger_guard_function_authority(db)"
MUTATION_M2_REPLACEMENT = (
    "await db.execute(text('SELECT 1'))  "
    "# MUTATION M2: ownership precondition removed"
)

MUTATION_M1_NAMED_RED = {
    "tests/test_tenant_bootstrap_db_authority.py::"
    "test_r1_public_lifecycle_activates_tenant_as_runtime_role",
    "tests/test_tenant_bootstrap_db_authority.py::"
    "test_mutation_m1_sentinel_reintroducing_runtime_replace_is_refused",
}
MUTATION_M2_NAMED_RED = {
    "tests/test_tenant_bootstrap_db_authority.py::"
    "test_n3_runtime_owned_guard_function_fails_closed_zero_partial_tenant",
    "tests/test_tenant_bootstrap_db_authority.py::"
    "test_mutation_m2_sentinel_ownership_precondition_is_load_bearing",
    "tests/test_tenant_bootstrap_db_authority.py::"
    "test_bootstrap_script_never_replaces_or_reowns_public_guard",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run(command: list[str], *, env: dict | None = None, timeout: int = 1200,
         verify: bool = False, label: str = "") -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = subprocess.run(
        command, env=merged, cwd=str(BACKEND_DIR), capture_output=True,
        text=True, timeout=timeout, encoding="utf-8", errors="replace",
    )
    if verify and result.returncode != 0:
        raise RuntimeError(
            f"{label or command} failed (rc={result.returncode})\n"
            f"--- stdout ---\n{result.stdout[-4000:]}\n"
            f"--- stderr ---\n{result.stderr[-4000:]}"
        )
    return result


class Harness:
    def __init__(self, evidence_dir: Path, image: str, keep: bool,
                 python_exe: str, skip_mutations: bool) -> None:
        self.evidence_dir = evidence_dir
        self.image = image
        self.keep = keep
        self.python_exe = python_exe
        self.skip_mutations = skip_mutations
        self.container = f"mpango-v3-auth-{uuid.uuid4().hex[:10]}"
        self.port = _free_port()
        self.admin_password = secrets.token_hex(16)
        self.migrate_password = secrets.token_hex(16)
        self.app_password = secrets.token_hex(16)
        self.reporting_password = secrets.token_hex(16)
        self.host = "127.0.0.1"
        self.admin_url = (
            f"postgresql://postgres:{self.admin_password}"
            f"@{self.host}:{self.port}/postgres"
        )
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir = self.evidence_dir / "_work"
        self.work_dir.mkdir(exist_ok=True)
        self.snapshots: dict[str, dict] = {}
        self.report: dict = {
            "task": "MPANGO_TENANT_BOOTSTRAP_DB_AUTHORITY_R1",
            "authorization":
                "CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-2026-09-16",
            "started_at": _utc(),
            "image": image,
            "container": self.container,
            "port": self.port,
            "base_commit": "2665f0ee019302291bfca1d3f579cf852bc633ff",  # pragma: allowlist secret
            "phases": {},
        }

    # ------------------------------------------------------------- container
    def start_container(self) -> None:
        _run([
            "docker", "run", "--name", self.container,
            "-e", f"POSTGRES_PASSWORD={self.admin_password}",
            "-p", f"127.0.0.1:{self.port}:5432", "-d", self.image,
        ], verify=True, label="docker run")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            probe = _run([
                "docker", "exec", self.container, "pg_isready",
                "-U", "postgres", "-d", "postgres",
            ])
            if probe.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("postgres container did not become ready")
        version = _run([
            "docker", "exec", self.container, "psql", "-U", "postgres",
            "-tAc", "SHOW server_version_num;",
        ], verify=True, label="server_version probe")
        cluster = _run([
            "docker", "exec", self.container, "psql", "-U", "postgres",
            "-tAc", "SELECT system_identifier FROM pg_control_system();",
        ], verify=True, label="system_identifier probe")
        self.report["server_version_num"] = version.stdout.strip()
        self.report["cluster_system_identifier"] = cluster.stdout.strip()
        print(f"[container] {self.container} ready (PG "
              f"server_version_num={version.stdout.strip()}, "
              f"cluster={cluster.stdout.strip()})")

    def stop_container(self) -> None:
        _run(["docker", "rm", "-f", self.container])

    # ----------------------------------------------------------- provisioning
    def _urls(self, database: str) -> tuple[str, str, str]:
        common = f"{self.host}:{self.port}/{database}"
        return (
            f"postgresql://{MIGRATE_ROLE}:{self.migrate_password}@{common}",
            f"postgresql://{APP_ROLE}:{self.app_password}@{common}",
            database,
        )

    def provision_roles_and_database(self, database: str) -> None:
        migrate_url, app_url, _ = self._urls(database)
        _run(
            [self.python_exe, "scripts/provision_runtime_db_roles.py",
             "--provision",
             "--admin-url", self.admin_url,
             "--migrate-url", migrate_url,
             "--app-url", app_url],
            env={
                "MPANGO_DB_ADMIN_URL": self.admin_url,
                "MPANGO_DB_MIGRATE_URL": migrate_url,
                "MPANGO_DB_APP_URL": app_url,
                "MPANGO_DB_MIGRATE_PASSWORD": self.migrate_password,
                "MPANGO_DB_APP_PASSWORD": self.app_password,
            },
            verify=True, label=f"provision roles+db {database}",
        )
        print(f"[provision] {database}: roles + database wired")

    def run_migrations(self, database: str) -> str:
        migrate_url, _, _ = self._urls(database)
        result = _run(
            [self.python_exe, "-m", "alembic", "-c", "alembic.ini",
             "upgrade", "head"],
            env={
                "DATABASE_URL": migrate_url,
                "REPORTING_USER_PASSWORD": self.reporting_password,
            },
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"alembic upgrade head as {MIGRATE_ROLE} on {database} failed\n"
                f"{result.stdout[-4000:]}\n{result.stderr[-4000:]}"
            )
        head = _run([
            "docker", "exec", "-e",
            f"PGPASSWORD={self.migrate_password}", self.container,
            "psql", "-U", MIGRATE_ROLE, "-d", database, "-tAc",
            "SELECT version_num FROM public.alembic_version",
        ], verify=True, label=f"alembic_version probe {database}")
        print(f"[migrate] {database}: head={head.stdout.strip()} "
              f"(executed AS {MIGRATE_ROLE})")
        return head.stdout.strip()

    def apply_grants(self, database: str) -> None:
        migrate_url, app_url, _ = self._urls(database)
        result = _run(
            [self.python_exe, "scripts/provision_runtime_db_roles.py",
             "--apply-grants", "--verify",
             "--admin-url", self.admin_url,
             "--migrate-url", migrate_url,
             "--app-url", app_url],
            env={
                "MPANGO_DB_ADMIN_URL": self.admin_url,
                "MPANGO_DB_MIGRATE_URL": migrate_url,
                "MPANGO_DB_APP_URL": app_url,
            },
        )
        (self.evidence_dir / f"verify_{database}.json").write_text(
            result.stdout, encoding="utf-8"
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"apply grants/verify on {database} failed\n"
                f"{result.stdout[-4000:]}\n{result.stderr[-4000:]}"
            )
        print(f"[grants] {database}: minimum grants applied as "
              f"{MIGRATE_ROLE}; tool --verify ok")

    def induce_breakage(self, database: str, scenario: str) -> None:
        """Authority-side state changes that each negative scenario refuses.

        v3_wrongown reassigns the guard function to the runtime role.  Since
        PG16 an ALTER ... OWNER TO requires SET ROLE membership in the target
        role, so this misconfiguration — precisely what a deployment that ran
        migrations as the wrong role produces — is induced by the cluster
        administrator here, not by the migration authority.
        """
        via_admin = scenario == "v3_wrongown"
        statements = {
            "v3_nofunc": [
                "DROP FUNCTION public.prevent_ledger_modification()",
            ],
            "v3_badsig": [
                # PostgreSQL refuses CREATE OR REPLACE with a changed return
                # type, so the incompatible-signature variant is installed by
                # DROP + CREATE (owner stays the migration authority).
                "DROP FUNCTION public.prevent_ledger_modification()",
                "CREATE FUNCTION public.prevent_ledger_modification() "
                "RETURNS void AS $$ BEGIN END $$ LANGUAGE plpgsql",
            ],
            "v3_wrongown": [
                "ALTER FUNCTION public.prevent_ledger_modification() "
                f"OWNER TO {APP_ROLE}",
            ],
            "v3_nopriv": [
                "REVOKE EXECUTE ON FUNCTION "
                "public.prevent_ledger_modification() FROM PUBLIC",
                "REVOKE EXECUTE ON FUNCTION "
                f"public.prevent_ledger_modification() FROM {APP_ROLE}",
            ],
        }.get(scenario, [])
        if not statements:
            return
        if via_admin:
            # same admin user, but connected to the SCENARIO database
            url = self.admin_url.rsplit("/", 1)[0] + "/" + database
            connector = "admin"
        else:
            url = self._urls(database)[0]
            connector = MIGRATE_ROLE

        async def _apply() -> None:
            conn = await asyncpg.connect(url)
            try:
                for statement in statements:
                    await conn.execute(statement)
            finally:
                await conn.close()

        asyncio.run(_apply())
        print(f"[breakage] {database}: induced {scenario} (as {connector})")

    def snapshot_guard(self, database: str) -> dict:
        migrate_url, _, _ = self._urls(database)

        async def _snapshot() -> dict:
            conn = await asyncpg.connect(migrate_url)
            try:
                row = await conn.fetchrow(
                    "SELECT (to_regprocedure("
                    "'public.prevent_ledger_modification()') IS NOT NULL) "
                    "AS function_exists, "
                    "pg_get_userbyid(p.proowner) AS owner, "
                    "format_type(p.prorettype, NULL) AS return_type, "
                    "pg_get_function_identity_arguments(p.oid) AS args, "
                    "md5(pg_get_functiondef(p.oid)) AS definition_md5 "
                    "FROM pg_proc p "
                    "LEFT JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE (p.oid = to_regprocedure("
                    "'public.prevent_ledger_modification()')) "
                    "OR p.oid IS NULL LIMIT 1"
                )
                return dict(row) if row else {"function_exists": False}
            finally:
                await conn.close()

        return asyncio.run(_snapshot())

    # ----------------------------------------------------------------- suite
    def _write_manifest(self, label: str) -> Path:
        manifest = {
            "active_scenario": None,
            "cluster_system_identifier":
                self.report.get("cluster_system_identifier"),
            "server_version_num": self.report.get("server_version_num"),
            "admin_url": self.admin_url,
            "scenarios": {},
        }
        for name in SCENARIOS:
            migrate, app, database = self._urls(name)
            manifest["scenarios"][name] = {
                "migrate_url": migrate,
                "app_url": app,
                "database": database,
                "guard": self.snapshots.get(name, {}),
            }
        path = self.work_dir / f"manifest_{label}.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return path

    def run_suite(self, scenario: str, *, label: str) -> dict:
        _, app_url, _ = self._urls(scenario)
        manifest_path = self._write_manifest(label)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["active_scenario"] = scenario
        manifest_path.write_text(json.dumps(manifest, indent=2),
                                 encoding="utf-8")
        outcome = _run(
            [self.python_exe, "-m", "pytest", TEST_FILE, "-v",
             "--no-header", "-rA", "--tb=short"],
            env={
                "DATABASE_URL": app_url,
                "MPANGO_ENV": "test",
                "MPANGO_MIGRATION_AUTHORITY_ROLE": MIGRATE_ROLE,
                "MPANGO_DB_APP_ROLE": APP_ROLE,
                "MPANGO_DB_AUTHORITY_MANIFEST": str(manifest_path),
                "MPANGO_DB_AUTHORITY_SCENARIO": scenario,
                "REPORTING_USER_PASSWORD": self.reporting_password,
            },
        )
        output_path = self.evidence_dir / f"pytest_{label}.log"
        output_path.write_text(
            f"$ pytest {TEST_FILE} (scenario={scenario}, label={label})\n"
            f"rc={outcome.returncode}\n\n{outcome.stdout}\n{outcome.stderr}",
            encoding="utf-8",
        )
        failed, errored = _failed_nodeids(outcome.stdout)
        summary = {
            "scenario": scenario,
            "label": label,
            "rc": outcome.returncode,
            "failed": sorted(failed),
            "errors": sorted(errored),
            "log": output_path.name,
        }
        print(f"[suite] {label}: rc={outcome.returncode} "
              f"failed={len(failed)} errors={len(errored)}")
        return summary

    # -------------------------------------------------------------- mutation
    def _patch_bootstrap(self, original_bytes: bytes, old_lf: str,
                         new_lf: str) -> None:
        text = original_bytes.decode("utf-8")
        eol = "\r\n" if "\r\n" in text else "\n"

        def _to_eol(sample: str) -> str:
            return sample.replace("\n", eol) if eol != "\n" else sample

        old, new = _to_eol(old_lf), _to_eol(new_lf)
        assert old in text, f"mutation anchor not found: {old_lf!r}"
        BOOTSTRAP_SCRIPT.write_bytes(
            text.replace(old, new, 1).encode("utf-8")
        )

    def run_mutations(self) -> list[dict]:
        results: list[dict] = []
        original_bytes = BOOTSTRAP_SCRIPT.read_bytes()
        original_sha = _sha256(BOOTSTRAP_SCRIPT)
        self.report["bootstrap_script_sha256"] = original_sha

        mutations = [] if self.skip_mutations else [
            {
                "name": "M1",
                "title": "runtime_create_or_replace_reintroduced",
                "apply": lambda: self._patch_bootstrap(
                    original_bytes, MUTATION_M1_ANCHOR,
                    MUTATION_M1_SNIPPET + MUTATION_M1_ANCHOR,
                ),
                "scenario": "v3_ok",
                "named_red": sorted(MUTATION_M1_NAMED_RED),
                "rationale": (
                    "reintroducing the runtime CREATE OR REPLACE of the "
                    "migration-owned public guard must be refused by "
                    "PostgreSQL (the runtime role is not the owner and holds "
                    "no CREATE privilege on public); the lifecycle must fail "
                    "closed with zero active tenant and the guard must stay "
                    "migration-owned"
                ),
            },
            {
                "name": "M2",
                "title": "ownership_precondition_removed",
                "apply": lambda: self._patch_bootstrap(
                    original_bytes, MUTATION_M2_TARGET,
                    MUTATION_M2_REPLACEMENT,
                ),
                "scenario": "v3_wrongown",
                "named_red": sorted(MUTATION_M2_NAMED_RED),
                "rationale": (
                    "removing the ownership precondition must let a "
                    "runtime-owned guard through; the wrong-owner negative "
                    "tests are the named RED detectors proving the "
                    "precondition is load-bearing"
                ),
            },
        ]
        try:
            for mutation in mutations:
                mutation["apply"]()
                mutated_sha = _sha256(BOOTSTRAP_SCRIPT)
                run = self.run_suite(
                    mutation["scenario"],
                    label=f"mutation_{mutation['name']}",
                )
                red_nodes = set(run["failed"]) | set(run["errors"])
                named_hits = sorted(red_nodes & set(mutation["named_red"]))
                results.append({
                    "mutation": mutation["name"],
                    "title": mutation["title"],
                    "scenario": mutation["scenario"],
                    "rationale": mutation["rationale"],
                    "named_red_expected": mutation["named_red"],
                    "mutated_sha256": mutated_sha,
                    "run": run,
                    "went_red": run["rc"] != 0 and bool(red_nodes),
                    "named_red_hits": named_hits,
                })
                print(f"[mutation] {mutation['name']}: went_red="
                      f"{run['rc'] != 0} named={named_hits}")
        finally:
            BOOTSTRAP_SCRIPT.write_bytes(original_bytes)
            restored_sha = _sha256(BOOTSTRAP_SCRIPT)
            for result in results:
                result["restored_sha256"] = restored_sha
                result["byte_identical_restore"] = (
                    restored_sha == original_sha
                )
                if result.get("mutation"):
                    assert result["byte_identical_restore"], (
                        f"{result['mutation']}: restore not byte-identical"
                    )
            print(f"[mutation] restored bootstrap script "
                  f"(sha256={restored_sha[:16]}...) byte-identical")

        post = self.run_suite("v3_ok", label="post_restore")
        results.append({
            "mutation": None,
            "title": "post_restore_reproducibility",
            "run": post,
            "post_restore_green": post["rc"] == 0,
        })
        print(f"[mutation] post-restore v3_ok run green={post['rc'] == 0}")
        return results

    # ------------------------------------------------------------------ main
    def run(self) -> dict:
        try:
            self.start_container()
            heads: dict[str, str] = {}
            for scenario in SCENARIOS:
                self.provision_roles_and_database(scenario)
            for scenario in SCENARIOS:
                heads[scenario] = self.run_migrations(scenario)
            for scenario in SCENARIOS:
                self.apply_grants(scenario)
            for scenario in SCENARIOS:
                self.induce_breakage(scenario, scenario)
            for scenario in SCENARIOS:
                self.snapshots[scenario] = self.snapshot_guard(scenario)

            suite_runs = []
            for scenario in SCENARIOS:
                suite_runs.append(self.run_suite(scenario, label=scenario))
            for run in suite_runs:
                assert run["rc"] == 0, (
                    f"scenario {run['scenario']} did not pass: "
                    f"failed={run['failed']} errors={run['errors']}"
                )

            mutation_results = self.run_mutations()
            for result in mutation_results:
                if result.get("mutation"):
                    assert result["went_red"], (
                        f"{result['mutation']} did NOT go RED"
                    )
                    assert result["named_red_hits"], (
                        f"{result['mutation']} missed its named RED set"
                    )
                else:
                    assert result["post_restore_green"], (
                        "post-restore run is not green"
                    )

            self.report["phases"] = {
                "alembic_heads": heads,
                "suite_runs": suite_runs,
                "mutations": mutation_results,
                "guard_snapshots": self.snapshots,
                "bootstrap_script_sha256_restored": _sha256(BOOTSTRAP_SCRIPT),
                "grants_script_sha256": _sha256(GRANTS_SCRIPT),
                "finished_at": _utc(),
            }
            self.report["verdict"] = "PASS"
            return self.report
        except Exception as exc:  # noqa: BLE001
            self.report["verdict"] = "FAIL"
            self.report["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._write_report()
            if not self.keep:
                self.stop_container()

    def _write_report(self) -> None:
        payload = json.loads(json.dumps(self.report, default=str))
        blob = json.dumps(_group_hex_strings(payload), indent=2)
        for secret in (self.admin_password, self.migrate_password,
                       self.app_password, self.reporting_password):
            blob = blob.replace(secret, "***REDACTED***")
        blob = re.sub(r"(postgresql://[^:/\"]+:)[^@\"]+@", r"\1***@", blob)
        target = self.evidence_dir / "harness_report.json"
        target.write_text(blob, encoding="utf-8")
        print(f"[evidence] wrote {target}")


_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{32,64}$")


def _group_hex_strings(obj):
    """Group raw hex digests into 8-char chunks (repo secret-scanner
    convention, mirroring the kimi smtp R2 evidence): integrity digests are
    published in grouped form; strip spaces to compare."""
    if isinstance(obj, dict):
        return {key: _group_hex_strings(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_group_hex_strings(value) for value in obj]
    if isinstance(obj, str) and _HEX_DIGEST_RE.fullmatch(obj):
        return " ".join(obj[index:index + 8] for index in range(0, len(obj), 8))
    return obj


def _failed_nodeids(pytest_output: str) -> tuple[set[str], set[str]]:
    failed: set[str] = set()
    errored: set[str] = set()
    for match in re.finditer(
        r"^(FAILED|ERROR) (tests/\S+)", pytest_output, re.MULTILINE
    ):
        (failed if match.group(1) == "FAILED" else errored).add(
            match.group(2)
        )
    for match in re.finditer(
        r"^(tests/\S+) (FAILED|ERROR)", pytest_output, re.MULTILINE
    ):
        (failed if match.group(2) == "FAILED" else errored).add(
            match.group(1)
        )
    return failed, errored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--image", default=IMAGE_DEFAULT)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--keep", action="store_true",
                        help="keep the container after the run")
    parser.add_argument("--skip-mutations", action="store_true")
    args = parser.parse_args()

    harness = Harness(
        evidence_dir=args.evidence_dir, image=args.image, keep=args.keep,
        python_exe=args.python, skip_mutations=args.skip_mutations,
    )
    report = harness.run()
    print(f"HARNESS {report['verdict']}")


if __name__ == "__main__":
    main()
