import asyncio
import warnings

import pytest

from tests import async_test_utils


TEST_SOURCE_URL = "postgresql://test_runner@127.0.0.1:55448/test_dc11t2_source"


def _authorize_temp_db(monkeypatch, source_url=TEST_SOURCE_URL):
    monkeypatch.setenv("MPANGO_ENV", "test")
    monkeypatch.setenv("MPANGO_ALLOW_TEMP_DB_CREATE", "1")
    monkeypatch.setenv("MPANGO_TEMP_DB_ALLOWED_PORTS", "55448")
    monkeypatch.setenv("TEST_DATABASE_URL", source_url)
    monkeypatch.delenv("MPANGO_TEMP_DB_ALLOWED_HOSTS", raising=False)


@pytest.fixture()
def isolated_event_loop():
    policy = asyncio.get_event_loop_policy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            previous = policy.get_event_loop()
        except RuntimeError:
            previous = None
    loop = policy.new_event_loop()
    policy.set_event_loop(loop)
    try:
        yield loop
    finally:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            try:
                current = policy.get_event_loop()
            except RuntimeError:
                current = None
        if current is not None and current is not previous and not current.is_closed():
            current.close()
        if previous is not None and not previous.is_closed():
            policy.set_event_loop(previous)
        else:
            policy.set_event_loop(policy.new_event_loop())


def test_run_coroutine_reuses_current_loop(isolated_event_loop):
    assert async_test_utils.run_coroutine(asyncio.sleep(0, result="ok")) == "ok"
    assert asyncio.get_event_loop() is isolated_event_loop
    assert not isolated_event_loop.is_closed()


def test_run_coroutine_replaces_closed_loop(isolated_event_loop):
    isolated_event_loop.close()
    assert async_test_utils.run_coroutine(asyncio.sleep(0, result=7)) == 7
    replacement = asyncio.get_event_loop()
    assert replacement is not isolated_event_loop
    assert not replacement.is_closed()


def test_alembic_upgrade_restores_current_loop(monkeypatch, isolated_event_loop):
    def clobber_current_loop(config, revision):
        asyncio.set_event_loop(None)

    monkeypatch.setattr(async_test_utils.command, "upgrade", clobber_current_loop)
    async_test_utils.run_alembic_upgrade(object(), "head")
    assert asyncio.get_event_loop() is isolated_event_loop


def test_alembic_downgrade_restores_current_loop(monkeypatch, isolated_event_loop):
    def clobber_current_loop(config, revision):
        asyncio.set_event_loop(None)

    monkeypatch.setattr(async_test_utils.command, "downgrade", clobber_current_loop)
    async_test_utils.run_alembic_downgrade(object(), "base")
    assert asyncio.get_event_loop() is isolated_event_loop


def test_temp_db_guard_accepts_explicit_loopback_test_source(monkeypatch):
    _authorize_temp_db(monkeypatch)

    parsed = async_test_utils._validate_temporary_database_source(TEST_SOURCE_URL)

    assert parsed.hostname == "127.0.0.1"
    assert parsed.port == 55448
    assert parsed.path == "/test_dc11t2_source"


@pytest.mark.parametrize(
    ("env_name", "env_value", "expected"),
    [
        ("MPANGO_ENV", "production", "test environment"),
        ("MPANGO_ALLOW_TEMP_DB_CREATE", "0", "explicit opt-in"),
        ("MPANGO_TEMP_DB_ALLOWED_PORTS", "55449", "port is not explicitly allowed"),
    ],
)
def test_temp_db_guard_rejects_missing_positive_authorization(
    monkeypatch, env_name, env_value, expected
):
    _authorize_temp_db(monkeypatch)
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(RuntimeError, match=expected):
        async_test_utils._validate_temporary_database_source(TEST_SOURCE_URL)


def test_temp_db_guard_rejects_source_not_matching_test_database_url(monkeypatch):
    _authorize_temp_db(monkeypatch)
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql://test_runner@127.0.0.1:55448/test_other_source",
    )

    with pytest.raises(RuntimeError, match="must match TEST_DATABASE_URL"):
        async_test_utils._validate_temporary_database_source(TEST_SOURCE_URL)


def test_temp_db_guard_rejects_nonlocal_host(monkeypatch):
    source_url = "postgresql://test_runner@db.example.invalid:55448/test_dc11t2_source"
    _authorize_temp_db(monkeypatch, source_url)

    with pytest.raises(RuntimeError, match="host is not explicitly allowed"):
        async_test_utils._validate_temporary_database_source(source_url)


def test_temp_db_guard_rejects_unmarked_database_name(monkeypatch):
    source_url = "postgresql://test_runner@127.0.0.1:55448/customer_data"
    _authorize_temp_db(monkeypatch, source_url)

    with pytest.raises(RuntimeError, match="explicit test name"):
        async_test_utils._validate_temporary_database_source(source_url)


def test_temp_db_guard_rejects_production_user(monkeypatch):
    source_url = "postgresql://mpango@127.0.0.1:55448/test_dc11t2_source"
    _authorize_temp_db(monkeypatch, source_url)

    with pytest.raises(RuntimeError, match="user is not test-safe"):
        async_test_utils._validate_temporary_database_source(source_url)


def test_temporary_database_context_refuses_without_positive_guard(monkeypatch):
    monkeypatch.setenv("MPANGO_ENV", "test")
    monkeypatch.delenv("MPANGO_ALLOW_TEMP_DB_CREATE", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="explicit opt-in"):
        with async_test_utils.temporary_database_url(TEST_SOURCE_URL, "dc11t2"):
            pytest.fail("an unauthorized temporary database was created")


def test_temporary_database_context_rejects_untrusted_prefix(monkeypatch):
    _authorize_temp_db(monkeypatch)

    with pytest.raises(RuntimeError, match="prefix is invalid"):
        with async_test_utils.temporary_database_url(TEST_SOURCE_URL, "../unsafe"):
            pytest.fail("a temporary database with an unsafe prefix was created")
