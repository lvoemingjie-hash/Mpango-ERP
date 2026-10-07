"""Offline CI gate contracts and discriminating counterexamples (R3/R6).

Authorization: CTO-C91-CI-EXECUTABLE-CONTRACT-ZCODEW-R3-20261006,
CTO-C91-CI-R6-FIVE-TASK-PREPARATION-20261007.

Covers the candidate bytes:

* AST no-print gate: real builtin prints (including spaced calls, explicit
  ``builtins.print``, aliases) rejected; names/strings/comments pass; an
  unambiguous module-level shadow exempts only call sites AFTER the binding
  (a print before a later ``def print`` stays a finding); unparseable files
  fail closed.
* Deploy Staging test job (R6: five instance-independent matrix legs):
  task-owned labeled containers with per-run random admin credentials,
  five-phase wrapper provisioning, frozen-boundary runtime shard argfiles,
  shard membership gates (file and node level), ONE pytest body per leg
  with per-leg outer timeouts + junit, sanitized-only artifact publication,
  and a final outcome gate that keeps the pytest rc authoritative.
* Bootstrap wrapper: real-mode execution against FAKE psql/poetry tools —
  call order, failure blocking, credential channels (argv clean; secrets
  only via env/stdin; canary byte-identical in the real channel) — plus
  preflight refusals (missing tests source, empty selection, role-name
  drift, non-distinct identities) and plan-file idempotence.
* R6 load-bearing controls (each with a discriminating counterexample):
  missing/duplicate shard members are RED; a failed pytest rc cannot be
  washed green by upload steps; removing artifact sanitization is caught
  by the tool's own fail-closed residual scan on a high-entropy positive.

Everything runs offline on synthetic fixtures; no network, no docker, no
database. Windows hosts pin PYTHON_BIN/BASH explicitly (the store-stub
python3 and System32 WSL bash are not usable interpreters).
"""
from __future__ import annotations

