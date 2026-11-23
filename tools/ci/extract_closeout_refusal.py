"""Summarize the original closeout entry's first named refusal; category+rc only.

Reads the runner-private closeout log and the captured real closeout rc,
extracts at most the FIRST ``prepare_test_evidence: REFUSED: <category>`` line
through a fixed allowlist, and writes a JSON summary containing no log text,
environment values, directory names, process arguments or wiring values. A
category outside the allowlist (or no readable category at all) is reported
as UNKNOWN together with the real rc, never with raw log content.
"""
import argparse
import json
import re
from pathlib import Path

_REFUSED = re.compile(r"^prepare_test_evidence: REFUSED: (\S+)\s*$")

# Fixed allowlist: every named category the queue-runtime-env entry can print.
# prepare_test_evidence.py's _queue_require prefixes "QUEUE_" onto its
# category argument, so prefixed literals below mirror the tool verbatim.
_ALLOWED_STATIC = frozenset("""
ATOMIC_PUBLISH_REFUSED
ATOMIC_PUBLISH_UNAVAILABLE
CAPSULE_DRIFT
CAPTURE_DRIFT
CAPTURE_MISSING
CAPTURE_SOURCE_BINDING
CHILD_BINDING_DRIFT
CHILD_ENV_MAPPING
CHILD_IDENTITY
CHILD_KEY_WHITELIST
CHILD_NATIVE_BINDING
CHILD_PLAN
CHILD_PROCESS_GROUP
CHILD_RECORD_SCOPE
CHILD_STILL_ALIVE
CI_REF_INVALID
CI_REF_MISMATCH
CLOSEOUT_RECEIPT_SCOPE
DATABASE_SCOPE
DUPLICATE_JSON_KEY
ENV_BINDING_NEWLINE
GITHUB_ENV_BINDING
GITHUB_ENV_SCOPE
OUTPUT_EXISTS
PARENT_BINDING_DRIFT
PARENT_CHILD_SOURCE_MISMATCH
PARENT_CONSUMER_MISMATCH
PATH_MODE
PATH_OWNER
PATH_SCOPE
PATH_TYPE
FILE_HARDLINK
PREEXISTING_PROOF
PROFILE_MISMATCH
REDIS_SCOPE
REGISTRATION_MISMATCH
REGISTRATION_SOURCE_MISMATCH
REPO_SCOPE
RETIREMENT_DRIFT
ROLE_MISMATCH
ROOT_MISMATCH
RUNNER_ROOT
SECRET_KEY_SHAPE
SHARD_REFUSED
SOURCE_OBJECT_MISMATCH
TASK_BINDING
TASK_IDENTITY_SHAPE
TMP_IDENTITY
TMP_SCOPE
URL_SCOPE
""".split()) | {"JSON_INVALID"}

_ALLOWED = frozenset("QUEUE_" + name for name in _ALLOWED_STATIC) | {
    # The closeout entry wraps the body in
    #   except (OSError, ValueError, KeyError) as error:
    #       Refused("QUEUE_INPUT_IO_OR_SHAPE_" + type(error).__name__, 3)
    # so the printed category carries the CONCRETE subclass name, not the
    # caught base class. The base names stay for completeness; the three
    # subclass names below were produced by the real entry offline (missing
    # path, file used as a directory component, unreadable directory), each
    # with rc 3, and are the ones observed in practice.
    "QUEUE_INPUT_IO_OR_SHAPE_" + name for name in (
        "OSError", "ValueError", "KeyError",
        "FileNotFoundError", "NotADirectoryError", "PermissionError",
    )
} | frozenset(
    "QUEUE_MISSING_KEY_" + key for key in (
        "RUNNER_TEMP", "GITHUB_WORKSPACE", "GITHUB_SHA", "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT", "CI_TASK_LABEL", "CI_OWNER_LABEL", "CI_PG_PORT",
        "CI_REDIS_PORT", "CI_TEST_DB", "DATABASE_URL", "TEST_REPORTING_DATABASE_URL",
        "REDIS_URL", "SECRET_KEY", "MPANGO_ENV", "TMPDIR",
    )
)


def _categorize(candidate):
    return candidate if candidate in _ALLOWED else "UNKNOWN"


def build_summary(log_path, rc_path):
    category = "UNKNOWN"
    if log_path is not None and log_path.is_file():
        try:
            for line in log_path.read_text(encoding="utf-8", errors="strict").splitlines():
                match = _REFUSED.match(line)
                if match is not None:
                    category = _categorize(match.group(1))
                    break
        except (OSError, UnicodeDecodeError):
            category = "UNKNOWN"
    closeout_rc = "missing"
    if rc_path is not None and rc_path.is_file():
        try:
            text = rc_path.read_text(encoding="ascii").strip()
            if re.fullmatch(r"-?[0-9]+", text):
                closeout_rc = int(text)
        except (OSError, UnicodeDecodeError):
            closeout_rc = "missing"
    return {"closeout_rc": closeout_rc, "first_refusal_category": category}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", required=True, help="runner-private closeout log (read-only)")
    parser.add_argument("--rc-file", required=True, help="runner-private captured closeout rc")
    parser.add_argument("--out", required=True, help="summary destination (category+rc only)")
    args = parser.parse_args(argv)
    summary = build_summary(Path(args.log), Path(args.rc_file))
    Path(args.out).write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print("[extract_closeout_refusal] category=%s rc=%s" % (
        summary["first_refusal_category"], summary["closeout_rc"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
