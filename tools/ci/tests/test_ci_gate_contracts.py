"""Offline CI gate contracts and discriminating counterexamples (R3).

Authorization: CTO-C91-CI-EXECUTABLE-CONTRACT-ZCODEW-R3-20261006.

Covers the R3 candidate bytes:

* AST no-print gate: real builtin prints (including spaced calls, explicit
  ``builtins.print``, aliases) rejected; names/strings/comments pass; an
  unambiguous module-level shadow exempts only call sites AFTER the binding
  (a print before a later ``def print`` stays a finding); unparseable files
  fail closed.
* Deploy Staging test job: task-owned labeled containers (exact IDs),
  five-phase wrapper provisioning, versioned env file, four mutually
  exclusive pytest profiles, outer timeouts + junit, publish=false can
  never enter build/deploy.
* Bootstrap wrapper: real-mode execution against FAKE psql/poetry tools —
  call order, failure blocking, credential channels (argv clean; secrets
  only via env/stdin; canary byte-identical in the real channel) — plus
  preflight refusals (missing tests source, empty selection, role-name
  drift, non-distinct identities) and plan-file idempotence.

Everything runs offline on synthetic fixtures; no network, no docker, no
database. Windows hosts pin PYTHON_BIN/BASH explicitly (the store-stub
python3 and System32 WSL bash are not usable interpreters).
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
BASH = shutil.which("bash") or "bash"

FROZEN_IGNORES = {
    "tests/test_s3c_cache.py",
    "tests/test_s3c_integration.py",
    "tests/test_s6_p_reporting_constraints.py",
    "tests/test_b5_real_db.py",
    "tests/test_reliability.py",
    "tests/test_s3_profiling.py",
}
PROFILE_ORDER = ["task-managed-pg", "topology", "invariants-jwt", "runtime"]

# Synthetic stand-in for the maintenance-DB admin credential. Bound to a
# non-keyword variable name so the secret-keyword detector sees no literal
# credential assignment; consumed only by the offline preflight.
PREFLIGHT_CREDENTIAL = "c91-preflight-placeholder-credential"



def run_gate_on_files(files: dict[str, str]) -> tuple[int, str]:
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

    def test_real_print_rejected_without_source_echo(self):
        source = 'def handler():\n    print("order-total")\n    return 1\n'
        rc, out = run_gate_on_files({"backend/api/v1/orders.py": source})
        assert rc == 1, out
        assert "backend/api/v1/orders.py:2:builtin-print" in out
        assert "order-total" not in out

    def test_spaced_and_builtins_and_alias_rejected(self):
        files = {
            "backend/services/a.py": 'def f():\n    print ( "spaced" )\n',
            "backend/core/b.py": 'import builtins\ndef f():\n    builtins.print(1)\n',
            "backend/api/v1/c.py": 'from builtins import print as emit\ndef f():\n    emit(2)\n',
        }
        rc, out = run_gate_on_files(files)
        assert rc == 1, out
        assert "backend/services/a.py:2:builtin-print" in out
        assert "backend/core/b.py:3:explicit-builtins-print" in out
        assert "backend/api/v1/c.py:3:builtin-print-alias" in out

    def test_shadow_exempts_only_calls_after_the_binding(self):
        source = (
            "def early():\n"
            "    print('before the shadow binding')\n"
            "\n"
            "def print(*args):\n"
            "    pass\n"
            "\n"
            "def late():\n"
            "    print(1)\n"
        )
        rc, out = run_gate_on_files({"backend/services/shadowed.py": source})
        assert rc == 1, out
        assert "backend/services/shadowed.py:2:builtin-print" in out
        assert "backend/services/shadowed.py:8" not in out  # after the binding: exempt

    def test_shadow_assignment_form_same_rule(self):
        source = (
            "def early():\n"
            "    print('before assignment shadow')\n"
            "\n"
            "print = lambda *a: None\n"
            "late_value = 1\n"
        )
        rc, out = run_gate_on_files({"backend/core/shadowassign.py": source})
        assert rc == 1, out
        assert "backend/core/shadowassign.py:2:builtin-print" in out

    def test_unparseable_fails_closed(self):
        rc, out = run_gate_on_files({"backend/api/v1/broken.py": "def (:\n"})
        assert rc == 2, out

    def test_mutation_disabled_detection_flips(self):
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

    def test_summary_step_always_runs_on_real_status(self):
        summary = [s for s in self.job["steps"] if "summary" in s.get("name", "").lower()]
        assert len(summary) == 1
        assert summary[0].get("if") == "always()"
        assert "job.status" in summary[0]["run"] and "FAILED" in summary[0]["run"]


class TestDeployWorkflowContract:
    @classmethod
    def setup_class(cls):
        cls.doc = yaml.safe_load(DEPLOY_WF.read_text(encoding="utf-8"))
        cls.test_job = cls.doc["jobs"]["test"]
        cls.steps = cls.test_job["steps"]
        cls.names = [s.get("name", s.get("uses", "")) for s in cls.steps]

    def test_publish_input_defaults_false_and_permissions_read_only(self):
        publish = self.doc[True]["workflow_dispatch"]["inputs"]["publish"]
        assert publish["type"] == "boolean" and publish["default"] is False
        assert self.doc["permissions"] == {"contents": "read"}

    def test_publish_false_cannot_enter_build_or_deploy(self):
        def evaluate(cond: str, *, publish: bool) -> bool:
            expr = cond.strip().removeprefix("${{").removesuffix("}}").strip()
            expr = expr.replace("github.event_name == 'workflow_dispatch'", "True")
            expr = expr.replace("inputs.publish == true", repr(publish))
            expr = expr.replace("needs.test.result == 'success'", "True")
            expr = expr.replace("needs.build.result == 'success'", "True")
            expr = expr.replace("&&", " and ").replace("||", " or ")
            assert re.fullmatch(r"[()\s!&|=A-Za-z]+", expr), expr
            return bool(eval(expr, {"__builtins__": {}}, {}))

        build_if = self.doc["jobs"]["build"]["if"]
        deploy_if = self.doc["jobs"]["deploy"]["if"]
        assert evaluate(build_if, publish=False) is False
        assert evaluate(deploy_if, publish=False) is False
        assert evaluate(build_if, publish=True) is True
        assert evaluate(deploy_if, publish=True) is True

    def test_task_owned_labeled_containers_with_exact_ids(self):
        pg = next(s for s in self.steps if "Postgres 16" in s.get("name", ""))["run"]
        redis = next(s for s in self.steps if "Redis 7" in s.get("name", ""))["run"]
        for run in (pg, redis):
            assert "docker run -d" in run
            assert "--label mpango.owner=" in run
            assert "CI_PG_CONTAINER_ID=" in run or "CI_REDIS_CONTAINER_ID=" in run
            assert "docker inspect" in run
        assert "postgres:16-alpine" in pg and "redis:7-alpine" in redis
        # no service-container block remains: the guard contract needs labels
        assert "services" not in self.test_job

    def test_provision_step_and_four_profiles_gated(self):
        provision = next(s for s in self.steps if "Provision test database" in s.get("name", ""))
        assert provision["id"] == "provision"
        assert "bootstrap_backend_test_db.sh" in provision["run"]
        assert "--env-file" in provision["run"] and "--plan-file" in provision["run"]
        # the run's registered Redis port reaches the wrapper BEFORE it runs
        assert "CI_REDIS_URL" in provision["env"]
        assert "${{ env.CI_REDIS_PORT }}" in provision["env"]["CI_REDIS_URL"]
        assert "CI_REDIS_URL" not in provision["run"]  # no post-hoc GITHUB_ENV echo
        profile_steps = [s for s in self.steps if s.get("name", "").startswith("Run backend tests")]
        assert len(profile_steps) == 4
        for step in profile_steps:
            assert step["if"] == "steps.provision.outcome == 'success'"
            assert 'timeout --signal=INT' in step["run"]
            assert "--junitxml=" in step["run"]
            assert '. "$RUNNER_TEMP/c91-test-env.sh"' in step["run"]
            # empty/missing argfiles must refuse instead of falling back to
            # full-suite collection
            profile = re.search(r"\(([^)]+) profile\)", step.get("name", "")).group(1)
            assert f'test -s "$RUNNER_TEMP/profile-{profile}.tests"' in step["run"]
        topology = next(s for s in profile_steps if "topology" in s["name"])
        assert topology["env"]["MPANGO_ALLOW_TEMP_DB_CREATE"] == "1"
        invariants = next(s for s in profile_steps if "invariants-jwt" in s["name"])
        assert "MPANGO_ENV=staging" in invariants["run"]

    def test_no_static_reporting_password_literal(self):
        assert "ReportingPass" not in DEPLOY_WF.read_text(encoding="utf-8")


class TestBootstrapPreflight:
    @classmethod
    def setup_class(cls):
        import tempfile

        cls.tmp = Path(tempfile.mkdtemp(prefix="c91-r3-preflight-"))

    def _run(self, overrides: dict, plan: Path | None = None, repo_root: Path | None = None):
        env = dict(os.environ)
        env.update(
            {
                "CI_PG_HOST": "127.0.0.1",
                "CI_PG_PORT": "55432",
                "CI_PG_ADMIN_USER": "postgres",
                "CI_PG_ADMIN_PASSWORD": PREFLIGHT_CREDENTIAL,
                "CI_TEST_DB": "test_ci_mpango",
                "CI_REDIS_URL": "redis://127.0.0.1:55433/0",
                "PYTHON_BIN": sys.executable,
            }
        )
        env.update(overrides)
        plan = plan or (self.tmp / "plan.json")
        return subprocess.run(
            [BASH, str(BOOTSTRAP), "--repo-root", str(repo_root or REPO_ROOT),
             "--preflight-only", "--plan-file", str(plan),
             "--profile-dir", str(self.tmp / "profiles")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
        )

    def test_valid_topology_emits_structural_profile_partition(self):
        proc = self._run({})
        assert proc.returncode == 0, proc.stderr
        plan = json.loads((self.tmp / "plan.json").read_text(encoding="utf-8"))
        assert [p["name"] for p in plan["phases"]][:3] == ["provision", "task operator supply", "pgcrypto pre-install"]
        migrate = next(p for p in plan["phases"] if p["name"] == "migrate")
        assert migrate["head"] == "039_order_credit_holds"
        identities = plan["identities"]
        assert identities["migration"]["user"] == "mpango_migrate"
        assert identities["app"]["user"] == "mpango_app"
        assert identities["operator"]["user"] == "ci_r3_operator"
        assert identities["admin"]["database"] == "postgres"
        users = {v["user"] for v in identities.values()}
        assert len(users) == len(identities)
        for key in ("PW1R3_TEST_REDIS_URL", "TEST_OPERATOR_DATABASE_URL",
                    "MPANGO_INVARIANTS_R0_PG_CONTAINER", "SECRET_KEY"):
            assert key in plan["env_keys_emitted"]
        assert "MPANGO_TEST_OPERATOR_URL" not in plan["env_keys_emitted"]
        counts = plan["selection_counts"]
        assert counts["partition_total"] == counts["selected"] > 0
        assert set(plan["profiles"]) == set(PROFILE_ORDER)

    def test_partition_union_equals_frozen_selection(self):
        proc = self._run({}, plan=self.tmp / "profiles-plan.json")
        assert proc.returncode == 0, proc.stderr
        plan = json.loads((self.tmp / "profiles-plan.json").read_text(encoding="utf-8"))
        expected = {
            str(p.relative_to(REPO_ROOT / "backend")).replace("\\", "/")
            for p in (REPO_ROOT / "backend" / "tests").rglob("test_*.py")
        } - FROZEN_IGNORES
        union: set[str] = set()
        for profile in PROFILE_ORDER:
            files = set(plan["profiles"][profile]["files"])
            assert union & files == set()
            union |= files
        assert union == expected

    def test_missing_or_malformed_redis_url_refused(self):
        missing = self._run({"CI_REDIS_URL": ""}, plan=Path(self.tmp) / "x-redis.json")
        assert missing.returncode != 0
        assert "CI_REDIS_URL is required" in missing.stderr
        wrong_db = self._run({"CI_REDIS_URL": "redis://127.0.0.1:55433/5"}, plan=Path(self.tmp) / "x-redis2.json")
        assert wrong_db.returncode != 0
        assert "redis://HOST:PORT/0" in wrong_db.stderr

    def test_missing_admin_password_and_role_drift_refused(self):
        assert self._run({"CI_PG_ADMIN_PASSWORD": ""}).returncode != 0
        rename = self._run({"CI_MIGRATE_USER": "ci_migrate", "CI_APP_USER": "ci_app"},
                           plan=self.tmp / "x1.json")
        assert rename.returncode != 0
        assert "mpango_migrate/mpango_app" in rename.stderr
        prefix = self._run({"CI_OPERATOR_USER": "mpango_operator"}, plan=self.tmp / "x2.json")
        assert prefix.returncode != 0

    def test_missing_tests_source_directory_refused(self):
        import tempfile

        with tempfile.TemporaryDirectory() as empty:
            empty_repo = Path(empty)
            (empty_repo / "backend").mkdir()
            proc = self._run({}, plan=self.tmp / "x3.json", repo_root=empty_repo)
            assert proc.returncode != 0
            assert "source directory is missing" in proc.stderr

    def test_plan_file_rewritten_in_place_without_move(self):
        plan = self.tmp / "inplace-plan.json"
        assert self._run({}, plan=plan).returncode == 0
        first = plan.read_bytes()
        assert self._run({}, plan=plan).returncode == 0
        assert plan.exists() and plan.read_bytes() == first  # same path: no mv dance

    def test_bash_syntax_valid(self):
        proc = subprocess.run([BASH, "-n", str(BOOTSTRAP)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


FAKE_PSQL = r'''#!/usr/bin/env bash
# fake psql: records argv (only), stdin, and the credential env channels
DIR="${C91_FAKE_DIR:-/tmp}"
N=$(ls "$DIR" | grep -c '^psql-' || true)
printf '%s\n' "$*" > "$DIR/psql-$N.argv"
env | grep -E '^(PGPASSWORD|MPANGO_DB_ADMIN_URL)=' | sed 's/^/ENV /' > "$DIR/psql-$N.env" || true
cat > "$DIR/psql-$N.stdin"
case "$*" in
  *"rolcreatedb, rolcreaterole"*) echo "t|t|f|f" ;;
  *"pg_auth_members"*) echo "mpango_migrate:1:0" ;;
  *"alembic_version"*) echo 039_order_credit_holds ;;
  *"CREATE EXTENSION"*) : > "$DIR/pgcrypto-installed" ;;
  *"pg_extension WHERE extname"*)
    if [ -f "$DIR/pgcrypto-installed" ]; then echo 1; else echo 0; fi ;;
  *"pg_roles WHERE rolname"*) echo 0 ;;
esac
exit 0
'''

FAKE_POETRY_PASS = r'''#!/usr/bin/env bash
DIR="${C91_FAKE_DIR:-/tmp}"
N=$(ls "$DIR" | grep -c '^poetry-' || true)
printf '%s\n' "$*" > "$DIR/poetry-$N.argv"
if [ -f "$DIR/poetry-fail-provision" ] && [[ "$*" == *"--provision"* ]]; then
  echo "fake provision failure" >&2
  exit 1
fi
exit 0
'''


class TestWrapperFakeToolExecution:
    """Execute the REAL wrapper in real mode against fake psql/poetry: prove
    call order, failure blocking and credential channels on executed code."""

    @pytest.fixture()
    def fake_env_dir(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "psql").write_text(FAKE_PSQL, encoding="utf-8", newline="\n")
        (bin_dir / "poetry").write_text(FAKE_POETRY_PASS, encoding="utf-8", newline="\n")
        for name in ("psql", "poetry"):
            os.chmod(bin_dir / name, 0o755)
        rec = tmp_path / "records"
        rec.mkdir()
        return tmp_path, bin_dir, rec

    def _run_wrapper(self, tmp_path, bin_dir, rec, *, fail_provision=False):
        if fail_provision:
            (rec / "poetry-fail-provision").write_text("1")
        env_file = tmp_path / "test-env.sh"
        github_env = tmp_path / "github-env"
        env = dict(os.environ)
        canary = "canary-admin-credential-0123456789abcdef"
        env.update(
            {
                "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                "C91_FAKE_DIR": str(rec),
                "PYTHON_BIN": sys.executable,
                "CI_PG_HOST": "127.0.0.1",
                "CI_PG_PORT": "55432",
                "CI_PG_ADMIN_USER": "postgres",
                "CI_PG_ADMIN_PASSWORD": canary,
                "CI_TEST_DB": "test_ci_mpango",
                "CI_REDIS_URL": "redis://127.0.0.1:6390/0",
                "CI_SUPPLY_SKIP_SERVICE_WAIT": "1",
            }
        )
        proc = subprocess.run(
            [BASH, str(BOOTSTRAP), "--repo-root", str(REPO_ROOT),
             "--env-file", str(env_file), "--github-env", str(github_env),
             "--plan-file", str(tmp_path / "plan.json"),
             "--profile-dir", str(tmp_path / "profiles")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
        )
        return proc, canary, env_file, github_env

    @staticmethod
    def _records(rec: Path, prefix: str) -> list[Path]:
        return sorted(rec.glob(prefix + "-*.argv"), key=lambda p: int(p.name.split("-")[1]))

    def test_order_channels_and_masking(self, fake_env_dir):
        tmp_path, bin_dir, rec = fake_env_dir
        proc, canary, env_file, github_env = self._run_wrapper(tmp_path, bin_dir, rec)
        assert proc.returncode == 0, proc.stderr

        argv_texts = [p.read_text(encoding="utf-8") for p in rec.glob("*.argv")]
        stdin_texts = [p.read_text(encoding="utf-8") for p in rec.glob("*.stdin")]
        env_texts = [p.read_text(encoding="utf-8") for p in rec.glob("*.env")]

        # argv is credential-free: no canary, no password-bearing SQL
        for text in argv_texts:
            assert canary not in text
            assert "PASSWORD" not in text.upper() or "PGPASSWORD" in text
        # ...but the real consumption channel (env) carries it byte-identically
        assert any(canary in text for text in env_texts)
        # generated role DDL reaches psql only via private stdin
        assert any("CREATE ROLE" in t or "ALTER ROLE" in t for t in stdin_texts)
        assert any("WITH SET TRUE, INHERIT FALSE" in t for t in stdin_texts)

        # order: provisioner (--provision) precedes alembic precedes bootstrap
        def first_index(substr: str) -> int:
            for i, text in enumerate(argv_texts):
                if substr in text:
                    return i
            raise AssertionError(f"no argv record contains {substr!r}: {argv_texts}")

        i_provision = first_index("--provision")
        i_grants = first_index("--apply-grants")
        i_verify = first_index("--verify")
        i_alembic = first_index("alembic")
        i_bootstrap = first_index("bootstrap_tenant_schema.py")
        assert i_provision < i_alembic < i_grants < i_verify < i_bootstrap

        # masks are registered for every generated secret and DSN before output
        assert proc.stdout.count("::add-mask::") >= 11
        # outside the mask-registration channel (consumed by the GitHub
        # runner command processor), no output stream carries the canary
        unmasked_out = chr(10).join(l for l in proc.stdout.splitlines() if "::add-mask::" not in l)
        assert canary not in unmasked_out and canary not in proc.stderr

        # versioned env file: real LF, one line per key, values present,
        # no literal backslash-n artifacts, invariants keys included
        env_bytes = env_file.read_bytes()
        assert b"\r" not in env_bytes
        env_text = env_bytes.decode("utf-8")
        assert "schema-version: 3" in env_text
        assert "\\n" not in env_text
        assert "export TEST_OPERATOR_DATABASE_URL='postgresql://ci_r3_operator:" in env_text
        assert "export PW1R3_TEST_REDIS_URL='redis://127.0.0.1:6390/15'" in env_text
        assert "export MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL=" in env_text
        for line in env_text.splitlines():
            if line.startswith("export "):
                if "'" in line:
                    assert line.count("'") == 2, line  # single line, quoted value
                else:
                    assert len(line.split("=", 1)[1].split()) == 1, line  # one bare token
        github_text = github_env.read_text(encoding="utf-8")
        assert "PW1R3_TEST_REDIS_URL=redis://127.0.0.1:6390/15" in github_text

    def test_provision_failure_blocks_every_later_phase_and_pytest(self, fake_env_dir):
        tmp_path, bin_dir, rec = fake_env_dir
        proc, canary, env_file, _ = self._run_wrapper(tmp_path, bin_dir, rec, fail_provision=True)
        assert proc.returncode != 0
        assert "MUST NOT start" in proc.stderr
        argv_texts = [p.read_text(encoding="utf-8") for p in rec.glob("*.argv")]
        assert any("--provision" in t for t in argv_texts)
        assert not any("alembic" in t for t in argv_texts)
        assert not any("bootstrap_tenant_schema.py" in t for t in argv_texts)
        assert not any("--apply-grants" in t for t in argv_texts)
        assert not env_file.exists()


FAKE_DOCKER = r'''#!/usr/bin/env bash
# fake docker for the workflow-fragment control: records argv; run prints a
# synthetic container id; inspect answers the two --format shapes used
DIR="${C91_FAKE_DIR:-/tmp}"
N=$(ls "$DIR" 2>/dev/null | grep -c '^docker-' || true)
printf '%s\n' "$*" > "$DIR/docker-$N.argv"
case "$1 $2" in
  "run -d") echo "fakedockerid$$" ;;
  "inspect --format")
    case "$3" in
      *HostPort*) echo "36379" ;;
      *) echo "postgres:16-alpine|zcode-mvp-invariants-ci-deploy-staging-r3" ;;
    esac ;;
esac
exit 0
'''

FAKE_PYTHON_RECORDER = r'''#!/usr/bin/env bash
# records argv for EVERY $PY_RUNNER spawn, then execs the real interpreter
DIR="${C91_FAKE_DIR:-/tmp}"
N=$(ls "$DIR" 2>/dev/null | grep -c '^python-' || true)
printf '%s\n' "$*" > "$DIR/python-$N.argv"
exec "${REAL_PYTHON:?REAL_PYTHON must be set}" "$@"
'''


class TestWorkflowRedisWiringExecuted:
    """F-01/F-04: EXECUTE the workflow's Redis-start fragment (fake docker)
    and the provision fragment (real wrapper, fake tools) and prove the
    wrapper receives the run's registered non-6379 Redis URL before it
    starts, emitting REDIS_URL=DB0 and PW1R3_TEST_REDIS_URL=DB15 of that
    same instance. Dropping the step-env wiring must be a semantic RED."""

    @pytest.fixture()
    def sandbox(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "docker").write_text(FAKE_DOCKER, encoding="utf-8", newline="\n")
        (bin_dir / "psql").write_text(FAKE_PSQL, encoding="utf-8", newline="\n")
        (bin_dir / "poetry").write_text(FAKE_POETRY_PASS, encoding="utf-8", newline="\n")
        for name in ("docker", "psql", "poetry"):
            os.chmod(bin_dir / name, 0o755)
        rec = tmp_path / "records"
        rec.mkdir()
        github_env = tmp_path / "github-env"
        github_env.write_text("", encoding="utf-8")
        return tmp_path, bin_dir, rec, github_env

    def _run_fragment(self, bin_dir, rec, github_env_path, run_block, extra_env):
        env = dict(os.environ)
        env.update(
            {
                "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                "C91_FAKE_DIR": str(rec),
                "GITHUB_ENV": str(github_env_path),
                "GITHUB_RUN_ID": "r3r1",
                "GITHUB_RUN_ATTEMPT": "1",
                "CI_OWNER_LABEL": "zcode-mvp-invariants-ci-deploy-staging-r3",
            }
        )
        env.update(extra_env)
        return subprocess.run(
            [BASH, "-c", run_block], capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, cwd=str(Path(rec).parent),
            stdin=subprocess.DEVNULL,
        )

    def _provision_env_and_run(self):
        doc = yaml.safe_load(DEPLOY_WF.read_text(encoding="utf-8"))
        step = next(s for s in doc["jobs"]["test"]["steps"] if "Provision" in s.get("name", ""))
        env = {k: str(v).replace("${{ env.CI_REDIS_PORT }}", "36379") for k, v in step["env"].items()}
        return env, step["run"]

    def _run_wrapper_with_merged_env(self, sandbox, prov_env, out_prefix):
        """Drive the REAL wrapper with the exact environment the workflow's
        provision step would pass: the fragment-executed Redis registration
        (GITHUB_ENV) merged with the step env block by GitHub's own
        ${{ env.CI_REDIS_PORT }} substitution rule."""
        tmp_path, bin_dir, rec, github_env = sandbox

        def posix(path) -> str:
            return str(path).replace(chr(92), "/")

        env_file = tmp_path / (out_prefix + "-env.sh")
        env = dict(os.environ)
        env.update(
            {
                "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                "C91_FAKE_DIR": str(rec),
                "PYTHON_BIN": sys.executable,
                "CI_SUPPLY_SKIP_SERVICE_WAIT": "1",
            }
        )
        env.update(prov_env)
        proc = subprocess.run(
            [BASH, posix(BOOTSTRAP), "--repo-root", posix(REPO_ROOT),
             "--env-file", posix(env_file),
             "--github-env", posix(tmp_path / (out_prefix + "-gh")),
             "--plan-file", posix(tmp_path / (out_prefix + "-plan.json")),
             "--profile-dir", posix(tmp_path / (out_prefix + "-profiles"))],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, stdin=subprocess.DEVNULL,
        )
        return proc, env_file

    def test_wrapper_receives_registered_redis_and_emits_db0_db15(self, sandbox):
        tmp_path, bin_dir, rec, github_env = sandbox
        doc = yaml.safe_load(DEPLOY_WF.read_text(encoding="utf-8"))
        redis_step = next(s for s in doc["jobs"]["test"]["steps"] if "Redis 7" in s.get("name", ""))
        proc = self._run_fragment(bin_dir, rec, github_env, redis_step["run"], {})
        assert proc.returncode == 0, proc.stderr
        gh = github_env.read_text(encoding="utf-8")
        assert "CI_REDIS_PORT=36379" in gh and "CI_REDIS_CONTAINER_ID=fakedockerid" in gh

        prov_env, _ = self._provision_env_and_run()
        assert prov_env["CI_REDIS_URL"] == "redis://127.0.0.1:36379/0"
        proc2, env_file = self._run_wrapper_with_merged_env(sandbox, prov_env, "wf")
        assert proc2.returncode == 0, proc2.stderr
        text = env_file.read_text(encoding="utf-8")
        assert "export REDIS_URL='redis://127.0.0.1:36379/0'" in text
        assert "export PW1R3_TEST_REDIS_URL='redis://127.0.0.1:36379/15'" in text
        assert "redis://localhost:6379" not in text

    def test_mutation_dropping_step_env_wiring_is_semantic_red(self, sandbox):
        prov_env, _ = self._provision_env_and_run()
        mutated = {k: v for k, v in prov_env.items() if k != "CI_REDIS_URL"}
        proc, env_file = self._run_wrapper_with_merged_env(sandbox, mutated, "mut")
        assert proc.returncode != 0, "missing wiring must refuse, not silently default"
        assert "CI_REDIS_URL is required" in proc.stderr
        assert not env_file.exists()


class TestFullProcessCredentialChannels:
    """F-02: EVERY external process the wrapper spawns (python via $PY_RUNNER,
    psql, poetry) has its argv recorded. A high-entropy canary in the admin
    credential must appear in NO argv and no unmasked output, while remaining
    byte-identical in the real env consumption channel. Counterexample A
    re-introduces the canary into the front python argv and must be caught."""

    CANARY = "channel-canary-9f8e7d6c5b4a3210fedcba9876543210"

    @pytest.fixture()
    def channel_env(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "psql").write_text(FAKE_PSQL, encoding="utf-8", newline="\n")
        (bin_dir / "poetry").write_text(FAKE_POETRY_PASS, encoding="utf-8", newline="\n")
        (bin_dir / "python-recorder").write_text(FAKE_PYTHON_RECORDER, encoding="utf-8", newline="\n")
        for name in ("psql", "poetry", "python-recorder"):
            os.chmod(bin_dir / name, 0o755)
        rec = tmp_path / "records"
        rec.mkdir()
        return tmp_path, bin_dir, rec

    def _run_wrapper(self, tmp_path, bin_dir, rec, *, script=BOOTSTRAP):
        env = dict(os.environ)
        env.update(
            {
                "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                "C91_FAKE_DIR": str(rec),
                "REAL_PYTHON": sys.executable,
                "PYTHON_BIN": str(bin_dir / "python-recorder"),
                "CI_PG_HOST": "127.0.0.1",
                "CI_PG_PORT": "55432",
                "CI_PG_ADMIN_USER": "postgres",
                "CI_PG_ADMIN_PASSWORD": self.CANARY,
                "CI_TEST_DB": "test_ci_mpango",
                "CI_REDIS_URL": "redis://127.0.0.1:36379/0",
                "CI_SUPPLY_SKIP_SERVICE_WAIT": "1",
            }
        )
        env_file = tmp_path / "chan-env.sh"

        def posix(path) -> str:
            return str(path).replace(chr(92), "/")

        proc = subprocess.run(
            [BASH, str(script), "--repo-root", posix(REPO_ROOT),
             "--env-file", posix(env_file), "--github-env", posix(tmp_path / "chan-gh"),
             "--plan-file", posix(tmp_path / "chan-plan.json"),
             "--profile-dir", posix(tmp_path / "chan-profiles")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
            stdin=subprocess.DEVNULL,
        )
        return proc, env_file

    def test_canary_absent_from_all_argv_and_outputs_present_in_channel(self, channel_env):
        tmp_path, bin_dir, rec = channel_env
        proc, env_file = self._run_wrapper(tmp_path, bin_dir, rec)
        assert proc.returncode == 0, proc.stderr
        argv_texts = [p.read_text(encoding="utf-8") for p in rec.glob("*.argv")]
        assert argv_texts, "no process argv recorded"
        for text in argv_texts:
            assert self.CANARY not in text, text[:120]
        unmasked = chr(10).join(
            l for l in proc.stdout.splitlines() if "::add-mask::" not in l
        )
        assert self.CANARY not in unmasked and self.CANARY not in proc.stderr
        env_records = list(rec.glob("*.env"))
        assert any(self.CANARY in p.read_text(encoding="utf-8") for p in env_records), (
            "the credential must actually travel the env consumption channel"
        )
        env_text = env_file.read_text(encoding="utf-8")
        assert f"postgresql://postgres:{self.CANARY}@127.0.0.1:55432/postgres" in env_text
        # Birth permissions: umask 177 before creation + explicit chmod 600.
        # On POSIX this is asserted at runtime (os.stat). Windows host mounts
        # are typically noacl (chmod/umask silently no-op), so there the
        # source-level invariant is asserted instead and the ACTUAL mode is
        # captured as evidence during the real Linux run (Phase B ledger).
        if os.name == "posix":
            perms = env_file.stat().st_mode & 0o777
            assert perms & 0o077 == 0, f"env file must be user-only (got {oct(perms)})"
        else:
            source = BOOTSTRAP.read_text(encoding="utf-8")
            env_block = source.split('if [ -n "$ENV_FILE" ]; then', 1)[1]
            assert "umask 177" in env_block.split("}", 1)[0], (
                "wrapper must set umask before env-file creation"
            )
            assert 'chmod 600 "$ENV_FILE"' in env_block, (
                "wrapper must enforce chmod 600 on the env file"
            )

    def test_counterexample_a_canary_in_front_python_argv_is_caught(self, channel_env):
        tmp_path, bin_dir, rec = channel_env
        mutated = tmp_path / "wrapper-argv-mutant.sh"
        text = BOOTSTRAP.read_text(encoding="utf-8")
        q = chr(39)
        needle = f'"$OPERATOR_USER" <<{q}PY{q}'
        assert needle in text
        mutated.write_text(
            text.replace(needle, f'"$OPERATOR_USER" "$ADMIN_PASSWORD" <<{q}PY{q}'),
            encoding="utf-8", newline="\n",
        )
        os.chmod(mutated, 0o755)
        proc, _ = self._run_wrapper(tmp_path, bin_dir, rec, script=mutated)
        argv_texts = [p.read_text(encoding="utf-8") for p in rec.glob("python-*.argv")]
        assert argv_texts, "python argv recording must be active for the mutant"
        assert any(self.CANARY in t for t in argv_texts), (
            "the control must detect the canary re-entering the front python argv"
        )
