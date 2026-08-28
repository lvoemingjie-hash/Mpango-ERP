"""HE2-ET1-R2 mutation probes: live Redis authority weakenings.

Each R2 mutation patches the CANDIDATE runner or plugin with a specific
weakening of the live Redis authority and a PROBE must then report the gate
as WEAKENED (a behavior the pristine candidate rejects becomes accepted).
Probes are hermetic: the runner probes run against an in-process threaded
fake RESP server speaking real wire protocol, and the plugin probe uses an
empty environment (no PG, no Redis, no pytest child needed).

Probe contract: probe(mod, ctx) -> bool, True == gate HELD (pristine),
False == weakness ESCAPED (patched candidate accepted what it must reject).
"""

import importlib.util
import socket
import sys
import threading
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
RUNNER_RELPATH = "harness-governance/validator/authority_runner.py"
PLUGIN_RELPATH = "harness-governance/tests/pytest_et1_collector.py"


class MiniRedis(threading.Thread):
    """Threaded fake RESP server (real sockets, real wire bytes)."""

    def __init__(self, handlers):
        super().__init__(daemon=True)
        self.handlers = handlers
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.stop_flag = threading.Event()

    def run(self):
        while not self.stop_flag.is_set():
            try:
                self.sock.settimeout(0.2)
                conn, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            with conn:
                reader = conn.makefile("rb")
                while True:
                    line = reader.readline()
                    if not line:
                        break
                    verb = line.decode("utf-8", "replace").split(" ", 1)[0].strip()
                    reply = self.handlers.get(verb, b"-ERR fake\r\n")
                    if reply:
                        try:
                            conn.sendall(reply)
                        except OSError:
                            break

    def close(self):
        self.stop_flag.set()
        try:
            self.sock.close()
        except OSError:
            pass


def _default_handlers():
    return {
        "AUTH": b"+OK\r\n", "PING": b"+PONG\r\n",
        "SELECT": b"+OK\r\n", "DBSIZE": b":0\r\n", "QUIT": b"",
    }


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _load(path, key):
    sys.modules.pop(key, None)
    spec = importlib.util.spec_from_file_location(key, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Probes (True == gate held) ----------------------------------------------


def probe_connect_deleted(mod, ctx):
    """Unreachable Redis must VOID; with the connect call deleted the check
    must fail loudly (any non-TrapFired outcome = escape)."""
    url = f"redis://127.0.0.1:{_free_port()}/15"
    try:
        mod.redis_live_check(url)
        return False  # unreachable accepted
    except mod.TrapFired as fired:
        return fired.evidence.get("redis") == "connect_failed"


def probe_ping_skipped(mod, ctx):
    handlers = _default_handlers()
    handlers["PING"] = b"+WRONG\r\n"  # a server that answers PING wrongly
    server = MiniRedis(handlers)
    server.start()
    try:
        try:
            mod.redis_live_check(f"redis://127.0.0.1:{server.port}/15")
            return False  # wrong PONG accepted
        except mod.TrapFired as fired:
            return fired.evidence.get("redis") == "ping_failed"
    finally:
        server.close()


def probe_dbsize_skipped(mod, ctx):
    handlers = _default_handlers()
    handlers["DBSIZE"] = b":7\r\n"  # non-empty task DB15
    server = MiniRedis(handlers)
    server.start()
    try:
        try:
            mod.redis_live_check(f"redis://127.0.0.1:{server.port}/15")
            return False  # dirty DB15 accepted
        except mod.TrapFired as fired:
            return fired.evidence.get("redis") == "db_nonempty"
    finally:
        server.close()


def probe_connect_errors_swallowed(mod, ctx):
    url = f"redis://127.0.0.1:{_free_port()}/15"
    try:
        result = mod.redis_live_check(url)
        return result.get("redis") != "ok"  # swallowed failure reports not-ok
    except mod.TrapFired as fired:
        return fired.evidence.get("redis") == "connect_failed"


def probe_child_redis_recheck_deleted(mod_plugin, ctx):
    """The child sessionstart gate must surface redis:* problems when the
    Redis authority is unprovable; deleting the child recheck hides them."""
    gate = mod_plugin.sessionstart_gate({})  # empty env: nothing proven
    problems = gate.get("problems", [])
    return any(p.startswith("redis:") for p in problems)


PROBES = {
    "connect_deleted": probe_connect_deleted,
    "ping_skipped": probe_ping_skipped,
    "dbsize_skipped": probe_dbsize_skipped,
    "connect_errors_swallowed": probe_connect_errors_swallowed,
    "child_redis_recheck_deleted": probe_child_redis_recheck_deleted,
}


# (name, target relpath, (anchor, replacement) canonical-LF patch, probe)
R2_MUTATIONS = [
    (
        "R201-redis-connect-deleted", RUNNER_RELPATH,
        (
            "    sock = socket.create_connection((host, port), timeout=REDIS_TIMEOUT_S)",
            "    sock = _connect_call_deleted()",
        ),
        "connect_deleted",
    ),
    (
        "R202-redis-ping-skipped", RUNNER_RELPATH,
        (
            '        if _redis_cmd(reader, sock, ("PING",)) != ("simple", "PONG"):',
            '        if False and _redis_cmd(reader, sock, ("PING",)) != ("simple", "PONG"):',
        ),
        "ping_skipped",
    ),
    (
        "R203-redis-dbsize-skipped", RUNNER_RELPATH,
        (
            '        if _redis_cmd(reader, sock, ("DBSIZE",)) != ("int", 0):',
            '        if False and _redis_cmd(reader, sock, ("DBSIZE",)) != ("int", 0):',
        ),
        "dbsize_skipped",
    ),
    (
        "R204-redis-connect-errors-swallowed", RUNNER_RELPATH,
        (
            '        raise TrapFired(*REDIS_TRAP, True, {"redis": "connect_failed"})',
            '        return {"redis": "ok"}',
        ),
        "connect_errors_swallowed",
    ),
    (
        "R205-child-redis-recheck-deleted", PLUGIN_RELPATH,
        (
            "    problems.extend(_redis_recheck_problems(env))",
            "    problems.extend([])",
        ),
        "child_redis_recheck_deleted",
    ),
]


def run_probe(probe_name, runner_path=None, plugin_path=None):
    """Load the (possibly patched) candidate and evaluate one probe.

    Returns True when the gate HELD and False when the weakness ESCAPED;
    any unexpected exception counts as ESCAPED (fail loud)."""
    runner_path = Path(runner_path) if runner_path else REPO_ROOT / RUNNER_RELPATH
    plugin_path = Path(plugin_path) if plugin_path else REPO_ROOT / PLUGIN_RELPATH
    try:
        if probe_name == "child_redis_recheck_deleted":
            mod = _load(plugin_path, "et1_r2_probe_plugin")
        else:
            mod = _load(runner_path, "et1_r2_probe_runner")
        return bool(PROBES[probe_name](mod, None))
    except Exception:
        return False
