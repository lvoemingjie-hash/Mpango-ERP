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


def parse_redis_url(url: str) -> tuple[str, int]:
    """Return (host, port) from a REDIS_URL.  Rejects credentials — the
    current Compose Redis service is no-auth, so a credentialed URL cannot
    connect and must fail closed."""
    try:
        u = urlparse(url)
    except Exception:
        _fail("REDIS_URL is malformed")
    if u.scheme != "redis":
        _fail("REDIS_URL scheme is not redis")
    if u.username or u.password:
        _fail("REDIS_URL must not carry credentials (Compose Redis is no-auth)")
    host = u.hostname or ""
    try:
        port = u.port if u.port is not None else 6379
    except (ValueError, TypeError):
        _fail("REDIS_URL has an invalid port")
    return host, port


# ---------------------------------------------------------------------------
# Compose port-object validator
# ---------------------------------------------------------------------------
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
    if not file_db:
        _fail("DATABASE_URL not found in backend/.env")
    if not file_redis:
        _fail("REDIS_URL not found in backend/.env")

    # process-env vs file conflict (secrets read from os.environ, never argv)
    proc_db = os.environ.get("DATABASE_URL", "")
    proc_redis = os.environ.get("REDIS_URL", "")
    if proc_db and proc_db != file_db:
        _fail("DATABASE_URL conflict: process env differs from backend/.env")
    if proc_redis and proc_redis != file_redis:
        _fail("REDIS_URL conflict: process env differs from backend/.env")

    db_user, db_pass, db_host, db_port, db_name = parse_db_url(file_db)
    rd_host, rd_port = parse_redis_url(file_redis)

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

    if db_user != pg_env.get("POSTGRES_USER", ""):
        _fail("DATABASE_URL username does not match Compose POSTGRES_USER")
    if db_pass != pg_env.get("POSTGRES_PASSWORD", ""):
        _fail("DATABASE_URL password does not match Compose POSTGRES_PASSWORD")
    if db_name != pg_env.get("POSTGRES_DB", ""):
        _fail("DATABASE_URL database does not match Compose POSTGRES_DB")

    print("OK")


# ---------------------------------------------------------------------------
# post-install mode (imports core.config)
# ---------------------------------------------------------------------------
def run_post_install(env_path: str) -> None:
    env = parse_env_file(env_path)
    file_db = env.get("DATABASE_URL", "")
    file_redis = env.get("REDIS_URL", "")
    if not file_db:
        _fail("DATABASE_URL not found in backend/.env")
    if not file_redis:
        _fail("REDIS_URL not found in backend/.env")

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
