#!/usr/bin/env python3
"""HE2-R1 machine-enforced harness governance validator for Mpango ERP.

Implements DC-12R1-MVP-L1-HE2-R1 (bypass closure) on top of the HE2
validator and the HE1 standard
(docs/ai/HARNESS_ENGINEERING_GOVERNANCE_STANDARD.md):

  * validates inventory, coverage-debt, critical-interaction, waiver,
    protocol-delta, and governed-paths documents against their JSON
    schemas using a stdlib-only fail-closed subset checker (unknown
    schema keywords and unresolvable $refs are RED);
  * enforces governance self-protection: a hardcoded protected-path set
    and minimum product prefixes that governed-paths.json can neither
    remove nor waive;
  * enforces SEMANTIC inventory sync: every changed governed path must be
    covered by a record that actually changed (node anchor, interaction
    source/affected path, debt affected path, or a new protocol delta) —
    touching notes, README, or unrelated JSON no longer satisfies the gate;
  * waivers are fail-closed: scoped paths only (no wildcards, no repo
    root, no implicit global), owner/reason/risk/approval/dates required,
    union coverage per changed path, expired = RED, protected paths never
    waivable;
  * PASS evidence must bind to a real, reachable git commit (plus
    evidence_paths, and blob-byte SHA-256 verification for 64-hex digests);
  * protocol deltas are anti-replay: base_sha bound to the comparison
    base, kind-precise authorization, historical deltas cannot be reused,
    unauthorized status transitions are violations;
  * source anchors must exist with in-range line numbers;
  * separates STRUCTURAL_GATE (PASS/FAIL) from RELEASE_GATE
    (PASS/BLOCKED): --mode structural (default) and --mode release.

Python 3.11+, standard library only. Exit codes: 0 = GREEN,
1 = structural violations, 3 = release blocked (release mode),
2 = usage/environment error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys

VALIDATOR_VERSION = "2.0.0"

GOV_DIR = "harness-governance"
CONFIG_RELPATH = f"{GOV_DIR}/governed-paths.json"
INVENTORY_RELPATH = f"{GOV_DIR}/inventory/inventory.json"
DEBT_RELPATH = f"{GOV_DIR}/inventory/coverage-debt.json"
REGISTRY_RELPATH = f"{GOV_DIR}/inventory/critical-interactions.json"
WAIVERS_RELPATH = f"{GOV_DIR}/inventory/waivers.json"
DELTAS_RELPATH = f"{GOV_DIR}/inventory/protocol-deltas.json"
SCHEMA_DIR_RELPATH = f"{GOV_DIR}/schemas"

CONFIG_SCHEMA = "governed-paths.schema.json"
INVENTORY_SCHEMA = "inventory.schema.json"
DEBT_SCHEMA = "coverage-debt.schema.json"
REGISTRY_SCHEMA = "critical-interactions.schema.json"
WAIVERS_SCHEMA = "waivers.schema.json"
DELTAS_SCHEMA = "protocol-deltas.schema.json"

STATUSES = ("PASS", "FAIL", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE")
RISKS = ("P0", "P1", "P2", "P3")
ORACLE_FIELDS = (
    "ui_oracle",
    "navigation_oracle",
    "network_oracle",
    "session_oracle",
    "persistence_security_oracle",
)
ORACLE_SENTINEL = "NOT_APPLICABLE"
_FAKE_SENTINELS = {"N/A", "NA", "NOT APPLICABLE", "NOT_APPLICABLE"}
MUTATION_SENTINELS = {"", "NOT_APPLICABLE", "N/A", "NA", "TBD"}
SHA_RE = re.compile(r"^([0-9a-f]{40}|[0-9a-f]{64})$")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WILDCARD_RE = re.compile(r"[\*\?\[]")

# Phase 2 self-protection: these paths are governed and non-waivable no
# matter what governed-paths.json says. Only a kind=governance protocol
# delta (owner, reason, approval_ref, matching base_sha) can authorize
# changes to them.
PROTECTED_PATHS = (
    ".github/workflows/harness-governance-gate.yml",
    ".secrets.baseline",
    f"{GOV_DIR}/governed-paths.json",
    f"{GOV_DIR}/validator/",
    f"{GOV_DIR}/schemas/",
    f"{GOV_DIR}/tests/",
    # HE2-ET1: execution-traps registry, authority profiles, and the
    # fail-stop authority runner are governance-protected; changes need a
    # kind=governance protocol delta and can never be waived.
    f"{GOV_DIR}/inventory/execution-traps.json",
    f"{GOV_DIR}/schemas/execution-traps.schema.json",
    f"{GOV_DIR}/inventory/authority-profiles.json",
    f"{GOV_DIR}/validator/authority_runner.py",
)

# R3: files where base_sha/evidence_sha/evidence_commit JSON lines are
# legitimately allowed. The detect-secrets anchored exclusion applies only
# to these files; the validator enforces this by scanning the whole repo.
_SCANNER_ALLOWED_FILES = frozenset(
    {
        INVENTORY_RELPATH,
        DEBT_RELPATH,
        REGISTRY_RELPATH,
        WAIVERS_RELPATH,
        DELTAS_RELPATH,
    }
)

# R3: strict anchored regex matching ONLY the three governance hex keys
# with 40 or 64 hex values and an optional trailing comma.
_SCANNER_HEX_RE = re.compile(
    r'^\s*"(base_sha|evidence_sha|evidence_commit)"\s*:\s*'
    r'"[0-9a-f]{40}([0-9a-f]{24})?"\s*,?\s*$'
)
# R3-R1: the same contract as ASCII BYTES so the scanner never decodes file
# content (an errors=replace decode could silently mangle and skip matches).
_SCANNER_HEX_RE_BYTES = re.compile(
    rb'^\s*"(base_sha|evidence_sha|evidence_commit)"\s*:\s*'
    rb'"[0-9a-f]{40}([0-9a-f]{24})?"\s*,?\s*$'
)
# Phase 2: the minimum product surface that governed_prefixes must always
# include; removing any of these is RED.
MINIMUM_GOVERNED_PREFIXES = ("backend/", "frontend/src/", "scenarios/")

# Phase 7 fail-closed schema checking: every keyword the subset checker
# understands. Anything else in a schema document is RED, never ignored.
SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "description",
        "type",
        "enum",
        "required",
        "properties",
        "items",
        "minLength",
        "minItems",
        "uniqueItems",
        "pattern",
        "additionalProperties",
        "definitions",
        "$ref",
    }
)

# Phase 6: status transitions allowed without a reclassify delta.
# Entering an executed/failed state from a pending/blocked one is normal
# evidence flow; leaving an executed state (PASS/FAIL), or any transition
# involving NOT_APPLICABLE, is a reclassification and needs authorization.
NODE_EXECUTION_TRANSITIONS = frozenset(
    {
        ("NOT_RUN", "PASS"),
        ("NOT_RUN", "FAIL"),
        ("NOT_RUN", "BLOCKED"),
        ("BLOCKED", "PASS"),
        ("BLOCKED", "FAIL"),
    }
)
DEBT_STATUSES = ("BLOCKED", "NOT_COVERED", "CLOSED")

# Paths ignored when comparing two workspace trees in --baseline-dir mode.
FS_COMPARE_IGNORE = {".git", "__pycache__", "node_modules", ".pytest_cache", ".venv", ".gitnexus"}

# Non-semantic record fields: changing them is not a semantic record change
# for the purposes of the sync gate (Phase 3: notes must not satisfy sync).
NON_SEMANTIC_FIELDS = frozenset({"notes"})


class Violation:
    __slots__ = ("code", "path", "message")

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message

    def as_dict(self) -> dict:
        return {"code": self.code, "path": self.path, "message": self.message}


class GovernanceContext:
    def __init__(self):
        self.violations: list[Violation] = []
        self.warnings: list[Violation] = []

    def emit(self, code: str, path: str, message: str) -> None:
        self.violations.append(Violation(code, path, message))

    def warn(self, code: str, path: str, message: str) -> None:
        self.warnings.append(Violation(code, path, message))


# ---------------------------------------------------------------------------
# Mini JSON Schema (draft-07 subset) checker — fail-closed.
# ---------------------------------------------------------------------------

_TYPE_MAP = {"object": dict, "array": list, "string": str, "boolean": bool}


def _type_ok(value, type_name: str) -> bool:
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    py_type = _TYPE_MAP.get(type_name)
    if py_type is None:
        return True
    if py_type is bool:
        return isinstance(value, bool)
    if py_type is str:
        return isinstance(value, str)
    return isinstance(value, py_type) and not isinstance(value, bool)


def _resolve_ref(ref, root_schema: dict):
    if not isinstance(ref, str) or not ref.startswith("#/definitions/"):
        return None
    name = ref.split("/")[-1]
    definitions = root_schema.get("definitions", {}) if isinstance(root_schema, dict) else {}
    target = definitions.get(name)
    return target if isinstance(target, dict) else None


def check_against_schema(instance, schema: dict, path: str, root_schema: dict, emit) -> None:
    """Validate *instance* against a draft-07 subset schema, emitting violations."""

    if not isinstance(schema, dict):
        emit("SCHEMA-TYPE", path, "schema fragment is not an object")
        return
    ref = schema.get("$ref")
    if ref is not None:
        resolved = _resolve_ref(ref, root_schema)
        if resolved is None:
            emit("SCHEMA-BAD-REF", path, f"unresolvable $ref {ref!r}")
            return
        check_against_schema(instance, resolved, path, root_schema, emit)
        return

    type_name = schema.get("type")
    if type_name and not _type_ok(instance, type_name):
        emit("SCHEMA-TYPE", path, f"expected {type_name}, got {type(instance).__name__}")
        return

    if "enum" in schema and instance not in schema["enum"]:
        emit("SCHEMA-ENUM", path, f"value {instance!r} is not one of {schema['enum']!r}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            emit(
                "SCHEMA-MINLENGTH",
                path,
                f"string shorter than minLength {schema['minLength']}",
            )
        pattern = schema.get("pattern")
        if pattern is not None:
            try:
                ok = re.search(pattern, instance) is not None
            except re.error:
                ok = True
            if not ok:
                emit("SCHEMA-PATTERN", path, f"string does not match pattern {pattern!r}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            emit(
                "SCHEMA-MINITEMS",
                path,
                f"array has {len(instance)} items, minItems {schema['minItems']}",
            )
        if schema.get("uniqueItems"):
            seen = []
            for item in instance:
                key = json.dumps(item, sort_keys=True)
                if key in seen:
                    emit("SCHEMA-UNIQUE", path, f"array items are not unique (e.g. {item!r})")
                    break
                seen.append(key)
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(instance):
                check_against_schema(item, item_schema, f"{path}/{i}", root_schema, emit)

    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in instance:
                emit("SCHEMA-REQUIRED", path, f"missing required property {required!r}")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    emit(
                        "SCHEMA-ADDITIONAL",
                        f"{path}/{key}",
                        f"unknown property {key!r} (additionalProperties is false)",
                    )
        for key, sub_schema in props.items():
            if key in instance:
                check_against_schema(
                    instance[key], sub_schema, f"{path}/{key}", root_schema, emit
                )


def check_schema_document(schema, relpath: str, emit) -> None:
    """Phase 7: reject schema files using keywords the checker cannot honor."""

    def walk(node, path):
        if isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}/{i}")
            return
        if not isinstance(node, dict):
            return
        for key in node:
            if key not in SUPPORTED_SCHEMA_KEYWORDS:
                emit(
                    "SCHEMA-UNKNOWN-KEYWORD",
                    f"{relpath}#{path}/{key}",
                    f"unsupported schema keyword {key!r}; the stdlib checker "
                    f"would silently ignore it, which is fail-open",
                )
        ref = node.get("$ref")
        if ref is not None and _resolve_ref(ref, schema) is None:
            emit("SCHEMA-BAD-REF", f"{relpath}#{path}", f"unresolvable $ref {ref!r}")
        for key, value in node.items():
            if key in ("properties", "definitions"):
                # The keys inside properties/definitions are instance field
                # names (data), not schema keywords; only their values are schemas.
                if isinstance(value, dict):
                    for name, sub in value.items():
                        walk(sub, f"{path}/{key}/{name}")
                continue
            if key == "$ref":
                continue
            walk(value, f"{path}/{key}")

    walk(schema, "")


# ---------------------------------------------------------------------------
# Small helpers (unit-tested directly).
# ---------------------------------------------------------------------------


def lcs(a: list, b: list) -> list:
    """Longest common subsequence of two lists of hashable items."""

    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if a[i] == b[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    out = []
    i = j = 0
    while i < n and j < m:
        if a[i] == b[j]:
            out.append(a[i])
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def moved_ids(baseline_order: list, head_order: list) -> set:
    """IDs present in both orders whose relative order changed (not on the LCS)."""

    common_base = [x for x in baseline_order if x in set(head_order)]
    common_head = [x for x in head_order if x in set(baseline_order)]
    stable = set(lcs(common_base, common_head))
    return {x for x in common_head if x not in stable}


def parse_date(value: str):
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        return None


def is_expired(expires: str, today: _dt.date) -> bool:
    """A waiver is active on its expiry day and expired the day after."""

    parsed = parse_date(expires)
    return parsed is None or parsed < today


def blank(value) -> bool:
    return not isinstance(value, str) or value.strip() == ""


def path_matches(path: str, prefix: str) -> bool:
    prefix = prefix.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def parse_anchor(anchor: str):
    """Split 'path', 'path:LINE', or 'path:START-END' into (path, lines|None).

    Returns lines == "invalid" when a line part is present but malformed.
    """

    if ":" not in anchor:
        return anchor, None
    path, _, line_part = anchor.rpartition(":")
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", line_part)
    if not match or not path:
        return anchor, "invalid"
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else start
    return path, (start, end)


def semantic_view(record):
    """Record content without non-semantic fields; used for record-level diffs."""

    if not isinstance(record, dict):
        return record
    return {key: value for key, value in record.items() if key not in NON_SEMANTIC_FIELDS}


def load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, f"file not found: {path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def _git(root: str, *args: str):
    return subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _git_raw(root: str, *args: str):
    """Raw-byte git helper for binary blob retrieval. No text decode,
    no re-encode, no errors=replace — the caller hashes stdout bytes
    directly, so any mangling would silently corrupt the digest."""

    return subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Baseline resolution (git ref, directory tree, or none)
# ---------------------------------------------------------------------------


def _docs_from_map(loader) -> dict:
    """Load the four governed documents through loader(relpath) -> dict|None."""

    docs = {}
    for key, relpath in (
        ("inventory", INVENTORY_RELPATH),
        ("registry", REGISTRY_RELPATH),
        ("debt", DEBT_RELPATH),
        ("deltas", DELTAS_RELPATH),
    ):
        docs[key] = loader(relpath)
    return docs


def resolve_baseline(root: str, args) -> dict:
    """Return {'mode','changed','docs','governance_present','base_sha','error'}."""

    if not args.baseline_ref and not args.baseline_dir:
        return {
            "mode": "none",
            "changed": set(),
            "docs": {},
            "governance_present": False,
            "base_sha": None,
        }

    if args.baseline_dir:
        base = args.baseline_dir

        def loader(relpath):
            data, _ = load_json(os.path.join(base, relpath))
            return data if isinstance(data, (dict, list)) else None

        return {
            "mode": "dir",
            "changed": fs_changed_paths(root, base),
            "docs": _docs_from_map(loader),
            "governance_present": os.path.isfile(os.path.join(base, CONFIG_RELPATH)),
            "base_sha": args.base_sha,
        }

    ref = args.baseline_ref
    rev = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if rev.returncode != 0:
        return {
            "mode": "git-error",
            "changed": set(),
            "docs": {},
            "governance_present": False,
            "base_sha": None,
            "error": rev.stderr.strip() or f"cannot resolve ref {ref}",
        }

    def loader(relpath):
        show = _git(root, "show", f"{ref}:{relpath}")
        if show.returncode != 0:
            return None
        try:
            data = json.loads(show.stdout)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, (dict, list)) else None

    probe = _git(root, "cat-file", "-e", f"{ref}:{CONFIG_RELPATH}")
    diff = _git(root, "diff", "--name-only", ref, "HEAD")
    changed = {line.strip() for line in diff.stdout.splitlines() if line.strip()}
    return {
        "mode": "git",
        "ref": ref,
        "changed": changed,
        "docs": _docs_from_map(loader),
        "governance_present": probe.returncode == 0,
        "base_sha": rev.stdout.strip(),
    }


def fs_changed_paths(head_root: str, baseline_root: str) -> set:
    """Relative paths that differ between two directory trees (posix style)."""

    def snapshot(base: str) -> dict:
        out = {}
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in FS_COMPARE_IGNORE]
            for name in filenames:
                if name.endswith(".pyc"):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                with open(full, "rb") as fh:
                    out[rel] = hash(fh.read())
        return out

    head = snapshot(head_root)
    base = snapshot(baseline_root)
    changed = set()
    for rel, digest in head.items():
        if base.get(rel) != digest:
            changed.add(rel)
    for rel in base:
        if rel not in head:
            changed.add(rel)
    return changed


# ---------------------------------------------------------------------------
# Delta eligibility (Phase 6 anti-replay)
# ---------------------------------------------------------------------------


class DeltaAuthorizer:
    """Kind-precise authorization that only accepts deltas newly added or
    substantively modified in this comparison and bound to the comparison
    base. Historical deltas are single-use: reusing one is DELTA-REPLAY."""

    def __init__(self, head_deltas, base_deltas, base_sha):
        self.base_sha = base_sha
        self.base_by_id = {}
        for delta in base_deltas or []:
            if isinstance(delta, dict) and delta.get("delta_id"):
                self.base_by_id[delta["delta_id"]] = semantic_view(delta)
        self.new, self.historical, self.base_mismatch = [], [], []
        for delta in head_deltas or []:
            if not isinstance(delta, dict) or not delta.get("delta_id"):
                continue
            if self.base_by_id.get(delta["delta_id"]) == semantic_view(delta):
                self.historical.append(delta)
            else:
                self.new.append(delta)
                # Fail-closed: without a verified comparison base (base_sha None),
                # no delta can be considered base-bound and eligible.
                if delta.get("base_sha") != base_sha:
                    self.base_mismatch.append(delta)

    def _matches(self, delta, kind, ids=None, path=None):
        if delta.get("kind") != kind:
            return False
        if ids is not None and not ids <= set(delta.get("affected_ids") or []):
            return False
        if path is not None:
            paths = delta.get("affected_paths") or []
            if not any(path_matches(path, p) for p in paths if isinstance(p, str)):
                return False
        return True

    def authorize(self, kind, ids=None, path=None):
        """Return None when authorized, else the violation code to emit."""

        for delta in self.new:
            if delta in self.base_mismatch:
                continue
            if self._matches(delta, kind, ids, path):
                return None
        for delta in self.base_mismatch:
            if self._matches(delta, kind, ids, path):
                return "DELTA-BASE-MISMATCH"
        for delta in self.historical:
            if self._matches(delta, kind, ids, path):
                return "DELTA-REPLAY"
        return ""

    def covered_paths(self, kinds=None) -> set:
        """Paths authorized by eligible deltas of the given kinds (all if None)."""

        out = set()
        for delta in self.new:
            if delta in self.base_mismatch:
                continue
            if kinds is not None and delta.get("kind") not in kinds:
                continue
            for path in delta.get("affected_paths") or []:
                if isinstance(path, str):
                    out.add(path)
        return out


# ---------------------------------------------------------------------------
# Workspace validation
# ---------------------------------------------------------------------------


# HE2-ET1 evaluator whitelist (mirrors authority_runner.EVALUATOR_WHITELIST;
# the registry may only reference these in-process evaluator ids).
ET1_EVALUATOR_WHITELIST = frozenset(
    {
        "EVAL_PG_ROLE", "EVAL_TEST_DB_URL", "EVAL_TEMP_DB", "EVAL_ALEMBIC_HEAD",
        "EVAL_REDIS", "EVAL_COLLECT_MANIFEST", "EVAL_PHASE_FAIL_STOP",
        "EVAL_ROLE_RECHECK", "EVAL_SESSIONSTART_PROOF", "EVAL_GIT_REMOTE",
        "EVAL_GIT_LINEAGE", "EVAL_EVIDENCE_PACKAGING", "EVAL_EOL",
        "EVAL_VITE_SETTLE", "EVAL_EMAIL_DOMAIN",
    }
)
ET1_TRAPS_RELPATH = f"{GOV_DIR}/inventory/execution-traps.json"
ET1_PROFILES_RELPATH = f"{GOV_DIR}/inventory/authority-profiles.json"


def _check_execution_traps(ctx: "GovernanceContext", root: str) -> None:
    """HE2-ET1 structural mode: registry/profile/evaluator truth.

    RED on: registry/profile unreadable, trap deleted (expected id set is
    hardcoded), any P0/P1 trap disabled, duplicate exit codes, unknown
    evaluator, evaluator without a reachable negative control, a P0/P1 trap
    not referenced by any authority profile, or any authority profile
    referencing an unknown trap.
    """
    registry, rerr = load_json(os.path.join(root, ET1_TRAPS_RELPATH))
    if rerr or not isinstance(registry, dict):
        ctx.emit("ET1-REGISTRY-ERROR", ET1_TRAPS_RELPATH, rerr or "must be an object")
        return
    profiles, perr = load_json(os.path.join(root, ET1_PROFILES_RELPATH))
    if perr or not isinstance(profiles, dict):
        ctx.emit("ET1-PROFILES-ERROR", ET1_PROFILES_RELPATH, perr or "must be an object")
        profiles = {}

    expected_trap_ids = {
        "TRAP_PG_ROLE_SUPER", "TRAP_TEST_DB_URL_EMPTY", "TRAP_TEMP_DB_CAPABILITY",
        "TRAP_ALEMBIC_MULTI_HEAD", "TRAP_REDIS_WRONG_DB",
        "TRAP_COLLECT_NODE_SET_DRIFT", "TRAP_PHASE_CONTINUE_AFTER_FAIL",
        "TRAP_JIT_ROLE_ESCALATION", "TRAP_SESSIONSTART_DRIFT",
        "TRAP_NON_CANONICAL_REMOTE", "TRAP_LINEAGE_CONFUSION",
        "TRAP_EVIDENCE_GITIGNORED", "TRAP_MIXED_EOF", "TRAP_VITE_NETWORKIDLE",
        "TRAP_SPECIAL_USE_EMAIL_DOMAIN",
    }
    traps = registry.get("traps")
    if not isinstance(traps, list):
        ctx.emit("ET1-REGISTRY-ERROR", ET1_TRAPS_RELPATH, "traps must be an array")
        return
    seen_ids = set()
    exit_codes = {}
    by_id = {}
    for trap in traps:
        trap_id = trap.get("trap_id")
        if trap_id in seen_ids:
            ctx.emit("ET1-DUPLICATE-TRAP", ET1_TRAPS_RELPATH, f"duplicate trap id {trap_id}")
            continue
        seen_ids.add(trap_id)
        by_id[trap_id] = trap
        code = trap.get("stable_exit_code")
        if code in exit_codes:
            ctx.emit(
                "ET1-EXIT-CODE-CONFLICT", ET1_TRAPS_RELPATH,
                f"exit code {code} reused by {exit_codes[code]} and {trap_id}",
            )
        else:
            exit_codes[code] = trap_id
        if trap.get("evaluator_id") not in ET1_EVALUATOR_WHITELIST:
            ctx.emit(
                "ET1-UNKNOWN-EVALUATOR", ET1_TRAPS_RELPATH,
                f"trap {trap_id} references evaluator {trap.get('evaluator_id')}",
            )
        elif not str(trap.get("negative_control_id") or "").startswith(("NC-", "NC_")):
            ctx.emit(
                "ET1-MISSING-NEGATIVE-CONTROL", ET1_TRAPS_RELPATH,
                f"trap {trap_id} lacks a reachable negative control id",
            )
        if trap.get("risk") in ("P0", "P1") and trap.get("status") != "ACTIVE":
            ctx.emit(
                "ET1-P0P1-DISABLED", ET1_TRAPS_RELPATH,
                f"trap {trap_id} ({trap.get('risk')}) is {trap.get('status')}",
            )
    for trap_id in sorted(expected_trap_ids - seen_ids):
        ctx.emit("ET1-TRAP-DELETED", ET1_TRAPS_RELPATH, f"expected trap {trap_id} missing")

    profile_trap_refs = set()
    for profile in profiles.get("profiles", []) or []:
        for ref in profile.get("required_traps", []) or []:
            profile_trap_refs.add(ref)
            if ref not in by_id:
                ctx.emit(
                    "ET1-PROFILE-UNKNOWN-TRAP", ET1_PROFILES_RELPATH,
                    f"profile {profile.get('profile_id')} references unknown trap {ref}",
                )
    for trap_id, trap in sorted(by_id.items()):
        if trap.get("risk") in ("P0", "P1") and trap_id not in profile_trap_refs:
            ctx.emit(
                "ET1-P0P1-UNREFERENCED", ET1_TRAPS_RELPATH,
                f"{trap.get('risk')} trap {trap_id} is not referenced by any authority profile",
            )


def validate_workspace(root: str, today: _dt.date, args) -> dict:
    ctx = GovernanceContext()
    mode = getattr(args, "mode", "structural")

    root = os.path.abspath(root)
    config, err = load_json(os.path.join(root, CONFIG_RELPATH))
    if err or not isinstance(config, dict):
        ctx.emit("CONFIG-ERROR", CONFIG_RELPATH, err or "governed-paths.json must be an object")
        config = {}

    def load_schema(filename):
        schema, serr = load_json(os.path.join(root, SCHEMA_DIR_RELPATH, filename))
        if serr:
            ctx.emit("LOAD-ERROR", f"{SCHEMA_DIR_RELPATH}/{filename}", serr)
            return None
        check_schema_document(schema, f"{SCHEMA_DIR_RELPATH}/{filename}", ctx.emit)
        return schema

    config_schema = load_schema(CONFIG_SCHEMA)
    if config_schema is not None:
        check_against_schema(config, config_schema, CONFIG_RELPATH, config_schema, ctx.emit)

    governed_prefixes = config.get("governed_prefixes") or []
    _check_config_semantics(ctx, config)

    _check_execution_traps(ctx, root)

    docs = {}
    doc_specs = [
        ("inventory", INVENTORY_RELPATH, INVENTORY_SCHEMA),
        ("debt", DEBT_RELPATH, DEBT_SCHEMA),
        ("registry", REGISTRY_RELPATH, REGISTRY_SCHEMA),
        ("waivers", WAIVERS_RELPATH, WAIVERS_SCHEMA),
        ("deltas", DELTAS_RELPATH, DELTAS_SCHEMA),
        # HE2-ET1: execution-traps registry + authority profiles are
        # schema-validated like every other governed document.
        ("et1_traps", ET1_TRAPS_RELPATH, "execution-traps.schema.json"),
        ("et1_profiles", ET1_PROFILES_RELPATH, "authority-profiles.schema.json"),
    ]
    for key, relpath, schema_file in doc_specs:
        schema = load_schema(schema_file)
        if schema is None:
            continue
        doc, derr = load_json(os.path.join(root, relpath))
        if derr:
            ctx.emit("LOAD-ERROR", relpath, derr)
            continue
        docs[key] = doc
        check_against_schema(doc, schema, relpath, schema, ctx.emit)

    inventory = docs.get("inventory") if isinstance(docs.get("inventory"), dict) else {}
    nodes = inventory.get("nodes", []) if isinstance(inventory, dict) else []
    debt_doc = docs.get("debt") if isinstance(docs.get("debt"), dict) else {}
    debts = debt_doc.get("debts", []) if isinstance(debt_doc, dict) else []
    registry = docs.get("registry") if isinstance(docs.get("registry"), dict) else {}
    interactions = registry.get("interactions", []) if isinstance(registry, dict) else []
    waivers = docs.get("waivers", []) if isinstance(docs.get("waivers"), list) else []
    deltas = docs.get("deltas", []) if isinstance(docs.get("deltas"), list) else []

    _check_inventory_semantics(ctx, nodes, interactions, debts)
    _check_debt_semantics(ctx, debts, nodes)
    _check_registry_semantics(
        ctx, interactions, config.get("required_interaction_categories") or []
    )
    _check_waivers(ctx, waivers, today)
    _check_anchor_targets(ctx, root, nodes, interactions)
    _check_scanner_scope(ctx, root)
    _check_ids_unique(ctx, nodes, debts, interactions, waivers, deltas)

    baseline = resolve_baseline(root, args)
    if baseline.get("mode") == "git-error":
        ctx.emit("CONFIG-ERROR", "baseline", baseline.get("error", "baseline resolution failed"))
    else:
        base_docs = baseline.get("docs") or {}
        base_inventory = (
            base_docs.get("inventory") if isinstance(base_docs.get("inventory"), dict) else {}
        )
        base_nodes = base_inventory.get("nodes", []) if isinstance(base_inventory, dict) else []
        base_debt_doc = base_docs.get("debt") if isinstance(base_docs.get("debt"), dict) else {}
        base_debts = base_debt_doc.get("debts", []) if isinstance(base_debt_doc, dict) else []
        base_deltas_doc = base_docs.get("deltas")
        base_deltas = base_deltas_doc if isinstance(base_deltas_doc, list) else []

        authorizer = DeltaAuthorizer(deltas, base_deltas, baseline.get("base_sha"))
        _check_delta_semantics(ctx, deltas)
        _check_drift(ctx, baseline, nodes, authorizer)
        _check_status_transitions(ctx, baseline, nodes, base_nodes, debts, base_debts, authorizer)
        _check_semantic_sync(
            ctx, baseline, docs, base_docs, governed_prefixes, waivers, today, authorizer
        )

    _verify_pass_evidence(ctx, root, nodes)

    release_blockers = [
        debt.get("debt_id")
        for debt in debts
        if isinstance(debt, dict)
        and debt.get("status") in ("BLOCKED", "NOT_COVERED")
        and debt.get("risk") in ("P0", "P1")
        and debt.get("release_blocked")
    ]
    structural = "FAIL" if ctx.violations else "PASS"
    release = "BLOCKED" if release_blockers else "PASS"

    return {
        "validator_version": VALIDATOR_VERSION,
        "root": root,
        "today": today.isoformat(),
        "mode": mode,
        "baseline": {
            "mode": baseline.get("mode", "none"),
            "ref": baseline.get("ref"),
            "base_sha": baseline.get("base_sha"),
            "governance_present": baseline.get("governance_present", False),
        },
        "green": not ctx.violations,
        "gates": {
            "structural_gate": structural,
            "release_gate": release,
            "release_blockers": release_blockers,
        },
        "violations": [v.as_dict() for v in ctx.violations],
        "warnings": [v.as_dict() for v in ctx.warnings],
        "coverage": compute_coverage(nodes, interactions),
        "debt": compute_debt_summary(debts),
    }


def _check_config_semantics(ctx: GovernanceContext, config: dict) -> None:
    prefixes = config.get("governed_prefixes")
    if isinstance(prefixes, list):
        if not prefixes:
            ctx.emit(
                "CONFIG-PREFIXES-EMPTY",
                f"{CONFIG_RELPATH}#/governed_prefixes",
                "governed_prefixes must not be empty; emptying it would un-govern "
                "the whole product surface",
            )
        seen = set()
        for idx, prefix in enumerate(prefixes):
            if prefix in seen:
                ctx.emit(
                    "CONFIG-PREFIX-DUP",
                    f"{CONFIG_RELPATH}#/governed_prefixes/{idx}",
                    f"duplicate governed prefix {prefix!r}",
                )
            seen.add(prefix)
        missing = [p for p in MINIMUM_GOVERNED_PREFIXES if p not in set(prefixes)]
        if missing:
            ctx.emit(
                "CONFIG-MINIMUM-PREFIX",
                f"{CONFIG_RELPATH}#/governed_prefixes",
                f"governed_prefixes must always include the minimum product paths; "
                f"missing {missing}",
            )


def _check_inventory_semantics(ctx: GovernanceContext, nodes, interactions, debts) -> None:
    registry_ids = {i.get("interaction_id") for i in interactions if isinstance(i, dict)}
    open_debt_nodes = set()
    for debt in debts:
        if isinstance(debt, dict) and debt.get("status") in ("BLOCKED", "NOT_COVERED"):
            open_debt_nodes.update(debt.get("node_ids") or [])

    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        pointer = f"{INVENTORY_RELPATH}#/nodes/{idx}"
        node_id = node.get("id", f"index-{idx}")
        status = node.get("status")
        risk = node.get("risk")

        for field in ORACLE_FIELDS:
            value = node.get(field)
            if blank(value):
                ctx.emit(
                    "INV-ORACLE-EMPTY",
                    f"{pointer}/{field}",
                    f"node {node_id}: oracle {field} is blank; blank means NOT_COVERED, "
                    f"use {ORACLE_SENTINEL} explicitly when it does not apply",
                )
            elif str(value).strip().upper() in _FAKE_SENTINELS and value != ORACLE_SENTINEL:
                ctx.emit(
                    "INV-ORACLE-INVALID",
                    f"{pointer}/{field}",
                    f"node {node_id}: oracle {field} must be an assertion or exactly "
                    f"'{ORACLE_SENTINEL}', got {value!r}",
                )

        if risk in ("P0", "P1"):
            mutation = node.get("mutation_id")
            if not isinstance(mutation, str) or mutation.strip().upper() in MUTATION_SENTINELS:
                ctx.emit(
                    "INV-MUTATION-MISSING",
                    f"{pointer}/mutation_id",
                    f"node {node_id}: {risk} nodes require a mutation or counterexample ID "
                    "(standard section 11)",
                )

        if status == "BLOCKED":
            missing = [
                field
                for field in ("blocked_owner", "blocked_closure_condition")
                if blank(node.get(field))
            ]
            if missing:
                ctx.emit(
                    "INV-BLOCKED-OWNER",
                    pointer,
                    f"node {node_id}: BLOCKED requires blocked_owner and "
                    f"blocked_closure_condition; missing {missing}",
                )
            if node_id not in open_debt_nodes:
                ctx.emit(
                    "INV-BLOCKED-DEBT",
                    pointer,
                    f"node {node_id}: BLOCKED node has no open coverage-debt entry "
                    "(standard section 13)",
                )

        if status == "PASS":
            evidence = node.get("evidence_sha")
            if not isinstance(evidence, str) or not SHA_RE.match(evidence):
                ctx.emit(
                    "INV-PASS-EVIDENCE",
                    f"{pointer}/evidence_sha",
                    f"node {node_id}: PASS requires a 40- or 64-hex evidence SHA",
                )
        if status == "FAIL" and node_id not in open_debt_nodes:
            ctx.emit(
                "INV-FAIL-DEBT",
                pointer,
                f"node {node_id}: FAIL node must be tracked in an open coverage-debt entry",
            )

        for ref in node.get("interaction_ids") or []:
            if ref not in registry_ids:
                ctx.emit(
                    "REG-REF-UNKNOWN",
                    f"{pointer}/interaction_ids",
                    f"node {node_id}: references unknown interaction {ref!r}",
                )


def _check_debt_semantics(ctx: GovernanceContext, debts, nodes) -> None:
    node_ids = {n.get("id") for n in nodes if isinstance(n, dict)}
    for idx, debt in enumerate(debts):
        if not isinstance(debt, dict):
            continue
        pointer = f"{DEBT_RELPATH}#/debts/{idx}"
        if debt.get("status") in ("BLOCKED", "NOT_COVERED"):
            missing = [
                field
                for field in ("owner", "reason", "closure_condition", "target_milestone")
                if blank(debt.get(field))
            ]
            if missing:
                ctx.emit(
                    "DEBT-INCOMPLETE",
                    pointer,
                    f"debt {debt.get('debt_id', idx)}: BLOCKED/NOT_COVERED entries require "
                    f"owner, reason, closure_condition, and target_milestone; missing {missing}",
                )
        for ref in debt.get("node_ids") or []:
            if ref not in node_ids:
                ctx.emit(
                    "DEBT-NODE-REF-UNKNOWN",
                    f"{pointer}/node_ids",
                    f"debt {debt.get('debt_id', idx)}: references unknown node {ref!r}",
                )


def _check_registry_semantics(ctx: GovernanceContext, interactions, required_categories) -> None:
    present = {i.get("category") for i in interactions if isinstance(i, dict)}
    for category in required_categories:
        if category not in present:
            ctx.emit(
                "REG-CATEGORY-MISSING",
                REGISTRY_RELPATH,
                f"required critical-interaction category {category!r} is not registered",
            )


def _check_waivers(ctx: GovernanceContext, waivers, today: _dt.date) -> None:
    for idx, waiver in enumerate(waivers):
        if not isinstance(waiver, dict):
            continue
        pointer = f"{WAIVERS_RELPATH}#[{idx}]"
        waiver_id = waiver.get("waiver_id", idx)

        opened = (
            parse_date(waiver.get("opened_on")) if isinstance(waiver.get("opened_on"), str) else None
        )
        expires = (
            parse_date(waiver.get("expires_on")) if isinstance(waiver.get("expires_on"), str) else None
        )
        if opened is None or expires is None:
            ctx.emit(
                "WVR-INVALID-DATE",
                pointer,
                f"waiver {waiver_id}: opened_on and expires_on must be valid ISO dates",
            )
        elif expires < opened:
            ctx.emit(
                "WVR-INVALID-DATE",
                pointer,
                f"waiver {waiver_id}: expires_on {waiver.get('expires_on')} precedes "
                f"opened_on {waiver.get('opened_on')}",
            )
        elif expires < today:
            ctx.emit(
                "WVR-EXPIRED",
                pointer,
                f"waiver {waiver_id} expired on {waiver.get('expires_on')} "
                f"(today {today.isoformat()}); renew or remove it",
            )

        for pidx, path in enumerate(waiver.get("paths") or []):
            if not isinstance(path, str) or not path.strip():
                ctx.emit(
                    "WVR-PATH-INVALID",
                    f"{pointer}/paths/{pidx}",
                    f"waiver {waiver_id}: waiver paths must be non-empty repo paths",
                )
                continue
            if path.strip() in {"", ".", "/", ".."}:
                ctx.emit(
                    "WVR-PATH-INVALID",
                    f"{pointer}/paths/{pidx}",
                    f"waiver {waiver_id}: path {path!r} is a repository-root form; "
                    f"implicit global exemptions are forbidden",
                )
            if WILDCARD_RE.search(path):
                ctx.emit(
                    "WVR-PATH-INVALID",
                    f"{pointer}/paths/{pidx}",
                    f"waiver {waiver_id}: path {path!r} contains wildcard characters",
                )
            if any(
                path_matches(path, protected) or path_matches(protected, path)
                for protected in PROTECTED_PATHS
            ):
                ctx.emit(
                    "WVR-PATH-PROTECTED",
                    f"{pointer}/paths/{pidx}",
                    f"waiver {waiver_id}: path {path!r} touches the governance core, "
                    f"which is not waivable; use a governance protocol delta",
                )


def _check_anchor_targets(ctx: GovernanceContext, root: str, nodes, interactions) -> None:
    """Phase 7: anchors must exist with valid, in-range line numbers (RED)."""

    line_counts = {}

    def check(pointer: str, anchors) -> None:
        for anchor in anchors or []:
            if not isinstance(anchor, str) or not anchor.strip():
                continue
            path, lines = parse_anchor(anchor.strip())
            if lines == "invalid":
                ctx.emit(
                    "ANCHOR-LINE-INVALID",
                    pointer,
                    f"source anchor {anchor!r} has an invalid line specification",
                )
                continue
            full = os.path.join(root, path)
            if not os.path.isfile(full):
                ctx.emit(
                    "ANCHOR-MISSING",
                    pointer,
                    f"source anchor path does not exist in this tree: {path!r}",
                )
                continue
            if lines is None:
                continue
            if path not in line_counts:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    line_counts[path] = len(fh.read().splitlines())
            start, end = lines
            if not (1 <= start <= end <= line_counts[path]):
                ctx.emit(
                    "ANCHOR-LINE-INVALID",
                    pointer,
                    f"source anchor {anchor!r}: lines {start}-{end} out of range for "
                    f"{path!r} ({line_counts[path]} lines)",
                )

    for idx, node in enumerate(nodes):
        if isinstance(node, dict):
            check(
                f"{INVENTORY_RELPATH}#/nodes/{idx}/source_anchors", node.get("source_anchors")
            )
    for idx, interaction in enumerate(interactions):
        if isinstance(interaction, dict):
            check(
                f"{REGISTRY_RELPATH}#/interactions/{idx}/source_anchors",
                interaction.get("source_anchors"),
            )


def _scanner_candidate_files(root: str) -> list[str]:
    """R3-R1: every version-controlled or to-be-committed plain file under
    root — NO extension whitelist. Prefers
    ``git ls-files --cached --others --exclude-standard`` (gitignore is the
    exclusion mechanism for node_modules/.git/.venv and friends); when root
    is not itself a git work tree (unit-test workspaces), falls back to
    os.walk with the same FIXED directory exclusions. The exclusion set is
    a frozen constant — it can never be turned off through configuration."""
    git_root = None
    try:
        probe = subprocess.run(
            ["git", "-C", root, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            candidate = os.path.normpath(probe.stdout.strip())
            if candidate == os.path.normpath(root):
                git_root = candidate
    except OSError:
        git_root = None

    if git_root is not None:
        try:
            listing = subprocess.run(
                [
                    "git", "-C", root, "ls-files",
                    "--cached", "--others", "--exclude-standard", "-z",
                ],
                capture_output=True,
            )
            if listing.returncode == 0:
                names = listing.stdout.split(b"\0")
                out = []
                for raw in names:
                    if not raw:
                        continue
                    rel = raw.decode("utf-8", "surrogateescape")
                    # gitignore already excluded ignored files; the fixed
                    # non-indexable dirs are guarded defensively as well.
                    parts = rel.split("/")
                    if any(part in FS_COMPARE_IGNORE for part in parts[:-1]):
                        continue
                    out.append(rel)
                return out
        except OSError:
            pass

    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in FS_COMPARE_IGNORE]
        for name in filenames:
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return out


def _check_scanner_scope(ctx: GovernanceContext, root: str) -> None:
    """R3-R1: scan EVERY version-controlled / to-be-committed plain file
    (any extension — .py/.ts/.tsx/.md/.yaml/.yml/.toml/.env/json/... and
    everything else) for base_sha/evidence_sha/evidence_commit hex lines
    outside the allowed governance JSON set. Content is matched as raw
    ASCII bytes per line — no text decode, so no errors=replace path can
    silently skip a match. The detect-secrets anchored exclusion only
    applies to _SCANNER_ALLOWED_FILES; the same shape anywhere else is a
    structural violation."""

    for rel in _scanner_candidate_files(root):
        if rel in _SCANNER_ALLOWED_FILES:
            continue
        full = os.path.join(root, *rel.split("/"))
        try:
            with open(full, "rb") as fh:
                content = fh.read()
        except OSError:
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            if _SCANNER_HEX_RE_BYTES.match(line):
                ctx.emit(
                    "SCANNER-SCOPE-VIOLATION",
                    f"{rel}:{lineno}",
                    f"governance hex key (base_sha/evidence_sha/evidence_commit) "
                    f"found outside allowed governance JSON files; "
                    f"the detect-secrets anchored exclusion does not cover {rel!r}",
                )
                return  # one violation is enough to prove the point


def _check_ids_unique(ctx, nodes, debts, interactions, waivers, deltas) -> None:
    specs = [
        ("INV-DUP-ID", INVENTORY_RELPATH, nodes, "id", "nodes"),
        ("DEBT-DUP-ID", DEBT_RELPATH, debts, "debt_id", "debts"),
        ("REG-DUP-ID", REGISTRY_RELPATH, interactions, "interaction_id", "interactions"),
        ("WVR-DUP-ID", WAIVERS_RELPATH, waivers, "waiver_id", "waivers"),
        ("DELTA-DUP-ID", DELTAS_RELPATH, deltas, "delta_id", "deltas"),
    ]
    for code, relpath, items, key, section in specs:
        seen = {}
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            value = item.get(key)
            if value in seen:
                ctx.emit(
                    code,
                    f"{relpath}#/{section}/{idx}/{key}",
                    f"duplicate {key} {value!r} (first seen at index {seen[value]})",
                )
            else:
                seen[value] = idx


def _check_delta_semantics(ctx: GovernanceContext, deltas) -> None:
    for idx, delta in enumerate(deltas):
        if not isinstance(delta, dict):
            continue
        pointer = f"{DELTAS_RELPATH}#[{idx}]"
        kind = delta.get("kind")
        if kind in ("removal", "rename", "reorder", "reclassify") and not (
            delta.get("affected_ids") or []
        ):
            ctx.emit(
                "DELTA-AFFECTED-IDS-EMPTY",
                pointer,
                f"delta {delta.get('delta_id', idx)}: kind {kind!r} requires at least one "
                f"affected id",
            )
        if kind == "rename" and len(delta.get("affected_ids") or []) < 2:
            ctx.emit(
                "DELTA-AFFECTED-IDS-EMPTY",
                pointer,
                f"delta {delta.get('delta_id', idx)}: rename deltas must list both the "
                f"previous and the new node id in affected_ids",
            )
        if kind == "governance" and not (delta.get("affected_paths") or []):
            ctx.emit(
                "DELTA-AFFECTED-IDS-EMPTY",
                pointer,
                f"delta {delta.get('delta_id', idx)}: governance deltas must list the "
                f"affected governance paths in affected_paths",
            )


def _check_drift(ctx: GovernanceContext, baseline: dict, nodes, authorizer: DeltaAuthorizer) -> None:
    base_inventory = (baseline.get("docs") or {}).get("inventory")
    if not baseline.get("governance_present") or not isinstance(base_inventory, dict):
        return  # bootstrap: baseline predates the governance system

    baseline_nodes = base_inventory.get("nodes") or []
    baseline_ids = [n.get("id") for n in baseline_nodes if isinstance(n, dict)]
    head_ids = [n.get("id") for n in nodes if isinstance(n, dict)]
    head_set, baseline_set = set(head_ids), set(baseline_ids)

    renamed_away = {
        n.get("renamed_from") for n in nodes if isinstance(n, dict) and n.get("renamed_from")
    }

    for node_id in baseline_ids:
        if node_id in head_set or node_id in renamed_away:
            continue
        replay = authorizer.authorize("removal", ids={node_id})
        if replay is None:
            continue
        if replay:
            ctx.emit(
                replay,
                DELTAS_RELPATH,
                f"node {node_id!r} removal is not covered by an eligible delta "
                f"({replay})",
            )
        ctx.emit(
            "DRIFT-SILENT-DELETE",
            INVENTORY_RELPATH,
            f"node {node_id!r} exists in the baseline inventory but was removed without "
            f"an eligible 'removal' protocol delta",
        )

    for node in nodes:
        if not isinstance(node, dict):
            continue
        previous = node.get("renamed_from")
        if not previous:
            continue
        node_id = node.get("id")
        if previous not in baseline_set:
            ctx.emit(
                "DRIFT-RENAME-UNKNOWN",
                INVENTORY_RELPATH,
                f"node {node_id!r} claims renamed_from {previous!r} which does not exist "
                f"in the baseline inventory",
            )
            continue
        code = authorizer.authorize("rename", ids={previous, node_id})
        if code:
            ctx.emit(
                code,
                DELTAS_RELPATH,
                f"rename {previous!r} -> {node_id!r} has no eligible 'rename' delta "
                f"({code or 'missing'})",
            )

    for node_id in sorted(moved_ids(baseline_ids, head_ids)):
        code = authorizer.authorize("reorder", ids={node_id})
        if code is None:
            continue
        if code:
            ctx.emit(
                code,
                DELTAS_RELPATH,
                f"node {node_id!r} reorder is not covered by an eligible delta "
                f"({code})",
            )
        ctx.emit(
            "DRIFT-REORDER",
            INVENTORY_RELPATH,
            f"node {node_id!r} order changed without an eligible 'reorder' protocol "
            f"delta"
            + (" (a historical delta cannot be reused)" if code == "DELTA-REPLAY" else ""),
        )


def _check_status_transitions(
    ctx: GovernanceContext,
    baseline: dict,
    nodes,
    base_nodes,
    debts,
    base_debts,
    authorizer: DeltaAuthorizer,
) -> None:
    if not baseline.get("governance_present"):
        return

    base_status = {n.get("id"): n.get("status") for n in base_nodes if isinstance(n, dict)}
    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        node_id, status = node.get("id"), node.get("status")
        was = base_status.get(node_id)
        if was is None or was == status:
            continue
        if (was, status) in NODE_EXECUTION_TRANSITIONS:
            continue
        code = authorizer.authorize("reclassify", ids={node_id})
        if code is None:
            continue
        if code:
            ctx.emit(
                code,
                DELTAS_RELPATH,
                f"node {node_id!r} status transition {was} -> {status}: delta not "
                f"usable ({code})",
            )
        ctx.emit(
            "STATUS-UNAUTHORIZED",
            f"{INVENTORY_RELPATH}#/nodes/{idx}/status",
            f"node {node_id!r} status transition {was} -> {status} requires an eligible "
            f"'reclassify' protocol delta; executed results may not be relabeled "
            f"(standard section 16)",
        )

    base_debt_status = {
        d.get("debt_id"): d.get("status") for d in base_debts if isinstance(d, dict)
    }
    for idx, debt in enumerate(debts):
        if not isinstance(debt, dict):
            continue
        debt_id, status = debt.get("debt_id"), debt.get("status")
        was = base_debt_status.get(debt_id)
        if was is None or was == status or status == "CLOSED" or was != "CLOSED":
            continue
        code = authorizer.authorize("reclassify", ids={debt_id})
        if code is None:
            continue
        if code:
            ctx.emit(
                code,
                DELTAS_RELPATH,
                f"debt {debt_id!r} reopening {was} -> {status}: delta not usable ({code})",
            )
        ctx.emit(
            "STATUS-UNAUTHORIZED",
            f"{DEBT_RELPATH}#/debts/{idx}/status",
            f"debt {debt_id!r} reopened {was} -> {status} requires an eligible "
            f"'reclassify' protocol delta",
        )


# ---------------------------------------------------------------------------
# Semantic inventory sync (Phase 3)
# ---------------------------------------------------------------------------


def _head_records(docs: dict) -> dict:
    """record key -> (exact anchor file paths, prefix affected paths)."""

    records = {}
    inventory = docs.get("inventory") if isinstance(docs.get("inventory"), dict) else {}
    for node in (inventory.get("nodes") or []) if isinstance(inventory, dict) else []:
        if not isinstance(node, dict) or not node.get("id"):
            continue
        anchors = set()
        for anchor in node.get("source_anchors") or []:
            if isinstance(anchor, str) and anchor.strip():
                path, _ = parse_anchor(anchor.strip())
                anchors.add(path)
        records[("node", node["id"])] = (anchors, set())
    registry = docs.get("registry") if isinstance(docs.get("registry"), dict) else {}
    for interaction in (registry.get("interactions") or []) if isinstance(registry, dict) else []:
        if not isinstance(interaction, dict) or not interaction.get("interaction_id"):
            continue
        anchors, affected = set(), set()
        for anchor in interaction.get("source_anchors") or []:
            if isinstance(anchor, str) and anchor.strip():
                path, _ = parse_anchor(anchor.strip())
                anchors.add(path)
        for path in interaction.get("affected_paths") or []:
            if isinstance(path, str) and path.strip():
                affected.add(path)
        records[("interaction", interaction["interaction_id"])] = (anchors, affected)
    debt_doc = docs.get("debt") if isinstance(docs.get("debt"), dict) else {}
    for debt in (debt_doc.get("debts") or []) if isinstance(debt_doc, dict) else []:
        if not isinstance(debt, dict) or not debt.get("debt_id"):
            continue
        affected = {
            path
            for path in debt.get("affected_paths") or []
            if isinstance(path, str) and path.strip()
        }
        records[("debt", debt["debt_id"])] = (set(), affected)
    return records


def _raw_records(docs: dict) -> dict:
    """record key -> semantic content, for record-level diffing."""

    out = {}

    def add(kind, items, id_key):
        for item in items or []:
            if isinstance(item, dict) and item.get(id_key):
                out[(kind, item[id_key])] = semantic_view(item)

    inventory = docs.get("inventory") if isinstance(docs.get("inventory"), dict) else {}
    add("node", inventory.get("nodes"), "id")
    registry = docs.get("registry") if isinstance(docs.get("registry"), dict) else {}
    add("interaction", registry.get("interactions"), "interaction_id")
    debt_doc = docs.get("debt") if isinstance(docs.get("debt"), dict) else {}
    add("debt", debt_doc.get("debts"), "debt_id")
    return out


def _check_semantic_sync(
    ctx: GovernanceContext,
    baseline: dict,
    head_docs: dict,
    base_docs: dict,
    governed_prefixes: list,
    waivers,
    today: _dt.date,
    authorizer: DeltaAuthorizer,
) -> None:
    if not baseline.get("governance_present"):
        return  # bootstrap: enforcement binds changes after adoption

    changed = baseline.get("changed") or set()
    effective = list(governed_prefixes) + list(PROTECTED_PATHS)
    governed_changed = sorted(
        path for path in changed if any(path_matches(path, prefix) for prefix in effective)
    )
    if not governed_changed:
        return

    head_records = _head_records(head_docs)
    head_raw, base_raw = _raw_records(head_docs), _raw_records(base_docs)
    changed_keys = {
        key
        for key, content in head_raw.items()
        if key not in base_raw or base_raw[key] != content
    }

    def covered_by_records(path: str) -> bool:
        for key in changed_keys:
            if key not in head_records:
                continue
            anchors, affected = head_records[key]
            if path in anchors:
                return True
            if any(path_matches(path, prefix) for prefix in affected):
                return True
        return False

    delta_paths = authorizer.covered_paths()

    def covered_by_delta(path: str) -> bool:
        return any(path_matches(path, prefix) for prefix in delta_paths)

    active_waivers = []
    for waiver in waivers:
        if not isinstance(waiver, dict) or waiver.get("scope") != "inventory-sync":
            continue
        expires = (
            parse_date(waiver.get("expires_on"))
            if isinstance(waiver.get("expires_on"), str)
            else None
        )
        if expires is None or expires < today:
            continue
        active_waivers.append(waiver)

    def covered_by_waivers(path: str) -> bool:
        return any(
            any(path_matches(path, prefix) for prefix in waiver.get("paths") or [])
            for waiver in active_waivers
        )

    protected_uncovered, semantic_uncovered = [], []
    for path in governed_changed:
        if any(path_matches(path, protected) for protected in PROTECTED_PATHS):
            if not (covered_by_delta(path) or covered_by_records(path)):
                protected_uncovered.append(path)
            continue
        if covered_by_records(path) or covered_by_delta(path) or covered_by_waivers(path):
            continue
        semantic_uncovered.append(path)

    for path in protected_uncovered:
        ctx.emit(
            "SYNC-PROTECTED-PATH",
            path,
            "governance-core path changed without an eligible governance protocol "
            "delta; protected paths are never waivable",
        )
    if semantic_uncovered:
        preview = ", ".join(semantic_uncovered[:8]) + (
            " ..." if len(semantic_uncovered) > 8 else ""
        )
        ctx.emit(
            "SYNC-SEMANTIC-MISSING",
            CONFIG_RELPATH,
            f"{len(semantic_uncovered)} governed path(s) changed without a matching "
            f"semantic inventory record change (node anchor, interaction source/affected "
            f"path, debt affected path, or new protocol delta): {preview}",
        )

    # Phase 4 reporting hygiene: flag unused active waivers and abnormal overlap.
    for waiver in active_waivers:
        scopes = waiver.get("paths") or []
        if not any(
            any(path_matches(path, prefix) for prefix in scopes) for path in governed_changed
        ):
            ctx.warn(
                "WVR-UNUSED",
                WAIVERS_RELPATH,
                f"active waiver {waiver.get('waiver_id')!r} matches no governed changed "
                f"path in this comparison",
            )
    for i in range(len(active_waivers)):
        for j in range(i + 1, len(active_waivers)):
            a, b = active_waivers[i], active_waivers[j]
            overlap = [
                p
                for p in (a.get("paths") or [])
                if any(path_matches(p, q) or path_matches(q, p) for q in (b.get("paths") or []))
            ]
            if overlap:
                ctx.warn(
                    "WVR-OVERLAP",
                    WAIVERS_RELPATH,
                    f"active waivers {a.get('waiver_id')!r} and {b.get('waiver_id')!r} "
                    f"have overlapping scope {overlap[:3]}",
                )


# ---------------------------------------------------------------------------
# PASS evidence authenticity (Phase 5)
# ---------------------------------------------------------------------------


def _verify_pass_evidence(ctx: GovernanceContext, root: str, nodes) -> None:
    pass_nodes = [
        (idx, node)
        for idx, node in enumerate(nodes)
        if isinstance(node, dict) and node.get("status") == "PASS"
    ]
    if not pass_nodes:
        return

    probe = _git(root, "rev-parse", "--git-dir")
    is_repo = probe.returncode == 0
    for idx, node in pass_nodes:
        pointer = f"{INVENTORY_RELPATH}#/nodes/{idx}"
        node_id = node.get("id", f"index-{idx}")
        if not is_repo:
            ctx.emit(
                "EVIDENCE-UNVERIFIABLE",
                pointer,
                f"node {node_id}: PASS claims cannot be verified outside a git "
                f"repository; fail closed",
            )
            continue
        _verify_one_pass_node(ctx, root, pointer, node)


def _verify_one_pass_node(ctx: GovernanceContext, root: str, pointer: str, node: dict) -> None:
    node_id = node.get("id")
    evidence = node.get("evidence_sha")
    evidence_paths = node.get("evidence_paths") or []
    if not evidence_paths:
        ctx.emit(
            "EVIDENCE-PATH-MISSING",
            f"{pointer}/evidence_paths",
            f"node {node_id}: PASS requires evidence_paths listing the committed "
            f"evidence artifacts",
        )
        return
    if evidence == "0" * 40 or evidence == "0" * 64:
        ctx.emit(
            "EVIDENCE-SHA-INVALID",
            f"{pointer}/evidence_sha",
            f"node {node_id}: all-zero evidence SHA is not a valid evidence identity",
        )
        return

    if isinstance(evidence, str) and COMMIT_SHA_RE.match(evidence):
        commit = evidence
    else:
        commit = node.get("evidence_commit")
        if not (isinstance(commit, str) and COMMIT_SHA_RE.match(commit)):
            ctx.emit(
                "EVIDENCE-COMMIT-MISSING",
                f"{pointer}/evidence_commit",
                f"node {node_id}: 64-hex evidence digests must bind to a commit via "
                f"evidence_commit",
            )
            return

    kind = _git(root, "cat-file", "-t", commit)
    if kind.returncode != 0 or kind.stdout.strip() != "commit":
        ctx.emit(
            "EVIDENCE-COMMIT-MISSING",
            f"{pointer}/evidence_sha",
            f"node {node_id}: evidence commit {commit} does not exist in this repository",
        )
        return
    contains = _git(root, "branch", "-a", "--contains", commit)
    tags = _git(root, "tag", "--contains", commit)
    if not contains.stdout.strip() and not tags.stdout.strip():
        ctx.emit(
            "EVIDENCE-COMMIT-UNREACHABLE",
            f"{pointer}/evidence_sha",
            f"node {node_id}: evidence commit {commit} is not reachable from any "
            f"fetched branch or tag",
        )
        return
    for relpath in evidence_paths:
        exists = _git(root, "cat-file", "-e", f"{commit}:{relpath}")
        if exists.returncode != 0:
            ctx.emit(
                "EVIDENCE-PATH-MISSING",
                f"{pointer}/evidence_paths",
                f"node {node_id}: evidence path {relpath!r} does not exist at commit "
                f"{commit[:12]}",
            )
    if isinstance(evidence, str) and len(evidence) == 64:
        blob = _git_raw(root, "show", f"{commit}:{evidence_paths[0]}")
        if blob.returncode == 0:
            digest = hashlib.sha256(blob.stdout).hexdigest()
            if digest != evidence:
                ctx.emit(
                    "EVIDENCE-BLOB-MISMATCH",
                    f"{pointer}/evidence_sha",
                    f"node {node_id}: evidence digest does not match the blob bytes of "
                    f"{evidence_paths[0]!r} at {commit[:12]}",
                )


# ---------------------------------------------------------------------------
# Summaries and gates
# ---------------------------------------------------------------------------


def compute_coverage(nodes, interactions) -> dict:
    by_status = {status: 0 for status in STATUSES}
    by_risk = {risk: {s: 0 for s in STATUSES} for risk in RISKS}
    oracle_complete = 0
    mutation_covered = 0
    p0p1_total = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        status = node.get("status")
        risk = node.get("risk")
        if status in by_status:
            by_status[status] += 1
        if risk in by_risk and status in by_risk[risk]:
            by_risk[risk][status] += 1
        if all(not blank(node.get(field)) for field in ORACLE_FIELDS):
            oracle_complete += 1
        if risk in ("P0", "P1"):
            p0p1_total += 1
            mutation = node.get("mutation_id")
            if isinstance(mutation, str) and mutation.strip().upper() not in MUTATION_SENTINELS:
                mutation_covered += 1

    total = len([n for n in nodes if isinstance(n, dict)])
    # BLOCKED is never a passing state: the pass rate denominator excludes only
    # NOT_APPLICABLE nodes, so BLOCKED and NOT_RUN both count against coverage.
    denominator = max(total - by_status["NOT_APPLICABLE"], 0)
    registry_ids = [
        i.get("interaction_id")
        for i in interactions
        if isinstance(i, dict) and i.get("interaction_id")
    ]
    by_interaction = {rid: 0 for rid in registry_ids}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for ref in node.get("interaction_ids") or []:
            if ref in by_interaction:
                by_interaction[ref] += 1

    return {
        "total_nodes": total,
        "by_status": by_status,
        "by_risk": by_risk,
        "pass_rate": round(by_status["PASS"] / denominator, 4) if denominator else 0.0,
        "pass_rate_note": "PASS / (total - NOT_APPLICABLE); BLOCKED and NOT_RUN never count as PASS",
        "oracle_completeness": round(oracle_complete / total, 4) if total else 0.0,
        "p0_p1_mutation_coverage": {"covered": mutation_covered, "total": p0p1_total},
        "by_interaction": by_interaction,
    }


def compute_debt_summary(debts) -> dict:
    entries = []
    counts = {status: 0 for status in DEBT_STATUSES}
    by_risk_open = {risk: 0 for risk in RISKS}
    release_blocked = 0
    for debt in debts:
        if not isinstance(debt, dict):
            continue
        status = debt.get("status")
        if status in counts:
            counts[status] += 1
        if status in ("BLOCKED", "NOT_COVERED"):
            if debt.get("risk") in by_risk_open:
                by_risk_open[debt["risk"]] += 1
            if debt.get("release_blocked"):
                release_blocked += 1
            entries.append(
                {
                    "debt_id": debt.get("debt_id"),
                    "risk": debt.get("risk"),
                    "status": status,
                    "owner": debt.get("owner"),
                    "target_milestone": debt.get("target_milestone"),
                    "release_blocked": bool(debt.get("release_blocked")),
                    "blocker_class": debt.get("blocker_class"),
                }
            )
    return {
        "counts": counts,
        "open_by_risk": by_risk_open,
        "release_blocking": release_blocked,
        "open_entries": entries,
        "note": "open debt (BLOCKED/NOT_COVERED) is excluded from every PASS figure above",
    }


def render_markdown(report: dict) -> str:
    cov, debt, gates = report["coverage"], report["debt"], report["gates"]
    blockers = gates["release_blockers"]
    lines = [
        "# Harness Governance Gate (HE2-R1)",
        "",
        f"**STRUCTURAL_GATE:** {gates['structural_gate']} — "
        f"{len(report['violations'])} violation(s), {len(report['warnings'])} warning(s) "
        f"(validator {report['validator_version']}, mode {report['mode']}, "
        f"date {report['today']})",
        f"**RELEASE_GATE:** {gates['release_gate']}"
        + (
            f" — open P0/P1 release-blocking debt: "
            f"{', '.join(f'`{b}`' for b in blockers)}"
            if blockers
            else " — no open P0/P1 release-blocking debt"
        ),
        "",
        "Structural GREEN is not a release statement; BLOCKED never counts as PASS.",
        "",
        "## Coverage summary",
        "",
        "| Status | Nodes |",
        "|---|---:|",
    ]
    lines += [f"| {status} | {cov['by_status'][status]} |" for status in STATUSES]
    lines += [
        "",
        f"- Pass rate: {cov['pass_rate']:.1%} — {cov['pass_rate_note']}.",
        f"- Oracle completeness: {cov['oracle_completeness']:.1%} of nodes define all "
        f"five oracles explicitly.",
        f"- P0/P1 mutation coverage: {cov['p0_p1_mutation_coverage']['covered']}/"
        f"{cov['p0_p1_mutation_coverage']['total']} nodes carry a mutation or "
        f"counterexample ID.",
        "",
        "| Interaction | Inventoried nodes |",
        "|---|---:|",
    ]
    lines += [f"| `{rid}` | {count} |" for rid, count in cov["by_interaction"].items()]
    lines += [
        "",
        "## Debt summary",
        "",
        f"- Open debt: {debt['counts']['BLOCKED']} BLOCKED, "
        f"{debt['counts']['NOT_COVERED']} NOT_COVERED "
        f"({debt['release_blocking']} release-blocking).",
        f"- {debt['note']}.",
        "",
        "| Debt | Risk | Status | Owner | Milestone | Blocks release |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| `{e['debt_id']}` | {e['risk']} | {e['status']} | {e['owner']} | "
        f"{e['target_milestone']} | {'yes' if e['release_blocked'] else 'no'} |"
        for e in debt["open_entries"]
    ]
    if report["violations"]:
        lines += ["", "## Violations", ""]
        lines += [
            f"- `{v['code']}` — `{v['path']}` — {v['message']}" for v in report["violations"]
        ]
    if report["warnings"]:
        lines += ["", "## Warnings", ""]
        lines += [f"- `{w['code']}` — `{w['path']}` — {w['message']}" for w in report["warnings"]]
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    baseline = parser.add_mutually_exclusive_group()
    baseline.add_argument(
        "--baseline-ref",
        help="git ref (e.g. origin/product-dev-recovered) to diff against",
    )
    baseline.add_argument(
        "--baseline-dir",
        help="directory tree to diff against (used by the deterministic tests)",
    )
    parser.add_argument(
        "--base-sha",
        help="comparison base commit SHA for delta base-binding when --baseline-dir is used",
    )
    parser.add_argument(
        "--mode",
        choices=["structural", "release"],
        default="structural",
        help="structural: enforce document/semantic rules (PR gate); release: also "
        "require no open P0/P1 release-blocking debt",
    )
    parser.add_argument(
        "--today",
        default=_dt.date.today().isoformat(),
        help="reference date for waiver expiry (YYYY-MM-DD)",
    )
    parser.add_argument("--report-json", help="write the machine-readable report here")
    parser.add_argument("--markdown-summary", help="write the markdown summary here")
    parser.add_argument("--quiet", action="store_true", help="only print violations")
    args = parser.parse_args(argv)

    today = parse_date(args.today)
    if today is None:
        print(f"error: --today must be YYYY-MM-DD, got {args.today!r}", file=sys.stderr)
        return 2
    if not os.path.isdir(os.path.join(args.root, GOV_DIR)):
        print(
            f"error: {GOV_DIR}/ not found under root {args.root!r}; run from the "
            f"repository root",
            file=sys.stderr,
        )
        return 2

    report = validate_workspace(args.root, today, args)

    if args.report_json:
        os.makedirs(os.path.dirname(os.path.abspath(args.report_json)), exist_ok=True)
        with open(args.report_json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=False)
            fh.write("\n")
    if args.markdown_summary:
        os.makedirs(os.path.dirname(os.path.abspath(args.markdown_summary)), exist_ok=True)
        with open(args.markdown_summary, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(report))

    gates = report["gates"]
    if not args.quiet:
        print(
            f"HE2-R1 harness governance: structural={gates['structural_gate']} "
            f"release={gates['release_gate']} (mode {args.mode})"
        )
        print(
            f"nodes={report['coverage']['total_nodes']} "
            f"pass={report['coverage']['by_status']['PASS']} "
            f"blocked={report['coverage']['by_status']['BLOCKED']} "
            f"not_run={report['coverage']['by_status']['NOT_RUN']} "
            f"open_debt="
            f"{report['debt']['counts']['BLOCKED'] + report['debt']['counts']['NOT_COVERED']}"
        )
    for violation in report["violations"]:
        print(f"RED  [{violation['code']}] {violation['path']}: {violation['message']}")
    for warning in report["warnings"]:
        print(f"WARN [{warning['code']}] {warning['path']}: {warning['message']}")

    if report["violations"]:
        return 1
    if args.mode == "release" and gates["release_gate"] == "BLOCKED":
        print(
            "RELEASE_BLOCKED: open P0/P1 release-blocking debt "
            + ", ".join(f"'{b}'" for b in gates["release_blockers"]),
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
