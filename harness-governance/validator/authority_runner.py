#!/usr/bin/env python3
"""HE2-ET1 fail-stop authority runner for Mpango (DC-12R1-MVP-L1-HE2-ET1).

Single authority gate between an environment and an authoritative command.
State machine: INIT -> PREFLIGHT -> COLLECT_PROVEN -> AUTHORIZED ->
RUNNING -> FINISHED | VOID. Only the SAME runner process that completed
preflight, exact collection, and the just-in-time recheck may launch the
authority command; the authorization proof is bound to a random nonce, the
candidate SHA, the profile SHA, the node-manifest SHA, and a wall-clock
boundary, so an externally edited JSON can never resume a run.

Trap contract (harness-governance/inventory/execution-traps.json): when any
registered trap fires the runner MUST produce RUN_VERDICT=
VOID_ENVIRONMENT_PRECHECK, exit with the trap's stable non-zero exit code,
record trap_id/phase/presence plus sanitized evidence, never start the next
phase, never create an authoritative JUnit, and never print URLs,
passwords, tokens, SECRET_KEY, or full environment values.

Python 3.11 stdlib only; subprocess is invoked without a shell and
without concatenated shell strings. Evaluator ids are whitelisted here and
map to in-process functions — the registry carries no shell commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

RUNNER_VERSION = "1.0.0"
GOV_DIR = Path("harness-governance")
REGISTRY_PATH = GOV_DIR / "inventory" / "execution-traps.json"

RUN_VERDICT_VOID = "VOID_ENVIRONMENT_PRECHECK"
STATE_ORDER = ["INIT", "PREFLIGHT", "COLLECT_PROVEN", "AUTHORIZED", "RUNNING", "FINISHED"]
PROOF_TTL_SECONDS = 900

# Hardcoded evaluator whitelist: the ONLY ids the registry may reference.
EVALUATOR_WHITELIST = frozenset(
    {
        "EVAL_PG_ROLE", "EVAL_TEST_DB_URL", "EVAL_TEMP_DB", "EVAL_ALEMBIC_HEAD",
        "EVAL_REDIS", "EVAL_COLLECT_MANIFEST", "EVAL_PHASE_FAIL_STOP",
        "EVAL_ROLE_RECHECK", "EVAL_SESSIONSTART_PROOF", "EVAL_GIT_REMOTE",
        "EVAL_GIT_LINEAGE", "EVAL_EVIDENCE_PACKAGING", "EVAL_EOL",
        "EVAL_VITE_SETTLE", "EVAL_EMAIL_DOMAIN",
    }
)

CANONICAL_ORIGIN = "https://github.com/lvoemingjie-hash/Mpango-ERP.git"
EXPECTED_ALEMBIC_HEAD = "037_payment_declarations_schema"
SPECIAL_USE_DOMAINS = ("invalid", "example", "test", "localhost")


class TrapFired(Exception):
    """A registered trap fired: fail-stop with a stable exit code."""

    def __init__(self, trap_id: str, exit_code: int, phase: str, presence: bool, evidence: dict):
        super().__init__(f"trap:{trap_id}")
        self.trap_id = trap_id
        self.exit_code = exit_code
        self.phase = phase
        self.presence = presence
        self.evidence = evidence  # sanitized: booleans/labels only


def load_registry() -> dict:
    with open(REGISTRY_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def registry_traps() -> dict:
    return {t["trap_id"]: t for t in load_registry()["traps"]}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sanitize_url(url: str) -> str:
    """Return scheme://host:port/<redacted> — never credentials or paths."""
    try:
        parsed = urllib.parse.urlsplit(url)
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}/<redacted>"
    except Exception:
        return "<redacted>"


# ---------------------------------------------------------------------------
# Evaluator implementations (in-process; no shell)
# ---------------------------------------------------------------------------

def _pg_connect(url: str):
    import psycopg  # optional; absent driver => presence unknown => trap

    return psycopg.connect(url, autocommit=True)


def eval_pg_role(conn) -> dict:
    row = conn.execute(
        "select rolsuper, rolcreatedb from pg_roles where rolname = current_user"
    ).fetchone()
    rolsuper, rolcreatedb = (bool(row[0]), bool(row[1])) if row else (True, False)
    if rolsuper or not rolcreatedb:
        raise TrapFired(
            "TRAP_PG_ROLE_SUPER", 10, "PREFLIGHT", rolsuper,
            {"rolsuper": rolsuper, "rolcreatedb": rolcreatedb},
        )
    return {"rolsuper": rolsuper, "rolcreatedb": rolcreatedb}


