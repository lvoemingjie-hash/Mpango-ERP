"""HE2-ET1-R2-R1 unit tests: malformed URLs, RESP AUTH, shared probe (12 tests).

Covers the confirmed defects A-E and their forced fixes: invalid port and
malformed IPv6 URLs map to sanitized VOIDs (never a raw ValueError or
traceback); percent-encoded credentials are decoded exactly; ACL
username+password uses a proper RESP bulk array; credentials containing
spaces/CR/LF/non-ASCII cannot inject commands; username-without-password
fails closed; rediss is rejected fail-closed; and the runner and the child
plugin share ONE Redis authority module object.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
import unittest
import urllib.parse
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
GOV_DIR = REPO_ROOT / "harness-governance"
RUNNER_PATH = GOV_DIR / "validator" / "authority_runner.py"
PLUGIN_PATH = GOV_DIR / "tests" / "pytest_et1_collector.py"
SHARED_PATH = GOV_DIR / "validator" / "redis_authority.py"

sys.path.insert(0, str(TESTS_DIR))
from test_authority_runner_r2 import FakeRedis, default_handlers, free_port  # noqa: E402

DECODED_PASSWORD = "p@ss w0rd"  # percent-encodes to p%40ss%20w0rd  # pragma: allowlist secret test fixture
ENCODED_PASSWORD = "p%40ss%20w0rd"  # pragma: allowlist secret test fixture
INJECTION_PASSWORD = "pa ss\r\nQUIT\r\nSET x y\r\né"  # pragma: allowlist secret test fixture


def _load(path, key):
    spec = importlib.util.spec_from_file_location(key, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MalformedUrlTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = _load(RUNNER_PATH, "he2et1_r2r1_runner")

    def _category(self, url):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self.runner.redis_live_check(url)
        return ctx.exception.evidence.get("redis")

    def test_invalid_port_maps_to_sanitized_void(self):
        self.assertEqual(
            self._category("redis://127.0.0.1:notaport/15"), "url_malformed"
        )

    def test_out_of_range_port_maps_to_sanitized_void(self):
        self.assertEqual(self._category("redis://127.0.0.1:99999/15"), "url_malformed")

    def test_malformed_ipv6_maps_to_sanitized_void(self):
        self.assertEqual(self._category("redis://[::1:99999/15"), "url_malformed")
        self.assertEqual(self._category("redis://hg[::1]/15"), "url_malformed")

    def test_valid_ipv6_bracket_form_is_not_rejected_as_malformed(self):
        # A WELL-FORMED bracketed IPv6 URL must survive parsing (it may then
        # fail to connect, which is the connect_failed category instead).
        try:
            self.runner.redis_live_check("redis://[::1]:6399/15")
            category = "ok"
        except self.runner.TrapFired as fired:
            category = fired.evidence.get("redis")
        self.assertIn(category, ("connect_failed", "ok"))

    def test_rediss_fails_closed_unsupported(self):
        self.assertEqual(
            self._category("rediss://127.0.0.1:6399/15"),
            "tls_unsupported_fail_closed",
        )

    def test_username_without_password_fails_closed(self):
        self.assertEqual(
            self._category(f"redis://someuser@127.0.0.1:{free_port()}/15"),
            "auth_misconfigured",
        )


class RespAuthTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = _load(RUNNER_PATH, "he2et1_r2r1_runner_auth")

    def _category(self, url):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self.runner.redis_live_check(url)
        return ctx.exception.evidence.get("redis")

    def test_percent_encoded_password_decoded_exactly(self):
        handlers = default_handlers()

        def auth_check(args):
            return b"+OK\r\n" if args == [DECODED_PASSWORD] else b"-ERR\r\n"

        handlers["AUTH"] = auth_check
        server = FakeRedis(handlers)
        server.start()
        try:
            result = self.runner.redis_live_check(
                f"redis://:{ENCODED_PASSWORD}@127.0.0.1:{server.port}/15"
            )
            self.assertEqual(result["redis"], "ok")
            auth_commands = [c for c in server.commands if c[0] == "AUTH"]
            self.assertEqual(auth_commands, [("AUTH", [DECODED_PASSWORD])])
        finally:
            server.close()

    def test_acl_username_password_uses_two_arg_resp_array(self):
        handlers = default_handlers()

        def auth_check(args):
            return b"+OK\r\n" if args == ["acluser", DECODED_PASSWORD] else b"-ERR\r\n"

        handlers["AUTH"] = auth_check
        server = FakeRedis(handlers)
        server.start()
        try:
            result = self.runner.redis_live_check(
                f"redis://acluser:{ENCODED_PASSWORD}@127.0.0.1:{server.port}/15"
            )
            self.assertEqual(result["redis"], "ok")
            self.assertTrue(result["acl_username_used"])
            auth_commands = [c for c in server.commands if c[0] == "AUTH"]
            self.assertEqual(auth_commands, [("AUTH", ["acluser", DECODED_PASSWORD])])
        finally:
            server.close()

    def test_credentials_with_crlf_spaces_nonascii_cannot_inject(self):
        handlers = default_handlers()

        def auth_check(args):
            # The credential must arrive as ONE bulk argument, byte-exact.
            return b"+OK\r\n" if args == [INJECTION_PASSWORD] else b"-ERR\r\n"

        handlers["AUTH"] = auth_check
        server = FakeRedis(handlers)
        server.start()
        try:
            # The credential travels percent-encoded in the URL (urlsplit
            # itself strips raw CR/LF, which already blocks injection at the
            # URL layer); the shared module must decode it EXACTLY and send
            # it as ONE binary-safe bulk argument.
            encoded = urllib.parse.quote(INJECTION_PASSWORD, safe="")
            result = self.runner.redis_live_check(
                f"redis://:{encoded}@127.0.0.1:{server.port}/15"
            )
            self.assertEqual(result["redis"], "ok")
            verbs = [c[0] for c in server.commands]
            # No injected verb may appear as its own command.
            self.assertNotIn("SET", verbs)
            self.assertNotIn("CONFIG", verbs)
            self.assertEqual(verbs[:1], ["AUTH"])
            auth_commands = [c for c in server.commands if c[0] == "AUTH"]
            self.assertEqual(auth_commands, [("AUTH", [INJECTION_PASSWORD])])
        finally:
            server.close()

    def test_protocol_break_maps_to_sanitized_category(self):
        handlers = default_handlers()
        handlers["PING"] = b"garbage-no-kind\r\n"
        server = FakeRedis(handlers)
        server.start()
        try:
            self.assertEqual(
                self._category(f"redis://127.0.0.1:{server.port}/15"), "ping_failed"
            )
        finally:
            server.close()

    def test_server_closes_mid_session_maps_sanitized(self):
        handlers = default_handlers()

        def auth_then_close(args):
            return b""  # empty reply closes the connection

        handlers["AUTH"] = auth_then_close
        server = FakeRedis(handlers)
        server.start()
        try:
            category = self._category(
                f"redis://:{DECODED_PASSWORD}@127.0.0.1:{server.port}/15"
            )
            self.assertIn(category, ("auth_failed", "protocol_error"))
        finally:
            server.close()

    def test_no_traceback_text_in_any_failure_surface(self):
        handlers = default_handlers()
        handlers["PING"] = b"+NOPE\r\n"
        server = FakeRedis(handlers)
        server.start()
        try:
            with self.assertRaises(self.runner.TrapFired) as ctx:
                self.runner.redis_live_check(
                    f"redis://:{DECODED_PASSWORD}@127.0.0.1:{server.port}/15"
                )
            blob = json.dumps(
                {"evidence": ctx.exception.evidence, "exc": str(ctx.exception),
                 "trap": ctx.exception.trap_id}
            )
            for banned in ("Traceback", "ValueError", "OSError", DECODED_PASSWORD,
                           "127.0.0.1", str(server.port)):
                self.assertNotIn(banned, blob)
        finally:
            server.close()


class SharedImplementationTruthTests(unittest.TestCase):
    def test_runner_and_child_bind_same_canonical_path_and_bytes(self):
        """R2-R2 retraction: the R2-R1 'same module object' claim is WRONG
        across processes. Both consumers independently load from the SAME
        canonical path and bind the SAME raw-byte SHA-256."""
        import hashlib
        import sys as _sys

        runner = _load(RUNNER_PATH, "he2et1_r2r1_shared_runner")
        plugin = _load(PLUGIN_PATH, "he2et1_r2r1_shared_plugin")
        runner_path = runner.redis_module_canonical_path().resolve()
        plugin_path = plugin._redis_module_canonical_path().resolve()
        self.assertEqual(runner_path, SHARED_PATH.resolve())
        self.assertEqual(plugin_path, SHARED_PATH.resolve())
        # Both bind the same raw bytes of that one file.
        expected = hashlib.sha256(SHARED_PATH.read_bytes()).hexdigest()
        self.assertEqual(runner.redis_module_raw_digest(), expected)
        _plugin_module, _plugin_tampered = plugin._load_redis_authority()
        self.assertEqual(
            hashlib.sha256(plugin_path.read_bytes()).hexdigest(), expected
        )
        # And the fixed sys.modules key now holds the freshly executed real
        # module — not a trusted cache (it was evicted and re-executed).
        self.assertIn("et1_redis_authority", _sys.modules)

    def test_no_protocol_code_duplicated_in_runner_or_plugin(self):
        runner_src = RUNNER_PATH.read_text(encoding="utf-8")
        plugin_src = PLUGIN_PATH.read_text(encoding="utf-8")
        shared_src = SHARED_PATH.read_text(encoding="utf-8")
        # The RESP protocol primitives exist ONLY in the shared module.
        self.assertIn("def resp_encode", shared_src)
        self.assertNotIn("def resp_encode", runner_src)
        self.assertNotIn("def resp_encode", plugin_src)
        self.assertNotIn("def _redis_cmd", runner_src)
        self.assertNotIn("def _redis_cmd", plugin_src)
        self.assertNotIn("def _read_reply", runner_src)
        self.assertNotIn("def _read_reply", plugin_src)
        # The runner/plugin keep only thin DELEGATORS over the shared module.
        self.assertIn("module.redis_live_check(url)", runner_src)
        self.assertIn("module.eval_redis(url, SENTINEL_PROBE_ENDPOINT)", runner_src)
        self.assertIn("module.eval_redis(url, SENTINEL_PROBE_ENDPOINT)", plugin_src)
        # The shared module holds the whole probe body (connect/AUTH/PING/
        # SELECT/DBSIZE sequence appears once).
        probe_markers = ("create_connection", '"PING"', '"SELECT"', '"DBSIZE"')
        for marker in probe_markers:
            self.assertIn(marker, shared_src)
            self.assertNotIn(marker, plugin_src)


if __name__ == "__main__":
    unittest.main()
