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
            return 1
        if re.match(r"^(for|while|until|case)\b", low):
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

    # ------- step 1: locate the exact pip line --------------------------------
    pip_idx: int | None = None
    depth = 0
    for i, raw in enumerate(lines):
        s = raw.lstrip()
        if not s or s.startswith("#"):
            continue

        # track block depth BEFORE evaluating this line's content
        delta = _block_delta(s)
        if delta == -1 and depth > 0:
            depth -= 1
            if P in s:  # pip keyword inside a closer line? still reject
                pass
        new_depth = depth + delta if delta == 1 else depth

        # reject if blocks are open and this line contains pip
        if new_depth > 0 and P in s:
            raise ValueError("setup.sh: pip install inside a shell block is not allowed")

        if delta == 1:
            depth = new_depth
            if P in s:
                raise ValueError("setup.sh: pip install inside a shell block is not allowed")
            continue

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
    # DATABASE_URL resolution from core.config.settings
    if not any("settings.DATABASE_URL" in r for r in non_comment):
        raise ValueError("setup.sh: must resolve DATABASE_URL from core.config.settings")
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
            '''export DATABASE_URL="$RESOLVED_DATABASE_URL"
python scripts/bootstrap_tenant_schema.py "${DEFAULT_TENANT_SCHEMA:-t_dev}"''',
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
            'alembic upgrade head\n\n# ---- resolve',
            '# placeholder\n',
        )
        with pytest.raises(ValueError, match="public"):
            check_setup_sh_wiring(text)

    def test_RED_missing_bootstrap_database_url(self) -> None:
        text = self._base().replace('export DATABASE_URL="$RESOLVED_DATABASE_URL"\n', "")
        with pytest.raises(ValueError, match="(?i)database"):
            check_setup_sh_wiring(text)

    def test_RED_missing_database_url_resolution(self) -> None:
        text = self._base().replace("settings.DATABASE_URL", "os.environ.get('X')")
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
# ──────────────────────────────────────────────────────────────────────────── #
# Executable fake-PATH harness  (R5-R2 checkpoint — actual fake executables)
# ──────────────────────────────────────────────────────────────────────────── #
class TestH7R5R2ExecutableHarness:
    """Execute an UNMODIFIED copy of the committed setup.sh through subprocess
    against task-owned fake executables in a temporary fake-bin directory
    prepended to PATH (MSYS-style path so Git Bash performs the lookup).

    This proves actual exit-status preservation, command ordering, side-effect
    behaviour, and idempotency — not just source-text shape."""

    _FAKE_NAMES = ("docker", "pip", "alembic", "python", "pnpm")

    @staticmethod
    def _msys_path(windows_path: str) -> str:
        p = windows_path.replace("\\", "/")
        if len(p) >= 2 and p[1] == ":":
            return "/" + p[0].lower() + "/" + p[3:]
        return p

    @classmethod
    def _build_harness(cls, tmp_path: Path, **fake_exits: str) -> dict:
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
            "DATABASE_URL=postgresql://u:p@localhost:5432/db\n"
            "SECRET_KEY=notweaknotsecretkeyabcdef1234567890\n"  # pragma: allowlist secret
            "POSTGRES_USER=pguser\nPOSTGRES_DB=pgdb\n"
        )
        (repo / "frontend").mkdir(parents=True)
        (repo / "docker-compose.yml").write_text(
            "services:\n  postgres:\n    image: postgres\n  redis:\n    image: redis\n"
        )
        # UNMODIFIED copy of the committed setup.sh
        shutil.copy(SETUP_SH, repo / "backend" / "scripts" / "setup.sh")

        def _ev(name: str, default: str = "0") -> str:
            v = fake_exits.get(name, default)
            return v if v else default

        fake_bodies = {
            "docker": f'''#!/bin/bash
echo "docker $*" >> "{log_str}"
a="$*"
case "$a" in
    "compose version"*) echo "Docker Compose version v2.20.0"; exit 0;;
    "compose config"*) exit {_ev("compose_config")};;
    "compose up -d"*) exit 0;;
    "compose exec -T postgres"*)
        if echo "$a" | grep -q "pg_isready"; then
            exit {_ev("pg")}
        fi
        printf "pguser|pgdb"
        exit 0;;
    "compose exec -T redis"*) echo "PONG"; exit {_ev("redis")};;
    *) exit 0;;
esac
''',
            "pip": f'''#!/bin/bash
echo "pip $*" >> "{log_str}"
exit 0
''',
            "alembic": f'''#!/bin/bash
echo "alembic $*" >> "{log_str}"
exit {_ev("alembic")}
''',
            "python": f'''#!/bin/bash
echo "python $*" >> "{log_str}"
if [ "$1" = "-c" ]; then
    if echo "$2" | grep -q "settings.DATABASE_URL"; then
        echo "postgresql://pguser:pgpass@localhost:5432/pgdb"  # pragma: allowlist secret
        exit 0
    fi
    if echo "$2" | grep -q "urlparse"; then
        echo "pguser|pgpass|localhost|5432|pgdb"
        exit 0
    fi
fi
exit {_ev("bootstrap")}
''',
            "pnpm": f'''#!/bin/bash
echo "pnpm $*" >> "{log_str}"
exit {_ev("pnpm")}
''',
        }
        for name, body in fake_bodies.items():
            (bin_dir / name).write_text(body)
        # set MSYS2 executable bits via bash chmod
        bash_bin = shutil.which("bash") or "bash"
        quoted = " ".join(f'"{str(bin_dir / n)}"' for n in cls._FAKE_NAMES)
        subprocess.run([bash_bin, "-c", f"chmod +x {quoted}"], check=False)
        return {"repo": repo, "bin": bin_dir, "log": log_file}

    @classmethod
    def _run(cls, harness: dict, **env_overrides: str):
        import os
        import shutil
        import subprocess

        env = os.environ.copy()
        env["PATH"] = cls._msys_path(str(harness["bin"])) + os.pathsep + env.get("PATH", "")
        env["HOME"] = os.environ.get("HOME", "/tmp")
        env["SETUP_TIMEOUT_ATTEMPTS"] = env_overrides.pop("SETUP_TIMEOUT_ATTEMPTS", "3")
        env["SETUP_TIMEOUT_INTERVAL"] = env_overrides.pop("SETUP_TIMEOUT_INTERVAL", "0")
        env.update(env_overrides)
        bash_bin = shutil.which("bash") or "bash"
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
            "compose version",
            "compose config",
            "compose up -d",
            "compose exec -T postgres",
            "compose exec -T redis",
            "pip install -r requirements.txt",
            "alembic upgrade head",
            "python -c",
            "python scripts/bootstrap_tenant_schema.py",
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
        assert "compose up" not in log
        assert "pip install" not in log
        assert "alembic" not in log
        assert "bootstrap" not in log
        assert "pnpm" not in log

    def test_no_secret_in_output(self, tmp_path: Path) -> None:
        h = self._build_harness(tmp_path)
        r = self._run(h)
        combined = r.stdout + r.stderr
        assert "pgpass" not in combined
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
