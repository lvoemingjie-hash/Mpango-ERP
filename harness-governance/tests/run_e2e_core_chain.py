"""HE2-ET1-R1 E2E core-chain gate (8 cases; stdlib only).

Proves the vertical authority chain end to end against a REAL pytest child
and a REAL PG role: the GREEN case launches the authority command exactly
once (sentinel_calls == 1, collect_child_spawns == 1, nonce_match) and the
RED cases (superuser, empty URL, temp-DB capability off, missing command,
child nonce tamper, collect node drift, profile drift) all land VOID with
sentinel_calls == 0.

Required environment: TEST_DATABASE_URL (non-superuser CREATEDB role),
TEST_DATABASE_URL_SUPER (instance superuser; proves TRAP_PG_ROLE_SUPER),
PW1R3_TEST_REDIS_URL (redis URL with /15), MPANGO_ALLOW_TEMP_DB_CREATE=1.
Optional: ET1_E2E_BASELINE (chain base; default the HE2-ET1 chain base).
Run from the worktree root with pytest+psycopg available, e.g.:
  uv run --with pytest --with psycopg --with psycopg-binary     python harness-governance/tests/run_e2e_core_chain.py

Cases (all must pass before the round extends):
  1  GREEN full pipeline          -> rc 0, FINISHED, sentinel_calls == 1,
                                     collect_child_spawns == 1, nonce_match
  2  RED superuser URL            -> rc 10, VOID, sentinel_calls == 0
  3  RED empty TEST_DATABASE_URL  -> rc 11, VOID, sentinel_calls == 0
  4  RED temp-DB flag 0           -> rc 12, VOID, sentinel_calls == 0
  5  RED --authority, no command  -> rc 16, VOID, sentinel_calls == 0
  6  RED child nonce tamper       -> TrapFired nonce_mismatch, sentinel 0
  7  RED collect node drift       -> TrapFired TRAP_COLLECT_NODE_SET_DRIFT
  8  RED profile drift mid-flight -> TrapFired 18 profile_drift
"""



import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[2]
GOV = WORKTREE / "harness-governance"
RUNNER = GOV / "validator" / "authority_runner.py"
PROFILE = GOV / "inventory" / "authority-profiles.json"
MANIFEST = GOV / "inventory" / "et1-node-manifest.txt"
COLLECT = GOV / "tests" / "_et1_collector_fixtures.py"
BASELINE = os.environ.get("ET1_E2E_BASELINE", "246eb190fc07866f098a380e61ebdc5bd9428a04")

DB_URL = os.environ["TEST_DATABASE_URL"]
DB_URL_SUPER = os.environ.get("TEST_DATABASE_URL_SUPER", "")
REDIS_URL = os.environ.get("PW1R3_TEST_REDIS_URL", "redis://127.0.0.1:16379/15")

results = []


def report(name, ok, detail):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<34} {detail}")


def run_runner(extra_args, env_overrides):
    case_dir = Path(tempfile.mkdtemp(prefix="et1e2e-"))
    proof_out = case_dir / "collect-proof.json"
    env = {
        **os.environ,
        "TEST_DATABASE_URL": DB_URL,
        "PW1R3_TEST_REDIS_URL": REDIS_URL,
        "MPANGO_ALLOW_TEMP_DB_CREATE": "1",
        **env_overrides,
    }
    args = [
        sys.executable, str(RUNNER),
        "--baseline-sha", BASELINE,
        "--publish-dir", str(case_dir / "publish"),
        "--profile", str(PROFILE),
        "--node-manifest", str(MANIFEST),
        "--collect-target", str(COLLECT),
        "--proof-out", str(proof_out),
        "--sessionstart-out", str(case_dir / "sessionstart-proof.json"),
        *extra_args,
    ]
    proc = subprocess.run(args, capture_output=True, text=True, env=env, cwd=str(WORKTREE))
    published = {}
    pf = case_dir / "publish" / "authority-preflight.json"
    if pf.exists():
        published = json.loads(pf.read_text(encoding="utf-8"))
    return proc.returncode, published, proc.stdout + proc.stderr


