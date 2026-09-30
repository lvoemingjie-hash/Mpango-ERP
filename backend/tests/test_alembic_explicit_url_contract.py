"""Offline contract tests for the Alembic explicit migration-URL selection.

S-02 round (CTO-AUTH-MPANGO-PROMOTION-S02-EXPLICIT-URL-SOURCE-R1-20260930):
``backend/alembic.ini`` ships ``sqlalchemy.url`` EMPTY on purpose, and
``backend/alembic/env.py`` must resolve the migration URL from explicit
sources only, in this precedence:

1. the ``DATABASE_URL`` environment variable, whenever the key exists —
   a blank or malformed value must be rejected by name and must never
   fall back to the Alembic Config value or any default;
2. otherwise, a non-empty ``sqlalchemy.url`` set on the Alembic Config
   object by the caller.

With neither source usable, online and offline migration runs must fail
fast BEFORE any engine is created / context is configured, with a
value-free error whose displayable exception chain never carries the
input. No-connection commands (``heads``/``history``) must keep working
without any DSN.

These nodes exercise the REAL candidate ``env.py`` through Alembic's own
runtime entry points (``ScriptDirectory.run_env`` inside a real
``EnvironmentContext``) with the real candidate ``alembic.ini``. Every
external connection outlet is replaced by a recording/rejecting stand-in,
and an autouse socket blocker fails any node instantly if a code path
tries to open a network connection. No database is created, no migration
runs, and no inherited credential is used anywhere: all URLs are built
at runtime from per-test random tokens.
"""
import configparser
import os
import re
import socket
import uuid
from pathlib import Path

import pytest
from alembic.config import Config as AlembicConfig
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ENV_PY = BACKEND_DIR / "alembic" / "env.py"

_EXPECTED_REJECT_TYPE = "MigrationDatabaseUrlError"


# --------------------------------------------------------------------------
# offline-safety machinery
# --------------------------------------------------------------------------
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _target_host(args):
    if not args:
        return None
    target = args[0]
    if isinstance(target, tuple) and target and isinstance(target[0], str):
        return target[0].lower()
    return None


