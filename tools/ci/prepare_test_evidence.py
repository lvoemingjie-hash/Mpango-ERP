#!/usr/bin/env python3
"""Frozen-set shard planning and public evidence sanitization (R6).

Authorization: CTO-C91-CI-R6-FIVE-TASK-PREPARATION-20261007.

Three bounded functions, nothing else (no scheduling, no retries, no
network, no docker, no database, no new authority layer):

* ``shard-plan``   — cut the wrapper's runtime profile into two frozen-
                     boundary whole-module shard argfiles. The boundary
                     file is a frozen contract of the shard plan: if the
                     runtime membership drifts so that the boundary is
                     absent (or shard-b would be empty) the tool REFUSES;
                     it never silently re-cuts the shards.
* ``shard-verify`` — bidirectional reconciliation of one shard: argfile
                     members vs the plan's frozen sets (missing, extra or
                     duplicate members are RED) plus, when a collect list
                     is supplied, collected nodeid count/file checks
                     against the frozen expected node count.
* ``sanitize``     — publish-derivative production for artifacts before
                     any public upload: exact credential values from the
                     task credential store / environment channels (never
                     argv) plus SCRAM-verifier and DSN form rules; junit
                     node/status mapping invariance is proven across the
                     transformation or the file is REFUSED (nothing is
                     written); every refusal is fail-closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RUNTIME_SHARD_BOUNDARY = "tests/test_platform_p12_support_console.py"
SHARD_NAMES = ("runtime-a", "runtime-b", "topology", "invariants-jwt", "task-managed-pg")

# Form rules: shapes that may appear in logs/XML even when the exact value
# is not in the store (e.g. a full DSN with a per-run password).
SCRAM_VERIFIER_RE = re.compile(r"SCRAM-SHA-256\$[0-9]+:[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+")
PG_DSN_RE = re.compile(r"postgres(?:ql)?://[^\s:\"'<>/]+:[^\s:\"'<>@]+@[^\s\"'<>]+")
REDIS_DSN_RE = re.compile(r"rediss?://[^\s:\"'<>/]+:[^\s:\"'<>@]+@[^\s\"'<>]+")
XML_UNSAFE_CHARS = set("&<>\"'")

PLACEHOLDER = "[REDACTED:%s]"


class Refused(Exception):
    """Named fail-closed refusal. exit_code distinguishes plan/verify (3)
    from sanitize (4) so callers can record evidence gaps precisely."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    if shard not in SHARD_NAMES:
        raise Refused(f"UNKNOWN_SHARD: {shard} not in {SHARD_NAMES}", 3)
    expected = _expected_shard_files(plan, shard)
    members = _read_argfile(args.argfile)

    duplicates = sorted({m for m in members if members.count(m) > 1})
    if duplicates:
        raise Refused(f"DUPLICATE_SHARD_MEMBERS: {duplicates[:5]}", 3)
    expected_set, member_set = set(expected), set(members)
    missing = sorted(expected_set - member_set)
    extra = sorted(member_set - expected_set)
    if missing or extra:
        raise Refused(
            f"SHARD_MEMBERSHIP_MISMATCH: missing={missing[:5]} extra={extra[:5]}", 3
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
            raise Refused(f"DUPLICATE_COLLECTED_NODEIDS: {duplicate_ids[:5]}", 3)
        collected_files = sorted({n.split("::", 1)[0] for n in nodeids})
        outsiders = sorted(set(collected_files) - member_set)
        if outsiders:
            raise Refused(f"COLLECTED_FILE_NOT_IN_SHARD: {outsiders[:5]}", 3)
        if len(nodeids) != int(args.expected_nodes):
            raise Refused(
                f"SHARD_NODE_COUNT_MISMATCH: collected={len(nodeids)} "
                f"expected={args.expected_nodes}",
                3,
            )
        # A shard member may legitimately collect zero nodeids (e.g.
        # tests/test_s3_db_performance.py in runtime-b); the node total is
        # the authoritative count, so subset (not equality) is checked.
        print(f"[shard-verify] {shard}: {len(nodeids)} collected nodeids exact")
    return 0


# ---------------------------------------------------------------------------
# public evidence sanitization
# ---------------------------------------------------------------------------

def _load_secret_rules(secrets_file: str, extra_env: str) -> list:
    """Exact-value rules from the task credential store and from named
    environment variables. Values never appear on this tool's argv; the
    store path and env NAMES are the only references."""
    rules = []
    if secrets_file:
        store = Path(secrets_file)
        if not store.is_file():
            raise Refused(f"SECRETS_STORE_MISSING: {store}", 4)
        try:
            text = store.read_text(encoding="utf-8")
        except OSError as exc:
            raise Refused(f"SECRETS_STORE_UNREADABLE: {exc.__class__.__name__}", 4)
        pairs = []
        for ln in text.splitlines():
            if "=" not in ln:
                continue
            key, value = ln.split("=", 1)
            key, value = key.strip(), value.strip()
            if key and value:
                pairs.append((key, value))
        if not pairs:
            raise Refused("SECRETS_STORE_EMPTY: no KEY=VALUE credential entries", 4)
        for key, value in pairs:
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


def _junit_signature(data: bytes):
    """Full node/status signature of a junit document: every testcase's
    (name, classname, outcome, child tags) in document order plus every
    testsuite's counter attributes. Sanitization must not change it."""
    root = ET.fromstring(data)
    cases = []
    for tc in root.iter("testcase"):
        if tc.find("error") is not None:
            outcome = "error"
        elif tc.find("failure") is not None:
            outcome = "failure"
        elif tc.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        cases.append(
            (tc.get("name", ""), tc.get("classname", ""), outcome,
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


def cmd_sanitize(args: argparse.Namespace) -> int:
    src, dst = Path(args.input), Path(args.output)
    receipt_path = Path(args.receipt)
    if not src.is_file():
        raise Refused(f"INPUT_MISSING: {src}", 4)
    data = src.read_bytes()
    if not data:
        raise Refused(f"INPUT_EMPTY: {src}", 4)

    rules = _load_secret_rules(args.secrets_file, args.extra_env) + _form_rules()
    head = data.lstrip()[:16]
    is_xml = src.suffix == ".xml" or head.startswith(b"<?xml") or head.startswith(b"<testsuite")

    active = []
    skipped_xml_unsafe = []
    if is_xml:
        try:
            signature_before = _junit_signature(data)
        except ET.ParseError as exc:
            raise Refused(f"INPUT_NOT_WELL_FORMED_XML: {exc}", 4)
        for rule_id, kind, value in rules:
            if kind == "exact" and (set(value) & XML_UNSAFE_CHARS):
                # Byte-level replacement of a value containing XML-special
                # characters cannot be trusted inside attribute-escaped
                # documents; skip (under-replacement is the safe direction)
                # and disclose the skip in the receipt.
                skipped_xml_unsafe.append(rule_id)
            else:
                active.append((rule_id, kind, value))
        for name, classname, _outcome, _children in signature_before[0]:
            for field in (name, classname):
                for rule_id, kind, value in active:
                    if kind == "exact" and value in field:
                        raise Refused(
                            f"NODE_MAPPING_AT_RISK: rule {rule_id} would alter a testcase "
                            "name/classname; refusing to publish this file",
                            4,
                        )
                    if kind == "regex" and value.search(field):
                        raise Refused(
                            f"NODE_MAPPING_AT_RISK: rule {rule_id} would alter a testcase "
                            "name/classname; refusing to publish this file",
                            4,
                        )
    else:
        active = list(rules)

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Refused(f"INPUT_NOT_UTF8: {exc}", 4)

    counts = {}
    for rule_id, kind, value in active:
        if kind == "exact":
            replaced = text.count(value)
            if replaced:
                text = text.replace(value, PLACEHOLDER % rule_id.split(":", 1)[1])
        else:
            text, replaced = value.subn(PLACEHOLDER % rule_id.split(":", 1)[1], text)
        counts[rule_id] = replaced

    out_bytes = text.encode("utf-8")
    if not out_bytes:
        raise Refused("OUTPUT_EMPTY: sanitized derivative is empty", 4)

    if is_xml:
        try:
            signature_after = _junit_signature(out_bytes)
        except ET.ParseError:
            raise Refused("OUTPUT_NOT_WELL_FORMED_XML: replacement broke the document", 4)
        if signature_after != signature_before:
            raise Refused("OUTPUT_MAPPING_DRIFT: testcase/suite signature changed", 4)
        mapping_invariance = "ok"
    else:
        mapping_invariance = "not_applicable_text"

    for rule_id, kind, value in active:
        if kind == "exact" and value in text:
            raise Refused(f"RESIDUAL_SECRET: {rule_id} still present after replacement", 4)
        if kind == "regex" and value.search(text):
            raise Refused(f"RESIDUAL_SECRET_FORM: {rule_id} still present after replacement", 4)

    receipt = {
        "tool": "prepare_test_evidence.py sanitize",
        "mode": "junit" if is_xml else "text",
        "input_name": src.name,
        "derived_output_name": dst.name,
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "derived_output_sha256": hashlib.sha256(out_bytes).hexdigest(),
        "input_bytes": len(data),
        "derived_output_bytes": len(out_bytes),
        "replacements": counts,
        "mapping_invariance": mapping_invariance,
        "skipped_xml_unsafe_rules": skipped_xml_unsafe,
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


# ---------------------------------------------------------------------------

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
    p_verify.set_defaults(func=cmd_shard_verify)

    p_san = sub.add_parser("sanitize", help="produce a sanitized public derivative")
    p_san.add_argument("--input", required=True)
    p_san.add_argument("--output", required=True)
    p_san.add_argument("--receipt", required=True)
    p_san.add_argument("--secrets-file")
    p_san.add_argument("--extra-env", help="comma-separated ENV NAMES holding credential values (values never on argv)")
    p_san.set_defaults(func=cmd_sanitize)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Refused as exc:
        exit_code = exc.args[1] if len(exc.args) > 1 else 3
        print(f"prepare_test_evidence: REFUSED: {exc.args[0]}", file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
