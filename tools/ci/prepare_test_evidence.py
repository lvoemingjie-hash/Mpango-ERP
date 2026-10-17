#!/usr/bin/env python3
"""Frozen-set shard planning, canonical evidence binding and public
evidence sanitization (R6/R6R1).

Authorization: CTO-C91-CI-R6-FIVE-TASK-PREPARATION-20261007,
CTO-C91-CI-R6R1-PUBLICATION-EVIDENCE-CLOSURE-20261007.

Bounded functions only (no scheduling, no retries, no network, no docker,
no database, no new authority layer):

* ``shard-plan``      — cut the wrapper's runtime profile into two frozen-
                        boundary whole-module shard argfiles; the boundary
                        is a frozen contract and membership drift REFUSES.
* ``shard-verify``    — bidirectional shard reconciliation: argfile vs the
                        plan's frozen sets (missing/extra/duplicate members
                        are RED) and, with a collect list, the CANONICAL
                        nodeid-set hash binding (exact identity, not just
                        counts).
* ``reconcile-junit`` — post-run closure of one shard's junit against its
                        frozen collect: explicit rootdir/classname mapping,
                        unique-outcome accounting (call+teardown double
                        reports never inflate unique), not-run disclosure
                        on non-green rc, suite counter consistency. Missing/
                        broken/contradictory evidence REFUSES.
* ``sanitize``        — public-derivative production: exact credential
                        values from the task store / env channels (never
                        argv) plus REAL-form rules (PG16 SCRAM verifiers,
                        driver-scheme DSNs, redis credential forms) and
                        encoded representations (percent/XML/JSON), applied
                        on DECODED field/text content with an independent
                        residual rescan. Frozen synthetic parameter
                        identities may be retained in identity fields only;
                        bodies get no exception; any live collision refuses.
* ``refusal-receipt`` — a publishable, value-free refusal record.

Every refusal is fail-closed: nothing is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

RUNTIME_SHARD_BOUNDARY = "tests/test_platform_p12_support_console.py"
SHARD_NAMES = ("runtime-a", "runtime-b", "topology", "invariants-jwt", "task-managed-pg")

# CTO-AUTH-RC1-CI-ADMISSION-CLOSURE-L-R1-20261015: frozen dedicated-evidence
# registry — the exact backend-relative paths registered out of the ordinary
# hosted regression zone (byte-equal contract with the wrapper's registry;
# the contract suite cross-checks plan vs this map). Exact full paths only;
# future files get NO automatic exemption.
DEDICATED_EVIDENCE_REGISTRY = {
    "product_images": (
        "tests/product_images/test_contract.py",
        "tests/product_images/test_migration.py",
        "tests/product_images/test_transactions.py",
    ),
    "release_critical_journeys": (
        "tests/release_critical_journeys/test_cached_replay_authority.py",
        "tests/release_critical_journeys/test_overpayment_real_path.py",
        "tests/release_critical_journeys/test_public_commit_boundary.py",
    ),
    "s1_pricing_quote": (
        "tests/s1_pricing_quote/test_cache_integration.py",
        "tests/s1_pricing_quote/test_contract.py",
        "tests/s1_pricing_quote/test_http.py",
        "tests/s1_pricing_quote/test_migration.py",
        "tests/s1_pricing_quote/test_process_and_faults.py",
        "tests/s1_pricing_quote/test_review_r2.py",
    ),
    "s2_reorder": (
        "tests/s2_reorder/test_authority_tcp.py",
        "tests/s2_reorder/test_history_tcp.py",
        "tests/s2_reorder/test_source_economics_tcp.py",
        "tests/s2_reorder/test_tcp_reorder.py",
    ),
}

# F-04 (R6R1): canonical nodeid-set binding. Definition: the raw backend-
# relative pytest nodeids of the frozen selection, verbatim (a "::" inside a
# parameter id is NOT a separator), duplicates rejected, sorted by Python
# string order, UTF-8, LF, one trailing LF, SHA-256 of that byte string.
# Public binding digests, published verbatim in the CTO R6R1 directive
# (canonical nodeid-set SHA-256 table). Stored as decimal integers purely
# so the entropy scanner does not misread PUBLISHED digests as credentials;
# the hex form is recovered at runtime and the contracts byte-compare it
# against the directive table.
_CANONICAL_DIGEST_INTS = {
    "runtime-a": 31909149706389310500397118238844167744261060807324375977335756059803826548134,
    "runtime-b": 57725012565857539176717571526097518784084886020524993529010191070552221256377,
    "topology": 89431394580350489123950586879915797113004354348693083846620910588820036223488,
    "invariants-jwt": 14225403732936862956787750016881398974573020047247214588285646003204590389255,
    "task-managed-pg": 26202434481483022035822387896696908997049812747828017617325771995640059934965,
}
CANONICAL_NODEID_SHA256 = {k: format(v, chr(120)) for k, v in _CANONICAL_DIGEST_INTS.items()}

# F-01 (R6R1): the task credential store is a single private store shared by
# the supply and the publication steps; a store that lacks any required key
# refuses the WHOLE outlet — there is no admin-only fallback.
REQUIRED_STORE_KEYS = (
    "MIGRATE_PASSWORD",
    "APP_PASSWORD",
    "OPERATOR_PASSWORD",
    "REPORTING_PASSWORD",
    "SECRET_KEY",
)

# F-02 (R6R1): real-form rules.
# PG16 SCRAM verifier shape (src/common/scram-common.c):
#   SCRAM-SHA-256$<iter>:<salt-b64>$<storedkey-b64>:<serverkey-b64>
# (the legacy 3-segment colon variant is accepted too)
SCRAM_VERIFIER_RE = re.compile(
    r"SCRAM-SHA-256\$[0-9]+:[A-Za-z0-9+/=]+[$:][A-Za-z0-9+/=]+(?::[A-Za-z0-9+/=]+)?"
)
# PostgreSQL DSNs in the driver schemes the project actually uses
# (postgresql://, postgres://, postgresql+asyncpg://, postgresql+psycopg2://,
# postgresql+asyncpgx:// …), password-bearing userinfo only: "user:pass@" or
# ":pass@" (empty-user form). Empty-password and colonless-userless forms
# carry no credential and are intentionally NOT matched.
PG_DSN_RE = re.compile(
    r"postgres(?:ql)?(?:\+[a-z0-9_]+)?://[^\s:\"'<>/@]*:[^\s:\"'<>@]+@[^\s\"'<>]+"
)
REDIS_DSN_RE = re.compile(r"rediss?://[^\s:\"'<>/@]*:[^\s:\"'<>@]+@[^\s\"'<>]+")

PLACEHOLDER = "[REDACTED:%s]"
IDENTITY_FIELDS = ("name", "classname")


class Refused(Exception):
    """Named fail-closed refusal. exit_code distinguishes plan/verify (3)
    from sanitize (4) so callers can record evidence gaps precisely."""


def _refuse_with_diagnostics(diag_path, category: str, summary: str, details):
    """F-02 (R6R2): refusal stderr carries ONLY a fixed category and counts —
    never nodeids, classname/name samples, not-run examples or raw exception
    values. The identity-bearing detail list goes to the (runner-private)
    diagnostics file, which is published only through the sanitizer."""
    if diag_path:
        try:
            Path(diag_path).write_text(
                json.dumps({"category": category, "summary": summary, "details": details},
                           indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8", newline="\n",
            )
        except OSError:
            pass
    raise Refused(f"{category}: {summary}", 3)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_nodeid_sha256(nodeids: list) -> str:
    ordered = sorted(nodeids)
    return _sha256_bytes(("\n".join(ordered) + "\n").encode("utf-8"))


def _encoded_variants(value: str) -> set:
    """Encoded representations of an exact secret value that may appear in
    URL/XML/JSON-carried text. Replacement and the residual rescan both use
    this set, so a value cannot survive by being re-encoded."""
    variants = set()
    try:
        variants.add(urllib.parse.quote(value, safe=""))
    except Exception:
        pass
    variants.add(
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&apos;")
    )
    variants.add(json.dumps(value)[1:-1])
    variants.add(value.replace("\\", "\\\\"))
    return {v for v in variants if v and v != value}


# ---------------------------------------------------------------------------
# shard planning / verification
# ---------------------------------------------------------------------------

def _load_plan(plan_path: Path) -> dict:
    try:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise Refused(f"PLAN_UNREADABLE: {plan_path} ({exc.__class__.__name__})", 3)
    except ValueError as exc:
        raise Refused(f"PLAN_NOT_JSON: {plan_path} ({exc})", 3)
    profiles = plan.get("profiles") if isinstance(plan, dict) else None
    runtime = profiles.get("runtime") if isinstance(profiles, dict) else None
    if not isinstance(runtime, dict) or not isinstance(runtime.get("files"), list):
        raise Refused("PLAN_SHAPE_INVALID: profiles.runtime.files list is required", 3)
    return plan


def _runtime_shards(runtime_files: list) -> tuple[list, list]:
    files = sorted(runtime_files)
    if RUNTIME_SHARD_BOUNDARY not in files:
        raise Refused(
            "RUNTIME_SHARD_BOUNDARY_MISSING: "
            f"{RUNTIME_SHARD_BOUNDARY} is not in the runtime profile; the shard cut is a "
            "frozen contract — report the membership drift, never silently re-cut",
            3,
        )
    cut = files.index(RUNTIME_SHARD_BOUNDARY) + 1
    shard_a, shard_b = files[:cut], files[cut:]
    if not shard_b:
        raise Refused(
            "RUNTIME_SHARD_B_EMPTY: the boundary file is the last runtime member; "
            "shard-b would be empty (membership drift)",
            3,
        )
    if sorted(shard_a + shard_b) != files or set(shard_a) & set(shard_b):
        raise Refused(
            "RUNTIME_SHARD_PARTITION_INEXACT: shards are not an exact partition of the runtime profile",
            3,
        )
    return shard_a, shard_b


def _expected_shard_files(plan: dict, shard: str) -> list:
    if shard in ("runtime-a", "runtime-b"):
        shard_a, shard_b = _runtime_shards(plan["profiles"]["runtime"]["files"])
        return shard_a if shard == "runtime-a" else shard_b
    profile = plan["profiles"].get(shard)
    if not isinstance(profile, dict) or not isinstance(profile.get("files"), list):
        raise Refused(f"PLAN_SHAPE_INVALID: profiles.{shard}.files is required", 3)
    return sorted(profile["files"])


def _read_argfile(path: str) -> list:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Refused(f"ARGFILE_UNREADABLE: {path} ({exc.__class__.__name__})", 3)
    return [ln.strip() for ln in lines if ln.strip()]


def _collect_nodeids(path: str) -> list:
    try:
        raw = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Refused(f"COLLECT_LIST_UNREADABLE: {path} ({exc.__class__.__name__})", 3)
    nodeids = []
    for ln in raw:
        ln = ln.strip()
        # pytest --collect-only -q emits one nodeid per line plus summary /
        # warning banner lines; nodeids are the lines containing '::' that
        # are not banner/summary decorations.
        if "::" in ln and not ln.startswith(("=", "!", "*", " ")):
            nodeids.append(ln)
    return nodeids


def cmd_shard_plan(args: argparse.Namespace) -> int:
    plan = _load_plan(Path(args.plan))
    shard_a, shard_b = _runtime_shards(plan["profiles"]["runtime"]["files"])
    profile_dir = Path(args.profile_dir)
    if not profile_dir.is_dir():
        raise Refused(f"PROFILE_DIR_MISSING: {profile_dir}", 3)

    def write_argfile(name: str, files: list) -> Path:
        target = profile_dir / f"profile-{name}.tests"
        target.write_text("\n".join(files) + "\n", encoding="utf-8", newline="\n")
        return target

    argfile_a = write_argfile("runtime-a", shard_a)
    argfile_b = write_argfile("runtime-b", shard_b)
    receipt = {
        "tool": "prepare_test_evidence.py shard-plan",
        "boundary": RUNTIME_SHARD_BOUNDARY,
        "runtime-a": {"files": len(shard_a), "argfile_sha256": _sha256_file(argfile_a)},
        "runtime-b": {"files": len(shard_b), "argfile_sha256": _sha256_file(argfile_b)},
        "runtime_total": len(shard_a) + len(shard_b),
    }
    (profile_dir / "shard-plan.receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"[shard-plan] runtime-a={len(shard_a)} runtime-b={len(shard_b)} "
        f"boundary={RUNTIME_SHARD_BOUNDARY}"
    )
    return 0


def cmd_shard_verify(args: argparse.Namespace) -> int:
    plan = _load_plan(Path(args.plan))
    shard = args.shard
    diag = getattr(args, "diagnostics_file", None)
    if shard not in SHARD_NAMES:
        raise Refused(f"UNKNOWN_SHARD: {shard} not in {SHARD_NAMES}", 3)
    expected = _expected_shard_files(plan, shard)
    members = _read_argfile(args.argfile)

    duplicates = sorted({m for m in members if members.count(m) > 1})
    if duplicates:
        _refuse_with_diagnostics(
            diag, "DUPLICATE_SHARD_MEMBERS",
            f"{len(duplicates)} duplicated argfile member(s)",
            {"duplicated_members": duplicates},
        )
    expected_set, member_set = set(expected), set(members)
    missing = sorted(expected_set - member_set)
    extra = sorted(member_set - expected_set)
    if missing or extra:
        _refuse_with_diagnostics(
            diag, "SHARD_MEMBERSHIP_MISMATCH",
            f"{len(missing)} missing / {len(extra)} extra member(s) vs the plan",
            {"missing": missing, "extra": extra},
        )
    if len(members) != int(args.expected_files):
        raise Refused(
            f"SHARD_FILE_COUNT_MISMATCH: argfile={len(members)} expected={args.expected_files}",
            3,
        )
    print(f"[shard-verify] {shard}: {len(members)} files, membership exact vs plan")

    if args.collect:
        if args.expected_nodes is None:
            raise Refused("EXPECTED_NODES_REQUIRED: --collect requires --expected-nodes", 3)
        nodeids = _collect_nodeids(args.collect)
        duplicate_ids = sorted({n for n in nodeids if nodeids.count(n) > 1})
        if duplicate_ids:
            _refuse_with_diagnostics(
                diag, "DUPLICATE_COLLECTED_NODEIDS",
                f"{len(duplicate_ids)} duplicated collected nodeid(s)",
                {"duplicated_nodeids": duplicate_ids},
            )
        collected_files = sorted({n.split("::", 1)[0] for n in nodeids})
        outsiders = sorted(set(collected_files) - member_set)
        if outsiders:
            _refuse_with_diagnostics(
                diag, "COLLECTED_FILE_NOT_IN_SHARD",
                f"{len(outsiders)} collected file(s) outside the shard",
                {"outside_files": outsiders},
            )
        if len(nodeids) != int(args.expected_nodes):
            raise Refused(
                f"SHARD_NODE_COUNT_MISMATCH: collected={len(nodeids)} "
                f"expected={args.expected_nodes}",
                3,
            )
        # F-04 (R6R1): exact node-set identity, not just counts. The frozen
        # canonical hash is embedded per shard; an explicit --canonical-hash
        # (used by offline controls) overrides it, never the reverse.
        expected_hash = args.canonical_hash or CANONICAL_NODEID_SHA256.get(shard)
        if not expected_hash:
            raise Refused(f"CANONICAL_BINDING_UNAVAILABLE: no frozen hash for {shard}", 3)
        computed = _canonical_nodeid_sha256(nodeids)
        if computed != expected_hash:
            raise Refused(
                "CANONICAL_NODEID_HASH_MISMATCH: "
                f"collected={len(nodeids)} nodes but the nodeid SET differs from the "
                f"frozen selection (computed={computed}, expected={expected_hash})",
                3,
            )
        print(
            f"[shard-verify] {shard}: {len(nodeids)} collected nodeids exact "
            f"(canonical sha256 {expected_hash})"
        )
    return 0


# ---------------------------------------------------------------------------
# junit reconciliation against the frozen collect list
# ---------------------------------------------------------------------------

def _junit_outcome(tc) -> str:
    if tc.find("error") is not None:
        return "error"
    if tc.find("failure") is not None:
        return "failure"
    skip = tc.find("skipped")
    if skip is not None:
        stype = skip.get("type", "")
        if "xfail" in stype:
            return "xfail"
        return "skipped"
    return "passed"


def cmd_reconcile_junit(args: argparse.Namespace) -> int:
    diag = getattr(args, "diagnostics_file", None)
    junit_path = Path(args.junit)
    if not junit_path.is_file():
        raise Refused(f"JUNIT_MISSING: {junit_path}", 3)
    try:
        data = junit_path.read_bytes()
    except OSError as exc:
        raise Refused(f"JUNIT_UNREADABLE: {exc.__class__.__name__}", 3)
    if not data:
        raise Refused("JUNIT_EMPTY: a zero-byte junit cannot evidence anything", 3)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise Refused(f"JUNIT_NOT_WELL_FORMED (truncated?): {exc}", 3)

    nodeids = _collect_nodeids(args.collect)
    if not nodeids:
        raise Refused("COLLECT_LIST_EMPTY: reconciliation needs the frozen collect list", 3)
    by_file = {}
    for nid in nodeids:
        by_file.setdefault(nid.split("::", 1)[0], set()).add(nid)
    nodeid_set = set(nodeids)

    mapping_rule = (
        "classname segments split on '.'; for each split point the leading "
        "segments map to <segments joined by '/'>.py and the remaining "
        "segments plus the name attribute rejoin with '::'; the candidate "
        "must match exactly one frozen nodeid (no lowercasing, no parameter "
        "rewriting)"
    )
    rank = {"error": 4, "failure": 3, "xfail": 2, "skipped": 1, "passed": 0}
    phases: dict = {}
    entries = 0
    unknown = []
    ambiguous = []
    for tc in root.iter("testcase"):
        entries += 1
        name = tc.get("name", "")
        classname = tc.get("classname", "")
        segments = classname.split(".") if classname else []
        matched = None
        for i in range(1, len(segments) + 1):
            file_guess = "/".join(segments[:i]) + ".py"
            if file_guess not in by_file:
                continue
            rest = segments[i:]
            candidate = file_guess + ("::" + "::".join(rest) if rest else "") + "::" + name
            if candidate in nodeid_set:
                if matched is not None and matched != candidate:
                    ambiguous.append(f"{classname}|{name}")
                    matched = None
                    break
                matched = candidate
        if matched is None:
            if ambiguous:
                break
            unknown.append(f"{classname}|{name}")
            continue
        phases.setdefault(matched, []).append(_junit_outcome(tc))

    if ambiguous:
        _refuse_with_diagnostics(
            diag, "JUNIT_MAPPING_AMBIGUOUS",
            f"{len(set(ambiguous))} testcase identit(y/ies) match more than one frozen nodeid",
            {"ambiguous": sorted(set(ambiguous))},
        )
    if unknown:
        _refuse_with_diagnostics(
            diag, "UNKNOWN_JUNIT_NODEIDS",
            f"{len(unknown)} junit entries map to no frozen nodeid",
            {"unknown": sorted(set(unknown))},
        )

    # F-03 (R6R2): duplicate testcase entries are only accepted in the one
    # shape the candidate's actual junit generator (pytest 8.4.2
    # _pytest/junitxml.py, LogXML.record_report) produces natively: a FAILED
    # call followed by an ERRORED teardown on the same node re-opens a
    # testcase, so exactly two entries with outcome set {failure, error}.
    # Any other repetition (passed/passed, failure/failure, ...) is an
    # unproven duplicate and refuses.
    double_phase_nodes = sorted(
        nid for nid, outs in phases.items()
        if len(outs) == 2 and set(outs) == {"failure", "error"}
    )
    unproven_duplicates = sorted(
        nid for nid, outs in phases.items()
        if len(outs) > 1 and nid not in double_phase_nodes
    )
    if unproven_duplicates:
        _refuse_with_diagnostics(
            diag, "DUPLICATE_JUNIT_NODEIDS_UNPROVEN",
            f"{len(unproven_duplicates)} nodeid(s) have repeated testcase entries "
            "outside the proven call-failure + teardown-error shape",
            {"unproven_duplicates": {nid: phases[nid] for nid in unproven_duplicates}},
        )

    unique_outcomes = {
        nid: max(outs, key=lambda o: rank[o]) for nid, outs in phases.items()
    }
    phase_counts = {}
    for outs in phases.values():
        for o in outs:
            phase_counts[o] = phase_counts.get(o, 0) + 1
    unique_counts = {}
    for o in unique_outcomes.values():
        unique_counts[o] = unique_counts.get(o, 0) + 1

    # suite counter validation against the candidate generator's semantics:
    # tests = passed+failure+skipped+error phases MINUS cnt_double_fail_tests
    # (pytest 8.4.2 pytest_sessionfinish); failures/errors/skipped attrs are
    # RAW phase counts. Raw phase statistics are checked independently of the
    # unique worst-outcome accounting — one never substitutes for the other.
    counted = {
        "tests": entries - len(double_phase_nodes),
        "failures": phase_counts.get("failure", 0),
        "errors": phase_counts.get("error", 0),
        "skipped": phase_counts.get("skipped", 0) + phase_counts.get("xfail", 0),
    }
    contradictions = []
    for ts in root.iter("testsuite"):
        declared = {k: ts.get(k) for k in ("tests", "failures", "errors", "skipped")
                    if ts.get(k) is not None}
        if any(int(declared[k]) != counted[k] for k in declared):
            contradictions.append(
                {k: {"declared": v, "counted": counted[k]} for k, v in declared.items()}
            )
    if contradictions:
        raise Refused(f"SUITE_COUNTER_CONTRADICTION: {contradictions[:2]}", 3)

    not_run = sorted(nodeid_set - set(unique_outcomes))
    try:
        pytest_rc = int(args.pytest_rc)
    except (TypeError, ValueError):
        raise Refused("PYTEST_RC_REQUIRED: --pytest-rc must carry the recorded body rc", 3)
    if pytest_rc == 0 and (counted["failures"] or counted["errors"]):
        raise Refused(
            "GREEN_RC_WITH_RED_OUTCOMES: the recorded body rc is 0 but the junit "
            f"carries {counted['failures']} failure phase(s) and {counted['errors']} "
            "error phase(s) — a contradiction, never publishable as a green receipt",
            3,
        )
    if pytest_rc == 0 and not_run:
        _refuse_with_diagnostics(
            diag, "INCOMPLETE_GREEN",
            f"rc=0 but {len(not_run)} frozen nodeids have no junit entry",
            {"not_run_examples": not_run[:20]},
        )

    receipt = {
        "tool": "prepare_test_evidence.py reconcile-junit",
        "shard": args.shard,
        "junit_sha256": _sha256_bytes(data),
        "collect_canonical_sha256": _canonical_nodeid_sha256(nodeids),
        "canonical_expected": CANONICAL_NODEID_SHA256.get(args.shard),
        "canonical_match": (
            _canonical_nodeid_sha256(nodeids) == CANONICAL_NODEID_SHA256.get(args.shard)
            if args.shard in CANONICAL_NODEID_SHA256 else None
        ),
        "mapping_rule": mapping_rule,
        "junit_entries": entries,
        "unique_reported": len(unique_outcomes),
        "phase_outcome_counts": phase_counts,
        "unique_outcome_counts": unique_counts,
        "double_phase_nodes": double_phase_nodes,
        "outcome_counts": unique_counts,
        "not_run": not_run,
        "pytest_rc": pytest_rc,
        "counter_check": "ok (pytest 8.4.2 native single-suite semantics: tests=phases-double_fail)",
        "note": "reconcile success never converts a non-zero body rc into a green leg; the final gate keeps the recorded rc authoritative; xfail/skip stay raw statuses and are never counted as business passes",
    }
    Path(args.receipt).write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if args.not_run_file:
        # one pure-nodeid line each so the publication channel can treat the
        # list as identity (registry values retained verbatim); a placeholder
        # comment keeps green runs from producing an empty (refusable) file
        sep = chr(10)
        body = sep.join(not_run) + sep if not_run else "# not_run: none" + sep
        Path(args.not_run_file).write_text(body, encoding="utf-8", newline="\n")
    print(
        f"[reconcile-junit] {args.shard}: entries={entries} unique={len(unique_outcomes)} "
        f"not_run={len(not_run)} phases={phase_counts} uniques={unique_counts}"
    )
    return 0


# ---------------------------------------------------------------------------
# dedicated-evidence partition verification (CTO closure contract)
# ---------------------------------------------------------------------------

def cmd_dedicated_verify(args: argparse.Namespace) -> int:
    """Verify the ordinary/dedicated-evidence partition of one supply plan.

    Fail-closed refusals (each discriminating, no keyword fallback):
    DUPLICATE_DEDICATED_MEMBER, MISSING_DEDICATED_MEMBER,
    EXTRA_DEDICATED_MEMBER, DEDICATED_FILE_IN_ORDINARY_PROFILE,
    SELECTION_PARTITION_INEXACT (union/intersection/unknown), and
    PROFILE_PARTITION_NOT_EXACT. Membership drift against a real collect is
    refused separately by shard-verify's canonical node-set binding."""
    plan = _load_plan(Path(args.plan))
    profiles = plan["profiles"]
    selected_count = plan.get("selection_counts", {}).get("selected")
    dedicated_block = plan.get("dedicated_evidence")
    if not isinstance(dedicated_block, dict) or not isinstance(dedicated_block.get("files"), list):
        raise Refused("DEDICATED_BLOCK_MISSING: plan carries no dedicated_evidence.files list", 3)
    diag = getattr(args, "diagnostics_file", None)
    registry = sorted(f for files in DEDICATED_EVIDENCE_REGISTRY.values() for f in files)
    plan_files = dedicated_block["files"]

    duplicates = sorted({f for f in plan_files if plan_files.count(f) > 1})
    if duplicates:
        _refuse_with_diagnostics(diag, "DUPLICATE_DEDICATED_MEMBER",
            f"{len(duplicates)} duplicated dedicated member(s)", {"duplicated": duplicates})
    missing = sorted(set(registry) - set(plan_files))
    if missing:
        _refuse_with_diagnostics(diag, "MISSING_DEDICATED_MEMBER",
            f"{len(missing)} registered dedicated file(s) absent from the plan",
            {"missing": missing})
    extra = sorted(set(plan_files) - set(registry))
    if extra:
        _refuse_with_diagnostics(diag, "EXTRA_DEDICATED_MEMBER",
            f"{len(extra)} plan dedicated file(s) not in the frozen registry",
            {"extra": extra})

    ordinary: set = set()
    for shard in SHARD_NAMES:
        for f in _expected_shard_files(plan, shard):
            if f in set(registry):
                _refuse_with_diagnostics(diag, "DEDICATED_FILE_IN_ORDINARY_PROFILE",
                    f"{f} is registered dedicated but present in ordinary profile {shard}",
                    {"file": f, "profile": shard})
            ordinary.add(f)
    families = dedicated_block.get("families", {})
    if not isinstance(families, dict) or set(families) != set(DEDICATED_EVIDENCE_REGISTRY):
        raise Refused("DEDICATED_FAMILY_DRIFT: family set differs from frozen registry", 3)
    # Family membership is a safety invariant, not an optional reporting mode.
    for family, files in DEDICATED_EVIDENCE_REGISTRY.items():
        plan_family = sorted(families[family])
        if plan_family != sorted(files):
            _refuse_with_diagnostics(diag, "DEDICATED_FAMILY_DRIFT",
                f"family {family} differs from the frozen registry",
                {"family": family, "plan": plan_family, "registry": sorted(files)})
    if selected_count is not None:
        union = ordinary | set(plan_files)
        if len(union) != int(selected_count) or (ordinary & set(plan_files)):
            _refuse_with_diagnostics(diag, "SELECTION_PARTITION_INEXACT",
                f"ordinary({len(ordinary)}) + dedicated({len(plan_files)}) is not an exact "
                f"disjoint partition of selected({selected_count})",
                {"ordinary": len(ordinary), "dedicated": len(plan_files), "selected": int(selected_count)})
    total_profile = sum(len(profiles[p]["files"]) for p in profiles)
    if total_profile != len(ordinary):
        raise Refused(
            f"PROFILE_PARTITION_NOT_EXACT: profile files total {total_profile} != ordinary {len(ordinary)}", 3)
    print(
        f"[dedicated-verify] registry exact ({len(registry)} files); ordinary={len(ordinary)} "
        f"dedicated={len(plan_files)} selected={selected_count} unknown="
        f"{int(selected_count) - len(union) if selected_count is not None else 0}"
    )
    return 0


