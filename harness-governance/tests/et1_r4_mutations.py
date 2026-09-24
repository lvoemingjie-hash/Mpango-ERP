"""HE2-ET1-R4 mutation probes: bounded digest-bound manifest transport.

Every R4 mutation attacks one bypass point of the bounded transport; each
hermetic PROBE must report the gate WEAKENED under the patched candidate and
HELD after the byte-exact restore.

Probe contract: probe(...) -> bool, True == gate HELD, False == ESCAPED.
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
RUNNER_RELPATH = "harness-governance/validator/authority_runner.py"
PLUGIN_RELPATH = "harness-governance/tests/pytest_et1_collector.py"


def _load_runner():
    sys.modules.pop("et1_r4_probe_runner", None)
    sys.modules.pop("et1_backend_env_authority", None)
    spec = importlib.util.spec_from_file_location(
        "et1_r4_probe_runner", str(REPO_ROOT / RUNNER_RELPATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_plugin():
    sys.modules.pop("et1_r4_probe_plugin", None)
    sys.modules.pop("et1_backend_env_authority", None)
    spec = importlib.util.spec_from_file_location(
        "et1_r4_probe_plugin", str(REPO_ROOT / PLUGIN_RELPATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Probes (True == gate held) ----------------------------------------------


def probe_env_string_transport_restored(mod_runner, ctx):
    """R401: the single-string env transport is RETIRED. If the literal
    ET1_RUNNER_REQUIRED_NODES reappears in the runner or plugin source, the
    unbounded transport is back and ~3800-node manifests die E2BIG again."""
    for path in (REPO_ROOT / RUNNER_RELPATH, REPO_ROOT / PLUGIN_RELPATH):
        if "ET1_RUNNER_REQUIRED_NODES" in path.read_text(encoding="utf-8"):
            return False
    return True


def probe_child_digest_compare_deleted(mod_plugin, ctx):
    """R402: the child must compare the transport bytes it READ against the
    runner-bound digest. Deleting the compare accepts substituted files."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "et1-manifest.transport"
        path.write_bytes(b"a\n")
        problems, _ = mod_plugin._manifest_transport_problems({
            "ET1_RUNNER_MANIFEST_TRANSPORT_PATH": str(path),
            "ET1_RUNNER_MANIFEST_TRANSPORT_DIGEST": "f" * 64,  # wrong digest
        })
    return problems == ["manifest_transport:digest_mismatch"]


def probe_child_canonical_order_check_deleted(mod_plugin, ctx):
    """R403: a non-canonical (unsorted) transport file must fail closed even
    when its digest matches — reordering is a frozen-manifest mutation."""
    with tempfile.TemporaryDirectory() as tmp:
        raw = b"b\na\n"
        path = Path(tmp) / "et1-manifest.transport"
        path.write_bytes(raw)
        problems, _ = mod_plugin._manifest_transport_problems({
            "ET1_RUNNER_MANIFEST_TRANSPORT_PATH": str(path),
            "ET1_RUNNER_MANIFEST_TRANSPORT_DIGEST":
                __import__("hashlib").sha256(raw).hexdigest(),
        })
    return problems == ["manifest_transport:non_canonical_order"]


def probe_runner_transport_drift_recheck_deleted(mod_runner, ctx):
    """R404: the runner's JIT drift recheck must detect transport bytes that
    moved after the binding was minted (post-preflight mutation)."""
    import hashlib

    r = mod_runner.AuthorityRunner(REPO_ROOT, {"profile_id": "P"}, ["a"])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "et1-manifest.transport"
        path.write_bytes(b"a\n")
        r.transport_path = path
        r.transport_digest = hashlib.sha256(b"a\n").hexdigest()
        if r._transport_drift() is not None:
            return False  # pristine bytes must NOT report drift
        path.write_bytes(b"a\nb\n")
        return r._transport_drift() == "manifest_transport_drift"


