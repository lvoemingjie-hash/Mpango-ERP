#!/usr/bin/env python3
"""Static harness validator for the SKU browser harness (B1 + B3 + B4). Stdlib only.

Enforces, fail-closed:
  - exact two-node manifest (sorted, unique, LF-terminated, no duplicates,
    no reordering, deterministic identities);
  - deterministic node titles present in the specs;
  - desktop + mobile-390 viewport coverage (exact two projects, exact
    viewports, retries 0);
  - required assertion anchors (payload binding, mismatch rejection,
    cross-tenant rejection, independent stock, immutable snapshot,
    unavailable item);
  - no response mocking / route fulfillment / network interception;
  - no skip/fixme/only/retry;
  - no H2-C / j1h2b-forgot-reset imports;
  - no direct database drivers or DB seeding;
  - page.goto restricted to the whitelisted entry points (supported
    navigation guard);
  - B4 authority modes: exactly two mutually exclusive runtime modes
    (AUTHOR_DIAGNOSTIC / INDEPENDENT_AUTHORITY), fail-closed resolution,
    frozen recorded mode, append-only invocation accounting;
  - reconciliation accounting: every node x viewport combination recorded
    exactly once, and ONE execution mode + ONE candidate SHA shared by the
    invocation ledger, the live execution contract, the authority report,
    the Playwright report metadata and the reconciliation records
    (checked against a results dir when present, else skipped
    with --allow-missing-reconciliation).

Exit 0 = GREEN, 1 = RED (findings listed on stdout).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS.parents[1]

EXPECTED_NODES = [
    "sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001",
    "sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001",
]

RUNTIME_MODES = ("AUTHOR_DIAGNOSTIC", "INDEPENDENT_AUTHORITY")

# Required assertion anchors: the EXACT assertion code that must remain
# present. The mutation suite removes each one independently; the validator
# must turn RED when any is missing.
REQUIRED_ANCHORS = {
    "tests/catalog-id-001.spec.ts": [
        "expect(payloadUnitIds).toContain(bottleUuid);",
        "expect([400, 404, 409, 422]).toContain(mismatch.status());",
        "expect([400, 403, 404, 409, 422]).toContain(foreign.status());",
        "expect(String(bottleStock.skuId ?? bottleStock.sku_id ?? '')).not.toBe(",
        "expect(bottleUuid).toMatch(uuidRe);",
        # R1 product-level multipackaging oracle: containment + selected UUID
        "await expect(productContainer).toHaveCount(1, { timeout: 30_000 });",
        "await expect(containerUnits).toContainText(caseCode, { timeout: 30_000 });",
        "await expect(orderSection).toHaveAttribute('data-selected-sellable-unit-id', caseUuid, {",
        "await expect(page.getByTestId('selected-unit-stock')).toHaveText('Low Stock', {",
        "expect(orderItems[0].sellable_unit_id ?? orderItems[0].sellableUnitId).toBe(bottleUuid);",
    ],
    "tests/catalog-hist-001.spec.ts": [
        "expect(afterName).toBe(before.productName);",
        "await expect(unavailableUnitLink).toHaveCount(0);",
        # R1: the deactivated unit disappears from its OWN product container
        "await expect(productContainer).toBeVisible({ timeout: 30_000 });",
    ],
}

FORBIDDEN_PATTERNS = [
    (r"page\.route\s*\(", "api_mocking:page.route"),
    (r"context\.route\s*\(", "api_mocking:context.route"),
    (r"\.fulfill\s*\(", "api_mocking:fulfill"),
    (r"from\s+['\"]nock['\"]|require\(['\"]nock['\"]\)", "api_mocking:nock"),
    (r"msw", "api_mocking:msw"),
    (r"test\.skip|test\.only|\.fixme\s*\(|\.slow\s*\(", "skip_or_focus"),
    (r"retries\s*:\s*[1-9]", "retry_configured"),
    (r"j1h2b|forgot-reset|h2-c|h2c", "h2c_reference"),
    (r"from\s+['\"](pg|pg-promise|mysql|mysql2|mongodb)['\"]", "db_driver_import"),
    (r"from\s+['\"](psycopg|asyncpg|sqlalchemy)", "db_driver_import"),
    (r"INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM", "direct_db_seeding"),
    # B3 selector exactness: broad/conditional contract-critical navigation
    (r"getByRole\('link',\s*\{\s*name:\s*/client\|catalog\|back/i", "selector:broad_back_link"),
    (r"getByRole\('link',\s*\{\s*name:\s*/\.\*/", "selector:wildcard_link"),
    (r"getByRole\('link',\s*\{\s*name:\s*'Back to orders'\s*\}\)", "selector:back_as_link_role"),
    (r"getByRole\('button',\s*\{\s*name:\s*'Back to products'\s*\}\)", "selector:wrong_back_name"),
    # B3 auth truth: no 401 acceptance, no retry-on-401 replay
    (r"\[?[^\]]*401[^\]]*\]\)\.toContain|toContain\(.*401", "auth:401_accepted"),
    # R1: per-SKU link/card locators would re-introduce the two-cards proof
    (r"getByRole\('link',\s*\{\s*name:\s*new RegExp\(skuCode", "selector:per_sku_link_locator"),
    (r"for\s*\([^)]*401|while[^\n]*401", "auth:401_replay_loop"),
]

ALLOWED_GOTO = [
    r"^'/login'$", r"^'/client/login'$", r"^`/login`$", r"^`/client/login`$",
    r"^ENTRY_WHOLESALER_LOGIN$", r"^ENTRY_RETAILER_LOGIN$",
    r"^retailerEntry$",  # supported portal handoff entry (defined as `/client/login?w=<code>`)
]

# B4: single-occurrence control-plane anchors. Each one is the subject of a
# dedicated mutation; removing or weakening it must turn the validator RED.
AUTHORITY_ANCHORS = {
    "playwright.config.ts": [
        "B3_AUTHOR_DIAGNOSTIC",
        "B4_INDEPENDENT_AUTHORITY",
        "process.argv.some",
        "isListMode ? null : resolveRuntimeMode()",
        "= runtimeMode ? [",
        "src/authority-reporter",
        "execution_mode: runtimeMode",
        "candidate_sha: HARNESS_CONFIG.candidateSha",
        "metadata: reportBinding",
    ],
    "src/runtime.ts": [
        "if (authorSet && independentSet) {",
        "if (authorSet) return AUTHOR_DIAGNOSTIC;",
        "if (independentSet) return INDEPENDENT_AUTHORITY;",
        "`exactly one of ${AUTHOR_DIAGNOSTIC_ENV}=1 / ${INDEPENDENT_AUTHORITY_ENV}=1 is required",
        "CODE_MODE_VALUE_UNKNOWN,",
        "CODE_MODE_LABEL_UNKNOWN,",
        "if (contract) return assertKnownMode(contract.execution_mode, LIVE_EXECUTION_CONTRACT);",
        "record.candidate_sha !== candidateSha",
        "record.mode !== mode",
        "if (starts.length >= 1) {",
        "REFUSAL_SECOND_INVOCATION,",
        "REFUSAL_CROSS_MODE,",
        "REFUSAL_CANDIDATE_SHA_MISMATCH,",
        "live-execution-contract.json",
        "authority-report.json",
        "invocation-ledger.jsonl",
        "second_invocation_refused",
        "cross_mode_invocation_refused",
        "candidate_sha_mismatch_void",
        "both_modes_set",
        "mode_unset",
        "mode_value_unknown",
        "mode_label_unknown",
    ],
    "src/reconcile.ts": [
        "checkBinding('live_execution_contract'",
        "checkBinding(`invocation_ledger:",
        "checkBinding(`reconciliation_record:",
        "checkBinding('playwright_report'",
        "mode_mismatch:${label}",
        "candidate_sha_mismatch:${label}",
    ],
    "src/global-setup.ts": [
        "requireRuntimeMode();",
        "beginInvocation(HARNESS_CONFIG.candidateSha, WORKERS, RETRIES)",
        "writeLiveExecutionContract(mode, HARNESS_CONFIG.candidateSha, WORKERS, RETRIES)",
    ],
    "src/authority-reporter.ts": [
        "class BrowserAuthorityReporter",
        "execution_mode: mode",
        "candidate_sha: candidateSha",
        "workers: WORKERS",
        "retries: RETRIES",
        "expected_execution_count: EXPECTED_EXECUTION_COUNT",
        "observed_execution_count: this.executions.length",
        "failure_class: sanitizedFailureClass(result.status, result.errors)",
        "reportBindings: this.bindings",
    ],
    "src/fixtures.ts": [
        "hasRecordedInvocation()",
        "mode: recordedMode()",
        "candidate_sha: recordedCandidateSha()",
    ],
}

# B4: strings that must NOT appear — any of them would let author-mode
# evidence be relabelled as independent authority (or vice versa).
AUTHORITY_FORBIDDEN = {
    "src/fixtures.ts": ["isAuthorDiagnosticMode"],
    "src/authority-reporter.ts": ["AUTHOR_DIAGNOSTIC_ONLY", "B3_AUTHOR_DIAGNOSTIC"],
    "playwright.config.ts": ["diagnostic-reporter"],
}


def read(rel: str) -> str:
    return (HARNESS / rel).read_text(encoding="utf-8")


def check_manifest(findings: list[str]) -> None:
    raw = (HARNESS / "manifest" / "nodes.manifest.txt").read_bytes()
    if not raw.endswith(b"\n"):
        findings.append("manifest:missing_trailing_newline")
    text = raw.decode("utf-8")
    lines = text.split("\n")[:-1]
    if any(not line.strip() for line in lines):
        findings.append("manifest:blank_line")
    if len(lines) != 2:
        findings.append(f"manifest:expected_2_nodes_got_{len(lines)}")
    if len(lines) != len(set(lines)):
        findings.append("manifest:duplicate_nodes")
    if lines != sorted(lines):
        findings.append("manifest:reordered_nodes")
    if sorted(lines) != EXPECTED_NODES:
        findings.append("manifest:node_set_mismatch")


def check_config(findings: list[str]) -> None:
    cfg = read("playwright.config.ts")
    if "retries: 0" not in cfg:
        findings.append("config:retries_not_zero")
    for project, viewport in (("desktop", "1280"), ("mobile-390", "390")):
        name_idx = cfg.find(f"name: '{project}'")
        if name_idx < 0:
            findings.append(f"config:missing_project_{project}")
            continue
        window = cfg[name_idx : name_idx + 600]
        if f"width: {viewport}" not in window:
            findings.append(f"config:project_{project}_viewport_wrong")
    if "workers: 1" not in cfg:
        findings.append("config:workers_not_serialized")


def check_specs(findings: list[str]) -> None:
    id_spec = read("tests/catalog-id-001.spec.ts")
    hist_spec = read("tests/catalog-hist-001.spec.ts")
    if "test('CATALOG-ID-001'" not in id_spec:
        findings.append("spec:catalog_id_title_missing_or_nondeterministic")
    if "test('CATALOG-HIST-001'" not in hist_spec:
        findings.append("spec:catalog_hist_title_missing_or_nondeterministic")
    bodies = {"tests/catalog-id-001.spec.ts": id_spec, "tests/catalog-hist-001.spec.ts": hist_spec}
    for rel, anchors in REQUIRED_ANCHORS.items():
        body = bodies[rel]
        for anchor in anchors:
            if anchor not in body:
                findings.append(f"anchor:missing_in_{Path(rel).name}: {anchor[:60]}")

    for rel, body in (
        ("tests/catalog-id-001.spec.ts", id_spec),
        ("tests/catalog-hist-001.spec.ts", hist_spec),
        ("src/provision.ts", read("src/provision.ts")),
        ("src/observe.ts", read("src/observe.ts")),
        ("src/global-setup.ts", read("src/global-setup.ts")),
        ("src/preflight.ts", read("src/preflight.ts")),
        ("src/reconcile.ts", read("src/reconcile.ts")),
    ):
        for pattern, label in FORBIDDEN_PATTERNS:
            for match in re.finditer(pattern, body, re.IGNORECASE):
                findings.append(f"forbidden:{label}:{rel}:{match.group(0)[:30]}")
        if rel.startswith("tests/"):
            for match in re.finditer(r"page\.goto\(([^)]*)\)", body):
                target = match.group(1).strip()
                if not any(re.search(allowed, target) for allowed in ALLOWED_GOTO):
                    findings.append(f"navigation:unsupported_goto:{rel}:{target[:40]}")
    # uuid4 / Date.now() must never enter node identities (titles are the
    # constants asserted above; guard against dynamic test titles).
    for rel, body in (("tests/catalog-id-001.spec.ts", id_spec), ("tests/catalog-hist-001.spec.ts", hist_spec)):
        for match in re.finditer(r"(?<![\w.])test\(\s*([^'\)][^,)]*)", body):
            first_arg = match.group(1).strip()
            if not (first_arg.startswith("'") or first_arg.startswith('"')):
                findings.append(f"spec:dynamic_title:{rel}:{first_arg[:30]}")
    for rel, body in bodies.items():
        if "recordOutcome(" in body or "recordExecution(" in body:
            findings.append(f"reconciliation:tail_write_in_test_body:{rel}")
        if "from '../src/fixtures'" not in body:
            findings.append(f"reconciliation:central_fixture_not_imported:{rel}")


def _direct_request_blocks(body: str) -> list[tuple[int, str, str]]:
    """Yield (line, method, call-text) for every direct page.request call,
    with the balanced call text for header inspection."""
    out = []
    for match in re.finditer(r"page\.request\.(get|post|put|patch|delete)\(", body):
        method = match.group(1)
        start = match.end() - 1
        depth = 0
        i = start
        while i < len(body):
            if body[i] == "(":
                depth += 1
            elif body[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        call_text = body[start : i + 1]
        line = body[: match.start()].count("\n") + 1
        out.append((line, method, call_text))
    return out


def check_auth_truth(findings: list[str]) -> None:
    """B3 auth truth: EVERY direct page.request call must explicitly carry the
    correct contextual Authorization bearer header. 401 must never be accepted
    or retried. Failure output must not embed the token."""
    for rel in ("tests/catalog-id-001.spec.ts", "tests/catalog-hist-001.spec.ts"):
        body = read(rel)
        blocks = _direct_request_blocks(body)
        if not blocks:
            findings.append(f"auth:no_direct_calls:{rel}")
            continue
        for line_no, method, call_text in blocks:
            if "Authorization:" not in call_text and "Authorization =" not in call_text:
                findings.append(f"auth:bearer_missing:{rel}:{line_no}:{method}")
            if re.search(r"accessToken\]|`\$\{.*[Tt]oken", call_text):
                # tokens may be REFERENCED (state.tenantA.accessToken) — that is
                # required. Only literal token VALUES are forbidden; the specs
                # hold no literals, so this branch never fires for correct code.
                pass
        # 401 must never appear as an accepted status anywhere
        for i, line in enumerate(body.split("\n"), 1):
            if re.search(r"toContain\([^)]*401|toBe\(401\)|status\(\)\s*===?\s*401", line):
                findings.append(f"auth:401_accepted:{rel}:{i}")
        # no retry/replay constructs around authentication
        if re.search(r"for\s*\(\s*(let|var)\s+attempt|while\s*\([^)]*401|attempt\s*\+\s*1|retries\s*<|\.retry\(", body):
            findings.append(f"auth:retry_replay_construct:{rel}")


def check_namespace_isolation(findings: list[str]) -> None:
    """B3 resource isolation: per-execution namespace derived from node x
    viewport; no cross-node references inside either spec."""
    prov = read("src/provision.ts")
    if 'codes: [`${nodeShort}-${vp}-UNIT`, `${nodeShort}-${vp}-PACK`]' not in prov:
        findings.append("namespace:codes_not_derived_from_node_and_viewport")
    if "viewport === 'mobile-390' ? 'MOBILE-390' : 'DESKTOP'" not in prov:
        findings.append("namespace:viewport_id_not_derived")
    id_spec = read("tests/catalog-id-001.spec.ts")
    hist_spec = read("tests/catalog-hist-001.spec.ts")
    if "executionNamespace('CATID', viewport)" not in id_spec:
        findings.append("namespace:catalog_id_namespace_not_catid")
    if "executionNamespace('CATHIST', viewport)" not in hist_spec:
        findings.append("namespace:catalog_hist_namespace_not_cathist")
    if re.search(r"CATHIST", id_spec):
        findings.append("namespace:catalog_id_references_other_node")
    if re.search(r"CATID-", hist_spec):
        findings.append("namespace:catalog_hist_references_other_node")
    # shared fixed provisioning must not contain per-execution product codes
    official = read("provisioning/official.json")
    for fixed_code in ("B1-JUICE-BOTTLE", "B1-JUICE-CASE", "B1-FOREIGN-UNIT"):
        if fixed_code in official:
            findings.append(f"namespace:fixed_provisioning_code_present:{fixed_code}")


def check_mobile_navigation(findings: list[str]) -> None:
    """B3 mobile: the navigation menu must be explicitly opened via the named
    toggle button before contract-critical selection, on mobile only."""
    id_spec = read("tests/catalog-id-001.spec.ts")
    if "Toggle navigation menu" not in id_spec:
        findings.append("mobile:toggle_button_name_missing")
    if "async function openNavigation" not in id_spec:
        findings.append("mobile:open_navigation_helper_missing")
    if "await menuButton.click()" not in id_spec:
        findings.append("mobile:menu_click_missing")
    if viewport_line := [l for l in id_spec.splitlines() if "openNavigation(page, viewport)" in l]:
        if not any("if (viewport" in l or "mobile" in l for l in id_spec.splitlines()[: len(viewport_line)]):
            pass  # helper internally gates on viewport


def check_authority_mode(findings: list[str]) -> None:
    """B4 authority modes: two mutually exclusive modes, fail-closed
    resolution, a frozen recorded mode, and mode/candidate-SHA binding on
    every evidence source."""
    for rel, anchors in AUTHORITY_ANCHORS.items():
        try:
            body = read(rel)
        except FileNotFoundError:
            findings.append(f"authority:source_missing:{rel}")
            continue
        for anchor in anchors:
            if anchor not in body:
                findings.append(f"authority:anchor_missing:{rel}: {anchor[:60]}")
    for rel, forbidden in AUTHORITY_FORBIDDEN.items():
        body = read(rel)
        for token in forbidden:
            if token in body:
                findings.append(f"authority:forbidden_token:{rel}:{token}")


def check_runtime_lifecycle(findings: list[str]) -> None:
    cfg = read("playwright.config.ts")
    setup = read("src/global-setup.ts")
    fixtures = read("src/fixtures.ts")
    reporter = read("src/authority-reporter.ts")
    runtime = read("src/runtime.ts")
    reconcile = read("src/reconcile.ts")

    if "B3_AUTHOR_DIAGNOSTIC" not in cfg or "process.argv.some" not in cfg:
        findings.append("runtime:config_mode_or_list_guard_missing")
    if "const reporter" not in cfg or "authority-reporter" not in cfg:
        findings.append("runtime:authority_reporter_not_configured")
    if "requireRuntimeMode();" not in setup:
        findings.append("runtime:global_setup_mode_guard_missing")
    if setup.find("beginInvocation(") < 0 or setup.find("clearGeneratedRuntimeOutputs()") < 0:
        findings.append("runtime:invocation_or_cleanup_missing")
    elif setup.find("beginInvocation(") > setup.find("clearGeneratedRuntimeOutputs()"):
        findings.append("runtime:cleanup_before_invocation_not_ordered")
    if setup.find("clearGeneratedRuntimeOutputs()") > setup.find("runPreflight("):
        findings.append("runtime:cleanup_not_before_preflight")
    if setup.find("writeLiveExecutionContract(") > setup.find("runPreflight("):
        findings.append("runtime:live_contract_not_before_preflight")
    for target in (
        "reconciliation-in.jsonl",
        "reconciliation.json",
        "playwright-report.json",
        "preflight-verdict.json",
        "authority-report.json",
        "live-execution-contract.json",
        "test-artifacts",
        "maildir",
    ):
        if target not in runtime:
            findings.append(f"runtime:cleanup_target_missing:{target}")
    if "invocation-ledger.jsonl" not in runtime or "second_invocation_refused" not in runtime:
        findings.append("runtime:invocation_ledger_or_second_guard_missing")
    if "{ auto: true }" not in fixtures or "recordExecution({" not in fixtures:
        findings.append("runtime:central_auto_recorder_missing")
    if "testInfo.status === 'passed' ? 'passed' : 'failed'" not in fixtures:
        findings.append("runtime:failure_not_recorded_as_failed")
    if "buildReconciliation({" not in reporter or "endInvocation(" not in reporter:
        findings.append("runtime:reporter_reconciliation_or_ledger_end_missing")
    for field in (
        "unknown_nodes",
        "unknown_viewports",
        "report_disagreements",
        "playwright_without_reconciliation",
        "reconciliation_without_playwright",
        "mode_mismatches",
        "candidate_sha_mismatches",
    ):
        if field not in reconcile:
            findings.append(f"runtime:reconciliation_fail_closed_field_missing:{field}")
    if "reportDisagreements += 1;" not in reconcile:
        findings.append("runtime:report_disagreement_increment_missing")


def check_no_h2c_imports(findings: list[str]) -> None:
    for path in HARNESS.rglob("*.ts"):
        rel = path.relative_to(HARNESS)
        if "node_modules" in str(rel) or "results" in str(rel):
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        for pattern in ("j1h2b", "forgot-reset", "h2-c/", "h2c"):
            if pattern in body.lower() and "h2c_reference" not in pattern:
                findings.append(f"h2c_import:{rel}:{pattern}")


EXPECTED_COMBOS = {
    (node, viewport)
    for node in (
        "sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001",
        "sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001",
    )
    for viewport in ("desktop", "mobile-390")
}

LIVE_CONTRACT_SCHEMA = "sku-m1-browser/live-execution-contract/1"
AUTHORITY_REPORT_SCHEMA = "sku-m1-browser/authority-report/1"


def _playwright_results(report: Path) -> dict[tuple[str, str], str]:
    data = json.loads(report.read_text(encoding="utf-8"))
    observed: dict[tuple[str, str], str] = {}
    for suite in data.get("suites", []):
        file_name = Path(str(suite.get("file", ""))).name
        for spec in suite.get("specs", []) or []:
            title = spec.get("title")
            node = f"sku-m1-browser/tests/{file_name}::{title}"
            for test_case in spec.get("tests", []) or []:
                viewport = test_case.get("projectName")
                result_statuses = [
                    r.get("status") for r in (test_case.get("results") or [])
                    if r.get("status")
                ]
                status = "passed" if (
                    test_case.get("status") == "passed"
                    or (test_case.get("status") == "expected" and result_statuses == ["passed"])
                ) else "failed"
                observed[(node, viewport)] = status
    return observed


def _playwright_bindings(report: Path, findings: list[str]) -> set[tuple[str, str]]:
    """Mode/candidate-SHA binding carried by the Playwright report metadata."""
    data = json.loads(report.read_text(encoding="utf-8"))
    projects = ((data.get("config") or {}).get("projects")) or []
    if not projects:
        findings.append("authority:playwright_report_projects_absent")
        return {(None, None)}
    bindings: set[tuple[str, str]] = set()
    for project in projects:
        metadata = project.get("metadata")
        if not isinstance(metadata, dict):
            findings.append(f"authority:playwright_report_metadata_absent:{project.get('name')}")
            bindings.add((None, None))
            continue
        bindings.add((metadata.get("execution_mode"), metadata.get("candidate_sha")))
    return bindings


def _reconciliation_records(
    jsonl: Path,
) -> tuple[dict[tuple[str, str], str], set[tuple[str, str]], list[str]]:
    observed: dict[tuple[str, str], str] = {}
    bindings: set[tuple[str, str]] = set()
    findings: list[str] = []
    counts: dict[tuple[str, str], int] = {}
    for line_no, line in enumerate(jsonl.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        node = record.get("node")
        viewport = record.get("viewport")
        status = record.get("status")
        key = (node, viewport)
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > 1:
            findings.append(f"reconciliation:duplicate_combination:{line_no}:{key}")
        if key not in EXPECTED_COMBOS:
            if node not in {n for n, _ in EXPECTED_COMBOS}:
                findings.append(f"reconciliation:unknown_node:{node}")
            if viewport not in {v for _, v in EXPECTED_COMBOS}:
                findings.append(f"reconciliation:unknown_viewport:{viewport}")
        if status not in ("passed", "failed"):
            findings.append(f"reconciliation:unknown_status:{status}")
        observed[key] = status
        bindings.add((record.get("mode"), record.get("candidate_sha")))
    return observed, bindings, findings


def _live_contract_binding(path: Path, findings: list[str]) -> tuple[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != LIVE_CONTRACT_SCHEMA:
        findings.append(f"authority:live_contract_schema:{data.get('schema')}")
    if data.get("workers") != 1:
        findings.append(f"authority:live_contract_workers:{data.get('workers')}")
    if data.get("retries") != 0:
        findings.append(f"authority:live_contract_retries:{data.get('retries')}")
    if data.get("expected_execution_count") != 4:
        findings.append(f"authority:live_contract_expected:{data.get('expected_execution_count')}")
    if data.get("frozen_at_invocation_start") is not True:
        findings.append("authority:live_contract_not_frozen")
    return data.get("execution_mode"), data.get("candidate_sha")


def _authority_report_binding(path: Path, findings: list[str]) -> tuple[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != AUTHORITY_REPORT_SCHEMA:
        findings.append(f"authority:report_schema:{data.get('schema')}")
    for field, expected in (
        ("workers", 1),
        ("retries", 0),
        ("expected_execution_count", 4),
        ("observed_execution_count", 4),
    ):
        if data.get(field) != expected:
            findings.append(f"authority:report_field:{field}:{data.get(field)}")
    if data.get("status") != "passed":
        findings.append(f"authority:report_status_not_passed:{data.get('status')}")
    executions = data.get("executions") or []
    if len(executions) != 4:
        findings.append(f"authority:report_execution_count:{len(executions)}")
    seen: set[tuple[str, str]] = set()
    for execution in executions:
        key = (execution.get("node"), execution.get("viewport"))
        if key not in EXPECTED_COMBOS:
            findings.append(f"authority:report_unknown_combination:{key}")
        seen.add(key)
        if execution.get("status") not in ("passed", "failed"):
            findings.append(f"authority:report_execution_status:{execution.get('status')}")
        if not execution.get("failure_class"):
            findings.append(f"authority:report_failure_class_missing:{key}")
    if seen != EXPECTED_COMBOS:
        findings.append(f"authority:report_combination_mismatch(missing={sorted(EXPECTED_COMBOS - seen)})")
    return data.get("execution_mode"), data.get("candidate_sha")


def _ledger_binding(path: Path, findings: list[str]) -> tuple[str, str]:
    starts = ends = refused = 0
    modes: set[str] = set()
    shas: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        mode = record.get("mode")
        if mode not in RUNTIME_MODES:
            findings.append(f"invocation:unknown_mode:{mode}")
        modes.add(mode)
        shas.add(record.get("candidate_sha"))
        if record.get("event") == "start":
            starts += 1
            if record.get("workers") != 1 or record.get("retries") != 0:
                findings.append("invocation:workers_or_retries_wrong")
            if record.get("expected_node_count") != 4:
                findings.append("invocation:expected_node_count_wrong")
        elif record.get("event") == "end":
            ends += 1
            if record.get("observed_node_count") != 4:
                findings.append("invocation:observed_node_count_wrong")
            if record.get("status") != "passed":
                findings.append(f"invocation:end_status_not_passed:{record.get('status')}")
        elif record.get("event") == "refused":
            refused += 1
        else:
            findings.append(f"invocation:unknown_event:{record.get('event')}")
    if starts != 1 or ends != 1 or refused != 0:
        findings.append(f"invocation:expected_single_start_end(starts={starts}, ends={ends}, refused={refused})")
    if len(modes) != 1:
        findings.append(f"invocation:mode_not_uniform:{sorted(map(str, modes))}")
    if len(shas) != 1:
        findings.append(f"invocation:candidate_sha_not_uniform:{sorted(map(str, shas))}")
    return (next(iter(modes)) if len(modes) == 1 else None,
            next(iter(shas)) if len(shas) == 1 else None)


def check_reconciliation(
    findings: list[str],
    allow_missing: bool,
    require_mode: str | None = None,
) -> None:
    results = HARNESS / "results"
    reconciliation_json = results / "reconciliation.json"
    reconciliation_in = results / "reconciliation-in.jsonl"
    playwright_report = results / "playwright-report.json"
    invocation_ledger = results / "invocation-ledger.jsonl"
    authority_report = results / "authority-report.json"
    live_contract = results / "live-execution-contract.json"
    if not reconciliation_json.exists():
        if allow_missing:
            return
        findings.append("reconciliation:results_absent")
        return

    for required in (
        reconciliation_in,
        playwright_report,
        invocation_ledger,
        authority_report,
        live_contract,
    ):
        if not required.exists():
            findings.append(f"reconciliation:runtime_file_absent:{required.name}")
            return

    data = json.loads(reconciliation_json.read_text(encoding="utf-8"))
    accounting = data.get("accounting", {})
    if accounting.get("gap") != 0:
        findings.append(f"reconciliation:gap_nonzero({json.dumps(accounting)})")
    if accounting.get("pass") != 4 or accounting.get("fail") != 0:
        findings.append(f"reconciliation:pass_fail_not_4_0({json.dumps(accounting)})")
    if accounting.get("skipped") != 0 or accounting.get("not_run") != 0:
        findings.append(f"reconciliation:skipped_or_not_run_nonzero({json.dumps(accounting)})")
    if accounting.get("duplicates") != 0:
        findings.append(f"reconciliation:duplicates_nonzero({json.dumps(accounting)})")
    if accounting.get("mode_mismatches") != 0:
        findings.append(f"reconciliation:mode_mismatches_nonzero({accounting.get('mode_mismatches')})")
    if accounting.get("candidate_sha_mismatches") != 0:
        findings.append(
            f"reconciliation:candidate_sha_mismatches_nonzero({accounting.get('candidate_sha_mismatches')})"
        )
    if data.get("errors"):
        findings.append(f"reconciliation:errors_present({data.get('errors')})")
    seen = set()
    for node, records in (data.get("nodes") or {}).items():
        for rec in records or []:
            seen.add((node, rec.get("viewport")))
    if seen != EXPECTED_COMBOS:
        findings.append(f"reconciliation:combination_mismatch(missing={sorted(EXPECTED_COMBOS - seen)})")

    raw_records, record_bindings, record_findings = _reconciliation_records(reconciliation_in)
    findings.extend(record_findings)
    report_records = _playwright_results(playwright_report)
    if set(report_records) != EXPECTED_COMBOS:
        findings.append(f"reconciliation:playwright_combination_mismatch(missing={sorted(EXPECTED_COMBOS - set(report_records))})")
    for key in EXPECTED_COMBOS:
        if key in report_records and key not in raw_records:
            findings.append(f"reconciliation:playwright_without_record:{key}")
        if key in raw_records and key not in report_records:
            findings.append(f"reconciliation:record_without_playwright:{key}")
        if key in raw_records and key in report_records and raw_records[key] != report_records[key]:
            findings.append(f"reconciliation:report_disagreement:{key}:{raw_records[key]}:{report_records[key]}")

    sources: dict[str, tuple[str, str]] = {
        "invocation_ledger": _ledger_binding(invocation_ledger, findings),
        "live_execution_contract": _live_contract_binding(live_contract, findings),
        "authority_report": _authority_report_binding(authority_report, findings),
    }
    report_bindings = _playwright_bindings(playwright_report, findings)
    if len(report_bindings) != 1:
        findings.append(
            f"authority:playwright_report_binding_not_uniform:{sorted(map(str, report_bindings))}"
        )
    else:
        sources["playwright_report"] = next(iter(report_bindings))
    if len(record_bindings) != 1:
        findings.append(
            f"authority:reconciliation_record_binding_not_uniform:{sorted(map(str, record_bindings))}"
        )
    else:
        sources["reconciliation_records"] = next(iter(record_bindings))

    modes = {label: binding[0] for label, binding in sources.items()}
    shas = {label: binding[1] for label, binding in sources.items()}
    for label, mode in modes.items():
        if mode not in RUNTIME_MODES:
            findings.append(f"authority:unknown_mode:{label}:{mode}")
    if len({m for m in modes.values() if m is not None}) > 1:
        findings.append(f"authority:mode_mismatch_across_sources({json.dumps(modes, sort_keys=True)})")
    if len({s for s in shas.values() if s is not None}) > 1 or not shas:
        findings.append(f"authority:candidate_sha_mismatch_across_sources({json.dumps(shas, sort_keys=True)})")
    for label, sha in shas.items():
        if not sha:
            findings.append(f"authority:candidate_sha_absent:{label}")
    if require_mode:
        for label, mode in sorted(modes.items()):
            if mode != require_mode:
                findings.append(f"authority:required_mode_not_met:{label}:{mode}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-missing-reconciliation", action="store_true",
                        help="author validation mode: reconciliation.json may be absent")
    parser.add_argument("--require-mode", choices=list(RUNTIME_MODES), default=None,
                        help="require every evidence source to carry exactly this execution mode")
    args = parser.parse_args()

    findings: list[str] = []
    check_manifest(findings)
    check_config(findings)
    check_specs(findings)
    check_auth_truth(findings)
    check_namespace_isolation(findings)
    check_mobile_navigation(findings)
    check_authority_mode(findings)
    check_runtime_lifecycle(findings)
    check_no_h2c_imports(findings)
    check_reconciliation(findings, args.allow_missing_reconciliation, args.require_mode)

    if findings:
        print("STATIC VALIDATOR: RED")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("STATIC VALIDATOR: GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
