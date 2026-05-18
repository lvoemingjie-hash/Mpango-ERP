#!/usr/bin/env python3
"""
extract_leo_evidence.py — Extract evidence fields from openclaw agent --json output.

Usage:
    echo "$raw_json" | python3 extract_leo_evidence.py VERDICT
    echo "$raw_json" | python3 extract_leo_evidence.py COMMANDS_EXECUTED

Strategy:
1. Locate JSON object boundaries in raw output
2. Repair literal newlines inside string values (common openclaw bug)
3. Recursively scan ALL string fields for === LEO_EVIDENCE === marker
4. Extract the requested field value from the evidence block
5. Fallback: grep the raw output directly if JSON parsing fails

v1.0 — 2026-05-19 (extracted from run_directive.sh v3.6 inline Python)
"""
import json
import re
import sys


def find_evidence_text(obj, marker="=== LEO_EVIDENCE ==="):
    """Recursively scan all string fields for the evidence marker."""
    if isinstance(obj, str):
        return obj if marker in obj else None
    if isinstance(obj, dict):
        for v in obj.values():
            r = find_evidence_text(v, marker)
            if r:
                return r
    if isinstance(obj, list):
        for item in obj:
            r = find_evidence_text(item, marker)
            if r:
                return r
    return None


def repair_json_string(raw: str) -> str:
    """Replace literal newlines inside JSON string values with \\n escapes."""
    result = []
    in_string = False
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "\\" and in_string:
            result.append(c)
            if i + 1 < len(raw):
                i += 1
                result.append(raw[i])
            i += 1
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
        elif in_string and c in "\n\r":
            result.append("\\" + ("n" if c == "\n" else "r"))
        else:
            result.append(c)
        i += 1
    return "".join(result)


def extract_json_block(raw: str) -> str:
    """Find the outermost JSON object in raw output."""
    start = raw.find("{")
    if start < 0:
        return ""
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
        if depth == 0:
            return raw[start : i + 1]
    return ""


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_leo_evidence.py FIELD_NAME", file=sys.stderr)
        sys.exit(2)

    field_name = sys.argv[1]
    raw = sys.stdin.read()

    # Strategy 1: Parse JSON, find evidence text, extract field
    json_block = extract_json_block(raw)
    if json_block:
        repaired = repair_json_string(json_block)
        try:
            data = json.loads(repaired)
            evidence_text = find_evidence_text(data)
            if evidence_text:
                # Extract field: FIELD_NAME: value
                m = re.search(
                    rf"{re.escape(field_name)}:\s*(.+)",
                    evidence_text,
                    re.MULTILINE,
                )
                if m:
                    print(m.group(1).rstrip())
                    return
        except json.JSONDecodeError:
            pass

    # Strategy 2: grep fallback on raw output
    m = re.search(
        rf"{re.escape(field_name)}:\s*(.+)", raw, re.MULTILINE
    )
    if m:
        print(m.group(1).rstrip())
        return

    print("unknown")


if __name__ == "__main__":
    main()
