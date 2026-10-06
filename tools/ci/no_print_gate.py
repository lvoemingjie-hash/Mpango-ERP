#!/usr/bin/env python3
"""AST no-print gate for backend business request paths.

Contract (CTO-C91-CI-CONTRACT-ALIGNMENT-ZCODEW-R2-20261006):

* Scope covers the business request paths: backend/api, backend/services and
  backend/core.  Migrations, CLI/provisioning scripts and standalone manual
  test files at the backend root are outside the request path and are not
  linted here; backend/tests is likewise out of scope.
* ``backend/main.py`` and ``backend/core/config.py`` carry inherited startup
  diagnostics and are explicit, listed exceptions for this round only.  The
  exception is a scope decision, not a sign-off on the diagnostic content.
* A finding is a real call to the builtin ``print`` — either a ``print(...)``
  call, an explicit ``builtins.print(...)``, or any alias imported from
  ``builtins``.  Business function *names* containing "print", comments and
  string examples are not builtin calls and must not be reported.
* A module-level rebinding of ``print`` (``def print`` / ``print = ...``)
  is an unambiguous shadow ONLY for call sites AFTER the binding line; a
  ``print(...)`` that appears BEFORE a later module-level binding resolves
  to that same global and is reported (it would NameError at runtime).
  Nested-scope shadowing is intentionally not modeled: this is a lint, not
  a full resolver, and it makes no claim about dynamic Python or about the
  secret-safety of anything that is logged.
* Unparseable in-scope Python fails closed (exit code 2).
* Output carries relative path, line number and category only — never the
  source line or any data value.

Exit codes: 0 clean, 1 findings, 2 parse failure.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

SCOPE_DIRS = ("backend/api", "backend/services", "backend/core")
STARTUP_DIAGNOSTIC_EXCEPTIONS = (
    "backend/main.py",
    "backend/core/config.py",
)
EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_PARSE_FAILURE = 2


class ParseFailure(Exception):
    """An in-scope Python file could not be parsed; the gate fails closed."""


def _builtin_print_alias_names(tree: ast.Module) -> set[str]:
    """Names bound by ``from builtins import print [as alias]``."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "builtins":
            for name in node.names:
                if name.name == "print":
                    aliases.add(name.asname or "print")
    return aliases


def _module_level_print_binding_line(tree: ast.Module) -> int | None:
    """Line of the FIRST module-level binding of ``print``, or None.

    R3 contract: an unambiguous global shadow only exempts calls that appear
    AFTER the binding line.  A ``print(...)`` BEFORE a later module-level
    ``def print`` / ``print = ...`` resolves to that same global name at
    runtime and would raise NameError before the binding executes — it is a
    real defect, not a shadowed builtin call, and must stay a finding.
    """
    lines: list[int] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == "print":
                lines.append(node.lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "print":
                    lines.append(target.lineno)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "print":
                lines.append(target.lineno)
    return min(lines) if lines else None


def _is_builtin_print_call(node: ast.Call, aliases: set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "print" or func.id in aliases
    if isinstance(func, ast.Attribute):
        return (
            func.attr == "print"
            and isinstance(func.value, ast.Name)
            and func.value.id == "builtins"
        )
    return False


def check_source(source: str, *, detection_enabled: bool = True) -> list[tuple[int, str]]:
    """Return ``(line, category)`` findings for one module's source text.

    ``detection_enabled=False`` exists purely so the offline contract tests
    can prove the discriminating counterexamples go RED when the builtin-call
    check is removed (mutation guard); the gate itself always enables it.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ParseFailure(str(exc)) from exc

    findings: list[tuple[int, str]] = []
    if not detection_enabled:
        return findings

    aliases = _builtin_print_alias_names(tree)
    shadow_line = _module_level_print_binding_line(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Name)
            and func.id == "print"
            and shadow_line is not None
            and node.lineno > shadow_line
        ):
            # unambiguous: a module-level binding earlier in this file
            # shadows the builtin for this call site
            continue
        if _is_builtin_print_call(node, aliases):
            if isinstance(func, ast.Attribute):
                category = "explicit-builtins-print"
            elif isinstance(func, ast.Name) and func.id != "print":
                category = "builtin-print-alias"
            else:
                category = "builtin-print"
            findings.append((node.lineno, category))
    findings.sort()
    return findings


def iter_scope_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for scope_dir in SCOPE_DIRS:
        base = repo_root / scope_dir
        if not base.is_dir():
            raise ParseFailure(f"scope directory missing: {scope_dir}")
        files.extend(sorted(base.rglob("*.py")))
    return files


def run_gate(repo_root: Path) -> tuple[int, list[str], list[str]]:
    """Run the gate; returns (exit_code, finding_lines, summary_lines)."""
    findings: list[str] = []
    parse_failures: list[str] = []
    checked = 0
    for path in iter_scope_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        if rel in STARTUP_DIAGNOSTIC_EXCEPTIONS:
            continue
        checked += 1
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            parse_failures.append(f"{rel}:unreadable:{type(exc).__name__}")
            continue
        try:
            file_findings = check_source(source)
        except ParseFailure:
            parse_failures.append(f"{rel}:parse-error")
            continue
        for lineno, category in file_findings:
            findings.append(f"{rel}:{lineno}:{category}")

    summary = [
        f"scope: {', '.join(SCOPE_DIRS)}",
        f"files-checked: {checked}",
        "startup-diagnostic-exceptions (inherited, listed): "
        + ", ".join(STARTUP_DIAGNOSTIC_EXCEPTIONS),
        f"findings: {len(findings)}",
        f"parse-failures: {len(parse_failures)}",
    ]
    if parse_failures:
        return EXIT_PARSE_FAILURE, findings, summary + parse_failures
    if findings:
        return EXIT_FINDINGS, findings, summary
    return EXIT_CLEAN, findings, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Repository root containing backend/ (default: this tool's repo)",
    )
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    exit_code, findings, summary = run_gate(repo_root)
    for line in summary:
        print(f"[no-print-gate] {line}")
    for finding in findings:
        print(f"[no-print-gate] finding {finding}")
    if exit_code == EXIT_FINDINGS:
        print(
            "[no-print-gate] FAIL: builtin print calls in business request "
            "paths; use core.structured_logging get_logger instead"
        )
    elif exit_code == EXIT_PARSE_FAILURE:
        print(
            "[no-print-gate] FAIL-CLOSED: in-scope Python failed to parse "
            "or read; refusing to pass an unlintable tree"
        )
    else:
        print("[no-print-gate] PASS: no builtin print calls in scope")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