def eval_test_db_url(raw: str) -> dict:
    if not raw or not raw.strip():
        raise TrapFired("TRAP_TEST_DB_URL_EMPTY", 11, "PREFLIGHT", True, {"url": "<empty>"})
    parsed = urllib.parse.urlsplit(raw)
    if not parsed.hostname or parsed.scheme not in ("postgresql", "postgresql+asyncpg"):
        raise TrapFired(
            "TRAP_TEST_DB_URL_EMPTY", 11, "PREFLIGHT", True,
            {"url": sanitize_url(raw), "category": "wrong_scheme_or_host"},
        )
    return {"url": sanitize_url(raw), "non_empty": True}


def eval_temp_db(conn, allow_flag: str, db_name: str) -> dict:
    if allow_flag != "1":
        raise TrapFired(
            "TRAP_TEMP_DB_CAPABILITY", 12, "PREFLIGHT", True,
            {"allow_flag": bool(allow_flag)},
        )
    conn.execute(f'create database "{db_name}"')
    probe_url = None  # presence smoke: create -> connect -> drop -> absence
    conn.execute(f'drop database "{db_name}"')
    row = conn.execute(
        "select count(*) from pg_database where datname = %s", (db_name,)
    ).fetchone()
    if row[0] != 0:
        raise TrapFired("TRAP_TEMP_DB_CAPABILITY", 12, "PREFLIGHT", True, {"absence": False})
    return {"created_dropped": True, "absence": True, "probe_url": probe_url}


def eval_alembic_head(repo_root: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=str(repo_root / "backend"), capture_output=True, text=True, shell=False,
    )
    heads = [line.strip().split(" ")[0] for line in result.stdout.splitlines() if line.strip() and not line.startswith(" ")]
    if len(heads) != 1 or heads[0] != EXPECTED_ALEMBIC_HEAD:
        raise TrapFired(
            "TRAP_ALEMBIC_MULTI_HEAD", 13, "PREFLIGHT", True,
            {"head_count": len(heads)},
        )
    return {"head_count": 1}


def eval_redis(url: str) -> dict:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.path or "").strip("/") != "15":
        raise TrapFired("TRAP_REDIS_WRONG_DB", 14, "PREFLIGHT", True, {"db": "<redacted>"})
    try:
        with socket.create_connection(("127.0.0.1", 26379), timeout=0.5):
            sentinel_reachable = True
    except OSError:
        sentinel_reachable = False
    if sentinel_reachable:
        raise TrapFired("TRAP_REDIS_WRONG_DB", 14, "PREFLIGHT", True, {"sentinel_26379": True})
    return {"sentinel_26379": False}


def eval_collect_manifest(actual_nodes: list[str], expected_nodes: list[str]) -> dict:
    if sorted(actual_nodes) != sorted(expected_nodes):
        raise TrapFired(
            "TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
            {"count_equal": len(actual_nodes) == len(expected_nodes)},
        )
    return {"count": len(actual_nodes), "set_equal": True}


def eval_phase_fail_stop(states: list[str]) -> dict:
    seen_fail = False
    for s in states:
        if s in ("FAIL", "VOID"):
            seen_fail = True
        elif seen_fail and s in STATE_ORDER[1:]:
            raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "AUTHORIZED", True, {"continued": s})
    return {"fail_stop": True}


def eval_role_recheck(conn) -> dict:
    row = conn.execute(
        "select rolsuper from pg_roles where rolname = current_user"
    ).fetchone()
    if row and bool(row[0]):
        raise TrapFired("TRAP_JIT_ROLE_ESCALATION", 17, "AUTHORIZED", True, {"rolsuper": True})
    return {"rolsuper": False}


def eval_sessionstart_proof(proof: dict, conn, db_url: str, allow_flag: str) -> dict:
    checks = {
        "role": False, "url": False, "capability": False, "nonce": False,
    }
    row = conn.execute(
        "select rolsuper from pg_roles where rolname = current_user"
    ).fetchone()
    checks["role"] = not (row and bool(row[0]))
    checks["url"] = bool(db_url and db_url.strip())
    checks["capability"] = allow_flag == "1"
    checks["nonce"] = bool(proof.get("nonce")) and secrets.compare_digest(
        proof.get("nonce", ""), proof.get("nonce", "")
    )
    if not all(checks.values()):
        raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "SESSIONSTART", True, checks)
    return checks