def load_runner_module():
    spec = importlib.util.spec_from_file_location("he2et1_e2e_runner", str(RUNNER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Case 1: GREEN full pipeline -------------------------------------------
manifest_nodes = [
    line.strip() for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()
]
rc, pub, out = run_runner(
    ["--authority", "--command", sys.executable, "-c", "pass"], {}
)
ok = (
    rc == 0 and pub.get("state") == "FINISHED"
    and pub.get("sentinel_calls") == 1 and pub.get("collect_child_spawns") == 1
    and pub.get("nonce_match") is True
    and pub.get("collected_node_count") == len(manifest_nodes)
    and all(pub.get("child_sha_match", {}).get(k) is True for k in ("candidate", "profile", "manifest"))
)
report("1-green-full-pipeline", ok, f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')}")

# --- Case 2: RED superuser --------------------------------------------------
if DB_URL_SUPER:
    rc, pub, _ = run_runner(["--authority", "--command", sys.executable, "-c", "pass"],
                            {"TEST_DATABASE_URL": DB_URL_SUPER})
    ok = rc == 10 and pub.get("state") == "VOID" and pub.get("sentinel_calls") == 0
    report("2-red-superuser", ok, f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')}")
else:
    report("2-red-superuser", False, "TEST_DATABASE_URL_SUPER not set")

# --- Case 3: RED empty URL --------------------------------------------------
rc, pub, _ = run_runner(["--authority", "--command", sys.executable, "-c", "pass"],
                        {"TEST_DATABASE_URL": ""})
ok = rc == 11 and pub.get("state") == "VOID" and pub.get("sentinel_calls") == 0
report("3-red-empty-url", ok, f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')}")

# --- Case 4: RED capability flag off ----------------------------------------
rc, pub, _ = run_runner(["--authority", "--command", sys.executable, "-c", "pass"],
                        {"MPANGO_ALLOW_TEMP_DB_CREATE": "0"})
ok = rc == 12 and pub.get("state") == "VOID" and pub.get("sentinel_calls") == 0
report("4-red-temp-db-flag", ok, f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')}")

# --- Case 5: RED missing command under --authority ---------------------------
rc, pub, _ = run_runner(["--authority"], {})
ok = rc == 16 and pub.get("state") == "VOID" and pub.get("sentinel_calls") == 0
report("5-red-missing-command", ok, f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')}")

# --- In-process cases --------------------------------------------------------
mod = load_runner_module()
case_dir = Path(tempfile.mkdtemp(prefix="et1e2e-inproc-"))
tmp_profile = case_dir / "authority-profiles.json"
tmp_manifest = case_dir / "et1-node-manifest.txt"
tmp_profile.write_bytes(PROFILE.read_bytes())
tmp_manifest.write_bytes(MANIFEST.read_bytes())


def make_inproc_runner(expected):
    profile = json.loads(tmp_profile.read_text(encoding="utf-8"))
    sel = next(p for p in profile["profiles"] if p["profile_id"] == "AUTHORITY_H2C_BACKEND")
    r = mod.AuthorityRunner(WORKTREE, sel, expected)
    r.profile_sha_file = tmp_profile
    r.manifest_sha_file = tmp_manifest
    r._to("PREFLIGHT")  # models a completed preflight; collect/authorize under test
    r.bind_redis_module()  # R2-R2: bind the shared module like a real preflight
    r._require_bound_redis_module()
    return r


def collect(r, tag):
    r.collect_proven(
        profile_path=tmp_profile, manifest_path=tmp_manifest,
        proof_out=case_dir / f"proof-{tag}.json",
        sessionstart_out=case_dir / f"ss-{tag}.json",
        collect_target=str(COLLECT),
    )


# --- Case 6: RED child nonce tamper -----------------------------------------
r6 = make_inproc_runner(manifest_nodes)
real_run = mod.subprocess.run


def tampering_run(cmd, **kwargs):
    env = kwargs.get("env")
    if env is not None and "ET1_RUNNER_NONCE" in env:
        env = dict(env)
        env["ET1_RUNNER_NONCE"] = "TAMPERED-NOT-THE-RUNNER-ORIGINAL!!"
        kwargs = dict(kwargs, env=env)
    return real_run(cmd, **kwargs)


mod.subprocess.run = tampering_run
try:
    collect(r6, "nonce")
    report("6-red-nonce-tamper", False, "no trap fired")
except mod.TrapFired as fired:
    ok = (fired.evidence.get("reason") == "nonce_mismatch"
          and r6.sentinel_calls == 0 and r6.collect_spawns == 1)
    report("6-red-nonce-tamper", ok,
           f"ev={json.dumps(fired.evidence, sort_keys=True)} sentinel={r6.sentinel_calls}")
finally:
    mod.subprocess.run = real_run

# --- Case 7: RED collect node drift ------------------------------------------
r7 = make_inproc_runner(manifest_nodes[:-1])
try:
    collect(r7, "drift")
    report("7-red-node-drift", False, "no trap fired")
except mod.TrapFired as fired:
    ok = fired.trap_id == "TRAP_COLLECT_NODE_SET_DRIFT" and r7.sentinel_calls == 0
    report("7-red-node-drift", ok, f"ev={json.dumps(fired.evidence, sort_keys=True)} sentinel={r7.sentinel_calls}")

# --- Case 8: RED profile drift between collect and authorize ------------------
r8 = make_inproc_runner(manifest_nodes)
collect(r8, "pdrift")
tmp_profile.write_bytes(tmp_profile.read_bytes() + b" " * 8)  # drift the bytes
try:
    r8.authorize(DB_URL, "1")
    report("8-red-profile-drift", False, "no trap fired")
except mod.TrapFired as fired:
    ok = fired.exit_code == 18 and fired.evidence.get("reason") == "profile_drift" and r8.sentinel_calls == 0
    report("8-red-profile-drift", ok,
           f"trap={fired.trap_id} reason={fired.evidence.get('reason')} sentinel={r8.sentinel_calls}")

print("-" * 72)
failed = [name for name, ok, _ in results if not ok]
print(f"E2E CORE CHAIN: {len(results) - len(failed)}/{len(results)} cases PASS")
if failed:
    print("FAILED:", ", ".join(failed))
    sys.exit(1)
print("ALL CORE CASES GREEN — vertical proof closed")
