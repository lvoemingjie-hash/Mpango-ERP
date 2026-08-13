"""Direct unit tests for backend/scripts/setup_preflight.py (H7-R5-R6).

The module is imported and exercised directly — never through fake parser
outputs or the executable shell harness.  Every failure path must emit a
FIXED neutral error, and no error may ever contain the offending URL,
password, or a Compose JSON fragment.

Compose truth (R5-R6): PostgreSQL environment must be a dict carrying the
exact required credential values; Redis environment may be absent or a
dict; both services require exactly one object-form port mapping with
host_ip=127.0.0.1, protocol=tcp, mode=ingress and exact target/published
ports.  String ports, duplicates, extra entries, missing fields, booleans,
floats and unknown structures are all rejected.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
_PREFLIGHT_PATH = BACKEND_DIR / "scripts" / "setup_preflight.py"

_spec = importlib.util.spec_from_file_location("h7_setup_preflight", _PREFLIGHT_PATH)
assert _spec is not None and _spec.loader is not None
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
GOOD_DB_URL = "postgresql://pguser:pgpass@localhost:5432/pgdb"  # pragma: allowlist secret
GOOD_REDIS_URL = "redis://localhost:6379/0"

GOOD_ENV = (
    "DATABASE_URL=postgresql://pguser:pgpass@localhost:5432/pgdb\n"  # pragma: allowlist secret
    "REDIS_URL=redis://localhost:6379/0\n"
    "POSTGRES_USER=pguser\n"
    "POSTGRES_PASSWORD=pgpass\n"
    "POSTGRES_DB=pgdb\n"
)

PG_ENV_GOOD = {"POSTGRES_USER": "pguser", "POSTGRES_PASSWORD": "pgpass", "POSTGRES_DB": "pgdb"}  # pragma: allowlist secret


def _port_entry(**overrides):
    base = {
        "host_ip": "127.0.0.1",
        "target": 5432,
        "published": 5432,
        "protocol": "tcp",
        "mode": "ingress",
    }
    base.update(overrides)
    return base


def _port_entry_redis(**overrides):
    base = {
        "host_ip": "127.0.0.1",
        "target": 6379,
        "published": 6379,
        "protocol": "tcp",
        "mode": "ingress",
    }
    base.update(overrides)
    return base


PG_SVC = {"environment": dict(PG_ENV_GOOD), "ports": [_port_entry()]}
REDIS_SVC = {"ports": [_port_entry_redis()]}


def _compose(pg=None, redis=None) -> str:
    """Build rendered-Compose JSON.  Default redis has NO environment key
    (absent is allowed per R5-R6)."""
    services = {
        "postgres": pg if pg is not None else dict(PG_SVC),
        "redis": redis
        if redis is not None
        else {"ports": [_port_entry_redis()]},
    }
    return json.dumps({"services": services})


def _expect_fail(capsys, func, *args, stdin_text: str = "") -> str:
    """Run func, expect SystemExit(1); return stderr text and assert the
    file-wide neutrality invariants (never echo values/secrets/JSON)."""
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(stdin_text)
    try:
        with pytest.raises(SystemExit) as exc:
            func(*args)
    finally:
        sys.stdin = old_stdin
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    err = captured.err.rstrip("\n")
    for bad in ("pgpass", "postgresql://", "redis://", '"host_ip"', '"published"'):
        assert bad not in err
    return err


# ---------------------------------------------------------------------------
# URL parsers
# ---------------------------------------------------------------------------
class TestParseDbUrl:
    def test_parses_plain(self) -> None:
        assert pf.parse_db_url("postgresql://u:p@localhost:5432/db") == (
            "u", "p", "localhost", "5432", "db",
        )

    def test_parses_asyncpg_scheme(self) -> None:
        assert pf.parse_db_url("postgresql+asyncpg://u:p@127.0.0.1:5432/db") == (
            "u", "p", "127.0.0.1", "5432", "db",
        )

    def test_url_decodes_credentials(self) -> None:
        # URL-decode BEFORE in-memory comparison
        assert pf.parse_db_url("postgresql://pg%40user:pa%40ss@localhost:5432/pgdb") == (  # pragma: allowlist secret
            "pg@user", "pa@ss", "localhost", "5432", "pgdb",
        )

    def test_default_port_is_5432(self) -> None:
        assert pf.parse_db_url("postgresql://u:p@localhost/db") == (
            "u", "p", "localhost", "5432", "db",
        )

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("mysql://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            ("postgres://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            ("postgresql+psycopg2://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            ("postgresql://:p@localhost:5432/db", "DATABASE_URL must contain a username and database"),
            ("postgresql://u:p@localhost:5432", "DATABASE_URL must contain a username and database"),
            ("postgresql://u:p@localhost:abc/db", "DATABASE_URL has an invalid port"),
        ],
    )
    def test_failures_exact_and_neutral(self, capsys, url: str, expected: str) -> None:
        err = _expect_fail(capsys, pf.parse_db_url, url)
        assert err == expected
        assert url not in err


class TestParseRedisUrl:
    def test_parses(self) -> None:
        assert pf.parse_redis_url("redis://localhost:6379/0") == ("localhost", "6379")

    def test_default_port_is_6379(self) -> None:
        assert pf.parse_redis_url("redis://127.0.0.1/0") == ("127.0.0.1", "6379")

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("http://localhost:6379/0", "REDIS_URL scheme is not redis"),
            ("rediss://localhost:6379/0", "REDIS_URL scheme is not redis"),
            ("redis://localhost:abc/0", "REDIS_URL has an invalid port"),
        ],
    )
    def test_failures_exact_and_neutral(self, capsys, url: str, expected: str) -> None:
        err = _expect_fail(capsys, pf.parse_redis_url, url)
        assert err == expected
        assert url not in err


# ---------------------------------------------------------------------------
# strict .env parser
# ---------------------------------------------------------------------------
class TestParseEnvFile:
    @staticmethod
    def _write(tmp_path: Path, content: str) -> str:
        p = tmp_path / "test.env"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_parses_quoted_values_comments_and_blanks(self, tmp_path: Path) -> None:
        p = self._write(
            tmp_path,
            "# comment\n"
            'DATABASE_URL="postgresql://u:p@localhost:5432/db"\n'
            "REDIS_URL='redis://localhost:6379/0'\n"
            "\n",
        )
        d = pf.parse_env_file(p)
        assert d["DATABASE_URL"] == "postgresql://u:p@localhost:5432/db"
        assert d["REDIS_URL"] == "redis://localhost:6379/0"

    @pytest.mark.parametrize(
        "content,expected",
        [
            ("export DATABASE_URL=postgresql://u:p@localhost:5432/db\n",
             "malformed .env line 1: export syntax rejected"),
            ("DATABASE_URL=postgresql://u:p@localhost:5432/db\nDATABASE_URL=postgresql://u:p@localhost:5432/db\n",
             "duplicate key in .env: DATABASE_URL"),
            ("DATABASE_URL\n", "malformed .env line 1: missing ="),
            ("DATABASE URL=postgresql://u:p@localhost:5432/db\n", "malformed .env line 1: invalid key"),
            ("DATABASE.URL=postgresql://u:p@localhost:5432/db\n", "malformed .env line 1: invalid key"),
            ("=x\n", "malformed .env line 1: invalid key"),
            ("DATABASE_URL='unclosed\n", "malformed .env line 1: unclosed quote"),
            ('DATABASE_URL="a\'\n', "malformed .env line 1: unclosed quote"),
            ('DATABASE_URL="a"b"\n', "malformed .env line 1: mismatched quotes"),
        ],
    )
    def test_failures_exact_and_neutral(self, capsys, tmp_path: Path, content: str, expected: str) -> None:
        p = self._write(tmp_path, content)
        err = _expect_fail(capsys, pf.parse_env_file, p)
        assert err == expected


# ---------------------------------------------------------------------------
# initial mode — URL/conflict/Compose matrix (run_initial)
# ---------------------------------------------------------------------------
class TestRunInitial:
    @staticmethod
    def _env(tmp_path: Path, content: str = GOOD_ENV) -> str:
        p = tmp_path / ".env"
        p.write_text(content, encoding="utf-8")
        return str(p)

    @staticmethod
    def _ok(capsys, func, *args) -> None:
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(_compose())
        try:
            func(*args)
        finally:
            sys.stdin = old_stdin
        captured = capsys.readouterr()
        assert captured.out == "OK\n"
        assert captured.err == ""

    def test_ok_prints_only_ok(self, capsys, tmp_path: Path) -> None:
        self._ok(capsys, pf.run_initial, self._env(tmp_path), "", "")

    def test_ok_with_matching_process_urls(self, capsys, tmp_path: Path) -> None:
        self._ok(capsys, pf.run_initial, self._env(tmp_path), GOOD_DB_URL, GOOD_REDIS_URL)

    def test_ok_loopback_127_0_0_1(self, capsys, tmp_path: Path) -> None:
        content = (
            "DATABASE_URL=postgresql://pguser:pgpass@127.0.0.1:5432/pgdb\n"  # pragma: allowlist secret
            "REDIS_URL=redis://127.0.0.1:6379/0\n"
            "POSTGRES_USER=pguser\nPOSTGRES_PASSWORD=pgpass\nPOSTGRES_DB=pgdb\n"
        )
        self._ok(capsys, pf.run_initial, self._env(tmp_path, content), "", "")

    def test_ok_url_encoded_credentials_match_compose(self, capsys, tmp_path: Path) -> None:
        content = (
            "DATABASE_URL=postgresql://pg%40user:pa%40ss@localhost:5432/pgdb\n"  # pragma: allowlist secret
            "REDIS_URL=redis://localhost:6379/0\n"
        )
        pg = {
            "environment": {"POSTGRES_USER": "pg@user", "POSTGRES_PASSWORD": "pa@ss", "POSTGRES_DB": "pgdb"},  # pragma: allowlist secret
            "ports": [_port_entry()],
        }
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(_compose(pg=pg))
        try:
            pf.run_initial(self._env(tmp_path, content), "", "")
        finally:
            sys.stdin = old_stdin
        captured = capsys.readouterr()
        assert captured.out == "OK\n" and captured.err == ""

    def test_redis_environment_absent_is_not_a_failure(self, capsys, tmp_path: Path) -> None:
        """Mutation removing Redis environment must NOT fail only because
        the environment is absent (default _compose has no redis env)."""
        self._ok(capsys, pf.run_initial, self._env(tmp_path), "", "")

    def test_redis_environment_dict_shapes_pass(self, capsys, tmp_path: Path) -> None:
        # empty dict and populated dict are the real rendered shapes
        for redis_env in ({}, {"REDIS_PASSWORD": "redispass"}):  # pragma: allowlist secret
            redis = {"environment": redis_env, "ports": [_port_entry_redis()]}
            old_stdin = sys.stdin
            sys.stdin = io.StringIO(_compose(redis=redis))
            try:
                pf.run_initial(self._env(tmp_path), "", "")
            finally:
                sys.stdin = old_stdin
            captured = capsys.readouterr()
            assert captured.out == "OK\n" and captured.err == ""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("mysql://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            ("postgresql+psycopg2://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            ("postgresql://u:p@db.example.com:5432/db", "DATABASE_URL host must be local"),
            ("postgresql://u:p@localhost:5433/db", "postgres port published mismatch"),
        ],
    )
    def test_db_url_failures(self, capsys, tmp_path: Path, url: str, expected: str) -> None:
        content = (
            f"DATABASE_URL={url}\n"
            "REDIS_URL=redis://localhost:6379/0\n"
            "POSTGRES_USER=pguser\nPOSTGRES_PASSWORD=pgpass\nPOSTGRES_DB=pgdb\n"
        )
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path, content), "", "",
            stdin_text=_compose(),
        )
        assert err == expected
        assert url not in err

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("redis://redis.example.com:6379/0", "REDIS_URL host must be local"),
            ("redis://localhost:6380/0", "redis port published mismatch"),
            ("rediss://localhost:6379/0", "REDIS_URL scheme is not redis"),
        ],
    )
    def test_redis_url_failures(self, capsys, tmp_path: Path, url: str, expected: str) -> None:
        content = f"DATABASE_URL={GOOD_DB_URL}\nREDIS_URL={url}\nPOSTGRES_USER=pguser\nPOSTGRES_PASSWORD=pgpass\nPOSTGRES_DB=pgdb\n"
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path, content), "", "",
            stdin_text=_compose(),
        )
        assert err == expected
        assert url not in err

    @pytest.mark.parametrize(
        "content,expected",
        [
            ("REDIS_URL=redis://localhost:6379/0\n", "DATABASE_URL not found in backend/.env"),
            ("DATABASE_URL=\nREDIS_URL=redis://localhost:6379/0\n", "DATABASE_URL not found in backend/.env"),
            ("DATABASE_URL=postgresql://pguser:pgpass@localhost:5432/pgdb\n",  # pragma: allowlist secret
             "REDIS_URL not found in backend/.env"),
        ],
    )
    def test_missing_required_urls(self, capsys, tmp_path: Path, content: str, expected: str) -> None:
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path, content), "", "",
            stdin_text=_compose(),
        )
        assert err == expected

    def test_process_db_conflict(self, capsys, tmp_path: Path) -> None:
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path),
            "postgresql://someone:else@localhost:5432/other", "",  # pragma: allowlist secret
            stdin_text=_compose(),
        )
        assert err == "DATABASE_URL conflict: process env differs from backend/.env"

    def test_process_redis_conflict(self, capsys, tmp_path: Path) -> None:
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path),
            "", "redis://localhost:9999/0",
            stdin_text=_compose(),
        )
        assert err == "REDIS_URL conflict: process env differs from backend/.env"

    @pytest.mark.parametrize(
        "services,expected",
        [
            ({"services": []}, "Compose services is not a dict"),
            ({"services": {"postgres": "x", "redis": {}}}, "postgres service is not a dict"),
            ({"services": {"postgres": {}, "redis": {}}}, "postgres ports must be a list with exactly one entry"),
            ({"services": {"postgres": {"ports": {}}, "redis": {}}}, "postgres ports must be a list with exactly one entry"),
            ({"services": {"postgres": {"ports": []}, "redis": {}}}, "postgres ports must be a list with exactly one entry"),
            ({"services": {"postgres": {"ports": [_port_entry(), _port_entry()]}, "redis": {}}},
             "postgres ports must be a list with exactly one entry"),
            ({"services": {"postgres": {"ports": ["5432:5432"]}, "redis": {}}},
             "postgres port entry must be an object (string form rejected)"),
            ({"services": {"postgres": {"ports": [{"host_ip": "127.0.0.1", "target": 5432, "published": 5432, "protocol": "tcp"}]}, "redis": {}}},
             "postgres port entry has unknown or missing fields"),
            ({"services": {"postgres": {"ports": [_port_entry(mode="host")]}, "redis": {}}},
             "postgres port mode must be ingress"),
            ({"services": {"postgres": {"ports": [_port_entry(protocol="udp")]}, "redis": {}}},
             "postgres port protocol must be tcp"),
            ({"services": {"postgres": {"ports": [_port_entry(host_ip="0.0.0.0")]}, "redis": {}}},
             "postgres host_ip must be 127.0.0.1"),
            ({"services": {"postgres": {"ports": [_port_entry(target=5433)]}, "redis": {}}},
             "postgres port target mismatch"),
            ({"services": {"postgres": {"ports": [_port_entry(target=True)]}, "redis": {}}},
             "postgres port target mismatch"),
            ({"services": {"postgres": {"ports": [_port_entry(published=5432.0)]}, "redis": {}}},
             "postgres port published mismatch"),
            ({"services": {"postgres": {"ports": [_port_entry(target=[5432])]}, "redis": {}}},
             "postgres port target mismatch"),
            ({"services": {"postgres": {"ports": [dict(_port_entry(), name="web")]}, "redis": {}}},
             "postgres port entry has unknown or missing fields"),
            ({"services": {"postgres": {"ports": [_port_entry()], "environment": "NOTADICT"}, "redis": {}}},
             "postgres environment must be a dict"),
            ({"services": {"postgres": {"ports": [_port_entry()], "environment": ["POSTGRES_USER=pguser"]}, "redis": {}}},
             "postgres environment must be a dict"),
            ({"services": {"postgres": {"ports": [_port_entry()]}, "redis": {}}},
             "postgres environment must be a dict"),
            ({"services": {"postgres": {"ports": [_port_entry()], "environment": {"POSTGRES_USER": "pguser", "POSTGRES_PASSWORD": "pgpass", "POSTGRES_DB": "other"}}, "redis": dict(REDIS_SVC)}},
             "DATABASE_URL database does not match Compose POSTGRES_DB"),
            ({"services": {"postgres": {"ports": [_port_entry()], "environment": {"POSTGRES_USER": "someone", "POSTGRES_PASSWORD": "pgpass", "POSTGRES_DB": "pgdb"}}, "redis": dict(REDIS_SVC)}},
             "DATABASE_URL username does not match Compose POSTGRES_USER"),
            ({"services": {"postgres": {"ports": [_port_entry()], "environment": {"POSTGRES_USER": "pguser", "POSTGRES_PASSWORD": "different", "POSTGRES_DB": "pgdb"}}, "redis": dict(REDIS_SVC)}},
             "DATABASE_URL password does not match Compose POSTGRES_PASSWORD"),
            ({"services": {"postgres": dict(PG_SVC), "redis": {"ports": ["6379:6379"]}}},
             "redis port entry must be an object (string form rejected)"),
            ({"services": {"postgres": dict(PG_SVC), "redis": {"ports": [_port_entry_redis(host_ip="0.0.0.0")]}}},
             "redis host_ip must be 127.0.0.1"),
            ({"services": {"postgres": dict(PG_SVC), "redis": {"ports": [_port_entry_redis(published=6380)]}}},
             "redis port published mismatch"),
            ({"services": {"postgres": dict(PG_SVC), "redis": {"ports": [_port_entry_redis(), _port_entry_redis()]}}},
             "redis ports must be a list with exactly one entry"),
            ({"services": {"postgres": dict(PG_SVC), "redis": {"ports": [_port_entry_redis()], "environment": "NOTADICT"}}},
             "redis environment must be a dict"),
            ({"services": {"postgres": dict(PG_SVC), "redis": {"ports": [_port_entry_redis()], "environment": ["REDIS_PASSWORD=x"]}}},
             "redis environment must be a dict"),
        ],
    )
    def test_compose_shape_failures_exact_and_neutral(
        self, capsys, tmp_path: Path, services: dict, expected: str
    ) -> None:
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path), "", "",
            stdin_text=json.dumps(services),
        )
        assert err == expected


# ---------------------------------------------------------------------------
# post-install mode — imports core.config only after pip
# ---------------------------------------------------------------------------
class _FakeSettings:
    DATABASE_URL = ""
    REDIS_URL = ""


class _FakeCoreConfig:
    settings = _FakeSettings()


class TestRunPostInstall:
    @staticmethod
    def _env(tmp_path: Path, content: str = GOOD_ENV) -> str:
        p = tmp_path / ".env"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_ok_when_settings_match(self, capsys, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "core.config", _FakeCoreConfig)
        _FakeCoreConfig.settings.DATABASE_URL = GOOD_DB_URL
        _FakeCoreConfig.settings.REDIS_URL = GOOD_REDIS_URL
        pf.run_post_install(self._env(tmp_path))
        captured = capsys.readouterr()
        assert captured.out == "OK\n" and captured.err == ""

    def test_db_mismatch_exact(self, capsys, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "core.config", _FakeCoreConfig)
        _FakeCoreConfig.settings.DATABASE_URL = "postgresql://u:p@localhost:5432/db"
        _FakeCoreConfig.settings.REDIS_URL = GOOD_REDIS_URL
        err = _expect_fail(capsys, pf.run_post_install, self._env(tmp_path))
        assert err == "settings.DATABASE_URL differs from backend/.env after pip install"

    def test_redis_mismatch_exact(self, capsys, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "core.config", _FakeCoreConfig)
        _FakeCoreConfig.settings.DATABASE_URL = GOOD_DB_URL
        _FakeCoreConfig.settings.REDIS_URL = "redis://localhost:9999/0"
        err = _expect_fail(capsys, pf.run_post_install, self._env(tmp_path))
        assert err == "settings.REDIS_URL differs from backend/.env after pip install"

    def test_import_failure_exact(self, capsys, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "core.config", None)
        err = _expect_fail(capsys, pf.run_post_install, self._env(tmp_path))
        assert err == "Could not import core.config.settings"

    def test_main_post_install_smoke(self, capsys, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "core.config", _FakeCoreConfig)
        _FakeCoreConfig.settings.DATABASE_URL = GOOD_DB_URL
        _FakeCoreConfig.settings.REDIS_URL = GOOD_REDIS_URL
        monkeypatch.setattr(
            sys, "argv",
            ["setup_preflight.py", "--env-file", self._env(tmp_path), "--post-install"],
        )
        pf.main()
        captured = capsys.readouterr()
        assert captured.out == "OK\n" and captured.err == ""