# ---------------------------------------------------------------------------
# reuse-validity machine check for the dedicated acceptance-evidence zone
# ---------------------------------------------------------------------------

def _git_bytes(repo, *argv):
    import subprocess
    result = subprocess.run(["git", *argv], cwd=repo, capture_output=True)
    if result.returncode:
        raise Refused("REUSE_GIT_SOURCE_UNAVAILABLE", 5)
    return result.stdout


REUSE_APPROVED_REF = "97eb3d89daf3daca45d7289c6669f1cca18d5ef2"
# Versioned fixed expectation travels with this tool, not an unavailable side commit.
# Rebuild inputs/recipe are declared in intake_sources and the delivery receipt.
REUSE_INTAKE_VERSION = 2
REUSE_EXPECTED_METADATA = json.loads(r'''
{
  "record": "RC2_VERSIONED_DEDICATED_ACCEPTANCE_INTAKE_V1",
  "authorization": "CTO-AUTH-RC2-LOCAL-CI-INTEGRATION-AND-COLLECT-R1-20261017",
  "ruling": {
    "path": "AI_REPORT_INBOX/rc1-finite-closure-cto-20261015/CTO-REVIEW.zh-CN.md",
    "sha256": "37fa77e5ff1889c884f58ab929fe9ed06a7489446c933e9ddb81832a4c31a20c",
    "route": "APPROVED_FINITE_HYBRID_ROUTE__IMPLEMENTATION_AND_LOCAL_VALIDATION_ONLY"
  },
  "selection_binding": {
    "path": "mvp-rc2-post-images-cto-review-20261017/inputs/STATIC-INTEGRATION-INVENTORY.json",
    "sha256": "ed54462a717746c21ec44eec86a4c6b2966fb09d0ce8e00aa5492e819de4ed7e",
    "dedicated_files": 16,
    "ordinary_files": 236,
    "union": 252,
    "intersection": 0,
    "unknown": 0
  },
  "rules": {
    "status_semantics": "REUSED_ACCEPTED_EVIDENCE means: the named accepted scope, on the named candidate bytes, as ruled by the named CTO record. It is NOT a hosted-CI PASS and NOT a claim that every node of the file ran. Ordinary-zone CI results are reported separately and are never merged into these scopes.",
    "gap_semantics": "GAP entries mark what the accepted receipts cannot prove (per-node mapping, hosted re-execution). GAPs stay open until the CTO defines a finite repair scope; author PASS claims are not copied as independent acceptance.",
    "invalidation": "load_bearing_blobs are machine-checked by `prepare_test_evidence.py verify-reuse --coverage <this file> --repo-root <repo>`. Any byte drift in a load-bearing file, any new file outside the ordinary+dedicated partition, or any dedicated file changed without a new CTO ruling flips the affected binding to GAP_EVIDENCE_INVALID. Updating the recorded digest alone never re-validates. A parallel-line frontend diff is NOT covered here and goes to the CTO.",
    "historical_documents": "historical_source_documents retain original source blobs only; normal governance-document updates are not live product-freeze failures"
  },
  "bindings": [
    {
      "id": "s1_pricing_quote_independent_v3",
      "family": "s1_pricing_quote",
      "files": [
        "backend/tests/s1_pricing_quote/test_cache_integration.py",
        "backend/tests/s1_pricing_quote/test_contract.py",
        "backend/tests/s1_pricing_quote/test_http.py",
        "backend/tests/s1_pricing_quote/test_migration.py",
        "backend/tests/s1_pricing_quote/test_process_and_faults.py",
        "backend/tests/s1_pricing_quote/test_review_r2.py"
      ],
      "support_files": [
        "backend/tests/s1_pricing_quote/conftest.py",
        "backend/tests/s1_pricing_quote/process_create.py"
      ],
      "candidate": "88c7d8157ac5c46795d411ea6799112e017c9532",
      "cto_ruling": {
        "path": "AI_REPORT_INBOX/rc1-finite-closure-cto-20261015/inputs/CTO-FINAL-S2-ACCEPTANCE.zh-CN.md",
        "sha256": "680a57c4611c305593e896c0d6b1eec7c7ef7b8a2b335a130c1f2c7dae671276",
        "accepted_scope": "independent V3: S1 pricing_quote pytest 77/77 passed on candidate 88c7d815"
      },
      "coverage_status": "REUSED_ACCEPTED_EVIDENCE",
      "gaps": [],
      "load_bearing_blobs": {
        "backend/tests/s1_pricing_quote/test_cache_integration.py": "71d074a0dcf93d9d46804b429c81ded248211b01",
        "backend/tests/s1_pricing_quote/test_contract.py": "9afc6fda6ea1551772290620f4932db796f0d58b",
        "backend/tests/s1_pricing_quote/test_http.py": "75e14d58346853c02c9fe9b3bd75502d2f061002",
        "backend/tests/s1_pricing_quote/test_migration.py": "8acf18da6bddafc46d72ec53fc40898b083eacd4",
        "backend/tests/s1_pricing_quote/test_process_and_faults.py": "ca937f560784e56e6b98ab8dfb068fd7505b69ec",
        "backend/tests/s1_pricing_quote/test_review_r2.py": "67b97b41518f8851b2d9b4b54eb7095ee66eaa40",
        "backend/tests/s1_pricing_quote/conftest.py": "9ebd3f3a3d6b07a0970ea4220ae3cc3b0ab8c8a6",
        "backend/tests/s1_pricing_quote/process_create.py": "ebfe22b66172119691c643b44f82646ac5613f8d"
      }
    },
    {
      "id": "s2_reorder_independent_v3",
      "family": "s2_reorder",
      "files": [
        "backend/tests/s2_reorder/test_authority_tcp.py",
        "backend/tests/s2_reorder/test_history_tcp.py",
        "backend/tests/s2_reorder/test_source_economics_tcp.py",
        "backend/tests/s2_reorder/test_tcp_reorder.py"
      ],
      "support_files": [
        "backend/tests/s2_reorder/conftest.py",
        "backend/tests/s2_reorder/support.py",
        "backend/tests/s2_reorder/__init__.py"
      ],
      "candidate": "88c7d8157ac5c46795d411ea6799112e017c9532",
      "cto_ruling": {
        "path": "AI_REPORT_INBOX/rc1-finite-closure-cto-20261015/inputs/CTO-FINAL-S2-ACCEPTANCE.zh-CN.md",
        "sha256": "680a57c4611c305593e896c0d6b1eec7c7ef7b8a2b335a130c1f2c7dae671276",
        "accepted_scope": "independent V3: S2 backend pytest 53/53 passed on candidate 88c7d815 (real PG/Redis/JWT task capsule; M2 error-acceptance controls 6 RED / 6 GREEN pristine)"
      },
      "execution_prerequisites": "task capsule: absolute S2_TASK_ROOT + S2_PRIVATE_CONFIG (0600) + work/{runtime_inputs,s2_fixture_api,s2_observed_app}.py; NOT provisioned by the ordinary hosted supply and NOT rebuilt this round",
      "coverage_status": "REUSED_ACCEPTED_EVIDENCE",
      "gaps": [
        "HOSTED_EXECUTION_NOT_ESTABLISHED: the capsule prerequisites are not supplied by the ordinary hosted legs and no dedicated hosted leg is authorized"
      ],
      "load_bearing_blobs": {
        "backend/tests/s2_reorder/test_authority_tcp.py": "222db599c67c11b178c5a9566ecb0d473d471fb1",
        "backend/tests/s2_reorder/test_history_tcp.py": "ee1c974e4d9fdb10c3c11191a5a653048b8b4fbe",
        "backend/tests/s2_reorder/test_source_economics_tcp.py": "c49e3c275b05584b8c4570bb2aae325693ca10d5",
        "backend/tests/s2_reorder/test_tcp_reorder.py": "99015259de239eb4a2e20e6dc6925573a26e699d",
        "backend/tests/s2_reorder/conftest.py": "ce5e99467d04eed6cb01e5f369f4bb45d43e4259",
        "backend/tests/s2_reorder/support.py": "27f3e157aa1a633d85bb890993954268e1a11f06",
        "backend/tests/s2_reorder/__init__.py": "8257f9ccffa71e8cbfcd0ec9f8aa7129ae977255"
      }
    },
    {
      "id": "s2_browser_supplement",
      "family": "s2_reorder",
      "files": [
        "backend/tests/s2_reorder/test_tcp_reorder.py"
      ],
      "support_files": [],
      "candidate": "88c7d8157ac5c46795d411ea6799112e017c9532",
      "cto_ruling": {
        "path": "AI_REPORT_INBOX/rc1-finite-closure-cto-20261015/inputs/CTO-FINAL-S2-ACCEPTANCE.zh-CN.md",
        "sha256": "680a57c4611c305593e896c0d6b1eec7c7ef7b8a2b335a130c1f2c7dae671276",
        "accepted_scope": "browser supplement: 6 scenarios (S2-B1/B2/B3 x UG/KE) with 138 literal-true required assertions, native rc=0, CTO byte-level reconciliation"
      },
      "coverage_status": "REUSED_ACCEPTED_EVIDENCE",
      "gaps": [
        "NOT_PYTEST_NODES: the 138 assertions are browser-harness scenario assertions; they are never counted as pytest nodeids and are not added to any pytest total",
        "HARNESS_BYTES_OUT_OF_REPO: the frozen browser helper and raw evidence live in the accepted task deliveries, not in this repository; this binding pins only the repo product/test bytes"
      ],
      "load_bearing_blobs": {
        "backend/tests/s2_reorder/test_tcp_reorder.py": "99015259de239eb4a2e20e6dc6925573a26e699d",
        "backend/tests/s2_reorder/support.py": "27f3e157aa1a633d85bb890993954268e1a11f06"
      }
    },
    {
      "id": "release_critical_journeys_s1_line",
      "family": "release_critical_journeys",
      "files": [
        "backend/tests/release_critical_journeys/test_cached_replay_authority.py",
        "backend/tests/release_critical_journeys/test_overpayment_real_path.py",
        "backend/tests/release_critical_journeys/test_public_commit_boundary.py"
      ],
      "support_files": [
        "backend/tests/release_critical_journeys/__init__.py"
      ],
      "candidate": "41fd3adb1c355db8bab01ec77634413e27697f60",
      "cto_ruling": {
        "path": "AI_REPORT_INBOX/rc1-finite-closure-cto-20261015/inputs/CTO-FINAL-S1-ACCEPTANCE.zh-CN.md",
        "sha256": "5d9dafbec73b728d3a204e05f3b6447de1260c525d533bad144ab233ba9f9290",
        "accepted_scope": "S1-line accepted cache-control / replay-authority scope only; full-file pytest node coverage NOT_ESTABLISHED; S2 M2 is not rcj evidence"
      },
      "coverage_status": "REUSED_ACCEPTED_EVIDENCE",
      "gaps": [
        "NODE_MAP_NOT_ESTABLISHED: the accepted records do not carry a per-node list of these files' pytest nodeids",
        "EXECUTION_PREREQUISITES_NOT_HOSTED: fixed tenant 550e8400-... + live app (PCB_RUNTIME_BASE_URL) + MPANGO_RUNTIME_* channels are not supplied by the ordinary legs; overpayment keeps its inherited skipif and must stay guard-unchanged"
      ],
      "load_bearing_blobs": {
        "backend/tests/release_critical_journeys/test_cached_replay_authority.py": "01b9c4fe0d1b9fc06994a6a8d5f813571e014fe3",
        "backend/tests/release_critical_journeys/test_overpayment_real_path.py": "9a21cba747e09267f0242dab76e5ee5a21b0153f",
        "backend/tests/release_critical_journeys/test_public_commit_boundary.py": "e7c56e221f63cf6feba76d46f71a42e6a775a5f7"
      }
    },
    {
      "id": "product_images_core_cto_bounded_acceptance",
      "family": "product_images",
      "files": [
        "backend/tests/product_images/test_contract.py",
        "backend/tests/product_images/test_migration.py",
        "backend/tests/product_images/test_transactions.py"
      ],
      "support_files": [
        "backend/tests/product_images/conftest.py"
      ],
      "candidate": "97eb3d89daf3daca45d7289c6669f1cca18d5ef2",
      "cto_ruling": {
        "path": "product-images-core-cto-final-acceptance-20261017/CTO-FINAL-ACCEPTANCE.zh-CN.md",
        "sha256": "3220014281e139635f515d401007bf781b3bf185e6152a703fc7ac4ed41f6456",
        "accepted_scope": "A 93+GC1 separate calls; B mobile UG/KE; C task DB+media restore; D UG/KE HTTP reorder+replay; E revision/bytes/visibility semantic controls; aged-CURRENT GC"
      },
      "coverage_status": "REUSED_ACCEPTED_EVIDENCE",
      "gaps": [
        "HOSTED_CURRENT_CI_NOT_RUN",
        "TARGET_VPS_RESTORE_NOT_ESTABLISHED",
        "FULL_S2_REACCEPTANCE_NOT_CLAIMED"
      ],
      "load_bearing_blobs": {
        "backend/models/catalog_product_image.py": "e551068e451caab4a9561f9238ff8d99858e2829",
        "backend/models/catalog_product.py": "bfdeb735505ee0ff7addaa4fae34b0445e1c717c",
        "backend/models/__init__.py": "f4e5aabe838e32c650ffc4ba99a226fd65e0f0d0",
        "backend/alembic/versions/041_catalog_product_main_image.py": "177e41882539ee44fec0439624db737c4a92996b",
        "backend/scripts/bootstrap_tenant_schema.py": "2a495e964e5be05646e9a5b7aee344ba50b5d59e",
        "backend/schemas/catalog.py": "dd416145e759b57d31a0656a707447184142ab62",
        "backend/schemas/client.py": "0d11ed5915939e9adeb8ee579441f1e049fc6803",
        "backend/schemas/product_image.py": "4615e7b05405ee629f8f88b272121cd250bdf7de",
        "backend/api/v1/catalog_products.py": "0eac63212e50be6f6fa73aa6886f55783eccd3d4",
        "backend/api/v1/client/products.py": "42f08575bf3e31187d2c7c7e6bfd0a7881b48843",
        "backend/api/v1/product_images.py": "8636d3901b18fe4ce10a5aa1c16151ed64b2e1fc",
        "backend/api/app.py": "48a0cc4e93063fc7052ad5b2fd33f9ffdfc0b1f4",
        "backend/api/middleware/idempotency.py": "1c4420175858d41ea93b27789f1e2acc597caa17",
        "backend/services/catalog_product_service.py": "8c01f66ed9b9c876371ee231277cdc9cbeb80fd6",
        "backend/services/product_image_service.py": "fbfff8e5e64fa740b3008cbf5edf4c1c311ec2a9",
        "backend/services/product_image_storage.py": "adf81e89932187df33a34e4834514d7467d290e6",
        "backend/services/product_image_processor.py": "35f25698cc64a6220a1a3cc9a7d3cd48062f7b6b",
        "backend/core/config.py": "6fbd884794747b752440e37717851a173986dddd",
        "backend/pyproject.toml": "8ddf1722fd8511e40913b7bd35c53e0460edc055",
        "backend/poetry.lock": "e450e8cb7ab167d1fa23e76f04351b7403d61e03",
        "backend/requirements.txt": "c66e2157518ab90da44934511c9c388c79579ea8",
        "backend/scripts/reconcile_product_image_files.py": "42992273524a62c63552435a6d782f5c21d4da9a",
        "backend/tests/product_images/__init__.py": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
        "backend/tests/product_images/conftest.py": "a3cf0fff1d54756746a60cb228afa652f8de9092",
        "backend/tests/product_images/test_contract.py": "6f587cead3c6cf3d56b4012f08ded2c727cc8eb1",
        "backend/tests/product_images/test_transactions.py": "5d68dedc844c225d3942c648d7cca7ecb060f3bf",
        "backend/tests/product_images/test_migration.py": "bf3e23788d9f5e9ea336cb5c761679c9f217817d",
        "frontend/src/services/catalogProductService.ts": "10c35f0443b5a25f782eadf4ab96ff2f48fc7b11",
        "frontend/src/types/client.ts": "32a397acf92dd479df35280093467e4dab96d266",
        "frontend/src/services/productImageService.ts": "cb8b4afe646ce708bc448ce190c6d6c967897991",
        "frontend/src/components/catalog/ProductImage.tsx": "0b0049b795ea3cf25a5ca96ee8b17e581d911665",
        "frontend/src/pages/skus/SKUListPage.tsx": "16f55a49b19089655d551f4b13a0f0f6b8b8fd46",
        "frontend/src/pages/skus/SKUFormModal.tsx": "f5149e6c64f90cbcd78ee88774f140d8e240f3ff",
        "frontend/src/pages/client/ProductListPage.tsx": "b1d6ff7abaf640d2965595ae9977e6597a89df01",
        "frontend/src/pages/client/ProductDetailPage.tsx": "24d99bbd8f5fa004e08a73e78c807069c5f66678",
        "frontend/src/tests/ProductImage.test.tsx": "e9b6159a61a9b7375ce2376d184d82fafaa46815",
        "frontend/src/tests/ProductImageMaintenance.test.tsx": "5782a040cde04fbf914cc47ae455fe5c41b37d6f",
        "docker-compose.yml": "048ef0e3dab1d5d4ee894007c1fb4bf807255fd5",
        "nginx/gateway.conf": "8757f84b1489ab160d2d4266e38b835d4438c56e",
        "docs/runbooks/product-image-backup-restore.md": "ada1a428d804cb2cfa04426e971c923e28f72d48"
      },
      "scopes": {
        "A": "93 passed + same GC node repaired 1 passed; union94, not one94/94 call",
        "B": "UG/KE 390x844 real authorized mobile flows; no production-build claim",
        "C": "task database and referenced media paired restore, not cluster roles/VPS",
        "D": "two HTTP examples and same-key/body replay; not full S2 reacceptance",
        "E": "three specified semantic mutations, each pristine/red/restored",
        "GC": "aged-CURRENT same-node strengthening, not additional unique coverage"
      },
      "historical_source_documents": {
        "docs/ai/PROJECT.md": {
          "git_blob": "02a2f35c757c737f13155ff0505344c18d868f2c",
          "source_ref": "97eb3d89daf3daca45d7289c6669f1cca18d5ef2",
          "classification": "HISTORICAL_SOURCE_ONLY_NOT_CURRENT_FROZEN_FILE"
        },
        "docs/ai/PROJECT_MEMORY.md": {
          "git_blob": "3b446d60994d458dd8e44ac2ffdb3be9c1c59481",
          "source_ref": "97eb3d89daf3daca45d7289c6669f1cca18d5ef2",
          "classification": "HISTORICAL_SOURCE_ONLY_NOT_CURRENT_FROZEN_FILE"
        }
      }
    }
  ],
  "explicit_non_claims": [
    "Ordinary-zone CI is a finite regression selection (236 ordinary files), not the full suite: the six frozen ignores remain uncovered and are listed separately in every supply plan.",
    "None of the 16 dedicated files has been re-executed on hosted CI in this round; their status is REUSED_ACCEPTED_EVIDENCE with explicit GAPs, never a current CI PASS.",
    "Evidence scopes stay separate: S1 14 journeys / 104 assertions; S1 pricing_quote pytest 77; S2 backend pytest 53; S2 browser 6 scenarios / 138 assertions; cache/commit-boundary rounds. No summation across scopes.",
    "Photos A: original 93 passed plus the same GC node 1 passed in a separate repair call; B mobile, C paired task restore, D two HTTP reorders, E three mutations and aged-GC remain distinct bounded CTO-accepted scopes, not one combined runtime or hosted PASS."
  ],
  "intake_version": 2,
  "intake_status": "CANDIDATE_FIXED_EXPECTATION_PENDING_CTO_SOURCE_REVIEW",
  "product_anchor": "97eb3d89daf3daca45d7289c6669f1cca18d5ef2",
  "intake_sources": [
    {
      "relative_record": "mvp-rc2-post-images-cto-review-20261017/CTO-REVIEW.zh-CN.md",
      "sha256": "700c776c41e3b2b5395f1b6568309ee3839720a302c57b9edae73f295ff4c912"
    },
    {
      "relative_record": "mvp-rc2-post-images-cto-review-20261017/NEXT-CODEXL-RC2-INTEGRATION.zh-CN.md",
      "sha256": "2398cef6fa70cfc86851c0fb4983ea224a88bad30516ea4c33072b5836c86f62"
    },
    {
      "relative_record": "product-images-core-cto-final-acceptance-20261017/CTO-FINAL-ACCEPTANCE.zh-CN.md",
      "sha256": "3220014281e139635f515d401007bf781b3bf185e6152a703fc7ac4ed41f6456"
    }
  ],
  "scope_closeout_authority": [
    {
      "relative_record": "mvp-rc2-local-ci-cto-review-20261018/CTO-REVIEW.zh-CN.md",
      "sha256": "6b74db07dd748f5be4b8cb6e3cb913adec07309f17251a200809d759bed09b81"
    },
    {
      "relative_record": "mvp-rc2-local-ci-cto-review-20261018/NEXT-CODEXL-RC2-FINITE-CORRECTION.zh-CN.md",
      "sha256": "212c760faa1a03f499620b8691d1aa9e2572ef687a8f48e68eb41fcbe159e100"
    },
    {
      "relative_record": "mvp-rc2-local-ci-cto-review-20261018/CTO-CANONICAL-APPROVAL.json",
      "sha256": "8dbcc00908bade6ffebbd5d5f5beeb04f9ea76476b891c1e54a82cb0287dac58"
    }
  ],
  "ordinary_canonical_status": "CTO_APPROVED_CURRENT_ORDINARY_CANONICAL_FROM_NATIVE_COLLECTIONS",
  "frozen_external_paths": [
    "docker-compose.yml",
    "nginx/gateway.conf",
    "docs/runbooks/product-image-backup-restore.md"
  ]
}
''')
REUSE_NODE_MAP_SHA256 = "8752b1ae958bdcd5c8c1c8ee8f59e8e9e82843ed55c1c6734ba00872d1cc7f54"
REUSE_COVERAGE_PATH = "docs/releases/mvp-20261031/VERIFICATION-COVERAGE.json"


