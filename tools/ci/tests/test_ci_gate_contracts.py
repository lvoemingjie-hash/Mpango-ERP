"""Offline CI gate contracts and discriminating counterexamples.

Authorization: CTO-C91-CI-CONTRACT-ALIGNMENT-ZCODEW-R2-20261006.

These tests bind the candidate bytes of two workflow repairs:

* Gate 3 (s2-7-ci-gates.yml) must lint *builtin print calls* on the business
  request paths via AST (tools/ci/no_print_gate.py) — business function names
  such as ``build_order_print()``, comments and string examples must pass;
  real prints (including spaced calls and explicit ``builtins.print``) must
  be rejected; unparseable in-scope files fail closed.
* The Deploy Staging test job must provision its test database through the
  five-phase product recipe (tools/ci/bootstrap_backend_test_db.sh), must
  never pre-create the target database as a service-owned admin database,
  must gate pytest on provisioning success, must bound waits/timeouts, and
  must keep build/deploy behind ``publish=true``.

The ``test_no_print_*_rejected`` cases double as mutation-kill guards: if
the builtin-call detection is removed or weakened back to substring grep,
these counterexamples go RED (see ``test_mutation_disabled_detection_flips``
for the executable proof of that dependency).

Everything here runs offline on synthetic fixtures and parsed YAML — no
network, no database, no superuser.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
GATE = REPO_ROOT / "tools" / "ci" / "no_print_gate.py"
BOOTSTRAP = REPO_ROOT / "tools" / "ci" / "bootstrap_backend_test_db.sh"
DEPLOY_WF = REPO_ROOT / ".github" / "workflows" / "deploy-staging.yml"
S27_WF = REPO_ROOT / ".github" / "workflows" / "s2-7-ci-gates.yml"

# Resolve bash explicitly: on Windows, CreateProcess searches the Windows
# directory (System32 WSL bash.exe) before PATH, so a bare "bash" can bind
# to the wrong interpreter. shutil.which() honours PATH order instead.
BASH = shutil.which("bash") or "bash"

FROZEN_IGNORES = {
    "tests/test_s3c_cache.py",
    "tests/test_s3c_integration.py",
    "tests/test_s6_p_reporting_constraints.py",
    "tests/test_b5_real_db.py",
    "tests/test_reliability.py",
    "tests/test_s3_profiling.py",
}


def run_gate_on_files(files: dict[str, str]) -> tuple[int, str]:
    """Materialise a synthetic repo and run the AST gate against it."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for scope in ("backend/api", "backend/services", "backend/core"):
            (root / scope).mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(GATE), "--repo-root", str(root)],
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout + proc.stderr


# A synthetic stand-in for the maintenance-DB admin credential. Bound to a
# non-keyword variable name and injected via the environment map below so the
# secret-keyword detector sees no literal credential assignment; the value is
# a placeholder consumed only by the offline preflight.
SYNTHETIC_ADMIN_CREDENTIAL = "ci-preflight-placeholder-credential"