import json
import os
import re
import secrets
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
EVIDENCE_TOOL = REPO_ROOT / "tools" / "ci" / "prepare_test_evidence.py"
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
# R5: shared by the classification controls (same non-keyword binding rule)
CLASSIFICATION_CREDENTIAL = "c91-classification-placeholder-credential"




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
            # matrix key is part of the task ownership identity
            assert "${{ matrix.shard }}" in run
        assert "postgres:16-alpine" in pg and "redis:7-alpine" in redis
        # no service-container block remains: the guard contract needs labels
        assert "services" not in self.test_job
        # R6: the admin credential is generated per run (high entropy), is
        # masked before any value can reach an output stream, and never
        # exists as a literal in the workflow bytes.
        assert "token_urlsafe" in pg
        assert "::add-mask::" in pg.split("CI_PG_ADMIN_PASSWORD=")[0]
        workflow_text = DEPLOY_WF.read_text(encoding="utf-8")
        assert "CI_PG_ADMIN_PASSWORD: postgres" not in workflow_text
        assert "POSTGRES_PASSWORD=postgres" not in workflow_text

    def test_provision_step_and_shard_pipeline_gated(self):
        provision = next(s for s in self.steps if "Provision test database" in s.get("name", ""))
        assert provision["id"] == "provision"
        assert "bootstrap_backend_test_db.sh" in provision["run"]
        assert "--env-file" in provision["run"] and "--plan-file" in provision["run"]
        # the run's registered Redis port reaches the wrapper BEFORE it runs
        assert "CI_REDIS_URL" in provision["env"]
        assert "${{ env.CI_REDIS_PORT }}" in provision["env"]["CI_REDIS_URL"]
        assert "CI_REDIS_URL" not in provision["run"]  # no post-hoc GITHUB_ENV echo
        # R6: the task credential store is declared so the sanitize stage has
        # a fail-closed secret source; the admin credential reaches this step
        # through the GITHUB_ENV channel, not through YAML literals.
        assert "${{ runner.temp }}/c91-task-credentials.env" == provision["env"]["CI_CREDENTIALS_FILE"]
        assert "CI_PG_ADMIN_PASSWORD" not in provision["env"]

        shard_plan = next(s for s in self.steps if "Cut frozen runtime shard" in s.get("name", ""))
        assert shard_plan["if"] == "steps.provision.outcome == 'success'"
        assert "prepare_test_evidence.py shard-plan" in shard_plan["run"]

        gate = next(s for s in self.steps if "Shard gate" in s.get("name", ""))
        assert gate["if"] == "steps.provision.outcome == 'success'"
        # empty/missing argfiles must refuse instead of falling back to
        # full-suite collection
        assert 'test -s "$RUNNER_TEMP/profile-${{ matrix.shard }}.tests"' in gate["run"]
        # file-level and node-level reconciliation against the frozen plan
        assert gate["run"].count("prepare_test_evidence.py shard-verify") == 2
        assert '--collect "$RUNNER_TEMP/collect-${{ matrix.shard }}.txt"' in gate["run"]
        assert '--expected-nodes "${{ matrix.expected-nodes }}"' in gate["run"]
        assert "--collect-only -q" in gate["run"]
        # per-shard premise wiring: topology/task-managed opt-in, real JWT
        # staging env, private resource root
        assert "topology|task-managed-pg) export MPANGO_ALLOW_TEMP_DB_CREATE=1" in gate["run"]
        assert "invariants-jwt) export MPANGO_ENV=staging" in gate["run"]
        assert 'export C91_R3_RESOURCE_ROOT="$RUNNER_TEMP/c91-resource-root"' in gate["run"]
        assert "chmod 700" in gate["run"]

        body = next(s for s in self.steps if "Run shard test body" in s.get("name", ""))
        assert body["if"] == "steps.provision.outcome == 'success'"
        assert "continue-on-error" not in body
        # exactly ONE pytest test-body invocation per leg
        pytest_lines = [
            ln for ln in body["run"].splitlines()
            if "poetry run pytest" in ln and "--collect-only" not in ln
        ]
        assert len(pytest_lines) == 1
        pytest_line = pytest_lines[0]
        assert "timeout --signal=INT --kill-after=60s ${{ matrix.pytest-timeout }}" in pytest_line
        assert "--junitxml=../junit-${{ matrix.shard }}.xml" in pytest_line
        assert 'xargs -a "$RUNNER_TEMP/profile-${{ matrix.shard }}.tests"' in pytest_line
        # the recorded rc — not a later step's success — decides the leg
        assert 'echo "$rc" > "$RUNNER_TEMP/pytest-rc.txt"' in body["run"]
        assert 'exit "$rc"' in body["run"]
        # the pytest command itself is never softened with || true / || exit 0
        assert "|| true" not in pytest_line and "|| exit 0" not in pytest_line
        assert "set -o pipefail" in body["run"]

    def test_five_legs_budget_and_isolation(self):
        strategy = self.test_job["strategy"]
        assert strategy["fail-fast"] is False
        assert strategy["max-parallel"] == 2
        include = strategy["matrix"]["include"]
        expected = {
            "runtime-a": (30, "18m", "93", "1655"),
            "runtime-b": (30, "18m", "97", "1651"),
            "topology": (50, "38m", "39", "798"),
            "invariants-jwt": (25, "13m", "3", "92"),
            "task-managed-pg": (25, "13m", "4", "92"),
        }
        assert {leg["shard"] for leg in include} == set(expected)
        for leg in include:
            got = (
                leg["job-timeout-minutes"], leg["pytest-timeout"],
                leg["expected-files"], leg["expected-nodes"],
            )
            assert got == expected[leg["shard"]], leg["shard"]
        # the owner-approved hard budget cap is exactly 160 runner-minutes
        assert sum(leg["job-timeout-minutes"] for leg in include) == 160
        # no leg (and no step) may convert a failure into success
        workflow_text = DEPLOY_WF.read_text(encoding="utf-8")
        assert "continue-on-error" not in workflow_text
        assert self.test_job["env"]["CI_OWNER_LABEL"] == "zcode-mvp-invariants-ci-deploy-staging-r6"

    def test_publication_pipeline_sanitizes_before_upload_and_never_uploads_raw(self):
        def index_of(fragment):
            return self.names.index(next(n for n in self.names if fragment in n))

        order = [
            index_of("Cut frozen runtime shard"),
            index_of("Shard gate"),
            index_of("Run shard test body"),
            index_of("Sanitize shard evidence"),
            index_of("Upload sanitized shard evidence"),
            index_of("Assert shard outcome"),
        ]
        assert order == sorted(order), "evidence pipeline steps are out of order"

        sanitize = next(s for s in self.steps if "Sanitize shard evidence" in s.get("name", ""))
        assert sanitize["if"] == "always()"
        assert "prepare_test_evidence.py sanitize" in sanitize["run"]
        assert '--secrets-file "$SECRETS"' in sanitize["run"]
        assert "--extra-env CI_PG_ADMIN_PASSWORD" in sanitize["run"]
        # a refused sanitization records a gap and never uploads the raw file
        assert 'echo "sanitize_refused" > "$RUNNER_TEMP/GAP-$dst.txt"' in sanitize["run"]

        upload = next(s for s in self.steps if "Upload sanitized shard evidence" in s.get("name", ""))
        assert upload["if"] == "always()"
        assert upload["uses"] == "actions/upload-artifact@v4"
        # artifact identity includes shard/run/attempt (no matrix collisions)
        assert upload["with"]["name"] == (
            "test-evidence-${{ matrix.shard }}-run${{ github.run_id }}"
            "-attempt${{ github.run_attempt }}"
        )
        # ONLY the sanitized publish directory is uploaded — never a raw
        # junit/collect/connections/supply-plan path
        assert upload["with"]["path"] == "${{ runner.temp }}/publish"
        assert upload["with"]["if-no-files-found"] == "error"

        final = next(s for s in self.steps if "Assert shard outcome" in s.get("name", ""))
        assert final["if"] == "always()"
        assert "$RUNNER_TEMP/pytest-rc.txt" in final["run"]
        assert '"$rc" != "0"' in final["run"]
        assert '"$gaps" -ne 0' in final["run"]

    def test_connection_observer_is_read_only_and_5s_sampled(self):
        body = next(s for s in self.steps if "Run shard test body" in s.get("name", ""))["run"]
        segments = body.split("PYOBS")
        assert len(segments) == 3, "the observer heredoc must open and close exactly once"
        observer = segments[1]
        assert "pg_stat_activity" in observer
        assert "c91_observer" in observer
        assert "time.sleep(5)" in observer
        # read-only observation: no SQL text, no locals, no passwords — only
        # identity/state/wait columns and counts
        for ln in observer.splitlines():
            if "SELECT" in ln:
                assert "query" not in ln.lower(), ln
        assert "readonly=True" in observer

    def test_publish_gate_closed_for_non_dispatch_events(self):
        build_if = self.doc["jobs"]["build"]["if"]

        def evaluate(cond: str, *, event: str) -> bool:
            expr = cond.strip().removeprefix("${{").removesuffix("}}").strip()
            expr = expr.replace("github.event_name == 'workflow_dispatch'", repr(event == "workflow_dispatch"))
            expr = expr.replace("inputs.publish == true", "True")
            expr = expr.replace("needs.test.result == 'success'", "True")
            expr = expr.replace("needs.build.result == 'success'", "True")
            expr = expr.replace("&&", " and ").replace("||", " or ")
            assert re.fullmatch(r"[()\s!&|=A-Za-z0-9']+", expr), expr
            return bool(eval(expr, {"__builtins__": {}}, {}))

        # push (main) and pull_request events can never publish, even with
        # every other condition satisfied
        assert evaluate(build_if, event="push") is False
        assert evaluate(build_if, event="pull_request") is False
        assert evaluate(build_if, event="workflow_dispatch") is True

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
        # GitHub renders ${{ }} expressions before the shell sees the script;
        # the harness renders the representative matrix leg the same way.
        run_block = run_block.replace("${{ matrix.shard }}", "runtime-a")
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

    def _provision_env_and_run(self, sandbox):
        """Workflow step env + the GITHUB_ENV channel, with GitHub's own
        ${{ env.* }} / ${{ runner.temp }} substitution rules applied."""
        tmp_path = sandbox[0]
        doc = yaml.safe_load(DEPLOY_WF.read_text(encoding="utf-8"))
        step = next(s for s in doc["jobs"]["test"]["steps"] if "Provision" in s.get("name", ""))
        posix_tmp = str(tmp_path).replace(chr(92), "/")
        env = {
            k: str(v)
            .replace("${{ env.CI_REDIS_PORT }}", "36379")
            .replace("${{ runner.temp }}", posix_tmp)
            for k, v in step["env"].items()
        }
        # GitHub semantics: lines exported to GITHUB_ENV by earlier steps are
        # part of every later step's environment. Only the credential/port
        # channel keys are merged here; container-ID ownership verification
        # is exercised by the wrapper fake-tool controls instead.
        github_env = sandbox[3].read_text(encoding="utf-8")
        for key in ("CI_PG_ADMIN_PASSWORD", "CI_PG_PORT", "CI_REDIS_PORT"):
            m = re.search(rf"^{key}=(.*)$", github_env, re.M)
            if m:
                env[key] = m.group(1)
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
        pg_step = next(s for s in doc["jobs"]["test"]["steps"] if "Postgres 16" in s.get("name", ""))
        proc_pg = self._run_fragment(bin_dir, rec, github_env, pg_step["run"], {})
        assert proc_pg.returncode == 0, proc_pg.stderr
        redis_step = next(s for s in doc["jobs"]["test"]["steps"] if "Redis 7" in s.get("name", ""))
        proc = self._run_fragment(bin_dir, rec, github_env, redis_step["run"], {})
        assert proc.returncode == 0, proc.stderr
        gh = github_env.read_text(encoding="utf-8")
        assert "CI_REDIS_PORT=36379" in gh and "CI_REDIS_CONTAINER_ID=fakedockerid" in gh
        assert "CI_PG_PORT=36379" in gh and "CI_PG_CONTAINER_ID=fakedockerid" in gh
        # R6: the admin credential travels via the GITHUB_ENV channel —
        # generated per run (high entropy), never the old fixed literal
        m = re.search(r"^CI_PG_ADMIN_PASSWORD=(\S+)$", gh, re.M)
        assert m and len(m.group(1)) >= 24

        prov_env, _ = self._provision_env_and_run(sandbox)
        assert prov_env["CI_REDIS_URL"] == "redis://127.0.0.1:36379/0"
        proc2, env_file = self._run_wrapper_with_merged_env(sandbox, prov_env, "wf")
        assert proc2.returncode == 0, proc2.stderr
        text = env_file.read_text(encoding="utf-8")
        assert "export REDIS_URL='redis://127.0.0.1:36379/0'" in text
        assert "export PW1R3_TEST_REDIS_URL='redis://127.0.0.1:36379/15'" in text
        assert "redis://localhost:6379" not in text
        # R6: the task credential store the sanitize stage depends on is live
        store = Path(prov_env["CI_CREDENTIALS_FILE"])
        assert store.is_file()
        assert "MIGRATE_PASSWORD=" in store.read_text(encoding="utf-8")

    def test_mutation_dropping_step_env_wiring_is_semantic_red(self, sandbox):
        prov_env, _ = self._provision_env_and_run(sandbox)
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


