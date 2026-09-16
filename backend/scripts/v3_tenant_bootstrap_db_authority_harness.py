#!/usr/bin/env python3
"""V3 harness: MPANGO-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R4.

Successor to the R1-R3 harness; orchestrates the full
merge-critical data-integrity/security verification on FRESH PostgreSQL 16
clusters:

  phase validator  the exact named-RED set validator is itself exercised with
                   synthetic results BEFORE any container starts: missing
                   declared REDs (including the 2-expected/1-hit case),
                   extra/undeclared REDs and an empty declaration must all
                   fail closed, or the gate goes RED
  phase identity   FAIL-CLOSED preflight BEFORE any container is created:
                   the declared --candidate-commit must equal the checked-out
                   HEAD with a clean worktree, the immediate R1-R3 predecessor
                   (and the frozen R1-R2 link behind it) must be ancestors,
                   the candidate commit message must carry the R1-R4
                   authorization id, and every source file's working-tree
                   digest must match its committed blob (both digest forms,
                   working-tree CRLF vs blob LF, are recorded)
  phase provision  two throwaway postgres:16 containers (main + a second
                   cluster for the cross-cluster counterexample); roles and
                   six scenario databases per the frozen authority contract
  phase migrate    `alembic upgrade head` AS the migration authority in
                   every scenario database
  phase grants     minimum runtime grants AS the migration authority +
                   tool --verify per database
  phase breakage   one induced authority violation per negative database
                   (missing function / bad signature / runtime-owned
                   function / revoked EXECUTE / runtime-owned function for
                   the verify counterexample)
  phase suite      tests/test_tenant_bootstrap_db_authority.py once per
                   scenario; every run must be GREEN
  phase mutation   MM1 commit-type verify restored, MM2 owner fallback
                   restored, MM3 identifier validation bypassed, MM4 cluster
                   binding bypassed, MM5a existing-database refusal deleted,
                   MM5b partial-role-set refusal deleted, MM6 netloc leak
                   restored, MM7 public-CREATE check deleted, MM8
                   zero-connection early refusal bypassed - each must go RED
                   on its declared named REDs, the observed RED set must
                   match the declaration EXACTLY (missing, extra/undeclared
                   or undeclared-because-empty all fail closed), then BOTH
                   scripts are restored and proven byte-identical (sha256);
                   a post-restore run is re-proven green
  phase regression the R1 7-file bootstrap-heavy suite run on the
                   historical regression comparison base and on the
                   candidate in an identical two-role topology; per-node
                   outcomes must be identical
  phase teardown   remove both containers, the BASE worktree and the
                   synthetic-credential work dir (retained only under --keep)

Usage (from backend/):
    python scripts/v3_tenant_bootstrap_db_authority_harness.py \
        --evidence-dir ../ai-ledger/product-ai/evidence/<dir> \
        --candidate-commit <40-hex implementation candidate commit>
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
BOOTSTRAP_SCRIPT = BACKEND_DIR / "scripts" / "bootstrap_tenant_schema.py"
GRANTS_SCRIPT = BACKEND_DIR / "scripts" / "provision_runtime_db_roles.py"
TEST_FILE = "tests/test_tenant_bootstrap_db_authority.py"

IMAGE_MAIN = "postgres:16.15"
IMAGE_SECOND = "postgres:16.15-alpine"
MIGRATE_ROLE = "mpango_migrate"
APP_ROLE = "mpango_app"

# R1-R4 formal evidence identity.  Recorded SEPARATELY in the machine
# report: the task authorization id, the exact implementation candidate
# commit (declared per invocation via --candidate-commit), the immediate
# R1-R3 predecessor, and the historical regression comparison base.
TASK_ID = "MPANGO_TENANT_BOOTSTRAP_DB_AUTHORITY_R1_R4"
AUTHORIZATION_ID = "CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R4-2026-09-16"
R1_R3_PREDECESSOR_COMMIT = (
    "a21878c169d97e4c6fa837cd19dd9cced7de71e2"  # pragma: allowlist secret
)
# Immediate R1-R2 predecessor, kept for the frozen chain of custody.
R1_R2_PREDECESSOR_COMMIT = (
    "8951112bf126d70643dc64882c8bbee911321928"  # pragma: allowlist secret
)
# Historical regression comparison base (R1 manifest commit), retained so
# the bootstrap-heavy regression chain stays comparable across rounds.
BASE_COMMIT = "0a16ed707ad898e9924c26b28097148708677af9"  # pragma: allowlist secret
SCENARIOS = (
    "v3_ok", "v3_nofunc", "v3_badsig", "v3_wrongown", "v3_nopriv",
    "v3_verify_wrongown",
)
REGRESSION_FILES = (
    "tests/business/test_s4e_reservation_schema_contract.py",
    "tests/business/test_s4f_business_invariant_closeout.py",
    "tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py",
    "tests/test_sku_bc06_reprice_guard.py",
    "tests/test_sku_b2_catalog_serialization.py",
    "tests/test_dc12r1_s3_s2b_i1_r3_migration_preflight.py",
    "tests/test_u1r1_bootstrap_completeness.py",
)

SUITE = "tests/test_tenant_bootstrap_db_authority.py::"

# --------------------------------------------------------------------------
# Mutations (framework from R1-R1 fix 7; MM5-MM7 added in R1-R2, MM8 in
# R1-R3, MM5 split into MM5a/MM5b and exact-set declarations in R1-R4).
# Each entry: file, anchor (LF form), replacement, scenario in which the REDs
# live, the REQUIRED named RED nodeids (`named_red`), and the additional nodes
# that may legitimately go RED (`tolerated_red`).  The validator compares the
# declaration against the observed RED set exactly: a missing required node,
# any RED outside required ∪ tolerated, or an empty declaration fails closed.
# --------------------------------------------------------------------------
MM1_PROBE = (
    "            cannot_replace = True\n"
    "            try:\n"
    "                await app.execute(\n"
    '                    f"CREATE OR REPLACE FUNCTION {LEDGER_GUARD_SIGNATURE} "\n'
    '                    "RETURNS TRIGGER AS $$ BEGIN RETURN OLD; END $$ '
    'LANGUAGE plpgsql"\n'
    "                )\n"
    "                cannot_replace = False\n"
    "            except asyncpg.InsufficientPrivilegeError:\n"
    "                cannot_replace = True\n"
    "            _record(\n"
    '                "app_cannot_replace_guard", cannot_replace,\n'
    '                reason="" if cannot_replace else "replacement succeeded",\n'
    "            )\n"
)

MUTATIONS = [
    {
        "name": "MM1",
        "title": "commit_type_verify_restored",
        "file": "grants",
        "anchor": (
            "            # Pure-catalog replace-capability proof: replacing or "
            "dropping\n"
        ),
        "replacement": (
            MM1_PROBE
            + "            # Pure-catalog replace-capability proof: replacing "
            "or dropping\n"
        ),
        "scenario": "v3_verify_wrongown",
        "named_red": [
            SUITE + "test_static_verify_is_pure_catalog_read_only",
        ],
        "tolerated_red": [],
        "rationale": (
            "restoring a committing DDL probe inside --verify must be caught "
            "by the pure-catalog static semantic assertion. The behavioral "
            "identity proof additionally shows the probe CANNOT mutate the "
            "guard under the minimum-grant topology: PostgreSQL refuses "
            "CREATE OR REPLACE even for the function's OWNER without CREATE "
            "on schema public, which the minimum grants never confer — a "
            "second, independent structural defense"
        ),
    },
    {
        "name": "MM2",
        "title": "owner_fallback_restored",
        "file": "bootstrap",
        "anchor": (
            "        if owner_name != authority:\n"
            "            violations.append(\n"
            '                f"owner is {owner_name!r}, expected migration '
            'authority "\n'
            '                f"{authority!r} (the database owner)"\n'
            "            )\n"
            "        if connected_role == authority:\n"
            "            violations.append(\n"
            '                f"connected role {connected_role!r} IS the '
            'migration "\n'
            '                f"authority {authority!r} (single-role topology). '
            'The "\n'
            '                "runtime role must be a different, non-privileged '
            'role; "\n'
            '                "refusing to bootstrap in place of the '
            'authority."\n'
            "            )\n"
        ),
        "replacement": (
            "        required_owner = (\n"
            "            os.environ.get(MIGRATION_AUTHORITY_ROLE_ENV, "
            '""").strip()\n'
            "            or connected_role\n"
            "        )\n"
            "        if owner_name != required_owner:\n"
            "            violations.append(\n"
            '                f"owner is {owner_name!r}, expected '
            '{required_owner!r}"\n'
            "            )\n"
        ),
        "scenario": "v3_ok",
        "named_red": [
            SUITE + "test_r0_single_role_topology_refused_zero_partial_tenant",
            SUITE + "test_static_owner_fallback_removed_and_"
            "authority_derived_from_db_owner",
        ],
        "tolerated_red": [
            # MM2 removes the ownership precondition in the bootstrap script,
            # which several other fail-closed statics/counterexamples also
            # assert; they may go RED and are declared here.
            SUITE + "test_bootstrap_script_never_replaces_or_reowns_public_"
            "guard",
            SUITE + "test_bootstrap_script_keeps_fail_closed_precondition_"
            "semantics",
            SUITE + "test_static_identifier_validation_wired_in_all_modes",
            SUITE + "test_runtime_with_public_create_refused_zero_tenant",
        ],
        "rationale": (
            "restoring the connected-role owner fallback lets the "
            "single-role topology bootstrap silently — the single-role "
            "refusal and the no-fallback static must catch it"
        ),
    },
    {
        "name": "MM3",
        "title": "identifier_validation_bypassed",
        "file": "grants",
        "anchor": (
            "    if not isinstance(value, str) or "
            "not _SAFE_IDENTIFIER_RE.fullmatch(value):\n"
            "        raise ValueError(\n"
        ),
        "replacement": "    if False:\n        raise ValueError(\n",
        "scenario": "v3_verify_wrongown",
        "named_red": [
            SUITE + "test_injection_identifiers_rejected_zero_writes",
            SUITE + "test_static_identifier_validation_wired_in_all_modes",
        ],
        "tolerated_red": [],
        "rationale": (
            "bypassing identifier validation lets the quote/semicolon/"
            "comment payload reach CREATE ROLE rendering and execute — the "
            "injection counterexample and the wiring static must catch it"
        ),
    },
    {
        "name": "MM4",
        "title": "cluster_binding_bypassed",
        "file": "grants",
        "anchor": (
            "        binding = await self._assert_cluster_binding("
            "require_live=False)\n"
        ),
        "replacement": (
            "        binding = {\"mode\": \"bypassed\", "
            "\"system_identifier\": \"MUTATION-MM4\",\n"
            "                  \"database\": self.database, "
            "\"admin_user\": \"mutated\"}\n"
        ),
        "scenario": "v3_ok",
        "named_red": [
            SUITE + "test_cluster_binding_mismatch_zero_writes",
            SUITE + "test_static_cluster_binding_precedes_writes",
        ],
        "tolerated_red": [
            # bypassing the whole preflight also lets the partial-state
            # counterexample proceed, so that node may go RED too
            SUITE + "test_partial_exists_first_deploy_refused_zero_writes",
        ],
        "rationale": (
            "bypassing the binding preflight lets a cross-cluster admin URL "
            "receive role/database writes — the cross-cluster counterexample "
            "and the binding-order static must catch it"
        ),
    },
    {
        "name": "MM5a",
        "title": "existing_database_refusal_deleted",
        "file": "grants",
        "anchor": (
            "            deferral_allowed = False\n"
            "            if database_exists:\n"
        ),
        "replacement": (
            "            deferral_allowed = True  # MUTATION MM5a\n"
            "            if False:  # MUTATION MM5a: existing-database "
            "refusal deleted\n"
        ),
        "scenario": "v3_ok",
        "named_red": [
            SUITE + "test_wrong_password_provision_refused_zero_writes",
        ],
        "tolerated_red": [],
        "rationale": (
            "deleting the existing-target-database refusal lets --provision "
            "tolerate wrong credentials against an established deployment "
            "(the state falls through to the credential probe, which is a "
            "DIFFERENT guard, so the refusal message changes) — the "
            "wrong-password counterexample's 'is not fresh' semantic "
            "assertion must catch it"
        ),
    },
    {
        "name": "MM5b",
        "title": "partial_role_set_refusal_deleted",
        "file": "grants",
        "anchor": (
            "            elif migrate_role_exists != app_role_exists:\n"
            "                existing, absent = (\n"
            "                    (self.migrate_role, self.app_role)\n"
            "                    if migrate_role_exists\n"
            "                    else (self.app_role, self.migrate_role)\n"
            "                )\n"
            "                problems.append(\n"
            '                    "deferred provisioning refused: the '
            'deployment state is "\n'
            '                    f"not fresh (partial role set: role '
            '{existing!r} already "\n'
            '                    f"exists while role {absent!r} does not) - '
            'partial role "\n'
            '                    "states are never provisioned over (zero '
            'writes "\n'
            '                    "performed)"\n'
            "                )\n"
        ),
        "replacement": (
            "            elif False:  # MUTATION MM5b: partial-role-set "
            "refusal deleted\n"
            "                pass\n"
        ),
        "scenario": "v3_ok",
        "named_red": [
            SUITE + "test_partial_exists_first_deploy_refused_zero_writes",
        ],
        "tolerated_red": [],
        "rationale": (
            "deleting the partial-role-set refusal lets a half-created "
            "deployment fall through to the credential probe instead of "
            "refusing as 'not fresh (partial role set ...)' — the "
            "partial-exists counterexample's 'is not fresh' and 'already "
            "exists' semantic assertions must catch it"
        ),
    },
    {
        "name": "MM6",
        "title": "netloc_leak_restored",
        "file": "grants",
        "anchor": (
            '            rendered = " vs ".join(\n'
            '                f"{host}:{port}" for host, port in '
            "endpoints.values()\n"
            "            )\n"
        ),
        "replacement": (
            '            rendered = " vs ".join([\n'
            "                admin_parsed.netloc, migrate_parsed.netloc, "
            "app_parsed.netloc,\n"
            "            ])\n"
        ),
        "scenario": "v3_ok",
        "named_red": [
            SUITE + "test_cluster_binding_mismatch_zero_writes",
            SUITE + "test_first_deploy_cross_cluster_refused_zero_writes",
        ],
        "tolerated_red": [
            # restoring netloc rendering breaks the credential-hygiene
            # assertions of the zero-connection endpoint-mismatch tests too
            SUITE + "test_layer1_admin_endpoint_mismatch_refused_zero_"
            "connections",
            SUITE + "test_layer1_migrate_endpoint_mismatch_refused_zero_"
            "connections",
            SUITE + "test_layer1_app_endpoint_mismatch_refused_zero_"
            "connections",
        ],
        "rationale": (
            "restoring netloc rendering puts username:password@host into the "
            "refusal diagnostic — the credential-hygiene assertions of the "
            "cross-cluster counterexamples must catch it"
        ),
    },
    {
        "name": "MM7",
        "title": "public_create_check_deleted",
        "file": "bootstrap",
        "anchor": (
            '    if row["can_create_in_public"]:\n'
            "        violations.append(\n"
            '            f"connected role {connected_role!r} holds CREATE on '
            'schema "\n'
            '            "public; the runtime role must never be able to '
            'create or "\n'
            '            "substitute objects in the migration-owned public '
            'schema"\n'
            "        )\n"
        ),
        "replacement": "",
        "scenario": "v3_ok",
        "named_red": [
            SUITE + "test_runtime_with_public_create_refused_zero_tenant",
            SUITE + "test_bootstrap_script_keeps_fail_closed_precondition_"
            "semantics",
        ],
        "tolerated_red": [],
        "rationale": (
            "deleting the runtime no-CREATE-on-public precondition lets a "
            "runtime that can write into public proceed to bootstrap — the "
            "zero-tenant counterexample and the fail-closed static must "
            "catch it"
        ),
    },
    {
        "name": "MM8",
        "title": "layer1_zero_connection_refusal_bypassed",
        "file": "grants",
        "anchor": (
            "        if problems:\n"
            "            raise ClusterBindingError(\n"
            "                _binding_refusal_message(problems)\n"
            "            )\n"
            "\n"
            "        import asyncpg\n"
        ),
        "replacement": (
            "        if False:  # MUTATION MM8: zero-connection early "
            "refusal bypassed\n"
            "            raise ClusterBindingError(\n"
            "                _binding_refusal_message(problems)\n"
            "            )\n"
            "\n"
            "        import asyncpg\n"
        ),
        "scenario": "v3_ok",
        "named_red": [
            SUITE + "test_layer1_admin_endpoint_mismatch_refused_zero_"
            "connections",
            SUITE + "test_layer1_migrate_endpoint_mismatch_refused_zero_"
            "connections",
            SUITE + "test_layer1_app_endpoint_mismatch_refused_zero_"
            "connections",
            SUITE + "test_layer1_database_path_mismatch_refused_zero_"
            "connections",
            SUITE + "test_layer1_migrate_username_mismatch_refused_zero_"
            "connections",
            SUITE + "test_layer1_app_username_mismatch_refused_zero_"
            "connections",
            SUITE + "test_static_layer1_early_refusal_is_unconditional_"
            "and_precedes_connection",
        ],
        "tolerated_red": [],
        "rationale": (
            "bypassing the early Layer-1 refusal lets a mis-wired URL set "
            "reach asyncpg.connect (the admin URL included) before the "
            "refusal — the intercepting-spy zero-connection tests and the "
            "unconditional-guard static sentinel must catch it"
        ),
    },
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run(command, *, env=None, timeout=1200, verify=False, label="",
         cwd=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = subprocess.run(
        command, env=merged, cwd=str(cwd or BACKEND_DIR), capture_output=True,
        text=True, timeout=timeout, encoding="utf-8", errors="replace",
    )
    if verify and result.returncode != 0:
        raise RuntimeError(
            f"{label or command} failed (rc={result.returncode})\n"
            f"--- stdout ---\n{result.stdout[-4000:]}\n"
            f"--- stderr ---\n{result.stderr[-4000:]}"
        )
    return result


def _failed_nodeids(pytest_output: str):
    failed, errored = set(), set()
    for match in re.finditer(
        r"^(FAILED|ERROR) (tests/\S+)", pytest_output, re.MULTILINE
    ):
        (failed if match.group(1) == "FAILED" else errored).add(
            match.group(2)
        )
    for match in re.finditer(
        r"^(tests/\S+) (FAILED|ERROR)", pytest_output, re.MULTILINE
    ):
        (failed if match.group(2) == "FAILED" else errored).add(
            match.group(1)
        )
    return failed, errored


def _outcome_map(pytest_output: str) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for match in re.finditer(
        r"^(PASSED|FAILED|ERROR|XFAIL|XFAILED|SKIPPED) (tests/\S+)",
        pytest_output, re.MULTILINE,
    ):
        outcomes[match.group(2)] = match.group(1)
    for match in re.finditer(
        r"^(tests/\S+) (PASSED|FAILED|ERROR|XFAIL|XFAILED|SKIPPED)",
        pytest_output, re.MULTILINE,
    ):
        outcomes[match.group(1)] = match.group(2)
    return outcomes


_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{32,64}$")
_HEX_IN_TEXT_RE = re.compile(r"\b[0-9a-f]{32,64}\b")


def mutation_red_set_verdict(result: dict) -> dict:
    """R1-R4: EXACT named-RED set comparison for one mutation run.

    A mutation declares a required ``named_red`` set (the semantic targets
    that MUST turn RED) and a ``tolerated_red`` set (additional nodes that MAY
    turn RED because the same defect also trips them).  The declared universe
    is required ∪ tolerated; anything RED outside it is undeclared.  The
    verdict fails closed unless:

      * at least one required node is declared (a mutation may not declare
        "nothing must fail"), and
      * EVERY required node actually turned RED (a missing hit means the
        mutation's semantic target did not detect it), and
      * NO RED node falls outside the declared universe (an extra/undeclared
        RED is a detection path nobody declared), and
      * at least one node actually turned RED (the mutation must be detected).
    """
    named = set(result.get("named_red_expected") or [])
    tolerated = set(result.get("tolerated_red") or [])
    observed = set(result.get("red_nodes") or [])
    missing = sorted(named - observed)
    undeclared = sorted(observed - named - tolerated)
    declared_but_not_red = sorted(tolerated - observed)
    failures = []
    if not named:
        failures.append("no required named-RED node declared")
    if missing:
        failures.append("missing named RED(s): " + ", ".join(missing))
    if undeclared:
        failures.append("extra/undeclared RED(s): " + ", ".join(undeclared))
    if not observed:
        failures.append("mutation produced NO RED at all")
    return {
        "named_red_required": sorted(named),
        "tolerated_red": sorted(tolerated),
        "observed_red": sorted(observed),
        "missing_named_red": missing,
        "undeclared_red": undeclared,
        "declared_but_not_red": declared_but_not_red,
        "exact_set_ok": not failures,
        "error": "; ".join(failures) or None,
    }


def assert_mutation_red_set_exact(result: dict) -> dict:
    """Fail closed when a mutation's RED set does not match its declaration."""
    verdict = mutation_red_set_verdict(result)
    if not verdict["exact_set_ok"]:
        raise RuntimeError(
            f"{result.get('mutation')!r}: named-RED set mismatch — "
            f"{verdict['error']}"
        )
    return verdict


# R1-R4: negative cases for the validator itself.  `must_raise` is what the
# validator MUST do; the harness asserts every case behaves as declared, so a
# validator that stopped failing closed (e.g. accepting 2 expected / 1 hit)
# turns the formal gate RED.
VALIDATOR_NEGATIVE_CASES: tuple[dict, ...] = (
    {
        "name": "two_expected_one_hit",
        "named": ["n1", "n2"], "tolerated": [], "observed": ["n1"],
        "must_raise": True,
    },
    {
        "name": "single_expected_zero_hits",
        "named": ["n1"], "tolerated": [], "observed": [],
        "must_raise": True,
    },
    {
        "name": "undeclared_extra_red",
        "named": ["n1", "n2"], "tolerated": [], "observed": ["n1", "n2", "x"],
        "must_raise": True,
    },
    {
        "name": "no_declaration_at_all",
        "named": [], "tolerated": [], "observed": ["n1"],
        "must_raise": True,
    },
    {
        "name": "exact_hits",
        "named": ["n1", "n2"], "tolerated": [], "observed": ["n1", "n2"],
        "must_raise": False,
    },
    {
        "name": "tolerated_red_may_fire",
        "named": ["n1", "n2"], "tolerated": ["t1"], "observed": ["n1", "n2", "t1"],
        "must_raise": False,
    },
    {
        "name": "tolerated_red_may_stay_green",
        "named": ["n1", "n2"], "tolerated": ["t1"], "observed": ["n1", "n2"],
        "must_raise": False,
    },
)


def run_validator_negative_cases() -> list[dict]:
    """Exercise the exact-set validator with synthetic results.

    Proves the validator fails closed on missing, extra/undeclared and
    absent declarations, and passes only on exact or explicitly declared
    sets.  The harness asserts ``ok`` for every case, so these become a
    formal gate rather than a comment.
    """
    results = []
    for case in VALIDATOR_NEGATIVE_CASES:
        synthetic = {
            "mutation": f"SYNTHETIC-{case['name']}",
            "named_red_expected": list(case["named"]),
            "tolerated_red": list(case["tolerated"]),
            "red_nodes": list(case["observed"]),
        }
        raised, message = False, ""
        try:
            assert_mutation_red_set_exact(synthetic)
        except RuntimeError as exc:
            raised, message = True, str(exc)
        results.append({
            "case": case["name"],
            "named_red_required": list(case["named"]),
            "tolerated_red": list(case["tolerated"]),
            "observed_red": list(case["observed"]),
            "must_raise": case["must_raise"],
            "raised": raised,
            "ok": raised == case["must_raise"],
            "message": message[:300],
        })
    return results


def _group_hex_in_text(text: str) -> str:
    """Group raw hex digests inside plain text (grouped 8-char form)."""
    return _HEX_IN_TEXT_RE.sub(
        lambda m: " ".join(
            m.group(0)[i:i + 8] for i in range(0, len(m.group(0)), 8)
        ),
        text,
    )


def _group_hex_strings(obj):
    if isinstance(obj, dict):
        return {k: _group_hex_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_group_hex_strings(v) for v in obj]
    if isinstance(obj, str) and _HEX_DIGEST_RE.fullmatch(obj):
        return " ".join(obj[i:i + 8] for i in range(0, len(obj), 8))
    return obj


class Harness:
    def __init__(self, evidence_dir, image, second_image, keep, python_exe,
                 skip_mutations, skip_regression, candidate_commit):
        self.evidence_dir = evidence_dir
        self.image = image
        self.second_image = second_image
        self.keep = keep
        self.python_exe = python_exe
        self.skip_mutations = skip_mutations
        self.skip_regression = skip_regression
        self.candidate_commit = candidate_commit.strip().lower()
        self.container = f"mpango-v3auth3-{uuid.uuid4().hex[:10]}"
        self.second_container = f"mpango-v3auth3b-{uuid.uuid4().hex[:10]}"
        self.port = _free_port()
        self.second_port = _free_port()
        self.synthetic_token = secrets.token_hex(16)
        self.admin_password = f"adm{self.synthetic_token}"
        self.migrate_password = f"mig{self.synthetic_token}"
        self.app_password = f"app{self.synthetic_token}"
        self.reporting_password = f"rep{self.synthetic_token}"
        self.second_admin_password = f"sec{self.synthetic_token}"
        self.host = "127.0.0.1"
        self.admin_url = (
            f"postgresql://postgres:{self.admin_password}"
            f"@{self.host}:{self.port}/postgres"
        )
        self.second_admin_url = (
            f"postgresql://postgres:{self.second_admin_password}"
            f"@{self.host}:{self.second_port}/postgres"
        )
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        # Work dir (secret-bearing manifests + nested BASE worktree) stays
        # OUTSIDE the repository tree and is never committed.
        import tempfile

        self.work_dir = Path(tempfile.mkdtemp(prefix="mpango_v3_r1r4_"))
        self.snapshots: dict[str, dict] = {}
        self.base_worktree: Path | None = None
        self.report = {
            "task": TASK_ID,
            "authorization": AUTHORIZATION_ID,
            "implementation_candidate_commit": self.candidate_commit,
            "r1_r3_predecessor_commit": R1_R3_PREDECESSOR_COMMIT,
            "r1_r2_predecessor_commit": R1_R2_PREDECESSOR_COMMIT,
            "historical_regression_base_commit": BASE_COMMIT,
            "started_at": _utc(),
            "image": image,
            "second_image": second_image,
            "container": self.container,
            "second_container": self.second_container,
            "port": self.port,
            "second_port": self.second_port,
            "phases": {},
        }

    # ----------------------------------------------------- identity preflight
    def preflight_identity(self) -> dict:
        """R1-R4: fail-closed evidence identity gate.

        Runs BEFORE any container is created.  Refuses (fail closed) unless
        the declared candidate commit IS the checked-out HEAD with a clean
        worktree, the immediate R1-R3 predecessor (and the frozen R1-R2 link
        behind it) are ancestors of HEAD, the candidate commit message carries
        the declared R1-R4 authorization id, and every source file's
        working-tree bytes match the committed blob (LF-normalized
        comparison; both raw digest forms are recorded).
        """
        repo_root = _run(["git", "rev-parse", "--show-toplevel"],
                         verify=True).stdout.strip()
        head = _run(["git", "rev-parse", "HEAD"], verify=True).stdout.strip()
        if head.lower() != self.candidate_commit:
            raise RuntimeError(
                "identity preflight failed: declared candidate commit "
                f"{self.candidate_commit!r} != checked-out HEAD {head!r}"
            )
        status = _run(["git", "status", "--porcelain"], verify=True).stdout
        if status.strip():
            raise RuntimeError(
                "identity preflight failed: worktree is not clean (the "
                "candidate commit must carry every source byte):\n"
                + status.strip()[:2000]
            )
        for label, ancestor in (
            ("R1-R3 predecessor", R1_R3_PREDECESSOR_COMMIT),
            ("frozen R1-R2 predecessor", R1_R2_PREDECESSOR_COMMIT),
        ):
            result = _run(["git", "merge-base", "--is-ancestor",
                           ancestor, "HEAD"])
            if result.returncode != 0:
                raise RuntimeError(
                    f"identity preflight failed: the {label} {ancestor} is "
                    "not an ancestor of HEAD"
                )
        message = _run(["git", "log", "-1", "--format=%B", "HEAD"],
                       verify=True).stdout
        if AUTHORIZATION_ID not in message:
            raise RuntimeError(
                "identity preflight failed: the candidate commit message "
                f"does not carry the authorization id {AUTHORIZATION_ID}"
            )

        root = Path(repo_root).resolve()
        digests: dict[str, dict] = {}
        for label, path in (
            ("bootstrap_script", BOOTSTRAP_SCRIPT),
            ("grants_script", GRANTS_SCRIPT),
            ("v3_suite", BACKEND_DIR / TEST_FILE),
            ("harness", Path(__file__).resolve()),
        ):
            rel_posix = path.resolve().relative_to(root).as_posix()
            blob = self._git_blob_bytes(repo_root, rel_posix)
            working_tree = path.read_bytes()
            if working_tree.replace(b"\r\n", b"\n") != blob.replace(
                b"\r\n", b"\n"
            ):
                raise RuntimeError(
                    "identity preflight failed: source digest drift on "
                    f"{rel_posix} (working tree != committed candidate)"
                )
            digests[label] = {
                "path": rel_posix,
                "worktree_sha256": hashlib.sha256(working_tree).hexdigest(),
                "blob_sha256": hashlib.sha256(blob).hexdigest(),
            }
        result = {
            "declared_candidate_commit": self.candidate_commit,
            "head_commit": head,
            "worktree_clean": True,
            "r1_r3_predecessor_ancestor": True,
            "r1_r2_predecessor_ancestor": True,
            "authorization_id_in_commit_message": True,
            "source_digests": digests,
        }
        print(f"[identity] candidate {head[:12]} == HEAD, worktree clean, "
              f"predecessors {R1_R3_PREDECESSOR_COMMIT[:12]} / "
              f"{R1_R2_PREDECESSOR_COMMIT[:12]} are ancestors, "
              "authorization id present, 4 source digests match committed "
              "blobs")
        return result

    @staticmethod
    def _git_blob_bytes(repo_root: str, rel_posix: str) -> bytes:
        outcome = subprocess.run(
            ["git", "show", f"HEAD:{rel_posix}"], cwd=repo_root,
            capture_output=True, timeout=120,
        )
        if outcome.returncode != 0:
            raise RuntimeError(
                f"identity preflight failed: cannot read HEAD:{rel_posix}: "
                f"{outcome.stderr.decode(errors='replace')[-500:]}"
            )
        return outcome.stdout

    # ------------------------------------------------------------- containers
    def _start_container(self, name, image, port, password):
        _run(["docker", "run", "--name", name,
              "-e", f"POSTGRES_PASSWORD={password}",
              "-p", f"127.0.0.1:{port}:5432", "-d", image],
             verify=True, label=f"docker run {name}")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            probe = _run(["docker", "exec", name, "pg_isready",
                          "-U", "postgres", "-d", "postgres"])
            if probe.returncode == 0:
                return
            time.sleep(1)
        raise RuntimeError(f"container {name} did not become ready")

    def start_containers(self) -> None:
        self._start_container(
            self.container, self.image, self.port, self.admin_password
        )
        self._start_container(
            self.second_container, self.second_image, self.second_port,
            self.second_admin_password,
        )
        version = _run(["docker", "exec", self.container, "psql", "-U",
                        "postgres", "-tAc",
                        "SHOW server_version_num;"], verify=True)
        cluster = _run(["docker", "exec", self.container, "psql", "-U",
                        "postgres", "-tAc",
                        "SELECT system_identifier FROM pg_control_system();"],
                       verify=True)
        second_cluster = _run(
            ["docker", "exec", self.second_container, "psql", "-U",
             "postgres", "-tAc",
             "SELECT system_identifier FROM pg_control_system();"],
            verify=True,
        )
        self.report["server_version_num"] = version.stdout.strip()
        self.report["cluster_system_identifier"] = cluster.stdout.strip()
        self.report["second_cluster_system_identifier"] = (
            second_cluster.stdout.strip()
        )
        assert cluster.stdout.strip() != second_cluster.stdout.strip(), \
            "the two containers must be DIFFERENT clusters"
        print(f"[container] main cluster {cluster.stdout.strip()} + second "
              f"cluster {second_cluster.stdout.strip()} ready")

    def stop_containers(self) -> None:
        _run(["docker", "rm", "-f", self.container])
        _run(["docker", "rm", "-f", self.second_container])

    # ----------------------------------------------------------- provisioning
    def _urls(self, database):
        common = f"{self.host}:{self.port}/{database}"
        return (
            f"postgresql://{MIGRATE_ROLE}:{self.migrate_password}@{common}",
            f"postgresql://{APP_ROLE}:{self.app_password}@{common}",
            database,
        )

    def provision_database(self, database):
        migrate_url, app_url, _ = self._urls(database)
        result = _run(
            [self.python_exe, "scripts/provision_runtime_db_roles.py",
             "--provision",
             "--admin-url", self.admin_url,
             "--migrate-url", migrate_url, "--app-url", app_url],
            env={
                "MPANGO_DB_ADMIN_URL": self.admin_url,
                "MPANGO_DB_MIGRATE_URL": migrate_url,
                "MPANGO_DB_APP_URL": app_url,
                "MPANGO_DB_MIGRATE_PASSWORD": self.migrate_password,
                "MPANGO_DB_APP_PASSWORD": self.app_password,
            },
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"provision {database} failed\n{result.stdout[-3000:]}\n"
                f"{result.stderr[-3000:]}"
            )
        print(f"[provision] {database}: roles + database wired "
              "(binding-preflighted)")

    def apply_grants(self, database):
        # Grants (incl. EXECUTE on the guard) require migrations to have run.
        migrate_url, app_url, _ = self._urls(database)
        result = _run(
            [self.python_exe, "scripts/provision_runtime_db_roles.py",
             "--apply-grants",
             "--admin-url", self.admin_url,
             "--migrate-url", migrate_url, "--app-url", app_url],
            env={
                "MPANGO_DB_ADMIN_URL": self.admin_url,
                "MPANGO_DB_MIGRATE_URL": migrate_url,
                "MPANGO_DB_APP_URL": app_url,
            },
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"apply grants {database} failed\n{result.stdout[-3000:]}\n"
                f"{result.stderr[-3000:]}"
            )
        print(f"[grants] {database}: minimum grants applied AS {MIGRATE_ROLE}")

    def run_migrations(self, database):
        migrate_url, _, _ = self._urls(database)
        result = _run(
            [self.python_exe, "-m", "alembic", "-c", "alembic.ini",
             "upgrade", "head"],
            env={"DATABASE_URL": migrate_url,
                 "REPORTING_USER_PASSWORD": self.reporting_password},
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"alembic upgrade head as {MIGRATE_ROLE} on {database} "
                f"failed\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}"
            )
        head = _run(["docker", "exec", self.container, "psql", "-U",
                     "postgres", "-d", database, "-tAc",
                     "SELECT version_num FROM public.alembic_version"],
                    verify=True)
        print(f"[migrate] {database}: head={head.stdout.strip()} (AS "
              f"{MIGRATE_ROLE})")
        return head.stdout.strip()

    def run_tool_verify(self, database, *, expect_ok):
        migrate_url, app_url, _ = self._urls(database)
        admin_scenario = self.admin_url.rsplit("/", 1)[0] + "/" + database
        result = _run(
            [self.python_exe, "scripts/provision_runtime_db_roles.py",
             "--verify", "--admin-url", admin_scenario,
             "--migrate-url", migrate_url, "--app-url", app_url],
            env={"MPANGO_DB_ADMIN_URL": admin_scenario,
                 "MPANGO_DB_MIGRATE_URL": migrate_url,
                 "MPANGO_DB_APP_URL": app_url},
        )
        content = _group_hex_in_text(
            f"rc={result.returncode}\n\n{result.stdout}\n{result.stderr}"
        )
        (self.evidence_dir / f"verify_{database}.txt").write_text(
            content, encoding="utf-8",
        )
        ok = result.returncode == 0
        if ok != expect_ok:
            raise RuntimeError(
                f"--verify on {database}: expected ok={expect_ok}, got "
                f"rc={result.returncode}\n{result.stdout[-2500:]}"
            )
        print(f"[verify] {database}: rc={result.returncode} "
              f"(expected {'0' if expect_ok else 'non-zero'})")

    def induce_breakage(self, database, scenario):
        statements = {
            "v3_nofunc": [
                "DROP FUNCTION public.prevent_ledger_modification()",
            ],
            "v3_badsig": [
                "DROP FUNCTION public.prevent_ledger_modification()",
                "CREATE FUNCTION public.prevent_ledger_modification() "
                "RETURNS void AS $$ BEGIN END $$ LANGUAGE plpgsql",
            ],
            "v3_wrongown": [
                "ALTER FUNCTION public.prevent_ledger_modification() "
                f"OWNER TO {APP_ROLE}",
            ],
            "v3_verify_wrongown": [
                "ALTER FUNCTION public.prevent_ledger_modification() "
                f"OWNER TO {APP_ROLE}",
            ],
            "v3_nopriv": [
                "REVOKE EXECUTE ON FUNCTION "
                "public.prevent_ledger_modification() FROM PUBLIC",
                "REVOKE EXECUTE ON FUNCTION "
                f"public.prevent_ledger_modification() FROM {APP_ROLE}",
            ],
        }.get(scenario, [])
        if not statements:
            return
        # admin (superuser) induces the DBA-level misconfiguration; connected
        # to the SCENARIO database.
        url = self.admin_url.rsplit("/", 1)[0] + "/" + database

        async def _apply():
            conn = await asyncpg.connect(url)
            try:
                for statement in statements:
                    await conn.execute(statement)
            finally:
                await conn.close()

        asyncio.run(_apply())
        print(f"[breakage] {database}: induced {scenario}")

    def snapshot_guard(self, database):
        migrate_url, _, _ = self._urls(database)

        async def _snapshot():
            conn = await asyncpg.connect(migrate_url)
            try:
                row = await conn.fetchrow(
                    "SELECT (to_regprocedure("
                    "'public.prevent_ledger_modification()') IS NOT NULL) "
                    "AS function_exists, "
                    "pg_get_userbyid(p.proowner) AS owner, "
                    "format_type(p.prorettype, NULL) AS return_type, "
                    "pg_get_function_identity_arguments(p.oid) AS args, "
                    "md5(pg_get_functiondef(p.oid)) AS definition_md5, "
                    "p.oid::bigint AS function_oid "
                    "FROM pg_proc p "
                    "LEFT JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE (p.oid = to_regprocedure("
                    "'public.prevent_ledger_modification()')) "
                    "OR p.oid IS NULL LIMIT 1"
                )
                return dict(row) if row else {"function_exists": False}
            finally:
                await conn.close()

        return asyncio.run(_snapshot())

    # ----------------------------------------------------------------- suite
    def _write_manifest(self, label, active):
        manifest = {
            "active_scenario": active,
            "cluster_system_identifier":
                self.report.get("cluster_system_identifier"),
            "second_cluster": {
                "system_identifier":
                    self.report.get("second_cluster_system_identifier"),
                "admin_url": self.second_admin_url,
            },
            "admin_url": self.admin_url,
            "scenarios": {},
        }
        for name in SCENARIOS:
            migrate, app, database = self._urls(name)
            manifest["scenarios"][name] = {
                "migrate_url": migrate,
                "app_url": app,
                "database": database,
                "guard": self.snapshots.get(name, {}),
            }
        path = self.work_dir / f"manifest_{label}.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return path

    def run_suite(self, scenario, *, label, backend_dir=None):
        backend = backend_dir or BACKEND_DIR
        _, app_url, _ = self._urls(scenario)
        manifest_path = self._write_manifest(label, scenario)
        outcome = subprocess.run(
            [self.python_exe, "-m", "pytest", TEST_FILE, "-v",
             "--no-header", "-rA", "--tb=short"],
            env={
                **os.environ,
                "DATABASE_URL": app_url,
                "MPANGO_ENV": "test",
                "MPANGO_MIGRATION_AUTHORITY_ROLE": MIGRATE_ROLE,
                "MPANGO_DB_APP_ROLE": APP_ROLE,
                "MPANGO_DB_AUTHORITY_MANIFEST": str(manifest_path),
                "MPANGO_DB_AUTHORITY_SCENARIO": scenario,
                "REPORTING_USER_PASSWORD": self.reporting_password,
            },
            cwd=str(backend), capture_output=True, text=True, timeout=1200,
            encoding="utf-8", errors="replace",
        )
        output_path = self.evidence_dir / f"pytest_{label}.txt"
        # Mutation-run logs may legitimately contain a leaked diagnostic
        # (that is what the leak detectors caught); the synthetic secret
        # material is masked in place so evidence shows the leak location
        # without carrying the secret.
        masked = (
            f"{outcome.stdout}\n{outcome.stderr}"
        ).replace(
            self.synthetic_token, "***SYNTHETIC-SECRET-REDACTED***"
        ).replace(
            _group_hex_in_text(self.synthetic_token),
            "***SYNTHETIC-SECRET-REDACTED***",
        )
        output_path.write_text(
            f"$ pytest {TEST_FILE} (scenario={scenario}, label={label}, "
            f"backend={backend})\nrc={outcome.returncode}\n\n{masked}",
            encoding="utf-8",
        )
        failed, errored = _failed_nodeids(outcome.stdout)
        summary = {
            "scenario": scenario, "label": label, "rc": outcome.returncode,
            "failed": sorted(failed), "errors": sorted(errored),
            "log": output_path.name,
        }
        print(f"[suite] {label}: rc={outcome.returncode} failed={len(failed)} "
              f"errors={len(errored)}")
        return summary

    # -------------------------------------------------------------- mutation
    def _patch(self, path: Path, old_lf: str, new_lf: str) -> None:
        text = path.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in text else "\n"

        def _to_eol(sample: str) -> str:
            return sample.replace("\n", eol) if eol != "\n" else sample

        old, new = _to_eol(old_lf), _to_eol(new_lf)
        if old not in text:
            raise RuntimeError(
                f"mutation anchor not found in {path.name}: {old_lf[:80]!r}"
            )
        path.write_bytes(text.replace(old, new, 1).encode("utf-8"))

    def run_mutations(self):
        results = []
        originals = {
            "bootstrap": BOOTSTRAP_SCRIPT.read_bytes(),
            "grants": GRANTS_SCRIPT.read_bytes(),
        }
        original_shas = {
            "bootstrap": _sha256(BOOTSTRAP_SCRIPT),
            "grants": _sha256(GRANTS_SCRIPT),
        }
        self.report["bootstrap_script_sha256"] = original_shas["bootstrap"]
        self.report["grants_script_sha256"] = original_shas["grants"]
        paths = {"bootstrap": BOOTSTRAP_SCRIPT, "grants": GRANTS_SCRIPT}

        if self.skip_mutations:
            return results
        try:
            for mutation in MUTATIONS:
                # Restore whatever the previous mutation left before applying
                # the next one: every mutation run must be ISOLATED (only its
                # own semantic mutation active).
                BOOTSTRAP_SCRIPT.write_bytes(originals["bootstrap"])
                GRANTS_SCRIPT.write_bytes(originals["grants"])
                self._patch(
                    paths[mutation["file"]],
                    mutation["anchor"], mutation["replacement"],
                )
                mutated_sha = _sha256(paths[mutation["file"]])
                run = self.run_suite(
                    mutation["scenario"], label=f"mutation_{mutation['name']}"
                )
                red_nodes = set(run["failed"]) | set(run["errors"])
                named_hits = sorted(red_nodes & set(mutation["named_red"]))
                results.append({
                    "mutation": mutation["name"],
                    "title": mutation["title"],
                    "scenario": mutation["scenario"],
                    "rationale": mutation["rationale"],
                    "named_red_expected": mutation["named_red"],
                    "tolerated_red": list(mutation.get("tolerated_red", [])),
                    "mutated_file": mutation["file"],
                    "mutated_sha256": mutated_sha,
                    "run": run,
                    "red_nodes": sorted(red_nodes),
                    "went_red": run["rc"] != 0 and bool(red_nodes),
                    "named_red_hits": named_hits,
                })
                print(f"[mutation] {mutation['name']}: went_red="
                      f"{run['rc'] != 0} named={named_hits}")
        finally:
            BOOTSTRAP_SCRIPT.write_bytes(originals["bootstrap"])
            GRANTS_SCRIPT.write_bytes(originals["grants"])
            restored = {
                "bootstrap": _sha256(BOOTSTRAP_SCRIPT),
                "grants": _sha256(GRANTS_SCRIPT),
            }
            byte_identical = (
                restored["bootstrap"] == original_shas["bootstrap"]
                and restored["grants"] == original_shas["grants"]
            )
            for result in results:
                result["restored_sha256"] = restored[result["mutated_file"]]
                result["byte_identical_restore"] = byte_identical
            if not byte_identical:
                raise RuntimeError("restore was not byte-identical")
            print(f"[mutation] both scripts restored byte-identical "
                  f"(bootstrap={restored['bootstrap'][:12]}..., "
                  f"grants={restored['grants'][:12]}...)")

        post = self.run_suite("v3_ok", label="post_restore")
        results.append({
            "mutation": None, "title": "post_restore_reproducibility",
            "run": post, "post_restore_green": post["rc"] == 0,
        })
        print(f"[mutation] post-restore v3_ok green={post['rc'] == 0}")
        return results

    # ------------------------------------------------------------ regression
    def _prepare_regression_database(self, database):
        # Two-role topology identical for BASE and candidate: authority owns
        # everything; the suite connects as the runtime role; the declared
        # authority env matches the derived database owner for both branches.
        self.provision_database(database)
        self.run_migrations(database)
        self.apply_grants(database)
        _, app_url, _ = self._urls(database)
        return app_url

    def _run_regression_set(self, backend_dir: Path, app_url: str,
                            label: str):
        outcome = subprocess.run(
            [self.python_exe, "-m", "pytest", *REGRESSION_FILES,
             "-q", "-p", "no:warnings", "--tb=no", "-rA"],
            env={
                **os.environ,
                "DATABASE_URL": app_url,
                "TEST_DATABASE_URL": app_url,
                "MPANGO_ENV": "test",
                "MPANGO_MIGRATION_AUTHORITY_ROLE": MIGRATE_ROLE,
                "REPORTING_USER_PASSWORD": self.reporting_password,
                "MPANGO_ALLOW_TEMP_DB_CREATE": "1",
                "MPANGO_TEMP_DB_ALLOWED_HOSTS": "127.0.0.1",
                "MPANGO_TEMP_DB_ALLOWED_PORTS": str(self.port),
            },
            cwd=str(backend_dir), capture_output=True, text=True,
            timeout=1800, encoding="utf-8", errors="replace",
        )
        (self.evidence_dir / f"regression_{label}.txt").write_text(
            f"rc={outcome.returncode}\n\n{outcome.stdout[-120000:]}\n"
            f"{outcome.stderr[-4000:]}",
            encoding="utf-8",
        )
        outcomes = _outcome_map(outcome.stdout)
        print(f"[regression] {label}: rc={outcome.returncode} "
              f"nodes={len(outcomes)}")
        return {"rc": outcome.returncode, "outcomes": outcomes}

    def run_regression(self):
        if self.skip_regression:
            return {"skipped": True}
        repo_root = _run(["git", "rev-parse", "--show-toplevel"],
                         verify=True).stdout.strip()
        base_dir = self.work_dir / "base_worktree"
        if base_dir.exists():
            _run(["git", "worktree", "remove", "--force", str(base_dir)])
        _run(["git", "worktree", "add", "--detach", str(base_dir),
              BASE_COMMIT], verify=True, label="worktree add BASE")
        self.base_worktree = base_dir

        base_app = self._prepare_regression_database("reg_base")
        cand_app = self._prepare_regression_database("reg_cand")

        base_run = self._run_regression_set(
            base_dir / "backend", base_app, "base"
        )
        cand_run = self._run_regression_set(BACKEND_DIR, cand_app, "candidate")

        base_out, cand_out = base_run["outcomes"], cand_run["outcomes"]
        deltas = []
        for node in sorted(set(base_out) | set(cand_out)):
            if base_out.get(node) != cand_out.get(node):
                deltas.append({
                    "node": node,
                    "base": base_out.get(node),
                    "candidate": cand_out.get(node),
                })
        report = {
            "base_rc": base_run["rc"], "candidate_rc": cand_run["rc"],
            "base_nodes": len(base_out), "candidate_nodes": len(cand_out),
            "deltas": deltas, "identical": not deltas,
        }
        print(f"[regression] base={len(base_out)} nodes, "
              f"candidate={len(cand_out)} nodes, deltas={len(deltas)}")
        return report

    # ------------------------------------------------------------------ main
    def run(self):
        try:
            # R1-R4: the exact-set validator must itself fail closed.  Proven
            # on EVERY invocation, before any container starts, so a
            # validator that stopped rejecting a 2-expected/1-hit declaration
            # turns the formal gate RED instead of silently passing.
            validator_cases = run_validator_negative_cases()
            failed_cases = [c for c in validator_cases if not c["ok"]]
            assert not failed_cases, (
                "named-RED set validator did not fail closed on: "
                + ", ".join(c["case"] for c in failed_cases)
            )
            self.report["validator_negative_cases"] = validator_cases
            print(f"[validator] {len(validator_cases)} negative/positive cases "
                  "behaved as declared")
            # R1-R3 fix 2: identity preflight strictly BEFORE any container.
            self.report["identity_preflight"] = self.preflight_identity()
            self.start_containers()
            heads = {}
            for scenario in SCENARIOS:
                self.provision_database(scenario)
            for scenario in SCENARIOS:
                heads[scenario] = self.run_migrations(scenario)
            for scenario in SCENARIOS:
                self.apply_grants(scenario)
            # tool --verify: must be GREEN on the intact database and RED on
            # the wrong-owner counterexample (fix 2), strictly read-only.
            self.run_tool_verify("v3_ok", expect_ok=True)
            for scenario in SCENARIOS:
                self.induce_breakage(scenario, scenario)
            self.run_tool_verify("v3_verify_wrongown", expect_ok=False)
            for scenario in SCENARIOS:
                self.snapshots[scenario] = self.snapshot_guard(scenario)

            suite_runs = []
            for scenario in SCENARIOS:
                suite_runs.append(self.run_suite(scenario, label=scenario))
            for run in suite_runs:
                assert run["rc"] == 0, (
                    f"scenario {run['scenario']} did not pass: "
                    f"failed={run['failed']} errors={run['errors']}"
                )

            mutation_results = self.run_mutations()
            # R1-R4: EXACT named-RED set verification.  Missing declared
            # REDs, extra/undeclared REDs and mutations that declare nothing
            # all fail closed here (previously only "at least one hit").
            red_set_verdicts = []
            for result in mutation_results:
                if result.get("mutation"):
                    assert result["went_red"], (
                        f"{result['mutation']} did NOT go RED"
                    )
                    red_set_verdicts.append(
                        assert_mutation_red_set_exact(result)
                    )
                else:
                    assert result["post_restore_green"], (
                        "post-restore run is not green"
                    )
            self.report["phases"]["mutation_red_set_verdicts"] = (
                red_set_verdicts
            )

            regression = self.run_regression()
            if not regression.get("skipped"):
                assert regression["identical"], (
                    "regression per-node outcomes differ between BASE and "
                    f"candidate: {regression['deltas'][:10]}"
                )

            # R1-R2 fix 5: synthetic-secret leak scan over EVERY evidence
            # file — every password embeds the token, so any occurrence
            # means a credential leaked into a diagnostic.
            scan = self._scan_evidence_for_secrets()
            assert scan["files_containing_secret"] == 0, (
                "SYNTHETIC SECRET LEAKED into "
                f"{scan['files_containing_secret']} evidence file(s)"
            )
            self.report["synthetic_secret_scan"] = scan

            self.report["phases"] = {
                "alembic_heads": heads,
                "suite_runs": suite_runs,
                "mutations": mutation_results,
                "regression": regression,
                "guard_snapshots": self.snapshots,
                "bootstrap_script_sha256_restored": _sha256(BOOTSTRAP_SCRIPT),
                "grants_script_sha256_restored": _sha256(GRANTS_SCRIPT),
                "finished_at": _utc(),
            }
            self.report["verdict"] = "PASS"
            return self.report
        except Exception as exc:  # noqa: BLE001
            self.report["verdict"] = "FAIL"
            self.report["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            try:
                if self.base_worktree and self.base_worktree.exists():
                    _run(["git", "worktree", "remove", "--force",
                          str(self.base_worktree)])
                if not self.keep:
                    self.stop_containers()
                # R1-R4: never leave the synthetic-credential work dir behind.
                self._cleanup_work_dir()
            except Exception as exc:  # noqa: BLE001 - cleanup must not mask
                print(f"[cleanup] warning: {type(exc).__name__}: {exc}")
            finally:
                self._write_report()

    def _cleanup_work_dir(self) -> None:
        """Remove the run work dir, which holds secret-bearing manifests.

        Every password embeds the per-run synthetic token, so the default is
        removal; ``--keep`` deliberately RETAINS the directory for debugging
        and reports its path (isolated and declared, never silently left).
        """
        import shutil

        if not self.work_dir.exists():
            self.report["work_dir_disposition"] = "already-absent"
            return
        if self.keep:
            self.report["work_dir_disposition"] = (
                f"retained (--keep): {self.work_dir}"
            )
            print(f"[cleanup] --keep: work dir retained at {self.work_dir}")
            return
        shutil.rmtree(self.work_dir, ignore_errors=True)
        disposition = "removed" if not self.work_dir.exists() else "remove-failed"
        self.report["work_dir_disposition"] = disposition
        print(f"[cleanup] work dir {disposition}")

    def _scan_evidence_for_secrets(self) -> dict:
        """Scan every evidence file for the synthetic secret token."""
        files = 0
        leaking = []
        for path in sorted(self.evidence_dir.rglob("*")):
            if path.is_file():
                files += 1
                if self.synthetic_token in path.read_text(
                    encoding="utf-8", errors="replace"
                ):
                    leaking.append(path.name)
        return {
            "files_scanned": files,
            "files_containing_secret": len(leaking),
            "leaking_files": leaking,
        }

    def _write_report(self):
        # R1-R3 fix 2: refuse to publish a machine-generated report whose
        # identity does not match this round before it is written.
        mismatches = [
            f"{field}: report={self.report.get(field)!r} expected={expected!r}"
            for field, expected in (
                ("task", TASK_ID),
                ("authorization", AUTHORIZATION_ID),
                ("implementation_candidate_commit", self.candidate_commit),
            )
            if self.report.get(field) != expected
        ]
        if mismatches:
            raise RuntimeError(
                "report identity validation failed (refusing to publish a "
                "mis-identified harness report): " + "; ".join(mismatches)
            )
        payload = json.loads(json.dumps(self.report, default=str))
        blob = json.dumps(_group_hex_strings(payload), indent=2)
        for secret in (self.admin_password, self.migrate_password,
                       self.app_password, self.reporting_password,
                       self.second_admin_password):
            blob = blob.replace(secret, "***REDACTED***")
        blob = re.sub(r"(postgresql://[^:/\"]+:)[^@\"]+@", r"\1***@", blob)
        target = self.evidence_dir / "harness_report.json"
        target.write_text(blob, encoding="utf-8")
        print(f"[evidence] wrote {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument(
        "--candidate-commit", required=True,
        help="exact implementation candidate commit the run must be "
             "executed against (must equal HEAD with a clean worktree; "
             "enforced by the fail-closed identity preflight)",
    )
    parser.add_argument("--image", default=IMAGE_MAIN)
    parser.add_argument("--second-image", default=IMAGE_SECOND)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--skip-mutations", action="store_true")
    parser.add_argument("--skip-regression", action="store_true")
    args = parser.parse_args()

    harness = Harness(
        evidence_dir=args.evidence_dir, image=args.image,
        second_image=args.second_image, keep=args.keep,
        python_exe=args.python, skip_mutations=args.skip_mutations,
        skip_regression=args.skip_regression,
        candidate_commit=args.candidate_commit,
    )
    report = harness.run()
    print(f"HARNESS {report['verdict']}")


if __name__ == "__main__":
    main()
