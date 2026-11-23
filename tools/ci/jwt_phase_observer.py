"""Frozen-order phase timeline for the invariants-jwt leg; observation only.

Sequence numbers are NOT assigned on first sight. The plugin reads the frozen
ordered nodeid list named by JWT_FROZEN_ORDER_FILE, compares it with the
order pytest actually collected IN THIS PROCESS, and only then binds each
nodeid to its 1-based frozen position. Every line is
{"ev","n","ph","t"} with n = frozen position and t = time.monotonic() offset
from session start, appended and flushed immediately so an interrupted
session still shows the last reached phase; ends are never synthesized.

When the binding cannot be established (frozen list unavailable, duplicated
or mismatched against the collected set/order) the plugin emits a single
marker line with NO sequence numbers at all, so no line can be mistaken for a
valid frozen position. A write failure emits exactly one valueless marker
({"ev":"write_failed"}) and then stays silent; exception text is never
written or printed. The plugin never raises out of a hook, so pytest results
are unchanged. No nodeid, parameter, SQL, DSN, credential or business value
is written: nodeids live only in this process's memory.
"""
import json
import os
import time

import pytest

_OUT_ENV = "JWT_PHASE_OBSERVATION_FILE"
_FROZEN_ENV = "JWT_FROZEN_ORDER_FILE"

_PENDING, _BOUND, _REFUSED = "pending", "bound", "refused"


def _frozen_nodeids(path):
    """Mirror prepare_test_evidence._collect_nodeids: nodeid lines only."""
    raw = []
    with open(path, "r", encoding="utf-8", errors="strict") as handle:
        for line in handle:
            line = line.strip()
            if "::" in line and not line.startswith(("=", "!", "*", " ")):
                raw.append(line)
    if not raw or len(set(raw)) != len(raw):
        raise ValueError("frozen list empty or duplicated")
    return raw


class _Timeline:
    def __init__(self):
        self.handle = None
        self.path = None
        self.t0 = None
        self.mode = _PENDING
        self.index = {}
        self.dead = False

    # -- output ---------------------------------------------------------
    def _write(self, payload):
        if self.dead or self.handle is None:
            return False
        try:
            self.handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            self.handle.flush()
            return True
        except (OSError, ValueError):
            return False

    def emit(self, payload):
        if self._write(payload):
            return True
        if self.handle is None:
            # Already past the single failure marker; stay silent.
            self.dead = True
            return False
        # Exactly one valueless marker, then silence: no exception text, no
        # repeated attempts, no effect on pytest.
        self.dead = True
        try:
            self.handle.close()
        except (OSError, ValueError):
            pass
        self.handle = None
        try:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write('{"ev":"write_failed"}\n')
                handle.flush()
        except (OSError, ValueError):
            pass
        return False

    # -- lifecycle ------------------------------------------------------
    def bind(self):
        self.path = os.environ.get(_OUT_ENV)
        if not self.path:
            return
        try:
            self.handle = open(self.path, "a", encoding="utf-8")
        except OSError:
            self.handle = None
            self.dead = True
            return
        self.t0 = time.monotonic()
        self.emit({"ev": "session_start", "t": 0.0})

    def verify_order(self, collected):
        """Bind frozen positions only when collection order matches exactly."""
        if self.handle is None:
            return
        frozen_path = os.environ.get(_FROZEN_ENV)
        if not frozen_path:
            self.mode = _REFUSED
            self.emit({"ev": "binding_unavailable"})
            return
        try:
            frozen = _frozen_nodeids(frozen_path)
        except (OSError, ValueError):
            self.mode = _REFUSED
            self.emit({"ev": "binding_unavailable"})
            return
        if list(collected) != frozen:
            self.mode = _REFUSED
            self.emit({"ev": "order_mismatch"})
            return
        self.index = {nodeid: pos for pos, nodeid in enumerate(frozen, 1)}
        self.mode = _BOUND
        self.emit({"ev": "order_verified", "count": len(frozen)})

    def phase(self, nodeid, name, event):
        if self.mode is not _BOUND:
            return
        position = self.index.get(nodeid)
        if position is None:
            return
        self.emit({"ev": event, "n": position, "ph": name,
                   "t": round(time.monotonic() - self.t0, 6)})


_timeline = _Timeline()


def pytest_configure(config):
    # pytest_configure is a historic hook (wrappers are refused); binding
    # here only opens the file and fixes the monotonic epoch.
    try:
        _timeline.bind()
    except Exception:
        _timeline.handle = None
        _timeline.dead = True


def pytest_collection_finish(session):
    # In-process verification of the ACTUAL collection order.
    try:
        _timeline.verify_order([item.nodeid for item in session.items])
    except Exception:
        _timeline.mode = _REFUSED


def _phase_hook(nodeid, name, event):
    try:
        _timeline.phase(nodeid, name, event)
    except Exception:
        pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    _phase_hook(item.nodeid, "setup", "start")
    yield
    _phase_hook(item.nodeid, "setup", "end")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _phase_hook(item.nodeid, "call", "start")
    yield
    _phase_hook(item.nodeid, "call", "end")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    _phase_hook(item.nodeid, "teardown", "start")
    yield
    _phase_hook(item.nodeid, "teardown", "end")
