"""Direct unit tests for backend/scripts/setup_preflight.py (H7-R9).

The module is imported and exercised directly — never through fake parser
outputs or the executable shell harness.  Every failure path must emit a
FIXED neutral error, and no error/log/output may ever contain a URL,
password, or Compose JSON fragment.  The asymmetric port contract enforced
here and in the module is:

  * ``target``  — exact int only (bool / float / string / Unicode digits /
    structured values all rejected).
  * ``published`` — exact int OR a *complete* ASCII ``[0-9]+`` string with no
    whitespace or trailing characters (the form Compose v2 emits for
    env-substituted published ports).  bool / float / Unicode digits /
    whitespace-bearing strings / structured values are rejected.

Other hardening: env keys strictly [A-Za-z_][A-Za-z0-9_]*; exact DB scheme
parse (no global replacement); blank DB passwords rejected; Compose root
must be a dict; malformed URL / file / JSON / non-UTF-8 → fixed neutral
errors; Redis credentials rejected (no-auth Compose Redis); process URLs
read from os.environ (never argv).
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
# unique sentinel used to prove secrets never reach argv / logs / output
SENTINEL_URL = "postgresql://sentinel:h7r7sentinel_pw@localhost:5432/sentinel"  # pragma: allowlist secret
SENTINEL_TOKEN = "h7r7sentinel_pw"

GOOD_ENV = (
    "DATABASE_URL=postgresql://pguser:pgpass@localhost:5432/pgdb\n"  # pragma: allowlist secret
    "REDIS_URL=redis://localhost:6379/0\n"
    "POSTGRES_USER=pguser\n"
    "POSTGRES_PASSWORD=pgpass\n"
    "POSTGRES_DB=pgdb\n"
    "REPORTING_USER_PASSWORD=reportingpass\n"  # pragma: allowlist secret
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
    """Build rendered-Compose JSON.  Default redis has NO environment key."""
    services = {
        "postgres": pg if pg is not None else dict(PG_SVC),
        "redis": redis if redis is not None else {"ports": [_port_entry_redis()]},
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
    for bad in (
        "pgpass", "reportingpass", "postgresql://", "redis://",
        '"host_ip"', '"published"', SENTINEL_TOKEN,
    ):
        assert bad not in err
    return err


@pytest.fixture(autouse=True)
def _clean_process_urls(monkeypatch):
    """Preflight reads DATABASE_URL/REDIS_URL/REPORTING_USER_PASSWORD from
    os.environ. Clear the host's real values so the default (non-conflict)
    cases are deterministic; tests that exercise the conflict path set them
    explicitly."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REPORTING_USER_PASSWORD", raising=False)


# ---------------------------------------------------------------------------
# URL parsers
# ---------------------------------------------------------------------------
class TestParseDbUrl:
    def test_parses_plain(self) -> None:
        assert pf.parse_db_url("postgresql://u:p@localhost:5432/db") == (
            "u", "p", "localhost", 5432, "db",
        )

    def test_parses_asyncpg_scheme_exact(self) -> None:
        # exact scheme match — no global string replacement
        assert pf.parse_db_url("postgresql+asyncpg://u:p@127.0.0.1:5432/db") == (
            "u", "p", "127.0.0.1", 5432, "db",
        )

    def test_url_decodes_credentials(self) -> None:
        assert pf.parse_db_url("postgresql://pg%40user:pa%40ss@localhost:5432/pgdb") == (  # pragma: allowlist secret
            "pg@user", "pa@ss", "localhost", 5432, "pgdb",
        )

    def test_default_port_is_5432(self) -> None:
        assert pf.parse_db_url("postgresql://u:p@localhost/db") == (
            "u", "p", "localhost", 5432, "db",
        )

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("mysql://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            ("postgres://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            ("postgresql+psycopg2://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            # global-replace bug regression: a near-scheme must NOT be normalised
            ("postgresql+asyncpgx://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            ("postgresql://:p@localhost:5432/db", "DATABASE_URL must contain a username and database"),
            ("postgresql://u:p@localhost:5432", "DATABASE_URL must contain a username and database"),
            ("postgresql://u:@localhost:5432/db", "DATABASE_URL must contain a password"),
            ("postgresql://u@localhost:5432/db", "DATABASE_URL must contain a password"),
            ("postgresql://u:p@localhost:abc/db", "DATABASE_URL has an invalid port"),
            ("postgresql://u:p@[INVALID", "DATABASE_URL is malformed"),
        ],
    )
    def test_failures_exact_and_neutral(self, capsys, url: str, expected: str) -> None:
        err = _expect_fail(capsys, pf.parse_db_url, url)
        assert err == expected
        assert url not in err