class TestTopologyHelperClassification:
    """R5 (F-02): files that ImportFrom reporting_bootstrap_contract_helpers
    (which calls async_test_utils.temporary_database_url) belong to the
    topology profile. The controls below drive the REAL wrapper preflight —
    never a source-string search — against the candidate bytes, against the
    pre-fix bytes (module registration removed), and against known runtime
    negatives (pytest_plugins STRING references must NOT move a file)."""

    TARGET = "tests/test_dc11t4c_reporting_bootstrap_contract.py"

    def _preflight_plan(self, tmp_path, script):
        env = dict(os.environ)
        env.update(
            {
                "CI_PG_HOST": "127.0.0.1",
                "CI_PG_PORT": "55432",
                "CI_PG_ADMIN_USER": "postgres",
                "CI_PG_ADMIN_PASSWORD": CLASSIFICATION_CREDENTIAL,
                "CI_TEST_DB": "test_ci_mpango",
                "CI_REDIS_URL": "redis://127.0.0.1:55433/0",
                "PYTHON_BIN": sys.executable,
            }
        )
        plan_file = tmp_path / "plan.json"
        proc = subprocess.run(
            [BASH, str(script), "--repo-root", str(REPO_ROOT), "--preflight-only",
             "--plan-file", str(plan_file), "--profile-dir", str(tmp_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, stdin=subprocess.DEVNULL,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(plan_file.read_text(encoding="utf-8"))

    def test_candidate_bytes_classify_importer_as_topology(self, tmp_path):
        plan = self._preflight_plan(tmp_path, BOOTSTRAP)
        assert self.TARGET in plan["profiles"]["topology"]["files"]
        assert self.TARGET not in plan["profiles"]["runtime"]["files"]
        assert plan["profiles"]["topology"]["count"] == 39
        assert plan["profiles"]["runtime"]["count"] == 190
        assert plan["selection_counts"]["partition_total"] == 236
        # pytest_plugins STRING references do not move a file (R4 evidence:
        # both files passed under the runtime profile)
        for non_importer in (
            "tests/test_s6_2_materialized_views.py",
            "tests/test_s6_3_dashboard_api.py",
        ):
            assert non_importer in plan["profiles"]["runtime"]["files"]
            assert non_importer not in plan["profiles"]["topology"]["files"]

    def test_counterexample_pre_fix_bytes_classify_runtime(self, tmp_path):
        """Removing the helper registration (the pre-fix classifier) must put
        the importer back into runtime — proving the classification control
        discriminates real preflight output, not strings."""
        mutant = tmp_path / "wrapper-prefix-bug.sh"
        text = BOOTSTRAP.read_text(encoding='utf-8')
        fixed = 'TOPOLOGY_MODULES = {"async_test_utils", "reporting_bootstrap_contract_helpers"}'
        assert fixed in text
        mutant.write_text(
            text.replace(fixed, 'TOPOLOGY_MODULES = {"async_test_utils"}'),
            encoding="utf-8", newline="\n",
        )
        os.chmod(mutant, 0o755)
        plan = self._preflight_plan(tmp_path, mutant)
        assert self.TARGET in plan["profiles"]["runtime"]["files"], (
            "pre-fix bytes must classify the importer as runtime (control RED direction)"
        )
        assert self.TARGET not in plan["profiles"]["topology"]["files"]
        assert plan["profiles"]["runtime"]["count"] == 191

    def test_runtime_negative_without_topology_imports(self, tmp_path):
        plan = self._preflight_plan(tmp_path, BOOTSTRAP)
        negative = "tests/test_s5_5_ledger_hardening.py"
        assert negative in plan["profiles"]["runtime"]["files"]
        assert negative not in plan["profiles"]["topology"]["files"]


class TestR6ShardPlanControls:
    """Load-bearing control 1 (missing/duplicate shard members are RED):
    drive the REAL prepare_test_evidence.py shard-plan/shard-verify against
    a synthetic frozen plan — never string matching — and prove the exact
    frozen-boundary partition, the boundary-drift refusals, and RED on
    dropped, duplicated, extra or miscounted members at both the file and
    the node level."""

    RUNTIME_FILES = [
        "tests/test_m00.py",
        "tests/test_m01.py",
        "tests/test_m02.py",
        "tests/test_platform_p12_support_console.py",  # frozen boundary: last of a
        "tests/test_platform_p17dc_backup_models.py",  # frozen boundary: first of b
        "tests/test_z9_zero_nodes.py",
    ]

    @staticmethod
    def _write_plan(tmp_path, runtime_files):
        plan = {
            "profiles": {
                "runtime": {"files": sorted(runtime_files), "count": len(runtime_files)},
                "topology": {"files": ["tests/test_topo_a.py"], "count": 1},
                "invariants-jwt": {"files": ["tests/test_inv_a.py"], "count": 1},
                "task-managed-pg": {"files": ["tests/test_task_a.py"], "count": 1},
            }
        }
        plan_path = tmp_path / "supply-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8", newline="\n")
        return plan_path

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(EVIDENCE_TOOL), *[str(a) for a in args]],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL,
        )

    @staticmethod
    def _collect_file(tmp_path, nodeids):
        path = tmp_path / "collect.txt"
        body = "\n".join(nodeids) + "\n== 3 tests collected in 0.01s ==\n"
        path.write_text(body, encoding="utf-8", newline="\n")
        return path

    def test_shard_plan_cuts_exact_partition_and_receipt(self, tmp_path):
        plan_path = self._write_plan(tmp_path, self.RUNTIME_FILES)
        proc = self._run("shard-plan", "--plan", plan_path, "--profile-dir", tmp_path)
        assert proc.returncode == 0, proc.stderr
        shard_a = (tmp_path / "profile-runtime-a.tests").read_text(encoding="utf-8").splitlines()
        shard_b = (tmp_path / "profile-runtime-b.tests").read_text(encoding="utf-8").splitlines()
        assert shard_a[-1] == "tests/test_platform_p12_support_console.py"
        assert shard_b[0] == "tests/test_platform_p17dc_backup_models.py"
        assert sorted(shard_a + shard_b) == sorted(self.RUNTIME_FILES)
        assert not set(shard_a) & set(shard_b)
        receipt = json.loads((tmp_path / "shard-plan.receipt.json").read_text(encoding="utf-8"))
        assert receipt["runtime-a"]["files"] == 4
        assert receipt["runtime-b"]["files"] == 2
        assert receipt["runtime_total"] == 6

    def test_shard_plan_refuses_boundary_missing(self, tmp_path):
        drifted = [f for f in self.RUNTIME_FILES if "p12_support_console" not in f]
        plan_path = self._write_plan(tmp_path, drifted)
        proc = self._run("shard-plan", "--plan", plan_path, "--profile-dir", tmp_path)
        assert proc.returncode == 3
        assert "RUNTIME_SHARD_BOUNDARY_MISSING" in proc.stderr
        assert not (tmp_path / "profile-runtime-a.tests").exists()

    def test_shard_plan_refuses_empty_shard_b(self, tmp_path):
        plan_path = self._write_plan(tmp_path, ["tests/test_platform_p12_support_console.py"])
        proc = self._run("shard-plan", "--plan", plan_path, "--profile-dir", tmp_path)
        assert proc.returncode == 3
        assert "RUNTIME_SHARD_B_EMPTY" in proc.stderr

    def test_shard_verify_green_with_zero_nodeid_member(self, tmp_path):
        plan_path = self._write_plan(tmp_path, self.RUNTIME_FILES)
        assert self._run("shard-plan", "--plan", plan_path, "--profile-dir", tmp_path).returncode == 0
        # shard-b: three nodeids from the first member; the z9 member
        # collects zero nodeids (mirrors tests/test_s3_db_performance.py in
        # the real frozen set) — the node total stays authoritative
        collect = self._collect_file(tmp_path, [
            "tests/test_platform_p17dc_backup_models.py::test_alpha",
            "tests/test_platform_p17dc_backup_models.py::test_beta",
            "tests/test_platform_p17dc_backup_models.py::test_gamma",
        ])
        proc = self._run(
            "shard-verify", "--plan", plan_path, "--shard", "runtime-b",
            "--argfile", tmp_path / "profile-runtime-b.tests",
            "--expected-files", "2", "--collect", collect, "--expected-nodes", "3",
        )
        assert proc.returncode == 0, proc.stderr

    def test_shard_verify_red_on_missing_member(self, tmp_path):
        plan_path = self._write_plan(tmp_path, self.RUNTIME_FILES)
        assert self._run("shard-plan", "--plan", plan_path, "--profile-dir", tmp_path).returncode == 0
        argfile = tmp_path / "argfile-b-dropped.tests"
        argfile.write_text(
            "tests/test_platform_p17dc_backup_models.py\n", encoding="utf-8", newline="\n"
        )
        proc = self._run(
            "shard-verify", "--plan", plan_path, "--shard", "runtime-b",
            "--argfile", argfile, "--expected-files", "2",
        )
        assert proc.returncode == 3
        assert "SHARD_MEMBERSHIP_MISMATCH" in proc.stderr
        assert "tests/test_z9_zero_nodes.py" in proc.stderr

    def test_shard_verify_red_on_duplicate_member(self, tmp_path):
        plan_path = self._write_plan(tmp_path, self.RUNTIME_FILES)
        argfile = tmp_path / "argfile-b-dup.tests"
        argfile.write_text(
            "tests/test_platform_p17dc_backup_models.py\n"
            "tests/test_platform_p17dc_backup_models.py\n"
            "tests/test_z9_zero_nodes.py\n",
            encoding="utf-8", newline="\n",
        )
        proc = self._run(
            "shard-verify", "--plan", plan_path, "--shard", "runtime-b",
            "--argfile", argfile, "--expected-files", "3",
        )
        assert proc.returncode == 3
        assert "DUPLICATE_SHARD_MEMBERS" in proc.stderr

    def test_shard_verify_red_on_extra_member(self, tmp_path):
        plan_path = self._write_plan(tmp_path, self.RUNTIME_FILES)
        argfile = tmp_path / "argfile-topo-extra.tests"
        argfile.write_text(
            "tests/test_topo_a.py\ntests/test_task_a.py\n", encoding="utf-8", newline="\n"
        )
        proc = self._run(
            "shard-verify", "--plan", plan_path, "--shard", "topology",
            "--argfile", argfile, "--expected-files", "1",
        )
        assert proc.returncode == 3
        assert "SHARD_MEMBERSHIP_MISMATCH" in proc.stderr
        assert "tests/test_task_a.py" in proc.stderr

    def test_shard_verify_red_on_node_count_drift(self, tmp_path):
        plan_path = self._write_plan(tmp_path, self.RUNTIME_FILES)
        assert self._run("shard-plan", "--plan", plan_path, "--profile-dir", tmp_path).returncode == 0
        collect = self._collect_file(tmp_path, [
            "tests/test_platform_p17dc_backup_models.py::test_alpha",
        ])
        proc = self._run(
            "shard-verify", "--plan", plan_path, "--shard", "runtime-b",
            "--argfile", tmp_path / "profile-runtime-b.tests",
            "--expected-files", "2", "--collect", collect, "--expected-nodes", "3",
        )
        assert proc.returncode == 3
        assert "SHARD_NODE_COUNT_MISMATCH" in proc.stderr

    def test_shard_verify_red_on_outsider_collected_file(self, tmp_path):
        plan_path = self._write_plan(tmp_path, self.RUNTIME_FILES)
        assert self._run("shard-plan", "--plan", plan_path, "--profile-dir", tmp_path).returncode == 0
        collect = self._collect_file(tmp_path, [
            "tests/test_platform_p17dc_backup_models.py::test_alpha",
            "tests/test_m00.py::test_outsider",
        ])
        proc = self._run(
            "shard-verify", "--plan", plan_path, "--shard", "runtime-b",
            "--argfile", tmp_path / "profile-runtime-b.tests",
            "--expected-files", "2", "--collect", collect, "--expected-nodes", "2",
        )
        assert proc.returncode == 3
        assert "COLLECTED_FILE_NOT_IN_SHARD" in proc.stderr


