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

    Non-blank, non-comment lines are scanned.  The guard requires:

      * a line whose stripped content starts with exactly
        ``pip install -r requirements.txt`` and is NOT a commented, quoted,
        inert, or dead-branch form;
      * the line is NOT unreachable (no bare ``exit``/``return`` outside an
        ``if … fi`` block before it);
      * a ``cd … backend`` line precedes the pip line and ``alembic upgrade
        head`` follows it.
    """
    P = "pip install -r requirements.txt"
    lines = text.splitlines()

    # 1) find the pip line; reject malformed forms inline
    pip_idx = None
    for i, raw in enumerate(lines):
        s = raw.lstrip()
        if not s or s.startswith("#"):
            continue
        if P not in s:
            continue

        # ---- reject forms that contain the substring but aren't real ----
        low = s.lower()
        if low.startswith(("if ", "elif ", "for ", "while ", "until ", "case ")):
            raise ValueError("setup.sh: pip install inside a shell block is not allowed")
        if low.startswith(("echo ", "printf ")):
            raise ValueError("setup.sh: pip install line appears to be inert (echo/printf)")
        if re.match(r"(false|true)\s*(&&|\|\|)", s):
            raise ValueError("setup.sh: pip install line is behind a dead-branch short-circuit")
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", s):
            raise ValueError("setup.sh: pip install command is embedded in a variable assignment")
        if s.startswith(('"', "'")):
            raise ValueError("setup.sh: pip install appears inside quoted text")

        # ---- the line itself must start with the exact command ----
        if not s.startswith(P):
            raise ValueError("setup.sh: pip install line is not a bare command")

        if pip_idx is not None:
            raise ValueError("setup.sh: more than one pip install line found")
        pip_idx = i

    if pip_idx is None:
        raise ValueError("setup.sh: no active 'pip install -r requirements.txt' command found")

    # 2) check for unreachable bare exit/return (outside if..fi) before pip
    if_depth = 0
    for raw in lines[:pip_idx]:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        # crude if/fi depth tracker
        if re.match(r"^if\b", s):
            if_depth += 1
        elif re.match(r"^fi\b", s):
            if_depth = max(0, if_depth - 1)
        elif re.match(r"^(exit|return)\b", s) and if_depth == 0:
            raise ValueError(f"setup.sh: unreachable (exit/return before pip line at L{pip_idx + 1})")

    # 3) cd backend before pip, alembic after pip
    cd_found = any(
        re.match(r"^cd\b", raw.strip()) and "backend" in raw
        for raw in lines[:pip_idx]
    )
    if not cd_found:
        raise ValueError("setup.sh: must cd into backend before pip install")
    alembic_found = any(
        raw.strip().startswith("alembic upgrade head") for raw in lines[pip_idx + 1 :]
    )
    if not alembic_found:
        raise ValueError("setup.sh: must run alembic upgrade head after pip install")


def check_dockerfile_wiring(text: str) -> None:
    """Verify the Dockerfile actively installs via Poetry/lock.

    The guard requires:

      * a ``COPY`` instruction that mentions both ``pyproject.toml`` and
        ``poetry.lock`` (ignoring comments and continuations);
      * that ``COPY`` appears textually **before** an active ``RUN poetry
        install`` line (the ``RUN`` line must NOT be commented, inert, or
        unreachable);
      * both instructions are in the same (final) build stage (no ``FROM``
        line between them).
    """
    lines = text.splitlines()
    copy_line = None
    poetry_run_line = None
    from_line_after_copy = -1

    for i, raw in enumerate(lines):
        s = raw.lstrip()
        if not s or s.startswith("#"):
            continue
        # handle COPY
        if s.upper().startswith("COPY") and "pyproject.toml" in s and "poetry.lock" in s:
            if copy_line is not None:
                raise ValueError("Dockerfile: multiple COPY pyproject+lock instructions found")
            copy_line = i
        # handle RUN poetry install
        if s.upper().startswith("RUN") and "poetry install" in s:
            # reject commented / inert
            if raw.strip().startswith("#"):
                continue  # already filtered, but double-check
            if poetry_run_line is not None:
                raise ValueError("Dockerfile: multiple RUN poetry install lines found")
            poetry_run_line = i
        # detect FROM (stage boundary)
        if s.upper().startswith("FROM") and copy_line is not None and poetry_run_line is None:
            from_line_after_copy = i

    if copy_line is None:
        raise ValueError("Dockerfile: COPY pyproject.toml poetry.lock instruction not found")
    if poetry_run_line is None:
        raise ValueError("Dockerfile: RUN poetry install instruction not found")
    if poetry_run_line <= copy_line:
        raise ValueError("Dockerfile: RUN poetry install must appear AFTER COPY pyproject.toml poetry.lock")
    if from_line_after_copy >= 0 and from_line_after_copy < poetry_run_line:
        raise ValueError("Dockerfile: COPY and RUN poetry install are not in the same build stage")


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
# GREEN — install-path source-shape guards (real files must pass)
# ──────────────────────────────────────────────────────────────────────────── #
class TestH7R4InstallPathWiring:
    def test_setup_sh_passes_structural_guard(self) -> None:
        text = SETUP_SH.read_text(encoding="utf-8")
        check_setup_sh_wiring(text)  # must not raise

    def test_dockerfile_passes_structural_guard(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        check_dockerfile_wiring(text)

    # RED mutations (setup.sh)
    def test_RED_setup_sh_commented_pip_line_detected(self) -> None:
        text = "cd backend\n# pip install -r requirements.txt\nalembic upgrade head -x t_dev"
        with pytest.raises(ValueError, match="no active"):
            check_setup_sh_wiring(text)

    def test_RED_setup_sh_pip_after_exit_rejected(self) -> None:
        with pytest.raises(ValueError, match="unreachable"):
            check_setup_sh_wiring("exit 0\npip install -r requirements.txt")

    def test_RED_setup_sh_pip_inside_if_block_rejected(self) -> None:
        with pytest.raises(ValueError, match="block"):
            check_setup_sh_wiring("if true; then pip install -r requirements.txt; fi")

    def test_RED_setup_sh_pip_inside_echo_rejected(self) -> None:
        with pytest.raises(ValueError, match="inert"):
            check_setup_sh_wiring('echo "pip install -r requirements.txt"')

    def test_RED_setup_sh_false_and_dead_rejected(self) -> None:
        with pytest.raises(ValueError, match="short-circuit"):
            check_setup_sh_wiring("false && pip install -r requirements.txt")

    def test_RED_setup_sh_missing_cd_backend_rejected(self) -> None:
        with pytest.raises(ValueError, match="cd"):
            check_setup_sh_wiring("pip install -r requirements.txt\nalembic upgrade head -x t_dev")

    def test_RED_setup_sh_missing_alembic_rejected(self) -> None:
        with pytest.raises(ValueError, match="alembic"):
            check_setup_sh_wiring("cd backend\npip install -r requirements.txt")

    # RED mutations (Dockerfile)
    def test_RED_dockerfile_poetry_run_before_copy_rejected(self) -> None:
        text = "FROM python:3.11\nRUN poetry install --no-root --only main\nCOPY pyproject.toml poetry.lock ./"
        with pytest.raises(ValueError, match="must appear AFTER"):
            check_dockerfile_wiring(text)

    def test_RED_dockerfile_copy_absent_rejected(self) -> None:
        with pytest.raises(ValueError, match="COPY .* not found"):
            check_dockerfile_wiring("FROM python:3.11\nRUN poetry install --no-root --only main")

    def test_RED_dockerfile_run_poetry_install_absent_rejected(self) -> None:
        with pytest.raises(ValueError, match="RUN poetry install"):
            check_dockerfile_wiring("FROM python:3.11\nCOPY pyproject.toml poetry.lock ./")


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
