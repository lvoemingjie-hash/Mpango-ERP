#!/usr/bin/env python3
"""Platform Function Registry - Mpango ERP.

Enumerates all platform harness scripts, pairs them with tests,
and identifies related ledger artifacts.
"""

import argparse
import json
import os
import re
import sys


def normalize_path(p):
    return p.replace("\\", "/")


def scan_scripts(scripts_dir):
    """Enumerate scripts/platform_*.py and pair with test files."""
    entries = []
    if not os.path.isdir(scripts_dir):
        return entries
    for name in sorted(os.listdir(scripts_dir)):
        if name.startswith("platform_") and name.endswith(".py"):
            script_rel = normalize_path(os.path.join("scripts", name))
            test_name = "test_" + name
            test_rel = normalize_path(os.path.join("scripts", test_name))
            has_test = os.path.isfile(os.path.join(scripts_dir, test_name))

            # Extract function name from script name
            # platform_health_check.py -> health_check
            func_name = name[len("platform_"):-len(".py")]

            entries.append({
                "script": script_rel,
                "test": test_rel if has_test else None,
                "function": func_name,
                "paired": has_test,
            })
    return entries


def find_related_ledgers(ledger_dir, function_name):
    """Find ledger files related to a function name.

    Looks for ledgers whose filename contains the function name
    or keywords from it.
    """
    related = []
    if not os.path.isdir(ledger_dir):
        return related

    # Split function_name into keywords
    # e.g. "harness_index" -> ["harness", "index"]
    keywords = [k for k in re.split(r"[_]", function_name) if len(k) > 2]

    for name in sorted(os.listdir(ledger_dir)):
        if not name.endswith((".md", ".json", ".jsonl")):
            continue
        name_lower = name.lower()
        # Check if function name or any keyword appears in the ledger name
        if function_name in name_lower:
            related.append(normalize_path(os.path.join("ai-ledger", "platform", name)))
        elif keywords and any(k in name_lower for k in keywords):
            related.append(normalize_path(os.path.join("ai-ledger", "platform", name)))

    return related


def build_registry(repo_path):
    """Build a full function registry."""
    scripts_dir = os.path.join(repo_path, "scripts")
    ledger_dir = os.path.join(repo_path, "ai-ledger", "platform")

    entries = scan_scripts(scripts_dir)

    for entry in entries:
        entry["ledgers"] = find_related_ledgers(ledger_dir, entry["function"])

    return {
        "total_scripts": len(entries),
        "paired": sum(1 for e in entries if e["paired"]),
        "unpaired": sum(1 for e in entries if not e["paired"]),
        "entries": entries,
    }


def format_human(registry):
    lines = ["Platform Function Registry", "=" * 40]
    lines.append(f"Total scripts: {registry['total_scripts']}")
    lines.append(f"Paired: {registry['paired']}")
    lines.append(f"Unpaired: {registry['unpaired']}")
    lines.append("")

    for entry in registry["entries"]:
        status = "PASS" if entry["paired"] else "MISSING TEST"
        lines.append(f"  {entry['function']}: {status}")
        lines.append(f"    script: {entry['script']}")
        if entry["test"]:
            lines.append(f"    test:   {entry['test']}")
        if entry["ledgers"]:
            lines.append(f"    ledgers: {len(entry['ledgers'])}")
            for l in entry["ledgers"][:3]:
                lines.append(f"      {l}")
            if len(entry["ledgers"]) > 3:
                lines.append(f"      ... and {len(entry['ledgers']) - 3} more")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Function Registry"
    )
    parser.add_argument(
        "--repo", default=".",
        help="Path to the git repository root (default: current directory)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output in JSON format",
    )
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    registry = build_registry(repo_path)

    if args.json:
        print(json.dumps(registry, indent=2))
    else:
        print(format_human(registry))

    sys.exit(0)


if __name__ == "__main__":
    main()