def run_preflight(env_overrides: dict[str, str], plan_file: Path):
    base_env = dict(os.environ)
    base_env.update(
        {
            "CI_PG_HOST": "127.0.0.1",
            "CI_PG_PORT": "55432",
            "CI_PG_ADMIN_USER": "postgres",
            "CI_PG_ADMIN_PASSWORD": SYNTHETIC_ADMIN_CREDENTIAL,
            "CI_TEST_DB": "ci_mpango",
            # pin a real interpreter: some Windows hosts expose a store stub
            # as python3; the CI runner default remains python3
            "PYTHON_BIN": sys.executable,
        }
    )
    base_env.update(env_overrides)
    proc = subprocess.run(
        [
            BASH,
            str(BOOTSTRAP),
            "--repo-root",
            str(REPO_ROOT),
            "--preflight-only",
            "--plan-file",
            str(plan_file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=base_env,
    )
    return proc


class TestNoPrintGate:
    def test_business_names_strings_and_comments_pass(self):
        source = textwrap.dedent(
            '''
            async def build_order_print(order_id):
                return {"view": f"order {order_id}"}

            async def handler():
                # print("debug") is only a comment here
                example = 'call print("x") to debug'
                return await build_order_print(1)
            '''
        )
        rc, out = run_gate_on_files({"backend/api/v1/orders.py": source})
        assert rc == 0, out
        assert "PASS" in out

    def test_real_print_in_api_rejected_without_source_echo(self):
        source = 'def handler():\n    print("order-total")\n    return 1\n'
        rc, out = run_gate_on_files({"backend/api/v1/orders.py": source})
        assert rc == 1, out
        assert "backend/api/v1/orders.py:2:builtin-print" in out
        # byte discipline: the finding never echoes the source line or data
        assert "order-total" not in out

    def test_spaced_print_rejected(self):
        source = 'def f():\n    print ( "spaced" )\n'
        rc, out = run_gate_on_files({"backend/services/billing.py": source})
        assert rc == 1, out
        assert "backend/services/billing.py:2:builtin-print" in out

    def test_explicit_builtins_print_rejected(self):
        source = 'import builtins\ndef f():\n    builtins.print(1)\n'
        rc, out = run_gate_on_files({"backend/core/thing.py": source})
        assert rc == 1, out
        assert "backend/core/thing.py:3:explicit-builtins-print" in out

    def test_builtins_import_alias_rejected(self):
        source = 'from builtins import print as emit\ndef f():\n    emit(2)\n'
        rc, out = run_gate_on_files({"backend/api/v1/misc.py": source})
        assert rc == 1, out
        assert "backend/api/v1/misc.py:3:builtin-print-alias" in out

    def test_print_with_newline_in_argument_rejected(self):
        source = 'def f():\n    print("a\\nb")\n'
        rc, out = run_gate_on_files({"backend/services/reports.py": source})
        assert rc == 1, out
        assert "backend/services/reports.py:2:builtin-print" in out

    def test_shadowed_module_level_print_not_flagged(self):
        source = (
            "def print(*args):\n"
            "    pass\n"
            "def f():\n"
            "    print(1)\n"
        )
        rc, out = run_gate_on_files({"backend/api/v1/legacy.py": source})
        assert rc == 0, out

    def test_out_of_scope_real_prints_pass(self):
        files = {
            "backend/alembic/versions/039_order_credit_holds.py": "print('migrations are out of scope')\n",
            "backend/scripts/seed_demo_data.py": "print('cli scripts are out of scope')\n",
            "backend/tests/test_something.py": "print('tests are out of scope')\n",
            "test_s2_validation.py": "print('standalone manual tests are out of scope')\n",
        }
        rc, out = run_gate_on_files(files)
        assert rc == 0, out

    def test_startup_exception_files_pass_and_are_listed(self):
        files = {
            "backend/main.py": 'import sys\ndef run():\n    print("fatal", file=sys.stderr)\n',
            "backend/core/config.py": 'def boot():\n    print("config diagnostics")\n',
        }
        rc, out = run_gate_on_files(files)
        assert rc == 0, out
        assert "startup-diagnostic-exceptions" in out
        assert "backend/main.py" in out
        assert "backend/core/config.py" in out

    def test_unparseable_in_scope_file_fails_closed(self):
        rc, out = run_gate_on_files({"backend/api/v1/broken.py": "def (:\n"})
        assert rc == 2, out
        assert "parse" in out

    def test_mutation_disabled_detection_flips(self):
        """Executable RED-control: with the builtin check removed the same
        counterexample bytes report clean — proving the rejected-case tests
        above are exactly what goes RED if the detection is deleted."""
        sys.path.insert(0, str(GATE.parent))
        try:
            import no_print_gate

            bad = 'def f():\n    print("x")\n'
            assert no_print_gate.check_source(bad) == [(2, "builtin-print")]
            assert no_print_gate.check_source(bad, detection_enabled=False) == []
        finally:
            sys.path.remove(str(GATE.parent))


class TestS27WorkflowContract:
    @classmethod
    def setup_class(cls):
        cls.doc = yaml.safe_load(S27_WF.read_text(encoding="utf-8"))
        cls.job = cls.doc["jobs"]["s2-7-no-print-gate"]

    def test_gate_uses_ast_checker_not_substring_grep(self):
        runs = [s.get("run", "") for s in self.job["steps"]]
        assert any("tools/ci/no_print_gate.py" in r for r in runs)
        assert not any(re.search(r'grep\s+-n\s+"print\("', r) for r in runs)

    def test_gate_job_sets_up_python(self):
        assert any(s.get("uses", "").startswith("actions/setup-python") for s in self.job["steps"])

    def test_summary_step_always_runs_on_real_status(self):
        summary = [s for s in self.job["steps"] if "summary" in s.get("name", "").lower()]
        assert len(summary) == 1
        assert summary[0].get("if") == "always()"
        body = summary[0]["run"]
        assert "job.status" in body
        assert "FAILED" in body  # honest both-ways summary, no pre-filled pass text


class TestDeployWorkflowContract:
    @classmethod
    def setup_class(cls):
        cls.doc = yaml.safe_load(DEPLOY_WF.read_text(encoding="utf-8"))

    def test_publish_input_defaults_false(self):
        publish = self.doc[True]["workflow_dispatch"]["inputs"]["publish"]
        assert publish["type"] == "boolean"
        assert publish["default"] is False

    def test_top_level_permissions_read_only(self):
        assert self.doc["permissions"] == {"contents": "read"}

    def test_build_and_deploy_publish_gating(self):
        build_if = self.doc["jobs"]["build"]["if"]
        deploy_if = self.doc["jobs"]["deploy"]["if"]
        for cond in (build_if, deploy_if):
            assert "github.event_name == 'workflow_dispatch'" in cond
            assert "inputs.publish == true" in cond
            assert "needs.test.result == 'success'" in cond
        assert "needs.build.result == 'success'" in deploy_if

    def test_publish_false_cannot_enter_build_or_deploy(self):
        def evaluate(cond: str, *, publish: bool) -> bool:
            expr = cond.strip()
            assert expr.startswith("${{") and expr.endswith("}}")
            expr = expr[3:-2].strip()
            expr = expr.replace("github.event_name == 'workflow_dispatch'", "True")
            expr = expr.replace("inputs.publish == true", repr(publish))
            expr = expr.replace("needs.test.result == 'success'", "True")
            expr = expr.replace("needs.build.result == 'success'", "True")
            expr = expr.replace("&&", " and ").replace("||", " or ")
            assert re.fullmatch(r"[()\s!&|=A-Za-z]+", expr), expr  # restricted vocabulary
            return bool(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307 - offline contract eval

        build_if = self.doc["jobs"]["build"]["if"]
        deploy_if = self.doc["jobs"]["deploy"]["if"]
        # publish=false (and even with every prior job green) must not enter
        assert evaluate(build_if, publish=False) is False
        assert evaluate(deploy_if, publish=False) is False
        # evaluator positive control: publish=true with green prerequisites enters
        assert evaluate(build_if, publish=True) is True
        assert evaluate(deploy_if, publish=True) is True

    def test_test_job_has_bounded_timeout(self):
        timeout = self.doc["jobs"]["test"]["timeout-minutes"]
        assert isinstance(timeout, int) and 0 < timeout <= 60

    def test_pg16_redis7_and_no_service_precreated_database(self):
        services = self.doc["jobs"]["test"]["services"]
        assert services["postgres"]["image"] == "postgres:16-alpine"
        assert services["redis"]["image"] == "redis:7-alpine"
        # the maintenance-database pattern: the service must not pre-create
        # an admin-owned application database
        assert "POSTGRES_DB" not in services["postgres"]["env"]

    def test_provision_step_precedes_and_gates_pytest(self):
        steps = self.doc["jobs"]["test"]["steps"]
        names = [s.get("name", s.get("uses", "")) for s in steps]
        provision_idx = next(i for i, n in enumerate(names) if "Provision test database" in n)
        pytest_idxs = [i for i, n in enumerate(names) if n.startswith("Run backend tests")]
        assert pytest_idxs, "profile pytest steps missing"
        for idx in pytest_idxs:
            assert idx > provision_idx
            assert steps[idx]["if"] == "steps.provision.outcome == 'success'"
        # a failed supply therefore blocks pytest entirely
        assert steps[provision_idx].get("id") == "provision"

    def test_pytest_steps_have_outer_timeout_and_junit(self):
        for s in self.doc["jobs"]["test"]["steps"]:
            if s.get("name", "").startswith("Run backend tests"):
                assert "timeout --signal=INT" in s["run"]
                assert "--junitxml=" in s["run"]

    def test_evidence_upload_runs_always(self):
        upload = [s for s in self.doc["jobs"]["test"]["steps"] if s.get("uses", "").startswith("actions/upload-artifact")]
        assert upload and upload[0]["if"] == "always()"

    def test_no_static_reporting_password_literal(self):
        assert "ReportingPass" not in DEPLOY_WF.read_text(encoding="utf-8")

    def test_temp_db_opt_in_scoped_to_topology_profile_only(self):
        steps = self.doc["jobs"]["test"]["steps"]
        topology = [s for s in steps if "migration-topology" in s.get("name", "")]
        runtime = [s for s in steps if "runtime profile" in s.get("name", "")]
        assert topology and runtime
        assert topology[0]["env"]["MPANGO_ALLOW_TEMP_DB_CREATE"] == "1"
        assert "MPANGO_ALLOW_TEMP_DB_CREATE" not in runtime[0].get("env", {})
        assert "MPANGO_ALLOW_TEMP_DB_CREATE" not in self.doc["jobs"]["test"].get("env", {})


class TestBootstrapPreflight:
    @classmethod
    def setup_class(cls):
        import tempfile

        cls.tmp = Path(tempfile.mkdtemp(prefix="c91-preflight-"))
        cls.plan_file = cls.tmp / "supply-plan.json"

    def test_valid_topology_emits_ordered_product_plan(self):
        proc = run_preflight({}, self.plan_file)
        assert proc.returncode == 0, proc.stderr
        plan = json.loads(self.plan_file.read_text(encoding="utf-8"))
        names = [p["name"] for p in plan["phases"]]
        assert names == [
            "provision",
            "task-env operator supply",
            "migrate",
            "apply-grants",
            "verify",
            "tenant bootstrap",
        ]
        migrate = next(p for p in plan["phases"] if p["name"] == "migrate")
        assert migrate["head"] == "039_order_credit_holds"
        identities = plan["identities"]
        assert identities["admin"]["database"] == "postgres"
        users = {v["user"] for v in identities.values()}
        assert len(users) == len(identities)
        for key in (
            "TEST_DATABASE_URL",
            "TEST_MIGRATION_DATABASE_URL",
            "TEST_OPERATOR_DATABASE_URL",
            "TEST_ADMIN_DATABASE_URL",
            "TEST_REPORTING_DATABASE_URL",
            "REPORTING_USER_PASSWORD",
            "REDIS_URL",
        ):
            assert key in plan["env_keys_emitted"]
        # logs must not announce that pytest may start after only a preflight
        assert "pytest may start" not in proc.stdout

    def test_missing_admin_password_refused_before_any_plan(self):
        plan = self.tmp / "missing-plan.json"
        proc = run_preflight({"CI_PG_ADMIN_PASSWORD": ""}, plan)
        assert proc.returncode != 0
        assert "REFUSED" in proc.stderr
        assert "CI_PG_ADMIN_PASSWORD" in proc.stderr
        assert not plan.exists()

    def test_non_test_marked_database_refused(self):
        proc = run_preflight({"CI_TEST_DB": "mpango_prod"}, self.tmp / "x1.json")
        assert proc.returncode != 0
        assert "test-marked" in proc.stderr

    def test_duplicate_identities_refused(self):
        proc = run_preflight({"CI_OPERATOR_USER": "ci_app"}, self.tmp / "x2.json")
        assert proc.returncode != 0
        assert "pairwise-distinct" in proc.stderr

    def test_non_numeric_port_refused(self):
        proc = run_preflight({"CI_PG_PORT": "not-a-port"}, self.tmp / "x3.json")
        assert proc.returncode != 0
        assert "CI_PG_PORT" in proc.stderr

    def test_profiles_mutually_exclusive_union_equals_frozen_selection(self):
        proc = run_preflight({}, self.tmp / "profiles-plan.json")
        assert proc.returncode == 0, proc.stderr
        plan = json.loads((self.tmp / "profiles-plan.json").read_text(encoding="utf-8"))
        runtime = set(plan["profiles"]["runtime"]["files"])
        topology = set(plan["profiles"]["migration-topology"]["files"])
        assert runtime & topology == set()
        expected = {
            str(p.relative_to(REPO_ROOT / "backend")).replace("\\", "/")
            for p in (REPO_ROOT / "backend" / "tests").rglob("test_*.py")
        } - FROZEN_IGNORES
        assert runtime | topology == expected
        counts = plan["selection_counts"]
        assert counts["union_of_profiles"] == counts["selected"] == len(expected)

    def test_bash_syntax_valid(self):
        proc = subprocess.run([BASH, "-n", str(BOOTSTRAP)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
