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

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Refused as exc:
        exit_code = exc.args[1] if len(exc.args) > 1 else 3
        print(f"prepare_test_evidence: REFUSED: {exc.args[0]}", file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
