#!/usr/bin/env python3
"""Deterministic RED mutation gate for the HE2-R1 harness governance validator.

Every mutation tampers with a pristine copy of the real governance tree and
MUST turn the validator RED with the intended rule code. This proves the
gate is sensitive to the regressions it exists to catch (standard section
11): a gate that stays green when its own detection logic is attacked is
not evidence. GREEN controls prove the harness still passes when it should.

R1 adds mutations for every closed bypass (config self-protection, notes
sync, partial waiver coverage, evidence authenticity, delta replay,
unauthorized relabeling, fail-closed schema checking, release gating) and
a frozen-snapshot integrity check proving the gate never modifies the
candidate tree it validates (Phase 9.41).

Standard library only. Exit code 0 iff every mutation goes RED with the
expected codes, every control stays GREEN, and the candidate tree is
byte-identical before and after the run.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
GOV_DIR = REPO_ROOT / "harness-governance"
VALIDATOR = GOV_DIR / "validator" / "harness_governance_validator.py"

TODAY = "2026-08-25"
EXPIRED_DATE = "2026-08-24"
ACTIVE_DATE = "2026-08-26"
OPENED_DATE = "2026-08-20"


def _load(root, relpath):
    with open(os.path.join(root, relpath), encoding="utf-8") as fh:
        return json.load(fh)


def _save(root, relpath, doc):
    path = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _nodes(root):
    doc = _load(root, "harness-governance/inventory/inventory.json")
    return doc, doc["nodes"]


def _node(root, node_id):
    doc, nodes = _nodes(root)
    return doc, next(node for node in nodes if node["id"] == node_id)


def _copy_anchors(dst_root):
    """Copy every anchored product file so R1's RED anchor checks can pass."""

    anchors = set()
    for relpath in ("inventory/inventory.json", "inventory/critical-interactions.json"):
        with open(os.path.join(GOV_DIR, relpath), encoding="utf-8") as fh:
            doc = json.load(fh)
        for item in doc.get("nodes") or doc.get("interactions") or []:
            for anchor in item.get("source_anchors", []):
                path = anchor.split(":", 1)[0].strip()
                if path:
                    anchors.add(path)
    for relpath in sorted(anchors):
        src = os.path.join(REPO_ROOT, relpath)
        if os.path.isfile(src):
            dst = os.path.join(dst_root, relpath)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)


def make_workspace():
    head = tempfile.mkdtemp(prefix="he2r1-mut-head-")
    baseline = tempfile.mkdtemp(prefix="he2r1-mut-base-")
    for root in (head, baseline):
        shutil.copytree(GOV_DIR, os.path.join(root, "harness-governance"))
        _copy_anchors(root)
    return head, baseline


