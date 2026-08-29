"""HE2-ET1-R2 live Redis authority E2E cases (stdlib only).

Truth nodes over a REAL redis7 container (task-scoped, throwaway):
  RL1 GREEN          fresh empty DB15 -> full authority chain rc=0 FINISHED
                     sentinel_calls=1
  RL2 wrong DB       URL /0 -> rc 14 VOID sentinel 0
  RL7 invalid port   ':notaport' -> rc 14 VOID, no traceback
  RL3 unreachable    redis stopped -> rc 14 VOID sentinel 0
  RL4 DB15 nonempty  one seeded key -> rc 14 VOID sentinel 0
  RL5 post-preflight redis disappears -> child sessionstart fail-closed,
                     collect trap, sentinel 0 (in-process around the child)
  RL6 sentinel 26379 reachable (temporary local listener) -> rc 14 VOID

PING-not-PONG and SELECT-failure nodes are proven in test_authority_runner_r2.py
against a controlled real-socket fake RESP server (a real redis cannot be
made to misbehave on demand); those unit proofs are cross-referenced here.

Required env: TEST_DATABASE_URL (non-superuser CREATEDB role on a live PG),
TEST_DATABASE_URL_SUPER, PW1R3_TEST_REDIS_URL (fresh redis7 DB15),
MPANGO_ALLOW_TEMP_DB_CREATE=1. Optional ET1_E2E_BASELINE.
Run from the worktree root with pytest+psycopg available, e.g.:
  uv run --with pytest --with psycopg --with psycopg-binary     python harness-governance/tests/run_e2e_redis_cases.py

Cases:
  1 GREEN / 2 wrong-db / 3 unreachable / 4 nonempty / 5 post-preflight-gone
  / 6 sentinel-reachable -> all asserted as listed above.
"""

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[2]
GOV = WORKTREE / "harness-governance"
RUNNER = GOV / "validator" / "authority_runner.py"
PROFILE = GOV / "inventory" / "authority-profiles.json"
MANIFEST = GOV / "inventory" / "et1-node-manifest.txt"
COLLECT = GOV / "tests" / "_et1_collector_fixtures.py"
BASELINE = os.environ.get("ET1_E2E_BASELINE", "246eb190fc07866f098a380e61ebdc5bd9428a04")

DB_URL = os.environ["TEST_DATABASE_URL"]
REDIS_URL = os.environ["PW1R3_TEST_REDIS_URL"]

results = []


def report(name, ok, detail):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<30} {detail}")


def run_authority(redis_url):
    case_dir = Path(tempfile.mkdtemp(prefix="et1r2-"))
    env = {
        **os.environ,
        "TEST_DATABASE_URL": DB_URL,
        "PW1R3_TEST_REDIS_URL": redis_url,
        "MPANGO_ALLOW_TEMP_DB_CREATE": "1",
    }
    args = [
        sys.executable, str(RUNNER),
        "--baseline-sha", BASELINE,
        "--publish-dir", str(case_dir / "publish"),
        "--profile", str(PROFILE), "--node-manifest", str(MANIFEST),
        "--collect-target", str(COLLECT),
        "--proof-out", str(case_dir / "proof.json"),
        "--sessionstart-out", str(case_dir / "ss.json"),
        "--authority", "--command", sys.executable, "-c", "pass",
    ]
    proc = subprocess.run(args, capture_output=True, text=True, env=env, cwd=str(WORKTREE))
    published = {}
    pf = case_dir / "publish" / "authority-preflight.json"
    if pf.exists():
        published = json.loads(pf.read_text(encoding="utf-8"))
    return proc.returncode, published, proc.stdout + proc.stderr


def wait_port(host, port, up, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.4):
                reachable = True
        except OSError:
            reachable = False
        if reachable == up:
            return True
        time.sleep(0.4)
    return False


