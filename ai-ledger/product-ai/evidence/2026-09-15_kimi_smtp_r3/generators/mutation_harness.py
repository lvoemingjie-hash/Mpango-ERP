"""Published generator (see the R3 evidence README).

Same logic as the task-local script that produced the R3 evidence, with
absolute paths replaced by environment lookups so it runs from a checkout:

  KIMI_SMTP_BACKEND_DIR     backend/ directory of the checkout (required)
  KIMI_SMTP_EVIDENCE_DIR    where evidence files are written (default .)
  python                    sys.executable is used for subprocesses
"""
import os
import sys

BACKEND = os.environ["KIMI_SMTP_BACKEND_DIR"]
WORKTREE = os.path.dirname(os.path.abspath(BACKEND))
PYTHON = sys.executable
SCRATCH = os.environ.get("KIMI_SMTP_EVIDENCE_DIR") or os.getcwd()


import hashlib
import json
import os
import subprocess
import sys

BACKEND = WORKTREE + r"\backend"
EVIDENCE = os.path.join(SCRATCH, "mutation_evidence_r3.json")

CONFIG = BACKEND + r"\core\config.py"
DELIVERY = BACKEND + r"\services\email_delivery.py"

PURE = "tests/test_smtp_auth_mode_guard_config.py"
DBFILE = "tests/test_smtp_loopback_noauth_contract.py"

MUTATIONS = [
    {
        "id": "M1_settings_loopback_validator_removed",
        "file": CONFIG,
        "old": 'if self.SMTP_AUTH_MODE == "none" and not is_loopback_smtp_host(self.SMTP_HOST):',
        "new": 'if False and self.SMTP_AUTH_MODE == "none" and not is_loopback_smtp_host(self.SMTP_HOST):',
        "expect_red": [f"{PURE}::test_noauth_mode_is_rejected_for_non_loopback_host"],
    },
    {
        "id": "M2_default_auth_mode_flipped_to_none",
        "file": CONFIG,
        "old": 'SMTP_AUTH_MODE: Literal["login", "none"] = Field(\n        default="login",',
        "new": 'SMTP_AUTH_MODE: Literal["login", "none"] = Field(\n        default="none",',
        "expect_red": [f"{PURE}::test_login_remains_the_default_auth_mode"],
    },
    {
        "id": "M3_config_completeness_loopback_guard_removed",
        "file": DELIVERY,
        "old": '    if auth_mode == "none" and not is_loopback_smtp_host(str(host)):\n'
               '        # Fail closed: unauthenticated delivery is only ever valid for a\n'
               '        # task-owned loopback capture sink (mirrors the Settings validator;\n'
               '        # this also guards loosely constructed settings objects).\n'
               '        return False\n',
        "new": "",
        "expect_red": [f"{PURE}::test_config_completeness_rejects_offloopback_noauth"],
    },
    {
        "id": "M4_send_layer_loopback_guard_removed",
        "file": DELIVERY,
        "old": '    if auth_mode == "none" and not is_loopback_smtp_host(host):\n'
               '        # Fail closed even for loosely constructed settings: no-auth\n'
               '        # delivery must never leave the loopback capture-sink boundary.\n'
               '        raise EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED")\n',
        "new": "",
        # The config-completeness gate (M3) still shields the API path, so the
        # true detector of the send-layer loopback guard is the direct
        # zero-connection assertion on _send_smtp_email.
        "expect_red": [
            f"{PURE}::test_delivery_layer_guard_blocks_offloopback_noauth_before_transport",
        ],
    },
    {
        "id": "M5_send_layer_unknown_mode_guard_removed",
        "file": DELIVERY,
        "old": '    if auth_mode not in _SMTP_AUTH_MODES:\n'
               '        raise EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED")\n',
        "new": "",
        # Removing this check lets the transport be constructed (tripwire fires)
        # before the wrapped 503 is produced; the direct zero-connection
        # assertion on _send_smtp_email must therefore go RED.
        "expect_red": [
            f"{PURE}::test_send_layer_unknown_mode_guard_blocks_before_transport",
        ],
    },    {
        "id": "M6_settings_login_transport_guard_removed",
        "file": CONFIG,
        "old": '        if login_would_send_cleartext(\n            auth_mode=self.SMTP_AUTH_MODE,',
        "new": '        if False and login_would_send_cleartext(\n            auth_mode=self.SMTP_AUTH_MODE,',
        "expect_red": [
            f"{PURE}::test_external_login_without_transport_encryption_is_rejected_by_settings",
        ],
    },
    {
        "id": "M7_completeness_login_transport_guard_removed",
        "file": DELIVERY,
        "old": '    if login_would_send_cleartext(\n'
               '        auth_mode=auth_mode,\n'
               '        host=str(host),\n'
               '        use_tls=bool(getattr(settings, "SMTP_USE_TLS", False)),\n'
               '        use_starttls=bool(getattr(settings, "SMTP_STARTTLS", True)),\n'
               '    ):\n'
               '        # Layer 2 of the shared rule: external login without TLS or STARTTLS\n'
               '        # is not a complete configuration.\n'
               '        return False\n',
        "new": "",
        "expect_red": [
            f"{PURE}::test_external_login_without_transport_encryption_fails_completeness",
        ],
    },
    {
        "id": "M8_send_layer_login_transport_guard_removed",
        "file": DELIVERY,
        "old": '    if login_would_send_cleartext(\n'
               '        auth_mode=auth_mode,\n'
               '        host=host,\n'
               '        use_tls=use_tls,\n'
               '        use_starttls=use_starttls,\n'
               '    ):\n'
               '        # Layer 3 (final guard, before SMTP/SMTP_SSL is ever constructed):\n'
               '        # never send login credentials to a non-loopback host unencrypted.\n'
               '        raise EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED")\n',
        "new": "",
        "expect_red": [
            f"{PURE}::test_external_login_without_transport_encryption_constructs_no_smtp_client",
        ],
    },
]


def sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def run_pytest(target: str) -> tuple[int, str]:
    env = dict(os.environ)
    result = subprocess.run(
        [PYTHON, "-m", "pytest", target, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=env,
    )
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    failing = [line for line in lines if line.startswith(("FAILED", "ERROR"))]
    summary = lines[-1][:200] if lines else (result.stderr or "").strip()[:200]
    return result.returncode, "; ".join(failing[:3]) or f"no FAILED line; stderr/status: {summary}"


def main() -> int:
    evidence: list[dict] = []
    survivors: list[str] = []
    for mutation in MUTATIONS:
        path = mutation["file"]
        with open(path, encoding="utf-8", newline="") as handle:
            original = handle.read()
        before_digest = hashlib.sha256(original.encode()).hexdigest()
        newline = "\r\n" if "\r\n" in original else "\n"
        old = mutation["old"].replace("\n", newline)
        new = mutation["new"].replace("\n", newline) if mutation["new"] else mutation["new"]
        assert original.count(old) == 1, (mutation["id"], "anchor not unique")

        entry: dict = {
            "id": mutation["id"],
            "file": os.path.relpath(path, WORKTREE).replace("\\", "/"),
            "sha256_before": before_digest,
            "results": [],
        }
        try:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(original.replace(old, new))
            if sha256(path) == before_digest:
                raise AssertionError(f"{mutation['id']}: mutation did not change the file bytes")
            for target in mutation["expect_red"]:
                code, failing = run_pytest(target)
                entry["results"].append(
                    {"node": target, "exit_code": code, "verdict": "DETECTED" if code != 0 else "SURVIVED", "failing": failing}
                )
                if code == 0:
                    survivors.append(f"{mutation['id']}::{target}")
        finally:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(original)
        after_digest = sha256(path)
        entry["sha256_after_restore"] = after_digest
        entry["restored_exact"] = after_digest == before_digest
        if not entry["restored_exact"]:
            survivors.append(f"{mutation['id']}::RESTORE_MISMATCH")
        evidence.append(entry)

    with open(EVIDENCE, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"mutations": evidence, "survivors": survivors}, handle, indent=2)

    for entry in evidence:
        for result in entry["results"]:
            print(f"{entry['id']:48s} {result['verdict']:9s} restored_exact={entry['restored_exact']} {result['node']}")
            if result["failing"]:
                print(f"    red: {result['failing'][:150]}")
    print(f"evidence: {EVIDENCE}")
    if survivors:
        print("SURVIVORS:", survivors)
        return 1
    print("all mutations detected; all source files restored byte-identically")
    return 0


if __name__ == "__main__":
    sys.exit(main())
