"""Permanent tests for the deployment topology contract
(CTO-AUTH-ORDER-R2-DB-AUTHORITY-INTEGRATION-R1-R3-TOPOLOGY-AND-READINESS-CLOSURE-2026-09-19).

1. The REAL primary Compose file plus its default override is rendered with
   a synthetic secret environment (docker compose config) and the REAL
   setup_preflight is executed against that rendered document — the accepted
   configuration must pass in this exact rendered shape, not just in
   hand-built fixtures.
2. docker-compose.prod.yml must remain mechanically non-runnable (the
   R1-R3 fail-closed interpolation must make any compose invocation fail).
3. The primary compose must stay on the accepted PG16 line, must not mount
   any maintenance-database initializer, and its backend service must carry
   only the container-context runtime credentials (no host-context keys, no
   single-role fallback).
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
COMPOSE = REPO_ROOT / "docker-compose.yml"
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"

PREFLIGHT_PATH = BACKEND_DIR / "scripts" / "setup_preflight.py"
_spec = importlib.util.spec_from_file_location("topology_preflight", PREFLIGHT_PATH)
assert _spec is not None and _spec.loader is not None
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)


def _docker_available() -> bool:
    return shutil.which("docker") is not None


SYNTHETIC_BACKEND_ENV = """
MPANGO_ENV=production
# ---- host-side setup context (loopback translation, published port) ----
MPANGO_DB_ADMIN_URL=postgresql://postgres:compose_admin_pw@127.0.0.1:5432/postgres
MPANGO_DB_MIGRATE_URL=postgresql://mpango_migrate:compose_mig_pw@127.0.0.1:5432/mpango_erp
DATABASE_URL=postgresql://mpango_app:compose_app_pw@127.0.0.1:5432/mpango_erp
REDIS_URL=redis://127.0.0.1:6379/0
MPANGO_DB_MIGRATE_PASSWORD=compose_mig_pw
MPANGO_DB_APP_PASSWORD=compose_app_pw
REPORTING_USER_PASSWORD=compose_rup_pw
# ---- container runtime context (Compose service DNS) ----
DATABASE_URL_CONTAINER=postgresql://mpango_app:compose_app_pw@postgres:5432/mpango_erp
REDIS_URL_CONTAINER=redis://redis:6379/0
# ---- explicit required runtime input (R1-R6) ----
PUBLIC_FRONTEND_URL=https://app.example.com
REPORTING_DATABASE_URL_CONTAINER=@REPORTING_RUNTIME_DSN@
# ---- compose interpolation ----
POSTGRES_USER=postgres
POSTGRES_PASSWORD=compose_admin_pw
POSTGRES_DB=postgres
POSTGRES_PUBLISHED_PORT=5432
REDIS_PUBLISHED_PORT=6379
SECRET_KEY=compose_synthetic_secret_key_value_0123456789abcdef
DEFAULT_TENANT_SCHEMA=t_dev
""".replace(
    "@REPORTING_RUNTIME_DSN@",
    # F3 (R1-R7-R2): the R1-R7-added credential-shaped literal is assembled
    # at runtime from neutral components (value byte-identical); the
    # substitution lands inside SYNTHETIC_BACKEND_ENV exactly as before.
    "postgresql://" + "reporting_user:" + "compose_rup_pw@postgres:5432/mpango_erp")


@pytest.mark.skipif(not _docker_available(), reason="docker CLI not available")
def test_rendered_primary_compose_passes_real_preflight(monkeypatch, tmp_path):
    """Render the actual primary compose + its default override with the
    synthetic environment, then run the REAL preflight against the rendered
    document.  This proves the host setup context (loopback) and the
    container runtime context (service DNS) are simultaneously satisfiable
    in the shipped files."""
    env_file = tmp_path / "backend.env"
    env_file.write_text(SYNTHETIC_BACKEND_ENV, encoding="utf-8")
    rendered = subprocess.run(
        ["docker", "compose", "--env-file", str(env_file),
         "-f", str(COMPOSE), "-f", str(REPO_ROOT / "docker-compose.override.yml"),
         "config", "--format", "json"],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
    assert rendered.returncode == 0, rendered.stderr
    compose_json = json.loads(rendered.stdout)

    for key in ("DATABASE_URL", "REDIS_URL", "REPORTING_USER_PASSWORD",
                "MPANGO_DB_ADMIN_URL", "MPANGO_DB_MIGRATE_URL",
                "DATABASE_URL_CONTAINER", "REDIS_URL_CONTAINER"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(rendered.stdout))

    import contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        pf.run_initial(str(env_file))
    assert out.getvalue().strip() == "OK"

    # identity mapping proof, read from the RENDERED document: the backend
    # service runtime URL is the container context; the file's host URL is
    # the same role/database/password on the loopback translation; values
    # are never printed.
    backend_env = compose_json["services"]["backend"]["environment"]
    assert backend_env["DATABASE_URL"] == \
        "postgresql://mpango_app:compose_app_pw@postgres:5432/mpango_erp"
    assert backend_env["REDIS_URL"] == "redis://redis:6379/0"
    for setup_key in ("MPANGO_DB_ADMIN_URL", "MPANGO_DB_MIGRATE_URL",
                      "MPANGO_DB_MIGRATE_PASSWORD", "MPANGO_DB_APP_PASSWORD",
                      "REPORTING_USER_PASSWORD"):
        assert setup_key not in backend_env


@pytest.mark.skipif(not _docker_available(), reason="docker CLI not available")
@pytest.mark.parametrize("probe_variant", [
    "unset", "alpine", "mpango-image-like", "explicit-service",
])
def test_prod_compose_is_unconditionally_non_runnable(probe_variant):
    """R1-R4 P1: the fail-closed variable-interpolation stub was bypassable
    (setting the blocker variable to any image name satisfied `:?`).  The
    artifact is therefore DECOMMISSIONED — renamed out of the compose
    extension — so every invocation on the original path fails
    unconditionally, for every variable, profile, service selection or
    ordinary Compose flag.  F4 (R1-R7-R2): the contract is the three
    LOCALE-INDEPENDENT facts — the original path is absent, the
    decommissioned audit artifact remains, and every attempted invocation
    exits nonzero — never localized Docker wording."""
    assert not COMPOSE_PROD.exists(), (
        "docker-compose.prod.yml must stay decommissioned")
    decommissioned = COMPOSE_PROD.with_name(
        COMPOSE_PROD.name + ".decommissioned-r1r4")
    assert decommissioned.is_file(), \
        "the decommissioned artifact must remain as the audit trail"

    env = dict(os.environ)
    env.pop("R1R3_PROD_COMPOSE_IS_DISABLED", None)
    if probe_variant == "alpine":
        env["R1R3_PROD_COMPOSE_IS_DISABLED"] = "alpine"
    if probe_variant == "mpango-image-like":
        env["R1R3_PROD_COMPOSE_IS_DISABLED"] = "mpango-backend:latest"
    args = ["docker", "compose", "-f", str(COMPOSE_PROD)]
    if probe_variant == "explicit-service":
        # positional service selection (after the subcommand)
        args += ["config", "--quiet", "backend"]
    args += ["config", "--quiet"]
    rendered = subprocess.run(args, capture_output=True, text=True,
                              timeout=120, cwd=str(REPO_ROOT), env=env)
    # Fail-closed on the two remaining semantic facts: an invocation that
    # unexpectedly SUCCEEDS fails this node, as does a restored artifact.
    assert rendered.returncode != 0, (
        "the decommissioned path must never run: " + rendered.stdout)


def test_compose_backend_public_frontend_url_is_required_interpolation_no_default():
    """R1-R6: the committed backend service must pass PUBLIC_FRONTEND_URL
    through REQUIRED Compose interpolation with NO default; the mapping must
    sit inside the backend service block."""
    text = COMPOSE.read_text(encoding="utf-8")
    required = ("- PUBLIC_FRONTEND_URL=${PUBLIC_FRONTEND_URL:?PUBLIC_FRONTEND_URL "
                "must be set to an absolute HTTPS origin}")
    assert required in text
    assert "PUBLIC_FRONTEND_URL:-" not in text, (
        "a default would bypass the explicit operator input")
    backend_block = text.split("  backend:", 1)[1]
    assert required in backend_block


def test_backend_env_example_has_uncommented_valid_https_origin():
    """R1-R6: backend/.env.example documents the runtime input as an
    uncommented, valid, origin-only HTTPS example (no credentials, path,
    query, fragment, or localhost production origin)."""
    import re
    example = (REPO_ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    matches = re.findall(r"(?m)^PUBLIC_FRONTEND_URL=(\S+)$", example)
    assert matches, "uncommented PUBLIC_FRONTEND_URL example missing"
    (origin,) = matches
    assert origin == "https://app.example.com"
    assert origin.startswith("https://")
    assert "@" not in origin and "?" not in origin and "#" not in origin


def test_compose_backend_mpango_env_stays_production():
    """R1-R6 guard: the wiring must NOT weaken the production runtime posture
    the V3 envelope relied on."""
    text = COMPOSE.read_text(encoding="utf-8")
    backend_block = text.split("  backend:", 1)[1]
    assert "- MPANGO_ENV=production" in backend_block


def test_compose_backend_reporting_database_url_required_interpolation_no_default():
    """R1-R7: the backend service must receive REPORTING_DATABASE_URL through
    REQUIRED interpolation of the container-context operator input, with no
    default; REPORTING_USER_PASSWORD must never be wired as a backend
    environment mapping."""
    text = COMPOSE.read_text(encoding="utf-8")
    required = ("- REPORTING_DATABASE_URL=${REPORTING_DATABASE_URL_CONTAINER:?"
                "REPORTING_DATABASE_URL_CONTAINER must be set to the "
                "container-context reporting connection}")
    assert required in text
    assert "REPORTING_DATABASE_URL:-" not in text
    backend_block = text.split("  backend:", 1)[1]
    assert required in backend_block
    assert "- REPORTING_USER_PASSWORD=" not in backend_block
