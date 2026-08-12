"""DC-12R1-H7-R3 — fail-closed manifest parsers + full main-runtime parity.

Supersedes H7-R2. Closes the three Kilo findings (KILO-H7R2V1-001/002/003):

  * 001 — the requirements parser silently overwrote duplicate governed lines
    (last-wins dict assignment). It now rejects every duplicate normalized name.
  * 002 — the lock parser used a dict comprehension that silently overwrote
    duplicate package entries. It now validates every entry and rejects
    duplicates.
  * 003 — requirements.txt lacked an exact ``et-xmlfile`` pin even though
    ``openpyxl 3.1.5`` depends on it and ``poetry.lock`` fixes it at ``2.0.0``.
    ``et-xmlfile==2.0.0`` is now pinned, so requirements.txt and Poetry's
    main-runtime lock package set have identical normalized package names and
    exact versions (name/version parity — marker/hash equivalence is NOT
    claimed).

The parsers in this module are fail-closed by construction and are the SAME
helpers the mutation tests exercise (no parser logic is copied into tests).
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

# Direct-runtime packages governed by the H7 reconciliation.
EXPECTED = {
    "bcrypt": "4.0.1",
    "cryptography": "46.0.5",
    "openpyxl": "3.1.5",
    "et-xmlfile": "2.0.0",
    "passlib": "1.7.4",
}


# --------------------------------------------------------------------------- #
# fail-closed requirements parser (addresses KILO-H7R2V1-001)
# --------------------------------------------------------------------------- #
def parse_requirements_text(text: str) -> dict[str, str]:
    """Parse a requirements.txt body into ``{canonical_name: exact_version}``.

    Fail-closed: every non-blank, non-comment line must be a single, exact,
    non-wildcard ``==`` pin (parsed by ``packaging.requirements.Requirement``);
    URL requirements, non-exact / wildcard specifiers, trailing garbage and any
    duplicate canonical name are rejected. Last-wins overwrite is impossible.
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
                f"line {lineno}: duplicate normalized package name {name!r}: {raw!r}"
            )
        out[name] = str(spec.version)
    return out


