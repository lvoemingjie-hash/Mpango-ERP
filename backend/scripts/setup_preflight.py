#!/usr/bin/env python3
"""
Stdlib-only setup preflight validator (H7-R11).

Secret hygiene: DATABASE_URL / REDIS_URL are read ONLY from ``os.environ``
and from ``backend/.env`` — they are never accepted on the command line, so
no secret ever appears in argv (process listings / logs).  Output is only
``OK`` on success; every failure writes a FIXED neutral error to stderr and
exits non-zero.  No error ever echoes a URL, password, or Compose JSON.

Project isolation: any rendered service declaring an explicit
``container_name`` is rejected (a fixed name would collide across Compose
project namespaces).

Usage (initial mode — reads Compose JSON from stdin):
    docker compose --env-file backend/.env config --format json | \
        python scripts/setup_preflight.py --env-file backend/.env

Usage (post-install mode — imports core.config.settings):
    python scripts/setup_preflight.py --env-file backend/.env --post-install
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DB_SCHEMES = ("postgresql", "postgresql+asyncpg")
# Compose v2 emits env-substituted `published` ports as a decimal-digit string.
_PUBLISHED_RE = re.compile(r"^[0-9]+$")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _fail(msg: str) -> None:
    """Write a neutral error and exit.  Never includes secret values."""
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def _is_loopback(host: str) -> bool:
    return host in ("localhost", "127.0.0.1", "::1")


def _target_int(value, svc_name: str) -> int:
    """``target`` (container port) must be an exact int — bool, float, string,
    Unicode digits and structured types are all rejected."""
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{svc_name} port target must be an integer")
    return value


def _published_int(value, svc_name: str) -> int:
    """``published`` (host port) must be an exact int OR a complete ASCII
    ``[0-9]+`` string with no whitespace or trailing characters (the form
    Compose v2 emits for env-substituted published ports).  bool, float,
    Unicode-digit strings, whitespace-bearing strings and structured types are
    rejected.  ``fullmatch`` is required: ``re.match`` with a ``$`` anchor
    accepts a trailing newline, which violates the contract."""
    if isinstance(value, bool):
        _fail(f"{svc_name} port published must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _PUBLISHED_RE.fullmatch(value):
        return int(value)
    _fail(f"{svc_name} port published must be an integer")


# ---------------------------------------------------------------------------
# strict .env parser
# ---------------------------------------------------------------------------
def parse_env_file(path: str) -> dict[str, str]:
    """Parse a .env file into a dict.  Keys must match [A-Za-z_][A-Za-z0-9_]*.
    Reject export syntax, duplicates, malformed lines, bad quotes and any
    non-UTF-8 content with a single fixed neutral error."""
    seen: dict[str, str] = {}
    try:
        fh = open(path, encoding="utf-8")
    except (FileNotFoundError, OSError):
        _fail("backend/.env not readable")
    try:
        with fh:
            for lineno, raw in enumerate(fh, 1):
                s = raw.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("export "):
                    _fail(f"malformed .env line {lineno}: export syntax rejected")
                if "=" not in s:
                    _fail(f"malformed .env line {lineno}: missing =")
                key, val = s.split("=", 1)
                key = key.strip()
                if not _ENV_KEY_RE.match(key):
                    _fail(f"malformed .env line {lineno}: invalid key")
                if key in seen:
                    _fail(f"duplicate key in .env: {key}")
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    inner = val[1:-1]
                    if val[0] in inner:
                        _fail(f"malformed .env line {lineno}: mismatched quotes")
                    val = inner
                elif val.startswith('"') or val.startswith("'"):
                    _fail(f"malformed .env line {lineno}: unclosed quote")
                seen[key] = val
    except UnicodeDecodeError:
        _fail("backend/.env is not valid UTF-8")
    return seen


# ---------------------------------------------------------------------------
# URL parsers
# ---------------------------------------------------------------------------
def parse_db_url(url: str) -> tuple[str, str, str, int, str]:
    """Return (user, password, host, port, database) from a DATABASE_URL.

    Accepts exactly the postgresql / postgresql+asyncpg schemes (no global
    string replacement).  Rejects blank passwords and malformed URLs."""
    try:
        u = urlparse(url)
    except Exception:
        _fail("DATABASE_URL is malformed")
    if u.scheme not in _DB_SCHEMES:
        _fail("DATABASE_URL scheme is not postgresql")
    user = unquote(u.username) if u.username else ""
    password = unquote(u.password) if u.password else ""
    host = u.hostname or ""
    try:
        port = u.port if u.port is not None else 5432
    except (ValueError, TypeError):
        _fail("DATABASE_URL has an invalid port")
    database = u.path.lstrip("/") or ""
    if not user or not database:
        _fail("DATABASE_URL must contain a username and database")
    if not password:
        _fail("DATABASE_URL must contain a password")
    return user, password, host, port, database


def parse_redis_url(url: str) -> tuple[str, int, int]:
    """Return (host, port, logical_database_index) from a REDIS_URL.

    Documented identity policy (R1-R4): the URL must use scheme redis, carry
    NO credentials, NO query string and NO fragment, and MUST include an
    explicit numeric logical database index in the path (for example /0).
    The index is part of the Redis identity the host setup context and the
    container runtime context must share, so any malformed, index-less,
    query-bearing or fragment-bearing form fails closed."""
    try:
        u = urlparse(url)
    except Exception:
        _fail("REDIS_URL is malformed")
    if u.scheme != "redis":
        _fail("REDIS_URL scheme is not redis")
    if u.username or u.password:
        _fail("REDIS_URL must not carry credentials (Compose Redis is no-auth)")
    if u.query:
        _fail("REDIS_URL must not carry a query string")
    if u.fragment:
        _fail("REDIS_URL must not carry a fragment")
    host = u.hostname or ""
    try:
        port = u.port if u.port is not None else 6379
    except (ValueError, TypeError):
        _fail("REDIS_URL has an invalid port")
    index = u.path.lstrip("/")
    if not index.isdigit():
        _fail("REDIS_URL must include a numeric logical database index "
              "(for example /0)")
    return host, port, int(index)


# ---------------------------------------------------------------------------
# Compose port-object validator
# ---------------------------------------------------------------------------
def parse_public_frontend_url(value):
    """R1-R6: stdlib-only shape validation of the PUBLIC_FRONTEND_URL runtime
    input.  Mirrors the SHAPE rules of the authoritative production Settings
    validator (absolute https origin; no credentials/query/fragment; origin
    only, where a single trailing slash is accepted and stripped) WITHOUT
    importing product Settings.  Returns (origin, None) on success or
    (None, error) with a FIXED neutral message that never echoes the value.
    """
    if not isinstance(value, str) or value == "":
        return None, "PUBLIC_FRONTEND_URL not found in backend/.env"
    from urllib.parse import urlsplit
    parts = urlsplit(value)
    if parts.scheme != "https":
        return None, "PUBLIC_FRONTEND_URL must use https"
    if not parts.netloc:
        return None, "PUBLIC_FRONTEND_URL must include a host"
    if parts.username or parts.password:
        return None, "PUBLIC_FRONTEND_URL must not contain credentials"
    if parts.query:
        return None, "PUBLIC_FRONTEND_URL must not contain a query string"
    if parts.fragment:
        return None, "PUBLIC_FRONTEND_URL must not contain a fragment"
    if parts.path and parts.path != "/":
        return None, "PUBLIC_FRONTEND_URL must be an origin only (no path)"
    return value.rstrip("/"), None


def _validate_port_entry(
    services: dict, svc_name: str, target_int: int, published_int: int,
    require_env: bool = True,
) -> dict | None:
    """Validate exactly one object-form port mapping with the exact allowed
    field set.  ``target`` must be an exact int; ``published`` may be an exact
    int or an ASCII [0-9]+ string (Compose v2 form).  Returns the service
    environment dict — required for postgres, optional (absent allowed) for
    redis."""
    svc = services.get(svc_name)
    if not isinstance(svc, dict):
        _fail(f"{svc_name} service is not a dict")
    ports = svc.get("ports")
    if not isinstance(ports, list) or len(ports) != 1:
        _fail(f"{svc_name} ports must be a list with exactly one entry")
    entry = ports[0]
    if not isinstance(entry, dict):
        _fail(f"{svc_name} port entry must be an object (string form rejected)")
    if set(entry.keys()) != {"host_ip", "target", "published", "protocol", "mode"}:
        _fail(f"{svc_name} port entry has unknown or missing fields")
    if entry.get("mode") != "ingress":
        _fail(f"{svc_name} port mode must be ingress")
    if entry.get("protocol") != "tcp":
        _fail(f"{svc_name} port protocol must be tcp")
    if entry.get("host_ip") != "127.0.0.1":
        _fail(f"{svc_name} host_ip must be 127.0.0.1")
    if _target_int(entry.get("target"), svc_name) != target_int:
        _fail(f"{svc_name} port target mismatch")
    if _published_int(entry.get("published"), svc_name) != published_int:
        _fail(f"{svc_name} port published mismatch")
    env = svc.get("environment")
    if env is None and not require_env:
        return None
    if not isinstance(env, dict):
        _fail(f"{svc_name} environment must be a dict")
    return env


# ---------------------------------------------------------------------------
# initial mode (stdin Compose JSON + .env; process URLs from os.environ)
# ---------------------------------------------------------------------------
def run_initial(env_path: str) -> None:
    env = parse_env_file(env_path)
    file_db = env.get("DATABASE_URL", "")
    file_redis = env.get("REDIS_URL", "")
    file_rup = env.get("REPORTING_USER_PASSWORD", "")
    if not file_db:
        _fail("DATABASE_URL not found in backend/.env")
    if not file_redis:
        _fail("REDIS_URL not found in backend/.env")
    if not file_rup:
        _fail("REPORTING_USER_PASSWORD not found in backend/.env")

    # process-env vs file conflict (secrets read from os.environ, never argv).
    # R15-R1: an empty-but-present process REPORTING_USER_PASSWORD is also a conflict.
    proc_db = os.environ.get("DATABASE_URL", "")
    proc_redis = os.environ.get("REDIS_URL", "")
    proc_db_ct = os.environ.get("DATABASE_URL_CONTAINER", "")
    proc_redis_ct = os.environ.get("REDIS_URL_CONTAINER", "")
    if proc_db and proc_db != file_db:
        _fail("DATABASE_URL conflict: process env differs from backend/.env")
    if proc_redis and proc_redis != file_redis:
        _fail("REDIS_URL conflict: process env differs from backend/.env")
    file_db_ct = env.get("DATABASE_URL_CONTAINER", "")
    file_redis_ct = env.get("REDIS_URL_CONTAINER", "")
    if proc_db_ct and file_db_ct and proc_db_ct != file_db_ct:
        _fail("DATABASE_URL_CONTAINER conflict: process env differs from backend/.env")
    if proc_redis_ct and file_redis_ct and proc_redis_ct != file_redis_ct:
        _fail("REDIS_URL_CONTAINER conflict: process env differs from backend/.env")
    if "REPORTING_USER_PASSWORD" in os.environ and os.environ["REPORTING_USER_PASSWORD"] != file_rup:
        _fail("REPORTING_USER_PASSWORD conflict: process env differs from backend/.env")

    db_user, db_pass, db_host, db_port, db_name = parse_db_url(file_db)
    rd_host, rd_port, rd_db_index = parse_redis_url(file_redis)

    if not _is_loopback(db_host):
        _fail("DATABASE_URL host must be local")
    if not _is_loopback(rd_host):
        _fail("REDIS_URL host must be local")
    try:
        cfg = json.load(sys.stdin)
    except Exception:
        _fail("Could not parse Compose JSON from stdin")
    if not isinstance(cfg, dict):
        _fail("Compose root is not a dict")
    services = cfg.get("services")
    if not isinstance(services, dict):
        _fail("Compose services is not a dict")

    # project isolation: no rendered service may pin a container_name (the
    # value would collide across project namespaces). Fixed neutral error;
    # the container_name value itself is never echoed.
    for _svc_name, _svc in services.items():
        if isinstance(_svc, dict) and "container_name" in _svc:
            _fail(f"{_svc_name} declares an explicit container_name")

    pg_env = _validate_port_entry(services, "postgres", 5432, db_port)
    _validate_port_entry(services, "redis", 6379, rd_port, require_env=False)

    # ------------------------------------------------------------------
    # Two-role DB authority (MPANGO-TENANT-BOOTSTRAP-DB-AUTHORITY R1):
    # DATABASE_URL binds the RUNTIME role; MPANGO_DB_ADMIN_URL binds the
    # cluster administrator (the Compose postgres account) and is setup-time
    # only; MPANGO_DB_MIGRATE_URL binds the migration authority.  The three
    # roles must be pairwise distinct (a single-role configuration is
    # rejected here, before any side effect), all three must target one
    # endpoint/database, and the provisioning passwords must equal the
    # passwords embedded in the runtime/migration URLs so the provisioned
    # roles are exactly the roles those URLs will use.
    admin_url = env.get("MPANGO_DB_ADMIN_URL", "")
    migrate_url = env.get("MPANGO_DB_MIGRATE_URL", "")
    app_password = env.get("MPANGO_DB_APP_PASSWORD", "")
    migrate_password = env.get("MPANGO_DB_MIGRATE_PASSWORD", "")
    if not admin_url:
        _fail("MPANGO_DB_ADMIN_URL not found in backend/.env")
    if not migrate_url:
        _fail("MPANGO_DB_MIGRATE_URL not found in backend/.env")
    if not app_password:
        _fail("MPANGO_DB_APP_PASSWORD not found in backend/.env")
    if not migrate_password:
        _fail("MPANGO_DB_MIGRATE_PASSWORD not found in backend/.env")
    if not env.get("DATABASE_URL_CONTAINER"):
        _fail("DATABASE_URL_CONTAINER not found in backend/.env")
    if not env.get("REDIS_URL_CONTAINER"):
        _fail("REDIS_URL_CONTAINER not found in backend/.env")
    admin_user, admin_pass, admin_host, admin_port, admin_db = parse_db_url(admin_url)
    mig_user, mig_pass, mig_host, mig_port, mig_db = parse_db_url(migrate_url)
    if not _is_loopback(admin_host):
        _fail("MPANGO_DB_ADMIN_URL host must be local")
    if not _is_loopback(mig_host):
        _fail("MPANGO_DB_MIGRATE_URL host must be local")
    if admin_user == db_user or mig_user == db_user or admin_user == mig_user:
        _fail("single-role configuration rejected: admin, migration and "
              "runtime URLs must bind three distinct roles")
    if (admin_host, admin_port) != (db_host, db_port) or             (mig_host, mig_port) != (db_host, db_port):
        _fail("admin, migration and runtime URLs must target one endpoint")
    if mig_db != db_name:
        _fail("migration and runtime URLs must target the application database")
    if app_password != db_pass:
        _fail("MPANGO_DB_APP_PASSWORD does not match the runtime DATABASE_URL "
              "password")
    if migrate_password != mig_pass:
        _fail("MPANGO_DB_MIGRATE_PASSWORD does not match the migration URL "
              "password")
    # The Compose postgres account is the ADMIN of the two-role contract, not
    # the application identity: the runtime DATABASE_URL must NOT name it.
    if admin_user != pg_env.get("POSTGRES_USER", ""):
        _fail("MPANGO_DB_ADMIN_URL username does not match Compose POSTGRES_USER")
    if admin_pass != pg_env.get("POSTGRES_PASSWORD", ""):
        _fail("MPANGO_DB_ADMIN_URL password does not match Compose POSTGRES_PASSWORD")
    if admin_db != pg_env.get("POSTGRES_DB", ""):
        _fail("MPANGO_DB_ADMIN_URL database does not match Compose POSTGRES_DB")
    # ------------------------------------------------------------------
    # Container runtime context (R1-R3): DATABASE_URL_CONTAINER and
    # REDIS_URL_CONTAINER are what the rendered backend service receives.
    # They must bind the SAME role/database/password identity as their host
    # counterparts, translated ONLY to the Compose service DNS name and the
    # container target port.  Host loopback addresses inside the container
    # context, unknown service names, wrong target ports and any
    # role/database/password drift all fail closed.
    container_db = env.get("DATABASE_URL_CONTAINER", "")
    container_redis = env.get("REDIS_URL_CONTAINER", "")
    ct_user, ct_pass, ct_host, ct_port, ct_database = parse_db_url(container_db)
    rd_ct_host, rd_ct_port, rd_ct_db_index = parse_redis_url(container_redis)
    if ct_host in ("localhost", "127.0.0.1", "::1"):
        _fail("DATABASE_URL_CONTAINER host must be the Compose service name, "
              "not a loopback host (the backend container cannot reach the "
              "host loopback)")
    if ct_host != "postgres":
        _fail("DATABASE_URL_CONTAINER host must be the Compose postgres "
              "service")
    if ct_port != 5432:
        _fail("DATABASE_URL_CONTAINER port must be the postgres container "
              "target port")
    if (ct_user, ct_pass, ct_database) != (db_user, db_pass, db_name):
        _fail("container runtime URL does not bind the same role, password "
              "and database identity as the host runtime DATABASE_URL")
    if rd_ct_host != "redis":
        _fail("REDIS_URL_CONTAINER host must be the Compose redis service")
    if rd_ct_port != 6379:
        _fail("REDIS_URL_CONTAINER port must be the redis container target "
              "port")
    if rd_ct_db_index != rd_db_index:
        _fail("host and container Redis URLs must use the same logical "
              "database index")

    # R15-R1: the rendered backend service MUST exist and carry a string
    # REPORTING_USER_PASSWORD that exactly matches .env. Missing service,
    # missing/non-dict environment, missing key, null/bool/int/list values,
    # or a value mismatch all fail closed with a fixed neutral error.
    _backend = services.get("backend")
    if not isinstance(_backend, dict):
        _fail("backend service is not a dict")
    _backend_env = _backend.get("environment")
    if not isinstance(_backend_env, dict):
        _fail("backend environment must be a dict")
    # The rendered backend service receives ONLY the runtime DATABASE_URL.
    # Every setup-only credential (admin/migration URLs, role passwords,
    # reporting-user password) is refused here: those are consumed by the
    # setup phases from backend/.env and must never reach the runtime
    # environment.
    # Only the five setup-only credentials are banned BY KEY.  The runtime
    # DATABASE_URL/REDIS_URL keys must exist under exactly those names (the
    # application reads settings.DATABASE_URL), but their VALUES must be the
    # container context — enforced by the equality checks against
    # DATABASE_URL_CONTAINER / REDIS_URL_CONTAINER below, which is what
    # rejects a host-loopback URL leaking into the container environment.
    for _setup_key in (
        "MPANGO_DB_ADMIN_URL",
        "MPANGO_DB_MIGRATE_URL",
        "MPANGO_DB_MIGRATE_PASSWORD",
        "MPANGO_DB_APP_PASSWORD",
        "REPORTING_USER_PASSWORD",
    ):
        if _setup_key in _backend_env:
            _fail(f"backend service environment must not contain {_setup_key}")
    # the rendered KEY names stay DATABASE_URL/REDIS_URL (the application
    # reads settings.DATABASE_URL); the VALUES must be the container context
    _backend_url = _backend_env.get("DATABASE_URL")
    if not isinstance(_backend_url, str):
        _fail("backend service must carry the runtime DATABASE_URL")
    if _backend_url != container_db:
        _fail("backend service DATABASE_URL does not match the container "
              "runtime context in backend/.env (DATABASE_URL_CONTAINER)")
    _backend_redis = _backend_env.get("REDIS_URL")
    if not isinstance(_backend_redis, str):
        _fail("backend service must carry the runtime REDIS_URL")
    if _backend_redis != container_redis:
        _fail("backend service REDIS_URL does not match the container "
              "runtime context in backend/.env (REDIS_URL_CONTAINER)")

    # R1-R6: PUBLIC_FRONTEND_URL is an explicit required runtime input.
    # backend/.env is authoritative; the rendered backend service must carry
    # the exact same value.  The shape rules mirrored here (stdlib only) are
    # enforced authoritatively by production Settings at application import.
    _pfu_value = env.get("PUBLIC_FRONTEND_URL", "")
    _pfu_origin, _pfu_err = parse_public_frontend_url(_pfu_value)
    if _pfu_err:
        _fail(_pfu_err)
    _rendered_pfu = _backend_env.get("PUBLIC_FRONTEND_URL")
    if _rendered_pfu is None:
        _fail("backend service environment must carry PUBLIC_FRONTEND_URL")
    if not isinstance(_rendered_pfu, str):
        _fail("backend service PUBLIC_FRONTEND_URL must be a string")
    if _rendered_pfu != _pfu_value:
        _fail("backend service PUBLIC_FRONTEND_URL does not match backend/.env")

    print("OK")


# ---------------------------------------------------------------------------
# post-install mode (imports core.config)
# ---------------------------------------------------------------------------
def run_post_install(env_path: str) -> None:
    env = parse_env_file(env_path)
    file_db = env.get("DATABASE_URL", "")
    file_redis = env.get("REDIS_URL", "")
    file_rup = env.get("REPORTING_USER_PASSWORD", "")
    if not file_db:
        _fail("DATABASE_URL not found in backend/.env")
    if not file_redis:
        _fail("REDIS_URL not found in backend/.env")
    if not file_rup:
        _fail("REPORTING_USER_PASSWORD not found in backend/.env")

    # make the backend package root importable regardless of cwd
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from core.config import settings  # noqa: imported only after pip
    except Exception:
        _fail("Could not import core.config.settings")

    if settings.DATABASE_URL != file_db:
        _fail("settings.DATABASE_URL differs from backend/.env after pip install")
    if getattr(settings, "REDIS_URL", "") != file_redis:
        _fail("settings.REDIS_URL differs from backend/.env after pip install")

    print("OK")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Setup preflight validator")
    parser.add_argument("--env-file", required=True, help="Path to backend/.env")
    parser.add_argument("--post-install", action="store_true", help="Post-install mode")
    args = parser.parse_args()

    if args.post_install:
        run_post_install(args.env_file)
    else:
        run_initial(args.env_file)


if __name__ == "__main__":
    main()
