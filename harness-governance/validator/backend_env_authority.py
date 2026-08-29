"""HE2-ET1-R3 shared stdlib backend-CWD / temporary-database authority module.

THE single implementation of the backend CWD + temp-DB authority contract.
The authority runner's preflight AND the child plugin's pytest_sessionstart
both bootstrap THIS module from its canonical path (origin-verified, raw
bytes digest-bound — never a trusted sys.modules cache) and call its pure
probe. Protocol/parsing code is never duplicated in consumers.

Machine contract enforced (nothing of it lives in prose):
  1. the authority CWD is exactly the repository's canonical `backend/`
     directory (exists, is a real directory, not a symlink, resolved);
  2. MPANGO_ENV is exactly `test` or `testing`;
  3. TEST_DATABASE_URL's database name fullmatches
     ^(?:test|pytest|ci)[_-][a-z0-9_-]+$
     (an unsafe name such as `mpango_erp_test` fails closed);
  4. TEST_DATABASE_URL's actual port (explicit or default 5432) is a member
     of MPANGO_TEMP_DB_ALLOWED_PORTS (comma-separated integers; a missing
     or empty allowlist fails closed);
  5. TEST_DATABASE_URL's host is a loopback address or a member of
     MPANGO_TEMP_DB_ALLOWED_HOSTS.

Sanitization: every outcome is a FIXED category from BACKEND_ENV_CATEGORIES
(no paths, no URLs, no hosts, no ports, no credential values — numbers that
ARE the evidence, such as a port number, are published only as membership
booleans, never echoed). All parse/OS failures map to fixed categories; no
raw exception escapes the probe.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_ENV_KEY = "et1_backend_env_authority"

MPANGO_ENV_ALLOWED = frozenset({"test", "testing"})
DB_NAME_PATTERN = re.compile(r"^(?:test|pytest|ci)[_-][a-z0-9_-]+$")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DEFAULT_PG_PORT = 5432

BACKEND_ENV_CATEGORIES = frozenset(
    {
        "cwd_not_canonical",
        "mpango_env_missing",
        "mpango_env_invalid",
        "db_url_absent",
        "db_name_unsafe",
        "db_port_allowlist_missing",
        "db_port_not_allowed",
        "host_not_allowed",
        "ok",
    }
)

# Child-side `benv:<label>` translations (fixed set; asserted by tests).
CHILD_LABELS = frozenset(
    {
        "cwd_not_canonical", "mpango_env_missing", "mpango_env_invalid",
        "db_url_absent", "db_name_unsafe", "db_port_allowlist_missing",
        "db_port_not_allowed", "host_not_allowed", "digest_missing",
        "digest_mismatch",
    }
)


class BackendEnvAuthorityError(Exception):
    """Sanitized probe failure; `category` is a fixed label from
    BACKEND_ENV_CATEGORIES. Never carries path/URL/host/port/credential
    values or chainable context."""

    def __init__(self, category: str):
        super().__init__(f"backend_env:{category}")
        self.category = category


def canonical_backend_dir(module_file) -> Path:
    """The repository's canonical backend/ directory, resolved relative to
    the consuming file (each consumer bootstraps its own resolution; both
    must land on the same path)."""
    return (Path(module_file).resolve().parents[2] / "backend").resolve()


def _parse_allowlist(raw: str) -> list:
    ports = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ports.append(int(part))
        except ValueError:
            raise BackendEnvAuthorityError("db_port_allowlist_missing") from None
    return ports


def backend_env_facts(url: str, mpango_env: str, allowed_ports_raw: str,
                      allowed_hosts_raw: str, authority_cwd) -> dict:
    """Core probe: validates every invariant and returns the ACCEPTED FACTS
    (values stay in-process; callers bind them into a digest and publish
    only booleans/fixed categories)."""
    cwd = Path(authority_cwd)
    if (
        not cwd.exists()
        or cwd.name != "backend"
        or not cwd.is_dir()
        or cwd.is_symlink()
    ):
        raise BackendEnvAuthorityError("cwd_not_canonical")
    env = (mpango_env or "").strip()
    if not env:
        raise BackendEnvAuthorityError("mpango_env_missing")
    if env not in MPANGO_ENV_ALLOWED:
        raise BackendEnvAuthorityError("mpango_env_invalid")
    raw_url = (url or "").strip()
    if not raw_url:
        raise BackendEnvAuthorityError("db_url_absent")
    db_name = urllib_path(raw_url).strip("/")
    if not db_name or not DB_NAME_PATTERN.fullmatch(db_name):
        raise BackendEnvAuthorityError("db_name_unsafe")
    port, host = urllib_host_port(raw_url)
    ports = _parse_allowlist(allowed_ports_raw)
    if not ports:
        raise BackendEnvAuthorityError("db_port_allowlist_missing")
    if port not in ports:
        raise BackendEnvAuthorityError("db_port_not_allowed")
    hosts = {h.strip() for h in (allowed_hosts_raw or "").split(",") if h.strip()}
    if host not in LOOPBACK_HOSTS and host not in hosts:
        raise BackendEnvAuthorityError("host_not_allowed")
    canonical_ports = ",".join(str(x) for x in sorted(ports))
    canonical_hosts = ",".join(sorted(hosts))
    return {
        "mpango_env": env,
        "db_name": db_name,
        "port": port,
        "host": host,
        "allowed_ports": canonical_ports,
        "allowed_hosts": canonical_hosts,
        "authority_cwd": str(cwd),
    }


def check_backend_env(url: str, mpango_env: str, allowed_ports_raw: str,
                      allowed_hosts_raw: str, authority_cwd) -> dict:
    """Pure probe over the given values (no process state). Raises
    BackendEnvAuthorityError(category) on the FIRST failing invariant;
    returns sanitized booleans on success. `authority_cwd` is the directory
    the authority command will run in — not the probe caller's CWD."""
    backend_env_facts(url, mpango_env, allowed_ports_raw, allowed_hosts_raw,
                      authority_cwd)
    return {
        "backend_env": "ok",
        "mpango_env_valid": True,
        "db_name_safe": True,
        "port_allowed": True,
        "host_allowed": True,
        "cwd_canonical": True,
        "auth_used": False,
    }


