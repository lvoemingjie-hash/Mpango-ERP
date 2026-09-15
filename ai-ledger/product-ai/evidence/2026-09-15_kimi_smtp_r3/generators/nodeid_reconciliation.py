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
import io
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

BACKEND = os.environ["KIMI_SMTP_BACKEND_DIR"]
SCRATCH = os.environ.get("KIMI_SMTP_EVIDENCE_DIR") or os.getcwd()
PYTHON = sys.executable
FILE_LIST = os.path.join(SCRATCH, "focused_files_r3.txt")
JUNIT = os.path.join(SCRATCH, "focused_r3.xml")
EVIDENCE = os.path.join(SCRATCH, "nodeid_reconciliation_r3.json")
PER_NODE = os.path.join(SCRATCH, "per_node_r3.txt")

REQUIRED_ENV = (
    "KIMI_SMTP_TASK_DATABASE_URL",
    "KIMI_SMTP_TASK_CLUSTER_ID",
    "TEST_DATABASE_URL",
)

FILES = [line.strip() for line in io.open(FILE_LIST, encoding="utf-8") if line.strip()]
PYTEST_PATHS = [path[len("backend/"):] if path.startswith("backend/") else path for path in FILES]
DOTTED = {path[:-3].replace("/", "."): path for path in PYTEST_PATHS}


def child_env() -> dict:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key)]
    if missing:
        raise SystemExit(
            "refusing to run: missing environment variables "
            f"{missing} (the database suite fails closed without them)"
        )
    return dict(os.environ)


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "pytest", *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=child_env(),
    )


def collect_ids() -> tuple[set[str], int, str]:
    result = run(["--collect-only", "-q", "-o", "addopts=", "-p", "no:cacheprovider", *PYTEST_PATHS])
    output = (result.stdout or "") + (result.stderr or "")
    ids = {
        line.strip()
        for line in output.splitlines()
        if re.match(r"^tests/\S+\.py::", line.strip())
    }
    tail = output.strip().splitlines()[-1][:140] if output.strip() else ""
    return ids, result.returncode, tail


def nodeid_from_case(classname: str, name: str) -> str | None:
    for dotted in sorted(DOTTED, key=len, reverse=True):
        path = DOTTED[dotted]
        if classname == dotted:
            return f"{path}::{name}"
        if classname.startswith(dotted + "."):
            klass = classname[len(dotted) + 1:]
            return f"{path}::{klass}::{name}"
    return None


def result_ids() -> tuple[set[str], dict[str, int], list[str]]:
    if os.path.exists(JUNIT):
        os.remove(JUNIT)
    run(["-q", "-o", "addopts=", "-p", "no:cacheprovider", f"--junit-xml={JUNIT}", *PYTEST_PATHS])
    tree = ET.parse(JUNIT)
    executed: set[str] = set()
    unresolvable: list[str] = []
    verdicts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for case in tree.iter("testcase"):
        nodeid = nodeid_from_case(case.get("classname") or "", case.get("name") or "")
        if nodeid is None:
            unresolvable.append(f"{case.get('classname')}::{case.get('name')}")
            continue
        executed.add(nodeid)
        children = {child.tag for child in case}
        if "failure" in children:
            verdicts["failed"] += 1
        elif "error" in children:
            verdicts["error"] += 1
        elif "skipped" in children:
            verdicts["skipped"] += 1
        else:
            verdicts["passed"] += 1
    return executed, verdicts, unresolvable


def digest(items: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(items)).encode("utf-8")).hexdigest()


def main() -> int:
    collected, collect_code, collect_tail = collect_ids()
    if collect_code != 0 or not collected:
        raise SystemExit(f"collect failed (code {collect_code}): {collect_tail}")
    executed, verdicts, unresolvable = result_ids()

    missing = sorted(collected - executed)
    extra = sorted(executed - collected)
    equal = collected == executed
    evidence = {
        "files": FILES,
        "file_count": len(FILES),
        "collect_count": len(collected),
        "result_count": len(executed),
        "collect_set_sha256": digest(collected),
        "result_set_sha256": digest(executed),
        "sets_equal": equal,
        "missing_from_results": missing,
        "extra_in_results": extra,
        "unresolvable_junit_cases": unresolvable,
        "verdicts": verdicts,
        "collect_tail": collect_tail,
    }
    with io.open(EVIDENCE, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(evidence, handle, indent=2, sort_keys=True)

    with io.open(PER_NODE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# per-node results regenerated from junit XML attributes\n")
        handle.write("# nodeids are verbatim (parameters keep their exact whitespace)\n")
        handle.write(f"# collect set == result set: {equal}\n")
        handle.write(
            f"# nodes: {len(executed)} (passed={verdicts['passed']}, failed={verdicts['failed']}, "
            f"error={verdicts['error']}, skipped={verdicts['skipped']})\n\n"
        )
        for nodeid in sorted(executed):
            handle.write(nodeid + "\n")

    print(json.dumps({k: evidence[k] for k in (
        "file_count", "collect_count", "result_count", "sets_equal",
        "missing_from_results", "extra_in_results", "unresolvable_junit_cases", "verdicts")}, indent=2))
    print("evidence:", EVIDENCE)
    print("per-node:", PER_NODE)
    return 0 if equal and not unresolvable else 1


if __name__ == "__main__":
    sys.exit(main())
