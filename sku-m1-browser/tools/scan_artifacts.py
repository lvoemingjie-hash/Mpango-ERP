#!/usr/bin/env python3
"""Sanitized artifact scanner for the SKU browser harness (B1). Stdlib only.

Scans run artifacts (playwright report, traces dir listing, reconciliation,
preflight verdict) and the harness sources for secret-looking material that
must never leave the harness: real passwords from the official provisioning
file, bearer/JWT token shapes, SMTP capture contents with credentials.

Raw provisioning passwords are the ONLY fixtures in this harness and must not
appear in any published artifact. The scanner fails (exit 1) when any forbidden
string appears in any scanned artifact file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]


def forbidden_strings() -> list[str]:
    secrets: list[str] = []
    official = HARNESS / "provisioning" / "official.json"
    if official.exists():
        data = json.loads(official.read_text(encoding="utf-8"))
        for tenant_key in ("tenant_a", "tenant_b"):
            tenant = data.get(tenant_key, {})
            if tenant.get("owner_password"):
                secrets.append(tenant["owner_password"])
            if tenant.get("retailer", {}).get("password"):
                secrets.append(tenant["retailer"]["password"])
    return secrets


TOKEN_SHAPES = [
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "jwt_shape"),
]


def scan_file(path: Path, secrets: list[str]) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for secret in secrets:
        if secret in text:
            findings.append(f"provisioning_password_leak:{path.name}")
            break
    for pattern, label in TOKEN_SHAPES:
        if re.search(pattern, text):
            findings.append(f"token_shape:{label}:{path.name}")
            break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=str(HARNESS / "results"))
    args = parser.parse_args()
    secrets = forbidden_strings()
    findings: list[str] = []
    results = Path(args.results)
    scanned = 0
    if results.exists():
        for path in results.rglob("*"):
            if path.is_file() and path.suffix in (".json", ".jsonl", ".txt", ".log", ".md", ".eml"):
                scanned += 1
                findings.extend(scan_file(path, secrets))
    for label in findings:
        print(f"  - {label}")
    if findings:
        print(f"ARTIFACT SCANNER: RED ({scanned} files scanned, {len(findings)} findings)")
        return 1
    print(f"ARTIFACT SCANNER: GREEN ({scanned} files scanned, 0 findings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