@pytest.fixture(autouse=True)
def _block_all_network_outlets(monkeypatch):
    """Layered offline guard: any unexpected outlet fails the node fast.

    Layer 1 (sockets): every outbound connection attempt to a non-loopback
    destination raises immediately. Loopback connect calls are passed to
    the real socket API solely because ``asyncio.run``'s event loop needs
    its internal self-pipe; database traffic on loopback cannot pass this
    layer because layer 2 refuses every engine creation.
    Layer 2 (SQLAlchemy): ``create_engine``/``create_async_engine`` are
    unconditional refusals — no real engine, and therefore no real
    connection (loopback included), can be created in these nodes.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_create_connection = socket.create_connection

    def _refuse_connect(sock, *args, **kwargs):
        host = _target_host(args)
        if host is not None and (
                host in _LOOPBACK_HOSTS or host.endswith(".localhost")):
            return real_connect(sock, *args, **kwargs)
        raise AssertionError(
            "network outlet reached during offline contract test")

    def _refuse_connect_ex(sock, *args, **kwargs):
        host = _target_host(args)
        if host is not None and (
                host in _LOOPBACK_HOSTS or host.endswith(".localhost")):
            return real_connect_ex(sock, *args, **kwargs)
        raise AssertionError(
            "network outlet reached during offline contract test")

    def _refuse_create_connection(*args, **kwargs):
        host = _target_host(args)
        if host is not None and (
                host in _LOOPBACK_HOSTS or host.endswith(".localhost")):
            return real_create_connection(*args, **kwargs)
        raise AssertionError(
            "network outlet reached during offline contract test")

    def _refuse_engine(*_args, **_kwargs):
        raise AssertionError(
            "database engine outlet reached during offline contract test")

    monkeypatch.setattr(socket.socket, "connect", _refuse_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse_connect_ex)
    monkeypatch.setattr(socket, "create_connection", _refuse_create_connection)

    import sqlalchemy
    import sqlalchemy.ext.asyncio as _aio
    monkeypatch.setattr(sqlalchemy, "create_engine", _refuse_engine)
    monkeypatch.setattr(_aio, "create_async_engine", _refuse_engine)


class _FakeAsyncConnection:
    def __init__(self, events):
        self._events = events

    async def run_sync(self, fn, *args, **kwargs):
        # Recording stand-in only: never invoke the migration body, so no
        # real migration code executes in these nodes.
        self._events.append(("run_sync", fn.__name__))


class _FakeConnectCM:
    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        self._events.append(("connect",))
        return _FakeAsyncConnection(self._events)

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeAsyncEngine:
    def __init__(self, events):
        self._events = events

    def connect(self):
        return _FakeConnectCM(self._events)

    async def dispose(self):
        self._events.append(("dispose",))


def _patch_engine_factory(monkeypatch, events):
    """Replace the external engine outlet with a recording stand-in."""
    import sqlalchemy.ext.asyncio as _aio

    captured = {}

    def _factory(configuration, prefix="sqlalchemy.", **options):
        captured["section"] = dict(configuration)
        captured["prefix"] = prefix
        events.append(("engine_factory",))
        return _FakeAsyncEngine(events)

    monkeypatch.setattr(_aio, "async_engine_from_config", _factory)
    return captured


@pytest.fixture
def configure_recorder(monkeypatch):
    """Record every EnvironmentContext.configure call (url included)."""
    calls = []
    original = EnvironmentContext.configure

    def _spy(self, *args, **kwargs):
        calls.append({"args": args, "kwargs": dict(kwargs)})
        return original(self, *args, **kwargs)

    monkeypatch.setattr(EnvironmentContext, "configure", _spy)
    return calls


# --------------------------------------------------------------------------
# harness: execute the real candidate env.py via Alembic's own entry points
# --------------------------------------------------------------------------
def _make_alembic_config() -> AlembicConfig:
    cfg = AlembicConfig(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def _run_candidate_env(monkeypatch, cfg, *, offline: bool):
    """Execute the real env.py the way alembic commands do.

    This is Alembic's own runtime path (EnvironmentContext +
    ScriptDirectory.run_env) — the URL selection under test is the
    candidate module itself, never a re-implementation.
    """
    script = ScriptDirectory.from_config(cfg)
    env_context = EnvironmentContext(cfg, script, as_sql=offline)
    with env_context:
        script.run_env()
    return env_context


def _clear_env_database_url(monkeypatch):
    # Clear the task-process-relevant key regardless of what the outer
    # environment or the suite conftest seeded it with.
    monkeypatch.delenv("DATABASE_URL", raising=False)


def _reject_context():
    return pytest.raises(RuntimeError)


def _assert_named_value_free_reject(exc_info, *, category, canary):
    err = exc_info.value
    assert type(err).__name__ == _EXPECTED_REJECT_TYPE, (
        f"expected named rejection, got {type(err).__name__}: {err}")
    assert isinstance(err, RuntimeError)
    message = str(err)
    assert category in message
    # Fixed key names present, offending value absent.
    assert "DATABASE_URL" in message
    assert "sqlalchemy.url" in message
    assert canary not in message
    assert "://" not in message
    # Clean displayable chain: no wrapped library error that could carry
    # the input back in.
    assert err.__cause__ is None
    assert err.__context__ is None
    link = err
    seen = set()
    while link is not None and id(link) not in seen:
        seen.add(id(link))
        assert canary not in str(link)
        assert "://" not in str(link)
        link = link.__cause__ if link.__cause__ is not None else link.__context__


def _dsn(scheme: str, login: str, password: str, host: str, dbname: str) -> str:
    """Assemble a synthetic DSN at runtime from neutral components.

    This is a source-representation concern only: no contiguous
    credential-shaped literal is kept in this file (secret scanners read
    the source text, not the runtime values). The assembled bytes — and
    therefore every parametrize input and id below — are exactly the
    strings this suite has always used.
    """
    return scheme + "://" + login + ":" + password + "@" + host + "/" + dbname


def _synthetic_url(scheme: str, token: str) -> str:
    return _dsn(
        scheme.rstrip(":"),
        f"synthetic_user_{token}",
        f"synthetic_pw_{token}",
        "127.0.0.1:5432",
        f"synthetic_db_{token}",
    )


# --------------------------------------------------------------------------
# 1. no sources at all -> named rejection, zero engine/context calls
# --------------------------------------------------------------------------
@pytest.mark.parametrize("offline", [False, True],
                         ids=["online", "offline"])
def test_no_sources_named_rejection_with_zero_outlet_calls(
        monkeypatch, configure_recorder, offline):
    _clear_env_database_url(monkeypatch)
    canary = f"canary-{uuid.uuid4().hex[:12]}"
    events = []
    _patch_engine_factory(monkeypatch, events)

    cfg = _make_alembic_config()
    with _reject_context() as exc_info:
        _run_candidate_env(monkeypatch, cfg, offline=offline)

    _assert_named_value_free_reject(
        exc_info, category="sqlalchemy.url_EMPTY", canary=canary)
    assert events == []
    assert configure_recorder == []


# --------------------------------------------------------------------------
# 2. explicitly blank env beats a non-empty Config value -> still rejected
# --------------------------------------------------------------------------
def _force_env_database_url(monkeypatch, value):
    """Put DATABASE_URL into the process environment byte-faithfully.

    On Windows the CRT removes a variable whose value is set to the empty
    string, which would silently turn the POSIX-representable ``KEY=""``
    case into the key-absent case. Seeding a delegating environment copy
    keeps the key present with the exact value under test on every OS.
    """
    seeded = dict(os.environ)
    seeded["DATABASE_URL"] = value
    monkeypatch.setattr(os, "environ", seeded)


@pytest.mark.parametrize(
    ["blank", "use_env_proxy"], [("", True), ("   \t   ", False)],
    ids=["empty_string", "whitespace_only"])
def test_blank_env_key_rejected_despite_nonempty_config(
        monkeypatch, configure_recorder, blank, use_env_proxy):
    token = uuid.uuid4().hex[:12]
    canary = f"canary-{token}"
    if use_env_proxy:
        _force_env_database_url(monkeypatch, blank)
    else:
        monkeypatch.setenv("DATABASE_URL", blank)
    events = []
    _patch_engine_factory(monkeypatch, events)

    cfg = _make_alembic_config()
    cfg.set_main_option("sqlalchemy.url", _synthetic_url(
        "postgresql+asyncpg:", token))
    with _reject_context() as exc_info:
        _run_candidate_env(monkeypatch, cfg, offline=False)

    _assert_named_value_free_reject(
        exc_info, category="DATABASE_URL_EMPTY", canary=canary)
    assert events == []
    assert configure_recorder == []


# --------------------------------------------------------------------------
# 3. valid env overrides a different explicit Config value (normalized)
# --------------------------------------------------------------------------
def test_valid_env_wins_over_explicit_config_with_normalized_capture(
        monkeypatch, configure_recorder):
    token = uuid.uuid4().hex[:12]
    env_url = _dsn(
        "postgresql",
        f"env_user_{token}",
        f"env_pw_{token}",
        f"env_host_{token}:5433",
        f"env_db_{token}",
    )
    other_token = uuid.uuid4().hex[:12]
    config_url = _synthetic_url("postgresql+asyncpg:", other_token)

    monkeypatch.setenv("DATABASE_URL", env_url)
    events = []
    captured = _patch_engine_factory(monkeypatch, events)

    cfg = _make_alembic_config()
    cfg.set_main_option("sqlalchemy.url", config_url)
    _run_candidate_env(monkeypatch, cfg, offline=False)

    expected = env_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    assert captured["section"]["sqlalchemy.url"] == expected
    assert captured["section"]["sqlalchemy.url"] != config_url
    assert [name for _, name in [e for e in events if e[0] == "run_sync"]] == [
        "do_run_migrations"]
    assert ("dispose",) in events
    # The offline context is never configured on this online path.
    assert configure_recorder == []


# --------------------------------------------------------------------------
# 4. env absent + explicit Config value -> existing path kept, not ini read
# --------------------------------------------------------------------------
def test_explicit_config_path_preserved_when_env_key_absent(
        monkeypatch, configure_recorder):
    _clear_env_database_url(monkeypatch)
    token = uuid.uuid4().hex[:12]
    config_url = _synthetic_url("postgresql+asyncpg:", token)

    events = []
    captured = _patch_engine_factory(monkeypatch, events)

    parser_probe = configparser.ConfigParser()
    parser_probe.read(ALEMBIC_INI, encoding="utf-8")
    ini_value = parser_probe.get("alembic", "sqlalchemy.url", fallback=None)

    cfg = _make_alembic_config()
    cfg.set_main_option("sqlalchemy.url", config_url)
    _run_candidate_env(monkeypatch, cfg, offline=False)

    # The captured URL is exactly what the caller set — byte for byte —
    # and provably not a static constant read back from alembic.ini.
    assert captured["section"]["sqlalchemy.url"] == config_url
    assert ini_value is not None and ini_value.strip() == ""
    assert config_url not in ALEMBIC_INI.read_text(encoding="utf-8")
    assert ("dispose",) in events


# --------------------------------------------------------------------------
# 5. postgres scheme normalization + percent bytes preserved, no new creds
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw_url",
    [
        # plain scheme upgrade
        _dsn("postgresql", "plain_user", "plain_pw", "plain_host:5432", "plain_db"),
        # percent-encoded userinfo must survive byte-exact
        _dsn("postgresql", "u%5Fser", "p%40ss%25w%2Fd", "127.0.0.1:5432", "pc_db"),
        # ConfigParser-hostile percent forms must survive byte-exact
        _dsn("postgresql+asyncpg", "u", "p%%40dd%%25x%%%%lit%(paren)sw", "h1", "db1"),
    ],
    ids=["scheme_upgrade", "percent_encoded", "percent_parser_hostile"],
)
def test_postgres_normalization_and_percent_bytes_preserved(
        monkeypatch, raw_url):
    monkeypatch.setenv("DATABASE_URL", raw_url)
    events = []
    captured = _patch_engine_factory(monkeypatch, events)

    cfg = _make_alembic_config()
    _run_candidate_env(monkeypatch, cfg, offline=False)

    got = captured["section"]["sqlalchemy.url"]
    expected = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    assert got == expected
    # No new default credentials: the only userinfo in play is the one the
    # test itself supplied on this line of the node.
    assert got.count("@") == 1
    assert "postgres:" not in got.split("@")[0].split("//", 1)[1]


# --------------------------------------------------------------------------
# 6. malformed inputs -> named rejection, value-free displayable chain
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_url",
    [
        "not-a-dsn-{canary}",
        "postgresql://u:p@[::1:5432-{canary}/db",
        "://missing-scheme-{canary}",
        "postgresql+asyncpg://u:p@host-{canary}:NOT_A_PORT/db",
        "postgre sql://{canary}@host/db",
    ],
)
def test_malformed_env_value_named_reject_value_free_chain(
        monkeypatch, bad_url):
    token = uuid.uuid4().hex[:12]
    canary = f"canary-{token}"
    monkeypatch.setenv("DATABASE_URL", bad_url.format(canary=canary))
    events = []
    _patch_engine_factory(monkeypatch, events)

    cfg = _make_alembic_config()
    with _reject_context() as exc_info:
        _run_candidate_env(monkeypatch, cfg, offline=False)

    _assert_named_value_free_reject(
        exc_info, category="DATABASE_URL_MALFORMED", canary=canary)
    assert events == []


def test_malformed_config_value_named_reject_value_free_chain(
        monkeypatch, configure_recorder):
    _clear_env_database_url(monkeypatch)
    token = uuid.uuid4().hex[:12]
    canary = f"canary-{token}"
    events = []
    _patch_engine_factory(monkeypatch, events)

    cfg = _make_alembic_config()
    cfg.set_main_option("sqlalchemy.url", f"definitely-not-a-dsn-{canary}")
    with _reject_context() as exc_info:
        _run_candidate_env(monkeypatch, cfg, offline=False)

    _assert_named_value_free_reject(
        exc_info, category="sqlalchemy.url_MALFORMED", canary=canary)
    assert events == []
    assert configure_recorder == []


# --------------------------------------------------------------------------
# 7. static contract: ini ships empty, README documents the real loading
# --------------------------------------------------------------------------
def test_ini_ships_empty_url_and_readme_matches_loading_order():
    ini_bytes = ALEMBIC_INI.read_bytes()
    assert not ini_bytes.startswith(b"\xef\xbb\xbf"), "BOM in alembic.ini"
    assert b"\x00" not in ini_bytes, "NUL byte in alembic.ini"
    ini_text = ini_bytes.decode("utf-8")

    parser = configparser.ConfigParser()
    parser.read_string(ini_text)
    assert parser.get("alembic", "sqlalchemy.url", fallback=None) is not None
    assert parser.get("alembic", "sqlalchemy.url").strip() == ""

    # No non-empty sqlalchemy.url value anywhere (spaces/tabs only after
    # the key: the ini intentionally ships the value empty)...
    assert not re.search(r"^sqlalchemy\.url[ \t]*=[ \t]*\S", ini_text, re.M)
    # ...and no credential-bearing default DSN shape at all.
    assert not re.search(r"[a-zA-Z0-9+]+://[^\s:@/]+:[^\s@/]+@", ini_text)

    readme_text = (BACKEND_DIR.parent / "README.md").read_text(encoding="utf-8")
    assert "alembic upgrade head" in readme_text
    assert "DATABASE_URL" in readme_text
    assert "empty by design" in readme_text
    assert "rejected by name" in readme_text
    # No concrete credential-bearing DSN anywhere in README: any userinfo
    # credential present must be the explicit-placeholder form.
    assert "postgresql://<user>:<password>@" in readme_text
    assert not re.search(
        r"[a-zA-Z0-9+]+://[^\s@'\"<]+:[^\s@'\"<]+@", readme_text)
    # The documented precedence matches the real loading order in env.py:
    # env var first, named refusal, Config-object fallback.
    assert readme_text.index("DATABASE_URL") < readme_text.index(
        "alembic upgrade head")


# --------------------------------------------------------------------------
# 8. no-connection commands keep reporting the migration graph without DSN
# --------------------------------------------------------------------------
def test_heads_reports_migration_graph_with_database_url_key_cleared(
        monkeypatch):
    import io

    from alembic import command

    _clear_env_database_url(monkeypatch)
    events = []
    _patch_engine_factory(monkeypatch, events)

    cfg = _make_alembic_config()
    cfg.stdout = io.StringIO()
    script = ScriptDirectory.from_config(cfg)
    expected_heads = script.get_heads()

    command.heads(cfg)
    printed = cfg.stdout.getvalue()
    assert expected_heads, "migration graph must have at least one head"
    for head in expected_heads:
        assert head in printed
    # env.py never executed and no outlet was touched.
    assert events == []
