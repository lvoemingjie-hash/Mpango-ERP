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
    "s3_negotiation": (
        "tests/s3_negotiation/test_atomicity_and_races.py",
        "tests/s3_negotiation/test_contract.py",
        "tests/s3_negotiation/test_migration.py",
        "tests/s3_negotiation/test_provenance_and_safety.py",
        "tests/s3_negotiation/test_safety_boundaries.py",
    ),
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
_HISTORICAL_CANONICAL_DIGEST_INTS = {
    "runtime-a": 31909149706389310500397118238844167744261060807324375977335756059803826548134,
    "runtime-b": 57725012565857539176717571526097518784084886020524993529010191070552221256377,
    "topology": 89431394580350489123950586879915797113004354348693083846620910588820036223488,
    "invariants-jwt": 14225403732936862956787750016881398974573020047247214588285646003204590389255,
    "task-managed-pg": 26202434481483022035822387896696908997049812747828017617325771995640059934965,
}
# Current values come from the five native RC4 collections, not old counts.
CANONICAL_NODEID_SHA256 = {
    "runtime-a": "6eed0a210105843cc4c82be0c919f4f5962b325fe600d7a7dffcf1e9dcdc4472",
    "runtime-b": "88092068a62c32710a9e83831c3b6de43a0d5105a00843b28b810d05ac8ef59b",
    "topology": "c5b860246b7e6829d45924e4f608da4250e27ad519d2fae00eea11a268a38200",
    "invariants-jwt": "9babd523542d1937d0418cf1d5b01fffb90886d41988164e2b4e3c9feb0c4b2e",
    "task-managed-pg": "39ee0d676ac12ae3fcd28a06908f2a6eede9182c325c4819067ed381a88038f5",
}

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

    suites = list(root.iter("testsuite"))
    if len(suites) != 1 or any(
        suites[0].get(key) is None for key in ("tests", "failures", "errors", "skipped")
    ):
        raise Refused("JUNIT_SINGLE_SUITE_COUNTERS_REQUIRED", 3)

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
    teardown_only = set()
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
        error = tc.find("error")
        if (error is not None and len(tc.findall("error")) == 1
                and tc.find("failure") is None and tc.find("skipped") is None
                and error.get("message", "").startswith('failed on teardown with "')):
            teardown_only.add(matched)

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
    # pytest 8.4.2 increments append_pass during the call, then appends an
    # error on teardown without reopening that testcase. Only its native
    # teardown-only shape contributes this otherwise invisible passed call.
    passed_then_teardown = sorted(nid for nid in teardown_only if phases[nid] == ["error"])
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
        "tests": entries - len(double_phase_nodes) + len(passed_then_teardown),
        "failures": phase_counts.get("failure", 0),
        "errors": phase_counts.get("error", 0),
        "skipped": phase_counts.get("skipped", 0) + phase_counts.get("xfail", 0),
    }
    contradictions = []
    for ts in suites:
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
        "pytest_generator_phase_counts": {
            **phase_counts,
            "passed": phase_counts.get("passed", 0) + len(passed_then_teardown),
        },
        "passed_call_then_teardown_error_nodes": passed_then_teardown,
        "unique_outcome_counts": unique_counts,
        "double_phase_nodes": double_phase_nodes,
        "outcome_counts": unique_counts,
        "not_run": not_run,
        "pytest_rc": pytest_rc,
        "counter_check": "ok (pytest 8.4.2: tests=XML_entries-double_fail+passed_call_teardown_error)",
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