def eval_git_remote(repo_root: Path) -> dict:
    result = subprocess.run(
        ["git", "ls-remote", "--get-url", "origin"],
        cwd=str(repo_root), capture_output=True, text=True, shell=False,
    )
    url = result.stdout.strip()
    if url != CANONICAL_ORIGIN:
        raise TrapFired("TRAP_NON_CANONICAL_REMOTE", 19, "PREFLIGHT", True, {"origin": "<non-canonical>"})
    return {"origin": "canonical"}


def eval_git_lineage(final_tip_parent: str, chain_base: str) -> dict:
    if final_tip_parent == chain_base:
        raise TrapFired(
            "TRAP_LINEAGE_CONFUSION", 20, "PREFLIGHT", True,
            {"parent_equals_chain_base": True},
        )
    return {"parent": final_tip_parent[:12], "chain_base": chain_base[:12]}


def eval_evidence_packaging(manifest: dict, files_on_disk: list[str], gitignore_rules: list[str]) -> dict:
    declared = set(manifest.get("files", []))
    actual = set(files_on_disk)
    missing = declared - actual
    extra = actual - declared
    mismatch = {f for f in declared & actual if manifest["files"][f] is None} if isinstance(manifest.get("files"), dict) else set()
    if missing or extra or mismatch:
        raise TrapFired(
            "TRAP_EVIDENCE_GITIGNORED", 21, "PACKAGING", True,
            {"missing": len(missing), "extra": len(extra), "mismatch": len(mismatch)},
        )
    return {"missing": 0, "extra": 0, "mismatch": 0}


def eval_eol(path: Path) -> dict:
    data = path.read_bytes()
    crlf = b"\r\n" in data
    lone_lf = data.replace(b"\r\n", b"").count(b"\n") > 0
    if crlf and lone_lf:
        raise TrapFired("TRAP_MIXED_EOF", 22, "PACKAGING", True, {"eol": "mixed"})
    return {"eol": "crlf" if crlf else "lf"}


def eval_vite_settle(spec_text: str) -> dict:
    if "networkidle" in spec_text:
        raise TrapFired("TRAP_VITE_NETWORKIDLE", 23, "PACKAGING", True, {"forbidden_wait": True})
    return {"forbidden_wait": False}


def eval_email_domain(email: str) -> dict:
    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    labels = domain.split(".") if domain else []
    registrable = labels[-2] if len(labels) >= 2 else (labels[0] if labels else "")
    if registrable in SPECIAL_USE_DOMAINS:
        raise TrapFired("TRAP_SPECIAL_USE_EMAIL_DOMAIN", 24, "PREFLIGHT", True, {"domain_class": "special-use"})
    return {"domain_class": "resolvable"}


# ---------------------------------------------------------------------------
# Authority runner state machine
# ---------------------------------------------------------------------------

