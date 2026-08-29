"""HE2-ET1-R2 / R2-R1 mutation probes: live Redis authority weakenings.

Each mutation patches the CANDIDATE (shared Redis authority module, runner,
or child plugin) with a specific weakening and a PROBE must then report
the gate as WEAKENED (a behavior the pristine candidate rejects becomes
accepted, or a valid environment starts being rejected). Probes are
hermetic: they run against an in-process threaded fake RESP server
speaking the real wire protocol (RESP arrays with bulk-string arguments,
inline fallback), loaded from test_authority_runner_r2.

Probe contract: probe(mod, ctx) -> bool, True == gate HELD (pristine),
False == weakness ESCAPED (patched candidate misbehaves).
"""

import importlib.util
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
sys.path.insert(0, str(TESTS_DIR))
from test_authority_runner_r2 import FakeRedis, default_handlers, free_port  # noqa: E402

RUNNER_RELPATH = "harness-governance/validator/authority_runner.py"
PLUGIN_RELPATH = "harness-governance/tests/pytest_et1_collector.py"
SHARED_RELPATH = "harness-governance/validator/redis_authority.py"

INJECT_PASSWORD = "pa ss\r\nINJECT007\r\nSET x y\r\né"  # pragma: allowlist secret test fixture
DECODED_PASSWORD = "p@ss w0rd"          # percent-form: p%40ss%20w0rd  # pragma: allowlist secret test fixture
ENCODED_PASSWORD = "p%40ss%20w0rd"  # pragma: allowlist secret test fixture
ACL_USER = "acluser"


