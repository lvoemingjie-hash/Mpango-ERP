import asyncio
import warnings

import pytest

from tests import async_test_utils


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
