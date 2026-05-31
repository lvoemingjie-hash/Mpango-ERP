#!/usr/bin/env python3
"""Platform Ledger Gap Audit CLI - Mpango ERP.

Scans ai-ledger/platform/ for missing or broken ledger artifact chains:
mission JSON -> mission markdown, result, events.
"""

import argparse
import json
import os
import sys


LEDGER_DIR = "ai-ledger/platform"

FORBIDDEN_PREFIXES = [
    "backend/", "frontend/", ".github/workflows/", ".claude/", "docs/ai/",
]

FORBIDDEN_FRAGMENTS = [
    "auth", "rbac", "tenancy", "migration", "payment", "session",
]


def normalize_path(p):
    return p.replace("\\", "/")


def is_unsafe_path(path):
    """Return (is_unsafe, reason) tuple."""
    n = normalize_path(path)
    if os.path.isabs(path) or n.startswith("/"):
        return True, "absolute path"
    parts = n.split("/")
    if ".." in parts:
        return True, "directory traversal"
    if "" in parts:
        return True, "empty path segment"
    first = parts[0]
    if ":" in first and len(first) > 2:
        return True, "drive-qualified path"
    return False, None


def is_forbidden_path(path):
    n = normalize_path(path)
    for prefix in FORBIDDEN_PREFIXES:
        if n.startswith(prefix):
            return True
    for part in n.split("/"):
        low = part.lower()
        for frag in FORBIDDEN_FRAGMENTS:
            if frag in low:
                return True
    return False


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None
    except Exception:
        return None