class TestParseRedisUrl:
    def test_parses(self) -> None:
        assert pf.parse_redis_url("redis://localhost:6379/0") == ("localhost", 6379)

    def test_default_port_is_6379(self) -> None:
        assert pf.parse_redis_url("redis://127.0.0.1/0") == ("127.0.0.1", 6379)

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("http://localhost:6379/0", "REDIS_URL scheme is not redis"),
            ("rediss://localhost:6379/0", "REDIS_URL scheme is not redis"),
            ("redis://localhost:abc/0", "REDIS_URL has an invalid port"),
            ("redis://:pass@localhost:6379/0", "REDIS_URL must not carry credentials (Compose Redis is no-auth)"),
            ("redis://user@localhost:6379/0", "REDIS_URL must not carry credentials (Compose Redis is no-auth)"),
            ("redis://user:pass@localhost:6379/0", "REDIS_URL must not carry credentials (Compose Redis is no-auth)"),  # pragma: allowlist secret
            ("redis://[INVALID", "REDIS_URL is malformed"),
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
            "_LEADING_UNDERSCORE=ok\nA1=ok\n\n",
        )
        d = pf.parse_env_file(p)
        assert d["DATABASE_URL"] == "postgresql://u:p@localhost:5432/db"
        assert d["REDIS_URL"] == "redis://localhost:6379/0"
        assert d["_LEADING_UNDERSCORE"] == "ok"
        assert d["A1"] == "ok"

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
            ("1KEY=postgresql://u:p@localhost:5432/db\n", "malformed .env line 1: invalid key"),
            ("KEY-NAME=postgresql://u:p@localhost:5432/db\n", "malformed .env line 1: invalid key"),
            ("KEY NAME=postgresql://u:p@localhost:5432/db\n", "malformed .env line 1: invalid key"),
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

    def test_missing_file_neutral(self, capsys, tmp_path: Path) -> None:
        err = _expect_fail(capsys, pf.parse_env_file, str(tmp_path / "nope.env"))
        assert err == "backend/.env not readable"

    def test_invalid_utf8_direct_neutral(self, capsys, tmp_path: Path) -> None:
        # invalid UTF-8 anywhere in the file → one fixed neutral error, no bytes/path
        p = tmp_path / "test.env"
        p.write_bytes(b"DATABASE_URL=postgresql://u:p@localhost:5432/db\n\xff\xfe NOT-UTF8\n")
        err = _expect_fail(capsys, pf.parse_env_file, str(p))
        assert err == "backend/.env is not valid UTF-8"
        assert b"\xff" not in err.encode() and "test.env" not in err


def test_invalid_utf8_cli_neutral(tmp_path: Path) -> None:
    """The CLI must emit the same fixed neutral error for a non-UTF-8 .env."""
    import subprocess
    env = tmp_path / ".env"
    env.write_bytes(b"DATABASE_URL=postgresql://u:p@localhost:5432/db\n\xff\xfe NOT-UTF8\n")
    res = subprocess.run(
        [sys.executable, str(_PREFLIGHT_PATH), "--env-file", str(env)],
        capture_output=True, text=False, stdin=subprocess.DEVNULL,
    )
    assert res.returncode == 1
    err = res.stderr.decode("utf-8", errors="replace").strip()
    assert err == "backend/.env is not valid UTF-8"