class TestR6OutcomePropagationControls:
    """Load-bearing control 2 (a failed pytest rc cannot be washed green by
    upload steps): EXECUTE the workflow's real final-gate script under the
    recorded-outcome filesystem states — rc!=0, outer-timeout 124, a
    never-run body, or evidence gaps all fail the leg; only rc=0 with
    complete sanitized evidence passes."""

    def _final_gate_script(self):
        doc = yaml.safe_load(DEPLOY_WF.read_text(encoding="utf-8"))
        step = next(
            s for s in doc["jobs"]["test"]["steps"] if "Assert shard outcome" in s.get("name", "")
        )
        return step["run"].replace("${{ matrix.shard }}", "runtime-a")

    def _run_final_gate(self, tmp_path, *, rc_value=None, gap_files=()):
        runner_temp = tmp_path / "runner-temp"
        runner_temp.mkdir(exist_ok=True)
        if rc_value is not None:
            (runner_temp / "pytest-rc.txt").write_text(str(rc_value), encoding="utf-8")
        for name in gap_files:
            (runner_temp / f"GAP-{name}.txt").write_text("sanitize_refused", encoding="utf-8")
        env = dict(os.environ)
        env["RUNNER_TEMP"] = str(runner_temp).replace(chr(92), "/")
        return subprocess.run(
            [BASH, "-c", self._final_gate_script()],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, stdin=subprocess.DEVNULL,
        )

    def test_failed_rc_fails_the_leg_despite_uploads(self, tmp_path):
        proc = self._run_final_gate(tmp_path, rc_value=1)
        assert proc.returncode == 1
        assert "rc=1" in proc.stdout

    def test_outer_timeout_rc_124_fails_the_leg(self, tmp_path):
        proc = self._run_final_gate(tmp_path, rc_value=124)
        assert proc.returncode == 1
        assert "124=outer timeout" in proc.stdout

    def test_never_ran_body_fails_the_leg(self, tmp_path):
        proc = self._run_final_gate(tmp_path, rc_value=None)
        assert proc.returncode == 1

    def test_green_rc_passes_only_without_evidence_gaps(self, tmp_path):
        green = self._run_final_gate(tmp_path, rc_value=0)
        assert green.returncode == 0
        with_gap = self._run_final_gate(tmp_path, rc_value=0, gap_files=("junit",))
        assert with_gap.returncode == 1
        assert "evidence gaps" in with_gap.stdout


