"""Permanent contract tests for the CI secret gates.

Covers the CTO R5 acceptance matrix (directive §A3):
clean GREEN; detector-recognizable synthetic canary RED; hardcoded-pattern
path RED; tool missing RED; corrupt baseline RED; paths with spaces covered;
workflow wiring real; baseline byte-immutable across runs; zero-file
enumeration RED. Canary values are public AWS documentation examples,
constructed at runtime; they never appear in assertions' expected output.

These tests exercise the gate scripts in this repository, so a mutation of
those scripts (e.g. restoring write-back scan or rc-swallowing shell) turns
the suite RED; byte-exact restore turns it GREEN again.

Run:  python -m pytest tests/ci --confcutdir=tests/ci -o addopts=""
Requires detect-secrets-hook (1.5.0) on PATH, e.g. the task venv.
"""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SECRETS_GATE = REPO / "tools" / "ci" / "secrets_gate.sh"
HARDCODED_GATE = REPO / "tools" / "ci" / "hardcoded_creds_gate.sh"
WORKFLOW = REPO / ".github" / "workflows" / "security-scan.yml"

AWS_EXAMPLE_SECRET = "wJalr" + "XUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
CANARY_PASSWORD = "SuperSecret123" + "!"
PINNED_VERSION = "1.5.0"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(script: Path, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(script), str(cwd)],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=120,
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(repo), check=True,
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "GIT_CONFIG_NOSYSTEM": "1",
             "HOME": os.environ.get("HOME", "/tmp")},
    )


@pytest.fixture()
def gate_env() -> dict:
    env = os.environ.copy()
    if shutil.which("detect-secrets-hook", path=env.get("PATH")) is None:
        pytest.skip("detect-secrets-hook not on PATH (task venv not activated)")
    version = subprocess.run(
        ["detect-secrets-hook", "--version"], capture_output=True, text=True, env=env
    ).stdout.strip()
    if version != PINNED_VERSION:
        pytest.skip(f"detect-secrets {version!r} != pinned {PINNED_VERSION!r}")
    return env


@pytest.fixture()
def clean_repo(tmp_path: Path, gate_env: dict) -> Path:
    repo = tmp_path / "fixture"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    (repo / "app.py").write_text('print("hello")\n')
    (repo / "README.md").write_text("# readme\n")
    _git(repo, "add", "-A")
    # Baseline creation via stdout (1.5.0 --baseline requires an existing file).
    baseline = subprocess.run(
        ["detect-secrets", "scan"], capture_output=True, text=True,
        cwd=str(repo), env=gate_env, check=True,
    ).stdout
    doc = json.loads(baseline)
    assert isinstance(doc.get("results"), dict)
    (repo / ".secrets.baseline").write_text(baseline)
    _git(repo, "add", "-A")
    return repo


def test_clean_tree_green_and_baseline_unchanged(clean_repo: Path, gate_env: dict):
    baseline = clean_repo / ".secrets.baseline"
    before = _sha256(baseline)
    proc = _run(SECRETS_GATE, clean_repo, gate_env)
    assert proc.returncode == 0, proc.stderr
    assert "no new secrets" in proc.stdout
    assert _sha256(baseline) == before


def test_canary_red_spaces_path_covered_no_value_leak(clean_repo: Path, gate_env: dict):
    baseline = clean_repo / ".secrets.baseline"
    before = _sha256(baseline)
    (clean_repo / "secret config.py").write_text(
        f'aws_secret_access_key = "{AWS_EXAMPLE_SECRET}"\n'
    )
    _git(clean_repo, "add", "-A")
    proc = _run(SECRETS_GATE, clean_repo, gate_env)
    assert proc.returncode == 1, (proc.stdout, proc.stderr)
    assert "secret config.py" in proc.stderr
    assert AWS_EXAMPLE_SECRET not in proc.stdout + proc.stderr
    assert _sha256(baseline) == before


def test_tool_missing_red(clean_repo: Path):
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp")}
    proc = _run(SECRETS_GATE, clean_repo, env)
    assert proc.returncode == 3
    assert "not found" in proc.stderr


def test_corrupt_baseline_red(clean_repo: Path, gate_env: dict):
    (clean_repo / ".secrets.baseline").write_text("not json")
    proc = _run(SECRETS_GATE, clean_repo, gate_env)
    assert proc.returncode == 4
    (clean_repo / ".secrets.baseline").write_text('{"foo": 1}')
    proc = _run(SECRETS_GATE, clean_repo, gate_env)
    assert proc.returncode == 4


def test_zero_file_enumeration_red(tmp_path: Path, gate_env: dict):
    repo = tmp_path / "empty-fixture"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    (repo / ".secrets.baseline").write_text('{"version": "1.5.0", "results": {}}')
    _git(repo, "add", "-A")
    proc = _run(SECRETS_GATE, repo, gate_env)
    assert proc.returncode == 5
    assert "clean" not in proc.stdout.lower()


def test_hardcoded_clean_green(clean_repo: Path, gate_env: dict):
    proc = _run(HARDCODED_GATE, clean_repo, gate_env)
    assert proc.returncode == 0, proc.stderr


def test_hardcoded_canary_red_location_reported_value_suppressed(clean_repo: Path, gate_env: dict):
    (clean_repo / "db.py").write_text(f'password = "{CANARY_PASSWORD}"\n')
    _git(clean_repo, "add", "-A")
    proc = _run(HARDCODED_GATE, clean_repo, gate_env)
    assert proc.returncode == 1
    assert "db.py:1" in proc.stderr
    assert CANARY_PASSWORD not in proc.stdout + proc.stderr


def test_hardcoded_exclusion_semantics_proven(clean_repo: Path, gate_env: dict):
    excluded = clean_repo / "backend" / "tests"
    excluded.mkdir(parents=True)
    (excluded / "db.py").write_text(f'password = "{CANARY_PASSWORD}"\n')
    _git(clean_repo, "add", "-A")
    proc = _run(HARDCODED_GATE, clean_repo, gate_env)
    assert proc.returncode == 0, proc.stderr


def test_workflow_wires_real_implementation():
    import yaml

    doc = yaml.safe_load(WORKFLOW.read_text())
    steps = {s.get("id"): s for s in doc["jobs"]["secret-detection"]["steps"] if s.get("id")}

    ds_run = steps["detect-secrets"]["run"]
    assert "tools/ci/secrets_gate.sh" in ds_run
    assert f"detect-secrets=={PINNED_VERSION}" in ds_run
    assert "--baseline" not in ds_run, "write-back scan must not reappear in the step"

    hc_run = steps["hardcoded-credentials"]["run"]
    assert hc_run.strip() == "tools/ci/hardcoded_creds_gate.sh"

    summary = steps and next(
        s["run"] for s in doc["jobs"]["secret-detection"]["steps"]
        if s.get("name") == "Security scan summary"
    )
    assert "steps.detect-secrets.outcome" in summary
    assert "steps.hardcoded-credentials.outcome" in summary
    assert "All security checks completed" not in summary


def test_gate_scripts_executable_and_syntax_clean():
    for script in (SECRETS_GATE, HARDCODED_GATE):
        assert os.access(script, os.X_OK), f"{script} not executable"
        subprocess.run(["bash", "-n", str(script)], check=True, capture_output=True)
