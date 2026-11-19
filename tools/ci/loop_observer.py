import asyncio, json, os, time
import pytest

_LOG = None
_CUR = {"n": 0}

def _slot():
    try:
        policy = asyncio.get_event_loop_policy()
        local = getattr(policy, "_local", None)
        loop = getattr(local, "_loop", None)
        if loop is None:
            return None
        return {"id": id(loop), "closed": bool(loop.is_closed())}
    except Exception as e:
        return {"err": type(e).__name__}

def _running():
    try:
        asyncio.get_running_loop()
        return True
    except Exception:
        return False

def rec(ev, node):
    if _LOG is not None:
        _LOG.write(json.dumps({"i": _CUR["n"], "ev": ev, "node": node,
                               "slot": _slot(), "running": _running(),
                               "t": time.time()}, ensure_ascii=False) + "\n")
        _LOG.flush()

def pytest_sessionstart(session):
    global _LOG
    _LOG = open(os.environ.get("LOOP_OBSERVER_LOG", "loop-observer.jsonl"), "a", encoding="utf-8")
    rec("session_start", "")

def pytest_sessionfinish(session):
    rec("session_end", "")
    if _LOG is not None:
        _LOG.close()

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    _CUR["n"] += 1
    rec("protocol_in", item.nodeid)
    yield
    rec("protocol_out", item.nodeid)

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    rec("setup_in", item.nodeid)
    yield
    rec("setup_out", item.nodeid)

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    rec("call_in", item.nodeid)
    yield
    rec("call_out", item.nodeid)

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    rec("teardown_in", item.nodeid)
    yield
    rec("teardown_out", item.nodeid)