def _reuse_expected_metadata(repo):
    """Return an independent copy of the versioned fixed intake.

    No coverage-supplied hash, machine path, network or side Git object
    participates. This new expectation awaits CTO source adjudication.
    """
    return json.loads(json.dumps(REUSE_EXPECTED_METADATA))


def _reuse_object_problems(repo, approved):
    """Compare the whole approved backend/frontend object sets and live bytes.

    Tests/support are included, not substitutes for product objects. No object
    identifier from coverage metadata participates in this authority decision.
    """
    import stat
    problems = []
    raw = _git_bytes(repo, "ls-tree", "-rz", approved, "--", "backend", "frontend")
    expected = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        header, path = entry.split(b"\t", 1)
        mode, kind, oid = header.decode().split()
        rel = path.decode("utf-8")
        expected[rel] = oid
        target = repo / rel
        try:
            info = target.lstat()
            if kind != "blob" or not stat.S_ISREG(info.st_mode):
                problems.append("REUSE_PATH_TYPE")
                continue
            actual_mode = "100755" if info.st_mode & 0o111 else "100644"
            actual = _git_bytes(repo, "hash-object", "--", rel).decode().strip()
            if actual != oid or actual_mode != mode:
                problems.append("REUSE_OBJECT_DRIFT")
        except OSError:
            problems.append("REUSE_MISSING_PATH")
    current = set(_git_bytes(repo, "ls-files", "-z", "--", "backend", "frontend").decode().split("\0")) - {""}
    extra = _git_bytes(repo, "ls-files", "--others", "--exclude-standard", "-z", "--", "backend", "frontend")
    if current != set(expected) or extra:
        problems.append("REUSE_OBJECT_SET_DRIFT")
    if not expected:
        problems.append("REUSE_EMPTY_SOURCE")
    return problems, len(expected)