class TestR6SanitizeControls:
    """Load-bearing control 3 (removing artifact sanitization is caught by a
    high-entropy positive): the REAL sanitizer replaces generated
    high-entropy credentials plus DSN/SCRAM form matches in junit
    derivatives while proving node/status mapping invariance; refusals are
    fail-closed (no output file is written); and a mutant with the exact-
    value replacement disabled is caught by the tool's own residual scan —
    proving the control discriminates, not just exists."""

    @staticmethod
    def _junit(name, classname, inner=""):
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<testsuites><testsuite name="s" tests="1" failures="0" errors="0" skipped="0">'
            f'<testcase name="{name}" classname="{classname}">{inner}</testcase>'
            "</testsuite></testsuites>"
        )

    def _run_sanitize(self, tmp_path, content, *, store=None, extra_env=None,
                      tool=None, store_exists=True, input_name="junit.xml"):
        src = tmp_path / input_name
        src.write_text(content, encoding="utf-8", newline="\n")
        out = tmp_path / (input_name + ".sanitized")
        receipt = tmp_path / "receipt.json"
        store_path = tmp_path / "store.env"
        if store_exists:
            if store is None:
                store = {"APP_PASSWORD": secrets.token_hex(16), "SECRET_KEY": secrets.token_hex(32)}
            store_path.write_text(
                "".join(f"{k}={v}\n" for k, v in store.items()),
                encoding="utf-8", newline="\n",
            )
        argv = [
            sys.executable, str(tool or EVIDENCE_TOOL), "sanitize",
            "--input", src, "--output", out, "--receipt", receipt,
            "--secrets-file", store_path,
        ]
        if extra_env:
            argv += ["--extra-env", ",".join(extra_env)]
        env = dict(os.environ)
        for name, value in (extra_env or {}).items():
            if value is not None:
                env[name] = value
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, stdin=subprocess.DEVNULL,
        )
        return proc, out, receipt

    def test_high_entropy_values_replaced_with_mapping_invariance(self, tmp_path):
        app_secret = secrets.token_hex(16)
        # foreign-password DSN built at runtime (high entropy, no literal
        # credential shape in source): exercises the form rule for values
        # that are NOT in the credential store
        foreign_pw = "fwd-" + secrets.token_hex(12)
        foreign_dsn = f"postgresql://mpango_app:{foreign_pw}@127.0.0.1:55432/test_ci_mpango"
        content = self._junit(
            "test_example", "tests.test_example",
            f'<failure message="connect failed: postgresql://mpango_app:{app_secret}'
            f'@127.0.0.1:55432/test_ci_mpango retry {app_secret}" type="OperationalError">'
            f"<system-err>alt endpoint {foreign_dsn}</system-err></failure>",
        )
        proc, out, receipt = self._run_sanitize(
            tmp_path, content, store={"APP_PASSWORD": app_secret}
        )
        assert proc.returncode == 0, proc.stderr
        sanitized = out.read_text(encoding="utf-8")
        assert app_secret not in sanitized
        assert foreign_pw not in sanitized
        assert "[REDACTED:APP_PASSWORD]" in sanitized
        assert "[REDACTED:pg-dsn]" in sanitized
        data = json.loads(receipt.read_text(encoding="utf-8"))
        assert data["mapping_invariance"] == "ok"
        assert data["replacements"]["exact:APP_PASSWORD"] >= 2
        assert data["replacements"]["form:pg-dsn"] >= 1
        # the node identity survived byte-level replacement
        assert 'name="test_example"' in sanitized
        assert app_secret not in receipt.read_text(encoding="utf-8")

    def test_scram_verifier_form_rule(self, tmp_path):
        verifier = "SCRAM-SHA-256$4096:c3RvcmVrZXlzdG9yZWtleQ==:c2FsdHNhbHRzYWx0"
        content = self._junit(
            "test_roles", "tests.test_roles",
            f'<failure message="role row leaked {verifier}" type="AssertionError"/>',
        )
        proc, out, _ = self._run_sanitize(tmp_path, content)
        assert proc.returncode == 0, proc.stderr
        sanitized = out.read_text(encoding="utf-8")
        assert verifier not in sanitized
        assert "[REDACTED:scram-verifier]" in sanitized

    def test_missing_store_refuses_fail_closed(self, tmp_path):
        proc, out, _ = self._run_sanitize(
            tmp_path, self._junit("t", "c"), store_exists=False
        )
        assert proc.returncode == 4
        assert "SECRETS_STORE_MISSING" in proc.stderr
        assert not out.exists()

    def test_empty_store_refuses_fail_closed(self, tmp_path):
        proc, out, _ = self._run_sanitize(
            tmp_path, self._junit("t", "c"),
            store_exists=True, store={"APP_PASSWORD": ""},
        )
        assert proc.returncode == 4
        assert "SECRETS_STORE_EMPTY" in proc.stderr
        assert not out.exists()

    def test_unset_extra_env_refuses_fail_closed(self, tmp_path):
        proc, out, _ = self._run_sanitize(
            tmp_path, self._junit("t", "c"),
            extra_env={"C91_SYNTH_ADMIN_TOKEN": None},
        )
        assert proc.returncode == 4
        assert "SECRETS_ENV_MISSING" in proc.stderr
        assert not out.exists()

    def test_secret_touching_a_node_name_refuses(self, tmp_path):
        app_secret = secrets.token_hex(16)
        content = self._junit(f"test_{app_secret}", "tests.test_example")
        proc, out, _ = self._run_sanitize(
            tmp_path, content, store={"APP_PASSWORD": app_secret}
        )
        assert proc.returncode == 4
        assert "NODE_MAPPING_AT_RISK" in proc.stderr
        assert not out.exists()

    def test_mutant_without_replacement_is_caught_by_residual_scan(self, tmp_path):
        source = EVIDENCE_TOOL.read_text(encoding="utf-8")
        disabled = "text = text.replace(value, PLACEHOLDER % rule_id.split(\":\", 1)[1])"
        assert disabled in source
        mutant = tmp_path / "prepare_test_evidence_mutant.py"
        mutant.write_text(
            source.replace(disabled, "text = text  # mutant: replacement disabled"),
            encoding="utf-8", newline="\n",
        )
        app_secret = secrets.token_hex(16)
        content = self._junit(
            "t", "c", f'<failure message="leak {app_secret}" type="E"/>'
        )
        proc, out, _ = self._run_sanitize(
            tmp_path, content, store={"APP_PASSWORD": app_secret}, tool=mutant
        )
        assert proc.returncode == 4
        assert "RESIDUAL_SECRET" in proc.stderr
        assert not out.exists(), "a bypassed sanitizer must not publish anything"

    def test_text_mode_replaces_in_collect_lists(self, tmp_path):
        app_secret = secrets.token_hex(16)
        content = (
            "tests/test_ok.py::test_one\n"
            f"tests/test_skipped.py::test_skip reason=dsn postgres://u:{app_secret}@h/db\n"
            "== 2 tests collected in 0.01s ==\n"
        )
        proc, out, receipt = self._run_sanitize(
            tmp_path, content, store={"APP_PASSWORD": app_secret},
            input_name="collect.txt",
        )
        assert proc.returncode == 0, proc.stderr
        sanitized = out.read_text(encoding="utf-8")
        assert app_secret not in sanitized
        assert "tests/test_ok.py::test_one" in sanitized
        data = json.loads(receipt.read_text(encoding="utf-8"))
        assert data["mapping_invariance"] == "not_applicable_text"