def _load_runner(runner_path=None):
    key = "et1_r2_probe_runner"
    sys.modules.pop(key, None)
    # the shared module must also reload so the patched bytes take effect
    sys.modules.pop("et1_redis_authority", None)
    spec = importlib.util.spec_from_file_location(
        key, str(runner_path or REPO_ROOT / RUNNER_RELPATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_plugin(plugin_path=None):
    key = "et1_r2_probe_plugin"
    sys.modules.pop(key, None)
    sys.modules.pop("et1_redis_authority", None)
    spec = importlib.util.spec_from_file_location(
        key, str(plugin_path or REPO_ROOT / PLUGIN_RELPATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _auth_validator(expected_args):
    def check(args):
        return b"+OK\r\n" if args == expected_args else b"-ERR fake auth\r\n"

    return check


# --- Probes (True == gate held) ----------------------------------------------


def probe_connect_deleted(mod, ctx):
    """Unreachable Redis must VOID with the sanitized connect_failed
    category; with the connect call deleted the outcome must still be a
    TrapFired (any raw exception = escape)."""
    url = f"redis://127.0.0.1:{free_port()}/15"
    try:
        mod.redis_live_check(url)
        return False  # unreachable accepted
    except mod.TrapFired as fired:
        return fired.evidence.get("redis") == "connect_failed"


def probe_ping_skipped(mod, ctx):
    handlers = default_handlers()
    handlers["PING"] = b"+WRONG\r\n"
    server = FakeRedis(handlers)
    server.start()
    try:
        try:
            mod.redis_live_check(f"redis://127.0.0.1:{server.port}/15")
            return False
        except mod.TrapFired as fired:
            return fired.evidence.get("redis") == "ping_failed"
    finally:
        server.close()


def probe_dbsize_skipped(mod, ctx):
    handlers = default_handlers()
    handlers["DBSIZE"] = b":7\r\n"
    server = FakeRedis(handlers)
    server.start()
    try:
        try:
            mod.redis_live_check(f"redis://127.0.0.1:{server.port}/15")
            return False
        except mod.TrapFired as fired:
            return fired.evidence.get("redis") == "db_nonempty"
    finally:
        server.close()


def probe_connect_errors_swallowed(mod, ctx):
    url = f"redis://127.0.0.1:{free_port()}/15"
    try:
        result = mod.redis_live_check(url)
        return result.get("redis") != "ok"
    except mod.TrapFired as fired:
        return fired.evidence.get("redis") == "connect_failed"


def probe_child_redis_recheck_deleted(mod_plugin, ctx):
    # A configured-but-unreachable Redis URL exercises the recheck itself
    # (an empty URL would early-return url_absent before the patched line).
    gate = mod_plugin.sessionstart_gate(
        {"PW1R3_TEST_REDIS_URL": f"redis://127.0.0.1:{free_port()}/15"}
    )
    problems = gate.get("problems", [])
    return any(p.startswith("redis:") for p in problems)


def probe_inline_encoder_restored(mod, ctx):
    """Credentials carrying CR/LF must travel as ONE binary-safe bulk
    argument; with the inline (space-joined) encoder restored, the payload
    splits into multiple injected commands."""
    import urllib.parse

    handlers = default_handlers()
    handlers["AUTH"] = _auth_validator([INJECT_PASSWORD])
    server = FakeRedis(handlers)
    server.start()
    try:
        encoded = urllib.parse.quote(INJECT_PASSWORD, safe="")
        try:
            result = mod.redis_live_check(
                f"redis://:{encoded}@127.0.0.1:{server.port}/15"
            )
            ok = result.get("redis") == "ok"
        except mod.TrapFired:
            ok = False
        verbs = [c[0] for c in server.commands]
        injected = "INJECT007" in verbs or "SET" in verbs
        return ok and not injected
    finally:
        server.close()


def probe_percent_decode_deleted(mod, ctx):
    """A percent-encoded password must be decoded EXACTLY before AUTH;
    without the decode the live check rejects a VALID environment."""
    handlers = default_handlers()
    handlers["AUTH"] = _auth_validator([DECODED_PASSWORD])
    server = FakeRedis(handlers)
    server.start()
    try:
        try:
            result = mod.redis_live_check(
                f"redis://:{ENCODED_PASSWORD}@127.0.0.1:{server.port}/15"
            )
            return result.get("redis") == "ok"
        except mod.TrapFired:
            return False
    finally:
        server.close()


def probe_username_ignored(mod, ctx):
    """ACL username+password must AUTH as a two-argument RESP array;
    dropping the username breaks valid ACL credentials."""
    import urllib.parse

    handlers = default_handlers()
    handlers["AUTH"] = _auth_validator([ACL_USER, DECODED_PASSWORD])
    server = FakeRedis(handlers)
    server.start()
    try:
        encoded = urllib.parse.quote(DECODED_PASSWORD, safe="")
        try:
            result = mod.redis_live_check(
                f"redis://{ACL_USER}:{encoded}@127.0.0.1:{server.port}/15"
            )
            return result.get("redis") == "ok"
        except mod.TrapFired:
            return False
    finally:
        server.close()


def probe_invalid_port_escapes(mod, ctx):
    """A malformed port must land in the sanitized url_malformed VOID —
    never escape as a raw ValueError/UnboundLocalError traceback."""
    try:
        mod.redis_live_check("redis://127.0.0.1:notaport/15")
        return False
    except mod.TrapFired as fired:
        return fired.evidence.get("redis") == "url_malformed"


def probe_child_bypasses_shared_probe(mod_plugin, ctx):
    """The child recheck must actually invoke the shared authority; a
    bypassed probe stops surfacing redis:* problems for a configured,
    unreachable Redis (the exact fail-closed signal)."""
    gate = mod_plugin.sessionstart_gate(
        {"PW1R3_TEST_REDIS_URL": f"redis://127.0.0.1:{free_port()}/15"}
    )
    problems = gate.get("problems", [])
    return any(p.startswith("redis:") for p in problems)


PROBES = {
    "connect_deleted": probe_connect_deleted,
    "ping_skipped": probe_ping_skipped,
    "dbsize_skipped": probe_dbsize_skipped,
    "connect_errors_swallowed": probe_connect_errors_swallowed,
    "child_redis_recheck_deleted": probe_child_redis_recheck_deleted,
    "inline_encoder_restored": probe_inline_encoder_restored,
    "percent_decode_deleted": probe_percent_decode_deleted,
    "username_ignored": probe_username_ignored,
    "invalid_port_escapes": probe_invalid_port_escapes,
    "child_bypasses_shared_probe": probe_child_bypasses_shared_probe,
}


# (name, target relpath, (anchor, replacement) canonical-LF patch, probe)
R2_MUTATIONS = [
    # R201-R205: the R2 set, retargeted onto the shared module (the
    # protocol code moved there in R2-R1; intents unchanged).
    (
        "R201-redis-connect-deleted", SHARED_RELPATH,
        (
            "    sock = socket.create_connection((host, port), timeout=REDIS_TIMEOUT_S)",
            "    sock = _connect_call_deleted()",
        ),
        "connect_deleted",
    ),
    (
        "R202-redis-ping-skipped", SHARED_RELPATH,
        (
            '        if _cmd(reader, sock, ("PING",)) != ("simple", "PONG"):',
            '        if False and _cmd(reader, sock, ("PING",)) != ("simple", "PONG"):',
        ),
        "ping_skipped",
    ),
    (
        "R203-redis-dbsize-skipped", SHARED_RELPATH,
        (
            '        if _cmd(reader, sock, ("DBSIZE",)) != ("int", 0):',
            '        if False and _cmd(reader, sock, ("DBSIZE",)) != ("int", 0):',
        ),
        "dbsize_skipped",
    ),
    (
        "R204-redis-connect-errors-swallowed", SHARED_RELPATH,
        (
            '        raise RedisAuthorityError("connect_failed")',
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
    # R211-R215: the R2-R1 defect mutations.
    (
        "R211-inline-encoder-restored", SHARED_RELPATH,
        (
            '    out = bytearray(b"*" + str(len(parts)).encode("ascii") + b"\\r\\n")\n'
            "    for part in parts:\n"
            '        raw = part if isinstance(part, bytes) else str(part).encode("utf-8")\n'
            '        out += b"$" + str(len(raw)).encode("ascii") + b"\\r\\n" + raw + b"\\r\\n"\n'
            "    return bytes(out)",
            '    return (" ".join(str(p) for p in parts) + "\\r\\n").encode("utf-8")',
        ),
        "inline_encoder_restored",
    ),
    (
        "R212-percent-decode-deleted", SHARED_RELPATH,
        (
            "        password = urllib.parse.unquote(parsed.password) if parsed.password else None",
            "        password = parsed.password if parsed.password else None",
        ),
        "percent_decode_deleted",
    ),
    (
        "R213-username-ignored", SHARED_RELPATH,
        (
            "            auth_args = (username, password) if username is not None else (password,)",
            "            auth_args = (password,)",
        ),
        "username_ignored",
    ),
    (
        "R214-invalid-port-escapes", SHARED_RELPATH,
        (
            '    except (ValueError, UnicodeError):\n        raise RedisAuthorityError("url_malformed")',
            '    except (ValueError, UnicodeError):\n        pass',
        ),
        "invalid_port_escapes",
    ),
    (
        "R215-child-bypasses-shared-probe", PLUGIN_RELPATH,
        (
            "        module.eval_redis(url, SENTINEL_PROBE_ENDPOINT)",
            "        pass  # shared probe bypassed",
        ),
        "child_bypasses_shared_probe",
    ),
]


def run_probe(probe_name, runner_path=None, plugin_path=None):
    """Load the (possibly patched) candidate and evaluate one probe.

    Returns True when the gate HELD and False when the weakness ESCAPED;
    any unexpected exception counts as ESCAPED (fail loud)."""
    try:
        if probe_name in ("child_redis_recheck_deleted", "child_bypasses_shared_probe"):
            mod = _load_plugin(plugin_path)
        else:
            mod = _load_runner(runner_path)
        return bool(PROBES[probe_name](mod, None))
    except Exception:
        return False