def touch(head, relpath, content="# governance mutation probe\n"):
    full = os.path.join(head, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    return relpath.replace(os.sep, "/")


def waiver_entry(waiver_id, paths, expires_on=ACTIVE_DATE):
    return {
        "waiver_id": waiver_id,
        "scope": "inventory-sync",
        "reason": "mutation gate waiver",
        "owner": "cto",
        "risk": "P2",
        "approval_ref": "mutation-gate",
        "opened_on": OPENED_DATE,
        "expires_on": expires_on,
        "paths": paths,
    }


def make_git_workspace():
    """Workspace whose head is a real git repo with committed evidence."""

    head, baseline = make_workspace()
    evidence = os.path.join(head, "evidence")
    os.makedirs(evidence, exist_ok=True)
    with open(os.path.join(evidence, "EVID-001.json"), "w", encoding="utf-8") as fh:
        json.dump({"node": "AUTH-INT-001", "result": "PASS", "artifact": "mutation gate"}, fh)
        fh.write("\n")

    def git(*args):
        subprocess.run(
            ["git", "-C", head, *args], check=True, capture_output=True, text=True
        )

    git("init", "-b", "main")
    git("config", "user.email", "mutation-gate@example.invalid")
    git("config", "user.name", "HE2-R1 mutation gate")
    git("add", "-A")
    git("commit", "-m", "evidence seed")
    sha = subprocess.run(
        ["git", "-C", head, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return head, baseline, sha


def run_validator(head, baseline, extra_args=()):
    report_path = os.path.join(head, "_mutation_report.json")
    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--root",
            head,
            "--baseline-dir",
            baseline,
            "--today",
            TODAY,
            "--report-json",
            report_path,
            "--quiet",
            *extra_args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = None
    if os.path.isfile(report_path):
        with open(report_path, encoding="utf-8") as fh:
            report = json.load(fh)
        os.remove(report_path)
    return proc.returncode, report


# ---------------------------------------------------------------------------
# Original HE2 mutations (M01-M14, kept; M08 updated to the R1 waiver shape)
# ---------------------------------------------------------------------------


def mut_duplicate_node_id():
    head, base = make_workspace()
    doc, nodes = _nodes(head)
    nodes[1]["id"] = nodes[0]["id"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_blank_oracle():
    head, base = make_workspace()
    doc, nodes = _nodes(head)
    nodes[0]["ui_oracle"] = "   "
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_unknown_status():
    head, base = make_workspace()
    doc, nodes = _nodes(head)
    nodes[0]["status"] = "PASSED"
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_p0_mutation_removed():
    head, base = make_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["mutation_id"] = ""
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_blocked_owner_removed():
    head, base = make_workspace()
    doc, node = _node(head, "MOBILE-DEV-001")
    node["blocked_owner"] = ""
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_silent_node_deletion():
    head, base = make_workspace()
    doc, nodes = _nodes(head)
    doc["nodes"] = [node for node in nodes if node["id"] != "TOKEN-INV-001"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_node_reorder():
    head, base = make_workspace()
    doc, nodes = _nodes(head)
    doc["nodes"] = nodes[1:] + nodes[:1]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_expired_waiver_on_unsynced_change():
    head, base = make_workspace()
    probe = touch(head, "backend/api/_mutation_probe.py")
    _save(
        head,
        "harness-governance/inventory/waivers.json",
        [waiver_entry("WVR-MUT-001", [probe], expires_on=EXPIRED_DATE)],
    )
    return head, base


def mut_pass_without_evidence():
    head, base = make_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["status"] = "PASS"
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_pass_with_bogus_evidence():
    head, base = make_workspace()
    doc, node = _node(head, "TENANT-ISO-001")
    node["status"] = "PASS"
    node["evidence_sha"] = "deadbeef"
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_debt_owner_blank():
    head, base = make_workspace()
    doc = _load(head, "harness-governance/inventory/coverage-debt.json")
    doc["debts"][0]["owner"] = "   "
    _save(head, "harness-governance/inventory/coverage-debt.json", doc)
    return head, base


def mut_required_interaction_removed():
    head, base = make_workspace()
    doc = _load(head, "harness-governance/inventory/critical-interactions.json")
    doc["interactions"] = [
        item for item in doc["interactions"] if item.get("category") != "tenant"
    ]
    _save(head, "harness-governance/inventory/critical-interactions.json", doc)
    return head, base


def mut_blocked_node_orphaned_from_debt():
    head, base = make_workspace()
    doc = _load(head, "harness-governance/inventory/coverage-debt.json")
    for debt in doc["debts"]:
        if debt["debt_id"] == "DEBT-MOBILE-REAL-DEVICE":
            debt["node_ids"] = []
    _save(head, "harness-governance/inventory/coverage-debt.json", doc)
    return head, base


def mut_unknown_interaction_reference():
    head, base = make_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["interaction_ids"] = ["CI-DOES-NOT-EXIST"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


# ---------------------------------------------------------------------------
# R1 mutations (N01-N15): every closed bypass must have a deterministic RED
# ---------------------------------------------------------------------------


def mut_empty_governed_prefixes():
    head, base = make_workspace()
    config = _load(head, "harness-governance/governed-paths.json")
    config["governed_prefixes"] = []
    _save(head, "harness-governance/governed-paths.json", config)
    return head, base


def mut_minimum_prefix_removed():
    head, base = make_workspace()
    config = _load(head, "harness-governance/governed-paths.json")
    config["governed_prefixes"] = [
        p for p in config["governed_prefixes"] if p != "backend/"
    ]
    _save(head, "harness-governance/governed-paths.json", config)
    return head, base


def mut_notes_only_sync():
    head, base = make_workspace()
    touch(head, "backend/api/_mutation_probe.py")
    doc, nodes = _nodes(head)
    doc["notes"] = doc.get("notes", "") + " [probe: touched the inventory file]"
    nodes[0]["notes"] = "note-only change must not satisfy sync"
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_partial_path_coverage():
    head, base = make_workspace()
    backend_probe = touch(head, "backend/api/_probe_a.py")
    touch(head, "frontend/src/_probe_b.tsx")
    doc, node = _node(head, "AUTH-INT-001")
    node["source_anchors"] = [
        backend_probe,
        *[a for a in node["source_anchors"] if a.startswith("frontend/src/services/api.ts")],
    ]
    node["ui_oracle"] = "updated assertion anchored only to the backend probe"
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_waiver_paths_missing():
    head, base = make_workspace()
    touch(head, "backend/api/_mutation_probe.py")
    entry = waiver_entry("WVR-MUT-002", ["backend/api/_mutation_probe.py"])
    del entry["paths"]
    _save(head, "harness-governance/inventory/waivers.json", [entry])
    return head, base


def mut_waiver_partial_coverage():
    head, base = make_workspace()
    touch(head, "backend/api/_probe_a.py")
    touch(head, "frontend/src/_probe_b.tsx")
    _save(
        head,
        "harness-governance/inventory/waivers.json",
        [waiver_entry("WVR-MUT-003", ["backend/api/_probe_a.py"])],
    )
    return head, base


def mut_evidence_all_zero_sha():
    head, base, _sha = make_git_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["status"] = "PASS"
    node["evidence_sha"] = "0" * 40
    node["evidence_paths"] = ["evidence/EVID-001.json"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_evidence_nonexistent_commit():
    head, base, _sha = make_git_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["status"] = "PASS"
    node["evidence_sha"] = "1" * 40
    node["evidence_paths"] = ["evidence/EVID-001.json"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_evidence_unreachable_commit():
    head, base, _sha = make_git_workspace()
    dangling = subprocess.run(
        ["git", "-C", head, "commit-tree", "HEAD^{tree}", "-m", "dangling evidence"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    doc, node = _node(head, "AUTH-INT-001")
    node["status"] = "PASS"
    node["evidence_sha"] = dangling
    node["evidence_paths"] = ["evidence/EVID-001.json"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_evidence_path_missing():
    head, base, sha = make_git_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["status"] = "PASS"
    node["evidence_sha"] = sha
    node["evidence_paths"] = ["evidence/DOES-NOT-EXIST.json"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_evidence_blob_digest_mismatch():
    head, base, sha = make_git_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["status"] = "PASS"
    node["evidence_sha"] = hashlib.sha256(b"not the committed bytes").hexdigest()
    node["evidence_commit"] = sha
    node["evidence_paths"] = ["evidence/EVID-001.json"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_historical_reorder_replay():
    head, base = make_workspace()
    replay_delta = {
        "delta_id": "PD-MUT-REPLAY",
        "kind": "reorder",
        "affected_ids": ["AUTH-INT-001"],
        "affected_paths": [],
        "base_sha": "a" * 40,
        "owner": "cto",
        "reason": "old reorder authorization that must be single-use",
        "approval_ref": "mutation-gate",
    }
    # The identical delta exists on BOTH sides: relying on it again is replay.
    _save(base, "harness-governance/inventory/protocol-deltas.json", [replay_delta])
    head_deltas = _load(head, "harness-governance/inventory/protocol-deltas.json")
    _save(
        head,
        "harness-governance/inventory/protocol-deltas.json",
        head_deltas + [replay_delta],
    )
    doc, nodes = _nodes(head)
    doc["nodes"] = [nodes[1], nodes[0], *nodes[2:]]  # AUTH-INT-001 moved
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_unauthorized_status_transition():
    head, base = make_workspace()
    base_doc = _load(base, "harness-governance/inventory/inventory.json")
    for node in base_doc["nodes"]:
        if node["id"] == "AUTH-INT-001":
            node["status"] = "PASS"
    _save(base, "harness-governance/inventory/inventory.json", base_doc)
    # head stays pristine (NOT_RUN): PASS -> NOT_RUN without a reclassify delta
    return head, base


def mut_unknown_schema_keyword():
    head, base = make_workspace()
    schema = _load(head, "harness-governance/schemas/inventory.schema.json")
    schema["definitions"]["node"]["properties"]["id"]["minimum"] = 1
    _save(head, "harness-governance/schemas/inventory.schema.json", schema)
    return head, base


def mut_invalid_schema_ref():
    head, base = make_workspace()
    schema = _load(head, "harness-governance/schemas/inventory.schema.json")
    schema["properties"]["nodes"]["items"] = {"$ref": "#/definitions/nonexistent"}
    _save(head, "harness-governance/schemas/inventory.schema.json", schema)
    return head, base


def mut_binary_blob_text_digest():
    """R2: binary blob with invalid UTF-8 + null bytes; digest computed via
    text decode/re-encode (the old buggy path) must mismatch the raw blob."""
    head, base, sha = make_git_workspace()
    # Write a binary blob that breaks UTF-8 decode
    binary = b"\x00\xff\xfe\x80\x01binary\x00\x00\xff"
    blob_path = os.path.join(head, "evidence", "BLOB-001.bin")
    with open(blob_path, "wb") as fh:
        fh.write(binary)
    subprocess.run(["git", "-C", head, "add", "evidence/BLOB-001.bin"], check=True, capture_output=True)
    subprocess.run(["git", "-C", head, "commit", "-m", "binary blob"], check=True, capture_output=True)
    sha = subprocess.run(
        ["git", "-C", head, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    # Compute digest the WRONG way (text decode/re-encode)
    text_digest = hashlib.sha256(
        binary.decode("utf-8", errors="replace").encode("utf-8", "surrogatepass")
    ).hexdigest()
    doc, node = _node(head, "AUTH-INT-001")
    node["status"] = "PASS"
    node["evidence_sha"] = text_digest
    node["evidence_commit"] = sha
    node["evidence_paths"] = ["evidence/BLOB-001.bin"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_secrets_baseline_modified():
    """R2: .secrets.baseline is now a protected path; modifying it without a
    governance delta must be SYNC-PROTECTED-PATH."""
    head, base = make_workspace()
    # Modify .secrets.baseline (append a comment-like line)
    baseline_path = os.path.join(head, ".secrets.baseline")
    with open(baseline_path, "a", encoding="utf-8") as fh:
        fh.write('  "# probe modification": []\n')
    return head, base


def mut_delete_r2_hop_delta():
    """R3: removing the R2-hop delta + changing a protected path → no eligible
    governance delta covers the 5a380586 hop → SYNC-PROTECTED-PATH."""
    head, base = make_workspace()
    deltas = _load(head, "harness-governance/inventory/protocol-deltas.json")
    _save(
        head,
        "harness-governance/inventory/protocol-deltas.json",
        [d for d in deltas if d.get("delta_id") != "PD-2026-08-25-HE2-R2-HOP"],
    )
    # Also modify a protected path so the sync check actually evaluates it
    baseline_path = os.path.join(head, ".secrets.baseline")
    with open(baseline_path, "a", encoding="utf-8") as fh:
        fh.write('  "# r2-hop-delta-deleted-probe": []\n')
    return head, base


def mut_delete_cumulative_delta():
    """R3: removing the cumulative delta + changing a protected path → no eligible
    governance delta covers the 94b0c300 hop → SYNC-PROTECTED-PATH."""
    head, base = make_workspace()
    deltas = _load(head, "harness-governance/inventory/protocol-deltas.json")
    _save(
        head,
        "harness-governance/inventory/protocol-deltas.json",
        [d for d in deltas if d.get("delta_id") != "PD-2026-08-25-HE2-CUMULATIVE"],
    )
    baseline_path = os.path.join(head, ".secrets.baseline")
    with open(baseline_path, "a", encoding="utf-8") as fh:
        fh.write('  "# cumulative-delta-deleted-probe": []\n')
    return head, base


def mut_scanner_hex_in_backend():
    """R3: governance hex key in a non-allowed backend JSON file must be RED."""
    head, base = make_workspace()
    probe = os.path.join(head, "backend", "api", "_probe.json")
    os.makedirs(os.path.dirname(probe), exist_ok=True)
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write('{\n  "base_sha": "' + "aabbccdd" * 5 + '"\n}\n')
    return head, base


def mut_scanner_py_ts_probes():
    """R3-R1 truth workspace: exact evidence_sha lines in a Python and a
    TypeScript probe. Against the candidate validator both must be RED
    (SCANNER-SCOPE-VIOLATION); against a validator weakened back to
    *.json-only scope they silently pass — which the gate must detect."""
    head, base = make_workspace()
    for relpath in ("backend/probe.py", "frontend/src/probe.ts"):
        full = os.path.join(head, *relpath.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write("# scanner scope probe\n")
            fh.write('  "evidence_sha": "' + "aabbccdd" * 5 + '",\n')
    return head, base


# R3-R1 validator mutations (N20/N21): these patch the CANDIDATE validator
# file itself, prove that the py/ts probes ESCAPE under the weakened scanner
# (the gate reports that as a failure — a regression that slipped through
# undetected), then restore the file byte-identically (sha256-verified) and
# re-prove the probes are caught again on the restored validator.

_N20_PATCH = (
    '        if rel in _SCANNER_ALLOWED_FILES:\n            continue\n',
    '        if not rel.endswith(".json"):\n            continue\n'
    '        if rel in _SCANNER_ALLOWED_FILES:\n            continue\n',
)

_N21_PATCH = (
    '    for rel in _scanner_candidate_files(root):\n',
    '    for rel in (r for r in _scanner_candidate_files(root) if r.endswith(".json")):\n',
)


# R3-R2: EOL-portable patch application. The patches above stay CANONICAL LF
# strings; at application time they are converted to the validator file's
# NATIVE checkout EOL so the gate works identically on LF and CRLF hosts.
# The candidate is never globally normalized — only the patch strings adapt.


def _detect_native_eol(data):
    """'\\n' for pure LF, '\\r\\n' for pure CRLF, None for mixed EOL."""
    lf = data.count(b"\n")
    cr = data.count(b"\r")
    crlf = data.count(b"\r\n")
    if cr == 0 and lf > 0:
        return "\n"
    if cr == crlf and lf == crlf and cr > 0:
        return "\r\n"
    return None


def _to_native_eol(text, native_eol):
    """Convert a canonical-LF patch string to the file's native EOL."""
    if native_eol == "\n":
        return text
    return text.replace("\n", "\r\n")


def _apply_validator_patch(original, patch):
    """Return (mutated_bytes, None) on success or (None, fail_category).

    Fail categories are fixed strings, never content:
      MIXED_EOL          — the validator blob mixes EOL styles; fail closed
                           WITHOUT modifying the file.
      PATCH-ANCHOR-NOT-UNIQUE — the anchor occurs 0 or >1 times; fail closed
                           WITHOUT modifying the file.
    """
    native_eol = _detect_native_eol(original)
    if native_eol is None:
        return None, "MIXED_EOL"
    old, new = (_to_native_eol(part, native_eol) for part in patch)
    text = original.decode("utf-8")
    if text.count(old) != 1:
        return None, "PATCH-ANCHOR-NOT-UNIQUE"
    return text.replace(old, new).encode("utf-8"), None


def _run_validator_mutation(name, patch, failures):
    original = VALIDATOR.read_bytes()
    mutated, fail_category = _apply_validator_patch(original, patch)
    if fail_category is not None:
        # Fail closed: the file was NOT modified and this is NOT a RED —
        # it is a gate-infrastructure failure that must be reported loudly.
        failures.append(f"{name}: {fail_category}")
        print(f"  {name:<40} FAIL CLOSED ({fail_category})")
        return
    try:
        VALIDATOR.write_bytes(mutated)
        head, base = mut_scanner_py_ts_probes()
        try:
            code, report = run_validator(head, base)
            codes = {v["code"] for v in (report or {}).get("violations", [])}
            if "SCANNER-SCOPE-VIOLATION" in codes:
                failures.append(
                    f"{name}: weakened validator still caught the py/ts probes — "
                    f"mutation is not a real weakening"
                )
                print(f"  {name:<40} ESCAPED (still caught)")
            else:
                print(f"  {name:<40} RED as intended (probes escaped the weakened scanner)")
        finally:
            shutil.rmtree(head, ignore_errors=True)
            shutil.rmtree(base, ignore_errors=True)
    finally:
        VALIDATOR.write_bytes(original)
    # R3-R2: full SHA-256 AND full bytes equality after restore.
    restored = VALIDATOR.read_bytes()
    if (
        hashlib.sha256(restored).digest() != hashlib.sha256(original).digest()
        or restored != original
    ):
        failures.append(f"{name}: validator blob NOT byte-identical after restore")
        print(f"  {name:<40} BLOB DRIFT after restore")
        return
    # GREEN re-proof on the restored candidate validator
    head, base = mut_scanner_py_ts_probes()
    try:
        code, report = run_validator(head, base)
        codes = {v["code"] for v in (report or {}).get("violations", [])}
        if "SCANNER-SCOPE-VIOLATION" not in codes or code != 1:
            failures.append(f"{name}: restored validator failed to catch the py/ts probes")
            print(f"  {name:<40} RESTORE GREEN-PROOF FAILED")
        else:
            print(f"  {name:<40} restored: blob identical, probes RED again")
    finally:
        shutil.rmtree(head, ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


VALIDATOR_MUTATIONS = [
    ("N20-restore-json-only-filter", _N20_PATCH),
    ("N21-drop-non-json-path-scan", _N21_PATCH),
]


def _run_probe_mutation(name, target_file, patch, probe_call, failures):
    """Patch the candidate runner/plugin, require the probe to report the
    gate WEAKENED, then restore byte-identically and re-probe (N20 pattern).
    Returns True when the mutation behaved as a detectable weakening."""
    original = target_file.read_bytes()
    mutated, fail_category = _apply_validator_patch(original, patch)
    if fail_category is not None:
        failures.append(f"{name}: {fail_category}")
        print(f"  {name:<40} FAIL CLOSED ({fail_category})")
        return False
    weak = False
    try:
        target_file.write_bytes(mutated)
        weak = probe_call() is False
        if weak:
            print(f"  {name:<40} RED as intended (probe escaped)")
        else:
            failures.append(
                f"{name}: probe still holds — mutation is not a real weakening"
            )
            print(f"  {name:<40} ESCAPED (still caught)")
    finally:
        target_file.write_bytes(original)
    restored = target_file.read_bytes()
    if (
        hashlib.sha256(restored).digest() != hashlib.sha256(original).digest()
        or restored != original
    ):
        failures.append(f"{name}: candidate blob NOT byte-identical after restore")
        print(f"  {name:<40} BLOB DRIFT after restore")
        return False
    if not probe_call():
        failures.append(f"{name}: restored candidate failed its probe")
        print(f"  {name:<40} RESTORE GREEN-PROOF FAILED")
        return False
    print(f"  {name:<40} restored: blob identical, probe holds again")
    return weak


# GREEN controls -------------------------------------------------------------


def control_pristine_green():
    return make_workspace()


def control_full_scoped_waiver():
    head, base = make_workspace()
    probe = touch(head, "backend/api/_mutation_probe.py")
    _save(
        head,
        "harness-governance/inventory/waivers.json",
        [waiver_entry("WVR-MUT-CTRL", [probe])],
    )
    return head, base


def control_semantic_mapping():
    head, base = make_workspace()
    probe = touch(head, "backend/api/_probe_c.py")
    doc, node = _node(head, "AUTH-INT-001")
    node["source_anchors"] = [*node["source_anchors"], probe]
    node["ui_oracle"] = "updated assertion covering the new probe path"
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def control_multi_waiver_union():
    head, base = make_workspace()
    probe_a = touch(head, "backend/api/_probe_a.py")
    probe_b = touch(head, "frontend/src/_probe_b.tsx")
    _save(
        head,
        "harness-governance/inventory/waivers.json",
        [
            waiver_entry("WVR-MUT-U1", [probe_a]),
            waiver_entry("WVR-MUT-U2", [probe_b]),
        ],
    )
    return head, base


def control_valid_committed_evidence():
    head, base, sha = make_git_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["status"] = "PASS"
    node["evidence_sha"] = sha
    node["evidence_paths"] = ["evidence/EVID-001.json"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


RED_MUTATIONS = [
    ("M01-duplicate-node-id", mut_duplicate_node_id, ["INV-DUP-ID"], ()),
    ("M02-blank-oracle", mut_blank_oracle, ["INV-ORACLE-EMPTY"], ()),
    ("M03-unknown-status", mut_unknown_status, ["SCHEMA-ENUM"], ()),
    ("M04-p0-mutation-removed", mut_p0_mutation_removed, ["INV-MUTATION-MISSING"], ()),
    ("M05-blocked-owner-removed", mut_blocked_owner_removed, ["INV-BLOCKED-OWNER"], ()),
    ("M06-silent-node-deletion", mut_silent_node_deletion, ["DRIFT-SILENT-DELETE"], ()),
    ("M07-node-reorder", mut_node_reorder, ["DRIFT-REORDER"], ()),
    (
        "M08-expired-waiver-on-unsynced-change",
        mut_expired_waiver_on_unsynced_change,
        ["WVR-EXPIRED", "SYNC-SEMANTIC-MISSING"],
        (),
    ),
    ("M09-pass-without-evidence", mut_pass_without_evidence, ["INV-PASS-EVIDENCE"], ()),
    ("M10-pass-with-bogus-evidence", mut_pass_with_bogus_evidence, ["INV-PASS-EVIDENCE"], ()),
    ("M11-debt-owner-blank", mut_debt_owner_blank, ["DEBT-INCOMPLETE"], ()),
    ("M12-required-interaction-removed", mut_required_interaction_removed, ["REG-CATEGORY-MISSING"], ()),
    (
        "M13-blocked-node-orphaned-from-debt",
        mut_blocked_node_orphaned_from_debt,
        ["INV-BLOCKED-DEBT"],
        (),
    ),
    ("M14-unknown-interaction-reference", mut_unknown_interaction_reference, ["REG-REF-UNKNOWN"], ()),
    ("N01-empty-governed-prefixes", mut_empty_governed_prefixes, ["CONFIG-PREFIXES-EMPTY", "CONFIG-MINIMUM-PREFIX"], ()),
    ("N02-minimum-prefix-removed", mut_minimum_prefix_removed, ["CONFIG-MINIMUM-PREFIX"], ()),
    ("N03-notes-only-sync", mut_notes_only_sync, ["SYNC-SEMANTIC-MISSING"], ()),
    ("N04-partial-path-coverage", mut_partial_path_coverage, ["SYNC-SEMANTIC-MISSING"], ()),
    ("N05-waiver-paths-missing", mut_waiver_paths_missing, ["SCHEMA-REQUIRED"], ()),
    ("N06-waiver-partial-coverage", mut_waiver_partial_coverage, ["SYNC-SEMANTIC-MISSING"], ()),
    ("N07-evidence-all-zero-sha", mut_evidence_all_zero_sha, ["EVIDENCE-SHA-INVALID"], ()),
    ("N08-evidence-nonexistent-commit", mut_evidence_nonexistent_commit, ["EVIDENCE-COMMIT-MISSING"], ()),
    ("N08b-evidence-unreachable-commit", mut_evidence_unreachable_commit, ["EVIDENCE-COMMIT-UNREACHABLE"], ()),
    ("N09-evidence-path-missing", mut_evidence_path_missing, ["EVIDENCE-PATH-MISSING"], ()),
    ("N09b-evidence-blob-digest-mismatch", mut_evidence_blob_digest_mismatch, ["EVIDENCE-BLOB-MISMATCH"], ()),
    ("N10-historical-reorder-replay", mut_historical_reorder_replay, ["DELTA-REPLAY", "DRIFT-REORDER"], ()),
    ("N11-unauthorized-status-transition", mut_unauthorized_status_transition, ["STATUS-UNAUTHORIZED"], ()),
    ("N12-unknown-schema-keyword", mut_unknown_schema_keyword, ["SCHEMA-UNKNOWN-KEYWORD"], ()),
    ("N13-invalid-schema-ref", mut_invalid_schema_ref, ["SCHEMA-BAD-REF"], ()),
    ("N15-binary-blob-text-digest", mut_binary_blob_text_digest, ["EVIDENCE-BLOB-MISMATCH"], ()),
    ("N16-secrets-baseline-modified", mut_secrets_baseline_modified, ["SYNC-PROTECTED-PATH"], ()),
    ("N17-delete-r2-hop-delta", mut_delete_r2_hop_delta, ["SYNC-PROTECTED-PATH"], ("--base-sha", "5a380586caab4f662d7e1dfbc7899cf5bd3bc300")),  # pragma: allowlist secret
    ("N18-delete-cumulative-delta", mut_delete_cumulative_delta, ["SYNC-PROTECTED-PATH"], ("--base-sha", "94b0c30034d04d1bad87f926a4b09e3dbbe3c6db")),  # pragma: allowlist secret
    ("N19-scanner-hex-in-backend", mut_scanner_hex_in_backend, ["SCANNER-SCOPE-VIOLATION"], ()),
]

# N14 is a mode-behavior proof rather than a tree tamper: structural GREEN
# with open P0/P1 release-blocking debt must NOT be reportable as a global
# GREEN in release mode (exit code 3, RELEASE_GATE=BLOCKED).
MODE_PROOFS = [
    ("N14-release-blocker-not-global-green", control_pristine_green, "--mode", "release"),
]

GREEN_CONTROLS = [
    ("C01-pristine-tree-green", control_pristine_green),
    ("C02-full-scoped-waiver", control_full_scoped_waiver),
    ("C03-semantic-record-mapping", control_semantic_mapping),
    ("C04-multi-waiver-union", control_multi_waiver_union),
    ("C05-valid-committed-evidence", control_valid_committed_evidence),
]

# HE2-ET1: execution-traps registry / authority-profile mutations (appended;
# the original 37 RED / 5 GREEN above are preserved untouched).
try:
    import et1_mutations as _et1

    def _et1_red(name, tamper, expected, extra):
        def factory():
            head, base = make_workspace()
            tamper(head, base)
            return head, base

        return (name, factory, expected, extra)

    def _et1_green(name, control):
        def factory():
            head, base = make_workspace()
            control(head, base)
            return head, base

        return (name, factory)

    RED_MUTATIONS = RED_MUTATIONS + [
        _et1_red(name, tamper, expected, extra)
        for name, tamper, expected, extra in _et1.ET1_MUTATIONS
    ]
    GREEN_CONTROLS = GREEN_CONTROLS + [
        _et1_green(name, control) for name, control in _et1.ET1_GREEN_CONTROLS
    ]
except ImportError:  # pragma: no cover - et1_mutations ships with the gate
    pass

# HE2-ET1-R1: end-to-end authority runner/plugin BEHAVIORAL mutations. Each
# patch weakens the candidate runner or plugin source; an in-process probe
# must then report the gate as WEAKENED (a behavior the pristine candidate
# rejects becomes accepted). Restores are sha256 + bytes verified like N20/N21.
try:
    import et1_e2e_mutations as _e2e_mut

    E2E_MUTATIONS_WIRED = [
        (name, REPO_ROOT / target_relpath, patch, probe_name)
        for name, target_relpath, patch, probe_name in _e2e_mut.E2E_MUTATIONS
    ]
except ImportError:  # pragma: no cover - et1_e2e_mutations ships with the gate
    E2E_MUTATIONS_WIRED = []

# HE2-ET1-R2: live Redis authority mutations (same patch-and-probe pattern).
try:
    import et1_r2_mutations as _r2_mut

    R2_MUTATIONS_WIRED = [
        (name, REPO_ROOT / target_relpath, patch, probe_name)
        for name, target_relpath, patch, probe_name in _r2_mut.R2_MUTATIONS
    ]
except ImportError:  # pragma: no cover - et1_r2_mutations ships with the gate
    R2_MUTATIONS_WIRED = []

# HE2-ET1-R2-R2: module-origin and cross-process byte-binding mutations.
try:
    import et1_r2r2_mutations as _r2r2_mut

    R2R2_MUTATIONS_WIRED = [
        (name, REPO_ROOT / target_relpath, patch, probe_name)
        for name, target_relpath, patch, probe_name in (
            _r2r2_mut.R2R2_MUTATIONS + _r2r2_mut.R2R2R1_MUTATIONS)
    ]
except ImportError:  # pragma: no cover - et1_r2r2_mutations ships with the gate
    R2R2_MUTATIONS_WIRED = []


def tree_digest():
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(GOV_DIR):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, GOV_DIR).replace(os.sep, "/")
            with open(full, "rb") as fh:
                digest.update(rel.encode("utf-8"))
                digest.update(fh.read())
    return digest.hexdigest()


def main() -> int:
    failures = []
    before = tree_digest()

    total_red = (len(RED_MUTATIONS) + len(MODE_PROOFS) + len(VALIDATOR_MUTATIONS)
                 + len(E2E_MUTATIONS_WIRED) + len(R2_MUTATIONS_WIRED)
                 + len(R2R2_MUTATIONS_WIRED))
    print(
        f"HE2-R1 RED mutation gate: {total_red} RED mutations "
        f"({len(RED_MUTATIONS)} tamper + {len(MODE_PROOFS)} mode proof + "
        f"{len(VALIDATOR_MUTATIONS)} validator-scope + {len(E2E_MUTATIONS_WIRED)} authority-e2e "
        f"+ {len(R2_MUTATIONS_WIRED)} redis-authority + {len(R2R2_MUTATIONS_WIRED)} module-binding), "
        f"{len(GREEN_CONTROLS)} GREEN controls"
    )
    print("-" * 78)

    for name, factory, expected_codes, extra in RED_MUTATIONS:
        result = factory()
        head, base = result[0], result[1]
        try:
            code, report = run_validator(head, base, extra)
            codes = {v["code"] for v in (report or {}).get("violations", [])}
            missing = [c for c in expected_codes if c not in codes]
            if code != 1:
                failures.append(f"{name}: validator stayed GREEN (exit {code})")
                status = "ESCAPED (green)"
            elif missing:
                failures.append(f"{name}: missing expected codes {missing}, got {sorted(codes)}")
                status = f"RED but wrong codes {sorted(codes)}"
            else:
                status = f"RED as intended ({', '.join(expected_codes)})"
            print(f"  {name:<40} {status}")
        finally:
            shutil.rmtree(head, ignore_errors=True)
            shutil.rmtree(base, ignore_errors=True)

    for name, patch in VALIDATOR_MUTATIONS:
        _run_validator_mutation(name, patch, failures)

    # HE2-ET1-R1 GREEN control: on the PRISTINE candidate every E2E probe
    # must hold (no weakness present). Then each mutation must weaken its
    # target probe, restore byte-identically, and leave the probe held again.
    if E2E_MUTATIONS_WIRED:
        pristine_held = all(_e2e_mut.run_probe(probe_name) for _, _, _, probe_name in E2E_MUTATIONS_WIRED)
        if pristine_held:
            print(f"  {'E2E-GC01-pristine-runner-all-probes-held':<40} GREEN as intended")
        else:
            failures.append("E2E-GC01: pristine candidate already fails an E2E probe")
            print(f"  {'E2E-GC01-pristine-runner-all-probes-held':<40} UNEXPECTED WEAK (pristine)")

    for name, target_file, patch, probe_name in E2E_MUTATIONS_WIRED:
        _run_probe_mutation(
            name, target_file, patch, (lambda pn=probe_name: _e2e_mut.run_probe(pn)), failures
        )

    # HE2-ET1-R2 GREEN control + live-Redis authority mutations.
    if R2_MUTATIONS_WIRED:
        pristine_r2 = all(_r2_mut.run_probe(probe_name) for _, _, _, probe_name in R2_MUTATIONS_WIRED)
        if pristine_r2:
            print(f"  {'RG-C01-pristine-redis-authority-held':<40} GREEN as intended")
        else:
            failures.append("RG-C01: pristine candidate already fails an R2 probe")
            print(f"  {'RG-C01-pristine-redis-authority-held':<40} UNEXPECTED WEAK (pristine)")
    for name, target_file, patch, probe_name in R2_MUTATIONS_WIRED:
        _run_probe_mutation(
            name, target_file, patch, (lambda pn=probe_name: _r2_mut.run_probe(pn)), failures
        )

    # HE2-ET1-R2-R2 GREEN control + module-binding mutations.
    if R2R2_MUTATIONS_WIRED:
        pristine_s = all(_r2r2_mut.run_probe(probe_name) for _, _, _, probe_name in R2R2_MUTATIONS_WIRED)
        if pristine_s:
            print(f"  {'RS-C01-pristine-module-binding-held':<40} GREEN as intended")
        else:
            failures.append("RS-C01: pristine candidate already fails an R2-R2 probe")
            print(f"  {'RS-C01-pristine-module-binding-held':<40} UNEXPECTED WEAK (pristine)")
    for name, target_file, patch, probe_name in R2R2_MUTATIONS_WIRED:
        _run_probe_mutation(
            name, target_file, patch, (lambda pn=probe_name: _r2r2_mut.run_probe(pn)), failures
        )

    for name, factory, *mode_args in MODE_PROOFS:
        result = factory()
        head, base = result[0], result[1]
        try:
            code, report = run_validator(head, base, tuple(mode_args))
            gates = (report or {}).get("gates", {})
            if code == 3 and gates.get("structural_gate") == "PASS" and gates.get(
                "release_gate"
            ) == "BLOCKED":
                print(f"  {name:<40} RED as intended (exit 3, RELEASE_GATE=BLOCKED)")
            else:
                failures.append(
                    f"{name}: expected exit 3 with structural PASS / release BLOCKED, "
                    f"got exit {code}, gates {gates}"
                )
                print(f"  {name:<40} FAILED (exit {code}, gates {gates})")
        finally:
            shutil.rmtree(head, ignore_errors=True)
            shutil.rmtree(base, ignore_errors=True)

    for name, factory in GREEN_CONTROLS:
        result = factory()
        head, base = result[0], result[1]
        try:
            code, report = run_validator(head, base)
            if code == 0:
                print(f"  {name:<40} GREEN as intended")
            else:
                violations = [v["code"] for v in (report or {}).get("violations", [])]
                failures.append(f"{name}: control went RED: {violations}")
                print(f"  {name:<40} UNEXPECTED RED {violations}")
        finally:
            shutil.rmtree(head, ignore_errors=True)
            shutil.rmtree(base, ignore_errors=True)

    after = tree_digest()
    print("-" * 78)
    if before != after:
        failures.append(
            "candidate tree integrity: harness-governance changed during the gate run"
        )
        print("TREE INTEGRITY: FAIL (candidate tree was modified)")
    else:
        print(f"TREE INTEGRITY: OK ({before[:12]} before == after)")

    if failures:
        print(f"FAIL: {len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        f"PASS: all {total_red} mutations produced the intended RED "
        f"({len(RED_MUTATIONS)} with explicit rule codes), "
        f"{len(GREEN_CONTROLS)} controls stayed GREEN, candidate tree byte-identical"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
