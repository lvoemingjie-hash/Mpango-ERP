"""HE2-ET1-R2 unit tests: live Redis authority + child recheck (14 tests).

A threaded fake RESP server provides REAL socket conversations (not mocks of
our code) so every truth node is exercised against actual wire behavior:
PONG/OK/:0 replies, wrong PING replies, -ERR SELECT, non-zero DBSIZE,
connection refusal, sentinel reachability (patched probe endpoint), and the
AUTH flow. Credential redaction is asserted over evidence and exception text.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import threading
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
GOV_DIR = REPO_ROOT / "harness-governance"
RUNNER_PATH = GOV_DIR / "validator" / "authority_runner.py"
PLUGIN_PATH = GOV_DIR / "tests" / "pytest_et1_collector.py"
REGISTRY_PATH = GOV_DIR / "inventory" / "execution-traps.json"
VALIDATOR_PATH = GOV_DIR / "validator" / "harness_governance_validator.py"

SECRET = "R2-Redis-Password-DO-NOT-LEAK"  # pragma: allowlist secret test fixture


def _load(path, key):
    spec = importlib.util.spec_from_file_location(key, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRedis(threading.Thread):
    """Minimal RESP server: handlers map VERB -> reply bytes (callable ok)."""

    def __init__(self, handlers):
        super().__init__(daemon=True)
        self.handlers = handlers
        self.received = []
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
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
                    arg = line.decode("utf-8", "replace")[len(verb):].strip()
                    self.received.append((verb, arg))
                    reply = self.handlers.get(verb)
                    if callable(reply):
                        reply = reply(arg)
                    if reply is None:
                        reply = b"-ERR fake\r\n"
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


def default_handlers():
    return {
        "AUTH": b"+OK\r\n",
        "PING": b"+PONG\r\n",
        "SELECT": b"+OK\r\n",
        "DBSIZE": b":0\r\n",
        "QUIT": b"",
    }


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class RunnerRedisTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = _load(RUNNER_PATH, "he2et1_r2_runner")

    def _trap_category(self, url):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self.runner.redis_live_check(url)
        evidence = json.dumps(ctx.exception.evidence)
        self.assertNotIn(SECRET, evidence)
        self.assertNotIn(SECRET, str(ctx.exception))
        return ctx.exception.evidence.get("redis")

    def test_green_live_db15_probe_passes(self):
        server = FakeRedis(default_handlers())
        server.start()
        try:
            result = self.runner.redis_live_check(
                f"redis://:{SECRET}@127.0.0.1:{server.port}/15"
            )
            self.assertEqual(result["redis"], "ok")
            self.assertTrue(result["ping_pong"] and result["selected_db15"])
            self.assertTrue(result["dbsize_zero"])
            self.assertTrue(result["auth_used"])
            self.assertIn(("AUTH", SECRET), server.received)
        finally:
            server.close()

    def test_absent_url_traps_url_absent(self):
        self.assertEqual(self._trap_category(""), "url_absent")

    def test_malformed_url_traps_url_malformed(self):
        self.assertEqual(self._trap_category("not-a-redis-url"), "url_malformed")
        self.assertEqual(self._trap_category("http://127.0.0.1/15"), "url_malformed")

    def test_wrong_db_traps_before_any_connection(self):
        server = FakeRedis(default_handlers())
        server.start()
        try:
            self.assertEqual(
                self._trap_category(f"redis://127.0.0.1:{server.port}/0"), "wrong_db"
            )
            self.assertEqual(server.received, [])  # no wire traffic at all
        finally:
            server.close()

    def test_unreachable_redis_traps_connect_failed(self):
        self.assertEqual(
            self._trap_category(f"redis://127.0.0.1:{free_port()}/15"), "connect_failed"
        )

    def test_ping_not_pong_traps_ping_failed(self):
        handlers = default_handlers()
        handlers["PING"] = b"+WRONG\r\n"
        server = FakeRedis(handlers)
        server.start()
        try:
            self.assertEqual(
                self._trap_category(f"redis://127.0.0.1:{server.port}/15"), "ping_failed"
            )
        finally:
            server.close()

    def test_select_error_traps_select_failed(self):
        handlers = default_handlers()
        handlers["SELECT"] = b"-ERR invalid DB index\r\n"
        server = FakeRedis(handlers)
        server.start()
        try:
            self.assertEqual(
                self._trap_category(f"redis://127.0.0.1:{server.port}/15"), "select_failed"
            )
        finally:
            server.close()

    def test_nonempty_db15_traps_db_nonempty(self):
        handlers = default_handlers()
        handlers["DBSIZE"] = b":5\r\n"
        server = FakeRedis(handlers)
        server.start()
        try:
            self.assertEqual(
                self._trap_category(f"redis://127.0.0.1:{server.port}/15"), "db_nonempty"
            )
        finally:
            server.close()

    def test_bad_auth_traps_auth_failed_without_leaking_secret(self):
        handlers = default_handlers()
        handlers["AUTH"] = b"-WRONGPASS\r\n"
        server = FakeRedis(handlers)
        server.start()
        try:
            self.assertEqual(
                self._trap_category(f"redis://:{SECRET}@127.0.0.1:{server.port}/15"),
                "auth_failed",
            )
        finally:
            server.close()

    def test_eval_redis_traps_when_sentinel_reachable(self):
        sentinel = socket.socket()
        sentinel.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sentinel.bind(("127.0.0.1", 0))
        sentinel.listen(1)
        server = FakeRedis(default_handlers())
        server.start()
        original_endpoint = self.runner.SENTINEL_PROBE_ENDPOINT
        self.runner.SENTINEL_PROBE_ENDPOINT = ("127.0.0.1", sentinel.getsockname()[1])
        try:
            with self.assertRaises(self.runner.TrapFired) as ctx:
                self.runner.eval_redis(f"redis://127.0.0.1:{server.port}/15")
            self.assertEqual(ctx.exception.evidence.get("redis"), "sentinel_reachable")
        finally:
            self.runner.SENTINEL_PROBE_ENDPOINT = original_endpoint
            sentinel.close()
            server.close()

    def test_eval_redis_green_when_sentinel_unreachable(self):
        server = FakeRedis(default_handlers())
        server.start()
        original_endpoint = self.runner.SENTINEL_PROBE_ENDPOINT
        self.runner.SENTINEL_PROBE_ENDPOINT = ("127.0.0.1", free_port())
        try:
            result = self.runner.eval_redis(f"redis://127.0.0.1:{server.port}/15")
            self.assertEqual(result["redis"], "ok")
            self.assertFalse(result["sentinel_26379"])
        finally:
            self.runner.SENTINEL_PROBE_ENDPOINT = original_endpoint
            server.close()

    def test_credentials_never_in_any_published_payload(self):
        handlers = default_handlers()
        handlers["PING"] = b"+NOPE\r\n"
        server = FakeRedis(handlers)
        server.start()
        runner2 = _load(RUNNER_PATH, "he2et1_r2_runner_leak")
        try:
            with self.assertRaises(runner2.TrapFired) as ctx:
                runner2.redis_live_check(f"redis://:{SECRET}@127.0.0.1:{server.port}/15")
            blob = json.dumps(
                {"evidence": ctx.exception.evidence, "exc": str(ctx.exception),
                 "trap": ctx.exception.trap_id, "phase": ctx.exception.phase}
            )
            self.assertNotIn(SECRET, blob)
            self.assertNotIn("127.0.0.1", blob)  # hosts never published either
        finally:
            server.close()


class ChildRecheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = _load(PLUGIN_PATH, "he2et1_r2_plugin")

    def test_child_recheck_absent_url(self):
        self.assertEqual(self.plugin._redis_recheck_problems({}), ["redis:url_absent"])
        self.assertEqual(
            self.plugin._redis_recheck_problems({"PW1R3_TEST_REDIS_URL": "  "}),
            ["redis:url_absent"],
        )

    def test_child_recheck_unreachable_and_green_paths(self):
        problems = self.plugin._redis_recheck_problems(
            {"PW1R3_TEST_REDIS_URL": f"redis://127.0.0.1:{free_port()}/15"}
        )
        self.assertEqual(problems, ["redis:unreachable"])
        server = FakeRedis(default_handlers())
        server.start()
        original_endpoint = self.plugin.SENTINEL_PROBE_ENDPOINT
        self.plugin.SENTINEL_PROBE_ENDPOINT = ("127.0.0.1", free_port())
        try:
            url = f"redis://:{SECRET}@127.0.0.1:{server.port}/15"
            self.assertEqual(self.plugin._redis_recheck_problems(
                {"PW1R3_TEST_REDIS_URL": url}), [])
            gate = self.plugin.sessionstart_gate({
                "PW1R3_TEST_REDIS_URL": url,
                "ET1_RUNNER_PROOF_OUT": "x", "ET1_RUNNER_NONCE": "n" * 32,
                "ET1_RUNNER_CANDIDATE_SHA": "c" * 40, "ET1_RUNNER_PROFILE_SHA": "p" * 64,
                "ET1_RUNNER_MANIFEST_SHA": "m" * 64, "ET1_RUNNER_REQUIRED_NODES": "a",
                "ET1_RUNNER_PROFILE_PATH": "p", "ET1_RUNNER_MANIFEST_PATH": "m",
                "ET1_RUNNER_REPO_ROOT": ".",
            })
            self.assertNotIn("redis:url_absent", gate["problems"])
            self.assertFalse(any(p.startswith("redis:") for p in gate["problems"]))
        finally:
            self.plugin.SENTINEL_PROBE_ENDPOINT = original_endpoint
            server.close()


class RegistryContractTests(unittest.TestCase):
    def test_trap_registered_p1_active_live_evaluator(self):
        with open(REGISTRY_PATH, encoding="utf-8") as fh:
            registry = json.load(fh)
        trap = next(
            t for t in registry["traps"] if t["trap_id"] == "TRAP_REDIS_WRONG_DB"
        )
        runner = _load(RUNNER_PATH, "he2et1_r2_registry_runner")
        self.assertEqual(trap["risk"], "P1")
        self.assertEqual(trap["status"], "ACTIVE")
        self.assertEqual(trap["evaluator_id"], "EVAL_REDIS_LIVE")
        self.assertIn("EVAL_REDIS_LIVE", runner.EVALUATOR_WHITELIST)
        self.assertIn("child.sessionstart", trap["applies_to"])
        self.assertTrue(any("PING" in e for e in trap["required_evidence"]))
        self.assertTrue(any("DBSIZE" in e for e in trap["required_evidence"]))
        self.assertTrue(any("credentials" in e for e in trap["required_evidence"]))
        validator_text = VALIDATOR_PATH.read_text(encoding="utf-8")
        self.assertIn('"EVAL_REDIS_LIVE"', validator_text)
        # the trap cannot be disabled via config: profile still references it
        with open(GOV_DIR / "inventory" / "authority-profiles.json", encoding="utf-8") as fh:
            profiles = json.load(fh)
        self.assertIn(
            "TRAP_REDIS_WRONG_DB", profiles["profiles"][0]["required_traps"]
        )


if __name__ == "__main__":
    unittest.main()