def main():
    parsed = __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(REDIS_URL)
    host, port = parsed.hostname, parsed.port or 6379
    db = (parsed.path or "").strip("/")

    # RL1 GREEN: fresh empty DB15 full chain.
    rc, pub, out = run_authority(REDIS_URL)
    ok = (rc == 0 and pub.get("state") == "FINISHED"
          and pub.get("sentinel_calls") == 1 and pub.get("collect_child_spawns") == 1)
    report("RL1-green-fresh-db15", ok,
           f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')}")

    # RL2 wrong DB: URL pointing at /0 (same server) must VOID pre-connect.
    rc, pub, _ = run_authority(f"redis://{host}:{port}/0")
    ok = rc == 14 and pub.get("state") == "VOID" and pub.get("sentinel_calls") == 0
    report("RL2-red-wrong-db", ok,
           f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')}")

    # RL7 invalid port: malformed port string must VOID sanitized (no traceback).
    rc, pub, out = run_authority("redis://127.0.0.1:notaport/15")
    ok = (rc == 14 and pub.get("state") == "VOID"
          and pub.get("sentinel_calls") == 0 and "Traceback" not in out)
    report("RL7-red-invalid-port", ok,
           f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')}")

    # RL4 DB15 nonempty: seed one key, expect VOID (clean up afterwards).
    seed = subprocess.run(
        [sys.executable, "-c",
         "import socket,sys\n"
         "s=socket.create_connection((sys.argv[1], int(sys.argv[2])), 3)\n"
         "f=s.makefile('rb')\n"
         "s.sendall(b'SELECT 15\\r\\n'); f.readline()\n"
         "s.sendall(b'SET r2probe locked\\r\\n'); f.readline()\n"
         "s.close()",
         str(host), str(port)],
        capture_output=True, text=True,
    )
    try:
        rc, pub, _ = run_authority(REDIS_URL)
        ok = rc == 14 and pub.get("state") == "VOID" and pub.get("sentinel_calls") == 0
        report("RL4-red-db15-nonempty", ok,
               f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')} seed_rc={seed.returncode}")
    finally:
        subprocess.run(
            [sys.executable, "-c",
             "import socket,sys\n"
             "s=socket.create_connection((sys.argv[1], int(sys.argv[2])), 3)\n"
             "f=s.makefile('rb')\n"
             "s.sendall(b'SELECT 15\\r\\n'); f.readline()\n"
             "s.sendall(b'DEL r2probe\\r\\n'); f.readline()\n"
             "s.close()",
             str(host), str(port)],
            capture_output=True, text=True,
        )

    # RL5 post-preflight disappearance: preflight-era Redis up; stop it; the
    # CHILD sessionstart recheck must fail closed -> no proof -> collect trap,
    # authority command never launched (in-process around the real child).
    spec = importlib.util.spec_from_file_location("he2et1_r2_e2e_runner", str(RUNNER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ok_live = mod.redis_live_check(REDIS_URL)  # stands in for completed preflight
    stop = subprocess.run(["docker", "stop", os.environ.get("ET1_R2_REDIS_CONTAINER", "")],
                          capture_output=True, text=True)
    gone = wait_port(host, port, up=False, timeout=15)
    try:
        r = mod.AuthorityRunner(WORKTREE, {"profile_id": "R2"}, ["x"])
        r._to("PREFLIGHT")
        case_dir = Path(tempfile.mkdtemp(prefix="et1r2-ip-"))
        trapped = None
        try:
            r.collect_proven(
                profile_path=str(PROFILE), manifest_path=str(MANIFEST),
                proof_out=str(case_dir / "proof.json"),
                sessionstart_out=str(case_dir / "ss.json"),
                collect_target=str(COLLECT),
            )
        except mod.TrapFired as fired:
            trapped = fired
        subprocess.run(["docker", "start", os.environ.get("ET1_R2_REDIS_CONTAINER", "")],
                       capture_output=True, text=True)
        wait_port(host, port, up=True, timeout=15)
        child_ss = case_dir / "ss.json"
        child_fail_closed = False
        if child_ss.exists():
            doc = json.loads(child_ss.read_text(encoding="utf-8"))
            child_fail_closed = doc.get("ok") is False and any(
                p.startswith("redis:") for p in doc.get("problems", [])
            )
        ok = (trapped is not None and gone and child_fail_closed
              and r.sentinel_calls == 0 and ok_live.get("redis") == "ok")
        report("RL5-red-redis-gone-after-preflight", ok,
               f"trap={trapped.trap_id if trapped else None} child_fail_closed={child_fail_closed} "
               f"sentinel={r.sentinel_calls} redis_was_down={gone}")
    finally:
        subprocess.run(["docker", "start", os.environ.get("ET1_R2_REDIS_CONTAINER", "")],
                       capture_output=True, text=True)
        wait_port(host, port, up=True, timeout=15)

    # RL3 unreachable: redis stopped for the WHOLE CLI authority attempt.
    subprocess.run(["docker", "stop", os.environ.get("ET1_R2_REDIS_CONTAINER", "")],
                   capture_output=True, text=True)
    gone = wait_port(host, port, up=False, timeout=15)
    try:
        rc, pub, _ = run_authority(REDIS_URL)
        ok = (rc == 14 and pub.get("state") == "VOID"
              and pub.get("sentinel_calls") == 0 and gone)
        report("RL3-red-unreachable", ok,
               f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')} redis_was_down={gone}")
    finally:
        subprocess.run(["docker", "start", os.environ.get("ET1_R2_REDIS_CONTAINER", "")],
                       capture_output=True, text=True)
        wait_port(host, port, up=True, timeout=15)

    # RL6 sentinel reachable: temporary listener on 127.0.0.1:26379.
    sentinel = None
    try:
        sentinel = socket.socket()
        sentinel.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sentinel.bind(("127.0.0.1", 26379))
        sentinel.listen(4)
        sentinel_open = True
    except OSError:
        sentinel_open = False
    try:
        if sentinel_open:
            rc, pub, _ = run_authority(REDIS_URL)
            ok = rc == 14 and pub.get("state") == "VOID" and pub.get("sentinel_calls") == 0
            report("RL6-red-sentinel-reachable", ok,
                   f"rc={rc} state={pub.get('state')} sentinel={pub.get('sentinel_calls')}")
        else:
            report("RL6-red-sentinel-reachable", False, "port 26379 not bindable locally")
    finally:
        if sentinel is not None:
            sentinel.close()

    print("-" * 72)
    failed = [name for name, ok, _ in results if not ok]
    print(f"R2 LIVE REDIS E2E: {len(results) - len(failed)}/{len(results)} cases PASS")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("ALL LIVE REDIS CASES GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
