"""HE2-ET1-R3-A1 mutation probes: profile-bound alembic successor authority.

Every A1 mutation attacks one bypass point of the profile-bound alembic
chain; each hermetic PROBE must report the gate WEAKENED under the patched
candidate and HOLD after the byte-exact restore.

Probe contract: probe(...) -> bool, True == gate HELD, False == ESCAPED.
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
RUNNER_RELPATH = "harness-governance/validator/authority_runner.py"
SHARED_RELPATH = "harness-governance/validator/backend_env_authority.py"
PLUGIN_RELPATH = "harness-governance/tests/pytest_et1_collector.py"

H2C = "037_payment_declarations_schema"
SKU = "038_catalog_identity_vertical_slice"
LEGAL_URL = "postgresql://ci_gate@127.0.0.1:15455/test_ci_gate"


def _load_runner():
    sys.modules.pop("et1_r3a1_probe_runner", None)
    sys.modules.pop("et1_backend_env_authority", None)
    spec = importlib.util.spec_from_file_location(
        "et1_r3a1_probe_runner", str(REPO_ROOT / RUNNER_RELPATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_plugin():
    sys.modules.pop("et1_r3a1_probe_plugin", None)
    sys.modules.pop("et1_backend_env_authority", None)
    spec = importlib.util.spec_from_file_location(
        "et1_r3a1_probe_plugin", str(REPO_ROOT / PLUGIN_RELPATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_shared():
    sys.modules.pop("et1_r3a1_probe_shared", None)
    spec = importlib.util.spec_from_file_location(
        "et1_r3a1_probe_shared", str(REPO_ROOT / SHARED_RELPATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture(tmp, layout):
    versions = Path(tmp) / "alembic" / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    for rev, down in layout:
        down_decl = f"'{down}'" if down else "None"
        (versions / f"{rev}_fixture.py").write_text(
            f"revision: str = '{rev}'\ndown_revision: str = {down_decl}\n",
            encoding="utf-8")
    return versions


# --- Probes (True == gate held) ----------------------------------------------


def probe_schema_required_head_dropped(mod_shared, ctx):
    """The schema REQUIRES expected_alembic_head on every profile. With the
    required entry present, a head-less profile is rejected; if the entry is
    dropped (the A101 mutation), the profile loads end-to-end unbound."""
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "profiles.json"
        bad.write_text(json.dumps({
            "schema_version": "1",
            "profiles": [{
                "profile_id": "AUTHORITY_NO_HEAD",
                "description": "x",
                "required_traps": ["TRAP_PG_ROLE_SUPER"],
                "phases": ["PREFLIGHT"],
                "runner": "harness-governance/validator/authority_runner.py",
                "status": "CANDIDATE",
            }],
        }), encoding="utf-8")
        try:
            mod_shared.load_explicit_profile(bad, GOV_SCHEMA, "AUTHORITY_NO_HEAD")
            return False  # missing-head profile accepted end-to-end
        except mod_shared.TrapFired:
            return True  # fail closed (schema and/or explicit check)


def probe_h2c_head_swapped_to_038(mod_shared, ctx):
    """A 037-bound profile given a tree whose actual head is 038 must VOID
    with head_mismatch; deleting the equality check accepts it."""
    with tempfile.TemporaryDirectory() as tmp:
        versions = _fixture(tmp, [("035_b", None), (H2C, "035_b"), (SKU, H2C)])
        try:
            mod_shared.alembic_verify(versions, H2C)
            return False  # wrong head accepted
        except mod_shared.BackendEnvAuthorityError as err:
            return err.category == "alembic_head_mismatch"


def probe_sku_head_swapped_to_037(mod_shared, ctx):
    with tempfile.TemporaryDirectory() as tmp:
        versions = _fixture(tmp, [("035_b", None), (SKU, "035_b")])
        try:
            mod_shared.alembic_verify(versions, SKU, H2C)
            return False  # broken lineage accepted
        except mod_shared.BackendEnvAuthorityError as err:
            return err.category == "alembic_parent_mismatch"


def probe_any_single_head_accepted(mod_shared, ctx):
    """`alembic_head == expected` must be byte-exact; deleting it accepts
    any single head (e.g. the prefix-similar 037...x)."""
    with tempfile.TemporaryDirectory() as tmp:
        versions = _fixture(tmp, [("035_b", "034_c"), (H2C + "x", "035_b")])
        try:
            mod_shared.alembic_verify(versions, H2C)
            return False  # near-miss head accepted
        except mod_shared.BackendEnvAuthorityError as err:
            return err.category == "alembic_head_mismatch"


def probe_multiple_heads_accepted(mod_shared, ctx):
    with tempfile.TemporaryDirectory() as tmp:
        versions = _fixture(tmp, [
            ("035_b", "034_c"), (H2C, "035_b"), (SKU, "035_b")])
        try:
            mod_shared.alembic_verify(versions, SKU, H2C)
            return False  # branch head accepted
        except mod_shared.BackendEnvAuthorityError as err:
            return err.category == "alembic_multiple_heads"


def probe_cli_override_wired(mod_runner, ctx):
    """No CLI flag may override the profile-bound expected head."""
    src = (REPO_ROOT / RUNNER_RELPATH).read_text(encoding="utf-8")
    return "expected-alembic-head" not in src


def probe_env_override_wired(mod_runner, ctx):
    """No environment variable may override the profile-bound head."""
    src = (REPO_ROOT / RUNNER_RELPATH).read_text(encoding="utf-8")
    return "MPANGO_EXPECTED_ALEMBIC_HEAD" not in src


def probe_child_alembic_recheck_deleted(mod_plugin, ctx):
    """A5: against the REAL 038 candidate tree, a child still bound to the
    H2C/037 expected head deterministically reports the alembic mismatch;
    deleting the child recheck (A107) hides it."""
    import json as _json

    with tempfile.TemporaryDirectory() as tmp:
        env = {
            "ET1_RUNNER_ALEMBIC_EXPECTED": H2C,
        }
        gate = mod_plugin.sessionstart_gate(env)
        problems = gate.get("problems", [])
        return any(p == "alembic:alembic_head_mismatch" for p in problems)


def probe_actual_head_drift_accepted(mod_runner, ctx):
    """Actual-head drift between preflight and launch must VOID. Seeds a
    fully authorized runner pointed at a fixture versions dir (037 single
    head), drifts it to 038, then drives run(): pristine blocks with
    drift_at_launch; the A108 patch deletes the JIT and lets it launch."""
    with tempfile.TemporaryDirectory() as tmp:
        versions = _fixture(tmp, [("035_b", "034_c"), (H2C, "035_b")])
        saved = {k: os.environ.get(k) for k in (
            "TEST_DATABASE_URL", "MPANGO_ENV",
            "MPANGO_TEMP_DB_ALLOWED_PORTS", "MPANGO_TEMP_DB_ALLOWED_HOSTS")}
        os.environ["TEST_DATABASE_URL"] = LEGAL_URL
        os.environ["MPANGO_ENV"] = "testing"
        os.environ["MPANGO_TEMP_DB_ALLOWED_PORTS"] = "15432,5432,15455"
        os.environ["MPANGO_TEMP_DB_ALLOWED_HOSTS"] = ""
        try:
            r = mod_runner.AuthorityRunner(REPO_ROOT, {
                "expected_alembic_head": H2C,
                "expected_alembic_parent": "035_b",
            }, ["x"])
            r._to("PREFLIGHT")
            r._to("COLLECT_PROVEN")
            r._to("AUTHORIZED")
            r.alembic_expected = H2C
            r.alembic_parent = "035_b"
            r.alembic_actual = H2C
            r.alembic_versions_dir = versions
            r.original_nonce = "N" * 32
            import time as _time
            r.profile_sha_file = REPO_ROOT / "harness-governance/inventory/authority-profiles.json"
            r.manifest_sha_file = REPO_ROOT / "harness-governance/inventory/et1-node-manifest.txt"
            r.profile_sha = mod_runner.sha256_file(r.profile_sha_file)
            r.manifest_sha = mod_runner.sha256_file(r.manifest_sha_file)
            r.candidate_sha = mod_runner.live_head(REPO_ROOT)
            r.proof = {"nonce": "N" * 32, "candidate_sha": r.candidate_sha,
                       "profile_sha": r.profile_sha,
                       "node_manifest_sha": r.manifest_sha,
                       "issued_at": _time.time(),
                       "expires_at": _time.time() + 900,
                       "state_trace": list(r.trace)}
            # drift the fixture tree: the successor lands (037 -> 038)
            (versions / f"{SKU}_fixture.py").write_text(
                f"revision: str = '{SKU}'\ndown_revision: str = '{H2C}'\n",
                encoding="utf-8")
            saved_connect = mod_runner._pg_connect
            mod_runner._pg_connect = lambda url: type(
                "C", (), {"execute": lambda s, *a: type(
                    "R", (), {"fetchone": lambda s2: (False, True)})(),
                    "close": lambda s: None})()
            sentinel_before = r.sentinel_calls
            try:
                r.run("stub", "1", [sys.executable, "-c", "pass"])
                launched = r.sentinel_calls > sentinel_before
            except mod_runner.TrapFired as fired:
                launched = False
                if fired.evidence.get("alembic") not in (
                        "alembic_head_drift", "alembic_multiple_heads",
                        "alembic_parent_drift", "drift_at_launch"):
                    return False  # wrong trap: gate semantics changed
            return not launched  # held == drift blocked the launch
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def probe_profile_sha_binding_deleted(mod, ctx):
    """Profile raw-byte drift after binding must VOID at authorize."""
    import json as _json
    import time as _time

    with tempfile.TemporaryDirectory() as tmp:
        profile_path = Path(tmp) / "profiles.json"
        profile_path.write_text(_json.dumps({
            "schema_version": "1",
            "profiles": [{
                "profile_id": "AUTHORITY_H2C_BACKEND",
                "description": "x",
                "required_traps": ["TRAP_PG_ROLE_SUPER"],
                "phases": ["PREFLIGHT"],
                "runner": "harness-governance/validator/authority_runner.py",
                "status": "CANDIDATE",
                "expected_alembic_head": H2C,
            }],
        }), encoding="utf-8")
        manifest_path = Path(tmp) / "manifest.txt"
        manifest_path.write_bytes(b"tests/m.py::test_a\n")
        profile = _json.loads(profile_path.read_text(encoding="utf-8"))
        sel = profile["profiles"][0]
        r = mod.AuthorityRunner(REPO_ROOT, sel, ["tests/m.py::test_a"])
        r._to("PREFLIGHT")
        r._to("COLLECT_PROVEN")
        r.profile_sha_file = profile_path
        r.manifest_sha_file = manifest_path
        r.profile_sha = mod.sha256_file(profile_path)
        r.manifest_sha = mod.sha256_file(manifest_path)
        r.candidate_sha = mod.live_head(REPO_ROOT)
        r.original_nonce = "N" * 32
        r.proof = {"nonce": "N" * 32, "candidate_sha": r.candidate_sha,
                   "profile_sha": r.profile_sha,
                   "node_manifest_sha": r.manifest_sha,
                   "issued_at": _time.time(),
                   "expires_at": _time.time() + 900,
                   "state_trace": list(r.trace)}
        # R4: bind a real canonical transport file so the transport JIT gate
        # sees pristine bytes (the probe targets profile drift, not transport).
        _fd, _transport_name = tempfile.mkstemp(prefix="et1r3a1-transport-")
        with os.fdopen(_fd, "wb") as _fh:
            _fh.write(mod.canonical_transport_bytes(["tests/m.py::test_a"]))
        r.transport_path = Path(_transport_name)
        r.transport_digest = mod.manifest_transport_digest(
            mod.canonical_transport_bytes(["tests/m.py::test_a"]))
        # drift the profile bytes AFTER binding, BEFORE the single authorize
        profile_path.write_text(
            _json.dumps({"schema_version": "1", "profiles": []}) + "\n",
            encoding="utf-8")
        saved = mod._pg_connect
        mod._pg_connect = lambda url: type(
            "C", (), {"execute": lambda s, *a: type(
                "R", (), {"fetchone": lambda s2: (False, True)})(),
                "close": lambda s: None})()
        try:
            r.authorize("stub", "1")
            return False  # drifted profile accepted
        except mod.TrapFired as fired:
            return fired.evidence.get("reason") == "profile_drift"
        finally:
            mod._pg_connect = saved


GOV_SCHEMA = REPO_ROOT / "harness-governance/schemas/authority-profiles.schema.json"

PROBES = {
    "schema_required_head_dropped": probe_schema_required_head_dropped,
    "h2c_head_swapped_to_038": probe_h2c_head_swapped_to_038,
    "sku_head_swapped_to_037": probe_sku_head_swapped_to_037,
    "any_single_head_accepted": probe_any_single_head_accepted,
    "multiple_heads_accepted": probe_multiple_heads_accepted,
    "cli_override_wired": probe_cli_override_wired,
    "env_override_wired": probe_env_override_wired,
    "child_alembic_recheck_deleted": probe_child_alembic_recheck_deleted,
    "actual_head_drift_accepted": probe_actual_head_drift_accepted,
    "profile_sha_binding_deleted": probe_profile_sha_binding_deleted,
}


# (name, target relpath, (anchor, replacement) canonical-LF patch, probe)
R3A1_MUTATIONS = [
    (
        "A101-schema-required-head-dropped",
        "harness-governance/schemas/authority-profiles.schema.json",
        (
            '          "status",\n          "expected_alembic_head"\n        ],',
            '          "status"\n        ],',
        ),
        "schema_required_head_dropped",
    ),
    (
        "A102-alembic-head-equality-deleted", SHARED_RELPATH,
        (
            "    if actual != expected_head:",
            "    if False and actual != expected_head:",
        ),
        "h2c_head_swapped_to_038",
    ),
    (
        "A103-multiple-heads-accepted", SHARED_RELPATH,
        (
            '    if len(scan["heads"]) != 1:',
            "    if False and len(scan[\"heads\"]) != 1:",
        ),
        "multiple_heads_accepted",
    ),
    (
        "A104-parent-lineage-check-deleted", SHARED_RELPATH,
        (
            "    if expected_parent is not None:\n"
            "        if entry[\"kind\"] is not None or entry[\"down\"] != expected_parent:\n"
            "            raise BackendEnvAuthorityError(\"alembic_parent_mismatch\")",
            "    if False:\n"
            "        if entry[\"kind\"] is not None or entry[\"down\"] != expected_parent:\n"
            "            raise BackendEnvAuthorityError(\"alembic_parent_mismatch\")",
        ),
        "sku_head_swapped_to_037",
    ),
    (
        "A105-cli-expected-head-override", RUNNER_RELPATH,
        (
            '    parser.add_argument("--profile-id", default="AUTHORITY_H2C_BACKEND")',
            '    parser.add_argument("--profile-id", default="AUTHORITY_H2C_BACKEND")\n'
            '    parser.add_argument("--expected-alembic-head", default=None)\n'
            '    if args.expected_alembic_head:\n'
            '        os.environ["MPANGO_EXPECTED_ALEMBIC_HEAD"]'
            " = args.expected_alembic_head",
        ),
        "cli_override_wired",
    ),
    (
        "A106-env-expected-head-override", RUNNER_RELPATH,
        (
            "        self.alembic_expected = self.profile.get(\"expected_alembic_head\", \"\")",
            "        self.alembic_expected = os.environ.get(\n"
            "            \"MPANGO_EXPECTED_ALEMBIC_HEAD\") or self.profile.get(\n"
            "            \"expected_alembic_head\", \"\")",
        ),
        "env_override_wired",
    ),
    (
        "A107-child-alembic-recheck-deleted", PLUGIN_RELPATH,
        (
            "    alembic_problems, alembic_actual = _alembic_recheck_problems(env)\n"
            "    problems.extend(alembic_problems)",
            "    alembic_problems, alembic_actual = [], \"\"",
        ),
        "child_alembic_recheck_deleted",
    ),
    (
        "A108-alembic-launch-jit-deleted", RUNNER_RELPATH,
        (
            "        if self.alembic_expected is not None:\n"
            "            drift = self._alembic_drift()\n"
            "            if drift:\n"
            '                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,\n'
            '                                {"alembic": drift})',
            "        if False and self.alembic_expected is not None:\n"
            "            drift = self._alembic_drift()\n"
            "            if drift:\n"
            '                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,\n'
            '                                {"alembic": drift})',
        ),
        "actual_head_drift_accepted",
    ),
    (
        "A109-profile-sha-binding-deleted", RUNNER_RELPATH,
        (
            "        if self.profile_sha_file is not None:\n"
            "            if sha256_file(self.profile_sha_file) != self.profile_sha:\n"
            '                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True,\n'
            '                                {"reason": "profile_drift"})',
            "        if self.profile_sha_file is not None:\n"
            "            if False and sha256_file(self.profile_sha_file) != self.profile_sha:\n"
            '                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True,\n'
            '                                {"reason": "profile_drift"})',
        ),
        "profile_sha_binding_deleted",
    ),
]


def run_probe(probe_name):
    try:
        if probe_name == "child_alembic_recheck_deleted":
            mod = _load_plugin()
        elif probe_name in ("runner_child_tempdb_compare_deleted",
                            "schema_required_head_dropped",
                            "cli_override_wired", "env_override_wired",
                            "actual_head_drift_accepted",
                            "profile_sha_binding_deleted"):
            mod = _load_runner()
        elif probe_name in ("cli_override_wired", "env_override_wired",
                            "actual_head_drift_accepted",
                            "profile_sha_binding_deleted"):
            mod = _load_runner()
        else:
            mod = _load_shared()
        return bool(PROBES[probe_name](mod, None))
    except Exception:
        return False