def parse_requirements_file() -> dict[str, str]:
    return parse_requirements_text(REQUIREMENTS.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# fail-closed lock parser (addresses KILO-H7R2V1-002)
# --------------------------------------------------------------------------- #
def parse_main_lock_packages(packages: list[dict]) -> dict[str, str]:
    """Build the ``{canonical_name: version}`` map for main-runtime packages.

    Fail-closed: every entry must have a nonempty ``name``, ``version`` and
    ``groups``; any duplicate canonical name (main or not) is rejected before
    insertion, so a dict comprehension can never silently overwrite.
    """
    out: dict[str, str] = {}
    seen: set[str] = set()
    for idx, pkg in enumerate(packages):
        if not isinstance(pkg, dict):
            raise ValueError(f"lock package [{idx}]: not a mapping: {pkg!r}")
        name = pkg.get("name")
        version = pkg.get("version")
        groups = pkg.get("groups")
        if not name or not version or groups is None:
            raise ValueError(
                f"lock package [{idx}]: malformed entry (need name/version/groups): {pkg!r}"
            )
        canonical = canonicalize_name(name)
        if canonical in seen:
            raise ValueError(f"lock package [{idx}]: duplicate package name {canonical!r}")
        seen.add(canonical)
        if "main" in groups:
            out[canonical] = version
    return out


def parse_main_lock_file() -> dict[str, str]:
    data = tomllib.load(POETRY_LOCK.open("rb"))
    return parse_main_lock_packages(data.get("package", []))


def main_runtime_deltas(
    req_text: str, lock_packages: list[dict]
) -> tuple[list[str], list[str], list[str]]:
    """Return ``(missing, extra, mismatched)`` canonical names vs the main lock."""
    req = parse_requirements_text(req_text)
    main = parse_main_lock_packages(lock_packages)
    missing = sorted(set(main) - set(req))
    extra = sorted(set(req) - set(main))
    mismatch = sorted(n for n in (set(req) & set(main)) if req[n] != main[n])
    return missing, extra, mismatch


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


# --------------------------------------------------------------------------- #
# GREEN — governed versions + full main-runtime parity
# --------------------------------------------------------------------------- #
class TestH7R3ManifestParity:
    @pytest.mark.parametrize("pkg,expected", sorted(EXPECTED.items()))
    def test_requirements_txt_resolves_expected(self, pkg: str, expected: str) -> None:
        req = parse_requirements_file()
        assert req[pkg] == expected, f"requirements.txt {pkg}=={req.get(pkg)}; expected {expected}"

    @pytest.mark.parametrize("pkg,expected", sorted(EXPECTED.items()))
    def test_poetry_lock_main_resolves_expected(self, pkg: str, expected: str) -> None:
        main = parse_main_lock_file()
        assert main[pkg] == expected, f"poetry.lock main {pkg}={main.get(pkg)}; expected {expected}"

    def test_bcrypt_within_pyproject_floor_and_ceiling(self) -> None:
        spec = _pyproject_runtime_specs()["bcrypt"]
        assert _spec_satisfies(spec, "4.0.1")
        assert not _spec_satisfies(spec, "4.1.0"), "pyproject must reject bcrypt >=4.1"

    def test_cryptography_meets_security_floor(self) -> None:
        spec = _pyproject_runtime_specs()["cryptography"]
        assert _spec_satisfies(spec, "46.0.5")
        assert not _spec_satisfies(spec, "46.0.4"), "pyproject must reject cryptography 46.0.4"

    @pytest.mark.parametrize("pkg", ["bcrypt", "cryptography", "openpyxl", "passlib"])
    def test_resolved_versions_satisfy_pyproject(self, pkg: str) -> None:
        # et-xmlfile is intentionally excluded: it is a transitive dependency of
        # openpyxl (no direct pyproject spec); it is governed by the full-parity
        # and exact-version assertions instead.
        spec = _pyproject_runtime_specs()[pkg]
        assert spec is not None and _spec_satisfies(spec, parse_requirements_file()[pkg])

    def test_passlib_unchanged_at_1_7_4(self) -> None:
        assert _pyproject_runtime_specs()["passlib"] == "1.7.4"
        assert parse_requirements_file()["passlib"] == "1.7.4"
        assert parse_main_lock_file()["passlib"] == "1.7.4"

    def test_requirements_equal_poetry_main_runtime_lock(self) -> None:
        """Name+version parity: requirements.txt == Poetry main-runtime lock set."""
        req = parse_requirements_file()
        main = parse_main_lock_file()
        assert set(req) == set(main), (
            f"package-name drift missing={sorted(set(main)-set(req))} "
            f"extra={sorted(set(req)-set(main))}"
        )
        assert req == main, f"version drift: { {k: (req[k], main[k]) for k in req if req[k]!=main[k]} }"


# --------------------------------------------------------------------------- #
# GREEN — install-path wiring
# --------------------------------------------------------------------------- #
class TestH7R3InstallPathWiring:
    def test_setup_sh_consumes_requirements(self) -> None:
        assert "pip install -r requirements.txt" in SETUP_SH.read_text(encoding="utf-8")

    def test_dockerfile_consumes_poetry_and_lock(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        assert "poetry install" in text
        assert "poetry.lock" in text and "pyproject.toml" in text


# --------------------------------------------------------------------------- #
# GREEN — installed runtime reflects the reconciled manifests
# --------------------------------------------------------------------------- #
class TestH7R3InstalledRuntime:
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
        phrase = "H7-R3-round-trip-123!"
        h = ctx.hash(phrase)
        assert h.startswith("$2") and ctx.verify(phrase, h) is True
        assert ctx.verify(phrase + "x", h) is False

    def test_core_security_hash_password_and_verify_password(self) -> None:
        from core.security import hash_password, verify_password

        phrase = "OwnerSetup123!"
        h = hash_password(phrase)
        assert verify_password(phrase, h) is True
        assert verify_password("wrong-password", h) is False
        long_input = "x" * 200
        assert verify_password(long_input, hash_password(long_input)) is True

    def test_openpyxl_and_et_xmlfile_import_and_workbook(self) -> None:
        import et_xmlfile  # noqa: F401
        import openpyxl

        assert openpyxl.__version__ == "3.1.5"
        wb = openpyxl.Workbook()
        wb.active["A1"] = "h7-r3"
        assert wb.active["A1"].value == "h7-r3"

    def test_cryptography_import_and_version(self) -> None:
        import cryptography

        assert cryptography.__version__ == self._version("cryptography") == "46.0.5"

    def test_fastapi_application_imports(self) -> None:
        from fastapi import FastAPI
        from main import app  # noqa: F401

        assert isinstance(app, FastAPI)


# --------------------------------------------------------------------------- #
# RED — requirements parser must fail closed (KILO-H7R2V1-001)
# --------------------------------------------------------------------------- #
class TestH7R3RequirementsParserFailClosed:
    def test_conflicting_duplicate_requirements(self) -> None:
        text = 'bcrypt==4.0.1 ; python_version >= "3.11"\nbcrypt==5.0.0 ; python_version >= "3.11"\n'
        with pytest.raises(ValueError):
            parse_requirements_text(text)

    def test_identical_duplicate_requirements(self) -> None:
        with pytest.raises(ValueError):
            parse_requirements_text("bcrypt==4.0.1\nbcrypt==4.0.1\n")

    def test_normalized_name_collision(self) -> None:
        # et-xmlfile and et_xmlfile canonicalize to the same name
        with pytest.raises(ValueError):
            parse_requirements_text("et-xmlfile==2.0.0\net_xmlfile==1.0.0\n")

    def test_malformed_trailing_garbage(self) -> None:
        with pytest.raises(ValueError):
            parse_requirements_text("bcrypt==4.0.1 garbage\n")

    def test_non_exact_specifier_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_requirements_text("bcrypt>=4.0.1\n")

    def test_wildcard_pin_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_requirements_text("bcrypt==4.0.*\n")

    def test_url_requirement_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_requirements_text("bcrypt @ https://example.com/bcrypt.tar.gz\n")


# --------------------------------------------------------------------------- #
# RED — lock parser must fail closed (KILO-H7R2V1-002)
# --------------------------------------------------------------------------- #
class TestH7R3LockParserFailClosed:
    def test_duplicate_lock_entries_rejected(self) -> None:
        pkgs = [
            {"name": "bcrypt", "version": "4.0.1", "groups": ["main"]},
            {"name": "bcrypt", "version": "5.0.0", "groups": ["main"]},
        ]
        with pytest.raises(ValueError):
            parse_main_lock_packages(pkgs)

    def test_malformed_lock_package_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_main_lock_packages([{"name": "bcrypt", "version": "4.0.1"}])  # missing groups
        with pytest.raises(ValueError):
            parse_main_lock_packages([{"name": "bcrypt", "groups": ["main"]}])  # missing version
        with pytest.raises(ValueError):
            parse_main_lock_packages([{"version": "4.0.1", "groups": ["main"]}])  # missing name


# --------------------------------------------------------------------------- #
# RED — full main-runtime parity must detect every drift (KILO-H7R2V1-003)
# --------------------------------------------------------------------------- #
class TestH7R3ParityFailClosed:
    @staticmethod
    def _fixtures() -> tuple[str, list[dict]]:
        return REQUIREMENTS.read_text(encoding="utf-8"), tomllib.load(POETRY_LOCK.open("rb"))["package"]

    def test_missing_main_runtime_package_detected(self) -> None:
        req_text, lock = self._fixtures()
        mutated = re.sub(r"(?m)^passlib==.*\n", "", req_text)
        missing, _, _ = main_runtime_deltas(mutated, lock)
        assert "passlib" in missing

    def test_extra_main_runtime_package_detected(self) -> None:
        req_text, lock = self._fixtures()
        mutated = req_text + 'not-a-real-package==1.2.3 ; python_version >= "3.11"\n'
        _, extra, _ = main_runtime_deltas(mutated, lock)
        assert "not-a-real-package" in extra

    def test_version_mismatch_detected(self) -> None:
        req_text, lock = self._fixtures()
        mutated = req_text.replace("passlib==1.7.4", "passlib==1.7.5")
        _, _, mismatch = main_runtime_deltas(mutated, lock)
        assert "passlib" in mismatch

    def test_et_xmlfile_removal_detected(self) -> None:
        req_text, lock = self._fixtures()
        mutated = re.sub(r"(?m)^et-xmlfile==.*\n", "", req_text)
        missing, _, _ = main_runtime_deltas(mutated, lock)
        assert "et-xmlfile" in missing

    def test_et_xmlfile_version_mutation_detected(self) -> None:
        req_text, lock = self._fixtures()
        mutated = req_text.replace("et-xmlfile==2.0.0", "et-xmlfile==9.9.9")
        _, _, mismatch = main_runtime_deltas(mutated, lock)
        assert "et-xmlfile" in mismatch