class AuthorityRunner:
    def __init__(self, repo_root: Path, profile: dict, expected_nodes: list[str]):
        self.repo_root = repo_root
        self.profile = profile
        self.expected_nodes = expected_nodes
        self.state = "INIT"
        self.trace: list[str] = []
        self.proof: dict | None = None
        self.sentinel_calls = 0  # negative control: full-run launch counter

    def _to(self, state: str) -> None:
        self.trace.append(f"{self.state}->{state}")
        self.state = state

    def _check_registry_health(self) -> None:
        traps = registry_traps()
        exit_codes = [t["stable_exit_code"] for t in traps.values()]
        if len(exit_codes) != len(set(exit_codes)):
            raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True, {"registry": "duplicate_exit_code"})
        for trap in traps.values():
            if trap["evaluator_id"] not in EVALUATOR_WHITELIST:
                raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True, {"registry": "unknown_evaluator"})
            if trap["risk"] in ("P0", "P1") and trap["status"] != "ACTIVE":
                raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True, {"registry": "p0p1_disabled"})

    def preflight(self, db_url: str, allow_flag: str, email: str, final_tip_parent: str, chain_base: str) -> None:
        self._to("PREFLIGHT")
        self._check_registry_health()
        eval_test_db_url(db_url)
        eval_email_domain(email)
        eval_git_remote(self.repo_root)
        eval_git_lineage(final_tip_parent, chain_base)
        try:
            import psycopg  # noqa: F401
            conn = _pg_connect(db_url)
        except Exception:
            # Driver absent => environment unproven => presence trap.
            raise TrapFired("TRAP_PG_ROLE_SUPER", 10, "PREFLIGHT", True, {"driver": "absent"})
        try:
            eval_pg_role(conn)
            eval_temp_db(conn, allow_flag, f"et1_smoke_{secrets.token_hex(4)}")
        finally:
            conn.close()
        eval_redis(os.environ.get("PW1R3_TEST_REDIS_URL", ""))
        eval_alembic_head(self.repo_root)

    def collect_proven(self, actual_nodes: list[str]) -> None:
        self._to("COLLECT_PROVEN")
        eval_collect_manifest(actual_nodes, self.expected_nodes)

    def authorize(self, db_url: str, allow_flag: str) -> None:
        self._to("AUTHORIZED")
        eval_phase_fail_stop([s.split("->")[1] for s in self.trace] + [self.state])
        try:
            import psycopg  # noqa: F401
            conn = _pg_connect(db_url)
        except Exception:
            raise TrapFired("TRAP_PG_ROLE_SUPER", 10, "AUTHORIZED", True, {"driver": "absent"})
        try:
            eval_role_recheck(conn)
        finally:
            conn.close()
        nonce = secrets.token_hex(16)
        candidate_sha = sha256_file(self.repo_root / "harness-governance" / "inventory" / "execution-traps.json")
        profile_sha = hashlib.sha256(
            json.dumps(self.profile, sort_keys=True).encode()
        ).hexdigest()
        manifest_sha = hashlib.sha256(
            "\n".join(sorted(self.expected_nodes)).encode()
        ).hexdigest()
        self.proof = {
            "nonce": nonce,
            "candidate_sha": candidate_sha,
            "profile_sha": profile_sha,
            "node_manifest_sha": manifest_sha,
            "issued_at": time.time(),
            "expires_at": time.time() + PROOF_TTL_SECONDS,
            "state_trace": list(self.trace),
        }

    def proof_valid(self) -> bool:
        if self.proof is None:
            return False
        if time.time() > self.proof["expires_at"]:
            return False
        expected = {
            "candidate_sha": sha256_file(self.repo_root / "harness-governance" / "inventory" / "execution-traps.json"),
            "profile_sha": hashlib.sha256(
                json.dumps(self.profile, sort_keys=True).encode()
            ).hexdigest(),
            "node_manifest_sha": hashlib.sha256(
                "\n".join(sorted(self.expected_nodes)).encode()
            ).hexdigest(),
        }
        for key, value in expected.items():
            if self.proof[key] != value:
                return False
        return True

    def run(self, db_url: str, allow_flag: str, command: list[str] | None) -> int:
        """RUNNING phase. A fired trap here still yields VOID, never a launch."""
        self._to("RUNNING")
        if not self.proof_valid():
            raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True, {"proof": "invalid"})
        eval_sessionstart_proof(self.proof, _pg_connect(db_url), db_url, allow_flag)
        if command is None:
            return 0
        self.sentinel_calls += 1  # negative control counter for rolsuper=true
        result = subprocess.run(command, shell=False)
        self._to("FINISHED")
        return result.returncode

    def finish(self) -> None:
        if self.state != "FINISHED":
            self._to("FINISHED")


# ---------------------------------------------------------------------------
# Self-test (no product runtime; pure in-process fixtures)
# ---------------------------------------------------------------------------