class TestPublishedInt:
    """Direct proof of the asymmetric published-port contract (R9).  R8 used
    ``re.match`` whose ``$`` accepts a trailing newline; ``fullmatch`` closes
    that false-acceptance."""

    @pytest.mark.parametrize("value", [5432, "5432"])
    def test_accepted(self, value) -> None:
        assert pf._published_int(value, "postgres") == 5432

    @pytest.mark.parametrize(
        "value",
        [
            "5432\n", "5432\r", "5432 ", " 5432", "\t5432", "5432\t",
            "５４３２", True, 5432.0, "abc", [5432], None,
        ],
    )
    def test_rejected_neutral(self, capsys, value) -> None:
        err = _expect_fail(capsys, pf._published_int, value, "postgres")
        assert err == "postgres port published must be an integer"


# ---------------------------------------------------------------------------
# initial mode — URL/conflict/Compose matrix (run_initial)
# ---------------------------------------------------------------------------
class TestRunInitial:
    @staticmethod
    def _env(tmp_path: Path, content: str = GOOD_ENV) -> str:
        p = tmp_path / ".env"
        # R15: auto-inject REPORTING_USER_PASSWORD for content that lacks it,
        # so existing tests that focus on other fields still pass the new
        # required-field check. Tests that explicitly verify RUP-missing write
        # the .env directly (bypassing this helper).
        if "REPORTING_USER_PASSWORD" not in content:
            content = content + "REPORTING_USER_PASSWORD=reportingpass\n"  # pragma: allowlist secret
        p.write_text(content, encoding="utf-8")
        return str(p)

    @staticmethod
    def _ok(capsys, func, *args, stdin_text: str = _compose()) -> None:
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        try:
            func(*args)
        finally:
            sys.stdin = old_stdin
        captured = capsys.readouterr()
        assert captured.out == "OK\n"
        assert captured.err == ""

    def test_ok_prints_only_ok(self, capsys, tmp_path: Path) -> None:
        self._ok(capsys, pf.run_initial, self._env(tmp_path))

    def test_ok_with_matching_process_urls_from_environ(
        self, capsys, tmp_path: Path, monkeypatch
    ) -> None:
        # process URLs come from os.environ (never argv)
        monkeypatch.setenv("DATABASE_URL", GOOD_DB_URL)
        monkeypatch.setenv("REDIS_URL", GOOD_REDIS_URL)
        self._ok(capsys, pf.run_initial, self._env(tmp_path))

    def test_ok_loopback_127_0_0_1(self, capsys, tmp_path: Path) -> None:
        content = (
            "DATABASE_URL=postgresql://pguser:pgpass@127.0.0.1:5432/pgdb\n"  # pragma: allowlist secret
            "REDIS_URL=redis://127.0.0.1:6379/0\n"
            "POSTGRES_USER=pguser\nPOSTGRES_PASSWORD=pgpass\nPOSTGRES_DB=pgdb\n"
        )
        self._ok(capsys, pf.run_initial, self._env(tmp_path, content))

    def test_ok_asyncpg_scheme(self, capsys, tmp_path: Path) -> None:
        content = (
            "DATABASE_URL=postgresql+asyncpg://pguser:pgpass@localhost:5432/pgdb\n"  # pragma: allowlist secret
            "REDIS_URL=redis://localhost:6379/0\n"
            "POSTGRES_USER=pguser\nPOSTGRES_PASSWORD=pgpass\nPOSTGRES_DB=pgdb\n"
        )
        self._ok(capsys, pf.run_initial, self._env(tmp_path, content))

    def test_ok_url_encoded_credentials_match_compose(self, capsys, tmp_path: Path) -> None:
        content = (
            "DATABASE_URL=postgresql://pg%40user:pa%40ss@localhost:5432/pgdb\n"  # pragma: allowlist secret
            "REDIS_URL=redis://localhost:6379/0\n"
        )
        pg = {
            "environment": {"POSTGRES_USER": "pg@user", "POSTGRES_PASSWORD": "pa@ss", "POSTGRES_DB": "pgdb"},  # pragma: allowlist secret
            "ports": [_port_entry()],
        }
        self._ok(capsys, pf.run_initial, self._env(tmp_path, content), stdin_text=_compose(pg=pg))

    def test_ok_real_rendered_shape_published_as_digit_string(
        self, capsys, tmp_path: Path
    ) -> None:
        # real `docker compose config --format json` emits `published` as a
        # decimal-digit string (env-var substitution) and `target` as an int;
        # integer-valued fields must be accepted.
        pg = {"environment": dict(PG_ENV_GOOD), "ports": [
            {"host_ip": "127.0.0.1", "target": 5432, "published": "5432", "protocol": "tcp", "mode": "ingress"}]}
        redis = {"ports": [
            {"host_ip": "127.0.0.1", "target": 6379, "published": "6379", "protocol": "tcp", "mode": "ingress"}]}
        self._ok(capsys, pf.run_initial, self._env(tmp_path), stdin_text=_compose(pg=pg, redis=redis))

    def test_published_trailing_newline_rejected_via_run_initial(
        self, capsys, tmp_path: Path
    ) -> None:
        """R9 RED via the complete run_initial() path (not only _published_int):
        real Compose-shaped JSON whose published string carries a trailing
        newline must be rejected with the fixed neutral error."""
        pg = {"environment": dict(PG_ENV_GOOD), "ports": [
            {"host_ip": "127.0.0.1", "target": 5432, "published": "5432\n", "protocol": "tcp", "mode": "ingress"}]}
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path), stdin_text=_compose(pg=pg),
        )
        assert err == "postgres port published must be an integer"

    def test_redis_environment_absent_is_not_a_failure(self, capsys, tmp_path: Path) -> None:
        self._ok(capsys, pf.run_initial, self._env(tmp_path))

    def test_redis_environment_dict_shapes_pass(self, capsys, tmp_path: Path) -> None:
        for redis_env in ({}, {"REDIS_PASSWORD": "redispass"}):  # pragma: allowlist secret
            redis = {"environment": redis_env, "ports": [_port_entry_redis()]}
            self._ok(capsys, pf.run_initial, self._env(tmp_path), stdin_text=_compose(redis=redis))

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("mysql://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            ("postgresql+psycopg2://u:p@localhost:5432/db", "DATABASE_URL scheme is not postgresql"),
            ("postgresql://u:p@db.example.com:5432/db", "DATABASE_URL host must be local"),
            ("postgresql://u:p@localhost:5433/db", "postgres port published mismatch"),
            ("postgresql://u:@localhost:5432/db", "DATABASE_URL must contain a password"),
        ],
    )
    def test_db_url_failures(self, capsys, tmp_path: Path, url: str, expected: str) -> None:
        content = (
            f"DATABASE_URL={url}\n"
            "REDIS_URL=redis://localhost:6379/0\n"
            "POSTGRES_USER=pguser\nPOSTGRES_PASSWORD=pgpass\nPOSTGRES_DB=pgdb\n"
        )
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path, content), stdin_text=_compose(),
        )
        assert err == expected
        assert url not in err

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("redis://redis.example.com:6379/0", "REDIS_URL host must be local"),
            ("redis://localhost:6380/0", "redis port published mismatch"),
            ("rediss://localhost:6379/0", "REDIS_URL scheme is not redis"),
            ("redis://:pw@localhost:6379/0", "REDIS_URL must not carry credentials (Compose Redis is no-auth)"),
        ],
    )
    def test_redis_url_failures(self, capsys, tmp_path: Path, url: str, expected: str) -> None:
        content = f"DATABASE_URL={GOOD_DB_URL}\nREDIS_URL={url}\nPOSTGRES_USER=pguser\nPOSTGRES_PASSWORD=pgpass\nPOSTGRES_DB=pgdb\n"
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path, content), stdin_text=_compose(),
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
            capsys, pf.run_initial, self._env(tmp_path, content), stdin_text=_compose(),
        )
        assert err == expected

    def test_process_db_conflict_from_environ(self, capsys, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("DATABASE_URL", SENTINEL_URL)
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path), stdin_text=_compose(),
        )
        assert err == "DATABASE_URL conflict: process env differs from backend/.env"
        assert SENTINEL_TOKEN not in err

    def test_process_redis_conflict_from_environ(self, capsys, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://localhost:9999/0")
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path), stdin_text=_compose(),
        )
        assert err == "REDIS_URL conflict: process env differs from backend/.env"

    def test_no_conflict_when_process_urls_unset(self, capsys, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        self._ok(capsys, pf.run_initial, self._env(tmp_path))

    def test_malformed_compose_json_neutral(self, capsys, tmp_path: Path) -> None:
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path), stdin_text="not-json{",
        )
        assert err == "Could not parse Compose JSON from stdin"

    @pytest.mark.parametrize(
        "root_json,expected",
        [
            ("[]", "Compose root is not a dict"),
            ('"a-string"', "Compose root is not a dict"),
            ("42", "Compose root is not a dict"),
        ],
    )
    def test_compose_root_not_dict(self, capsys, tmp_path: Path, root_json: str, expected: str) -> None:
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path), stdin_text=root_json,
        )
        assert err == expected

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
             "postgres port target must be an integer"),
            ({"services": {"postgres": {"ports": [_port_entry(target="abc")]}, "redis": {}}},
             "postgres port target must be an integer"),
            ({"services": {"postgres": {"ports": [_port_entry(target="5432")]}, "redis": {}}},
             "postgres port target must be an integer"),
            ({"services": {"postgres": {"ports": [_port_entry(target="5433")]}, "redis": {}}},
             "postgres port target must be an integer"),
            ({"services": {"postgres": {"ports": [_port_entry(target=5432.0)]}, "redis": {}}},
             "postgres port target must be an integer"),
            ({"services": {"postgres": {"ports": [_port_entry(target="５４３２")]}, "redis": {}}},
             "postgres port target must be an integer"),
            ({"services": {"postgres": {"ports": [_port_entry(target=[5432])]}, "redis": {}}},
             "postgres port target must be an integer"),
            ({"services": {"postgres": {"ports": [_port_entry(published=5433)]}, "redis": {}}},
             "postgres port published mismatch"),
            ({"services": {"postgres": {"ports": [_port_entry(published="5433")]}, "redis": {}}},
             "postgres port published mismatch"),
            ({"services": {"postgres": {"ports": [_port_entry(published=5432.0)]}, "redis": {}}},
             "postgres port published must be an integer"),
            ({"services": {"postgres": {"ports": [_port_entry(published=True)]}, "redis": {}}},
             "postgres port published must be an integer"),
            ({"services": {"postgres": {"ports": [_port_entry(published="abc")]}, "redis": {}}},
             "postgres port published must be an integer"),
            ({"services": {"postgres": {"ports": [_port_entry(published="５４３２")]}, "redis": {}}},
             "postgres port published must be an integer"),
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
            ({"services": {"postgres": dict(PG_SVC), "redis": {"ports": [_port_entry_redis(published="6380")]}}},
             "redis port published mismatch"),
            ({"services": {"postgres": dict(PG_SVC), "redis": {"ports": [_port_entry_redis(target="abc")]}}},
             "redis port target must be an integer"),
            ({"services": {"postgres": dict(PG_SVC), "redis": {"ports": [_port_entry_redis(target="6379")]}}},
             "redis port target must be an integer"),
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
            capsys, pf.run_initial, self._env(tmp_path), stdin_text=json.dumps(services),
        )
        assert err == expected

    @pytest.mark.parametrize(
        "services,expected",
        [
            # explicit container_name on any rendered service is rejected
            # (project isolation); the container_name value is never echoed.
            ({"services": {"postgres": {**PG_SVC, "container_name": "mpango_postgres"},
                            "redis": {"ports": [_port_entry_redis()]}}},
             "postgres declares an explicit container_name"),
            ({"services": {"postgres": dict(PG_SVC),
                            "redis": {"ports": [_port_entry_redis()], "container_name": "mpango_redis"}}},
             "redis declares an explicit container_name"),
            ({"services": {"postgres": dict(PG_SVC),
                            "redis": {"ports": [_port_entry_redis()]},
                            "backend": {"image": "x", "container_name": "mpango_backend"}}},
             "backend declares an explicit container_name"),
        ],
    )
    def test_container_name_rejected(
        self, capsys, tmp_path: Path, services: dict, expected: str
    ) -> None:
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path), stdin_text=json.dumps(services),
        )
        assert err == expected

    def test_no_container_name_passes_with_extra_services(self, capsys, tmp_path: Path) -> None:
        # multi-service compose with NO container_name on any service passes
        services = {
            "postgres": dict(PG_SVC),
            "redis": {"ports": [_port_entry_redis()]},
            "backend": {"image": "x"},
            "frontend": {"image": "y"},
        }
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps({"services": services}))
        try:
            pf.run_initial(self._env(tmp_path))
        finally:
            sys.stdin = old_stdin
        captured = capsys.readouterr()
        assert captured.out == "OK\n" and captured.err == ""

    # ---- R15: REPORTING_USER_PASSWORD required + conflict checks --------

    def test_rup_missing_fails(self, capsys, tmp_path: Path) -> None:
        """RED (R15): .env without REPORTING_USER_PASSWORD fails before any
        side effect."""
        p = tmp_path / ".env"
        p.write_text(
            "DATABASE_URL=postgresql://pguser:pgpass@localhost:5432/pgdb\n"  # pragma: allowlist secret
            "REDIS_URL=redis://localhost:6379/0\n"
            "POSTGRES_USER=pguser\nPOSTGRES_PASSWORD=pgpass\nPOSTGRES_DB=pgdb\n",
            encoding="utf-8",
        )
        err = _expect_fail(capsys, pf.run_initial, str(p), stdin_text=_compose())
        assert err == "REPORTING_USER_PASSWORD not found in backend/.env"

    def test_rup_process_env_conflict(self, capsys, tmp_path: Path, monkeypatch) -> None:
        """RED (R15): process REPORTING_USER_PASSWORD differing from .env
        fails closed before side effects."""
        monkeypatch.setenv("REPORTING_USER_PASSWORD", "different_value")
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path), stdin_text=_compose(),
        )
        assert err == "REPORTING_USER_PASSWORD conflict: process env differs from backend/.env"

    def test_rup_compose_backend_conflict(self, capsys, tmp_path: Path) -> None:
        """RED (R15): a rendered backend Compose service whose
        REPORTING_USER_PASSWORD differs from .env fails closed."""
        services = {
            "postgres": dict(PG_SVC),
            "redis": {"ports": [_port_entry_redis()]},
            "backend": {"environment": {"REPORTING_USER_PASSWORD": "wrong_value"}},  # pragma: allowlist secret
        }
        err = _expect_fail(
            capsys, pf.run_initial, self._env(tmp_path),
            stdin_text=json.dumps({"services": services}),
        )
        assert err == "REPORTING_USER_PASSWORD conflict: Compose backend differs from backend/.env"