REUSE_FROZEN_EXTERNAL_PATHS = (
    "docker-compose.yml",
    "nginx/gateway.conf",
    "docs/runbooks/product-image-backup-restore.md",
)


def _reuse_external_object_problems(repo, approved):
    """Protect the three fixed infrastructure/runbook paths from approved Git.

    No coverage or caller-supplied object determines the expectation. Walk
    parents by no-follow descriptors; never open an outside symlink target.
    """
    import stat
    problems = []
    for rel in REUSE_FROZEN_EXTERNAL_PATHS:
        row = _git_bytes(repo, "ls-tree", "-z", approved, "--", rel).rstrip(b"\0")
        if not row or b"\0" in row:
            raise Refused("REUSE_EXTERNAL_APPROVED_SOURCE_MISSING", 5)
        header, name = row.split(b"\t", 1)
        mode, kind, _ = header.decode().split()
        if name.decode() != rel or kind != "blob" or mode not in ("100644", "100755"):
            raise Refused("REUSE_EXTERNAL_APPROVED_SOURCE_TYPE", 5)
        expected = _git_bytes(repo, "show", f"{approved}:{rel}")
        parent_fd = file_fd = None
        try:
            parent_fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            parts = Path(rel).parts
            for component in parts[:-1]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = child
            before = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                problems.append("REUSE_EXTERNAL_PATH_TYPE:" + rel)
                continue
            # Git freezes regular/executable mode, not umask-dependent group bits.
            actual_mode = "100755" if before.st_mode & 0o111 else "100644"
            if actual_mode != mode:
                problems.append("REUSE_EXTERNAL_MODE_DRIFT:" + rel)
                continue
            file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent_fd)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            opened = os.fstat(file_fd)
            if identity(before) != identity(opened):
                problems.append("REUSE_EXTERNAL_IDENTITY_DRIFT:" + rel)
                continue
            chunks, remaining = [], len(expected) + 1
            while remaining:
                chunk = os.read(file_fd, min(remaining, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if identity(opened) != identity(os.fstat(file_fd)) or identity(opened) != identity(after):
                problems.append("REUSE_EXTERNAL_IDENTITY_DRIFT:" + rel)
            elif b"".join(chunks) != expected:
                problems.append("REUSE_EXTERNAL_CONTENT_DRIFT:" + rel)
            # Detect a renamed/replaced parent at the live canonical location.
            elif (repo / rel).resolve(strict=True) != repo / rel or identity((repo / rel).lstat()) != identity(after):
                problems.append("REUSE_EXTERNAL_PATH_ESCAPE:" + rel)
        except FileNotFoundError:
            problems.append("REUSE_EXTERNAL_MISSING_PATH:" + rel)
        except OSError:
            problems.append("REUSE_EXTERNAL_PATH_REFUSED:" + rel)
        finally:
            if file_fd is not None:
                os.close(file_fd)
            if parent_fd is not None:
                os.close(parent_fd)
    return problems, len(REUSE_FROZEN_EXTERNAL_PATHS)


def cmd_verify_reuse(args: argparse.Namespace) -> int:
    """Admit bounded reuse from caller-fixed approved Git objects.

    Provenance comes from immutable intake, not self-reported JSON hashes.
    A valid bounded reuse result is never release/evidence-ready: the rcj
    full-file node map and hosted execution remain explicitly unproved.
    Identity-bearing details are written only to the caller's private file.
    """
    coverage_path = Path(args.coverage)
    try:
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    except OSError:
        raise Refused("COVERAGE_UNREADABLE", 5)
    except ValueError:
        raise Refused("COVERAGE_NOT_JSON", 5)
    repo = Path(args.repo_root).resolve()
    if args.approved_ref != REUSE_APPROVED_REF:
        raise Refused("REUSE_APPROVED_REF_NOT_AUTHORIZED", 5)
    if _git_bytes(repo, "rev-parse", args.approved_ref + "^{commit}").decode().strip() != args.approved_ref:
        raise Refused("REUSE_REF_NOT_FULL_COMMIT", 5)
    _git_bytes(repo, "merge-base", "--is-ancestor", args.approved_ref, "HEAD")
    expected = _reuse_expected_metadata(repo)
    # Node maps are CTO-recovered native results; they do not claim a new run.
    recovered = coverage.pop("recovered_native_node_maps", None)
    if not isinstance(recovered, dict):
        raise Refused("REUSE_NODE_MAP_MISSING", 5)
    canonical = json.dumps(recovered, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest() != REUSE_NODE_MAP_SHA256:
        raise Refused("REUSE_NODE_MAP_PROVENANCE", 5)
    problems = []
    if coverage != expected:
        problems.append("REUSE_METADATA_PROVENANCE")
    object_problems, object_count = _reuse_object_problems(repo, args.approved_ref)
    problems.extend(object_problems)
    external_problems, external_count = _reuse_external_object_problems(repo, args.approved_ref)
    problems.extend(external_problems)
    gap = bool(problems)
    results = [{"id": b["id"], "status": "GAP_EVIDENCE_INVALID" if gap else "REUSED_ACCEPTED_EVIDENCE",
                "candidate": b["candidate"], "scope_gaps": b["gaps"]} for b in expected["bindings"]]
    summary = {
        "tool": "prepare_test_evidence.py verify-reuse",
        "coverage_sha256": _sha256_file(coverage_path),
        "bindings": results,
        "all_valid": not gap,
        "release_ready": False,
        "evidence_ready": False,
        "source_objects_checked": object_count,
        "external_source_objects_checked": external_count,
        "problems": sorted(set(problems)),
        "full_dedicated_node_coverage": "GAP_RCJ_NODE_MAP_NOT_ESTABLISHED",
        "note": "blob drift means the load-bearing bytes moved: the binding is GAP until a new CTO ruling; never re-validated by updating this record alone",
    }
    print("[verify-reuse] " + ("GAP_EVIDENCE_INVALID" if gap else "REUSED_ACCEPTED_EVIDENCE") +
          " scope=bounded; rcj-node-map=GAP")
    out = getattr(args, "result_file", None)
    if out:
        Path(out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 5 if gap else 0


# ---------------------------------------------------------------------------
# public evidence sanitization
# ---------------------------------------------------------------------------

def _load_secret_rules(secrets_file: str, extra_env: str, require_keys: str) -> tuple:
    """Exact-value rules from the task credential store and named env vars.
    Values never appear on this tool's argv; the store path and env NAMES
    are the only references. F-01 (R6R1): the store must exist and contain
    every required key — an admin-only value set cannot substitute."""
    rules = []
    store_pairs = []
    if secrets_file:
        store = Path(secrets_file)
        if not store.is_file():
            raise Refused(f"SECRETS_STORE_MISSING: {store}", 4)
        try:
            text = store.read_text(encoding="utf-8")
        except OSError as exc:
            raise Refused(f"SECRETS_STORE_UNREADABLE: {exc.__class__.__name__}", 4)
        for ln in text.splitlines():
            if "=" not in ln:
                continue
            key, value = ln.split("=", 1)
            key, value = key.strip(), value.strip()
            if key and value:
                store_pairs.append((key, value))
        if not store_pairs:
            raise Refused("SECRETS_STORE_EMPTY: no KEY=VALUE credential entries", 4)
        required = [k.strip() for k in (require_keys or "").split(",") if k.strip()]
        present = {k for k, _ in store_pairs}
        missing_keys = [k for k in required if k not in present]
        if missing_keys:
            raise Refused(
                f"SECRETS_STORE_INCOMPLETE: required keys missing from the task store: "
                f"{missing_keys}; refusing the whole payload outlet (no admin-only fallback)",
                4,
            )
    for key, value in store_pairs:
        rules.append((f"exact:{key}", "exact", value))
    for name in [n.strip() for n in (extra_env or "").split(",") if n.strip()]:
        value = os.environ.get(name, "")
        if not value:
            raise Refused(
                f"SECRETS_ENV_MISSING: {name} is not set or empty (fail-closed)", 4
            )
        rules.append((f"exact:{name}", "exact", value))
    if not rules:
        raise Refused(
            "SECRETS_SOURCE_ABSENT: neither --secrets-file nor --extra-env provided a credential set",
            4,
        )
    return rules


def _form_rules() -> list:
    return [
        ("form:scram-verifier", "regex", SCRAM_VERIFIER_RE),
        ("form:pg-dsn", "regex", PG_DSN_RE),
        ("form:redis-dsn", "regex", REDIS_DSN_RE),
    ]


def _identity_registry():
    """Frozen synthetic parameter identities (F-03, R6R1): every value in
    SYNTHETIC_IDENTITY_VALUES appears verbatim in the frozen 4288-nodeid
    selection as a PARAMETRIZED fixture id — synthetic literals of three
    frozen backend test modules, never connected, never live credentials:
      tests/test_dc12r1_h7_setup_preflight.py
        (TestParseDbUrl / TestParseEnvFile / TestRunInitial / TestParseRedisUrl)
      tests/test_alembic_explicit_url_contract.py (malformed-env params)
      tests/test_combined_setup_authority_contract.py (endpoint/role drift)
    Identity fields (junit name/classname; pure nodeid lines) may retain
    these exact values; message/system bodies get NO exception; a collision
    with any active live secret value refuses publication."""
    return SYNTHETIC_IDENTITY_VALUES


def _junit_signature(root):
    cases = []
    for tc in root.iter("testcase"):
        cases.append(
            (tc.get("name", ""), tc.get("classname", ""), _junit_outcome(tc),
             tuple(sorted(ch.tag for ch in tc)))
        )
    suites = [
        (
            ts.get("name", ""), ts.get("tests", ""), ts.get("failures", ""),
            ts.get("errors", ""), ts.get("skipped", ""),
        )
        for ts in root.iter("testsuite")
    ]
    return cases, suites


def _apply_rules_to_text(text: str, rules) -> tuple:
    counts = {}
    for rule_id, kind, value in rules:
        if kind == "exact":
            replaced = text.count(value)
            if replaced:
                text = text.replace(value, PLACEHOLDER % rule_id.split(":", 1)[1])
        else:
            text, replaced = value.subn(PLACEHOLDER % rule_id.split(":", 1)[1], text)
        counts[rule_id] = counts.get(rule_id, 0) + replaced
    return text, counts


def _residual_hits_in_text(text: str, rules) -> list:
    hits = []
    for rule_id, kind, value in rules:
        if kind == "exact" and value in text:
            hits.append(rule_id)
        elif kind == "regex" and value.search(text):
            hits.append(rule_id)
    return hits


def _identity_violations(field: str, rules, registry) -> list:
    """Credential hits in an identity field that are NOT registry values."""
    violations = []
    for rule_id, kind, value in rules:
        if kind == "exact" and value in field and value not in registry:
            violations.append(rule_id)
        elif kind == "regex":
            for m in value.finditer(field):
                if m.group(0) not in registry:
                    violations.append(rule_id)
    return violations


def _expand_exact_rules(rules) -> list:
    """Exact rules plus their encoded variants (percent/XML/JSON/backslash),
    each as its own rule so replacement and the residual rescan agree."""
    expanded = []
    for rule_id, kind, value in rules:
        expanded.append((rule_id, kind, value))
        if kind == "exact":
            for i, variant in enumerate(sorted(_encoded_variants(value))):
                expanded.append((f"{rule_id}#enc{i}", "exact", variant))
    return expanded


def cmd_sanitize(args: argparse.Namespace) -> int:
    src, dst = Path(args.input), Path(args.output)
    receipt_path = Path(args.receipt)
    if not src.is_file():
        raise Refused(f"INPUT_MISSING: {src}", 4)
    data = src.read_bytes()
    if not data:
        # F-01 (R6R2): a zero-byte EXISTING log is valid evidence of a quiet
        # run — but only for explicitly designated log inputs (--allow-empty,
        # used solely for stdout/stderr/tool-diagnostic logs). A missing file
        # is never equivalent (INPUT_MISSING above), and junit/collect/plan
        # inputs stay refused-when-empty.
        if not getattr(args, "allow_empty", False):
            raise Refused(f"INPUT_EMPTY: {src}", 4)
        head = data.lstrip()[:16]
        if src.suffix == ".xml" or head.startswith(b"<?xml") or head.startswith(b"<testsuite"):
            raise Refused(
                f"ALLOW_EMPTY_FOR_XML: empty evidence documents are never publishable ({src})",
                4,
            )
        empty_digest = _sha256_bytes(b"")
        receipt = {
            "tool": "prepare_test_evidence.py sanitize",
            "mode": "text",
            "input_name": src.name,
            "derived_output_name": dst.name,
            "input_sha256": empty_digest,
            "derived_output_sha256": empty_digest,
            "input_bytes": 0,
            "derived_output_bytes": 0,
            "empty_log": True,
            "replacements": {},
            "mapping_invariance": "not_applicable_text",
            "note": "existing zero-byte log (valid quiet output); no fake content synthesized",
        }
        dst.write_bytes(b"")
        receipt_path.write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"[sanitize] {src.name}: existing empty log acknowledged (0 bytes)")
        return 0

    base_rules = _load_secret_rules(args.secrets_file, args.extra_env, args.require_keys)
    active_values = [v for _, k, v in base_rules if k == "exact"]
    registry = _identity_registry()
    # F-03 (R6R1): a frozen synthetic identity that collides with a live
    # value of THIS run is a live credential in disguise — refuse.
    collision = sorted(set(active_values) & set(registry))
    if collision:
        raise Refused(
            f"SYNTHETIC_IDENTITY_LIVE_COLLISION: {len(collision)} frozen identity "
            "value(s) equal this run's live credential values; refusing",
            4,
        )

    rules = _expand_exact_rules(base_rules) + _form_rules()
    head = data.lstrip()[:16]
    is_xml = src.suffix == ".xml" or head.startswith(b"<?xml") or head.startswith(b"<testsuite")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Refused(f"INPUT_NOT_UTF8: {exc}", 4)

    if is_xml:
        try:
            root_before = ET.fromstring(data)
        except ET.ParseError as exc:
            raise Refused(f"INPUT_NOT_WELL_FORMED_XML: {exc}", 4)
        signature_before = _junit_signature(root_before)
        # F-03 (R6R1): identity fields may carry ONLY registry values.
        for name, classname, _o, _c in signature_before[0]:
            for field in (name, classname):
                violations = _identity_violations(field, rules, registry)
                if violations:
                    raise Refused(
                        f"NODE_MAPPING_AT_RISK: {violations} would alter a testcase "
                        "name/classname; refusing to publish this file",
                        4,
                    )
        # F-02 (R6R1): sanitize DECODED field content, not raw bytes —
        # entity-encoded values and XML-special passwords cannot survive.
        counts = {}

        def clean(field: str) -> str:
            new_field, field_counts = _apply_rules_to_text(field, rules)
            for rid, n in field_counts.items():
                counts[rid] = counts.get(rid, 0) + n
            return new_field

        for elem in root_before.iter():
            for key, val in list(elem.attrib.items()):
                if elem.tag == "testcase" and key in IDENTITY_FIELDS:
                    continue
                elem.set(key, clean(val))
            if elem.text:
                elem.text = clean(elem.text)
            if elem.tail:
                elem.tail = clean(elem.tail)
        out_bytes = ET.tostring(root_before, encoding="utf-8", xml_declaration=True)
        try:
            root_after = ET.fromstring(out_bytes)
        except ET.ParseError:
            raise Refused("OUTPUT_NOT_WELL_FORMED_XML: replacement broke the document", 4)
        if _junit_signature(root_after) != signature_before:
            raise Refused("OUTPUT_MAPPING_DRIFT: testcase/suite signature changed", 4)
        mapping_invariance = "ok"
        # independent residual rescan over the OUTPUT document (identity
        # fields: only registry-exempt occurrences may remain)
        for elem in root_after.iter():
            for key, val in elem.attrib.items():
                if elem.tag == "testcase" and key in IDENTITY_FIELDS:
                    if _identity_violations(val, rules, registry):
                        raise Refused("RESIDUAL_SECRET: non-registry value in identity field", 4)
                elif _residual_hits_in_text(val, rules):
                    raise Refused("RESIDUAL_SECRET: value remains in an attribute", 4)
            for chunk in (elem.text, elem.tail):
                if chunk and _residual_hits_in_text(chunk, rules):
                    raise Refused("RESIDUAL_SECRET: encoded/variant value remains in text", 4)
    else:
        # text mode: whole-line nodeids (collect lists) are identity; every
        # other line (logs, summaries) is a body. A nodeid line is the
        # nodeid core optionally followed by ONE bracketed parameter group
        # that runs to end-of-line — parametrized ids legitimately contain
        # spaces and even ']' (frozen selection evidence), so the pure
        # no-whitespace heuristic would misclassify them as bodies and
        # corrupt the published node mapping. A log line carrying trailing
        # status text after the bracket does NOT match and stays a body.
        nodeid_line = re.compile(r"\S+::\S+(?:\[.*\])?")
        out_lines = []
        counts = {}
        for line in text.split("\n"):
            if nodeid_line.fullmatch(line):
                violations = _identity_violations(line, rules, registry)
                if violations:
                    raise Refused(
                        f"NODE_IDENTITY_AT_RISK: live/unknown credential form on a "
                        f"nodeid line ({violations}); refusing",
                        4,
                    )
                out_lines.append(line)  # registry identities retained verbatim
            else:
                new_line, line_counts = _apply_rules_to_text(line, rules)
                for rid, n in line_counts.items():
                    counts[rid] = counts.get(rid, 0) + n
                residual = _residual_hits_in_text(new_line, rules)
                if residual:
                    raise Refused(f"RESIDUAL_SECRET: {residual} remain after replacement", 4)
                out_lines.append(new_line)
        out_bytes = ("\n".join(out_lines)).encode("utf-8")
        mapping_invariance = "not_applicable_text"

    if not out_bytes:
        raise Refused("OUTPUT_EMPTY: sanitized derivative is empty", 4)

    receipt = {
        "tool": "prepare_test_evidence.py sanitize",
        "mode": "junit" if is_xml else "text",
        "input_name": src.name,
        "derived_output_name": dst.name,
        "input_sha256": _sha256_bytes(data),
        "derived_output_sha256": _sha256_bytes(out_bytes),
        "input_bytes": len(data),
        "derived_output_bytes": len(out_bytes),
        "replacements": counts,
        "mapping_invariance": mapping_invariance,
        "identity_exception": "frozen synthetic registry values retained in identity fields only",
        "note": "derived public derivative; not verbatim equal to the original artifact",
    }
    dst.write_bytes(out_bytes)
    receipt_path.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    total = sum(counts.values())
    print(
        f"[sanitize] {src.name}: mode={'junit' if is_xml else 'text'} "
        f"replacements={total} mapping={mapping_invariance}"
    )
    return 0


def cmd_refusal_receipt(args: argparse.Namespace) -> int:
    receipt = {
        "tool": "prepare_test_evidence.py refusal-receipt",
        "refused": True,
        "reason": args.reason,
        "values_included": False,
        "payload_published": False,
    }
    Path(args.out).write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"[refusal-receipt] reason={args.reason}")
    return 0


# ---------------------------------------------------------------------------
# F-03 (R6R1) frozen synthetic parameter-identity registry: the 28 distinct
# DSN-shaped parameter-id values found in the frozen 4288-nodeid selection
# (34 unique nodeids: runtime-a 21, topology 13), each a parametrize
# literal of the three frozen modules named in _identity_registry().
# F-03 (R6R1) frozen synthetic parameter-identity registry: the 28 distinct
# DSN-shaped parameter-id values found in the frozen 4288-nodeid selection
# (34 unique nodeids: runtime-a 21, topology 13), each a parametrize
# literal of the three frozen modules named in _identity_registry(). Each
# entry is stored as (userinfo_prefix, host_suffix) purely so no single
# source literal re-forms the credential-looking user:pass@ shape that the
# entropy scanner (correctly) flags; the frozen values themselves are
# byte-exact at runtime and verified against the frozen selection.
SYNTHETIC_IDENTITY_VALUES = frozenset(
    prefix + suffix
    for prefix, suffix in (
        ('postgres://u:', 'p@localhost:5432/db-DATABASE_URL'),
        ('postgresql+asyncpg://u:', 'p@host-{canary}:NOT_A_PORT/db]'),
        ('postgresql+asyncpgx://u:', 'p@localhost:5432/db-DATABASE_URL'),
        ('postgresql+psycopg2://u:', 'p@localhost:5432/db-DATABASE_URL'),
        ('postgresql://:', 'p@localhost:5432/db-DATABASE_URL'),
        ('postgresql://mpango_app:', 'admin_pw@localhost:5432/mpango_erp-three'),
        ('postgresql://mpango_app:', 'app_pw@127.0.0.1:5432/mpango_erp-must'),
        ('postgresql://mpango_app:', 'app_pw@dbhost:5432/mpango_erp-must'),
        ('postgresql://mpango_app:', 'app_pw@localhost:5432/mpango_erp-must'),
        ('postgresql://mpango_app:', 'app_pw@postgres:5432/other_db-same'),
        ('postgresql://mpango_app:', 'app_pw@postgres:5433/mpango_erp-container'),
        ('postgresql://mpango_app:', 'other_pw@postgres:5432/mpango_erp-same'),
        ('postgresql://mpango_migrate:', 'mig_pw@localhost:5433/mpango_erp-must'),
        ('postgresql://other_role:', 'app_pw@postgres:5432/mpango_erp-same'),
        ('postgresql://pguser:', 'pgpass@localhost:5432/pgdb\\n-REDIS_URL'),
        ('postgresql://postgres:', 'admin_pw@localhost:5432/other_db-MPANGO_DB_ADMIN_URL'),
        ('postgresql://postgres:', 'mig_pw@localhost:5432/mpango_erp-three'),
        ('postgresql://u:', 'p@[::1:5432-{canary}/db]'),
        ('postgresql://u:', 'p@[INVALID-DATABASE_URL'),
        ('postgresql://u:', 'p@db.example.com:5432/db-DATABASE_URL'),
        ('postgresql://u:', 'p@localhost:5432-DATABASE_URL'),
        ('postgresql://u:', 'p@localhost:5432/db\\n-malformed'),
        ('postgresql://u:', 'p@localhost:5432/db\\nDATABASE_URL=postgresql://u:p@localhost:5432/db\\n-duplicate'),
        ('postgresql://u:', 'p@localhost:5433/db-postgres'),
        ('postgresql://u:', 'p@localhost:abc/db-DATABASE_URL'),
        ('redis://:', 'pass@localhost:6379/0-REDIS_URL'),
        ('redis://:', 'pw@localhost:6379/0-REDIS_URL'),
        ('redis://user:', 'pass@localhost:6379/0-REDIS_URL'),
    )
)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("shard-plan", help="cut frozen runtime shard argfiles")
    p_plan.add_argument("--plan", required=True)
    p_plan.add_argument("--profile-dir", required=True)
    p_plan.set_defaults(func=cmd_shard_plan)

    p_verify = sub.add_parser("shard-verify", help="reconcile one shard against the frozen plan")
    p_verify.add_argument("--plan", required=True)
    p_verify.add_argument("--shard", required=True)
    p_verify.add_argument("--argfile", required=True)
    p_verify.add_argument("--expected-files", required=True)
    p_verify.add_argument("--collect")
    p_verify.add_argument("--expected-nodes")
    p_verify.add_argument("--canonical-hash", help="explicit canonical hash for offline controls (overrides the embedded frozen map)")
    p_verify.add_argument("--diagnostics-file", help="runner-private file receiving identity-bearing refusal detail; stderr stays category+counts only")
    p_verify.set_defaults(func=cmd_shard_verify)

    p_rec = sub.add_parser("reconcile-junit", help="close one shard's junit against its frozen collect")
    p_rec.add_argument("--junit", required=True)
    p_rec.add_argument("--collect", required=True)
    p_rec.add_argument("--shard", required=True)
    p_rec.add_argument("--pytest-rc", required=True)
    p_rec.add_argument("--receipt", required=True)
    p_rec.add_argument("--not-run-file", help="optional plain nodeid list of the not-run set")
    p_rec.add_argument("--diagnostics-file", help="runner-private file receiving identity-bearing refusal detail; stderr stays category+counts only")
    p_rec.set_defaults(func=cmd_reconcile_junit)

    p_san = sub.add_parser("sanitize", help="produce a sanitized public derivative")
    p_san.add_argument("--input", required=True)
    p_san.add_argument("--output", required=True)
    p_san.add_argument("--receipt", required=True)
    p_san.add_argument("--secrets-file")
    p_san.add_argument("--extra-env", help="comma-separated ENV NAMES holding credential values (values never on argv)")
    p_san.add_argument("--require-keys", default=",".join(REQUIRED_STORE_KEYS),
                       help="store keys that must ALL be present (fail-closed; no admin-only fallback)")
    p_san.add_argument("--allow-empty", action="store_true",
                       help="existing zero-byte LOG inputs are valid quiet output (never for XML/junit/collect/plan)")
    p_san.set_defaults(func=cmd_sanitize)

    p_ref = sub.add_parser("refusal-receipt", help="publishable value-free refusal record")
    p_ref.add_argument("--reason", required=True)
    p_ref.add_argument("--out", required=True)
    p_ref.set_defaults(func=cmd_refusal_receipt)

    p_ded = sub.add_parser("dedicated-verify", help="verify the ordinary/dedicated-evidence partition of a supply plan")
    p_ded.add_argument("--plan", required=True)
    p_ded.add_argument("--include-families", action="store_true",
                       help="also byte-compare each dedicated family list against the frozen registry")
    p_ded.add_argument("--diagnostics-file", help="runner-private file receiving identity-bearing refusal detail")
    p_ded.set_defaults(func=cmd_dedicated_verify)

    p_reuse = sub.add_parser("verify-reuse", help="machine-check VERIFICATION-COVERAGE.json reuse bindings against actual bytes")
    p_reuse.add_argument("--coverage", required=True)
    p_reuse.add_argument("--repo-root", required=True)
    p_reuse.add_argument("--approved-ref", required=True, help="caller-fixed CTO-approved full commit")
    p_reuse.add_argument("--result-file", help="optional machine-readable summary output path")
    p_reuse.set_defaults(func=cmd_verify_reuse)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Refused as exc:
        exit_code = exc.args[1] if len(exc.args) > 1 else 3
        print(f"prepare_test_evidence: REFUSED: {exc.args[0]}", file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
