"""Frozen-order phase timeline for the invariants-jwt leg; observation only.

Appends one JSON line per setup/call/teardown start and end to the file named
by JWT_PHASE_OBSERVATION_FILE: {"ev","n","ph","t"} where n is the 1-based
frozen sequence number and t is the time.monotonic() offset from session
start. Lines are flushed immediately, so an interrupted session still shows
the last reached phase; ends are never synthesized for phases that did not
finish. No nodeid, parameter, SQL, DSN, credential or business value is ever
written: nodeids live only in this process's memory. When the environment
variable is unset the plugin stays silent and writes nothing.
"""
import json
import os
import time

import pytest

_ENV = "JWT_PHASE_OBSERVATION_FILE"


class _Timeline:
    def __init__(self):
        self.handle = None
        self.t0 = None
        self.order = {}
        self.write_errors = 0

    def bind(self):
        path = os.environ.get(_ENV)
        if not path:
            return
        self.handle = open(path, "a", encoding="utf-8")
        self.t0 = time.monotonic()
        self._emit({"ev": "session_start", "t": 0.0})

    def _emit(self, payload):
        if self.handle is None:
            return
        try:
            self.handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            self.handle.flush()
        except OSError:
            self.handle = None
            self.write_errors += 1

    def phase(self, nodeid, name, event):
        if self.handle is None:
            return
        number = self.order.get(nodeid)
        if number is None:
            number = len(self.order) + 1
            self.order[nodeid] = number
        self._emit({"ev": event, "n": number, "ph": name,
                    "t": round(time.monotonic() - self.t0, 6)})


_timeline = _Timeline()


def pytest_configure(config):
    # Plain (non-wrapper) implementation: pytest_configure is a historic
    # hook, so wrappers are refused; binding here only opens the file and
    # fixes the monotonic epoch before any test phase runs.
    try:
        _timeline.bind()
    except OSError:
        _timeline.handle = None
        _timeline.write_errors += 1


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    _timeline.phase(item.nodeid, "setup", "start")
    yield
    _timeline.phase(item.nodeid, "setup", "end")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _timeline.phase(item.nodeid, "call", "start")
    yield
    _timeline.phase(item.nodeid, "call", "end")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    _timeline.phase(item.nodeid, "teardown", "start")
    yield
    _timeline.phase(item.nodeid, "teardown", "end")


@pytest.hookimpl(hookwrapper=True)
def pytest_sessionfinish(session, exitstatus):
    yield
    # Bonus line only; readability never depends on it because every phase
    # line above is flushed the moment it is appended.
    if _timeline.handle is not None:
        _timeline._emit({"ev": "session_finish_observed",
                         "t": round(time.monotonic() - _timeline.t0, 6),
                         "write_errors": _timeline.write_errors})