def audit_ledger(repo_root):
    """Scan the ledger directory and return a list of gap dicts."""
    ledger_dir = os.path.join(repo_root, LEDGER_DIR)
    gaps = []

    if not os.path.isdir(ledger_dir):
        return gaps

    all_files = set(os.listdir(ledger_dir))

    mission_jsons = sorted(f for f in all_files if f.endswith("_mission.json"))
    result_jsons = sorted(f for f in all_files if f.endswith("_result.json"))
    events_jsonls = sorted(f for f in all_files if f.endswith("_events.jsonl"))
    mission_mds = set(f for f in all_files if f.endswith("_mission.md"))

    # Build mission stem -> mission json filename
    missions = {}
    for mj in mission_jsons:
        stem = mj[: -len("_mission.json")]
        full_path = os.path.join(ledger_dir, mj)
        data = load_json(full_path)
        if data is None:
            gaps.append({
                "type": "malformed_mission_json",
                "file": os.path.join(LEDGER_DIR, mj),
                "detail": "file is not valid JSON",
            })
            continue
        missions[stem] = {"filename": mj, "data": data}

    # Collect referenced paths from missions for orphan detection
    referenced = set()
    for stem, info in missions.items():
        data = info["data"]
        for key in ("mission", "result", "events"):
            val = data.get(key, "")
            if isinstance(val, str) and val.strip():
                referenced.add(normalize_path(val))
        for ef in data.get("expected_files", []):
            if isinstance(ef, str) and ef.strip():
                referenced.add(normalize_path(ef))

    # Check each mission JSON for gaps
    for stem, info in sorted(missions.items()):
        data = info["data"]
        mj_path = os.path.join(LEDGER_DIR, info["filename"])

        # Check mission markdown
        mission_md = data.get("mission", "")
        if isinstance(mission_md, str) and mission_md.strip():
            unsafe, reason = is_unsafe_path(mission_md)
            if unsafe:
                gaps.append({
                    "type": "unsafe_path",
                    "file": mj_path,
                    "field": "mission",
                    "ref": mission_md,
                    "detail": f"unsafe path: {reason}",
                })
            elif is_forbidden_path(mission_md):
                gaps.append({
                    "type": "forbidden_path",
                    "file": mj_path,
                    "field": "mission",
                    "ref": mission_md,
                    "detail": "references forbidden path",
                })
            else:
                md_abs = os.path.join(repo_root, normalize_path(mission_md))
                if not os.path.isfile(md_abs):
                    gaps.append({
                        "type": "missing_mission_markdown",
                        "file": mj_path,
                        "ref": mission_md,
                        "detail": "mission markdown file not found",
                    })

        # Check result
        result_ref = data.get("result", "")
        if isinstance(result_ref, str) and result_ref.strip():
            unsafe, reason = is_unsafe_path(result_ref)
            if unsafe:
                gaps.append({
                    "type": "unsafe_path",
                    "file": mj_path,
                    "field": "result",
                    "ref": result_ref,
                    "detail": f"unsafe path: {reason}",
                })
            elif is_forbidden_path(result_ref):
                gaps.append({
                    "type": "forbidden_path",
                    "file": mj_path,
                    "field": "result",
                    "ref": result_ref,
                    "detail": "references forbidden path",
                })
            else:
                res_abs = os.path.join(repo_root, normalize_path(result_ref))
                if not os.path.isfile(res_abs):
                    gaps.append({
                        "type": "missing_result",
                        "file": mj_path,
                        "ref": result_ref,
                        "detail": "result file not found",
                    })

        # Check events
        events_ref = data.get("events", "")
        if isinstance(events_ref, str) and events_ref.strip():
            unsafe, reason = is_unsafe_path(events_ref)
            if unsafe:
                gaps.append({
                    "type": "unsafe_path",
                    "file": mj_path,
                    "field": "events",
                    "ref": events_ref,
                    "detail": f"unsafe path: {reason}",
                })
            elif is_forbidden_path(events_ref):
                gaps.append({
                    "type": "forbidden_path",
                    "file": mj_path,
                    "field": "events",
                    "ref": events_ref,
                    "detail": "references forbidden path",
                })
            else:
                ev_abs = os.path.join(repo_root, normalize_path(events_ref))
                if not os.path.isfile(ev_abs):
                    gaps.append({
                        "type": "missing_events",
                        "file": mj_path,
                        "ref": events_ref,
                        "detail": "events file not found",
                    })

    # Check for orphan results (result JSON without a matching mission)
    for rj in result_jsons:
        ref_path = os.path.join(LEDGER_DIR, rj)
        norm_ref = normalize_path(ref_path)
        if norm_ref not in referenced:
            gaps.append({
                "type": "orphan_result",
                "file": ref_path,
                "detail": "result JSON has no related mission",
            })

    # Check for orphan events (events JSONL without a matching mission)
    for ev in events_jsonls:
        ref_path = os.path.join(LEDGER_DIR, ev)
        norm_ref = normalize_path(ref_path)
        if norm_ref not in referenced:
            gaps.append({
                "type": "orphan_events",
                "file": ref_path,
                "detail": "events JSONL has no related mission",
            })

    # Check for orphan mission markdown files
    for md_file in sorted(mission_mds):
        ref_path = os.path.join(LEDGER_DIR, md_file)
        norm_ref = normalize_path(ref_path)
        if norm_ref not in referenced:
            gaps.append({
                "type": "orphan_mission_markdown",
                "file": ref_path,
                "detail": "mission markdown not referenced by any mission JSON",
            })

    return gaps


def format_human(gaps):
    if not gaps:
        return "No ledger gaps found."
    lines = [f"Found {len(gaps)} ledger gap(s):\n"]
    for g in gaps:
        lines.append(f"  [{g['type']}] {g['file']}")
        if "ref" in g:
            lines.append(f"    ref: {g['ref']}")
        if "detail" in g:
            lines.append(f"    {g['detail']}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit platform ledger artifacts for gaps"
    )
    parser.add_argument(
        "--repo", required=True, help="Path to repository root"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    args = parser.parse_args(argv)

    repo_root = os.path.abspath(args.repo)
    if not os.path.isdir(repo_root):
        print(f"Error: {args.repo} is not a directory", file=sys.stderr)
        return 2

    gaps = audit_ledger(repo_root)

    if args.json:
        print(json.dumps({"gaps": gaps, "count": len(gaps)}, indent=2))
    else:
        print(format_human(gaps))

    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
