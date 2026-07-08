#!/usr/bin/env python3
"""Platform Batch Mission Check CLI - Mpango ERP.

Scans all ai-ledger/platform/*_mission.json files and validates each
using the mission contract logic from platform_agent_mission_gate.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_agent_mission_gate as gate

LEDGER_DIR = "ai-ledger/platform"


def load_mission(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        return {"_error": f"malformed JSON: {e}"}
    except Exception as e:
        return {"_error": f"read error: {e}"}


def batch_check(repo_root):
    """Check all mission JSONs. Returns (results, all_pass)."""
    ledger_dir = os.path.join(repo_root, LEDGER_DIR)
    results = []

    if not os.path.isdir(ledger_dir):
        return results, True

    mission_files = sorted(
        f for f in os.listdir(ledger_dir) if f.endswith("_mission.json")
    )

    if not mission_files:
        return results, True

    for mf in mission_files:
        full_path = os.path.join(ledger_dir, mf)
        rel_path = os.path.join(LEDGER_DIR, mf)
        data = load_mission(full_path)

        if "_error" in data:
            results.append({
                "file": rel_path,
                "valid": False,
                "failures": [data["_error"]],
            })
            continue

        failures = gate.validate_mission(data)
        results.append({
            "file": rel_path,
            "valid": len(failures) == 0,
            "failures": failures,
        })

    all_pass = all(r["valid"] for r in results)
    return results, all_pass


def format_human(results, all_pass):
    if not results:
        return "No mission files found."
    lines = []
    for r in results:
        status = "PASS" if r["valid"] else "FAIL"
        lines.append(f"  [{status}] {r['file']}")
        for f in r["failures"]:
            lines.append(f"         {f}")
    lines.append("")
    total = len(results)
    passed = sum(1 for r in results if r["valid"])
    lines.append(f"Total: {total} | Passed: {passed} | Failed: {total - passed}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Batch-check all platform mission JSONs"
    )
    parser.add_argument("--repo", required=True, help="Path to repository root")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args(argv)

    repo_root = os.path.abspath(args.repo)
    if not os.path.isdir(repo_root):
        print(f"Error: {args.repo} is not a directory", file=sys.stderr)
        return 2

    results, all_pass = batch_check(repo_root)

    if args.json:
        print(json.dumps({
            "missions": results,
            "total": len(results),
            "passed": sum(1 for r in results if r["valid"]),
            "failed": sum(1 for r in results if not r["valid"]),
            "all_pass": all_pass,
        }, indent=2))
    else:
        print(format_human(results, all_pass))

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