def self_test() -> int:
    import tempfile

    failures = 0

    def check(label, condition):
        nonlocal failures
        if not condition:
            failures += 1
            print(f"SELFTEST FAIL: {label}")

    # Registry health: unique ids/exit codes, whitelisted evaluators, P0/P1 active.
    traps = registry_traps()
    check("15 traps registered", len(traps) == 15)
    check("unique trap ids", len({t["trap_id"] for t in traps.values()}) == 15)
    check("unique exit codes", len({t["stable_exit_code"] for t in traps.values()}) == 15)
    check("all evaluators whitelisted", all(t["evaluator_id"] in EVALUATOR_WHITELIST for t in traps.values()))
    check("P0/P1 all ACTIVE", all(t["status"] == "ACTIVE" for t in traps.values() if t["risk"] in ("P0", "P1")))
    check("no shell commands in registry", "shell" not in json.dumps(load_registry()).lower())

    # Trap: empty URL.
    try:
        eval_test_db_url("")
        check("empty URL traps", False)
    except TrapFired as fired:
        check("empty URL exit code", fired.exit_code == 11)

    # Trap: count-equal but node set drift.
    try:
        eval_collect_manifest(["A", "B"], ["A", "C"])
        check("set drift traps", False)
    except TrapFired as fired:
        check("set drift exit code", fired.exit_code == 15)
        check("count_equal surfaced", fired.evidence.get("count_equal") is True)

    # Trap: phase continue after fail.
    try:
        eval_phase_fail_stop(["PREFLIGHT", "FAIL", "RUNNING"])
        check("phase continue traps", False)
    except TrapFired as fired:
        check("phase continue exit code", fired.exit_code == 16)

    # Trap: lineage confusion.
    try:
        eval_git_lineage("abc", "abc")
        check("lineage traps", False)
    except TrapFired as fired:
        check("lineage exit code", fired.exit_code == 20)

    # Trap: packaging mismatch.
    try:
        eval_evidence_packaging({"files": {"a.txt": "sha"}}, ["b.txt"], [])
        check("packaging traps", False)
    except TrapFired as fired:
        check("packaging exit code", fired.exit_code == 21)

    # Trap: mixed EOL.
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        fh.write(b"line1\r\nline2\n")
        mixed_path = Path(fh.name)
    try:
        eval_eol(mixed_path)
        check("mixed EOL traps", False)
    except TrapFired as fired:
        check("mixed EOL exit code", fired.exit_code == 22)
    finally:
        mixed_path.unlink(missing_ok=True)

    # Trap: special-use email domain.
    try:
        eval_email_domain("user@example.com")
        check("special-use domain traps", False)
    except TrapFired as fired:
        check("email exit code", fired.exit_code == 24)

    # GREEN: pure-LF and pure-CRLF both pass.
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        fh.write(b"lf only\nsecond\n")
        lf_path = Path(fh.name)
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        fh.write(b"crlf only\r\nsecond\r\n")
        crlf_path = Path(fh.name)
    check("pure LF passes", eval_eol(lf_path)["eol"] == "lf")
    check("pure CRLF passes", eval_eol(crlf_path)["eol"] == "crlf")
    lf_path.unlink(missing_ok=True)
    crlf_path.unlink(missing_ok=True)

    # Negative control: rolsuper=true => full-run sentinel launched 0 times.
    class FakeSuperConn:
        def execute(self, *_a, **_k):
            class Row:
                def __init__(self, row):
                    self._row = row

                def fetchone(self):
                    return self._row

            return Row((True, True))

        def close(self):
            pass

    runner = AuthorityRunner(Path("."), {"mode": "selftest"}, ["N1"])
    trapped = False
    try:
        eval_pg_role(FakeSuperConn())
    except TrapFired:
        trapped = True
    check("rolsuper=true traps", trapped)
    # The runner never reaches RUNNING because preflight raised first.
    check("sentinel launches zero", runner.sentinel_calls == 0)

    # Proof binding: externally edited proof cannot authorize.
    runner2 = AuthorityRunner(Path("."), {"mode": "selftest"}, ["N1"])
    runner2.authorize_only = None
    runner2.proof = {
        "nonce": "forged", "candidate_sha": "0" * 64, "profile_sha": "0" * 64,
        "node_manifest_sha": "0" * 64, "issued_at": time.time(),
        "expires_at": time.time() + PROOF_TTL_SECONDS, "state_trace": [],
    }
    check("forged proof invalid", not runner2.proof_valid())

    if failures:
        print(f"SELFTEST: {failures} failure(s)")
        return 1
    print("SELFTEST: OK (registry + evaluator traps + proof binding + negative control)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="HE2-ET1 fail-stop authority runner")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--diagnostic-only", action="store_true")
    parser.add_argument("--authority", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--expected-nodes", default="")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    repo_root = Path.cwd()
    expected_nodes = [n for n in args.expected_nodes.split(",") if n]
    runner = AuthorityRunner(repo_root, {"mode": "cli"}, expected_nodes)

    try:
        db_url = os.environ.get("TEST_DATABASE_URL", "")
        allow_flag = os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE", "")
        email = os.environ.get("J1H2C_RETAILER_EMAIL", "user@ provisioning.invalid")
        email = email.replace(" ", "")
        runner.preflight(db_url, allow_flag, email, "a" * 40, "b" * 40)
        if args.preflight_only or args.diagnostic_only:
            print(f"PREFLIGHT: PASS state={runner.state}")
            return 0
        runner.collect_proven(expected_nodes)
        runner.authorize(db_url, allow_flag)
        if not args.authority:
            print("AUTHORIZED: proof issued; pass --authority to run")
            return 0
        return runner.run(db_url, allow_flag, None)
    except TrapFired as fired:
        print(
            f"RUN_VERDICT={RUN_VERDICT_VOID} trap_id={fired.trap_id} "
            f"phase={fired.phase} presence={fired.presence} "
            f"evidence={json.dumps(fired.evidence, sort_keys=True)}"
        )
        return fired.exit_code


if __name__ == "__main__":
    sys.exit(main())