# ---------------------------------------------------------------------------
# secret hygiene — argv never carries secrets (process URLs via os.environ)
# ---------------------------------------------------------------------------
class TestSecretHygiene:
    """A unique sentinel proves secrets reach neither argv nor logs nor output.
    The executable-harness half of this proof lives in the parity test file
    (the fake-python log captures argv); here we prove the module reads only
    from os.environ and never echoes the value."""

    def test_conflict_neutral_hides_sentinel(self, capsys, tmp_path: Path, monkeypatch) -> None:
        p = tmp_path / ".env"
        p.write_text(GOOD_ENV, encoding="utf-8")
        monkeypatch.setenv("DATABASE_URL", SENTINEL_URL)
        err = _expect_fail(capsys, pf.run_initial, str(p), stdin_text=_compose())
        assert err == "DATABASE_URL conflict: process env differs from backend/.env"
        assert SENTINEL_TOKEN not in err
        assert "sentinel" not in err.lower()

    def test_environ_is_sole_source_for_process_url(
        self, capsys, tmp_path: Path, monkeypatch
    ) -> None:
        # with process URLs unset there is no conflict even though a sentinel
        # value is unrelatedly present in argv/sys — run_initial takes no url arg
        p = tmp_path / ".env"
        p.write_text(GOOD_ENV, encoding="utf-8")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(_compose())
        try:
            pf.run_initial(str(p))
        finally:
            sys.stdin = old_stdin
        captured = capsys.readouterr()
        assert captured.out == "OK\n" and captured.err == ""


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
        _FakeCoreConfig.settings.DATABASE_URL = "postgresql://u:p@localhost:5432/db"  # pragma: allowlist secret
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