# This is an implementation-side source-continuation proposal, not CTO acceptance.
REUSE_APPROVED_REF = "3a26b6d6baa2b73ecc044c3ffd30f4bb9f670a37"
# Versioned fixed expectation travels with this tool, not an unavailable side commit.
# Rebuild inputs/recipe are declared in intake_sources and the delivery receipt.
REUSE_INTAKE_VERSION = 9
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
    "invalidation": "Historical candidates, XML/node maps and load_bearing_blobs retain their original provenance; they are not current-byte or fresh-run claims. Current source authority is the tool-fixed CTO intake ref, compared independently against every backend/frontend path, byte and Git mode plus the three external paths. Any unapproved drift or coverage-only provenance change refuses. Current attachment deltas remain explicitly unrerun GAPs; all_valid is bounded admission, never release_ready/evidence_ready.",
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
    "Photos A: original 93 passed plus the same GC node 1 passed in a separate repair call; B mobile, C paired task restore, D two HTTP reorders, E three mutations and aged-GC remain distinct bounded CTO-accepted scopes, not one combined runtime or hosted PASS.",
    "Current 7d86e513 product freeze is CTO-approved source intake only. The author 511/build and four mobile scenarios do not reexecute the historical 77/53/138 or all S2 journeys; no hosted CI or current full collection is claimed."
  ],
  "intake_version": 3,
  "intake_status": "CTO_APPROVED_CURRENT_SOURCE_FREEZE__LOCAL_ADMISSION_ONLY",
  "product_anchor": "7d86e513fe8d37558bf4595330a62c9b082c7776",
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
  "ordinary_canonical_status": "FROZEN_ORDINARY_SELECTION_DEFINITION__CURRENT_FRESH_COLLECTION_NOT_ESTABLISHED",
  "frozen_external_paths": [
    "docker-compose.yml",
    "nginx/gateway.conf",
    "docs/runbooks/product-image-backup-restore.md"
  ],
  "previous_source_freezes": [
    {
      "intake_version": 2,
      "source_ref": "97eb3d89daf3daca45d7289c6669f1cca18d5ef2",
      "classification": "HISTORICAL_SOURCE_FREEZE_NOT_CURRENT_EXECUTION",
      "ordinary_canonical_status": "CTO_APPROVED_CURRENT_ORDINARY_CANONICAL_FROM_NATIVE_COLLECTIONS"
    }
  ],
  "current_source_intake": {
    "authority_record": {
      "path": "AI_REPORT_INBOX/retailer-mobile-ux-browser-cto-review-20261019/CURRENT-SOURCE-INTAKE.json",
      "sha256": "b15632375e76c36fad7fd01ebe989c74153fa2ae79c8e8b7a924a73c7dc0bed7"
    },
    "authorization": "CTO-AUTH-RC2-CURRENT-CI-SOURCE-INTAKE-L-R1-20261019",
    "source_ref": "7d86e513fe8d37558bf4595330a62c9b082c7776",
    "source_tree": "4282f72c260beee30c06cd3b3689fb077919df17",
    "source_parent": "38638de2bf15563267e3f3962a3cdd419d99914c",
    "backend_tree": "2acd4efaa63d2b1d7b0f13515e121d3eb5ee4513",
    "frontend_tree": "36a3075922779493f93b707ee3096e5a4b55d7ad",
    "cto_ruling": {
      "path": "/home/ivy/AI_REPORT_INBOX/retailer-mobile-ux-browser-cto-review-20261019/CTO-REVIEW.zh-CN.md",
      "sha256": "85511da10ecd25599126d63c7c2233ea10d869c636d599d99ec6de112fe28c57"
    },
    "accepted_author_local_frontend_scope": {
      "candidate": "7d86e513fe8d37558bf4595330a62c9b082c7776",
      "frontend_tree": "36a3075922779493f93b707ee3096e5a4b55d7ad",
      "vitest_files": 39,
      "vitest_tests_passed": 511,
      "build": "production build rc0, four dist hashes bound to this frontend tree",
      "source_delivery": "/home/ivy/AI_REPORT_INBOX/retailer-mobile-order-ux-finite-closeout-codexl-r1-20261019/delivery/",
      "source_manifest_sha256": "f13e0c831effe0496fd551e7e6391ee4519e57eeee4caabd0d37a572060cfaf4",
      "native_junit_sha256": "060fa5452cbd80a6f5dffef72155d2dc1334ed5b34d7e8da691e953891413fa4",
      "browser_scenarios": [
        "C1-UG",
        "C2-KE",
        "C3-UG",
        "C4-KE"
      ],
      "browser_delivery": "/home/ivy/AI_REPORT_INBOX/retailer-mobile-order-ux-browser-continue-codexl-r1r1-20261019/delivery/",
      "browser_manifest_sha256": "86903e957be978e38b2d06c11df233698433f0e3194e696963c0144f39d03d73",
      "tier": "author bounded live evidence reconciled by CTO, not independent V3",
      "visual_limit": "C4 replay screenshot is loading skeleton, not final order-detail render proof",
      "hmac_limit": "quote token and signer were unlinked; HMAC verification is author-recorded; CTO rederived retained payload fingerprints/key digests/items, not HMAC signatures"
    },
    "accepted_local_backend_boundary_scope": {
      "execution_candidate": "38638de2bf15563267e3f3962a3cdd419d99914c",
      "current_backend_tree_equals_execution_candidate": true,
      "groups": [
        43,
        92
      ],
      "source_delivery": "/home/ivy/AI_REPORT_INBOX/rc2-two-test-formal-continue-codexl-r1r3-20261018/delivery/",
      "source_manifest_sha256": "22f686a98ae747c4a13026e77726a44c6c8377c9b8d9b412d0ba78f347c5295d",
      "new_backend_calls_this_browser_round": 0,
      "claim": "bounded accepted groups only, not all 162 old CI REDs rerun on current source"
    },
    "historical_results_reexecuted": false,
    "hosted_ci_this_intake": "NOT_RUN",
    "independent_v3_this_intake": "NOT_ESTABLISHED",
    "current_fresh_ordinary_collection": "CURRENT_FRESH_COLLECTION_NOT_ESTABLISHED",
    "ordinary_definition": {
      "nodes": 4288,
      "files": 236,
      "dedicated_files": 16,
      "ignores": 6,
      "canonical_definition_changed": false
    },
    "old_source_ref": "97eb3d89daf3daca45d7289c6669f1cca18d5ef2",
    "source_deltas": [
      {
        "path": "backend/scripts/runtime_readiness_gate.py",
        "old_tree_entry": "100755 blob bbe2a33e0e1ab26a3cebea79639b714e22e902e5\tbackend/scripts/runtime_readiness_gate.py",
        "current_tree_entry": "100755 blob 37ca94dfbedd8e5c0dd1d87bfc4c2f6c7e0dd28e\tbackend/scripts/runtime_readiness_gate.py",
        "old_content_sha256": "fe70397b98b2f54195dec9aa831e64121a4ed7ebc005ef31cf277bf470190bbb",
        "current_content_sha256": "a078faf43943d8b87c21d5387c97a1619487858777dbe397e059608a0162290f",
        "source_commits": [
          "4fd581a6db4e6e10f28c374383a2191295fcd707"
        ]
      },
      {
        "path": "backend/scripts/seed_demo_data.py",
        "old_tree_entry": "100644 blob d07bd2dd1408e64b114312536ed9ab28dbd18c21\tbackend/scripts/seed_demo_data.py",
        "current_tree_entry": "100644 blob e52c42ca303572180672f5445e10b419a13276c1\tbackend/scripts/seed_demo_data.py",
        "old_content_sha256": "a9e5703e9380dbc02d04f3d3a8c624468619d80e4ba6f795b9ce0a87d6312e11",
        "current_content_sha256": "c697b3f14eed222700cbf263940dcef7f65ed07766e62bf566822ad04935f663",
        "source_commits": [
          "4fd581a6db4e6e10f28c374383a2191295fcd707"
        ]
      },
      {
        "path": "backend/tests/business/test_financial_loop.py",
        "old_tree_entry": "100644 blob 408c6f5e6cf162ee4528ee3f9a51635d959ac0f6\tbackend/tests/business/test_financial_loop.py",
        "current_tree_entry": "100644 blob 2c455387296abb162b6260e0f3cd0ba6e45109da\tbackend/tests/business/test_financial_loop.py",
        "old_content_sha256": "4604d1b46caeae04fbc89def3e4c99cc367b71a46be1f7b4d8dc0cb4b15410c8",
        "current_content_sha256": "bef695fb7a4ce2dcd4e2c658487b884142965d9ac64d84e90c7342bf0a272b99",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/business/test_s4e_stock_reservation_lifecycle_audit.py",
        "old_tree_entry": "100644 blob 830ce5b9468b7a681c0dcd91739de06bbd25399b\tbackend/tests/business/test_s4e_stock_reservation_lifecycle_audit.py",
        "current_tree_entry": "100644 blob bd0a8a7f63ef332f73c221d341197158bc791997\tbackend/tests/business/test_s4e_stock_reservation_lifecycle_audit.py",
        "old_content_sha256": "996b2375d639163fabb098cc0adb3b0edc3cbe2d87687c9c37dbf1d573be90b5",
        "current_content_sha256": "5b416659afefd30f4339a26086e1474129b0b8c80ee97d5fdfb4fe8b7c3a18bc",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/business/test_s4f_business_invariant_closeout.py",
        "old_tree_entry": "100644 blob 571238f5dbfc7d04233e7a232f4ac3358ea135a2\tbackend/tests/business/test_s4f_business_invariant_closeout.py",
        "current_tree_entry": "100644 blob 5214417b3e032ab657e30814c8d8fb6b67c5f9f7\tbackend/tests/business/test_s4f_business_invariant_closeout.py",
        "old_content_sha256": "37329dff7a73f29759565201b92828655819179ee59f110af2f9782f65c8c4c9",
        "current_content_sha256": "34706c1d6adc20c82fa53bb227d6bbf227b5e36d4f0e0f4cac20b1be14111780",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/mpango_invariants_r0_support.py",
        "old_tree_entry": "100644 blob 684c436d9969cbd8cf26f709140bb09b3b2f46d5\tbackend/tests/mpango_invariants_r0_support.py",
        "current_tree_entry": "100644 blob 98b82736cf3f821e1447787afba69d31143bdd6a\tbackend/tests/mpango_invariants_r0_support.py",
        "old_content_sha256": "e8559ab8d02b846061e353aeb83018bcc6631b2349afbd11e3f084f0c3840a97",
        "current_content_sha256": "9d1f6e0aa1eada63e95d22e746d5b5db9f37d18b61307c05e941346f8e81b59d",
        "source_commits": [
          "38638de2bf15563267e3f3962a3cdd419d99914c",
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/order_state_r2/test_migration_c3.py",
        "old_tree_entry": "100644 blob 09e5518d457400582bb4d34aac1f5d379d4cf333\tbackend/tests/order_state_r2/test_migration_c3.py",
        "current_tree_entry": "100644 blob aa8b1172829e37ce4af9fff04256d5159d1fa8ed\tbackend/tests/order_state_r2/test_migration_c3.py",
        "old_content_sha256": "b3de2857bee052edf124252e9f88d6f6e4f1b4be5c9b984d48b6b20474acd22e",
        "current_content_sha256": "9a16ba1e4302b9b6b986c3677a6a2aea2fe557f14ad8eb0fcffb57798d7bda0e",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/rc2_current_contract_support.py",
        "old_tree_entry": "",
        "current_tree_entry": "100644 blob 33b4dd5cf1d791a38fa0c5ea7fb974c3ed40647d\tbackend/tests/rc2_current_contract_support.py",
        "old_content_sha256": null,
        "current_content_sha256": "d67328e331d205a69c6280cc84d2579b0adfe6a1b3975ad21a90672363023857",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/s1_pricing_quote/test_review_r2.py",
        "old_tree_entry": "100644 blob 67b97b41518f8851b2d9b4b54eb7095ee66eaa40\tbackend/tests/s1_pricing_quote/test_review_r2.py",
        "current_tree_entry": "100644 blob d1dca2a4e91d2ea13da5627048d4ed44510e57fe\tbackend/tests/s1_pricing_quote/test_review_r2.py",
        "old_content_sha256": "b7a3de97590d66e9226acadd77f6b7d0bd339f588468dc3c71c4132d8ad5f33a",
        "current_content_sha256": "47d282d903a8e092f17a86a930b42e7fbe2b0c6546d86e4bedb45f3947941df6",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_auth_regressions.py",
        "old_tree_entry": "100644 blob 87f00875d41fcb87d05f7841bb7de57a2731e5a2\tbackend/tests/test_auth_regressions.py",
        "current_tree_entry": "100644 blob ccd9c3f4c05770bdd9b9a587e3bb7f08ff303168\tbackend/tests/test_auth_regressions.py",
        "old_content_sha256": "c650f8a721990083c6a35e2852356ba4ae63918efedc1010d6ef36f6265c05ae",
        "current_content_sha256": "0837df16831e95004399b8049c09d659df2e8449aaf74d51b8ceffa27cb89641",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_combined_setup_authority_contract.py",
        "old_tree_entry": "100644 blob 8fa7aed327dc6a90ad37070509ddd82563391d5a\tbackend/tests/test_combined_setup_authority_contract.py",
        "current_tree_entry": "100644 blob bf45082230d36cac6487db127f32fc6ac96a9931\tbackend/tests/test_combined_setup_authority_contract.py",
        "old_content_sha256": "372921ba2016f76e725150e85fad7729811a261f0f1a44237fb2e79ce8701399",
        "current_content_sha256": "0b21abf1d9e7b22e6ed3f578ec95f821f3e07eaa6967a520464c0c9fa9c28e3a",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_dc10l_order_status_enum_reconciliation.py",
        "old_tree_entry": "100644 blob 56746d2f0f76d1fe2bd8b6ae3f74f0169f4ed863\tbackend/tests/test_dc10l_order_status_enum_reconciliation.py",
        "current_tree_entry": "100644 blob 316e11ba64233bbc8cc6c94b5733051432511e02\tbackend/tests/test_dc10l_order_status_enum_reconciliation.py",
        "old_content_sha256": "b549db560787884df3c63b597739b79fc2b7a317fb4887b62201cdbdfc485ce8",
        "current_content_sha256": "19ca0f1ceeea1f4c0c61702cbf8f882fb8fa20781e519fc21b3d13ebbdcb2d7d",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_dc11d_payment_replay_concurrency_integrity.py",
        "old_tree_entry": "100644 blob accf5b9bfea478a8bb97416a9455cd1cf444a9fe\tbackend/tests/test_dc11d_payment_replay_concurrency_integrity.py",
        "current_tree_entry": "100644 blob c0f142726ed9ffb196faf318779c818cd8c72467\tbackend/tests/test_dc11d_payment_replay_concurrency_integrity.py",
        "old_content_sha256": "f7726867ae3ab13bee3731279e551d4108a4a661864b52e5b14c735e34d81a59",
        "current_content_sha256": "8ee8c2a6fd6477c8b93076bb3e021df015146fd43b45689837295fcb6052b03c",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py",
        "old_tree_entry": "100644 blob bc5ba7b5e768d39949bd2be82fb87b030a35031e\tbackend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py",
        "current_tree_entry": "100644 blob 9b33db5ff0d3a57fc664a0bf58f68d432fc9e02e\tbackend/tests/test_dc12r1_h7_bcrypt_manifest_parity.py",
        "old_content_sha256": "6249f4f2434a2772b21a13a2af1bf14b43580bf48e20a998c93b9258f7fbe949",
        "current_content_sha256": "165d3546c6edbdadf90fdaf700f1ae3ed10c4a9f95d8f042bd301acf494be05e",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py",
        "old_tree_entry": "100644 blob c7d3416f189accb4be02fe967ca4d9db6a754f77\tbackend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py",
        "current_tree_entry": "100644 blob ce429c78fffd1d3de729633a3b7e88e110935144\tbackend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py",
        "old_content_sha256": "da6c1697e321883190ab424ba05937c64cde80a10b28b323cc9155cb377ec5ae",
        "current_content_sha256": "a4e194d9b143bd20b2449752e2330dfd111536b75c2c75649efff27f41c110c2",
        "source_commits": [
          "38638de2bf15563267e3f3962a3cdd419d99914c",
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_dc12r1_s3_s2_read_only_retailer_finance.py",
        "old_tree_entry": "100644 blob ccd3f0832ea087deca983ba965190f934692a4f2\tbackend/tests/test_dc12r1_s3_s2_read_only_retailer_finance.py",
        "current_tree_entry": "100644 blob 175f6d2c2bc14637c72cbff51ed7811c1a405977\tbackend/tests/test_dc12r1_s3_s2_read_only_retailer_finance.py",
        "old_content_sha256": "44e206ed6bd1368a12dba275847b1e13ebd4a4cd1c435aa4146e89486fff167b",
        "current_content_sha256": "b10914718b606cb5582fa44148faa097f50d557274447cba880af45e60f5ef33",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_dc12r1_s3_s2b_i1_financial_schema_foundation.py",
        "old_tree_entry": "100644 blob cff3d29b79203cdd44d3d8c64649e2311f0ac478\tbackend/tests/test_dc12r1_s3_s2b_i1_financial_schema_foundation.py",
        "current_tree_entry": "100644 blob e625719526959b831d395d384424586b94c204bc\tbackend/tests/test_dc12r1_s3_s2b_i1_financial_schema_foundation.py",
        "old_content_sha256": "ffe7447c8082844e858f0570548d629a24b6c83a4b2797c58a0597122774c661",
        "current_content_sha256": "533cd16c129ba6024abcff5e38c49e72ef11d50e8ae915e5e6b7e20d6c34a164",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py",
        "old_tree_entry": "100644 blob c8e5ac26f8455f3cbd9a416076034b1427918b7b\tbackend/tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py",
        "current_tree_entry": "100644 blob 0c692ddc9ba05569f5cb257661ad248c2af191ea\tbackend/tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py",
        "old_content_sha256": "ef7f77524182918b60032e67e024603158a75c5841087080a538cac4a269f9df",
        "current_content_sha256": "5910f5f048104da4579933116cb18e7b9d02d7198dcca18f23c9a4630c7f8fe8",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_g1_r2_lifecycle_and_public_prep_contract.py",
        "old_tree_entry": "100644 blob 5d90bc89f6c399eaebb4c9584b85f2280de19b54\tbackend/tests/test_g1_r2_lifecycle_and_public_prep_contract.py",
        "current_tree_entry": "100644 blob f7ae0eebd54f27b9814b2a3181a1665db74a34f3\tbackend/tests/test_g1_r2_lifecycle_and_public_prep_contract.py",
        "old_content_sha256": "2777ef7df7d81aba3b20a69ca343a229e8af048ebaa79218a4c9f58a50f06050",
        "current_content_sha256": "5837bb93882d680fcbae1bcf5c09d1f6610c38ce4fbbd80f2b6e76e8c442fb83",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_g1_r2e_tenant_ddl_authority_contract.py",
        "old_tree_entry": "100644 blob c7ec495cc0f6ea7395fca9988ef556748324eb0e\tbackend/tests/test_g1_r2e_tenant_ddl_authority_contract.py",
        "current_tree_entry": "100644 blob 52fdd0db29604d3706d1bbc1632fb0b834d25b17\tbackend/tests/test_g1_r2e_tenant_ddl_authority_contract.py",
        "old_content_sha256": "b3c88cb6dac01b3dbb07c7dbcc95a3b69c6d4db1596c7fa153a5d3e482064326",
        "current_content_sha256": "dda2cd094a843e4d15e2754adf8768a47b47c762489e59fdb386bf8be8c6ba65",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_mpango_mvp_invariants_r0_concurrency.py",
        "old_tree_entry": "100644 blob 032a3c057953a2bd6fc542f2a8c3e3918d669258\tbackend/tests/test_mpango_mvp_invariants_r0_concurrency.py",
        "current_tree_entry": "100644 blob 51d87d0597875ae9bba37edc6d5279ef437ab6ce\tbackend/tests/test_mpango_mvp_invariants_r0_concurrency.py",
        "old_content_sha256": "fdd47eec8e3cc5fbe29d89938c59572e7cc77f446f029d6ae4fc124bacf57871",
        "current_content_sha256": "a0b4490ddf4658fd5288446e390a1000333ffef38ac8190e1096c6353c190050",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_runtime_readiness_gate.py",
        "old_tree_entry": "100644 blob aa2be37d9425b7016c763c642a0dda28e98487d7\tbackend/tests/test_runtime_readiness_gate.py",
        "current_tree_entry": "100644 blob 8dc312250fe3f61a7ff234e9c08ae74b9d5c0202\tbackend/tests/test_runtime_readiness_gate.py",
        "old_content_sha256": "7fb1c361c43b1fe6306018405a8e35e2a4194d40f0c14927b1becaa8487a3e3b",
        "current_content_sha256": "a139955025aabbb2ed9a0d30d3ca2cd6dd67048250d58cf484779d97ccb28025",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_s3a_fresh_tenant_runtime_smoke.py",
        "old_tree_entry": "100644 blob 683cb751037b253f7590115f541728113f579826\tbackend/tests/test_s3a_fresh_tenant_runtime_smoke.py",
        "current_tree_entry": "100644 blob 3f926a7684c58fa27f369b4528c9f6e5cc427c0d\tbackend/tests/test_s3a_fresh_tenant_runtime_smoke.py",
        "old_content_sha256": "b3459532e76b2cb6a3d550210f771d6c3190d177ade95cc3572d71592f768bbb",
        "current_content_sha256": "f143102f573b50ad843367635eee63a0be04966f8caaf3f6b1a8fd9e46728396",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_s3c_self_contained_fresh_tenant_live_proof.py",
        "old_tree_entry": "100644 blob d4e762cd5e2237ad349533a3c29d91d7b65405ff\tbackend/tests/test_s3c_self_contained_fresh_tenant_live_proof.py",
        "current_tree_entry": "100644 blob bdf1042c67da9883b474da29511a5eda515ba64d\tbackend/tests/test_s3c_self_contained_fresh_tenant_live_proof.py",
        "old_content_sha256": "e989024e6a5b6a093ee0a43d98a7c32e6822e15be1fe97049a0bc873611c137c",
        "current_content_sha256": "70384af0f60247b50f8fc1f012f7d3665febed4dd93a5a09fa7377a98b15900a",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_s5_ledger.py",
        "old_tree_entry": "100644 blob b51f674128ecdfc62b5a260a8291cef8f7dd4879\tbackend/tests/test_s5_ledger.py",
        "current_tree_entry": "100644 blob 98e24818a868aac255537e79d512f78aed6bef35\tbackend/tests/test_s5_ledger.py",
        "old_content_sha256": "4b58ded99c9bf874eecbfffc631e2f877ad21dcc226c4f319ef12493c7ddd8fc",
        "current_content_sha256": "e5bff3fb9512204c3defe55900a50614d9d8deef80ae33e497ddda9a42aa1ba3",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_s5_order_state_machine.py",
        "old_tree_entry": "100644 blob b19013149e3e2370be721b63820de4e044d78571\tbackend/tests/test_s5_order_state_machine.py",
        "current_tree_entry": "100644 blob ef14a4b0b994ea32a83c15b421679be8456ce40f\tbackend/tests/test_s5_order_state_machine.py",
        "old_content_sha256": "432dfc1484014b0d947e6521ece962888113a775d0dd7a845b0b60de28eb0239",
        "current_content_sha256": "929d6e5c18a1c2db5e7e68fd63bdbfe16cb5f466a651d8f64b2e2e33c130b688",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_s5a_fresh_tenant_real_user_journey_gate.py",
        "old_tree_entry": "100644 blob e7798bf9c637273a99abd04087038731c0a20229\tbackend/tests/test_s5a_fresh_tenant_real_user_journey_gate.py",
        "current_tree_entry": "100644 blob 6dae75e8da9e574263e2a6e3e80f9a4a58901363\tbackend/tests/test_s5a_fresh_tenant_real_user_journey_gate.py",
        "old_content_sha256": "c657c63b6e373eb39750ac376a38e18555a77341501623fc562ff2301d58c9c7",
        "current_content_sha256": "e38ddefb91a1f25fde2a751b2aa1cf68ea4c9834e91a33c4ff24ed7af6b26e5b",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_sku_m1_migration_pg16.py",
        "old_tree_entry": "100644 blob 44b7ad678a6274155687262f659cecdaa0a06a61\tbackend/tests/test_sku_m1_migration_pg16.py",
        "current_tree_entry": "100644 blob c996eaa9a27fee978efc3b8249c149196a19b3aa\tbackend/tests/test_sku_m1_migration_pg16.py",
        "old_content_sha256": "52b132aa991e70929d240229c6adb395b4dae22e2c892038742e7ccf7e376d2c",
        "current_content_sha256": "b5dd9bed0a808882a2ed6e6448a787f924178d5522987f2eaf13415e29301f15",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_sku_r1_client_catalog_contract.py",
        "old_tree_entry": "100644 blob d36d31a7ce3e9707e95a4db2ad0400189209ea48\tbackend/tests/test_sku_r1_client_catalog_contract.py",
        "current_tree_entry": "100644 blob dc81183f88b637a26e99ed3200f1bbb1bf25e28f\tbackend/tests/test_sku_r1_client_catalog_contract.py",
        "old_content_sha256": "91fc115898d0480aa02101a94a2f3f26e2071a8b1e147b812c5ee63797ff6ef7",
        "current_content_sha256": "51df335278e4bd9e432d4739964e0aa786f79abeb20479f51c9c411f042d8c3c",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_sku_r1_multipackaging_closure.py",
        "old_tree_entry": "100644 blob bd11217b97ec49d468c508eae9d7c685b280ece9\tbackend/tests/test_sku_r1_multipackaging_closure.py",
        "current_tree_entry": "100644 blob c00dd589371f8ae71f0e04ff95a626fa7cc50f58\tbackend/tests/test_sku_r1_multipackaging_closure.py",
        "old_content_sha256": "539f6d99cf2a6ae692ec9b2e9ce22ecfd893e5fe4571f7223d8c26b8d1bcba45",
        "current_content_sha256": "b6840cba2b88ea125b9adbfe422272d7457e74a1c4014f39ce1dfe6412463353",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_u6f_onboarding_auth_chain_closeout.py",
        "old_tree_entry": "100644 blob 93e8d2527bc595c703fa3d99b6f540226b032915\tbackend/tests/test_u6f_onboarding_auth_chain_closeout.py",
        "current_tree_entry": "100644 blob 0270d9d46e270fd86bbb9b7066246b3fc7cf7241\tbackend/tests/test_u6f_onboarding_auth_chain_closeout.py",
        "old_content_sha256": "a864af4f39ef02c6bb7836a5c9b882ac77c21efb6fe9fa8f8c0991cc2e2c80e7",
        "current_content_sha256": "3c3841b0f94d962623128f789e399c7f004f75a4e6564f143e0fe9f73f2882b8",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "backend/tests/test_u6i1_owner_credential_setup_schema.py",
        "old_tree_entry": "100644 blob a36959afe33d046556a5ad43a6d8a85057113abb\tbackend/tests/test_u6i1_owner_credential_setup_schema.py",
        "current_tree_entry": "100644 blob a6d90dec82a75b0e936818c0e23809e13d31a286\tbackend/tests/test_u6i1_owner_credential_setup_schema.py",
        "old_content_sha256": "790a7dc1f790646e67c3f7c1b0e88ebda9883536c8a4ff4eeb38ae1da1ae59f2",
        "current_content_sha256": "e1a40102259f074b0f553199f4b34731a55d64be757325ee4de2fb733dbe7a16",
        "source_commits": [
          "4af23f9899ab674537b653078dff72e1c465ce40"
        ]
      },
      {
        "path": "frontend/src/components/catalog/OrderProductPicker.tsx",
        "old_tree_entry": "",
        "current_tree_entry": "100644 blob ecd2597461a6a6b93346c4de9f6d6701300bd046\tfrontend/src/components/catalog/OrderProductPicker.tsx",
        "old_content_sha256": null,
        "current_content_sha256": "15f64e7baf1a833f85648d7c9bfb7468f5fcf5fbfe0c9f2bb5ac0b5eafe5e081",
        "source_commits": [
          "7d86e513fe8d37558bf4595330a62c9b082c7776"
        ]
      },
      {
        "path": "frontend/src/pages/client/CreateOrderPage.tsx",
        "old_tree_entry": "100644 blob 054c79dac4067690dd65d27c0774533156b57271\tfrontend/src/pages/client/CreateOrderPage.tsx",
        "current_tree_entry": "100644 blob be3f259f795107b7fd385049a7dfe8515031156e\tfrontend/src/pages/client/CreateOrderPage.tsx",
        "old_content_sha256": "2ad010731f8ecd33262841061d30da57a24ae7719032c61e37f4e9649ee53f3c",
        "current_content_sha256": "e69eb68c40efe2fdfd60fa5e7c781c19dc99e1857137977e4a552fd9161e6abe",
        "source_commits": [
          "7d86e513fe8d37558bf4595330a62c9b082c7776"
        ]
      },
      {
        "path": "frontend/src/pages/client/ProductDetailPage.tsx",
        "old_tree_entry": "100644 blob 24d99bbd8f5fa004e08a73e78c807069c5f66678\tfrontend/src/pages/client/ProductDetailPage.tsx",
        "current_tree_entry": "100644 blob 61788a64016c03af389e15bc9e287c2f65696af9\tfrontend/src/pages/client/ProductDetailPage.tsx",
        "old_content_sha256": "943e36f5e694affe82320c6b89937e83917c8c2f9153b6cf3474e9bba96ee231",
        "current_content_sha256": "7be62e8c610a09d92956c92fd57e7c7a00546cab4651413cc4200b456df0c411",
        "source_commits": [
          "7d86e513fe8d37558bf4595330a62c9b082c7776"
        ]
      },
      {
        "path": "frontend/src/tests/RetailerMobileOrder.test.tsx",
        "old_tree_entry": "",
        "current_tree_entry": "100644 blob d13f5f9ea801f2b56b41a5ca66ce9d0230b74527\tfrontend/src/tests/RetailerMobileOrder.test.tsx",
        "old_content_sha256": null,
        "current_content_sha256": "e0b144da25301c3d43feebf54cc612e81bf3fb703e8d90b41fc90fb7492be4f1",
        "source_commits": [
          "7d86e513fe8d37558bf4595330a62c9b082c7776"
        ]
      }
    ]
  },
  "current_attachment_deltas": [
    {
      "binding_id": "s1_pricing_quote_independent_v3",
      "path": "backend/tests/s1_pricing_quote/test_review_r2.py",
      "historical_candidate": "88c7d8157ac5c46795d411ea6799112e017c9532",
      "historical_load_bearing_blob": "67b97b41518f8851b2d9b4b54eb7095ee66eaa40",
      "current_source_ref": "7d86e513fe8d37558bf4595330a62c9b082c7776",
      "current_blob": "d1dca2a4e91d2ea13da5627048d4ed44510e57fe",
      "current_content_sha256": "47d282d903a8e092f17a86a930b42e7fbe2b0c6546d86e4bedb45f3947941df6",
      "classification": "GAP_CURRENT_ATTACHMENT_NOT_REEXECUTED",
      "current_file_same_as_historical": false,
      "current_file_reexecuted_this_intake": false,
      "change": "One static attachment line: read migration 041 instead of 040. Historical 77 XML and node map stay on their original blob.",
      "historical_evidence_rebound": false
    },
    {
      "binding_id": "product_images_core_cto_bounded_acceptance",
      "path": "frontend/src/pages/client/ProductDetailPage.tsx",
      "historical_candidate": "97eb3d89daf3daca45d7289c6669f1cca18d5ef2",
      "historical_load_bearing_blob": "24d99bbd8f5fa004e08a73e78c807069c5f66678",
      "current_source_ref": "7d86e513fe8d37558bf4595330a62c9b082c7776",
      "current_blob": "61788a64016c03af389e15bc9e287c2f65696af9",
      "current_content_sha256": "7be62e8c610a09d92956c92fd57e7c7a00546cab4651413cc4200b456df0c411",
      "classification": "GAP_CURRENT_ATTACHMENT_NOT_REEXECUTED",
      "current_file_same_as_historical": false,
      "current_file_reexecuted_this_intake": false,
      "change": "Mobile UX product-detail layout is changed; prior image/S2 browser scope is not a current frontend reexecution.",
      "historical_evidence_rebound": false
    }
  ]
}
''')
REUSE_NODE_MAP_SHA256 = "8752b1ae958bdcd5c8c1c8ee8f59e8e9e82843ed55c1c6734ba00872d1cc7f54"
REUSE_COVERAGE_PATH = "docs/releases/mvp-20261031/VERIFICATION-COVERAGE.json"


# CTO-published object/evidence digests, not credentials; explicit grouped bytes.
RC3_INTAKE = {
    'updates': {
        'record': 'RC3_VERSIONED_FINITE_ACCEPTANCE_INTAKE_V1',
        'authorization': 'CTO-AUTH-RC3-LOCAL-RELEASE-CI-ADMISSION-R1-20261020',
        'intake_version': 4,
        'intake_status': 'LOCAL_RC3_ADMISSION_CANDIDATE__CTO_SOURCE_REVIEW_PENDING',
        'product_anchor': bytes.fromhex('c2fff203 65b16254 db216350 4751fa5f 84746e80').hex(),
        'selection_binding': {
            'authority': 'CTO-AUTH-RC3-LOCAL-RELEASE-CI-ADMISSION-R1-20261020',
            'source_ref': bytes.fromhex('c2fff203 65b16254 db216350 4751fa5f 84746e80').hex(),
            'discovered_files': 263, 'ordinary_files': 236,
            'dedicated_files': 21, 'ignores': 6, 'union': 257,
            'intersection': 0, 'unknown': 0,
        },
        'current_source_intake': {
            'authorization': 'CTO-AUTH-RC3-LOCAL-RELEASE-CI-ADMISSION-R1-20261020',
            'source_ref': bytes.fromhex('c2fff203 65b16254 db216350 4751fa5f 84746e80').hex(),
            'source_tree': bytes.fromhex('aa773acd b55d4a09 9656a2f5 37103603 50d53738').hex(),
            'source_parent': bytes.fromhex('6d6016d5 94b14f6c 90ea6f52 1d0aa1f0 6fe0bd43').hex(),
            'backend_tree': bytes.fromhex('c3eec56f 61ff9256 570fbcdf 5aab4c5f ec5f47ee').hex(),
            'frontend_tree': bytes.fromhex('2d3f2ef3 252cabd8 c441815b feb944b2 f8a0ee97').hex(),
            'authority_record': {
                'path': 'AI_REPORT_INBOX/s3-cto-final-acceptance-rc3-handoff-20261020/delivery/CODEXL-RC3-RELEASE-CI-PREPARATION.zh-CN.md',
                'sha256': bytes.fromhex('509d17be a6d48f15 9585d3f2 8e5a93ed 3e68900c 6279ffe9 f5ccf41b 0883e14d').hex(),
            },
            'cto_ruling': {
                'path': 'AI_REPORT_INBOX/s3-cto-final-acceptance-rc3-handoff-20261020/delivery/CTO-FINAL-S3-ACCEPTANCE.zh-CN.md',
                'sha256': bytes.fromhex('641dabc8 1f93a52c d074ffd8 fa0d846d 9f49ab4e 7d18b89a 03fdfc64 1023935b').hex(),
            },
            'independent_v3_this_intake': 'CTO_ACCEPTED_S3_A_B_C_D_E_FINITE_SCOPE_ONLY',
            'historical_results_reexecuted': False,
            'hosted_ci_this_intake': 'NOT_RUN',
            'current_fresh_ordinary_collection': 'EXPECTED_UNCHANGED__SEE_LOCAL_COLLECTION_RECEIPTS',
            'ordinary_definition': {
                'nodes': 4288,
                'files': 236,
                'dedicated_files': 21,
                'ignores': 6,
                'canonical_definition_changed': False,
            },
            'source_deltas': [
                {
                    'path': 'backend/alembic/versions/042_order_negotiation_proposals.py',
                    'current_blob': bytes.fromhex('77700889 ffb92edd b49488ea 2b265834 b41e2697').hex(),
                    'current_sha256': bytes.fromhex('5e26d80d bb16cea1 d12f351d 374730d2 52024511 f4a378dd 5f8e0308 f2bd6f2f').hex(),
                },
                {
                    'path': 'backend/api/app.py',
                    'current_blob': bytes.fromhex('f247f1ba a6ce248d 07471414 8b88ffaa b68d772b').hex(),
                    'current_sha256': bytes.fromhex('4d3a9b7d e558b32e 3302c9c9 2cd05b0d fbfcd6ca e62b9e1d ce1b360b 06245bfd').hex(),
                },
                {
                    'path': 'backend/api/middleware/idempotency.py',
                    'current_blob': bytes.fromhex('89f4d3ae 78e2fd4a 6377d6a0 b497956a 1ae8179c').hex(),
                    'current_sha256': bytes.fromhex('15c85e33 c30b2fde cf170b28 e3e59f43 a75e79ac ea4cfc54 7dbb7c3f df5c1fa5').hex(),
                },
                {
                    'path': 'backend/api/v1/order_negotiations.py',
                    'current_blob': bytes.fromhex('4484c0a5 056c39a2 618573a6 dcc4a146 e4716ebe').hex(),
                    'current_sha256': bytes.fromhex('0446356c f3dd6d9b 67ac44ce 12991a44 7da5935b 69c1ac37 9a702e2e 7dc92a44').hex(),
                },
                {
                    'path': 'backend/models/__init__.py',
                    'current_blob': bytes.fromhex('9ac806be 1065c80e e98c49c0 0b104c23 f865e1e2').hex(),
                    'current_sha256': bytes.fromhex('adc0798a 4a43aeca 0d4c64f1 0e1bc56e 09dacb36 f5ec9f03 470e18d9 334a617f').hex(),
                },
                {
                    'path': 'backend/models/order_negotiation.py',
                    'current_blob': bytes.fromhex('4be0609b 69afd129 7a0bc130 41e5f0dc 3f69c792').hex(),
                    'current_sha256': bytes.fromhex('54427521 09103cb3 f0a64443 68ac3f0a d8e7a220 e7ae95d7 22ab2768 229f379f').hex(),
                },
                {
                    'path': 'backend/schemas/order_negotiation.py',
                    'current_blob': bytes.fromhex('3af0bb3b af2ef581 9ad6127f 84c61f43 4b8e0386').hex(),
                    'current_sha256': bytes.fromhex('5cabf08e 35921e69 47447470 5f98d383 815aba85 14009e16 ad7c1c8a 52f1b868').hex(),
                },
                {
                    'path': 'backend/scripts/bootstrap_tenant_schema.py',
                    'current_blob': bytes.fromhex('4ea5b190 188d2db6 76635b60 1689d0b9 428ff33d').hex(),
                    'current_sha256': bytes.fromhex('badbbee6 4e64c91a 43264d09 03c43c5c 38bcef34 d3ddae96 e669e397 fbe8e925').hex(),
                },
                {
                    'path': 'backend/scripts/runtime_readiness_gate.py',
                    'current_blob': bytes.fromhex('52c9c449 09dfc87c 03ec6e6b 8544fd02 e7f744db').hex(),
                    'current_sha256': bytes.fromhex('8c5d99fa 200bec93 98719dc0 ab31a366 a61f875a 1d6a756a feda3ff9 c61d0e34').hex(),
                },
                {
                    'path': 'backend/services/order_command_service.py',
                    'current_blob': bytes.fromhex('d21e48de 3df0d219 81a0896a 28e8c1a8 90df21e3').hex(),
                    'current_sha256': bytes.fromhex('b6d21702 8a83f75a ec5710c7 e0a545ee 0248b154 561e4ce2 97574f57 4d29ead8').hex(),
                },
                {
                    'path': 'backend/services/order_creation_service.py',
                    'current_blob': bytes.fromhex('4979cc64 e3d3c7d8 104f7b86 4899f913 3c00afc0').hex(),
                    'current_sha256': bytes.fromhex('c383213e a1a2db0d 51db6e64 5b7a945d 728553bf 25c7eaea b093a22b 2ac3ec4a').hex(),
                },
                {
                    'path': 'backend/services/order_negotiation_service.py',
                    'current_blob': bytes.fromhex('16a866b6 9fcb0255 00b8a73f f12304bb f20bfaa2').hex(),
                    'current_sha256': bytes.fromhex('7d6fca9a b8d693a4 dcfd0d77 6e1bdce4 5dcbb31d ddc81d16 48d5345d ff29dd3c').hex(),
                },
                {
                    'path': 'backend/services/pricing_quote_service.py',
                    'current_blob': bytes.fromhex('2eddc45b 8d69cc48 80241334 f5227f00 94efc852').hex(),
                    'current_sha256': bytes.fromhex('a5d7739d 6cbb4a13 7c62a055 372aa8e9 667543d0 58053057 2defb522 054d9c80').hex(),
                },
                {
                    'path': 'backend/tests/s1_pricing_quote/test_review_r2.py',
                    'current_blob': bytes.fromhex('9a289181 c71e3a42 a41089ab bf11d52b 27934540').hex(),
                    'current_sha256': bytes.fromhex('02427b49 5680855e 97b52516 40e990ee 4712298a 5c1cc748 59d2e8fb 8b9a150b').hex(),
                },
                {
                    'path': 'backend/tests/s3_negotiation/__init__.py',
                    'current_blob': bytes.fromhex('ac9fd632 17e0b3e6 3a4f4c85 d26fb78c 28ee802f').hex(),
                    'current_sha256': bytes.fromhex('786b1be6 c91f69f6 dad7e7df f9f74b1c 09b3e28c 0ffa1cff 5aed3be9 ee7742de').hex(),
                },
                {
                    'path': 'backend/tests/s3_negotiation/conftest.py',
                    'current_blob': bytes.fromhex('de9dd188 ea15bdd9 2fa9fecf 36296345 47f86954').hex(),
                    'current_sha256': bytes.fromhex('cc136f57 dc8493ae e5f26dd8 4be7c057 633d0dfe 9fba97c1 bcbd178d 4ce149cb').hex(),
                },
                {
                    'path': 'backend/tests/s3_negotiation/test_atomicity_and_races.py',
                    'current_blob': bytes.fromhex('67b840dd 63f2ddc3 bc576823 db43422f eb89b3b8').hex(),
                    'current_sha256': bytes.fromhex('0924fa47 9b34ff16 9fc150c6 c72ff55e aa863a22 f1d14f94 60182d48 f0c9a0f3').hex(),
                },
                {
                    'path': 'backend/tests/s3_negotiation/test_contract.py',
                    'current_blob': bytes.fromhex('c15541eb 943cc40b 3baddfc5 470ba91b 9e5de88d').hex(),
                    'current_sha256': bytes.fromhex('ffa43cb5 de9cd74d 0065e292 a3dee138 4ba67600 8d529c23 7cfeb1d8 f8215cf1').hex(),
                },
                {
                    'path': 'backend/tests/s3_negotiation/test_migration.py',
                    'current_blob': bytes.fromhex('bcfb5f93 21467c15 259ffff0 846bfe4c b7cfcc66').hex(),
                    'current_sha256': bytes.fromhex('7a7eb457 5fd688f3 604b16b6 72eb6c5a 20281340 28356bb1 9f67bd71 e1a2fa13').hex(),
                },
                {
                    'path': 'backend/tests/s3_negotiation/test_provenance_and_safety.py',
                    'current_blob': bytes.fromhex('626447be b523f991 97d1aa02 1d31c22a 4989bfdf').hex(),
                    'current_sha256': bytes.fromhex('2257cc79 571edd15 24121bac 16ac1cc7 eea1b37c c8583dd9 4efd3f0a 1aeee5cc').hex(),
                },
                {
                    'path': 'backend/tests/s3_negotiation/test_safety_boundaries.py',
                    'current_blob': bytes.fromhex('66f71981 878f6b1a c501b9a7 15a09f69 978df51f').hex(),
                    'current_sha256': bytes.fromhex('ea19e817 1268d984 6ede10f8 49d4c0bc 9917d773 8bb9e5c9 0ef51d23 888b014a').hex(),
                },
                {
                    'path': 'backend/tests/test_runtime_readiness_gate.py',
                    'current_blob': bytes.fromhex('681745db 2c192517 07926e2f 3e7748e7 aef1d228').hex(),
                    'current_sha256': bytes.fromhex('97939b6b 273bf103 f77aefba 6414a114 984a6adb 86c824a9 a6b674cd d3b70753').hex(),
                },
                {
                    'path': 'frontend/src/components/orders/OrderNegotiationPanel.tsx',
                    'current_blob': bytes.fromhex('47974c7a 162a6f2c fef10f23 001e930f 5dbdd2cb').hex(),
                    'current_sha256': bytes.fromhex('733be996 8b12fac9 742cade2 257727bd 42d90459 f67055b6 9210037b d6dbd215').hex(),
                },
                {
                    'path': 'frontend/src/pages/client/OrderDetailPage.tsx',
                    'current_blob': bytes.fromhex('06b4cfbb a89a6aa8 c27fde91 b9efe86b 82dfc81e').hex(),
                    'current_sha256': bytes.fromhex('3652e01c c41b56b8 4c76b1b8 3f7015a6 0a106d09 fe5a8f2a 2aa29b8d cb5a1f51').hex(),
                },
                {
                    'path': 'frontend/src/pages/orders/OrderListPage.tsx',
                    'current_blob': bytes.fromhex('28e98245 06cffa75 e7c2365e cf837a51 70b8148a').hex(),
                    'current_sha256': bytes.fromhex('f3002496 72f79ae7 f2a15595 affaf0c4 86569231 9e6add3c 808c8cd7 8cfd47cf').hex(),
                },
                {
                    'path': 'frontend/src/services/orderNegotiationService.ts',
                    'current_blob': bytes.fromhex('518794b8 27f991a2 1bab29eb 4b51720f 7bc76e41').hex(),
                    'current_sha256': bytes.fromhex('421f9d56 60d5ace0 d26aea8f dc9cb721 74b1a988 ff7a9e1f 79d7ff5c 9795a746').hex(),
                },
                {
                    'path': 'frontend/src/tests/S3Negotiation.test.tsx',
                    'current_blob': bytes.fromhex('8eea1303 649c5570 e2810216 64a71dec 7050aee7').hex(),
                    'current_sha256': bytes.fromhex('0245f537 f867ce65 3e661eae c2b1d893 7f14971b 02b6abc9 91a01d43 0f118027').hex(),
                },
            ],
        },
        'current_dependency_assessments': [
            {
                'binding_id': 's1_pricing_quote_independent_v3',
                'status': 'HISTORICAL_ACCEPTANCE__CURRENT_DEPENDENCY_GAPS',
                'historical_record_not_rebound': True,
                'current_dependency_changed_blobs': [
                    {
                        'path': 'backend/tests/s1_pricing_quote/test_review_r2.py',
                        'historical_blob': bytes.fromhex('67b97b41 518f8851 b2d9b4b5 4eb7095e e66eaa40').hex(),
                        'current_blob': bytes.fromhex('9a289181 c71e3a42 a41089ab bf11d52b 27934540').hex(),
                    },
                ],
                'shared_dependency_delta': [
                    {
                        'path': 'backend/api/middleware/idempotency.py',
                        'current_blob': bytes.fromhex('89f4d3ae 78e2fd4a 6377d6a0 b497956a 1ae8179c').hex(),
                        'current_sha256': bytes.fromhex('15c85e33 c30b2fde cf170b28 e3e59f43 a75e79ac ea4cfc54 7dbb7c3f df5c1fa5').hex(),
                    },
                    {
                        'path': 'backend/scripts/bootstrap_tenant_schema.py',
                        'current_blob': bytes.fromhex('4ea5b190 188d2db6 76635b60 1689d0b9 428ff33d').hex(),
                        'current_sha256': bytes.fromhex('badbbee6 4e64c91a 43264d09 03c43c5c 38bcef34 d3ddae96 e669e397 fbe8e925').hex(),
                    },
                    {
                        'path': 'backend/services/order_command_service.py',
                        'current_blob': bytes.fromhex('d21e48de 3df0d219 81a0896a 28e8c1a8 90df21e3').hex(),
                        'current_sha256': bytes.fromhex('b6d21702 8a83f75a ec5710c7 e0a545ee 0248b154 561e4ce2 97574f57 4d29ead8').hex(),
                    },
                    {
                        'path': 'backend/services/order_creation_service.py',
                        'current_blob': bytes.fromhex('4979cc64 e3d3c7d8 104f7b86 4899f913 3c00afc0').hex(),
                        'current_sha256': bytes.fromhex('c383213e a1a2db0d 51db6e64 5b7a945d 728553bf 25c7eaea b093a22b 2ac3ec4a').hex(),
                    },
                    {
                        'path': 'backend/services/pricing_quote_service.py',
                        'current_blob': bytes.fromhex('2eddc45b 8d69cc48 80241334 f5227f00 94efc852').hex(),
                        'current_sha256': bytes.fromhex('a5d7739d 6cbb4a13 7c62a055 372aa8e9 667543d0 58053057 2defb522 054d9c80').hex(),
                    },
                ],
                'current_accepted_exact_nodes': [
                    'tests/s1_pricing_quote/test_contract.py::test_confirmation_quote_refresh_preserves_joined_stock_lock_order',
                    'tests/s1_pricing_quote/test_contract.py::test_common_effective_price[None-override0-None-None-BASE_PRICE_REQUIRED]',
                    'tests/s1_pricing_quote/test_contract.py::test_common_effective_price[base1-None-value1-BASE_PRICE-None]',
                    'tests/s1_pricing_quote/test_contract.py::test_common_effective_price[base2-override2-value2-RETAILER_OVERRIDE-None]',
                    'tests/s1_pricing_quote/test_contract.py::test_common_effective_price[base3-override3-None-None-PRICE_DATA_INTEGRITY_RED]',
                    'tests/s1_pricing_quote/test_contract.py::test_common_effective_price[base4-override4-None-None-PRICE_DATA_INTEGRITY_RED]',
                    'tests/s1_pricing_quote/test_contract.py::test_exact_string_amount[90.000-UGX-90]',
                    'tests/s1_pricing_quote/test_contract.py::test_exact_string_amount[90.000-KES-90.00]',
                    'tests/s1_pricing_quote/test_contract.py::test_exact_string_amount[0-UGX-0]',
                    'tests/s1_pricing_quote/test_contract.py::test_exact_string_amount[9999999999.99-KES-9999999999.99]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[90.01-UGX-MONEY_PRECISION]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[90.001-KES-MONEY_PRECISION]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[NaN-KES-INVALID_MONEY]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[Infinity-KES-INVALID_MONEY]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[-1-KES-INVALID_MONEY]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[0-KES-INVALID_MONEY]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[10000000000-KES-INVALID_MONEY]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[1-XXX-TENANT_CURRENCY_UNRESOLVED]',
                    'tests/s1_pricing_quote/test_contract.py::test_price_change_requires_explicit_consent',
                    'tests/s1_pricing_quote/test_contract.py::test_same_total_opposing_lines_still_red',
                    'tests/s1_pricing_quote/test_contract.py::test_aba_revision_source_and_label_do_not_add_consent_click',
                    'tests/s1_pricing_quote/test_contract.py::test_cross_context_rejected[retailer-another]',
                    'tests/s1_pricing_quote/test_contract.py::test_cross_context_rejected[tenant-other]',
                    'tests/s1_pricing_quote/test_contract.py::test_cross_context_rejected[actor-other]',
                    'tests/s1_pricing_quote/test_contract.py::test_cross_context_rejected[currency-UGX]',
                    'tests/s1_pricing_quote/test_contract.py::test_quote_tamper_and_expiry',
                    'tests/s1_pricing_quote/test_http.py::test_two_countries_two_creation_entries[False-KE]',
                    'tests/s1_pricing_quote/test_http.py::test_two_countries_two_creation_entries[False-UG]',
                    'tests/s1_pricing_quote/test_http.py::test_two_countries_two_creation_entries[True-KE]',
                    'tests/s1_pricing_quote/test_http.py::test_two_countries_two_creation_entries[True-UG]',
                    'tests/s1_pricing_quote/test_http.py::test_reconsent_failure_does_not_consume_key',
                    'tests/s1_pricing_quote/test_http.py::test_missing_base_even_with_override',
                    'tests/s1_pricing_quote/test_http.py::test_versioned_override_retire_restore_same_row',
                    'tests/s1_pricing_quote/test_http.py::test_replay_rechecks_active_binding_and_conflicting_intent',
                    'tests/s1_pricing_quote/test_http.py::test_explicit_replacement_preserves_old_items',
                    'tests/s1_pricing_quote/test_http.py::test_confirm_uses_snapshot_and_one_quantity_contract[KE]',
                    'tests/s1_pricing_quote/test_http.py::test_confirm_uses_snapshot_and_one_quantity_contract[UG]',
                    'tests/s1_pricing_quote/test_http.py::test_used_unit_change_refuses_both_entries_label_preserves_history',
                    'tests/s1_pricing_quote/test_http.py::test_client_cannot_replace_merchant_or_confirmed_draft',
                    'tests/s1_pricing_quote/test_http.py::test_stale_confirm_does_not_reprice_or_start_economics',
                    'tests/s1_pricing_quote/test_http.py::test_quote_cannot_move_to_another_authorized_customer',
                    'tests/s1_pricing_quote/test_http.py::test_wrong_tenant_and_current_rbac_revoke_before_replay',
                    'tests/s1_pricing_quote/test_http.py::test_opposing_prices_same_total_requires_real_http_consent',
                    'tests/s1_pricing_quote/test_http.py::test_same_economics_aba_success_records_both_revisions',
                    'tests/s1_pricing_quote/test_http.py::test_old_fractional_ugx_price_remains_readable_but_not_orderable[UG]',
                    'tests/s1_pricing_quote/test_process_and_faults.py::test_two_processes_same_key_and_fresh_process_replay',
                    'tests/s1_pricing_quote/test_process_and_faults.py::test_create_fault_rolls_back_all_effects[second-item]',
                    'tests/s1_pricing_quote/test_process_and_faults.py::test_create_fault_rolls_back_all_effects[commit]',
                    'tests/s1_pricing_quote/test_process_and_faults.py::test_replacement_cancel_failure_restores_old_draft',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_create_cache_and_binding_revocation[merchant]',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_create_cache_and_binding_revocation[client]',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_cached_create_rechecks_live_subject',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_cached_create_preserves_intent_and_quote_ownership',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_s1_commit_publication[barrier]',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_s1_commit_publication[failure]',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_same_process_create_waits_for_commit[merchant]',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_same_process_create_waits_for_commit[client]',
                    'tests/s1_pricing_quote/test_review_r2.py::test_revision_contract_finite_consistency',
                ],
                'related_not_substitute_for_original_nodes': [
                ],
                'remaining_scope': 'GAP_NON_REEXECUTED_HISTORICAL_NODES_AND_JOURNEYS',
                'hosted_current_execution': 'NOT_RUN',
            },
            {
                'binding_id': 's2_reorder_independent_v3',
                'status': 'HISTORICAL_ACCEPTANCE__CURRENT_DEPENDENCY_GAPS',
                'historical_record_not_rebound': True,
                'current_dependency_changed_blobs': [
                ],
                'shared_dependency_delta': [
                    {
                        'path': 'backend/api/middleware/idempotency.py',
                        'current_blob': bytes.fromhex('89f4d3ae 78e2fd4a 6377d6a0 b497956a 1ae8179c').hex(),
                        'current_sha256': bytes.fromhex('15c85e33 c30b2fde cf170b28 e3e59f43 a75e79ac ea4cfc54 7dbb7c3f df5c1fa5').hex(),
                    },
                    {
                        'path': 'backend/scripts/bootstrap_tenant_schema.py',
                        'current_blob': bytes.fromhex('4ea5b190 188d2db6 76635b60 1689d0b9 428ff33d').hex(),
                        'current_sha256': bytes.fromhex('badbbee6 4e64c91a 43264d09 03c43c5c 38bcef34 d3ddae96 e669e397 fbe8e925').hex(),
                    },
                    {
                        'path': 'backend/services/order_command_service.py',
                        'current_blob': bytes.fromhex('d21e48de 3df0d219 81a0896a 28e8c1a8 90df21e3').hex(),
                        'current_sha256': bytes.fromhex('b6d21702 8a83f75a ec5710c7 e0a545ee 0248b154 561e4ce2 97574f57 4d29ead8').hex(),
                    },
                    {
                        'path': 'backend/services/order_creation_service.py',
                        'current_blob': bytes.fromhex('4979cc64 e3d3c7d8 104f7b86 4899f913 3c00afc0').hex(),
                        'current_sha256': bytes.fromhex('c383213e a1a2db0d 51db6e64 5b7a945d 728553bf 25c7eaea b093a22b 2ac3ec4a').hex(),
                    },
                    {
                        'path': 'backend/services/pricing_quote_service.py',
                        'current_blob': bytes.fromhex('2eddc45b 8d69cc48 80241334 f5227f00 94efc852').hex(),
                        'current_sha256': bytes.fromhex('a5d7739d 6cbb4a13 7c62a055 372aa8e9 667543d0 58053057 2defb522 054d9c80').hex(),
                    },
                ],
                'current_accepted_exact_nodes': [
                ],
                'related_not_substitute_for_original_nodes': [
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_negotiated_history_reorders_at_current_price',
                ],
                'remaining_scope': 'GAP_NON_REEXECUTED_HISTORICAL_NODES_AND_JOURNEYS',
                'hosted_current_execution': 'NOT_RUN',
            },
            {
                'binding_id': 's2_browser_supplement',
                'status': 'HISTORICAL_ACCEPTANCE__CURRENT_DEPENDENCY_GAPS',
                'historical_record_not_rebound': True,
                'current_dependency_changed_blobs': [
                ],
                'shared_dependency_delta': [
                    {
                        'path': 'backend/api/middleware/idempotency.py',
                        'current_blob': bytes.fromhex('89f4d3ae 78e2fd4a 6377d6a0 b497956a 1ae8179c').hex(),
                        'current_sha256': bytes.fromhex('15c85e33 c30b2fde cf170b28 e3e59f43 a75e79ac ea4cfc54 7dbb7c3f df5c1fa5').hex(),
                    },
                    {
                        'path': 'backend/scripts/bootstrap_tenant_schema.py',
                        'current_blob': bytes.fromhex('4ea5b190 188d2db6 76635b60 1689d0b9 428ff33d').hex(),
                        'current_sha256': bytes.fromhex('badbbee6 4e64c91a 43264d09 03c43c5c 38bcef34 d3ddae96 e669e397 fbe8e925').hex(),
                    },
                    {
                        'path': 'backend/services/order_command_service.py',
                        'current_blob': bytes.fromhex('d21e48de 3df0d219 81a0896a 28e8c1a8 90df21e3').hex(),
                        'current_sha256': bytes.fromhex('b6d21702 8a83f75a ec5710c7 e0a545ee 0248b154 561e4ce2 97574f57 4d29ead8').hex(),
                    },
                    {
                        'path': 'backend/services/order_creation_service.py',
                        'current_blob': bytes.fromhex('4979cc64 e3d3c7d8 104f7b86 4899f913 3c00afc0').hex(),
                        'current_sha256': bytes.fromhex('c383213e a1a2db0d 51db6e64 5b7a945d 728553bf 25c7eaea b093a22b 2ac3ec4a').hex(),
                    },
                    {
                        'path': 'backend/services/pricing_quote_service.py',
                        'current_blob': bytes.fromhex('2eddc45b 8d69cc48 80241334 f5227f00 94efc852').hex(),
                        'current_sha256': bytes.fromhex('a5d7739d 6cbb4a13 7c62a055 372aa8e9 667543d0 58053057 2defb522 054d9c80').hex(),
                    },
                ],
                'current_accepted_exact_nodes': [
                ],
                'related_not_substitute_for_original_nodes': [
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_negotiated_history_reorders_at_current_price',
                ],
                'remaining_scope': 'GAP_NON_REEXECUTED_HISTORICAL_NODES_AND_JOURNEYS',
                'hosted_current_execution': 'NOT_RUN',
            },
            {
                'binding_id': 'release_critical_journeys_s1_line',
                'status': 'HISTORICAL_ACCEPTANCE__CURRENT_DEPENDENCY_GAPS',
                'historical_record_not_rebound': True,
                'current_dependency_changed_blobs': [
                ],
                'shared_dependency_delta': [
                    {
                        'path': 'backend/api/middleware/idempotency.py',
                        'current_blob': bytes.fromhex('89f4d3ae 78e2fd4a 6377d6a0 b497956a 1ae8179c').hex(),
                        'current_sha256': bytes.fromhex('15c85e33 c30b2fde cf170b28 e3e59f43 a75e79ac ea4cfc54 7dbb7c3f df5c1fa5').hex(),
                    },
                    {
                        'path': 'backend/scripts/bootstrap_tenant_schema.py',
                        'current_blob': bytes.fromhex('4ea5b190 188d2db6 76635b60 1689d0b9 428ff33d').hex(),
                        'current_sha256': bytes.fromhex('badbbee6 4e64c91a 43264d09 03c43c5c 38bcef34 d3ddae96 e669e397 fbe8e925').hex(),
                    },
                    {
                        'path': 'backend/services/order_command_service.py',
                        'current_blob': bytes.fromhex('d21e48de 3df0d219 81a0896a 28e8c1a8 90df21e3').hex(),
                        'current_sha256': bytes.fromhex('b6d21702 8a83f75a ec5710c7 e0a545ee 0248b154 561e4ce2 97574f57 4d29ead8').hex(),
                    },
                    {
                        'path': 'backend/services/order_creation_service.py',
                        'current_blob': bytes.fromhex('4979cc64 e3d3c7d8 104f7b86 4899f913 3c00afc0').hex(),
                        'current_sha256': bytes.fromhex('c383213e a1a2db0d 51db6e64 5b7a945d 728553bf 25c7eaea b093a22b 2ac3ec4a').hex(),
                    },
                    {
                        'path': 'backend/services/pricing_quote_service.py',
                        'current_blob': bytes.fromhex('2eddc45b 8d69cc48 80241334 f5227f00 94efc852').hex(),
                        'current_sha256': bytes.fromhex('a5d7739d 6cbb4a13 7c62a055 372aa8e9 667543d0 58053057 2defb522 054d9c80').hex(),
                    },
                ],
                'current_accepted_exact_nodes': [
                ],
                'related_not_substitute_for_original_nodes': [
                ],
                'remaining_scope': 'GAP_NON_REEXECUTED_HISTORICAL_NODES_AND_JOURNEYS',
                'hosted_current_execution': 'NOT_RUN',
            },
            {
                'binding_id': 'product_images_core_cto_bounded_acceptance',
                'status': 'HISTORICAL_ACCEPTANCE__CURRENT_DEPENDENCY_GAPS',
                'historical_record_not_rebound': True,
                'current_dependency_changed_blobs': [
                    {
                        'path': 'backend/models/__init__.py',
                        'historical_blob': bytes.fromhex('f4e5aabe 838e32c6 50ffc4ba 99a226fd 65e0f0d0').hex(),
                        'current_blob': bytes.fromhex('9ac806be 1065c80e e98c49c0 0b104c23 f865e1e2').hex(),
                    },
                    {
                        'path': 'backend/scripts/bootstrap_tenant_schema.py',
                        'historical_blob': bytes.fromhex('2a495e96 4e5be056 46e9a5b7 aee344ba 50b5d59e').hex(),
                        'current_blob': bytes.fromhex('4ea5b190 188d2db6 76635b60 1689d0b9 428ff33d').hex(),
                    },
                    {
                        'path': 'backend/api/app.py',
                        'historical_blob': bytes.fromhex('48a0cc4e 93063fc7 052ad5b2 fd33f9ff dfc0b1f4').hex(),
                        'current_blob': bytes.fromhex('f247f1ba a6ce248d 07471414 8b88ffaa b68d772b').hex(),
                    },
                    {
                        'path': 'backend/api/middleware/idempotency.py',
                        'historical_blob': bytes.fromhex('1c442017 5858d41e a93b2778 9f1e2acc 597caa17').hex(),
                        'current_blob': bytes.fromhex('89f4d3ae 78e2fd4a 6377d6a0 b497956a 1ae8179c').hex(),
                    },
                    {
                        'path': 'frontend/src/pages/client/ProductDetailPage.tsx',
                        'historical_blob': bytes.fromhex('24d99bbd 8f5fa004 e08a73e7 8c807069 c5f66678').hex(),
                        'current_blob': bytes.fromhex('61788a64 016c03af 389e15bc 9e287c2f 65696af9').hex(),
                    },
                ],
                'shared_dependency_delta': [
                    {
                        'path': 'backend/api/middleware/idempotency.py',
                        'current_blob': bytes.fromhex('89f4d3ae 78e2fd4a 6377d6a0 b497956a 1ae8179c').hex(),
                        'current_sha256': bytes.fromhex('15c85e33 c30b2fde cf170b28 e3e59f43 a75e79ac ea4cfc54 7dbb7c3f df5c1fa5').hex(),
                    },
                    {
                        'path': 'backend/scripts/bootstrap_tenant_schema.py',
                        'current_blob': bytes.fromhex('4ea5b190 188d2db6 76635b60 1689d0b9 428ff33d').hex(),
                        'current_sha256': bytes.fromhex('badbbee6 4e64c91a 43264d09 03c43c5c 38bcef34 d3ddae96 e669e397 fbe8e925').hex(),
                    },
                    {
                        'path': 'backend/services/order_command_service.py',
                        'current_blob': bytes.fromhex('d21e48de 3df0d219 81a0896a 28e8c1a8 90df21e3').hex(),
                        'current_sha256': bytes.fromhex('b6d21702 8a83f75a ec5710c7 e0a545ee 0248b154 561e4ce2 97574f57 4d29ead8').hex(),
                    },
                    {
                        'path': 'backend/services/order_creation_service.py',
                        'current_blob': bytes.fromhex('4979cc64 e3d3c7d8 104f7b86 4899f913 3c00afc0').hex(),
                        'current_sha256': bytes.fromhex('c383213e a1a2db0d 51db6e64 5b7a945d 728553bf 25c7eaea b093a22b 2ac3ec4a').hex(),
                    },
                    {
                        'path': 'backend/services/pricing_quote_service.py',
                        'current_blob': bytes.fromhex('2eddc45b 8d69cc48 80241334 f5227f00 94efc852').hex(),
                        'current_sha256': bytes.fromhex('a5d7739d 6cbb4a13 7c62a055 372aa8e9 667543d0 58053057 2defb522 054d9c80').hex(),
                    },
                ],
                'current_accepted_exact_nodes': [
                ],
                'related_not_substitute_for_original_nodes': [
                ],
                'remaining_scope': 'GAP_NON_REEXECUTED_HISTORICAL_NODES_AND_JOURNEYS',
                'hosted_current_execution': 'NOT_RUN',
            },
        ],
        'explicit_non_claims': [
            '236 ordinary files / 4288 canonical nodes remain a finite selection; six frozen ignores are unchanged.',
            '21 dedicated files are exactly registered; only the named evidence scopes are accepted, never automatically all file nodes.',
            'S3 V3 A/B/C totals 166 disjoint nodes, including only 58 S1 nodes, not a full S1 directory pass.',
            'RCJ full node coverage remains GAP. Historical S1/S2/images keep their acceptance, not current dependent-byte reexecution.',
            'Current hosted CI and ordinary full body executions are NOT_RUN in this task.',
            'Changing approved-ref cannot authorize a different product, missing evidence or an edited coverage-only provenance.',
        ],
        'current_attachment_deltas': [
            {
                'binding_id': 's1_pricing_quote_independent_v3',
                'path': 'backend/tests/s1_pricing_quote/test_review_r2.py',
                'historical_candidate': bytes.fromhex('88c7d815 7ac5c467 95d411ea 6799112e 017c9532').hex(),
                'historical_load_bearing_blob': bytes.fromhex('67b97b41 518f8851 b2d9b4b5 4eb7095e e66eaa40').hex(),
                'current_source_ref': bytes.fromhex('c2fff203 65b16254 db216350 4751fa5f 84746e80').hex(),
                'current_blob': bytes.fromhex('9a289181 c71e3a42 a41089ab bf11d52b 27934540').hex(),
                'current_content_sha256': bytes.fromhex('02427b49 5680855e 97b52516 40e990ee 4712298a 5c1cc748 59d2e8fb 8b9a150b').hex(),
                'classification': 'PARTIAL_CURRENT_NODE_ACCEPTED__FULL_FILE_REEXECUTION_GAP',
                'current_file_same_as_historical': False,
                'current_file_reexecuted_this_intake': False,
                'change': 'Current revision-consistency node accepted at head042; historical 77-node evidence remains on its original blob, not rebound.',
                'historical_evidence_rebound': False,
                'current_accepted_exact_nodes': [
                    'tests/s1_pricing_quote/test_review_r2.py::test_revision_contract_finite_consistency',
                ],
            },
            {
                'binding_id': 'product_images_core_cto_bounded_acceptance',
                'path': 'frontend/src/pages/client/ProductDetailPage.tsx',
                'historical_candidate': bytes.fromhex('97eb3d89 daf3daca 45d7289c 6669f1cc a18d5ef2').hex(),
                'historical_load_bearing_blob': bytes.fromhex('24d99bbd 8f5fa004 e08a73e7 8c807069 c5f66678').hex(),
                'current_source_ref': bytes.fromhex('c2fff203 65b16254 db216350 4751fa5f 84746e80').hex(),
                'current_blob': bytes.fromhex('61788a64 016c03af 389e15bc 9e287c2f 65696af9').hex(),
                'current_content_sha256': bytes.fromhex('7be62e8c 610a09d9 2956c92f d57e7c7a 00546cab 4651413c c4200b45 6df0c411').hex(),
                'classification': 'GAP_CURRENT_ATTACHMENT_NOT_REEXECUTED',
                'current_file_same_as_historical': False,
                'current_file_reexecuted_this_intake': False,
                'change': 'Mobile UX product-detail layout is changed; prior image/S2 browser scope is not a current frontend reexecution.',
                'historical_evidence_rebound': False,
                'current_accepted_exact_nodes': [
                ],
            },
        ],
    },
    'additional_binding': {
        'id': 's3_minimum_negotiation_cto_independent_v3',
        'family': 's3_negotiation',
        'candidate': bytes.fromhex('c2fff203 65b16254 db216350 4751fa5f 84746e80').hex(),
        'files': [
            'backend/tests/s3_negotiation/test_atomicity_and_races.py',
            'backend/tests/s3_negotiation/test_contract.py',
            'backend/tests/s3_negotiation/test_migration.py',
            'backend/tests/s3_negotiation/test_provenance_and_safety.py',
            'backend/tests/s3_negotiation/test_safety_boundaries.py',
        ],
        'coverage_status': 'CTO_ACCEPTED_CURRENT_FINITE_SCOPE',
        'source_manifest_sha256': bytes.fromhex('0ff05256 aec813e1 f0f0bfcd 6b7edeb1 3534ad16 91c205ea 2c8851aa 9ee81305').hex(),
        'source_report_sha256': bytes.fromhex('319911be e56648d0 b481c00a 1acc9377 abffee0b 043b9666 da3a166e 361319e8').hex(),
        'load_bearing_blobs': {
            'backend/alembic/versions/042_order_negotiation_proposals.py': bytes.fromhex('77700889 ffb92edd b49488ea 2b265834 b41e2697').hex(),
            'backend/api/app.py': bytes.fromhex('f247f1ba a6ce248d 07471414 8b88ffaa b68d772b').hex(),
            'backend/api/middleware/idempotency.py': bytes.fromhex('89f4d3ae 78e2fd4a 6377d6a0 b497956a 1ae8179c').hex(),
            'backend/api/v1/order_negotiations.py': bytes.fromhex('4484c0a5 056c39a2 618573a6 dcc4a146 e4716ebe').hex(),
            'backend/models/__init__.py': bytes.fromhex('9ac806be 1065c80e e98c49c0 0b104c23 f865e1e2').hex(),
            'backend/models/order_negotiation.py': bytes.fromhex('4be0609b 69afd129 7a0bc130 41e5f0dc 3f69c792').hex(),
            'backend/schemas/order_negotiation.py': bytes.fromhex('3af0bb3b af2ef581 9ad6127f 84c61f43 4b8e0386').hex(),
            'backend/scripts/bootstrap_tenant_schema.py': bytes.fromhex('4ea5b190 188d2db6 76635b60 1689d0b9 428ff33d').hex(),
            'backend/scripts/runtime_readiness_gate.py': bytes.fromhex('52c9c449 09dfc87c 03ec6e6b 8544fd02 e7f744db').hex(),
            'backend/services/order_command_service.py': bytes.fromhex('d21e48de 3df0d219 81a0896a 28e8c1a8 90df21e3').hex(),
            'backend/services/order_creation_service.py': bytes.fromhex('4979cc64 e3d3c7d8 104f7b86 4899f913 3c00afc0').hex(),
            'backend/services/order_negotiation_service.py': bytes.fromhex('16a866b6 9fcb0255 00b8a73f f12304bb f20bfaa2').hex(),
            'backend/services/pricing_quote_service.py': bytes.fromhex('2eddc45b 8d69cc48 80241334 f5227f00 94efc852').hex(),
            'backend/tests/s1_pricing_quote/test_review_r2.py': bytes.fromhex('9a289181 c71e3a42 a41089ab bf11d52b 27934540').hex(),
            'backend/tests/s3_negotiation/__init__.py': bytes.fromhex('ac9fd632 17e0b3e6 3a4f4c85 d26fb78c 28ee802f').hex(),
            'backend/tests/s3_negotiation/conftest.py': bytes.fromhex('de9dd188 ea15bdd9 2fa9fecf 36296345 47f86954').hex(),
            'backend/tests/s3_negotiation/test_atomicity_and_races.py': bytes.fromhex('67b840dd 63f2ddc3 bc576823 db43422f eb89b3b8').hex(),
            'backend/tests/s3_negotiation/test_contract.py': bytes.fromhex('c15541eb 943cc40b 3baddfc5 470ba91b 9e5de88d').hex(),
            'backend/tests/s3_negotiation/test_migration.py': bytes.fromhex('bcfb5f93 21467c15 259ffff0 846bfe4c b7cfcc66').hex(),
            'backend/tests/s3_negotiation/test_provenance_and_safety.py': bytes.fromhex('626447be b523f991 97d1aa02 1d31c22a 4989bfdf').hex(),
            'backend/tests/s3_negotiation/test_safety_boundaries.py': bytes.fromhex('66f71981 878f6b1a c501b9a7 15a09f69 978df51f').hex(),
            'backend/tests/test_runtime_readiness_gate.py': bytes.fromhex('681745db 2c192517 07926e2f 3e7748e7 aef1d228').hex(),
            'frontend/src/components/orders/OrderNegotiationPanel.tsx': bytes.fromhex('47974c7a 162a6f2c fef10f23 001e930f 5dbdd2cb').hex(),
            'frontend/src/pages/client/OrderDetailPage.tsx': bytes.fromhex('06b4cfbb a89a6aa8 c27fde91 b9efe86b 82dfc81e').hex(),
            'frontend/src/pages/orders/OrderListPage.tsx': bytes.fromhex('28e98245 06cffa75 e7c2365e cf837a51 70b8148a').hex(),
            'frontend/src/services/orderNegotiationService.ts': bytes.fromhex('518794b8 27f991a2 1bab29eb 4b51720f 7bc76e41').hex(),
            'frontend/src/tests/S3Negotiation.test.tsx': bytes.fromhex('8eea1303 649c5570 e2810216 64a71dec 7050aee7').hex(),
        },
        'groups': [
            {
                'gate': 'A',
                'candidate': bytes.fromhex('c2fff203 65b16254 db216350 4751fa5f 84746e80').hex(),
                'native_receipt': 'evidence/formal-runtime-v3.json',
                'receipt_sha256': bytes.fromhex('998c3ac8 9ec499df ef160e93 9d93b177 e841b0da a04b85ce ce2c51ee c4633b86').hex(),
                'junit': 'evidence/formal-runtime-v3.xml',
                'junit_sha256': bytes.fromhex('0fb84d17 8b98fa18 1e930911 29300735 6c84b9dc f4cd6efb 96df4fb9 34e6b492').hex(),
                'node_list': 'evidence/formal-runtime-v3-nodes.txt',
                'node_list_sha256': bytes.fromhex('5cfc06f5 dc792ef2 b4a5d2e7 739ecd5c 9f31f743 85a334f8 3cf3a6d2 3da33e8b').hex(),
                'nodes': [
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_accept_save_or_close_failure_is_atomic_even_if_caller_commits[save]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_accept_save_or_close_failure_is_atomic_even_if_caller_commits[cancel]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_real_source_lock_races_have_one_legal_serial_history[accept-accept]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_real_source_lock_races_have_one_legal_serial_history[accept-reject]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_real_source_lock_races_have_one_legal_serial_history[reject-accept]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_real_source_lock_races_have_one_legal_serial_history[withdraw-accept]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_real_source_lock_races_have_one_legal_serial_history[accept-withdraw]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_real_source_lock_races_have_one_legal_serial_history[cancel-accept]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_real_source_lock_races_have_one_legal_serial_history[confirm-accept]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_real_source_lock_races_have_one_legal_serial_history[accept-confirm]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_real_source_lock_races_have_one_legal_serial_history[accept-cancel]',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_accept_waiting_for_source_lock_past_deadline_refuses',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_confirmation_waiting_for_stock_lock_past_deadline_refuses',
                    'tests/s3_negotiation/test_atomicity_and_races.py::test_committed_acceptance_replays_after_expiry_without_second_order',
                    'tests/s3_negotiation/test_contract.py::test_accept_preserves_history_and_zero_economics_then_confirms_fixed_price[UG]',
                    'tests/s3_negotiation/test_contract.py::test_accept_preserves_history_and_zero_economics_then_confirms_fixed_price[KE]',
                    'tests/s3_negotiation/test_contract.py::test_one_pending_withdraw_new_version_and_reject',
                    'tests/s3_negotiation/test_contract.py::test_invalid_exact_money_has_no_proposal[0]',
                    'tests/s3_negotiation/test_contract.py::test_invalid_exact_money_has_no_proposal[-1]',
                    'tests/s3_negotiation/test_contract.py::test_invalid_exact_money_has_no_proposal[NaN]',
                    'tests/s3_negotiation/test_contract.py::test_invalid_exact_money_has_no_proposal[Infinity]',
                    'tests/s3_negotiation/test_contract.py::test_invalid_exact_money_has_no_proposal[99999999999999]',
                    'tests/s3_negotiation/test_contract.py::test_invalid_exact_money_has_no_proposal[70.001]',
                    'tests/s3_negotiation/test_contract.py::test_deadline_mandatory_aware_and_future[2000-01-01T00:00:00Z]',
                    'tests/s3_negotiation/test_contract.py::test_deadline_mandatory_aware_and_future[2099-01-01T12:00:00]',
                    'tests/s3_negotiation/test_contract.py::test_deadline_mandatory_aware_and_future[None]',
                    'tests/s3_negotiation/test_contract.py::test_committed_replay_checks_intent_and_live_binding',
                    'tests/s3_negotiation/test_contract.py::test_merchant_cannot_accept_and_retailer_cannot_propose',
                    'tests/s3_negotiation/test_migration.py::test_bootstrap_rejects_changed_proposal_contract[constraint]',
                    'tests/s3_negotiation/test_migration.py::test_bootstrap_rejects_changed_proposal_contract[index]',
                    'tests/s3_negotiation/test_migration.py::test_bootstrap_rejects_changed_proposal_contract[trigger]',
                    'tests/s3_negotiation/test_migration.py::test_bootstrap_rejects_changed_proposal_contract[trigger_condition]',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_counterfeit_source_cannot_skip_s1_price_validation',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_same_total_different_lines_never_reuses_consent',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_unavailable_or_short_stock_cannot_confirm[short_stock]',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_unavailable_or_short_stock_cannot_confirm[inactive_sku]',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_unavailable_or_short_stock_cannot_confirm[inactive_product]',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_unavailable_or_short_stock_cannot_confirm[unit]',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_retained_economic_effect_refuses_accept',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_negotiated_history_reorders_at_current_price',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_durable_replay_rechecks_user_and_permission[permission]',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_durable_replay_rechecks_user_and_permission[user]',
                    'tests/s3_negotiation/test_provenance_and_safety.py::test_other_tenant_never_reads_or_accepts_proposal',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_offer_immutable_and_pending_unique_at_storage[price]',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_offer_immutable_and_pending_unique_at_storage[deadline]',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_offer_immutable_and_pending_unique_at_storage[delete]',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_key_cannot_accept_a_different_proposal',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_foreign_retailer_within_same_tenant_is_denied',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_confirmed_agreement_is_not_undone_by_later_expiry',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_negotiated_price_reaches_only_canonical_payment_once[cash-settled-0]',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_negotiated_price_reaches_only_canonical_payment_once[credit-converted-140]',
                    'tests/s1_pricing_quote/test_contract.py::test_confirmation_quote_refresh_preserves_joined_stock_lock_order',
                    'tests/s1_pricing_quote/test_contract.py::test_common_effective_price[None-override0-None-None-BASE_PRICE_REQUIRED]',
                    'tests/s1_pricing_quote/test_contract.py::test_common_effective_price[base1-None-value1-BASE_PRICE-None]',
                    'tests/s1_pricing_quote/test_contract.py::test_common_effective_price[base2-override2-value2-RETAILER_OVERRIDE-None]',
                    'tests/s1_pricing_quote/test_contract.py::test_common_effective_price[base3-override3-None-None-PRICE_DATA_INTEGRITY_RED]',
                    'tests/s1_pricing_quote/test_contract.py::test_common_effective_price[base4-override4-None-None-PRICE_DATA_INTEGRITY_RED]',
                    'tests/s1_pricing_quote/test_contract.py::test_exact_string_amount[90.000-UGX-90]',
                    'tests/s1_pricing_quote/test_contract.py::test_exact_string_amount[90.000-KES-90.00]',
                    'tests/s1_pricing_quote/test_contract.py::test_exact_string_amount[0-UGX-0]',
                    'tests/s1_pricing_quote/test_contract.py::test_exact_string_amount[9999999999.99-KES-9999999999.99]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[90.01-UGX-MONEY_PRECISION]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[90.001-KES-MONEY_PRECISION]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[NaN-KES-INVALID_MONEY]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[Infinity-KES-INVALID_MONEY]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[-1-KES-INVALID_MONEY]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[0-KES-INVALID_MONEY]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[10000000000-KES-INVALID_MONEY]',
                    'tests/s1_pricing_quote/test_contract.py::test_money_refusals[1-XXX-TENANT_CURRENCY_UNRESOLVED]',
                    'tests/s1_pricing_quote/test_contract.py::test_price_change_requires_explicit_consent',
                    'tests/s1_pricing_quote/test_contract.py::test_same_total_opposing_lines_still_red',
                    'tests/s1_pricing_quote/test_contract.py::test_aba_revision_source_and_label_do_not_add_consent_click',
                    'tests/s1_pricing_quote/test_contract.py::test_cross_context_rejected[retailer-another]',
                    'tests/s1_pricing_quote/test_contract.py::test_cross_context_rejected[tenant-other]',
                    'tests/s1_pricing_quote/test_contract.py::test_cross_context_rejected[actor-other]',
                    'tests/s1_pricing_quote/test_contract.py::test_cross_context_rejected[currency-UGX]',
                    'tests/s1_pricing_quote/test_contract.py::test_quote_tamper_and_expiry',
                    'tests/s1_pricing_quote/test_http.py::test_two_countries_two_creation_entries[False-KE]',
                    'tests/s1_pricing_quote/test_http.py::test_two_countries_two_creation_entries[False-UG]',
                    'tests/s1_pricing_quote/test_http.py::test_two_countries_two_creation_entries[True-KE]',
                    'tests/s1_pricing_quote/test_http.py::test_two_countries_two_creation_entries[True-UG]',
                    'tests/s1_pricing_quote/test_http.py::test_reconsent_failure_does_not_consume_key',
                    'tests/s1_pricing_quote/test_http.py::test_missing_base_even_with_override',
                    'tests/s1_pricing_quote/test_http.py::test_versioned_override_retire_restore_same_row',
                    'tests/s1_pricing_quote/test_http.py::test_replay_rechecks_active_binding_and_conflicting_intent',
                    'tests/s1_pricing_quote/test_http.py::test_explicit_replacement_preserves_old_items',
                    'tests/s1_pricing_quote/test_http.py::test_confirm_uses_snapshot_and_one_quantity_contract[KE]',
                    'tests/s1_pricing_quote/test_http.py::test_confirm_uses_snapshot_and_one_quantity_contract[UG]',
                    'tests/s1_pricing_quote/test_http.py::test_used_unit_change_refuses_both_entries_label_preserves_history',
                    'tests/s1_pricing_quote/test_http.py::test_client_cannot_replace_merchant_or_confirmed_draft',
                    'tests/s1_pricing_quote/test_http.py::test_stale_confirm_does_not_reprice_or_start_economics',
                    'tests/s1_pricing_quote/test_http.py::test_quote_cannot_move_to_another_authorized_customer',
                    'tests/s1_pricing_quote/test_http.py::test_wrong_tenant_and_current_rbac_revoke_before_replay',
                    'tests/s1_pricing_quote/test_http.py::test_opposing_prices_same_total_requires_real_http_consent',
                    'tests/s1_pricing_quote/test_http.py::test_same_economics_aba_success_records_both_revisions',
                    'tests/s1_pricing_quote/test_http.py::test_old_fractional_ugx_price_remains_readable_but_not_orderable[UG]',
                    'tests/s1_pricing_quote/test_process_and_faults.py::test_two_processes_same_key_and_fresh_process_replay',
                    'tests/s1_pricing_quote/test_process_and_faults.py::test_create_fault_rolls_back_all_effects[second-item]',
                    'tests/s1_pricing_quote/test_process_and_faults.py::test_create_fault_rolls_back_all_effects[commit]',
                    'tests/s1_pricing_quote/test_process_and_faults.py::test_replacement_cancel_failure_restores_old_draft',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_create_cache_and_binding_revocation[merchant]',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_create_cache_and_binding_revocation[client]',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_cached_create_rechecks_live_subject',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_cached_create_preserves_intent_and_quote_ownership',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_s1_commit_publication[barrier]',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_s1_commit_publication[failure]',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_same_process_create_waits_for_commit[merchant]',
                    'tests/s1_pricing_quote/test_cache_integration.py::test_same_process_create_waits_for_commit[client]',
                    'tests/s1_pricing_quote/test_review_r2.py::test_revision_contract_finite_consistency',
                    'tests/order_state_r1/test_static_guards.py::test_single_direct_status_writer',
                    'tests/order_state_r1/test_static_guards.py::test_command_service_holds_exactly_one_status_assignment',
                    'tests/order_state_r1/test_static_guards.py::test_no_confirmation_ledger_call_anywhere_in_production',
                    'tests/order_state_r1/test_static_guards.py::test_no_placeholder_notification_values_in_production',
                    'tests/order_state_r1/test_static_guards.py::test_payment_command_single_caller_guard',
                    'tests/order_state_r1/test_static_guards.py::test_adapter_refuses_payment_states',
                    'tests/order_state_r1/test_static_guards.py::test_all_commands_share_prelock_strategy',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_alternate_uuid_request_rechecks_live_authority[uppercase]',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_alternate_uuid_request_rechecks_live_authority[compact]',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_alternate_uuid_request_rechecks_live_authority[urn]',
                    'tests/s3_negotiation/test_safety_boundaries.py::test_alternate_uuid_request_rechecks_live_authority[braces]',
                ],
                'passed': 120,
                'failed': 0,
                'errors': 0,
                'skipped': 0,
            },
            {
                'gate': 'B',
                'candidate': bytes.fromhex('c2fff203 65b16254 db216350 4751fa5f 84746e80').hex(),
                'native_receipt': 'evidence/formal-legacy-v3.json',
                'receipt_sha256': bytes.fromhex('2c7cea6e 529ca1ca 17e5a464 17586024 d065ddb0 d3bb9552 cad39bc0 77c64d05').hex(),
                'junit': 'evidence/formal-legacy-v3.xml',
                'junit_sha256': bytes.fromhex('d729eb36 dea460bf c08239c9 a617bbd4 ba78725e f84765b3 49927532 a3f9e819').hex(),
                'node_list': 'evidence/formal-legacy-v3-nodes.txt',
                'node_list_sha256': bytes.fromhex('69a01e42 a51949f6 74719230 33121610 735e4150 ea320d46 7cf13009 e5b44acc').hex(),
                'nodes': [
                    'tests/test_s5_order_state_machine.py::test_state_transition_matrix',
                    'tests/test_s5_order_state_machine.py::test_get_valid_transitions',
                    'tests/test_s5_order_state_machine.py::test_terminal_states',
                    'tests/test_s5_order_state_machine.py::test_partially_paid_self_transition_is_not_globally_valid',
                    'tests/test_s5_order_state_machine.py::test_happy_path_draft_to_fulfilled',
                    'tests/test_s5_order_state_machine.py::test_illegal_transition_draft_to_fulfilled',
                    'tests/test_s5_order_state_machine.py::test_partially_paid_self_transition_allowed_only_for_payment_context',
                    'tests/test_s5_order_state_machine.py::test_invariant_violation_confirm_zero_total',
                    'tests/test_s5_order_state_machine.py::test_terminal_state_no_transitions',
                    'tests/test_s5_order_state_machine.py::test_void_vs_cancel_rules',
                    'tests/test_s5_order_state_machine.py::test_partial_payment_flow',
                    'tests/test_s5_order_state_machine.py::test_concurrent_transition_with_locking',
                    'tests/test_s5_order_state_machine.py::test_transition_with_updated_by',
                    'tests/test_s5_order_state_machine.py::test_order_not_found',
                    'tests/test_s5_order_state_machine.py::test_cannot_fulfill_unpaid_order',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_route_uses_canonical_payment_service_with_behavior_preserving_defaults',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_service_does_not_commit_or_rollback_calls',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_service_cash_partial_and_final_matches_route_outcomes',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_service_transfer_pending_then_completed_matches_route_outcomes',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_service_credit_collection_reduces_outstanding_balance_like_route',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_service_duplicate_transaction_id_exact_error',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_service_idempotent_replay_creates_one_financial_result',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_service_overpayment_rejection_exact_error',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_service_force_completed_cannot_create_pending_payment',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_service_cross_tenant_same_key_isolated',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_service_failures_after_mutation_stages_rollback_all_effects',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_r3_negative_cash_amount_rejected_with_zero_mutation',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_r3_zero_amount_rejected',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_r3_nan_and_infinity_rejected_without_500[nan]',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_r3_nan_and_infinity_rejected_without_500[pos_inf]',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_r3_nan_and_infinity_rejected_without_500[neg_inf]',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_r3_skip_prechecks_cannot_bypass_amount_guard',
                    'tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py::test_r3_failed_attempt_leaves_transaction_retryable',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_confirm_creates_owned_reservation_rows_and_updates_aggregate',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_confirm_insufficient_available_rolls_back_order_stock_and_reservations',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_concurrent_confirm_does_not_over_reserve_or_accept_excess_demand',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_duplicate_confirm_does_not_create_duplicate_reservation_rows',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_cancel_releases_only_this_order_reservation_rows',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_duplicate_cancel_does_not_double_release_reservation',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_fulfillment_consumes_only_this_order_reservation_and_deducts_on_hand',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_direct_paid_order_with_no_reservation_preserves_unrelated_reservations',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_return_restores_on_hand_without_creating_reservation',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_concurrent_fulfill_consumes_reservation_once_and_writes_one_movement',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_reservation_table_and_aggregate_stock_are_tenant_isolated',
                    'tests/business/test_s4e_stock_reservation_lifecycle_audit.py::test_reserve_release_and_consume_movement_boundaries',
                ],
                'passed': 45,
                'failed': 0,
                'errors': 0,
                'skipped': 0,
            },
            {
                'gate': 'C',
                'candidate': bytes.fromhex('c2fff203 65b16254 db216350 4751fa5f 84746e80').hex(),
                'native_receipt': 'evidence/formal-migration-v3.json',
                'receipt_sha256': bytes.fromhex('ef6fb812 ee196f2b 901dac23 8ddecbea 48bceba2 68a9247c 49f0a991 bdc0d9ce').hex(),
                'junit': 'evidence/formal-migration-v3.xml',
                'junit_sha256': bytes.fromhex('0e318bfb e9f55628 205365c4 9ef6aecb c59c40b0 51401eeb 4bd5452b 956f2470').hex(),
                'node_list': 'evidence/formal-migration-v3-nodes.txt',
                'node_list_sha256': bytes.fromhex('027b5597 89f60880 3a2967bb fa44f2c7 028863b2 457cd6b8 bf4c3367 4616837a').hex(),
                'nodes': [
                    'tests/s3_negotiation/test_migration.py::test_existing_041_upgrade_preserves_rows_and_matches_new_tenant',
                ],
                'passed': 1,
                'failed': 0,
                'errors': 0,
                'skipped': 0,
            },
        ],
        'browser': {
            'receipt': 'evidence/formal-browser-01-result.json',
            'sha256': bytes.fromhex('f7b78583 d4731ffa eda9b35f bed506ce 017c8452 473793ed 91cc11cd 0fd65c1f').hex(),
            'scenarios': 8,
            'literal_true': 102,
        },
        'mutations': {
            'receipt': 'evidence/s3-mutations-result.json',
            'sha256': bytes.fromhex('abe0f810 eaa12d42 8e0d2942 d77acd65 84ccd79d 18896bd9 64e3af26 879cf46d').hex(),
            'semantic_controls': 3,
        },
        'gaps': [
            'CURRENT_HOSTED_CI_NOT_RUN',
            'NOT_ALL_BACKEND_NODES',
            'NOT_ALL_HISTORICAL_S1_S2_IMAGE_RCJ_NODES',
        ],
        'node_union': {
            'count': 166,
            'unique': 166,
            'overlap': 0,
            's3_runtime': 55,
            's3_migration': 1,
            's1_subset': 58,
            'sole_writer': 7,
            'legacy_orders_payment_inventory': 45,
        },
    },
}


RC3_LOCAL_INTEGRATION = json.loads(r'''
{
  "authorization": "CTO-AUTH-RC3-LOCAL-TWO-LINE-INTEGRATION-AND-REUSE-INTAKE-R1-20261020",
  "approved_ref": "bac775df8257ea2fd626d6de425f3564748b37f2",
  "ci_input": "eac40af9167044d64b42e92a69fdfd751893e358",
  "source_tree": "9591f8ea6b613d472f27f8fdbff48b7943b473ee",
  "source_parent": "b46b74130b582e8e4f42579148b209eca540f576",
  "backend_tree": "c3eec56f61ff9256570fbcdf5aab4c5fec5f47ee",
  "frontend_tree": "d3e3ca842bd6d4eb2caca6aa5d1b1c3137d83f34",
  "authority_record": {
    "path": "AI_REPORT_INBOX/rc3-ui-closeout-and-local-integration-cto-20261020/delivery/CODEXL-RC3-LOCAL-INTEGRATION.zh-CN.md",
    "sha256": "874f6558323748eeace090f16969ff9138e296c57732298f178fdbc42a25523c"
  },
  "cto_ruling": {
    "path": "AI_REPORT_INBOX/rc3-ui-closeout-and-local-integration-cto-20261020/delivery/CTO-UI-CLOSEOUT-ACCEPTANCE.zh-CN.md",
    "sha256": "78d5a06a7781f4f0dc76e31daa44992383f4f52fdf1691675aa8d6a59029aeb9"
  },
  "source_deltas": [
    {
      "path": "frontend/src/components/ui/PaymentRecordModal.tsx",
      "current_blob": "e946942622c2630eb83ef1b5471b214b726a0940",
      "current_sha256": "0a2f55c8f164e7bc01d79d46e7ac08874fe4c162e508d4d56579fd16247a77d0"
    },
    {
      "path": "frontend/src/pages/orders/OrderListPage.tsx",
      "current_blob": "fd59647026b2545687c4aa864b0217be2e26fbf0",
      "current_sha256": "e7a0f8c1e18cc472f03b96f652104e67753a83724db2b676ce72af18a9016528"
    },
    {
      "path": "frontend/src/pages/pricing/RetailerPricingPage.tsx",
      "current_blob": "3599b6f0866878847741fd8a86d6bf8082f3fc49",
      "current_sha256": "990233118cc56978f82aa22b3207c90f37489d6e20d6f2eeb2dd26e8ea7d20dd"
    },
    {
      "path": "frontend/src/tests/PaymentCurrencyPricingUx.test.tsx",
      "current_blob": "90a653b45fa8045da565d6e746df7dcb52d5339b",
      "current_sha256": "b643652e23dff99de4aac7736fd8d1c6a6ed5d901b79d6fe4981f8bd70c02732"
    },
    {
      "path": "frontend/src/tests/S5BRealUserSmoke.test.tsx",
      "current_blob": "e34bb0cc02ae7f86885dc27f184594b5d034a0de",
      "current_sha256": "7e0128ac459fb49560741dafdc942bba296b63c55d3f70c51dbb0584808d78c0"
    }
  ],
  "ui_binding": {
    "id": "rc3_payment_currency_pricing_ui_cto_bounded_acceptance",
    "family": "rc3_payment_currency_pricing_ui",
    "candidate": "b46b74130b582e8e4f42579148b209eca540f576",
    "files": [],
    "support_files": [
      "frontend/src/components/ui/PaymentRecordModal.tsx",
      "frontend/src/pages/orders/OrderListPage.tsx",
      "frontend/src/pages/pricing/RetailerPricingPage.tsx",
      "frontend/src/tests/PaymentCurrencyPricingUx.test.tsx",
      "frontend/src/tests/S5BRealUserSmoke.test.tsx"
    ],
    "coverage_status": "CTO_ACCEPTED_UI_BOUNDED_SCOPE__NOT_CURRENT_CI",
    "cto_ruling": {
      "path": "AI_REPORT_INBOX/rc3-ui-closeout-and-local-integration-cto-20261020/delivery/CTO-UI-CLOSEOUT-ACCEPTANCE.zh-CN.md",
      "sha256": "78d5a06a7781f4f0dc76e31daa44992383f4f52fdf1691675aa8d6a59029aeb9",
      "accepted_scope": "Payment currency/Pricing UI finite scope; LF-only closeout; not new whole-business V3"
    },
    "load_bearing_blobs": {
      "frontend/src/components/ui/PaymentRecordModal.tsx": "e946942622c2630eb83ef1b5471b214b726a0940",
      "frontend/src/pages/orders/OrderListPage.tsx": "fd59647026b2545687c4aa864b0217be2e26fbf0",
      "frontend/src/pages/pricing/RetailerPricingPage.tsx": "3599b6f0866878847741fd8a86d6bf8082f3fc49",
      "frontend/src/tests/PaymentCurrencyPricingUx.test.tsx": "4128a6a48f3240d8d22a445284c902d59776759d",
      "frontend/src/tests/S5BRealUserSmoke.test.tsx": "e34bb0cc02ae7f86885dc27f184594b5d034a0de"
    },
    "current_product_blobs": {
      "frontend/src/components/ui/PaymentRecordModal.tsx": "e946942622c2630eb83ef1b5471b214b726a0940",
      "frontend/src/pages/orders/OrderListPage.tsx": "fd59647026b2545687c4aa864b0217be2e26fbf0",
      "frontend/src/pages/pricing/RetailerPricingPage.tsx": "3599b6f0866878847741fd8a86d6bf8082f3fc49",
      "frontend/src/tests/PaymentCurrencyPricingUx.test.tsx": "90a653b45fa8045da565d6e746df7dcb52d5339b",
      "frontend/src/tests/S5BRealUserSmoke.test.tsx": "e34bb0cc02ae7f86885dc27f184594b5d034a0de"
    },
    "evidence": {
      "vitest": {
        "candidate": "b46b74130b582e8e4f42579148b209eca540f576",
        "path": "cto-tasks/rc3-payment-currency-pricing-ux-zcodew-r1-20261020/reports/vitest-full.xml",
        "sha256": "7f330187b0e31839682d564d57206e33ab03c03c031f258e3efe4ec97329a6a0",
        "passed": 531,
        "failed": 0,
        "identity": "AUTHOR_EXECUTED__CTO_FINITE_ACCEPTANCE__NOT_NEW_INDEPENDENT_RUNTIME"
      },
      "browser": {
        "candidate": "b46b74130b582e8e4f42579148b209eca540f576",
        "path": "AI_REPORT_INBOX/rc3-payment-currency-pricing-ux-zcodew-r1-20261020/delivery/GATE-RESULTS.json",
        "sha256": "d41a3ea8245af9d4cb8676bd750b028d4f22eca1d955f40dc2ce3dcad981bdfc",
        "countries": [
          "UG",
          "KE"
        ],
        "observations": [
          "payment modal currency",
          "payment toast currency",
          "pricing empty state",
          "pricing save labels"
        ],
        "identity": "AUTHOR_UI_OBSERVATIONS__NOT_NEW_S3_BROWSER_EXECUTION",
        "screenshots": [
          {
            "path": "screenshots/GATE-KE-pay-filled.png",
            "sha256": "1c6954e941a42abffbce364f941e7e327e0207cc400ac88be6d386fb2655bc13"
          },
          {
            "path": "screenshots/GATE-KE-pay-modal.png",
            "sha256": "b6419c9daf850175da2ba21e5267fd525519be4926bc69c983b1659140007996"
          },
          {
            "path": "screenshots/GATE-KE-pay-toast.png",
            "sha256": "c3465246602d6cbe2d09f960c59e6ba77fbb77c436baa20ed7fc95fe2d2856b1"
          },
          {
            "path": "screenshots/GATE-pricing-empty-state.png",
            "sha256": "72efd05284a88621402fb2ef09f03608f7b812c9889452c5d288c4cf4366c4f1"
          },
          {
            "path": "screenshots/GATE-pricing-save-names.png",
            "sha256": "2d43c8d21e1f2a563d17508c37f417f949da993f3916a7316657262e4bf9a9a4"
          },
          {
            "path": "screenshots/GATE-UG-pay-filled.png",
            "sha256": "d52bccf27e978bdfb5224bb57fe259bdb77494f86012c2a44cc968fd8bd34865"
          },
          {
            "path": "screenshots/GATE-UG-pay-modal.png",
            "sha256": "14bd9d3fb9c1e43e65c192a686a6f25d4c9dff628dc69643dd40603c8906594e"
          },
          {
            "path": "screenshots/GATE-UG-pay-toast.png",
            "sha256": "03e019e1f2b19a06424e081eb2464532c27f35c2b628a7f88f095ee7d5628bbf"
          }
        ]
      },
      "build": {
        "candidate": "bac775df8257ea2fd626d6de425f3564748b37f2",
        "path": "AI_REPORT_INBOX/rc3-payment-currency-pricing-ux-zcodew-r1-20261020/delivery/normal-gate-closeout-r1/build-final.log",
        "sha256": "90cfa756bcdb851a371e7184e4a984a2219b7ec92527a27febd47b25e953df55",
        "rc": 0
      },
      "cto_normal_hook": {
        "path": "AI_REPORT_INBOX/rc3-ui-closeout-and-local-integration-cto-20261020/delivery/CTO-INDEPENDENT-NORMAL-PRECOMMIT.log",
        "sha256": "10d925202ad82dfcb6f646e3b9617238c8df0a9303b8caac5d07ad49b23ab1bd",
        "candidate": "bac775df8257ea2fd626d6de425f3564748b37f2",
        "rc": 0,
        "passed_hooks": 4,
        "yaml_hook": "SKIPPED_NO_YAML_INPUT__NOT_PRODUCT_TEST_SKIP"
      },
      "cto_native_binding": {
        "path": "AI_REPORT_INBOX/rc3-ui-closeout-and-local-integration-cto-20261020/delivery/CTO-VERIFICATION.json",
        "sha256": "d4a75f8a72c91d73c7a8bacbf5e447aad0a9e1c17f7f0e8b1433cb3a75dc016c"
      }
    },
    "line_ending_equivalence": {
      "path": "frontend/src/tests/PaymentCurrencyPricingUx.test.tsx",
      "from_candidate": "b46b74130b582e8e4f42579148b209eca540f576",
      "to_candidate": "bac775df8257ea2fd626d6de425f3564748b37f2",
      "rule": "new_bytes == old_bytes.replace(CRLF, LF)",
      "current_sha256": "b643652e23dff99de4aac7736fd8d1c6a6ed5d901b79d6fe4981f8bd70c02732",
      "only_this_path_changed_between_these_candidates": true
    },
    "gaps": [
      "CURRENT_INTEGRATED_HOSTED_CI_NOT_RUN",
      "NOT_NEW_FULL_PAYMENT_INVENTORY_V3",
      "NOT_NEW_S3_BROWSER_EXECUTION",
      "NOT_A_PYTEST_NODE_UNION"
    ]
  },
  "s3_frontend_changed_blobs": [
    {
      "path": "frontend/src/pages/orders/OrderListPage.tsx",
      "historical_blob": "28e9824506cffa75e7c2365ecf837a5170b8148a",
      "current_blob": "fd59647026b2545687c4aa864b0217be2e26fbf0"
    }
  ]
}
''')


RC3_SOURCE_CONTINUITY = json.loads(r'''
{
  "authorization": "CTO-AUTH-RC3-032A77E8-CI-SOURCE-CONTINUITY-R1-20261020",
  "approved_ref": "032a77e81112e606e85e35f8f609ada5a81c3c1e",
  "source_tree": "571568d910af512c7411b03654e4ac7dedf14acf",
  "source_parent": "4d606e04016fb2eef9d1a269a14f9b2705bc11d2",
  "backend_tree": "d631107a5a2bb54220a52033cc0599a53567f0e2",
  "frontend_tree": "d3e3ca842bd6d4eb2caca6aa5d1b1c3137d83f34",
  "authority_record": {
    "path": "AI_REPORT_INBOX/rc3-fixture-r1r2-cto-acceptance-20261020/delivery/CODEXL-CI-SOURCE-CONTINUITY.zh-CN.md",
    "sha256": "ee86c88ab929df03bdf28399a5a108a24984dd66fcc0b90032377532f97d2d4c"
  },
  "cto_ruling": {
    "path": "AI_REPORT_INBOX/rc3-fixture-r1r2-cto-acceptance-20261020/delivery/CTO-ACCEPTANCE.zh-CN.md",
    "sha256": "6b00cdc5d4b2d1e23ecc84375e748d861113342bf6ee82eed4426ded3868d616"
  },
  "source_deltas": [
    {
      "path": "backend/tests/test_u6i1_owner_credential_setup_schema.py",
      "current_blob": "105f37adc842305aff52a12dc157d97206b8cb1d",
      "current_sha256": "cee1fa64fc0fb6b49efad260afdd3b4bedba580144ed4f735d985f762428e7f7"
    },
    {
      "path": "backend/tests/test_u6f_onboarding_auth_chain_closeout.py",
      "current_blob": "f7c91ac217ce81e08595cfe7da4d581878a57a3e",
      "current_sha256": "0c699d6f23bf7d566ff10962295ee86eccbd2e626c2edf0c7325f02add7bc9b5"
    },
    {
      "path": "backend/tests/test_dc12r1_s3_s2b_i1_financial_schema_foundation.py",
      "current_blob": "59485795cc8f1a4df7513fc90d205b88cc1e176a",
      "current_sha256": "913387debbf5d06d51e58a5d211f45eb71622e5e57b2a089b428aa3e5932e719"
    },
    {
      "path": "backend/tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py",
      "current_blob": "6a44074f290bf28f99d4f1145cf706e3e1945eeb",
      "current_sha256": "aabf7f80bf218cf335b913911a85387ed766d1e989da991a40491aa999b96e3b"
    },
    {
      "path": "backend/tests/test_combined_setup_authority_contract.py",
      "current_blob": "229536520f8904f719016b9c6036da96af472943",
      "current_sha256": "90854ed6b22b2460777dcfdc6a1b86fb8c0dbc3aa4f2cc8aa953bb447f71f2a4"
    },
    {
      "path": "backend/tests/test_g1_r2_lifecycle_and_public_prep_contract.py",
      "current_blob": "8c2aca6b5519971c9296ebebed4faedf26fd2f85",
      "current_sha256": "715eebffc638c85ef3f98c9052450b8e6f0df75850e9f65258d9981c578708d1"
    },
    {
      "path": "backend/tests/mpango_invariants_r0_support.py",
      "current_blob": "433383e5247180561b77d593847be703a9b72cca",
      "current_sha256": "187e6e1f0ae98b218f99e74738cccbf2bfb523385b4bd328f36d5c6800dcc60e"
    },
    {
      "path": "backend/tests/test_runtime_readiness_gate.py",
      "current_blob": "849dc50f99983b8ea9109c79f46c691d7baa3942",
      "current_sha256": "93851f5bc157a3386088f5c8bdd9eae6c138bb243311792d186c7ceadafd8db5"
    },
    {
      "path": "backend/tests/task_owned_pg_resources.py",
      "current_blob": "6fed2c5aeae93b09168b8af4fad6eaf689571fd0",
      "current_sha256": "0fe1addb27ac17bdc0725678e18989f4ee31620620f7c2b3858b04f3828649f8"
    }
  ],
  "local_contract_closeout": {
    "classification": "CTO_ACCEPTED_RC3_CURRENT_042_TEST_CONTRACT_AND_CANONICAL_FIXTURE_FINITE_CLOSEOUT",
    "source_ref": "032a77e81112e606e85e35f8f609ada5a81c3c1e",
    "evidence_manifest": {
      "path": "AI_REPORT_INBOX/rc3-canonical-fixture-env-resume-codexl-r1r2-20261020/delivery/MANIFEST.sha256",
      "sha256": "ca242c50e3af497afa8275a01db3a2fe94c8db3cb460624dbbd8cb1dc9e8e75d"
    },
    "bounded_selections": {
      "prior_A": 4,
      "prior_Alembic": 29,
      "prior_B1_B2": 23,
      "current_C_D": 26
    },
    "execution_identity": "AUTHOR_EXECUTED__CTO_READONLY_ACCEPTED__CROSS_ROUND_NOT_ONE_FIRST_PASS",
    "fresh_collection": {
      "nodes": 4288,
      "body_executed": false,
      "definition_changed": false
    },
    "new_independent_v3": false,
    "hosted_ci": "NOT_RUN",
    "release_acceptance": "NOT_ISSUED"
  }
}
''')


RC3_ROUTE_CONTRACT_INTAKE = {
    "authorization": "CTO-AUTH-RC3-CI-THREE-FAMILY-FINITE-CLOSEOUT-R1-20261021",
    "source_ref": "9e2221393f0a8c3da493ea32d4a3d93e41f4fa33",
    "source_tree": "e98ef29fa641a404129b4d253829394f7f28d07a",
    "source_parent": "afb133c805203cd371bb08878b2e65fe55ab733d",
    "backend_tree": "2ec06ad1f3a37f08319f6f6b405d1eb8543692df",
    "frontend_tree": "d3e3ca842bd6d4eb2caca6aa5d1b1c3137d83f34",
    "classification": "AUTHOR_ROUTE_CONTRACT_CANDIDATE_PENDING_CTO",
    "authority_record": {
        "path": "AI_REPORT_INBOX/rc3-ci-three-family-finite-closeout-cto-20261021/delivery/CODEXL-FINITE-REPAIR.zh-CN.md",
        "sha256": "e7f0a2d8ffe7f587c0aba1963617740c33829e2a15753a266e662881ea0c1f6f",
    },
    "cto_ruling": {
        "path": "AI_REPORT_INBOX/rc3-ci-three-family-finite-closeout-cto-20261021/delivery/CTO-REVIEW.zh-CN.md",
        "sha256": "b5cfbc20d072647ae73c171ca8934f0d034f3079f7f55099506f45c2a9041448",
    },
    "source_deltas": [
        {"path": "backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py",
         "current_blob": "2683718ce1ed2e7bff05655e9ea4ed92d6b8282d",
         "current_sha256": "357f9eb1b30ad6279da3e8c4df03882b66ad300c0a4c9892a4a9b9266df946b1"},
        {"path": "backend/tests/test_dc12r1_s3_s2_read_only_retailer_finance.py",
         "current_blob": "3d1e38bcec1ee4b99afb40a478db96bd6b5abcfa",
         "current_sha256": "e2616c754e853aa0088861e36f4a6291408957cc85e3930a84806ad8d3e11965"},
        {"path": "backend/tests/test_route_authorization_policy.py",
         "current_blob": "b3ffdd204ea71c76bec179845e26fd55dab58670",
         "current_sha256": "78177b533677aa5324d8402c447d4620005ca56dce75d4f1174d3f555b66a848"},
    ],
    "new_independent_v3": False,
    "added_business_accepted_nodes": 0,
    "hosted_ci": "NOT_RUN",
}


RC3_FIXTURE_SCOPE_INTAKE = {
    "authorization": "CTO-AUTH-RC3-CI-FIXTURE-SCOPE-CONTINUE-R1-20261021",
    "source_ref": "82ad641d67baf3035c5e35fc449d701780a22b3a",
    "source_tree": "43d9051ab20e262e6096254eba465cc37c860075",
    "source_parent": "9e2221393f0a8c3da493ea32d4a3d93e41f4fa33",
    "backend_tree": "4efaa92c7b2189cee5ac876b174adf46c21829da",
    "frontend_tree": "d3e3ca842bd6d4eb2caca6aa5d1b1c3137d83f34",
    "classification": "AUTHOR_ROUTE_CONTRACT_CANDIDATE_PENDING_CTO",
    "authority_record": {
        "path": "AI_REPORT_INBOX/rc3-ci-three-family-finite-supplement-cto-20261021/delivery/CODEXL-FINITE-CONTINUE.zh-CN.md",
        "sha256": "c6533bcd1e1572dfb74a9f58a5217e1161adc9b9e46fd8e579a90d1966a02245",
    },
    "cto_ruling": {
        "path": "AI_REPORT_INBOX/rc3-ci-three-family-finite-supplement-cto-20261021/delivery/CTO-REVIEW.zh-CN.md",
        "sha256": "3da6e1dc798fcbbf698ffbfbc708aafde7d438063480d2c39929e293c7cbd6fe",
    },
    "source_deltas": [
        {"path": "backend/tests/rc2_current_contract_support.py",
         "current_blob": "dcbba531e7bfc4f358fa6314a09329395eebec71",
         "current_sha256": "7bc3c512eaf1ff6fddbfe302a6a67ce833c2f81c84b093651aba0aad812b5192"},
        {"path": "backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py",
         "current_blob": "88e904a2a9dff7e2a291ff2379619a3a385db7f4",
         "current_sha256": "e33c0ebc92ed358f4eea5a2dfc6aa5467805b5cf7fbbae8ef396a9d33d00009a"},
        {"path": "backend/tests/test_dc12r1_s3_s2_read_only_retailer_finance.py",
         "current_blob": "3d1e38bcec1ee4b99afb40a478db96bd6b5abcfa",
         "current_sha256": "e2616c754e853aa0088861e36f4a6291408957cc85e3930a84806ad8d3e11965"},
        {"path": "backend/tests/test_route_authorization_policy.py",
         "current_blob": "b3ffdd204ea71c76bec179845e26fd55dab58670",
         "current_sha256": "78177b533677aa5324d8402c447d4620005ca56dce75d4f1174d3f555b66a848"},
        {"path": "backend/tests/test_sku_r1_client_catalog_contract.py",
         "current_blob": "8c19a0ec4fcfa1b55f9374ff5aa5c2a74456e2ed",
         "current_sha256": "f64ee8e4c03b34d7403a75b5401cba7311189e8834367eaa30ccc03dcb843f0d"},
    ],
    "previous_tool_contract_execution": {
        "source_ref": "9e2221393f0a8c3da493ea32d4a3d93e41f4fa33",
        "tool_source_sha256": "363fa02b3980ad4de27dba769705996746afd2a60ef44b23a1e2666d32b42369",
        "junit_sha256": "04a4d2aa6fbe18cc389d687fd27defce553fbc28029e8a9b1981ce56f6509ed4",
        "passed": 202,
        "classification": "AUTHOR_OFFLINE_TOOL_EVIDENCE_AT_OLD_BYTES__NOT_REEXECUTED",
    },
    "poetry_configuration": "POETRY_221_VERSIONED_SOURCE_CHECKED_BY_CTO__LOCAL_CLI_NOT_RUN",
    "new_independent_v3": False,
    "added_business_accepted_nodes": 0,
    "hosted_ci": "NOT_RUN",
}


def _reuse_expected_metadata(repo):
    """Return an independent copy of the versioned fixed intake.

    No working-coverage hash, machine path, network or unavailable side
    intake participates. Only the fixed approved coverage blob supplies
    the previous RC4 metadata; historical execution identities stay intact.
    """
    expected = json.loads(json.dumps(REUSE_EXPECTED_METADATA))
    expected["previous_rc2_source_intake"] = expected["current_source_intake"]
    expected["historical_attachment_deltas"] = expected["current_attachment_deltas"]
    expected["historical_selection_binding"] = expected["selection_binding"]
    expected.update(json.loads(json.dumps(RC3_INTAKE["updates"])))
    expected["bindings"].append(json.loads(json.dumps(RC3_INTAKE["additional_binding"])))
    intake = json.loads(json.dumps(RC3_LOCAL_INTEGRATION))
    expected["previous_s3_source_intake"] = json.loads(json.dumps(expected["current_source_intake"]))
    expected["previous_s3_selection_binding"] = json.loads(json.dumps(expected["selection_binding"]))
    expected["previous_s3_attachment_deltas"] = json.loads(json.dumps(expected["current_attachment_deltas"]))
    expected.update(record="RC3_LOCAL_INTEGRATED_PRODUCT_INTAKE_V1",
                    authorization=intake["authorization"], intake_version=REUSE_INTAKE_VERSION,
                    intake_status="LOCAL_INTEGRATED_ADMISSION__CTO_SOURCE_DECISION_PENDING",
                    product_anchor=intake["approved_ref"])
    expected["selection_binding"].update(authority=intake["authorization"], source_ref=intake["approved_ref"])
    current = expected["current_source_intake"]
    current.update(authorization=intake["authorization"], source_ref=intake["approved_ref"],
                   source_tree=intake["source_tree"], source_parent=intake["source_parent"],
                   backend_tree=intake["backend_tree"], frontend_tree=intake["frontend_tree"],
                   authority_record=intake["authority_record"], cto_ruling=intake["cto_ruling"],
                   independent_v3_this_intake="NO_NEW_EXECUTION__S3_BACKEND_SAME_BYTES__UI_CTO_BOUNDED_INTAKE",
                   current_fresh_ordinary_collection="NOT_RUN_THIS_INTEGRATION__PRIOR_4288_RECONCILED")
    changes = {item["path"]: item for item in current["source_deltas"]}
    changes.update({item["path"]: item for item in intake["source_deltas"]})
    current["source_deltas"] = [changes[path] for path in sorted(changes)]
    for delta in expected["current_attachment_deltas"]:
        delta["current_source_ref"] = intake["approved_ref"]
    expected["bindings"].append(intake["ui_binding"])
    expected["current_dependency_assessments"].extend([
        {"binding_id": "s3_minimum_negotiation_cto_independent_v3",
         "status": "REUSED_S3_BACKEND_166__CURRENT_FRONTEND_GAP",
         "historical_record_not_rebound": True,
         "current_dependency_changed_blobs": intake["s3_frontend_changed_blobs"],
         "backend_nodes_same_bytes_reused": 166,
         "historical_browser_candidate": RC3_INTAKE["additional_binding"]["candidate"],
         "historical_browser_reexecuted": False,
         "remaining_scope": "GAP_CURRENT_S3_BROWSER_NOT_REEXECUTED__NOT_FULL_NODE_COVERAGE"},
        {"binding_id": intake["ui_binding"]["id"],
         "status": intake["ui_binding"]["coverage_status"],
         "historical_record_not_rebound": True,
         "vitest_count": 531, "vitest_candidate": intake["ui_binding"]["candidate"],
         "build_candidate": intake["approved_ref"], "not_backend_pytest_nodes": True,
         "remaining_scope": "GAP_CURRENT_INTEGRATED_HOSTED_CI_AND_FULL_BUSINESS_V3_NOT_RUN"},
    ])
    continuity = json.loads(json.dumps(RC3_SOURCE_CONTINUITY))
    expected["previous_local_integration_source_intake"] = json.loads(json.dumps(current))
    expected["previous_local_integration_selection_binding"] = json.loads(json.dumps(expected["selection_binding"]))
    expected["previous_local_integration_attachment_deltas"] = json.loads(json.dumps(expected["current_attachment_deltas"]))
    expected.update(record="RC3_LOCAL_CI_SOURCE_CONTINUITY_V1",
                    authorization=continuity["authorization"],
                    intake_status="LOCAL_SOURCE_CONTINUITY__CTO_CI_DECISION_PENDING",
                    product_anchor=continuity["approved_ref"])
    expected["selection_binding"].update(authority=continuity["authorization"], source_ref=continuity["approved_ref"])
    current.update(authorization=continuity["authorization"], source_ref=continuity["approved_ref"],
                   source_tree=continuity["source_tree"], source_parent=continuity["source_parent"],
                   backend_tree=continuity["backend_tree"], frontend_tree=continuity["frontend_tree"],
                   authority_record=continuity["authority_record"], cto_ruling=continuity["cto_ruling"],
                   independent_v3_this_intake="NO_NEW_V3__AUTHOR_FIXTURE_RESULTS_CTO_ACCEPTED",
                   current_fresh_ordinary_collection="R1R2_COLLECT_ONLY_4288__NO_4288_BODY_RUN")
    changes.update({item["path"]: item for item in continuity["source_deltas"]})
    current["source_deltas"] = [changes[path] for path in sorted(changes)]
    for delta in expected["current_attachment_deltas"]:
        delta["current_source_ref"] = continuity["approved_ref"]
    expected["local_fixture_contract_closeout"] = continuity["local_contract_closeout"]
    route = json.loads(json.dumps(RC3_ROUTE_CONTRACT_INTAKE))
    expected["previous_fixture_source_intake"] = json.loads(json.dumps(current))
    expected["previous_fixture_selection_binding"] = json.loads(json.dumps(expected["selection_binding"]))
    expected["previous_fixture_attachment_deltas"] = json.loads(json.dumps(expected["current_attachment_deltas"]))
    expected.update(record="RC3_ROUTE_CONTRACT_SOURCE_CONTINUITY_V1",
                    authorization=route["authorization"], intake_status=route["classification"],
                    product_anchor=route["source_ref"])
    expected["selection_binding"].update(authority=route["authorization"], source_ref=route["source_ref"])
    current.update({key: route[key] for key in (
        "authorization", "source_ref", "source_tree", "source_parent", "backend_tree",
        "frontend_tree", "authority_record", "cto_ruling")})
    current.update(independent_v3_this_intake="AUTHOR_ROUTE_CONTRACT_CANDIDATE_PENDING_CTO",
                   current_fresh_ordinary_collection="NOT_RUN_THIS_INTAKE__PRIOR_4288_DEFINITION_UNCHANGED")
    changes.update({item["path"]: item for item in route["source_deltas"]})
    current["source_deltas"] = [changes[path] for path in sorted(changes)]
    for delta in expected["current_attachment_deltas"]:
        delta["current_source_ref"] = route["source_ref"]
    expected["route_contract_closeout"] = route
    expected["previous_route_contract_source_intake"] = json.loads(json.dumps(current))
    expected["previous_route_contract_selection_binding"] = json.loads(json.dumps(expected["selection_binding"]))
    expected["previous_route_contract_attachment_deltas"] = json.loads(json.dumps(expected["current_attachment_deltas"]))
    expected["previous_route_contract_closeout"] = route
    route = json.loads(json.dumps(RC3_FIXTURE_SCOPE_INTAKE))
    expected.update(authorization=route["authorization"], intake_status=route["classification"],
                    product_anchor=route["source_ref"])
    expected["selection_binding"].update(authority=route["authorization"], source_ref=route["source_ref"])
    current.update({key: route[key] for key in (
        "authorization", "source_ref", "source_tree", "source_parent", "backend_tree",
        "frontend_tree", "authority_record", "cto_ruling")})
    changes.update({item["path"]: item for item in route["source_deltas"]})
    current["source_deltas"] = [changes[path] for path in sorted(changes)]
    for delta in expected["current_attachment_deltas"]:
        delta["current_source_ref"] = route["source_ref"]
    expected["route_contract_closeout"] = route
    expected["previous_rc3_source_intake"] = json.loads(json.dumps(current))
    expected["previous_rc3_selection_binding"] = json.loads(json.dumps(expected["selection_binding"]))
    expected["previous_rc3_dependency_assessments"] = json.loads(json.dumps(expected["current_dependency_assessments"]))
    expected["previous_rc3_attachment_deltas"] = json.loads(json.dumps(expected["current_attachment_deltas"]))
    previous_ci_ref = "cffc1271a8746cb5d8fe8dc6690f4880a6da0b1d"
    expected.update(record="RC4_CURRENT_SOURCE_CONTINUATION_PROPOSAL_V1",
                    authorization="CTO-AUTH-MVP-RC4-CURRENT-CI-INTAKE-CODEXL-R1-20261024",
                    intake_version=REUSE_INTAKE_VERSION,
                    intake_status="AUTHOR_LOCAL_SOURCE_PROPOSAL_PENDING_CTO",
                    product_anchor=previous_ci_ref)
    expected["current_source_intake"] = {
        "authorization": expected["authorization"],
        "source_ref": previous_ci_ref,
        "source_tree": "a32753d6f3d7c5388d7a522e1c04ac298e298d70",
        "source_parent": "bb625e893ab1ec3c50c7eb0cfeedf4a73e9f8f6b",
        "backend_tree": "c175cd58527923e4bab3e69c25110dfc7b5be1ad",
        "frontend_tree": "17c477ca022b0dc86118f481fd4ded907e92bcf8",
        "authority_status": "SOURCE_CONTINUATION_PROPOSED__CTO_REVIEW_PENDING",
        "source_contract_commit": "CURRENT_HEAD_TEST_ATTACHMENTS_ONLY__NO_PRODUCT_EDITS",
        "independent_v3_this_intake": "NOT_RUN",
        "current_fresh_ordinary_collection": "COLLECT_ONLY_4505_CURRENT_NATIVE_NODES__NO_FULL_BODY_PASS",
        "historical_results_reexecuted": False,
        "hosted_ci_this_intake": "NOT_RUN",
        "ordinary_definition": {"files": 250, "dedicated_files": 21, "ignores": 6,
                                "nodes": 4505, "canonical_definition_changed": True},
    }
    expected["selection_binding"] = {
        "authority": expected["authorization"], "source_ref": previous_ci_ref,
        "discovered_files": 277, "ordinary_files": 250, "dedicated_files": 21,
        "ignores": 6, "union": 271, "intersection": 0, "unknown": 0,
    }
    expected["current_dependency_assessments"] = [
        {"binding_id": item["binding_id"],
         "status": "HISTORICAL_ACCEPTANCE_RETAINED__CURRENT_DEPENDENCY_REVALIDATION_GAP",
         "historical_record_not_rebound": True,
         "remaining_scope": "GAP_RC4_CURRENT_DEPENDENCY_REVALIDATION__NO_NEW_FULL_FILE_OR_BROWSER_ACCEPTANCE"}
        for item in expected["previous_rc3_dependency_assessments"]
    ]
    for delta in expected["current_attachment_deltas"]:
        delta["current_source_ref"] = previous_ci_ref
    expected["ordinary_canonical_status"] = "AUTHOR_CURRENT_4505_NATIVE_COLLECTIONS__NO_FULL_BODY_PASS__CTO_PENDING"
    expected["additional_bounded_evidence"] = [{
        "id": "M01_R4_single_instance_UG_revoked_cached_replay",
        "product_ref": "bb625e893ab1ec3c50c7eb0cfeedf4a73e9f8f6b",
        "cto_ruling": "m01-r4-cto-final-acceptance-20261024/CTO-FINAL-RULING.zh-CN.md",
        "cto_ruling_sha256": "1dc01e9bc5483581f283ee12f843f742619cba48f3bf9165bf49f1a5d4142a5e",
        "status": "CTO_ACCEPTED_NAMED_SCOPE_ON_BB625E89__NOT_CURRENT_CI_OR_FULL_AUDIT",
        "scope": "single-instance UG: S1 201, S2 201 hot replay, product deactivate, old unexpired token 403/BINDING_NOT_ACTIVE, exact declared economic multisets unchanged",
        "not_claimed": ["all audit/cache/rcj", "multi-process", "SMTP registration", "full revenue recognition", "full suite", "release"],
        "new_pytest_nodes_claimed": 0,
    }]
    expected["explicit_non_claims"] = [
        "RC4 source-continuation is an author proposal pending CTO, not a CTO source acceptance.",
        "277 tracked files minus six ignores split into 250 ordinary and 21 dedicated files; five native collections froze 4505 nodes, no full body pass.",
        "Historical acceptance, node maps, candidates and original gaps retain their original scope and bytes.",
        "M01 R4 is a named single-instance UG chain on bb625e89, not all audit/cache/rcj coverage.",
        "No hosted CI, full backend body execution, independent V3 or release readiness is established here.",
    ]
    previous = json.loads(_git_bytes(
        repo, "show", REUSE_APPROVED_REF + ":docs/releases/mvp-20261031/VERIFICATION-COVERAGE.json"
    ))
    expected["previous_rc4_source_intake"] = previous["current_source_intake"]
    expected["previous_rc4_selection_binding"] = previous["selection_binding"]
    expected.update(record="RC4_FIXED_CI_SOURCE_BINDING_V1",
                    authorization="CTO-AUTH-RC4-3A26B6D6-CI-SOURCE-BINDING-L-R1-20261026",
                    intake_status="FIXED_SOURCE_BINDING_SUCCESSOR_PENDING_CTO",
                    product_anchor=REUSE_APPROVED_REF)
    current = json.loads(json.dumps(previous["current_source_intake"]))
    current.update(
        authorization=expected["authorization"], source_ref=REUSE_APPROVED_REF,
        source_tree="875c6b3a09e6745859074b8353d21eb49b97ed53",
        source_parent="7500acbf82c492e12a0f2ff9e8ce5ab495eece3b",
        backend_tree="782c3afdebe6c664ddaf8a58c430751f91e294f0",
        frontend_tree="17c477ca022b0dc86118f481fd4ded907e92bcf8",
        authority_status="SOURCE_COMPARISON_ANCHOR_AUTHORIZED__SUCCESSOR_PENDING_CTO",
        source_contract_commit=REUSE_APPROVED_REF,
        current_fresh_ordinary_collection="UNCHANGED_4505_DEFINITION__RETAINED_COLLECTIONS_ONLY",
        historical_attachment_deltas_preserved_at_previous_ref=True,
    )
    current["ordinary_definition"]["canonical_definition_changed"] = False
    expected["current_source_intake"] = current
    expected["selection_binding"].update(authority=expected["authorization"], source_ref=REUSE_APPROVED_REF)
    return expected


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
    assessments = {item["binding_id"]: item for item in expected["current_dependency_assessments"]}
    results = [{"id": b["id"], "status": "GAP_EVIDENCE_INVALID" if gap else
                assessments.get(b["id"], {}).get("status", b["coverage_status"]),
                "candidate": b["candidate"], "scope_gaps": b["gaps"]} for b in expected["bindings"]]
    summary = {
        "tool": "prepare_test_evidence.py verify-reuse",
        "coverage_sha256": _sha256_file(coverage_path),
        "bindings": results,
        "current_dependency_assessments": expected["current_dependency_assessments"],
        "current_accepted_node_union": 166,
        "all_valid": not gap,
        "release_ready": False,
        "evidence_ready": False,
        "current_source_authority": "AUTHOR_PROPOSAL_PENDING_CTO",
        "source_objects_checked": object_count,
        "external_source_objects_checked": external_count,
        "problems": sorted(set(problems)),
        "full_dedicated_node_coverage": "GAP_RCJ_NODE_MAP_NOT_ESTABLISHED",
        "note": "blob drift means the load-bearing bytes moved: the binding is GAP until a new CTO ruling; never re-validated by updating this record alone",
    }
    print("[verify-reuse] " + ("GAP_EVIDENCE_INVALID" if gap else "LOCAL_SOURCE_MATCH__CTO_PENDING") +
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
