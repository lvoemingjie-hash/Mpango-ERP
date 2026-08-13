"""DC-12R1-H7-R4 — evidence-gate authenticity final closure.

Supersedes H7-R3. Closes the four Kilo findings (KILO-H7R3V1-001/002/003/004):

  * 001 — lock parser silently accepted/excluded malformed entries or raised
    unrelated exceptions. Now explicitly validates name, version, groups
    type/shape/content and raises a controlled ValueError for every form.
  * 002 — the requirements parser silently dropped extras and the broader
    wording overclaimed parity. Extras are now rejected; all public contract
    language has been narrowed to the exact phrase below.
  * 003 — install-path tests used raw substring checks, allowing comment-only /
    dead-branch / inert-string false greens. setup.sh and Dockerfile are now
    checked with structural source-shape guards and RED mutation tests.
  * 004 — GitNexus status reproducibility is host-specific; recorded as such.

The only supported parity claim is:

    *requirements.txt and Poetry's main-group lock inventory have identical
    canonical package names and exact versions.*

Markers, lock hashes, lock sources, extras (rejected in requirements.txt), and
actual installer behaviour are explicitly NOT compared here.  Native ``setup.sh``
execution remains a mandatory Lubuntu independent gate.

Every fail-closed helper in this file is the same function the mutation tests
exercise (no parser logic is copied into tests).
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

BACKEND_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS = BACKEND_DIR / "requirements.txt"
PYPROJECT = BACKEND_DIR / "pyproject.toml"
POETRY_LOCK = BACKEND_DIR / "poetry.lock"
SETUP_SH = BACKEND_DIR / "scripts" / "setup.sh"
DOCKERFILE = BACKEND_DIR / "Dockerfile"

EXPECTED = {
    "bcrypt": "4.0.1",
    "cryptography": "46.0.5",
    "openpyxl": "3.1.5",
    "et-xmlfile": "2.0.0",
    "passlib": "1.7.4",
}


# --------------------------------------------------------------------------- #
# fail-closed requirements parser  (KILO-H7R3V1-002 — extras now rejected)
# --------------------------------------------------------------------------- #
def parse_requirements_text(text: str) -> dict[str, str]:
    """Return ``{canonical_name: exact_version}`` from a requirements.txt body.

    Fail-closed:
      * parsed with ``packaging.requirements.Requirement``;
      * URL requirements, non-exact / wildcard specifiers, trailing garbage,
        invalid markers, and **extras** (e.g. ``[standard]``) are rejected;
      * duplicate canonical names (identical, conflicting, or cross-normalised)
        are rejected — last-wins overwrite is impossible.
    """
    out: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            req = Requirement(line)
        except InvalidRequirement as exc:
            raise ValueError(f"line {lineno}: malformed requirement {raw!r}: {exc}") from exc
        if req.url:
            raise ValueError(f"line {lineno}: URL requirements are not allowed: {raw!r}")
        # --- extras are NOT part of the name/version inventory contract ---
        if req.extras:
            raise ValueError(
                f"line {lineno}: extras are not allowed in the inventory contract: {raw!r}"
            )
        specs = list(req.specifier)
        if len(specs) != 1:
            raise ValueError(
                f"line {lineno}: exactly one version specifier required: {raw!r}"
            )
        spec = specs[0]
        if spec.operator != "==":
            raise ValueError(
                f"line {lineno}: only exact '==' pins allowed, got {spec.operator!r}: {raw!r}"
            )
        if "*" in str(spec.version):
            raise ValueError(f"line {lineno}: wildcard pins are not allowed: {raw!r}")
        name = canonicalize_name(req.name)
        if name in out:
            raise ValueError(
                f"line {lineno}: duplicate canonical package name {name!r}: {raw!r}"
            )
        out[name] = str(spec.version)
    return out


def parse_requirements_file() -> dict[str, str]:
    return parse_requirements_text(REQUIREMENTS.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# fail-closed lock parser  (KILO-H7R3V1-001 — exhaustive validation)
# --------------------------------------------------------------------------- #
def parse_main_lock_packages(packages: object) -> dict[str, str]:
    """Build ``{canonical_name: version}`` for main-group lock packages.

    Every package entry is validated before insertion; the function raises a
    controlled ``ValueError`` (never an unrelated exception) for:

      1. ``packages`` is not a list.
      2. entry is not a ``dict``.
      3–6.  ``name``  — missing, not a string, empty, or has surrounding whitespace.
      7–10. ``version`` — missing, not a string, empty, or has surrounding whitespace.
      11–14. ``groups`` — missing, not a list, empty, or contains a non-string /
             empty / whitespace-only / ``None`` value.
      15. ``groups`` has duplicate string values.
      16. a canonicalised package name appears more than once (cross-group or not).

    ``canonicalize_name`` is called only after structural validation; it never
    receives a non-string value.
    """
    if not isinstance(packages, list):
        raise ValueError("top-level lock packages must be a list")
    out: dict[str, str] = {}
    seen: set[str] = set()
    for idx, pkg in enumerate(packages):
        if not isinstance(pkg, dict):
            raise ValueError(f"lock package [{idx}]: must be a mapping, got {type(pkg).__name__}")

        # ---- name ----
        name = pkg.get("name")
        if name is None:
            raise ValueError(f"lock package [{idx}]: missing 'name'")
        if not isinstance(name, str):
            raise ValueError(f"lock package [{idx}]: 'name' must be str, got {type(name).__name__}")
        if not name.strip():
            raise ValueError(f"lock package [{idx}]: 'name' must not be empty")
        if name != name.strip():
            raise ValueError(f"lock package [{idx}]: 'name' has surrounding whitespace")

        # ---- version ----
        version = pkg.get("version")
        if version is None:
            raise ValueError(f"lock package [{idx}]: missing 'version'")
        if not isinstance(version, str):
            raise ValueError(f"lock package [{idx}]: 'version' must be str, got {type(version).__name__}")
        if not version.strip():
            raise ValueError(f"lock package [{idx}]: 'version' must not be empty")
        if version != version.strip():
            raise ValueError(f"lock package [{idx}]: 'version' has surrounding whitespace")

        # ---- groups ----
        groups = pkg.get("groups")
        if groups is None:
            raise ValueError(f"lock package [{idx}]: missing 'groups'")
        if not isinstance(groups, list):
            raise ValueError(f"lock package [{idx}]: 'groups' must be a list, got {type(groups).__name__}")
        if not groups:
            raise ValueError(f"lock package [{idx}]: 'groups' must not be empty")
        seen_group_vals: set[str] = set()
        for gi, g in enumerate(groups):
            if g is None:
                raise ValueError(f"lock package [{idx}]: groups[{gi}] is None")
            if not isinstance(g, str):
                raise ValueError(f"lock package [{idx}]: groups[{gi}] must be str, got {type(g).__name__}")
            if not g.strip():
                raise ValueError(f"lock package [{idx}]: groups[{gi}] must not be empty")
            if g != g.strip():
                raise ValueError(f"lock package [{idx}]: groups[{gi}] has surrounding whitespace")
            if g in seen_group_vals:
                raise ValueError(f"lock package [{idx}]: duplicate group value {g!r}")
            seen_group_vals.add(g)

        # ---- canonical duplicate detection ----
        canonical = canonicalize_name(name)
        if canonical in seen:
            raise ValueError(f"lock package [{idx}]: duplicate canonical name {canonical!r}")
        seen.add(canonical)

        if "main" in groups:
            out[canonical] = version
    return out


def parse_main_lock_file() -> dict[str, str]:
    data = tomllib.load(POETRY_LOCK.open("rb"))
    return parse_main_lock_packages(data.get("package", []))


def main_inventory_deltas(
    req_text: str, lock_packages: list[dict]
) -> tuple[list[str], list[str], list[str]]:
    """Return ``(missing, extra, mismatched)`` canonical names."""
    req = parse_requirements_text(req_text)
    main = parse_main_lock_packages(lock_packages)
    missing = sorted(set(main) - set(req))
    extra = sorted(set(req) - set(main))
    mismatch = sorted(n for n in (set(req) & set(main)) if req[n] != main[n])
    return missing, extra, mismatch


# --------------------------------------------------------------------------- #
# install-path source-shape guards  (KILO-H7R3V1-003 — structural, not substring)
# --------------------------------------------------------------------------- #
def check_setup_sh_wiring(text: str) -> None:
    """Verify setup.sh has an active ``pip install -r requirements.txt`` line.

    Scans non-blank, non-comment lines with a shell-block depth tracker
    (if/fi, for/do/done, while/do/done, until/do/done, case/esac, and
    functions).  The guard requires:

      * the pip command line is **exactly**
        ``pip install -r requirements.txt`` (no suffix, redirect, ``||`` chain,
        or ``&&`` chain);
      * no shell block is open at the pip line (multi-line or same-line);
      * the line is NOT commented, quoted, inert (echo/printf), a variable
        assignment, or behind a dead-branch short-circuit (``false &&`` /
        ``true ||``);
      * no unconditional ``exit`` / ``return`` (outside ``if … fi``) precedes
        the pip line;
      * the exact sequence ``cd … backend`` → ``pip install -r requirements.txt``
        → ``alembic upgrade head`` (public) → ``alembic -x tenant_schema=…
        upgrade head`` (tenant) → ``pnpm install --frozen-lockfile`` is present
        in order;
      * the old alembic form ``alembic upgrade head -x …`` is rejected;
      * ``npm install`` is rejected (pnpm is required).

    This is a source-shape guard, not native-execution proof.
    """
    P = "pip install -r requirements.txt"
    OLD_ALEMBIC = "alembic upgrade head -x"
    PNPM_CMD = "pnpm install --frozen-lockfile"
    lines = text.splitlines()
    CD_BACKEND = "cd backend"

    # ------- block-depth helper -----------------------------------------------
    def _block_delta(s: str) -> int:
        """Return +1 for opener, -1 for closer, 0 otherwise."""
        low = s.lower()
        if re.match(r"^if\b", low):
            # single-line if...fi → net 0
            if re.search(r"\bfi\b", low):
                return 0
            return 1
        if re.match(r"^(for|while|until|case)\b", low):
            # if the matching closer is on the same line (single-line block), net 0
            first_word = low.split()[0] if low.split() else ""
            closer = {"for": "done", "while": "done", "until": "done", "case": "esac"}.get(first_word, "")
            if closer and re.search(rf"\b{closer}\b", low):
                return 0
            return 1
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\(\s*\)", s):
            return 1
        if re.match(r"^function\s+", low):
            return 1
        if re.match(r"^(fi|done|esac)\b", low):
            return -1
        if re.match(r"^\}\s*$", s):
            return -1  # function closer
        return 0

    # ------- pre-compute $(...) and heredoc line ranges --------------------
    # Lines inside $() or heredocs contain Python code whose if/for keywords
    # must not be mistaken for shell block openers.
    in_cmdsubst = [False] * len(lines)
    _cs = 0
    _in_heredoc = False
    _heredoc_delim = ""
    for _i, _raw in enumerate(lines):
        _s = _raw.strip()
        if _in_heredoc:
            in_cmdsubst[_i] = True
            if _s == _heredoc_delim:
                _in_heredoc = False
            continue
        if _cs > 0:
            in_cmdsubst[_i] = True
        # detect heredoc start: <<'DELIM' or <<DELIM
        _hm = re.search(r"<<-?'([^']+)'", _s) or re.search(r'<<-"([^"]+)"', _s) or re.search(r"<<'([A-Za-z_][A-Za-z0-9_]*)'", _s)
        if _hm:
            _heredoc_delim = _hm.group(1)
            _in_heredoc = True
        _cs = max(0, _cs + _s.count("(") - _s.count(")"))

    # ------- step 1: locate the exact pip line --------------------------------
    pip_idx: int | None = None
    depth = 0
    for i, raw in enumerate(lines):
        s = raw.lstrip()
        if not s or s.startswith("#"):
            continue
        if in_cmdsubst[i]:
            continue

        # simple linear block-depth tracking (skip cmdsubst lines)
        delta = _block_delta(s)
        if delta == 1:
            depth += 1
        elif delta == -1:
            depth = max(0, depth - 1)

        # reject if blocks are open and this line contains pip
        if depth > 0 and P in s:
            raise ValueError("setup.sh: pip install inside a shell block is not allowed")

        if P not in s:
            continue

        # ---- reject inert/dead forms inline ----
        low = s.lower()
        if low.startswith(("echo ", "printf ")):
            raise ValueError("setup.sh: pip install line appears to be inert (echo/printf)")
        if re.match(r"(false|true)\s*(&&|\|\|)", s):
            raise ValueError("setup.sh: pip install line is behind a dead-branch short-circuit")
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", s):
            raise ValueError("setup.sh: pip install command is embedded in a variable assignment")
        if s.startswith(('"', "'")):
            raise ValueError("setup.sh: pip install appears inside quoted text")

        # ---- exact command ----
        cmd = s
        if cmd != P:
            raise ValueError(
                f"setup.sh: pip line must be exactly {P!r}, got {cmd!r}"
            )
        if pip_idx is not None:
            raise ValueError("setup.sh: more than one pip install line found")
        pip_idx = i

    # final block balance check
    if depth != 0:
        raise ValueError(f"setup.sh: unbalanced shell blocks (depth={depth})")

    if pip_idx is None:
        raise ValueError("setup.sh: no active 'pip install -r requirements.txt' command found")

    # ------- step 2: unreachable exit/return (outside if..fi and functions) ----
    if_depth = 0
    func_depth = 0
    for raw in lines[:pip_idx]:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\(\s*\)\s*\{?", s) or re.match(r"^function\s+", s, re.IGNORECASE):
            func_depth += 1
        elif re.match(r"^\}\s*$", s):
            func_depth = max(0, func_depth - 1)
        elif re.match(r"^if\b", s):
            if_depth += 1
        elif re.match(r"^fi\b", s):
            if_depth = max(0, if_depth - 1)
        elif re.match(r"^(exit|return)\b", s) and if_depth == 0 and func_depth == 0:
            raise ValueError(f"setup.sh: unreachable (exit/return before pip line at L{pip_idx + 1})")

    # ------- step 3: canonical sequence checks -----------------------------
    after_pip = lines[pip_idx + 1 :]
    non_comment = [r.strip() for r in lines if r.strip() and not r.strip().startswith("#")]

    # strict mode
    if not any("set -Eeuo pipefail" in r for r in lines[:12]):
        raise ValueError("setup.sh: missing 'set -Eeuo pipefail' strict mode")
    # ERR trap present
    if not any(re.search(r"trap\b.*\bERR\b", r) for r in non_comment):
        raise ValueError("setup.sh: missing ERR trap")
    # ERR trap must not claim rollback / no-changes-applied (scan non-comment lines only)
    nc_text = "\n".join(non_comment).lower()
    for bad in ["no changes have been applied", "no changes applied", "rolled back", "rollback complete"]:
        if bad in nc_text:
            raise ValueError(f"setup.sh: ERR trap must not claim '{bad}'")
    # Compose stored as a shell array
    if not any(re.search(r"COMPOSE\s*=\s*\(", r) for r in non_comment):
        raise ValueError("setup.sh: Compose invocation must be a shell array (COMPOSE=(...))")
    # bounded PostgreSQL health polling
    if not any("pg_isready" in r for r in non_comment) or not any(re.search(r"seq\b.*MAX_ATTEMPTS|for i in.*seq", r) for r in non_comment):
        raise ValueError("setup.sh: missing bounded PostgreSQL readiness polling (pg_isready + loop)")
    if not any("redis-cli ping" in r for r in non_comment):
        raise ValueError("setup.sh: missing bounded Redis readiness polling (redis-cli ping)")
    # cd backend before pip
    if not any(re.match(r"^cd\b", r) and "backend" in r for r in [l.strip() for l in lines[:pip_idx]]):
        raise ValueError("setup.sh: must cd into backend before pip install")
    # public alembic upgrade head (bare) after pip
    pub_lines = [i for i, r in enumerate(after_pip) if re.match(r"^alembic upgrade head\s*(#|$)", r.strip())]
    if not pub_lines:
        raise ValueError("setup.sh: must run public 'alembic upgrade head' after pip install")
    pub_off = pub_lines[0]
    # REJECT the tenant alembic no-op form
    if any(re.match(r"^alembic\s+.*-x\s+tenant_schema=", r) for r in non_comment):
        raise ValueError("setup.sh: tenant alembic '-x tenant_schema=' is a no-op; use canonical bootstrap_tenant_schema.py")
    # REJECT hard-coded postgres user (must use env var)
    if any(re.search(r"pg_isready\s+-U\s+(mpango_test|postgres|mpango)\b", r) for r in non_comment):
        raise ValueError("setup.sh: pg_isready must use '${POSTGRES_USER:...}' env var, not a hard-coded user")
    # canonical bootstrap after public migration
    boot_lines = [i for i, r in enumerate(after_pip) if "bootstrap_tenant_schema.py" in r]
    if not boot_lines:
        raise ValueError("setup.sh: must invoke canonical 'python scripts/bootstrap_tenant_schema.py' after public migration")
    if boot_lines[0] < pub_off:
        raise ValueError("setup.sh: canonical bootstrap must run AFTER public 'alembic upgrade head'")
    # bootstrap must receive DATABASE_URL via --database-url OR env export (not both absent)
    bootstrap_idx = boot_lines[0]
    bootstrap_line = after_pip[bootstrap_idx]
    has_url_arg = "--database-url" in bootstrap_line
    has_env_export = any(
        re.search(r"(^|\s)export\s+DATABASE_URL\s*=", after_pip[j].strip())
        for j in range(bootstrap_idx)
    )
    if not has_url_arg and not has_env_export:
        raise ValueError("setup.sh: canonical bootstrap needs DATABASE_URL via --database-url or env export")
    # DATABASE_URL resolution must go through the extracted preflight module
    if not any("setup_preflight.py" in r for r in non_comment):
        raise ValueError("setup.sh: must resolve DATABASE_URL via setup_preflight.py")
    # R5-R6: rendered Compose JSON must be piped into setup_preflight.py
    if not any("config --format json" in r and "setup_preflight.py" in r for r in non_comment):
        raise ValueError("setup.sh: must pipe 'compose config --format json' into setup_preflight.py")
    # R7: secrets must never be passed on argv (read from os.environ inside the helper)
    if any("--process-db" in r or "--process-redis" in r for r in non_comment):
        raise ValueError("setup.sh: must not pass DATABASE_URL/REDIS_URL on argv (use os.environ)")
    # R5-R6: post-install settings/.env verification before Alembic
    if not any("--post-install" in r for r in non_comment):
        raise ValueError("setup.sh: missing --post-install preflight verification")
    # R5-R6: CRLF fail-closed self-check (python raw-byte read)
    if not any(re.search(r"b'\\r'", r) for r in non_comment):
        raise ValueError("setup.sh: missing CRLF fail-closed self-check")
    # R11: Compose must be given backend/.env explicitly via the global --env-file
    # option (no sourcing / exporting of .env into the caller environment).
    if not any("--env-file" in r for r in non_comment):
        raise ValueError("setup.sh: must pass backend/.env to Compose via --env-file")
    # R11: setup.sh must NOT overwrite a caller-provided COMPOSE_PROJECT_NAME
    if any(re.search(r"^\s*COMPOSE_PROJECT_NAME\s*=", r) for r in lines):
        raise ValueError("setup.sh: must not set/overwrite COMPOSE_PROJECT_NAME")
    # R15-R1/R15-R2: _NATIVE_CREDS must be actively unset (anchored command,
    # not an echo/comment/no-op) before Alembic.
    unset_creds_idx = next(
        (i for i, r in enumerate(lines)
         if re.match(r"^\s*unset\b.*\b_NATIVE_CREDS\b", r)), None,
    )
    if unset_creds_idx is None:
        raise ValueError("setup.sh: _NATIVE_CREDS must be unset before Alembic")
    if any("alembic upgrade head" in r.strip() and i < unset_creds_idx
           for i, r in enumerate(lines)):
        raise ValueError("setup.sh: _NATIVE_CREDS must be unset before Alembic")
    # R12: no Compose config operation may run before the --env-file-bearing
    # array is constructed (a premature config probe without --env-file would
    # fail interpolation and silently reject a standalone docker-compose).
    compose_array_idx = next(
        (i for i, r in enumerate(lines) if re.search(r"^\s*COMPOSE\s*=\(", r)), None
    )
    if compose_array_idx is None:
        raise ValueError("setup.sh: missing COMPOSE array")
    for r in lines[:compose_array_idx]:
        s = r.strip()
        if not s or s.startswith("#"):
            continue
        if re.search(r"\bconfig\b", s) and "version" not in s:
            raise ValueError(
                "setup.sh: Compose config operation runs before the --env-file-bearing array"
            )
    # REJECT npm (pnpm required; word-boundary so 'pnpm' is not flagged)
    for r in after_pip:
        if re.search(r"\bnpm\s+(install|i)\b", r) and "pnpm" not in r.lower():
            raise ValueError("setup.sh: npm install is not allowed — use pnpm install --frozen-lockfile")
    # pnpm frozen-lockfile (literal, $VAR, or "$VAR" forms)
    if not any("install --frozen-lockfile" in r and "pnpm" in r.lower() for r in after_pip):
        raise ValueError("setup.sh: must run 'pnpm install --frozen-lockfile' after migrations")


def check_dockerfile_wiring(text: str) -> None:
    """Verify the Dockerfile actively installs via Poetry/lock.

    Line continuations (``\\`` at end-of-line) are joined before parsing.
    The guard requires, in the **final** build stage (after the last ``FROM``):

      * exactly one ``COPY pyproject.toml poetry.lock ./`` line;
      * exactly one ``RUN poetry install --no-root --only main --no-ansi`` line;
      * the ``COPY`` appears textually **before** the ``RUN poetry install``;
      * no line is a commented, inert, or dead-branch form that contains the
        same substrings but would not actually execute the intended command
        (echo-wrapper, ``false &&``, ``|| true`` suffix, ``ENV``/``LABEL``/
        ``ARG`` assignment, comment-only, earlier-stage-only, duplicates).
    """
    COPY_LINE = "COPY pyproject.toml poetry.lock ./"
    RUN_LINE = "RUN poetry install --no-root --only main --no-ansi"

    # ------ join continuations -------------------------------------------
    joined: list[str] = []
    buf = ""
    for raw in text.splitlines():
        s = raw.rstrip()
        if s.endswith("\\"):
            buf += s[:-1] + " "
        else:
            buf += s
            joined.append(buf)
            buf = ""
    if buf:
        joined.append(buf)

    # ------ find the last FROM (final stage) -----------------------------
    last_from = -1
    for i, s in enumerate(joined):
        if re.match(r"^FROM\b", s, re.IGNORECASE):
            last_from = i

    stage_lines = joined[last_from:] if last_from >= 0 else joined

    # ------ scan for COPY and RUN poetry install -------------------------
    copy_idx = -1
    run_idx = -1
    for i, raw in enumerate(stage_lines):
        s = raw.lstrip()
        if not s or re.match(r"^\s*#", s) or s.startswith("#"):
            continue

        # ---- exact COPY pyproject.toml poetry.lock ./ -------------------
        if COPY_LINE in s:
            if not s.upper().startswith("COPY"):
                raise ValueError("Dockerfile: COPY line must be an active COPY instruction")
            if s != COPY_LINE:
                raise ValueError(f"Dockerfile: COPY must be exactly {COPY_LINE!r}, got {s!r}")
            if copy_idx >= 0:
                raise ValueError("Dockerfile: duplicate COPY+pyproject+lock instructions")
            copy_idx = i

        # ---- detect poetry install on non-COPY lines --------------------
        if "poetry install" in s:
            if s.upper().startswith("RUN"):
                after_run = s[3:].lstrip()
                # inert forms
                if after_run.lower().startswith(("echo ", "printf ")):
                    raise ValueError("Dockerfile: RUN poetry install line is inert (echo/printf)")
                if re.search(r"(false|true)\s*(&&|\|\|)", after_run):
                    raise ValueError("Dockerfile: RUN poetry install line behind dead-branch short-circuit")
                if re.search(r"\|\|\s*true\b", after_run):
                    raise ValueError("Dockerfile: RUN poetry install line has a || true guard")
                # must be exactly the expected command
                if s != RUN_LINE:
                    raise ValueError(f"Dockerfile: RUN must be exactly {RUN_LINE!r}, got {s!r}")
                if run_idx >= 0:
                    raise ValueError("Dockerfile: duplicate RUN poetry install lines")
                run_idx = i
            elif s.upper().startswith(("ENV", "LABEL", "ARG")):
                raise ValueError("Dockerfile: RUN poetry install text inside ENV/LABEL/ARG")

        # ---- detect a later FROM (stage boundary) --------------------------
        if re.match(r"^FROM\b", s, re.IGNORECASE) and i > 0:
            if last_from < 0:
                last_from = i

    if copy_idx < 0:
        raise ValueError("Dockerfile: active COPY pyproject.toml poetry.lock ./ not found")
    if run_idx < 0:
        raise ValueError("Dockerfile: active RUN poetry install --no-root --only main --no-ansi not found")
    if run_idx <= copy_idx:
        raise ValueError("Dockerfile: RUN poetry install must appear AFTER COPY pyproject.toml poetry.lock")


# --------------------------------------------------------------------------- #
# pyproject spec helpers (unchanged)
# --------------------------------------------------------------------------- #
def _pyproject_runtime_specs() -> dict[str, str]:
    data = tomllib.load(PYPROJECT.open("rb"))
    deps = data["tool"]["poetry"]["dependencies"]
    out: dict[str, str] = {}
    for name, spec in deps.items():
        if name == "python":
            continue
        ver = spec.get("version") if isinstance(spec, dict) else spec
        out[canonicalize_name(name)] = ver
    return out


def _spec_satisfies(spec: str, version: str) -> bool:
    normalized = spec.strip()
    if not re.match(r"^(==|!=|~=|>=|<=|>|<|===)", normalized):
        normalized = f"=={normalized}"
    return Version(version) in SpecifierSet(normalized)


# ──────────────────────────────────────────────────────────────────────────── #
# GREEN — governed versions + inventory equality
# ──────────────────────────────────────────────────────────────────────────── #
class TestH7R4InventoryParity:
    @pytest.mark.parametrize("pkg,expected", sorted(EXPECTED.items()))
    def test_requirements_txt_resolves_expected(self, pkg: str, expected: str) -> None:
        req = parse_requirements_file()
        assert req[pkg] == expected

    @pytest.mark.parametrize("pkg,expected", sorted(EXPECTED.items()))
    def test_poetry_main_lock_resolves_expected(self, pkg: str, expected: str) -> None:
        main = parse_main_lock_file()
        assert main[pkg] == expected

    def test_bcrypt_within_pyproject_floor_and_ceiling(self) -> None:
        spec = _pyproject_runtime_specs()["bcrypt"]
        assert _spec_satisfies(spec, "4.0.1") and not _spec_satisfies(spec, "4.1.0")

    def test_cryptography_meets_security_floor(self) -> None:
        spec = _pyproject_runtime_specs()["cryptography"]
        assert _spec_satisfies(spec, "46.0.5") and not _spec_satisfies(spec, "46.0.4")

    @pytest.mark.parametrize("pkg", ["bcrypt", "cryptography", "openpyxl", "passlib"])
    def test_resolved_versions_satisfy_pyproject(self, pkg: str) -> None:
        spec = _pyproject_runtime_specs()[pkg]
        assert spec is not None and _spec_satisfies(spec, parse_requirements_file()[pkg])

    def test_passlib_unchanged_at_1_7_4(self) -> None:
        assert _pyproject_runtime_specs()["passlib"] == "1.7.4"
        assert parse_requirements_file()["passlib"] == "1.7.4"
        assert parse_main_lock_file()["passlib"] == "1.7.4"

    def test_requirements_inventory_equals_lock_inventory(self) -> None:
        """requirements.txt name/version inventory == Poetry main-group lock inventory."""
        req = parse_requirements_file()
        main = parse_main_lock_file()
        assert set(req) == set(main), (
            f"name drift: missing={sorted(set(main)-set(req))} "
            f"extra={sorted(set(req)-set(main))}"
        )
        assert req == main, f"version drift: { {k: (req[k], main[k]) for k in req if req[k]!=main[k]} }"

    def test_marker_only_variants_same_inventory(self) -> None:
        """A marker change does not alter the name/version inventory."""
        text = REQUIREMENTS.read_text(encoding="utf-8")
        ref = parse_requirements_text(text)
        marker_mutated = text.replace(
            'et-xmlfile==2.0.0 ; python_version >= "3.11" and python_version < "4.0"',
            'et-xmlfile==2.0.0 ; python_version >= "3.12"',
        )
        assert parse_requirements_text(marker_mutated) == ref


# ──────────────────────────────────────────────────────────────────────────── #
# Install-path source-shape guards  (R5-R1 — canonical bootstrap)
# ──────────────────────────────────────────────────────────────────────────── #
class TestH7R5R1InstallPathWiring:
    """Each RED test reads the REAL committed setup.sh, mutates one element,
    and asserts the specific rejection.  This proves the guard catches real
    regressions, not just synthetic snippets."""

    @staticmethod
    def _base() -> str:
        return SETUP_SH.read_text(encoding="utf-8")

    # ---- GREEN ----
    def test_GREEN_real_setup_sh_passes(self) -> None:
        check_setup_sh_wiring(self._base())

    def test_GREEN_real_dockerfile_passes(self) -> None:
        check_dockerfile_wiring(DOCKERFILE.read_text(encoding="utf-8"))

    # ---- setup.sh RED: strict mode, ERR trap, compose, readiness ----------
    def test_RED_missing_strict_mode(self) -> None:
        text = self._base().replace("set -Eeuo pipefail", "set -e")
        with pytest.raises(ValueError, match="strict mode"):
            check_setup_sh_wiring(text)

    def test_RED_missing_err_trap(self) -> None:
        text = self._base().replace('''trap '_on_err "$LINENO" "$?"' ERR''', "true")
        with pytest.raises(ValueError, match="ERR trap"):
            check_setup_sh_wiring(text)

    def test_RED_false_no_changes_applied_wording(self) -> None:
        text = self._base().replace(
            "Partial local artifacts may exist",
            "No changes have been applied to your system",
        )
        with pytest.raises(ValueError, match="must not claim"):
            check_setup_sh_wiring(text)

    def test_RED_missing_compose_array(self) -> None:
        import re as _re
        text = _re.sub(r"COMPOSE\s*=\s*\(", "COMPOSE=", self._base())
        with pytest.raises(ValueError, match="shell array"):
            check_setup_sh_wiring(text)

    def test_RED_missing_pg_health_polling(self) -> None:
        text = self._base().replace("pg_isready", "true_check")
        with pytest.raises(ValueError, match="PostgreSQL readiness"):
            check_setup_sh_wiring(text)

    def test_RED_missing_redis_health_polling(self) -> None:
        text = self._base().replace("redis-cli ping", "true_check")
        with pytest.raises(ValueError, match="Redis readiness"):
            check_setup_sh_wiring(text)

    def test_RED_hardcoded_postgres_user(self) -> None:
        text = self._base().replace(
            'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
            "pg_isready -U mpango_test -d mpango_test",
        )
        with pytest.raises(ValueError, match="hard-coded"):
            check_setup_sh_wiring(text)

    # ---- setup.sh RED: alembic / bootstrap sequence ----------------------
    def test_RED_tenant_alembic_noop_rejected(self) -> None:
        text = self._base().replace(
            'python scripts/bootstrap_tenant_schema.py "${DEFAULT_TENANT_SCHEMA:-t_dev}"',
            'alembic -x tenant_schema="${DEFAULT_TENANT_SCHEMA:-t_dev}" upgrade head',
        )
        with pytest.raises(ValueError, match="tenant_schema"):
            check_setup_sh_wiring(text)

    def test_RED_missing_canonical_bootstrap(self) -> None:
        text = self._base().replace("python scripts/bootstrap_tenant_schema.py", "true")
        with pytest.raises(ValueError, match="canonical"):
            check_setup_sh_wiring(text)

    def test_RED_bootstrap_before_public_migration(self) -> None:
        text = self._base().replace(
            'alembic upgrade head',
            '# alembic removed',
        )
        with pytest.raises(ValueError, match="public"):
            check_setup_sh_wiring(text)

    def test_RED_missing_bootstrap_database_url(self) -> None:
        text = self._base().replace('export DATABASE_URL="$_NATIVE_DB_URL"\n', "")
        with pytest.raises(ValueError, match="(?i)database"):
            check_setup_sh_wiring(text)

    def test_RED_native_creds_not_cleared_before_alembic(self) -> None:
        """RED (R15-R1): removing the _NATIVE_CREDS unset means the combined
        buffer holding both secrets survives past Alembic — the guard catches it."""
        text = self._base().replace(
            "unset _NATIVE_CREDS  # R15-R1: clear the combined buffer immediately after split\n",
            "",
        )
        with pytest.raises(ValueError, match="_NATIVE_CREDS must be unset before Alembic"):
            check_setup_sh_wiring(text)

    @pytest.mark.parametrize(
        "inert",
        [
            'echo unset _NATIVE_CREDS',
            '# unset _NATIVE_CREDS',
            ': unset _NATIVE_CREDS',
            'true unset _NATIVE_CREDS',
        ],
    )
    def test_RED_native_creds_inert_unset_rejected(self, inert: str) -> None:
        """RED (R15-R2): echo / comment / colon / true no-op forms that merely
        contain the tokens must NOT satisfy the guard — only an active anchored
        `unset _NATIVE_CREDS` command is accepted."""
        text = self._base().replace(
            "unset _NATIVE_CREDS  # R15-R1: clear the combined buffer immediately after split\n",
            inert + "\n",
        )
        with pytest.raises(ValueError, match="_NATIVE_CREDS must be unset"):
            check_setup_sh_wiring(text)

    def test_RED_native_creds_unset_after_alembic_rejected(self) -> None:
        """RED (R15-R2): moving the unset AFTER `alembic upgrade head` leaves
        the combined buffer alive during Alembic — the guard catches the ordering."""
        text = self._base().replace(
            "unset _NATIVE_CREDS  # R15-R1: clear the combined buffer immediately after split\n",
            "",
        ).replace("alembic upgrade head", "alembic upgrade head\nunset _NATIVE_CREDS")
        with pytest.raises(ValueError, match="_NATIVE_CREDS must be unset"):
            check_setup_sh_wiring(text)

    def test_RED_missing_database_url_resolution(self) -> None:
        text = self._base().replace("setup_preflight.py", "preflight_placeholder.py")
        with pytest.raises(ValueError, match="DATABASE_URL"):
            check_setup_sh_wiring(text)

    # ---- setup.sh RED: pip / npm / pnpm ----------------------------------
    def test_RED_npm_rejected(self) -> None:
        text = self._base().replace('"$PNPM_BIN" install --frozen-lockfile', "npm install")
        with pytest.raises(ValueError, match="npm"):
            check_setup_sh_wiring(text)

    def test_RED_non_frozen_pnpm_rejected(self) -> None:
        text = self._base().replace('"$PNPM_BIN" install --frozen-lockfile', '"$PNPM_BIN" install')
        with pytest.raises(ValueError, match="frozen-lockfile"):
            check_setup_sh_wiring(text)

    # ---- setup.sh RED: pip-line context (preserved from R4-R1) -----------
    def test_RED_pip_inside_echo(self) -> None:
        with pytest.raises(ValueError, match="inert"):
            check_setup_sh_wiring('echo "pip install -r requirements.txt"')

    def test_RED_pip_false_and(self) -> None:
        with pytest.raises(ValueError, match="short-circuit"):
            check_setup_sh_wiring("false && pip install -r requirements.txt")

    def test_RED_pip_quoted(self) -> None:
        with pytest.raises(ValueError, match="quoted"):
            check_setup_sh_wiring('"pip install -r requirements.txt"')

    def test_RED_pip_var_assign(self) -> None:
        with pytest.raises(ValueError, match="variable assignment"):
            check_setup_sh_wiring("CMD=pip install -r requirements.txt")

    def test_RED_pip_inside_if_block(self) -> None:
        text = self._base().replace(
            "pip install -r requirements.txt",
            "if false; then\npip install -r requirements.txt\nfi",
        )
        with pytest.raises(ValueError, match="block"):
            check_setup_sh_wiring(text)

    # ---- Dockerfile RED mutations (unchanged from R4-R1) -----------------
    def test_RED_dockerfile_wrong_ordering_rejected(self) -> None:
        with pytest.raises(ValueError, match="must appear AFTER"):
            check_dockerfile_wiring("FROM python:3.11\nRUN poetry install --no-root --only main --no-ansi\nCOPY pyproject.toml poetry.lock ./")

    def test_RED_dockerfile_copy_absent_rejected(self) -> None:
        with pytest.raises(ValueError, match="COPY"):
            check_dockerfile_wiring("FROM python:3.11\nRUN poetry install --no-root --only main --no-ansi")

    def test_RED_dockerfile_run_absent_rejected(self) -> None:
        with pytest.raises(ValueError, match="poetry install"):
            check_dockerfile_wiring("FROM python:3.11\nCOPY pyproject.toml poetry.lock ./")

    def test_RED_dockerfile_echo_form_rejected(self) -> None:
        with pytest.raises(ValueError, match="inert"):
            check_dockerfile_wiring("FROM python:3.11\nRUN echo 'poetry install --no-root --only main --no-ansi'\nCOPY pyproject.toml poetry.lock ./")

    def test_RED_dockerfile_false_and_rejected(self) -> None:
        with pytest.raises(ValueError, match="short-circuit"):
            check_dockerfile_wiring("FROM python:3.11\nCOPY pyproject.toml poetry.lock ./\nRUN false && poetry install --no-root --only main --no-ansi")

    def test_RED_dockerfile_or_true_rejected(self) -> None:
        with pytest.raises(ValueError, match="true guard"):
            check_dockerfile_wiring("FROM python:3.11\nCOPY pyproject.toml poetry.lock ./\nRUN poetry install --no-root --only main --no-ansi || true")

    def test_RED_dockerfile_env_label_rejected(self) -> None:
        with pytest.raises(ValueError, match="ENV.*LABEL"):
            check_dockerfile_wiring("FROM python:3.11\nCOPY pyproject.toml poetry.lock ./\nENV X=poetry install --no-root --only main --no-ansi")

    def test_RED_dockerfile_commented_run_rejected(self) -> None:
        with pytest.raises(ValueError, match="poetry install"):
            check_dockerfile_wiring("FROM python:3.11\nCOPY pyproject.toml poetry.lock ./\n# RUN poetry install --no-root --only main --no-ansi")

    def test_RED_dockerfile_duplicate_copy_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            check_dockerfile_wiring("FROM python:3.11\nCOPY pyproject.toml poetry.lock ./\nCOPY pyproject.toml poetry.lock ./\nRUN poetry install --no-root --only main --no-ansi")

    def test_RED_dockerfile_duplicate_run_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            check_dockerfile_wiring("FROM python:3.11\nCOPY pyproject.toml poetry.lock ./\nRUN poetry install --no-root --only main --no-ansi\nRUN poetry install --no-root --only main --no-ansi")


# ──────────────────────────────────────────────────────────────────────────── #
# Executable fake-PATH harness  (R5-R2 — proves actual exit-status behaviour)
# ──────────────────────────────────────────────────────────────────────────── #
def _select_bash(isfile=None, which=None):
    """Explicitly select Git Bash on Windows, native bash on POSIX.

    Reject System32/WSL/WindowsApps bash.  Fail closed if unavailable.
    ``isfile``/``which`` are injectable for fail-closed launcher tests."""
    import os
    import shutil
    import sys

    if isfile is None:
        isfile = os.path.isfile
    if which is None:
        which = shutil.which

    if sys.platform == "win32":
        # Try known Git Bash installation paths first
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        la = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(pf, "Git", "usr", "bin", "bash.exe"),
            os.path.join(pf86, "Git", "usr", "bin", "bash.exe"),
            os.path.join(la, "Programs", "Git", "usr", "bin", "bash.exe"),
        ]
        for c in candidates:
            if isfile(c) and "system32" not in c.lower():
                return c
        # Fallback: PATH lookup but reject System32/WSL/WindowsApps
        bash = which("bash")
        if (
            bash
            and "system32" not in bash.lower()
            and "wsl" not in bash.lower()
            and "windowsapps" not in bash.lower()
        ):
            return bash
        raise RuntimeError("Git Bash not found; System32/WSL bash rejected")
    else:
        bash = which("bash")
        if bash and "system32" not in bash.lower():
            return bash
        raise RuntimeError("No suitable bash found on PATH")


class TestH7R5R2ExecutableHarness:
    """Execute an UNMODIFIED copy of the committed setup.sh through subprocess
    against task-owned fake executables in a temporary fake-bin directory
    prepended to PATH (MSYS-style path so Git Bash performs the lookup).

    This proves actual exit-status preservation, command ordering, side-effect
    behaviour, and idempotency — not just source-text shape."""

    _FAKE_NAMES = ("docker", "pip", "alembic", "python", "pnpm")
    # External commands setup.sh actually invokes (dirname/grep/mkdir/seq/sleep)
    # plus chmod used by harness preparation. No obsolete tr/cat/mktemp.
    _REQUIRED_COREUTILS = ("dirname", "grep", "mkdir", "seq", "sleep", "chmod")
    # genuinely unique password sentinel placed in the harness .env AND the
    # fake Compose output; proven absent from argv/log/stdout/stderr.
    _SENTINEL_PW = "H7R8HarnessSentinel123"  # pragma: allowlist secret
    # R15: second unique sentinel for REPORTING_USER_PASSWORD.
    _SENTINEL_RUP = "H7R15ReportingSentinel456"  # pragma: allowlist secret

    @staticmethod
    def _msys_path(windows_path: str) -> str:
        p = windows_path.replace("\\", "/")
        if len(p) >= 2 and p[1] == ":":
            return "/" + p[0].lower() + "/" + p[3:]
        return p

    @classmethod
    def _git_bin_dirs(cls, bash_bin: str) -> list[str]:
        """Explicitly provide the selected Git Bash /usr/bin and /mingw64/bin
        (MSYS-style) so cross-host runs resolve coreutils even when the
        inherited PATH lacks them. POSIX hosts rely on the native PATH."""
        import sys
        from pathlib import Path as _Path
        if sys.platform != "win32":
            return []
        usr_bin = _Path(bash_bin).resolve().parent  # <GIT>/usr/bin
        git_root = usr_bin.parent.parent  # <GIT>
        dirs = [cls._msys_path(str(usr_bin))]
        mingw_bin = git_root / "mingw64" / "bin"
        if mingw_bin.is_dir():
            dirs.append(cls._msys_path(str(mingw_bin)))
        return dirs

    @classmethod
    def _verify_coreutils(cls, bash_bin: str, path_dirs: list[str]) -> None:
        """Fail closed if the probe itself fails OR any required coreutil is
        unresolvable on the run PATH."""
        import os
        import subprocess
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join(path_dirs) + os.pathsep + env.get("PATH", "")
        script = (
            "for c in " + " ".join(cls._REQUIRED_COREUTILS)
            + "; do command -v \"$c\" >/dev/null 2>&1 || echo \"missing:$c\"; done"
        )
        res = None
        try:
            res = subprocess.run(
                [bash_bin, "-c", script], capture_output=True, text=True, env=env,
            )
        except OSError:
            raise RuntimeError("coreutils probe failed")
        if res.returncode != 0:
            raise RuntimeError("coreutils probe failed")
        missing = [
            ln[len("missing:"):] for ln in res.stdout.splitlines()
            if ln.startswith("missing:")
        ]
        if missing:
            raise RuntimeError("required coreutils not found: " + ", ".join(missing))

    @classmethod
    def _build_harness(cls, tmp_path: Path, standalone: bool = False, **fake_exits: str) -> dict:
        import os
        import shutil
        import subprocess

        repo = tmp_path / "h7r2_repo"
        bin_dir = tmp_path / "h7r2_bin"
        log_file = tmp_path / "h7r2_cmd.log"
        repo.mkdir(parents=True)
        bin_dir.mkdir(parents=True)
        log_str = str(log_file).replace("\\", "/")

        # minimal disposable repo structure
        (repo / "backend" / "scripts").mkdir(parents=True)
        (repo / "backend" / ".env").write_text(
            f"DATABASE_URL=postgresql://pguser:{cls._SENTINEL_PW}@localhost:5432/pgdb\n"  # pragma: allowlist secret
            "SECRET_KEY=notweaknotsecretkeyabcdef1234567890\n"  # pragma: allowlist secret
            "POSTGRES_USER=pguser\nPOSTGRES_DB=pgdb\n"
            "REDIS_URL=redis://localhost:6379/0\n"
            f"REPORTING_USER_PASSWORD={cls._SENTINEL_RUP}\n"  # pragma: allowlist secret
        )
        (repo / "frontend").mkdir(parents=True)
        (repo / "docker-compose.yml").write_text(
            "services:\n  postgres:\n    image: postgres\n  redis:\n    image: redis\n"
        )
        # UNMODIFIED copies of committed setup files
        shutil.copy(SETUP_SH, repo / "backend" / "scripts" / "setup.sh")
        preflight_src = BACKEND_DIR / "scripts" / "setup_preflight.py"
        shutil.copy(preflight_src, repo / "backend" / "scripts" / "setup_preflight.py")
        # Minimal disposable core.config so the delegated --post-install check
        # performs a real in-memory comparison (reads backend/.env); env
        # H7R2_POSTINSTALL_MISMATCH=1 forces a RED mismatch.
        mismatch_url = "postgresql://someone:else@localhost:9999/other"  # pragma: allowlist secret
        (repo / "backend" / "core").mkdir(parents=True)
        (repo / "backend" / "core" / "__init__.py").write_text("")
        (repo / "backend" / "core" / "config.py").write_text(
            "import os\n"
            "class _Settings:\n"
            "    pass\n"
            "settings = _Settings()\n"
            "_seen = {}\n"
            "for _line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'), encoding='utf-8'):\n"
            "    _s = _line.strip()\n"
            "    if _s and not _s.startswith('#') and '=' in _s:\n"
            "        _k, _v = _s.split('=', 1)\n"
            "        _seen[_k.strip()] = _v.strip()\n"
            "settings.DATABASE_URL = _seen.get('DATABASE_URL', '')\n"
            "settings.REDIS_URL = _seen.get('REDIS_URL', '')\n"
            "if os.environ.get('H7R2_POSTINSTALL_MISMATCH') == '1':\n"
            f"    settings.DATABASE_URL = {mismatch_url!r}\n"
        )

        def _ev(name: str, default: str = "0") -> str:
            v = fake_exits.get(name, default)
            return v if v else default

        # Fake Compose JSON with Compose v2 object-shape port entries; the
        # POSTGRES_PASSWORD carries the same unique sentinel as the .env.
        # R15: backend also carries the REPORTING_USER_PASSWORD sentinel.
        _pw = cls._SENTINEL_PW
        _pw_rup = cls._SENTINEL_RUP
        import json as _json
        _compose_json = _json.dumps({
            "services": {
                "postgres": {
                    "environment": {"POSTGRES_USER": "pguser", "POSTGRES_DB": "pgdb", "POSTGRES_PASSWORD": _pw},  # pragma: allowlist secret
                    "ports": [{"host_ip": "127.0.0.1", "target": 5432, "published": 5432, "protocol": "tcp", "mode": "ingress"}],
                },
                "redis": {
                    "ports": [{"host_ip": "127.0.0.1", "target": 6379, "published": 6379, "protocol": "tcp", "mode": "ingress"}],
                },
                "backend": {
                    "environment": {"REPORTING_USER_PASSWORD": _pw_rup},  # pragma: allowlist secret
                },
            }
        }, separators=(",", ":"))

        fake_bodies = {
            "docker": f'''#!/bin/bash
echo "docker $*" >> "{log_str}"
shift  # drop "compose"
[ "$1" = "--env-file" ] && shift 2  # R11: Compose global --env-file <path>
sub="$*"
case "$sub" in
    "version"*) echo "Docker Compose version v2.20.0"; exit 0;;
    "config --format json"*)
        echo '{_compose_json}'
        exit 0;;
    "config"*) exit {_ev("compose_config")};;
    "up -d"*) exit 0;;
    "exec -T postgres"*)
        if echo "$sub" | grep -q "pg_isready"; then
            exit {_ev("pg")}
        fi
        printf "pguser|pgdb"
        exit 0;;
    "exec -T redis"*) echo "PONG"; exit {_ev("redis")};;
    *) exit 0;;
esac
''',
            "pip": f'''#!/bin/bash
echo "pip $*" >> "{log_str}"
exit 0
''',
            "alembic": f'''#!/bin/bash
echo "alembic $*" >> "{log_str}"
# R14/R15: alembic must receive BOTH DATABASE_URL and REPORTING_USER_PASSWORD
# from backend/.env (no alembic.ini fallback). Fail closed on mismatch.
_exp_db="$(grep -E '^DATABASE_URL=' .env 2>/dev/null | head -1 | cut -d= -f2-)"
_exp_rup="$(grep -E '^REPORTING_USER_PASSWORD=' .env 2>/dev/null | head -1 | cut -d= -f2-)"
if [ -z "${{DATABASE_URL:-}}" ] || [ "$DATABASE_URL" != "$_exp_db" ]; then
    exit 2
fi
if [ -z "${{REPORTING_USER_PASSWORD:-}}" ] || [ "$REPORTING_USER_PASSWORD" != "$_exp_rup" ]; then
    exit 4
fi
exit {_ev("alembic")}
''',
            "python": f'''#!/bin/bash
echo "python $*" >> "{log_str}"
if echo "$*" | grep -q "bootstrap_tenant_schema"; then
    # R14/R15: bootstrap uses the SAME DATABASE_URL; REPORTING_USER_PASSWORD
    # must NOT survive into bootstrap (setup.sh unsets it before bootstrap).
    _exp_db="$(grep -E '^DATABASE_URL=' .env 2>/dev/null | head -1 | cut -d= -f2-)"
    if [ -z "${{DATABASE_URL:-}}" ] || [ "$DATABASE_URL" != "$_exp_db" ]; then
        exit 3
    fi
    if [ -n "${{REPORTING_USER_PASSWORD:-}}" ]; then
        exit 5
    fi
    exit {_ev("bootstrap")}
fi
if [ -n "$REAL_PYTHON" ]; then
    exec "$REAL_PYTHON" "$@"
fi
echo "REAL_PYTHON not set" >&2
exit 1
''',
            "pnpm": f'''#!/bin/bash
echo "pnpm $*" >> "{log_str}"
exit {_ev("pnpm")}
''',
        }
        if standalone:
            # R12 standalone harness: the `docker compose` plugin is hidden
            # (any docker call fails) and only a standalone Compose v2 exists.
            # Its `config` (and every operation) succeeds ONLY when
            # `--env-file <path>` is carried BEFORE the subcommand.
            fake_bodies["docker"] = f'''#!/bin/bash
echo "docker $*" >> "{log_str}"
exit 1
'''
            fake_bodies["docker-compose"] = f'''#!/bin/bash
echo "docker-compose $*" >> "{log_str}"
a="$*"
case "$a" in
    "version"*) echo "Docker Compose version v2.20.0"; exit 0;;
    "--env-file "*)
        rest="${{a#* }}"; rest="${{rest#* }}"
        case "$rest" in
            "config --format json"*) echo '{_compose_json}'; exit 0;;
            "config"*) exit {_ev("compose_config")};;
            "up -d"*) exit 0;;
            "exec -T postgres"*)
                if echo "$rest" | grep -q "pg_isready"; then
                    exit {_ev("pg")}
                fi
                printf "pguser|pgdb"
                exit 0;;
            "exec -T redis"*) echo "PONG"; exit {_ev("redis")};;
            *) exit 0;;
        esac;;
    *) exit 1;;
esac
'''
        for name, body in fake_bodies.items():
            (bin_dir / name).write_text(body)
        # set MSYS2 executable bits via bash chmod (MSYS-converted paths, checked).
        # R13: the standalone harness also chmods its docker-compose fake; the
        # normal harness must never attempt to chmod a file it does not create.
        chmod_names = list(cls._FAKE_NAMES)
        if standalone:
            chmod_names.append("docker-compose")
        missing = [n for n in chmod_names if not (bin_dir / n).exists()]
        if missing:
            raise RuntimeError("harness fakes missing before chmod: " + ", ".join(missing))
        bash_bin = _select_bash()
        git_dirs = cls._git_bin_dirs(bash_bin)
        path_dirs = [cls._msys_path(str(bin_dir))] + git_dirs
        cls._verify_coreutils(bash_bin, path_dirs)
        quoted = " ".join(f'"{cls._msys_path(str(bin_dir / n))}"' for n in chmod_names)
        chmod_env = os.environ.copy()
        chmod_env["PATH"] = os.pathsep.join(path_dirs) + os.pathsep + chmod_env.get("PATH", "")
        subprocess.run([bash_bin, "-c", f"chmod +x {quoted}"], check=True, env=chmod_env)
        real_python = shutil.which("python") or shutil.which("python3") or ""
        return {"repo": repo, "bin": bin_dir, "log": log_file, "real_python": real_python}

    @classmethod
    def _run(cls, harness: dict, **env_overrides: str):
        import os
        import shutil
        import subprocess

        env = os.environ.copy()
        # Clear host DB/Redis/Reporting URLs so preflight sees no process-env conflict
        env.pop("DATABASE_URL", None)
        env.pop("REDIS_URL", None)
        env.pop("REPORTING_USER_PASSWORD", None)
        bash_bin = _select_bash()
        # cross-host: explicitly provide Git Bash /usr/bin + /mingw64/bin and
        # verify required coreutils before running; fail closed if unavailable.
        git_dirs = cls._git_bin_dirs(bash_bin)
        path_dirs = [cls._msys_path(str(harness["bin"]))] + git_dirs
        cls._verify_coreutils(bash_bin, path_dirs)
        env["PATH"] = os.pathsep.join(path_dirs) + os.pathsep + env.get("PATH", "")
        env["HOME"] = os.environ.get("HOME", "/tmp")
        env["REAL_PYTHON"] = harness.get("real_python", "")
        env["SETUP_TIMEOUT_ATTEMPTS"] = env_overrides.pop("SETUP_TIMEOUT_ATTEMPTS", "3")
        env["SETUP_TIMEOUT_INTERVAL"] = env_overrides.pop("SETUP_TIMEOUT_INTERVAL", "0")
        env.update(env_overrides)
        script = str(harness["repo"] / "backend" / "scripts" / "setup.sh").replace("\\", "/")
        result = subprocess.run(
            [bash_bin, script], capture_output=True, text=False, env=env, timeout=60
        )
        result.stdout = result.stdout.decode("utf-8", errors="replace")
        result.stderr = result.stderr.decode("utf-8", errors="replace")
        return result

    # ---- required executable tests ----

    def test_complete_success_and_strict_ordered_indexes(self, tmp_path: Path) -> None:
        h = self._build_harness(tmp_path)
        r = self._run(h)
        assert r.returncode == 0, r.stderr
        assert "Setup complete" in r.stdout
        log_lines = h["log"].read_text().splitlines()
        marks = [
            "config --format json",      # preflight Compose render
            "up -d",                     # compose up (subcommand; --env-file precedes it)
            "exec -T postgres",          # pg readiness
            "exec -T redis",             # redis readiness
            "pip install -r requirements.txt",
            "alembic upgrade head",
            "bootstrap_tenant_schema.py",
            "pnpm install --frozen-lockfile",
        ]
        indexes = []
        for mark in marks:
            idx = next((i for i, l in enumerate(log_lines) if mark in l), None)
            assert idx is not None, f"missing command containing {mark!r}; log={log_lines}"
            indexes.append(idx)
        assert indexes == sorted(indexes), f"strict command order violated: {indexes}"

    def test_alembic_exit_42_preserved(self, tmp_path: Path) -> None:
        h = self._build_harness(tmp_path, alembic="42")
        r = self._run(h)
        assert r.returncode == 42
        assert "Setup complete" not in r.stdout

    def test_bootstrap_exit_43_preserved_no_pnpm(self, tmp_path: Path) -> None:
        h = self._build_harness(tmp_path, bootstrap="43")
        r = self._run(h)
        assert r.returncode == 43
        assert "pnpm" not in h["log"].read_text()
        assert "Setup complete" not in r.stdout

    def test_pnpm_exit_44_preserved(self, tmp_path: Path) -> None:
        h = self._build_harness(tmp_path, pnpm="44")
        r = self._run(h)
        assert r.returncode == 44
        assert "Setup complete" not in r.stdout

    def test_pg_timeout_nonzero_no_later_steps(self, tmp_path: Path) -> None:
        h = self._build_harness(tmp_path, pg="1")
        r = self._run(h)
        assert r.returncode != 0
        log = h["log"].read_text()
        assert "alembic" not in log
        assert "pip install" not in log

    def test_redis_timeout_nonzero(self, tmp_path: Path) -> None:
        h = self._build_harness(tmp_path, redis="1")
        r = self._run(h)
        assert r.returncode != 0

    def test_invalid_compose_config_zero_side_effects(self, tmp_path: Path) -> None:
        h = self._build_harness(tmp_path, compose_config="1")
        repo = h["repo"]
        r = self._run(h)
        assert r.returncode != 0
        assert not (repo / "logs").exists()
        assert not (repo / "uploads").exists()
        assert not (repo / "frontend" / ".env").exists()
        log = h["log"].read_text()
        assert "up -d" not in log
        assert "pip install" not in log
        assert "alembic" not in log
        assert "bootstrap" not in log
        assert "pnpm" not in log

    def test_no_secret_in_output(self, tmp_path: Path) -> None:
        h = self._build_harness(tmp_path)
        r = self._run(h)
        combined = r.stdout + r.stderr
        assert self._SENTINEL_PW not in combined
        assert "postgresql://pguser" not in combined

    def test_idempotent_second_run(self, tmp_path: Path) -> None:
        h = self._build_harness(tmp_path)
        assert self._run(h).returncode == 0
        before = {p.name: p.read_bytes() for p in (h["repo"] / "frontend").iterdir()}
        assert self._run(h).returncode == 0
        after = {p.name: p.read_bytes() for p in (h["repo"] / "frontend").iterdir()}
        assert set(before) == set(after)
        for name in before:
            assert before[name] == after[name], f"unexpected file mutation: {name}"
        assert (h["repo"] / "frontend" / ".env").read_text().count("VITE_API_URL") == 1

    # ---- launcher tests (R5-R5 / R5-R6) ----------------------------------

    def test_launcher_rejects_system32_wsl_bash(self) -> None:
        """The selected Bash must never be System32/WSL."""
        selected = _select_bash()
        assert "system32" not in selected.lower()
        assert "wsl" not in selected.lower()
        assert "windowsapps" not in selected.lower()
        import os
        assert os.path.isfile(selected)

    @pytest.mark.parametrize(
        "bad_path",
        [
            r"C:\Windows\System32\bash.exe",
            r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\bash.exe",
        ],
    )
    def test_launcher_fail_closed_when_only_system32_wsl_bash_exists(
        self, monkeypatch, bad_path: str
    ) -> None:
        """When only System32/WSL bash exists, selection must raise (fail closed)."""
        import os
        import shutil
        monkeypatch.setattr(os.path, "isfile", lambda p: False)
        monkeypatch.setattr(shutil, "which", lambda name: bad_path)
        with pytest.raises(RuntimeError):
            _select_bash()

    def test_launcher_crlf_enforcement_zero_crlf_blob(self) -> None:
        """The committed setup.sh blob must have zero CRLF bytes (cross-host
        LF guarantee via .gitattributes). Runtime CRLF enforcement is proven
        separately by setup.sh's fail-closed CRLF self-check."""
        import subprocess
        # The committed blob must be LF-only
        result = subprocess.run(
            ["git", "cat-file", "blob", "HEAD:backend/scripts/setup.sh"],
            capture_output=True, text=False,
        )
        assert result.returncode == 0, "could not read committed blob"
        assert b"\r" not in result.stdout, "committed setup.sh blob contains CRLF"
        # .gitattributes must enforce eol=lf
        ga = (BACKEND_DIR.parent / ".gitattributes").read_text(encoding="utf-8")
        assert "backend/scripts/setup.sh" in ga and "eol=lf" in ga

    def test_launcher_crlf_mutated_script_fails_before_any_command(
        self, tmp_path: Path
    ) -> None:
        """A CRLF-mutated copy of the committed setup.sh must exit non-zero via
        its fail-closed CRLF self-check BEFORE any fake command runs (only the
        python raw-byte self-check may appear in the command log)."""
        h = self._build_harness(tmp_path)
        script = h["repo"] / "backend" / "scripts" / "setup.sh"
        script.write_bytes(script.read_bytes().replace(b"\n", b"\r\n"))
        assert b"\r\n" in script.read_bytes()[:200]
        r = self._run(h)
        assert r.returncode != 0
        assert "CRLF line endings" in r.stderr
        log_lines = h["log"].read_text().splitlines()
        assert len(log_lines) == 1 and "python -c" in log_lines[0]

    def test_initial_preflight_pipe_runs_before_compose_up(self, tmp_path: Path) -> None:
        """The rendered-Compose-JSON pipe into setup_preflight.py must run
        before any service side effect (compose up)."""
        h = self._build_harness(tmp_path)
        r = self._run(h)
        assert r.returncode == 0, r.stderr
        log_lines = h["log"].read_text().splitlines()
        pre_idx = next(
            i for i, l in enumerate(log_lines)
            if "setup_preflight.py" in l and "--post-install" not in l
        )
        up_idx = next(i for i, l in enumerate(log_lines) if "up -d" in l)
        assert pre_idx < up_idx, f"initial preflight not before compose up: {log_lines}"

    def test_post_install_verification_runs_between_pip_and_alembic(
        self, tmp_path: Path
    ) -> None:
        """The --post-install settings comparison must run after pip install
        and BEFORE Alembic / tenant bootstrap."""
        h = self._build_harness(tmp_path)
        r = self._run(h)
        assert r.returncode == 0, r.stderr
        log_lines = h["log"].read_text().splitlines()
        pip_idx = next(i for i, l in enumerate(log_lines) if "pip install -r requirements.txt" in l)
        post_idx = next(i for i, l in enumerate(log_lines) if "setup_preflight.py --env-file .env --post-install" in l)
        alembic_idx = next(i for i, l in enumerate(log_lines) if "alembic upgrade head" in l)
        assert pip_idx < post_idx < alembic_idx, f"post-install order violated: {log_lines}"

    def test_post_install_mismatch_fails_before_alembic(self, tmp_path: Path) -> None:
        """A settings/.env mismatch detected by --post-install must stop the
        setup before Alembic or tenant bootstrap runs."""
        h = self._build_harness(tmp_path)
        r = self._run(h, H7R2_POSTINSTALL_MISMATCH="1")
        assert r.returncode != 0
        log = h["log"].read_text()
        assert "pip install -r requirements.txt" in log
        assert "alembic" not in log
        assert "bootstrap_tenant_schema" not in log
        assert "pnpm install" not in log

    # ---- cross-host + secret-argv (R7/R8) --------------------------------

    def test_cross_host_coreutils_verified_when_available(self, tmp_path: Path) -> None:
        """GREEN: on this host the required coreutils resolve and the run
        succeeds (Git Bash /usr/bin + /mingw64/bin explicitly provided)."""
        h = self._build_harness(tmp_path)
        r = self._run(h)
        assert r.returncode == 0, r.stderr

    def test_verify_coreutils_rejects_missing_real_dependency(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """RED: a REAL required dependency (dirname/grep/...) that is not on the
        probe PATH must fail closed. With PATH emptied, none resolve."""
        self._build_harness(tmp_path)  # ensure helper env exists
        monkeypatch.delenv("PATH", raising=False)
        with pytest.raises(RuntimeError, match="required coreutils not found"):
            self._verify_coreutils(_select_bash(), [])

    def test_verify_coreutils_rejects_probe_failure(self, tmp_path: Path) -> None:
        """RED: if the Bash probe cannot execute (missing bash) it must fail
        closed with the probe-failure error rather than a raw traceback."""
        h = self._build_harness(tmp_path)
        with pytest.raises(RuntimeError, match="coreutils probe failed"):
            self._verify_coreutils(
                "/definitely/not/a/real/bash", [self._msys_path(str(h["bin"]))]
            )

    def test_verify_coreutils_fails_when_probe_returns_nonzero(self, tmp_path: Path) -> None:
        """RED: the probe STARTS successfully but returns a NON-ZERO exit code.
        ``sys.executable`` is guaranteed to exist and launch, but it receives
        shell syntax (the coreutils probe) as Python code, so it exits non-zero
        with a SyntaxError.  ``_verify_coreutils`` must raise exactly
        ``RuntimeError('coreutils probe failed')``.  This is deterministic and
        host-independent (no reliance on a ``false`` coreutil being on PATH),
        and is distinct from the OSError / non-executable case."""
        import os
        import sys
        self._build_harness(tmp_path)
        exe = sys.executable
        assert exe and os.path.isfile(exe), "sys.executable must be an existing executable"
        with pytest.raises(RuntimeError) as exc_info:
            self._verify_coreutils(exe, [])
        assert str(exc_info.value) == "coreutils probe failed"

    def test_unique_sentinel_absent_from_all_captures(self, tmp_path: Path) -> None:
        """The unique password sentinel (in .env AND Compose output) must be
        absent from every captured surface: argv (the command log), stdout,
        and stderr — proving no secret is passed on argv or leaked."""
        h = self._build_harness(tmp_path)
        r = self._run(h)
        assert r.returncode == 0, r.stderr
        log = h["log"].read_text()
        sentinel = self._SENTINEL_PW
        # argv hygiene: the preflight invocation carries no secret/secret-argv
        preflight_lines = [l for l in log.splitlines() if "setup_preflight.py" in l]
        assert preflight_lines, "preflight invocation not logged"
        for line in preflight_lines:
            assert sentinel not in line
            assert "--process-db" not in line
            assert "--process-redis" not in line
        # every captured surface is sentinel-free
        assert sentinel not in log
        assert sentinel not in r.stdout
        assert sentinel not in r.stderr

    def test_compose_invocations_carry_env_file_before_subcommand(
        self, tmp_path: Path
    ) -> None:
        """R11: every Compose operation (config/up/exec) is invoked with the
        global ``--env-file <backend/.env>`` option BEFORE the subcommand —
        setup works without manually exporting backend/.env into the caller
        environment."""
        h = self._build_harness(tmp_path)
        r = self._run(h)
        assert r.returncode == 0, r.stderr
        docker_lines = [
            l for l in h["log"].read_text().splitlines() if l.startswith("docker ")
        ]
        # the `compose version` capability probe legitimately carries no
        # --env-file; every OPERATION (config/up/exec) must.
        operation_lines = [l for l in docker_lines if "version" not in l]
        assert operation_lines, "no docker operations logged"
        for line in operation_lines:
            assert "--env-file" in line, f"docker call missing --env-file: {line}"
        # --env-file precedes the subcommand for the render and up calls
        for mark in ("config --format json", "up -d"):
            marked = [l for l in operation_lines if mark in l]
            assert marked, f"no docker call with {mark!r}"
            for line in marked:
                assert line.index("--env-file") < line.index(mark.split()[0]), line

    # ---- standalone Compose v2 (R12) ------------------------------------

    @classmethod
    def _run_mutated_standalone(cls, tmp_path: Path, mutate):
        """Build a standalone harness, replace the committed setup.sh copy with
        a mutation, and run it.  Returns the CompletedProcess."""
        h = cls._build_harness(tmp_path, standalone=True)
        script = h["repo"] / "backend" / "scripts" / "setup.sh"
        original = SETUP_SH.read_text(encoding="utf-8")
        mutated = mutate(original)
        assert mutated != original, "mutation did not change setup.sh"
        # write LF bytes: text-mode writes would emit CRLF and trip the CRLF
        # self-check instead of the intended mutation path.
        script.write_bytes(mutated.encode("utf-8"))
        return cls._run(h)

    def test_standalone_compose_env_file_enforced(self, tmp_path: Path) -> None:
        """GREEN (R12): with the `docker compose` plugin hidden and only a
        standalone Compose v2 available, candidate selection uses the version
        probe, and every operation carries --env-file BEFORE the subcommand —
        setup completes."""
        h = self._build_harness(tmp_path, standalone=True)
        r = self._run(h)
        assert r.returncode == 0, r.stderr
        assert "Setup complete" in r.stdout
        log = h["log"].read_text()
        assert "docker-compose version" in log
        ops = [
            l for l in log.splitlines()
            if l.startswith("docker-compose ") and "version" not in l
        ]
        assert ops, "no docker-compose operations logged"
        for line in ops:
            assert line.startswith("docker-compose --env-file"), line

    def test_standalone_mutation_remove_env_file_fails(self, tmp_path: Path) -> None:
        """RED (R12): removing --env-file from the COMPOSE array makes the
        enforcing standalone fake reject `config` — setup fails."""
        r = self._run_mutated_standalone(
            tmp_path,
            lambda t: t.replace(
                'COMPOSE=("${COMPOSE_BASE[@]}" --env-file "$BACKEND_ENV")',
                'COMPOSE=("${COMPOSE_BASE[@]}")',
            ),
        )
        assert r.returncode != 0
        assert "docker-compose configuration is invalid" in r.stderr
        assert "Setup complete" not in r.stdout

    def test_standalone_mutation_env_file_after_subcommand_fails(
        self, tmp_path: Path
    ) -> None:
        """RED (R12): placing --env-file AFTER the config subcommand is
        rejected by the enforcing standalone fake — setup fails."""
        r = self._run_mutated_standalone(
            tmp_path,
            lambda t: t.replace(
                'COMPOSE=("${COMPOSE_BASE[@]}" --env-file "$BACKEND_ENV")',
                'COMPOSE=("${COMPOSE_BASE[@]}")',
            ).replace(
                '"${COMPOSE[@]}" config --quiet',
                '"${COMPOSE[@]}" config --env-file "$BACKEND_ENV" --quiet',
            ),
        )
        assert r.returncode != 0
        assert "docker-compose configuration is invalid" in r.stderr
        assert "Setup complete" not in r.stdout

    def test_standalone_mutation_premature_config_probe_fails(
        self, tmp_path: Path
    ) -> None:
        """RED (R12): restoring the premature `docker-compose config --format
        json` probe in candidate selection runs config WITHOUT --env-file and
        is rejected by the enforcing fake — selection fails closed."""
        r = self._run_mutated_standalone(
            tmp_path,
            lambda t: t.replace(
                "    COMPOSE_BASE=(docker-compose)\n",
                "    if docker-compose config --format json &> /dev/null < /dev/null; then\n        COMPOSE_BASE=(docker-compose)\n    fi\n",
            ),
        )
        assert r.returncode != 0
        assert "Docker Compose v2 is required" in r.stderr
        assert "Setup complete" not in r.stdout

    def test_standalone_fakes_exist_and_are_executable(self, tmp_path: Path) -> None:
        """Fail-closed (R13): the standalone docker-compose fake must EXIST and
        be executable — proven via the selected Bash's `test -x` (the POSIX/
        MSYS executability check that `chmod +x` satisfies; Windows os.stat
        does not expose exec bits)."""
        import subprocess
        h = self._build_harness(tmp_path, standalone=True)
        bash_bin = _select_bash()
        for name in ("docker", "docker-compose"):
            f = h["bin"] / name
            assert f.exists(), f"{name} fake missing"
            res = subprocess.run(
                [bash_bin, "-c", f'test -x "{self._msys_path(str(f))}"'],
                capture_output=True,
            )
            assert res.returncode == 0, f"{name} fake is not executable (bash test -x)"

    def test_normal_harness_does_not_chmod_nonexistent_docker_compose(
        self, tmp_path: Path
    ) -> None:
        """Fail-closed (R13): the normal harness builds only its own fakes and
        never attempts to chmod a docker-compose file it does not create."""
        import subprocess
        h = self._build_harness(tmp_path)
        assert not (h["bin"] / "docker-compose").exists()
        bash_bin = _select_bash()
        for name in self._FAKE_NAMES:
            f = h["bin"] / name
            assert f.exists(), f"{name} fake missing"
            res = subprocess.run(
                [bash_bin, "-c", f'test -x "{self._msys_path(str(f))}"'],
                capture_output=True,
            )
            assert res.returncode == 0, f"{name} fake is not executable (bash test -x)"

    # ---- native Alembic connection context (R14) ------------------------

    @classmethod
    def _run_mutated(cls, tmp_path: Path, mutate):
        """Build a normal harness, replace the committed setup.sh copy with a
        mutation, and run it.  Returns the CompletedProcess."""
        h = cls._build_harness(tmp_path)
        script = h["repo"] / "backend" / "scripts" / "setup.sh"
        original = SETUP_SH.read_text(encoding="utf-8")
        mutated = mutate(original)
        assert mutated != original, "mutation did not change setup.sh"
        script.write_bytes(mutated.encode("utf-8"))
        return cls._run(h)

    def test_alembic_and_bootstrap_use_validated_env_url(self, tmp_path: Path) -> None:
        """GREEN (R14/R15): Alembic and tenant bootstrap both receive the
        validated DATABASE_URL exported from backend/.env (the enforcing fakes
        would fail otherwise); neither sentinel reaches any capture channel."""
        h = self._build_harness(tmp_path)
        r = self._run(h)
        assert r.returncode == 0, r.stderr
        assert "Setup complete" in r.stdout
        log = h["log"].read_text()
        assert "alembic upgrade head" in log
        assert "bootstrap_tenant_schema" in log
        # R15: BOTH sentinels (DB password + reporting password) never appear
        for sentinel in (self._SENTINEL_PW, self._SENTINEL_RUP):
            assert sentinel not in log
            assert sentinel not in r.stdout
            assert sentinel not in r.stderr

    def test_mutation_remove_db_url_export_fails(self, tmp_path: Path) -> None:
        """RED (R14): removing the DATABASE_URL export leaves Alembic without
        the validated URL (alembic.ini fallback) — the enforcing fake fails."""
        r = self._run_mutated(
            tmp_path,
            lambda t: t.replace('export DATABASE_URL="$_NATIVE_DB_URL"\n', ""),
        )
        assert r.returncode != 0
        assert "Setup complete" not in r.stdout

    def test_mutation_db_url_export_after_alembic_fails(self, tmp_path: Path) -> None:
        """RED (R14): exporting DATABASE_URL only AFTER `alembic upgrade head`
        leaves Alembic without the URL — fails before completion."""
        text_mut = lambda t: (
            t.replace('export DATABASE_URL="$_NATIVE_DB_URL"\n', "")
             .replace("alembic upgrade head",
                      'alembic upgrade head\nexport DATABASE_URL="$_NATIVE_DB_URL"')
        )
        r = self._run_mutated(tmp_path, text_mut)
        assert r.returncode != 0
        assert "Setup complete" not in r.stdout

    def test_mutation_wrong_db_url_alembic_fails(self, tmp_path: Path) -> None:
        """RED (R14): exporting a DATABASE_URL that differs from backend/.env
        makes the enforcing Alembic fake reject the connection."""
        r = self._run_mutated(
            tmp_path,
            lambda t: t.replace(
                'export DATABASE_URL="$_NATIVE_DB_URL"',
                'export DATABASE_URL="postgresql://wrong:h7r14wrong@localhost:5432/wrong"',  # pragma: allowlist secret
            ),
        )
        assert r.returncode != 0
        assert "Setup complete" not in r.stdout

    def test_mutation_wrong_db_url_bootstrap_fails(self, tmp_path: Path) -> None:
        """RED (R14): re-exporting a mismatched DATABASE_URL between Alembic
        and bootstrap makes the enforcing bootstrap fake fail (Alembic still
        passes with the correct earlier export)."""
        r = self._run_mutated(
            tmp_path,
            lambda t: t.replace(
                "python scripts/bootstrap_tenant_schema.py",
                'export DATABASE_URL="postgresql://wrong:h7r14wrong@localhost:5432/wrong"\n'  # pragma: allowlist secret
                "python scripts/bootstrap_tenant_schema.py",
            ),
        )
        assert r.returncode != 0
        assert "Setup complete" not in r.stdout

    def test_missing_db_url_in_env_fails_before_alembic(self, tmp_path: Path) -> None:
        """RED (R14): a backend/.env without DATABASE_URL fails before Alembic
        runs (post-install verification rejects it)."""
        h = self._build_harness(tmp_path)
        env_file = h["repo"] / "backend" / ".env"
        kept = "\n".join(
            l for l in env_file.read_text().splitlines() if not l.startswith("DATABASE_URL=")
        ) + "\n"
        env_file.write_text(kept, encoding="utf-8")
        r = self._run(h)
        assert r.returncode != 0
        log = h["log"].read_text()
        assert "alembic" not in log

    # ---- R15: REPORTING_USER_PASSWORD dual-secret tests -----------------

    def test_mutation_remove_rup_export_fails(self, tmp_path: Path) -> None:
        """RED (R15): removing the REPORTING_USER_PASSWORD export leaves
        Alembic without the reporting password — the enforcing fake fails."""
        r = self._run_mutated(
            tmp_path,
            lambda t: t.replace('export REPORTING_USER_PASSWORD="$_NATIVE_RUP"\n', ""),
        )
        assert r.returncode != 0
        assert "Setup complete" not in r.stdout

    def test_mutation_wrong_rup_fails(self, tmp_path: Path) -> None:
        """RED (R15): exporting a REPORTING_USER_PASSWORD that differs from
        backend/.env makes the enforcing Alembic fake reject it."""
        r = self._run_mutated(
            tmp_path,
            lambda t: t.replace(
                'export REPORTING_USER_PASSWORD="$_NATIVE_RUP"',
                'export REPORTING_USER_PASSWORD="wrong_rup_value"',  # pragma: allowlist secret
            ),
        )
        assert r.returncode != 0
        assert "Setup complete" not in r.stdout

    def test_rup_unset_before_bootstrap(self, tmp_path: Path) -> None:
        """GREEN (R15): REPORTING_USER_PASSWORD is unset before tenant
        bootstrap (the enforcing bootstrap fake rejects a surviving RUP)."""
        h = self._build_harness(tmp_path)
        r = self._run(h)
        assert r.returncode == 0, r.stderr
        assert "Setup complete" in r.stdout


# ---------------------------------------------------------------------------
# AST migration-env dependency inventory (R15/R15-R1/R15-R2)
# ---------------------------------------------------------------------------
def _scan_migration_env_vars(source: str) -> set[str]:
    """Pure scanner: extract env-var names from Python source code. Recognized:
    os.environ.get(K), os.environ[K], os.getenv(K), and import/assignment
    aliases. Hard-fails (AssertionError) on dynamic keys, setdefault/pop/
    update/putenv, or any other os.environ access on a tracked name."""
    import ast
    tree = ast.parse(source)
    environ_names: set[str] = set()
    getenv_names: set[str] = set()
    # First pass: track imports and assignment aliases
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name == "environ":
                    environ_names.add(local)
                elif alias.name == "getenv":
                    getenv_names.add(local)
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        environ_names.add(target.id)
    env_vars: set[str] = set()

    def _is_environ(val):
        return (
            (isinstance(val, ast.Attribute) and val.attr == "environ")
            or (isinstance(val, ast.Name) and val.id in environ_names)
        )

    def _key(node):
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            raise AssertionError(f"dynamic env-var key at line {getattr(node, 'lineno', '?')}")
        env_vars.add(node.args[0].value)

    def _sub(node):
        sl = node.slice
        if not isinstance(sl, ast.Constant) or not isinstance(sl.value, str):
            raise AssertionError(f"dynamic env-var subscript at line {getattr(node, 'lineno', '?')}")
        env_vars.add(sl.value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr == "get" and _is_environ(func.value):
                    _key(node)
                elif func.attr == "getenv" and isinstance(func.value, ast.Name):
                    _key(node)
                elif func.attr in ("setdefault", "pop", "update") and _is_environ(func.value):
                    raise AssertionError(f"unauthorized os.environ.{func.attr} at line {node.lineno}")
                elif func.attr == "putenv":
                    raise AssertionError(f"os.putenv not allowed at line {node.lineno}")
            elif isinstance(func, ast.Name) and func.id in getenv_names:
                _key(node)
        if isinstance(node, ast.Subscript) and _is_environ(node.value):
            _sub(node)
    return env_vars


class TestMigrationEnvVarScanner:
    """Synthetic-source mutation tests for _scan_migration_env_vars — proves
    every supported syntax form is caught and every unauthorized form
    hard-fails."""

    @pytest.mark.parametrize("src,expected", [
        ('import os; os.environ.get("VAR")', {"VAR"}),
        ('import os; os.environ["VAR"]', {"VAR"}),
        ('import os; os.getenv("VAR")', {"VAR"}),
        ('import _os; _os.environ.get("VAR")', {"VAR"}),
        ('import _os; _os.environ["VAR"]', {"VAR"}),
        ('import _os; _os.getenv("VAR")', {"VAR"}),
        ('from os import environ; environ.get("VAR")', {"VAR"}),
        ('from os import environ; environ["VAR"]', {"VAR"}),
        ('from os import environ as e; e.get("VAR")', {"VAR"}),
        ('from os import environ as e; e["VAR"]', {"VAR"}),
        ('from os import getenv; getenv("VAR")', {"VAR"}),
        ('from os import getenv as g; g("VAR")', {"VAR"}),
        ('import os; env = os.environ; env.get("VAR")', {"VAR"}),
        ('import os; env = os.environ; env["VAR"]', {"VAR"}),
    ])
    def test_supported_forms(self, src: str, expected: set[str]) -> None:
        assert _scan_migration_env_vars(src) == expected

    @pytest.mark.parametrize("src", [
        'import os; os.environ.get(some_var)',             # dynamic key
        'import os; os.environ[some_var]',                 # dynamic subscript
        'import os; os.environ.setdefault("VAR", "x")',    # setdefault
        'import os; os.environ.pop("VAR")',                # pop
        'import os; os.environ.update({"VAR": "x"})',      # update
        'import os; os.putenv("VAR", "x")',                # putenv
        'import os; env = os.environ; env.setdefault("VAR", "x")',  # alias setdefault
    ])
    def test_unauthorized_forms_hard_fail(self, src: str) -> None:
        with pytest.raises(AssertionError):
            _scan_migration_env_vars(src)


def test_migration_env_dependency_inventory_is_exactly_reporting_user_password():
    """Real migration files 001–037: the non-connection env-var set must be
    exactly {REPORTING_USER_PASSWORD}."""
    migration_dir = BACKEND_DIR / "alembic" / "versions"
    env_vars: set[str] = set()
    for pyfile in sorted(migration_dir.glob("*.py")):
        env_vars |= _scan_migration_env_vars(pyfile.read_text(encoding="utf-8"))
    extra = env_vars - {"DATABASE_URL", "REDIS_URL"}
    assert extra == {"REPORTING_USER_PASSWORD"}, (
        f"unexpected migration env-var dependency set: {extra}"
    )


# ──────────────────────────────────────────────────────────────────────────── #
# GREEN — installed runtime reflects the reconciled manifests
# ──────────────────────────────────────────────────────────────────────────── #
class TestH7R4InstalledRuntime:
    @staticmethod
    def _version(pkg: str) -> str:
        from importlib.metadata import version

        return version(pkg)

    @pytest.mark.parametrize("pkg,expected", sorted(EXPECTED.items()))
    def test_installed_version_matches_manifest(self, pkg: str, expected: str) -> None:
        assert self._version(pkg) == expected

    def test_passlib_bcrypt_hash_verify_round_trip(self) -> None:
        from passlib.context import CryptContext

        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        phrase = "H7-R4-round-trip-123!"
        h = ctx.hash(phrase)
        assert h.startswith("$2") and ctx.verify(phrase, h) is True and ctx.verify(phrase + "x", h) is False

    def test_core_security_hash_password_and_verify_password(self) -> None:
        from core.security import hash_password, verify_password

        phrase = "OwnerSetup123!"
        h = hash_password(phrase)
        assert verify_password(phrase, h) is True and verify_password("wrong-password", h) is False
        long_input = "x" * 200
        assert verify_password(long_input, hash_password(long_input)) is True

    def test_openpyxl_and_et_xmlfile_import_and_workbook(self) -> None:
        import openpyxl
        import et_xmlfile  # noqa: F401

        assert openpyxl.__version__ == "3.1.5"
        wb = openpyxl.Workbook()
        wb.active["A1"] = "h7-r4"
        assert wb.active["A1"].value == "h7-r4"

    def test_cryptography_import_and_version(self) -> None:
        import cryptography

        assert cryptography.__version__ == self._version("cryptography") == "46.0.5"

    def test_fastapi_application_imports(self) -> None:
        from fastapi import FastAPI
        from main import app  # noqa: F401

        assert isinstance(app, FastAPI)


# ──────────────────────────────────────────────────────────────────────────── #
# RED — requirements parser fail-closed  (KILO-H7R3V1-002 — extras added)
# ──────────────────────────────────────────────────────────────────────────── #
class TestH7R4RequirementsParserFailClosed:
    def test_conflicting_duplicate_requirements(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            parse_requirements_text('bcrypt==4.0.1 ; python_version >= "3.11"\nbcrypt==5.0.0 ; python_version >= "3.11"\n')

    def test_identical_duplicate_requirements(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            parse_requirements_text("bcrypt==4.0.1\nbcrypt==4.0.1\n")

    def test_normalized_name_collision(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            parse_requirements_text("et-xmlfile==2.0.0\net_xmlfile==1.0.0\n")

    def test_duplicate_with_different_markers_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            parse_requirements_text('bcrypt==4.0.1 ; python_version >= "3.11"\nbcrypt==4.0.1 ; python_version >= "3.12"\n')

    def test_malformed_trailing_garbage(self) -> None:
        with pytest.raises(ValueError, match="malformed requirement"):
            parse_requirements_text("bcrypt==4.0.1 garbage\n")

    def test_non_exact_specifier_rejected(self) -> None:
        with pytest.raises(ValueError, match="only exact"):
            parse_requirements_text("bcrypt>=4.0.1\n")

    def test_wildcard_pin_rejected(self) -> None:
        with pytest.raises(ValueError, match="wildcard"):
            parse_requirements_text("bcrypt==4.0.*\n")

    def test_url_requirement_rejected(self) -> None:
        with pytest.raises(ValueError, match="URL"):
            parse_requirements_text("bcrypt @ https://example.com/bcrypt.tar.gz\n")

    def test_extras_rejected(self) -> None:
        with pytest.raises(ValueError, match="extras"):
            parse_requirements_text("uvicorn[standard]==0.40.0\n")

    def test_invalid_marker_rejected(self) -> None:
        with pytest.raises(ValueError, match="malformed requirement"):
            parse_requirements_text('bcrypt==4.0.1 ; python_version !=!= "3.11"\n')


# ──────────────────────────────────────────────────────────────────────────── #
# RED — lock parser fail-closed  (KILO-H7R3V1-001 — 10+ malformed forms)
# ──────────────────────────────────────────────────────────────────────────── #
class TestH7R4LockParserFailClosed:
    # ---- duplicate entries ----
    def test_duplicate_lock_entries_rejected(self) -> None:
        pkgs = [
            {"name": "bcrypt", "version": "4.0.1", "groups": ["main"]},
            {"name": "bcrypt", "version": "5.0.0", "groups": ["main"]},
        ]
        with pytest.raises(ValueError, match="duplicate"):
            parse_main_lock_packages(pkgs)

    # ---- structural: packages ----
    def test_packages_not_list_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a list"):
            parse_main_lock_packages({"name": "bcrypt"})  # type: ignore[arg-type]

    def test_entry_not_dict_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a mapping"):
            parse_main_lock_packages(["not-a-dict"])  # type: ignore[list-item]

    # ---- name malformed ----
    def test_name_missing_rejected(self) -> None:
        with pytest.raises(ValueError, match="missing 'name'"):
            parse_main_lock_packages([{"version": "4.0.1", "groups": ["main"]}])

    def test_name_non_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="'name' must be str"):
            parse_main_lock_packages([{"name": 123, "version": "4.0.1", "groups": ["main"]}])  # type: ignore[list-item]

    def test_name_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="'name' must not be empty"):
            parse_main_lock_packages([{"name": "", "version": "4.0.1", "groups": ["main"]}])

    def test_name_surrounding_whitespace_rejected(self) -> None:
        with pytest.raises(ValueError, match="surrounding whitespace"):
            parse_main_lock_packages([{"name": " bcrypt", "version": "4.0.1", "groups": ["main"]}])

    # ---- version malformed ----
    def test_version_missing_rejected(self) -> None:
        with pytest.raises(ValueError, match="missing 'version'"):
            parse_main_lock_packages([{"name": "bcrypt", "groups": ["main"]}])

    def test_version_non_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="'version' must be str"):
            parse_main_lock_packages([{"name": "bcrypt", "version": 401, "groups": ["main"]}])  # type: ignore[list-item]

    def test_version_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="'version' must not be empty"):
            parse_main_lock_packages([{"name": "bcrypt", "version": "", "groups": ["main"]}])

    def test_version_surrounding_whitespace_rejected(self) -> None:
        with pytest.raises(ValueError, match="surrounding whitespace"):
            parse_main_lock_packages([{"name": "bcrypt", "version": " 4.0.1", "groups": ["main"]}])

    # ---- groups malformed ----
    def test_groups_missing_rejected(self) -> None:
        with pytest.raises(ValueError, match="missing 'groups'"):
            parse_main_lock_packages([{"name": "bcrypt", "version": "4.0.1"}])

    def test_groups_not_list_rejected(self) -> None:
        with pytest.raises(ValueError, match="'groups' must be a list"):
            parse_main_lock_packages([{"name": "bcrypt", "version": "4.0.1", "groups": "main"}])  # type: ignore[list-item]

    def test_groups_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="'groups' must not be empty"):
            parse_main_lock_packages([{"name": "bcrypt", "version": "4.0.1", "groups": []}])

    def test_groups_contains_non_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be str"):
            parse_main_lock_packages([{"name": "bcrypt", "version": "4.0.1", "groups": [True]}])  # type: ignore[list-item]

    def test_groups_contains_empty_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            parse_main_lock_packages([{"name": "bcrypt", "version": "4.0.1", "groups": [""]}])

    def test_groups_contains_whitespace_rejected(self) -> None:
        with pytest.raises(ValueError, match="surrounding whitespace"):
            parse_main_lock_packages([{"name": "bcrypt", "version": "4.0.1", "groups": [" main"]}])

    def test_groups_contains_none_rejected(self) -> None:
        with pytest.raises(ValueError, match="is None"):
            parse_main_lock_packages([{"name": "bcrypt", "version": "4.0.1", "groups": [None]}])  # type: ignore[list-item]

    def test_groups_duplicate_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate group value"):
            parse_main_lock_packages([{"name": "bcrypt", "version": "4.0.1", "groups": ["main", "main"]}])