def probe_runner_child_transport_compare_deleted(mod_runner, ctx):
    """R405: verify_child_proof must cross-compare the child's independently
    re-derived transport digest against the runner's ORIGINAL."""
    child = {
        "schema": mod_runner.PLUGIN_PROOF_SCHEMA,
        "sessionstart_ok": True,
        "nonce": "n" * 32,
        "sha_match": {"candidate": True, "profile": True, "manifest": True},
        "redis_module_sha": "r" * 64,
        "tempdb_binding_sha": "d" * 64,
        "alembic_actual_head": "038_catalog_identity_vertical_slice",
        "collected_node_ids": ["a", "b"],
        "manifest_transport_sha": "wrong" ,
        "manifest_transport_nodes_total": 2,
    }
    try:
        mod_runner.verify_child_proof(
            child, "n" * 32, ["a", "b"],
            redis_module_sha="r" * 64,
            tempdb_binding_sha="d" * 64,
            alembic_actual_head="038_catalog_identity_vertical_slice",
            transport_digest="t" * 64)
    except mod_runner.TrapFired as fired:
        return fired.evidence.get("manifest_transport") == "child_digest_mismatch"
    return False  # escaped: substituted transport accepted


def probe_post_collect_drift_check_deleted(mod_runner, ctx):
    """R406: collect_proven must re-verify the transport bytes after the
    child ran (drift between collect and authorize must not go unnoticed)."""
    source = (REPO_ROOT / RUNNER_RELPATH).read_text(encoding="utf-8")
    return source.count("if self._current_transport_digest() != self.transport_digest:") >= 1


PROBES = {
    "env_string_transport_restored": probe_env_string_transport_restored,
    "child_digest_compare_deleted": probe_child_digest_compare_deleted,
    "child_canonical_order_check_deleted": probe_child_canonical_order_check_deleted,
    "runner_transport_drift_recheck_deleted": probe_runner_transport_drift_recheck_deleted,
    "runner_child_transport_compare_deleted": probe_runner_child_transport_compare_deleted,
    "post_collect_drift_check_deleted": probe_post_collect_drift_check_deleted,
}

R4_MUTATIONS = [
    (
        "R401-env-string-transport-restored",
        RUNNER_RELPATH,
        (
            '            TRANSPORT_PATH_VAR: str(transport_path),',
            '            TRANSPORT_PATH_VAR: str(transport_path),\n'
            '            "ET1_RUNNER_REQUIRED_NODES": ",".join(self.expected_nodes),',
        ),
        "env_string_transport_restored",
    ),
    (
        "R402-child-digest-compare-deleted",
        PLUGIN_RELPATH,
        (
            "    if not hmac.compare_digest(digest, expected_digest):",
            "    if False and not hmac.compare_digest(digest, expected_digest):",
        ),
        "child_digest_compare_deleted",
    ),
    (
        "R403-child-canonical-order-check-deleted",
        PLUGIN_RELPATH,
        (
            "    if lines != sorted(lines):",
            "    if False and lines != sorted(lines):",
        ),
        "child_canonical_order_check_deleted",
    ),
    (
        "R404-runner-transport-drift-recheck-deleted",
        RUNNER_RELPATH,
        (
            "        if self._current_transport_digest() != digest:\n"
            '            return "manifest_transport_drift"',
            "        if False and self._current_transport_digest() != digest:\n"
            '            return "manifest_transport_drift"',
        ),
        "runner_transport_drift_recheck_deleted",
    ),
    (
        "R405-runner-child-transport-compare-deleted",
        RUNNER_RELPATH,
        (
            "    if not secrets.compare_digest(child_transport_sha, transport_digest):",
            "    if False and not secrets.compare_digest(child_transport_sha, transport_digest):",
        ),
        "runner_child_transport_compare_deleted",
    ),
    (
        "R406-post-collect-drift-check-deleted",
        RUNNER_RELPATH,
        (
            "        # R4: the transport bytes must not have drifted while the child ran.\n"
            "        if self._current_transport_digest() != self.transport_digest:",
            "        # R4: the transport bytes must not have drifted while the child ran.\n"
            "        if False and self._current_transport_digest() != self.transport_digest:",
        ),
        "post_collect_drift_check_deleted",
    ),
]


def run_probe(probe_name):
    try:
        if probe_name == "env_string_transport_restored":
            return bool(PROBES[probe_name](_load_runner(), None))
        if probe_name in ("child_digest_compare_deleted",
                          "child_canonical_order_check_deleted"):
            return bool(PROBES[probe_name](_load_plugin(), None))
        return bool(PROBES[probe_name](_load_runner(), None))
    except Exception:
        return False
