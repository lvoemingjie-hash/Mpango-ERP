#!/usr/bin/env python3
"""HE2 machine-enforced harness governance validator for Mpango ERP.

Implements DC-12R1-MVP-L1-HE2 on top of the HE1 standard
(docs/ai/HARNESS_ENGINEERING_GOVERNANCE_STANDARD.md):

  * validates the machine-parseable inventory, coverage-debt,
    critical-interaction, waiver, and protocol-delta documents against
    their JSON schemas (a stdlib-only subset checker);
  * enforces the semantic rules: duplicate IDs, blank or non-exact
    oracle sentinels, unknown statuses, P0/P1 nodes without a mutation,
    BLOCKED nodes without an owner or debt, PASS without evidence SHA;
  * blocks silent inventory drift versus a baseline (deletions, renames,
    reorders) unless a reviewed protocol delta exists;
  * requires inventory co-change (or an active, unexpired waiver) when
    governed product/test/harness paths change;
  * emits a coverage summary and a debt summary in which BLOCKED and
    NOT_COVERED never count as PASS.

Python 3.11+, standard library only. Exit codes: 0 = GREEN, 1 = RED
(governance violations), 2 = usage/environment error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys

VALIDATOR_VERSION = "1.0.0"

GOV_DIR = "harness-governance"
CONFIG_RELPATH = f"{GOV_DIR}/governed-paths.json"
INVENTORY_RELPATH = f"{GOV_DIR}/inventory/inventory.json"
DEBT_RELPATH = f"{GOV_DIR}/inventory/coverage-debt.json"
REGISTRY_RELPATH = f"{GOV_DIR}/inventory/critical-interactions.json"
WAIVERS_RELPATH = f"{GOV_DIR}/inventory/waivers.json"
DELTAS_RELPATH = f"{GOV_DIR}/inventory/protocol-deltas.json"
SCHEMA_DIR_RELPATH = f"{GOV_DIR}/schemas"

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
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Paths ignored when comparing two workspace trees in --baseline-dir mode.
FS_COMPARE_IGNORE = {".git", "__pycache__", "node_modules", ".pytest_cache", ".venv"}


class Violation:
    __slots__ = ("code", "path", "message")

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message

    def as_dict(self) -> dict:
        return {"code": self.code, "path": self.path, "message": self.message}


# ---------------------------------------------------------------------------
# Mini JSON Schema (draft-07 subset) checker: type, enum, required, pattern,
# minLength, minItems, properties, items, additionalProperties, $ref.
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
}


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


def check_against_schema(instance, schema: dict, path: str, root_schema: dict, emit) -> None:
    """Validate *instance* against a draft-07 subset schema, emitting violations."""

    def resolve(sub: dict) -> dict:
        ref = sub.get("$ref")
        if not ref:
            return sub
        name = ref.split("/")[-1]
        return root_schema.get("definitions", {}).get(name, sub)

    schema = resolve(schema)
    if not isinstance(schema, dict):
        return

    type_name = schema.get("type")
    if type_name and not _type_ok(instance, type_name):
        emit("SCHEMA-TYPE", path, f"expected {type_name}, got {type(instance).__name__}")
        return

    if "enum" in schema and instance not in schema["enum"]:
        emit(
            "SCHEMA-ENUM",
            path,
            f"value {instance!r} is not one of {schema['enum']!r}",
        )

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


def load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, f"file not found: {path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


# ---------------------------------------------------------------------------
# Workspace validation
# ---------------------------------------------------------------------------


class GovernanceContext:
    def __init__(self):
        self.violations: list[Violation] = []
        self.warnings: list[Violation] = []

    def emit(self, code: str, path: str, message: str) -> None:
        self.violations.append(Violation(code, path, message))

    def warn(self, code: str, path: str, message: str) -> None:
        self.warnings.append(Violation(code, path, message))


def _git(root: str, *args: str):
    proc = subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc


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


def resolve_baseline(root: str, args) -> dict:
    """Return {'mode','changed','inventory','governance_present'} for the baseline."""

    if not args.baseline_ref and not args.baseline_dir:
        return {"mode": "none", "changed": set(), "inventory": None, "governance_present": False}

    if args.baseline_dir:
        inv, _ = load_json(os.path.join(args.baseline_dir, INVENTORY_RELPATH))
        return {
            "mode": "dir",
            "changed": fs_changed_paths(root, args.baseline_dir),
            "inventory": inv,
            "governance_present": os.path.isfile(
                os.path.join(args.baseline_dir, CONFIG_RELPATH)
            ),
        }

    ref = args.baseline_ref
    probe = _git(root, "cat-file", "-e", f"{ref}:{CONFIG_RELPATH}")
    show = _git(root, "show", f"{ref}:{INVENTORY_RELPATH}")
    diff = _git(root, "diff", "--name-only", ref, "HEAD")
    if diff.returncode != 0:
        return {
            "mode": "git-error",
            "changed": set(),
            "inventory": None,
            "governance_present": False,
            "error": diff.stderr.strip() or f"git diff failed for ref {ref}",
        }
    inventory = None
    if show.returncode == 0:
        try:
            inventory = json.loads(show.stdout)
        except json.JSONDecodeError:
            inventory = None
    changed = {line.strip() for line in diff.stdout.splitlines() if line.strip()}
    return {
        "mode": "git",
        "ref": ref,
        "changed": changed,
        "inventory": inventory,
        "governance_present": probe.returncode == 0,
    }


def validate_workspace(root: str, today: _dt.date, args) -> dict:
    ctx = GovernanceContext()

    root = os.path.abspath(root)
    config, err = load_json(os.path.join(root, CONFIG_RELPATH))
    if err or not isinstance(config, dict):
        ctx.emit("CONFIG-ERROR", CONFIG_RELPATH, err or "governed-paths.json must be an object")
        config = {}

    governed_prefixes = config.get("governed_prefixes") or []
    inventory_sync_paths = config.get("inventory_sync_paths") or []
    required_categories = config.get("required_interaction_categories") or []
    if not isinstance(governed_prefixes, list) or not all(
        isinstance(p, str) for p in governed_prefixes
    ):
        ctx.emit("CONFIG-ERROR", CONFIG_RELPATH, "governed_prefixes must be a list of strings")
        governed_prefixes = []
    if not isinstance(inventory_sync_paths, list):
        ctx.emit("CONFIG-ERROR", CONFIG_RELPATH, "inventory_sync_paths must be a list")
        inventory_sync_paths = []
    if not isinstance(required_categories, list):
        ctx.emit("CONFIG-ERROR", CONFIG_RELPATH, "required_interaction_categories must be a list")
        required_categories = []

    schemas = {}
    docs = {}
    doc_specs = [
        ("inventory", INVENTORY_RELPATH, INVENTORY_SCHEMA),
        ("debt", DEBT_RELPATH, DEBT_SCHEMA),
        ("registry", REGISTRY_RELPATH, REGISTRY_SCHEMA),
        ("waivers", WAIVERS_RELPATH, WAIVERS_SCHEMA),
        ("deltas", DELTAS_RELPATH, DELTAS_SCHEMA),
    ]
    for key, relpath, schema_file in doc_specs:
        schema, serr = load_json(os.path.join(root, SCHEMA_DIR_RELPATH, schema_file))
        if serr:
            ctx.emit("LOAD-ERROR", f"{SCHEMA_DIR_RELPATH}/{schema_file}", serr)
            continue
        schemas[key] = schema
        doc, derr = load_json(os.path.join(root, relpath))
        if derr:
            ctx.emit("LOAD-ERROR", relpath, derr)
            continue
        docs[key] = doc
        check_against_schema(doc, schema, relpath, schema, ctx.emit)

    nodes = docs.get("inventory", {}).get("nodes", []) if isinstance(docs.get("inventory"), dict) else []
    debts = docs.get("debt", {}).get("debts", []) if isinstance(docs.get("debt"), dict) else []
    interactions = (
        docs.get("registry", {}).get("interactions", [])
        if isinstance(docs.get("registry"), dict)
        else []
    )
    waivers = docs.get("waivers", []) if isinstance(docs.get("waivers"), list) else []
    deltas = docs.get("deltas", []) if isinstance(docs.get("deltas"), list) else []

    _check_inventory_semantics(ctx, nodes, interactions, debts)
    _check_debt_semantics(ctx, debts, nodes)
    _check_registry_semantics(ctx, interactions, required_categories)
    _check_waivers(ctx, waivers, today)
    _check_anchor_existence(ctx, root, nodes, interactions)
    _check_ids_unique(ctx, nodes, debts, interactions, waivers, deltas)

    baseline = resolve_baseline(root, args)
    if baseline.get("mode") == "git-error":
        ctx.emit("CONFIG-ERROR", "baseline", baseline.get("error", "baseline resolution failed"))
    else:
        _check_drift(ctx, baseline, nodes, deltas)
        _check_sync(ctx, baseline, governed_prefixes, inventory_sync_paths, waivers, today)

    report = {
        "validator_version": VALIDATOR_VERSION,
        "root": root,
        "today": today.isoformat(),
        "baseline": {
            "mode": baseline.get("mode", "none"),
            "ref": baseline.get("ref"),
            "governance_present": baseline.get("governance_present", False),
        },
        "green": not ctx.violations,
        "violations": [v.as_dict() for v in ctx.violations],
        "warnings": [v.as_dict() for v in ctx.warnings],
        "coverage": compute_coverage(nodes, interactions),
        "debt": compute_debt_summary(debts),
    }
    return report


def _node(nodes, node_id):
    for node in nodes:
        if isinstance(node, dict) and node.get("id") == node_id:
            return node
    return None


def _check_inventory_semantics(ctx: GovernanceContext, nodes, interactions, debts) -> None:
    registry_ids = {
        i.get("interaction_id") for i in interactions if isinstance(i, dict)
    }
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
                for field in (
                    "owner",
                    "reason",
                    "closure_condition",
                    "target_milestone",
                )
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
    present = {
        i.get("category") for i in interactions if isinstance(i, dict)
    }
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
        expires = waiver.get("expires")
        parsed = parse_date(expires) if isinstance(expires, str) else None
        if parsed is None:
            ctx.emit(
                "WVR-INVALID-DATE",
                f"{pointer}/expires",
                f"waiver {waiver.get('waiver_id', idx)}: expires must be a valid ISO date",
            )
            continue
        if parsed < today:
            ctx.emit(
                "WVR-EXPIRED",
                f"{pointer}/expires",
                f"waiver {waiver.get('waiver_id', idx)} expired on {expires} "
                f"(today {today.isoformat()}); renew or remove it",
            )


def _check_anchor_existence(ctx: GovernanceContext, root: str, nodes, interactions) -> None:
    def check(pointer: str, anchors) -> None:
        for anchor in anchors or []:
            if not isinstance(anchor, str) or not anchor.strip():
                continue
            rel = anchor.split(":", 1)[0].strip()
            if not rel or os.path.exists(os.path.join(root, rel)):
                continue
            ctx.warn(
                "ANCHOR-MISSING",
                pointer,
                f"source anchor path does not exist in this tree: {rel!r}",
            )

    for idx, node in enumerate(nodes):
        if isinstance(node, dict):
            check(f"{INVENTORY_RELPATH}#/nodes/{idx}/source_anchors", node.get("source_anchors"))
    for idx, interaction in enumerate(interactions):
        if isinstance(interaction, dict):
            check(
                f"{REGISTRY_RELPATH}#/interactions/{idx}/source_anchors",
                interaction.get("source_anchors"),
            )


def _check_ids_unique(ctx: GovernanceContext, nodes, debts, interactions, waivers, deltas) -> None:
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


def _check_drift(ctx: GovernanceContext, baseline: dict, nodes, deltas) -> None:
    baseline_inventory = baseline.get("inventory")
    if not baseline.get("governance_present") or not isinstance(baseline_inventory, dict):
        return  # bootstrap: baseline predates the governance system

    baseline_nodes = baseline_inventory.get("nodes") or []
    baseline_ids = [n.get("id") for n in baseline_nodes if isinstance(n, dict)]
    head_ids = [n.get("id") for n in nodes if isinstance(n, dict)]
    head_set, baseline_set = set(head_ids), set(baseline_ids)

    removals, renames, reorders = set(), [], set()
    for delta in deltas:
        if not isinstance(delta, dict):
            continue
        kind = delta.get("kind")
        ids = delta.get("node_ids") or []
        if kind == "removal":
            removals.update(ids)
        elif kind == "rename":
            renames.append((delta.get("previous_id"), set(ids)))
        elif kind == "reorder":
            reorders.update(ids)

    renamed_away = {
        n.get("renamed_from")
        for n in nodes
        if isinstance(n, dict) and n.get("renamed_from")
    }

    for node_id in baseline_ids:
        if node_id in head_set or node_id in renamed_away:
            continue
        if node_id not in removals:
            ctx.emit(
                "DRIFT-SILENT-DELETE",
                INVENTORY_RELPATH,
                f"node {node_id!r} exists in the baseline inventory but was removed "
                f"without a 'removal' protocol delta",
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
        elif not any(prev == previous and node_id in ids for prev, ids in renames):
            ctx.emit(
                "DRIFT-RENAME-UNREGISTERED",
                INVENTORY_RELPATH,
                f"rename {previous!r} -> {node_id!r} has no 'rename' protocol delta",
            )

    drifted = sorted(moved_ids(baseline_ids, head_ids) - reorders)
    if drifted:
        ctx.emit(
            "DRIFT-REORDER",
            INVENTORY_RELPATH,
            f"node order changed without 'reorder' protocol deltas for: {', '.join(drifted)}",
        )

    baseline_status = {
        n.get("id"): n.get("status")
        for n in baseline_nodes
        if isinstance(n, dict)
    }
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id, status = node.get("id"), node.get("status")
        was = baseline_status.get(node_id)
        if was in ("PASS", "FAIL") and status != was:
            ctx.warn(
                "DRIFT-STATUS-RELABEL",
                INVENTORY_RELPATH,
                f"node {node_id!r} changed status {was} -> {status}; relabeling executed "
                f"evidence requires preserved history (standard section 16)",
            )


def _check_sync(
    ctx: GovernanceContext,
    baseline: dict,
    governed_prefixes: list,
    inventory_sync_paths: list,
    waivers,
    today: _dt.date,
) -> None:
    if not baseline.get("governance_present"):
        return  # bootstrap: the sync obligation starts once both sides have governance

    changed = baseline.get("changed") or set()
    governed_changed = sorted(
        path
        for path in changed
        if any(path_matches(path, prefix) for prefix in governed_prefixes)
    )
    if not governed_changed:
        return
    # Updating waivers.json is the alternative to an inventory update, not an
    # inventory update itself; only real inventory changes satisfy the rule.
    inventory_touched = any(
        any(path_matches(path, prefix) for prefix in inventory_sync_paths)
        and path != WAIVERS_RELPATH
        for path in changed
    )
    if inventory_touched:
        return

    active = []
    for waiver in waivers:
        if not isinstance(waiver, dict) or waiver.get("scope") != "inventory-sync":
            continue
        expires = waiver.get("expires")
        parsed = parse_date(expires) if isinstance(expires, str) else None
        if parsed is None or parsed < today:
            continue
        scoped_paths = waiver.get("paths") or []
        if scoped_paths and not any(
            path_matches(path, prefix) for path in governed_changed for prefix in scoped_paths
        ):
            continue
        active.append(waiver.get("waiver_id"))

    if not active:
        preview = ", ".join(governed_changed[:8]) + (" ..." if len(governed_changed) > 8 else "")
        ctx.emit(
            "SYNC-INVENTORY-MISSING",
            CONFIG_RELPATH,
            f"governed paths changed ({len(governed_changed)}: {preview}) without an "
            f"inventory update under {inventory_sync_paths} and without an active "
            f"inventory-sync waiver",
        )


# ---------------------------------------------------------------------------
# Summaries
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
    by_interaction = {
        rid: 0 for rid in registry_ids
    }
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
    counts = {"BLOCKED": 0, "NOT_COVERED": 0, "CLOSED": 0}
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
    cov, debt = report["coverage"], report["debt"]
    verdict = "GREEN" if report["green"] else "RED"
    lines = [
        "# Harness Governance Gate (HE2)",
        "",
        f"**Verdict:** {verdict} — "
        f"{len(report['violations'])} violation(s), {len(report['warnings'])} warning(s) "
        f"(validator {report['validator_version']}, date {report['today']})",
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
        f"- Oracle completeness: {cov['oracle_completeness']:.1%} of nodes define all five oracles explicitly.",
        f"- P0/P1 mutation coverage: {cov['p0_p1_mutation_coverage']['covered']}/"
        f"{cov['p0_p1_mutation_coverage']['total']} nodes carry a mutation or counterexample ID.",
        "",
        "| Interaction | Inventoried nodes |",
        "|---|---:|",
    ]
    lines += [f"| `{rid}` | {count} |" for rid, count in cov["by_interaction"].items()]
    lines += [
        "",
        "## Debt summary",
        "",
        f"- Open debt: {debt['counts']['BLOCKED']} BLOCKED, {debt['counts']['NOT_COVERED']} NOT_COVERED "
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
            f"error: {GOV_DIR}/ not found under root {args.root!r}; run from the repository root",
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

    if not args.quiet:
        print(f"HE2 harness governance: {'GREEN' if report['green'] else 'RED'}")
        print(
            f"nodes={report['coverage']['total_nodes']} "
            f"pass={report['coverage']['by_status']['PASS']} "
            f"blocked={report['coverage']['by_status']['BLOCKED']} "
            f"not_run={report['coverage']['by_status']['NOT_RUN']} "
            f"open_debt={report['debt']['counts']['BLOCKED'] + report['debt']['counts']['NOT_COVERED']}"
        )
    for violation in report["violations"]:
        print(f"RED  [{violation['code']}] {violation['path']}: {violation['message']}")
    for warning in report["warnings"]:
        print(f"WARN [{warning['code']}] {warning['path']}: {warning['message']}")

    return 0 if report["green"] else 1


if __name__ == "__main__":
    sys.exit(main())