# ──────────────────────────────────────────────────────────────────────────── #
# RED — inventory deltas (missing / extra / mismatch + et-xmlfile)
# ──────────────────────────────────────────────────────────────────────────── #
class TestH7R4InventoryFailClosed:
    @staticmethod
    def _fixtures() -> tuple[str, list[dict]]:
        return (
            REQUIREMENTS.read_text(encoding="utf-8"),
            tomllib.load(POETRY_LOCK.open("rb"))["package"],
        )

    def test_missing_inventory_package_detected(self) -> None:
        r, lk = self._fixtures()
        r2 = re.sub(r"(?m)^passlib==.*\n", "", r)
        missing, _, _ = main_inventory_deltas(r2, lk)
        assert "passlib" in missing

    def test_extra_inventory_package_detected(self) -> None:
        r, lk = self._fixtures()
        r2 = r + 'not-a-real-pkg==1.2.3 ; python_version >= "3.11"\n'
        _, extra, _ = main_inventory_deltas(r2, lk)
        assert "not-a-real-pkg" in extra

    def test_version_mismatch_detected(self) -> None:
        r, lk = self._fixtures()
        r2 = r.replace("passlib==1.7.4", "passlib==1.7.5")
        _, _, mismatch = main_inventory_deltas(r2, lk)
        assert "passlib" in mismatch

    def test_et_xmlfile_removal_detected(self) -> None:
        r, lk = self._fixtures()
        r2 = re.sub(r"(?m)^et-xmlfile==.*\n", "", r)
        missing, _, _ = main_inventory_deltas(r2, lk)
        assert "et-xmlfile" in missing

    def test_et_xmlfile_version_mutation_detected(self) -> None:
        r, lk = self._fixtures()
        r2 = r.replace("et-xmlfile==2.0.0", "et-xmlfile==9.9.9")
        _, _, mismatch = main_inventory_deltas(r2, lk)
        assert "et-xmlfile" in mismatch
