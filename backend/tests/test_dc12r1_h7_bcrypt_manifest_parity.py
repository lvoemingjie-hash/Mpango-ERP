"""DC-12R1-H7-R2 — three-package runtime manifest parity (fail-closed gate).

Authoritative manifest-parity test for the H7-R2 reconciliation of the two
backend install paths:

  * Poetry / Docker  -> ``pyproject.toml`` + ``poetry.lock``
  * setup.sh / pip   -> ``requirements.txt``

H7-R1 correctly STOPPED because bcrypt was not the only material drift: bcrypt,
cryptography and openpyxl all diverged. H7-R2 (CTO-authorized) reconciles
exactly those three and no others. This test fails closed if:

  * any of bcrypt / cryptography / openpyxl / passlib resolves to a different
    exact version across the three manifests;
  * the resolved versions fall outside the pyproject runtime constraints
    (notably bcrypt ``<4.1`` and cryptography ``>=46.0.5``);
  * setup.sh stops consuming ``requirements.txt`` or the Dockerfile stops
    consuming Poetry / the lock; or
  * the installed runtime environment disagrees with the manifests.

It is intentionally dependency-light: the static manifest gate parses the files
directly (no network, no database) so it is deterministic and runs first.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

import pytest

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
    "passlib": "1.7.4",
}


# --------------------------------------------------------------------------- #
# manifest parsing helpers
# --------------------------------------------------------------------------- #
def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_requirements() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        spec_part = re.split(r"\s*;", line.strip(), maxsplit=1)[0].strip()
        if not spec_part or spec_part.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^;\s]+)", spec_part)
        if m:
            out[_norm(m.group(1))] = m.group(2)
    return out


def _parse_lock() -> dict[str, str]:
    data = tomllib.load(POETRY_LOCK.open("rb"))
    return {_norm(p["name"]): p["version"] for p in data.get("package", [])}


def _parse_pyproject_runtime() -> dict[str, str]:
    data = tomllib.load(PYPROJECT.open("rb"))
    deps = data["tool"]["poetry"]["dependencies"]
    out: dict[str, str] = {}
    for name, spec in deps.items():
        if name == "python":
            continue
        ver = spec.get("version") if isinstance(spec, dict) else spec
        out[_norm(name)] = ver
    return out


REQ = _parse_requirements()
LOCK = _parse_lock()
PYDEPS = _parse_pyproject_runtime()


def _spec_satisfies(spec: str, version: str) -> bool:
    """True if ``version`` satisfies ``spec`` (PEP 440).

    Poetry permits a bare exact version in pyproject (e.g. ``openpyxl = "3.1.5"``
    meaning ``==3.1.5``); ``packaging.SpecifierSet`` requires an explicit operator,
    so normalize a bare version to ``==<version>`` first.
    """
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    normalized = spec.strip()
    if not re.match(r"^(==|!=|~=|>=|<=|>|<|===)", normalized):
        normalized = f"=={normalized}"
    return Version(version) in SpecifierSet(normalized)


# --------------------------------------------------------------------------- #
# static manifest gate (deterministic, no env / no DB)
# --------------------------------------------------------------------------- #
class TestH7R2ManifestParity:
    """The three authorized reconciliations must hold across all manifests."""

    @pytest.mark.parametrize("pkg,expected", sorted(EXPECTED.items()))
    def test_requirements_txt_resolves_expected(self, pkg: str, expected: str) -> None:
        assert pkg in REQ, f"{pkg!r} missing from requirements.txt (RED: openpyxl was absent pre-H7-R2)"
        assert REQ[pkg] == expected, (
            f"requirements.txt {pkg}=={REQ[pkg]}; expected {expected}"
        )

    @pytest.mark.parametrize("pkg,expected", sorted(EXPECTED.items()))
    def test_poetry_lock_resolves_expected(self, pkg: str, expected: str) -> None:
        assert pkg in LOCK, f"{pkg!r} missing from poetry.lock"
        assert LOCK[pkg] == expected, f"poetry.lock {pkg}={LOCK[pkg]}; expected {expected}"

    @pytest.mark.parametrize("pkg,expected", sorted(EXPECTED.items()))
    def test_requirements_and_lock_agree(self, pkg: str, expected: str) -> None:
        assert REQ[pkg] == LOCK[pkg] == expected, (
            f"{pkg}: requirements.txt={REQ[pkg]} lock={LOCK[pkg]} expected={expected}"
        )

    def test_bcrypt_within_pyproject_floor_and_ceiling(self) -> None:
        spec = PYDEPS["bcrypt"]
        assert _spec_satisfies(spec, "4.0.1"), f"bcrypt 4.0.1 must satisfy {spec}"
        assert not _spec_satisfies(spec, "4.1.0"), (
            "pyproject must reject bcrypt >=4.1 (passlib 1.7.4 incompatibility)"
        )

    def test_cryptography_meets_security_floor(self) -> None:
        spec = PYDEPS["cryptography"]
        assert _spec_satisfies(spec, "46.0.5"), f"cryptography 46.0.5 must satisfy {spec}"
        assert not _spec_satisfies(spec, "46.0.4"), (
            "pyproject security floor (CVE-2026-26007) must reject 46.0.4"
        )

    @pytest.mark.parametrize("pkg", ["bcrypt", "cryptography", "openpyxl", "passlib"])
    def test_resolved_versions_satisfy_pyproject(self, pkg: str) -> None:
        spec = PYDEPS[pkg]
        assert spec is not None, f"{pkg} not a direct pyproject dependency"
        assert _spec_satisfies(spec, REQ[pkg]), (
            f"requirements.txt {pkg}=={REQ[pkg]} violates pyproject {spec}"
        )

    def test_passlib_unchanged_at_1_7_4(self) -> None:
        assert PYDEPS["passlib"] == "1.7.4"
        assert REQ["passlib"] == "1.7.4"
        assert LOCK["passlib"] == "1.7.4"


class TestH7R2InstallPathWiring:
    """The two install paths must still consume their authoritative manifests."""

    def test_setup_sh_consumes_requirements(self) -> None:
        text = SETUP_SH.read_text(encoding="utf-8")
        assert "pip install -r requirements.txt" in text, (
            "setup.sh must install from requirements.txt (pip install path)"
        )

    def test_dockerfile_consumes_poetry_and_lock(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        assert "poetry install" in text, "Dockerfile must install via Poetry (lock path)"
        # The lock + pyproject must be copied so `poetry install` is lock-bound.
        assert "poetry.lock" in text and "pyproject.toml" in text, (
            "Dockerfile must COPY pyproject.toml + poetry.lock for a lock-bound install"
        )


# --------------------------------------------------------------------------- #
# installed-runtime gate (defense in depth; reflects the running environment)
# --------------------------------------------------------------------------- #
class TestH7R2InstalledRuntime:
    """The running environment must match the reconciled manifests."""

    @staticmethod
    def _version(pkg: str) -> str:
        from importlib.metadata import version

        return version(pkg)

    @pytest.mark.parametrize("pkg,expected", sorted(EXPECTED.items()))
    def test_installed_version_matches_manifest(self, pkg: str, expected: str) -> None:
        assert self._version(pkg) == expected, (
            f"installed {pkg}={self._version(pkg)}; manifest expects {expected}"
        )

    def test_passlib_bcrypt_hash_verify_round_trip(self) -> None:
        from passlib.context import CryptContext

        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        phrase = "H7-R2-round-trip-123!"
        h = ctx.hash(phrase)
        assert h != phrase and h.startswith("$2")  # bcrypt hash family
        assert ctx.verify(phrase, h) is True
        assert ctx.verify(phrase + "x", h) is False

    def test_core_security_hash_password_and_verify_password(self) -> None:
        from core.security import hash_password, verify_password

        phrase = "OwnerSetup123!"
        h = hash_password(phrase)
        assert verify_password(phrase, h) is True
        assert verify_password("wrong-password", h) is False
        # 72-byte truncation contract is preserved (no bcrypt error on long input).
        long_input = "x" * 200
        h2 = hash_password(long_input)
        assert verify_password(long_input, h2) is True

    def test_openpyxl_import_and_workbook(self) -> None:
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "h7-r2"
        assert ws["A1"].value == "h7-r2"

    def test_cryptography_import_and_version(self) -> None:
        import cryptography

        assert self._version("cryptography") == cryptography.__version__ == "46.0.5"

    def test_fastapi_application_imports(self) -> None:
        from main import app  # noqa: F401  — import is the assertion

        from fastapi import FastAPI

        assert isinstance(app, FastAPI)