def urllib_path(url: str) -> str:
    import urllib.parse

    try:
        return urllib.parse.urlsplit(url).path or "/"
    except ValueError:
        raise BackendEnvAuthorityError("db_name_unsafe") from None


def urllib_host_port(url: str) -> tuple:
    import urllib.parse

    try:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname
        if not host:
            raise BackendEnvAuthorityError("db_url_absent")
        port = parsed.port  # ValueError on invalid port strings
    except ValueError as err:
        if isinstance(err, BackendEnvAuthorityError):
            raise
        raise BackendEnvAuthorityError("db_url_absent") from None
    return (port if port is not None else DEFAULT_PG_PORT), host


def binding_digest(facts_digest_input: str) -> str:
    import hashlib

    return hashlib.sha256(facts_digest_input.encode("utf-8")).hexdigest()


# ─── R3-A1: profile-bound alembic successor authority ───────────────────────

ALEMBIC_CATEGORIES = frozenset(
    {
        "alembic_multiple_heads", "alembic_head_mismatch",
        "alembic_parent_mismatch", "alembic_tree_unreadable",
    }
)


def _parse_revision_field(text: str, field: str):
    """Extract a single-string revision/down_revision declaration; returns
    (value, None) or (None, kind) when the field is absent or a non-single
    (merge) declaration — merge parents are never single successors."""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith(field):
            continue
        rest = line[len(field):].lstrip()
        # tolerate PEP annotations: down_revision: str | None = "x"
        rest = re.sub(r"^:[^=]*", "", rest).lstrip()
        if not rest.startswith("="):
            continue
        value = rest[1:].strip()
        if value.startswith("(") or value.startswith("["):
            return None, "merge"
        m = re.match(r"^['\"]([a-z0-9_]+)['\"]", value)
        if m:
            return m.group(1), None
        return None, "unparsed"
    return None, None


def alembic_scan(versions_dir) -> dict:
    """Parse backend/alembic/versions with pure stdlib: every revision, its
    down_revision, and the resulting head set. Byte-exact ids only — no
    startswith/regex/allowlist fuzzy acceptance anywhere."""
    versions = Path(versions_dir)
    if not versions.is_dir():
        raise BackendEnvAuthorityError("alembic_tree_unreadable")
    revisions = {}
    for path in sorted(versions.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="strict")
        rev = re.search(r"^revision(?::\s*str)?\s*=\s*['\"]([a-z0-9_]+)['\"]", text, re.M)
        if not rev:
            continue
        down, kind = _parse_revision_field(text, "down_revision")
        revisions[rev.group(1)] = {"down": down, "kind": kind, "file": path}
    if not revisions:
        raise BackendEnvAuthorityError("alembic_tree_unreadable")
    referenced = {d for v in revisions.values()
                  for d in ([v["down"]] if v["down"] else [])}
    heads = sorted(set(revisions) - referenced)
    return {"revisions": revisions, "heads": heads}


def alembic_verify(versions_dir, expected_head: str,
                   expected_parent: str | None = None) -> dict:
    """Profile-bound successor authority: exactly ONE head; byte-exact
    equality with the profile's expected head; and, when the profile
    declares an expected parent, the actual head's down_revision must be
    that exact single predecessor (a merge or any other lineage fails)."""
    scan = alembic_scan(versions_dir)
    if len(scan["heads"]) != 1:
        raise BackendEnvAuthorityError("alembic_multiple_heads")
    actual = scan["heads"][0]
    if actual != expected_head:
        raise BackendEnvAuthorityError("alembic_head_mismatch")
    entry = scan["revisions"][actual]
    if expected_parent is not None:
        if entry["kind"] is not None or entry["down"] != expected_parent:
            raise BackendEnvAuthorityError("alembic_parent_mismatch")
    return {"alembic_head": actual,
            "alembic_parent": entry["down"],
            "alembic_head_count": 1}
