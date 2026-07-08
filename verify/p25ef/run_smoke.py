"""
P25-EF Real-Stack Smoke Orchestrator.

Starts backend (uvicorn) + frontend (vite) as subprocesses, waits for
readiness, runs identity smoke + route smoke, captures all evidence,
then cleanly shuts down both servers.

Usage:
  cd c:\\Users\\Jeff0\\MPANGO ERP\\_p25ef_2026-07-08\\backend
  python ../verify/p25ef/run_smoke.py
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = SCRIPT_DIR.parent.parent / "backend"
FRONTEND_DIR = SCRIPT_DIR.parent.parent / "frontend"
EVIDENCE_DIR = SCRIPT_DIR
SHOTS_DIR = EVIDENCE_DIR / "screenshots"
SHOTS_DIR.mkdir(exist_ok=True)

# -- Environment for backend --
BACKEND_ENV = {
    **os.environ,
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
    "MPANGO_ENV": "production",
    # All secrets below are THROWAWAY test-only values for the disposable smoke
    # stack (local Docker Postgres on :5433). They are NOT production secrets.
    "DATABASE_URL": "postgresql://mpango:p25ec_throwaway_pw@localhost:5433/mpango_erp",  # pragma: allowlist secret
    "REDIS_URL": "redis://localhost:6379/1",
    "SECRET_KEY": "pHFmxXthWP58Gng5AILZ6yyw4GhIVTbf6wUJ2S8RQyU",  # pragma: allowlist secret
    "PLATFORM_OPERATOR_SECRET": "test-operator-secret",  # pragma: allowlist secret
    "PLATFORM_TEST_OVERRIDE_SECRET": "test-platform-override-secret",  # pragma: allowlist secret
    "ENABLE_METRICS": "false",
    "ENABLE_SQL_PROFILING": "false",
    "REPORTING_DATABASE_URL": "postgresql+asyncpg://mpango:p25ec_throwaway_pw@localhost:5433/mpango_erp",  # pragma: allowlist secret
}

BACKEND_PORT = 8000
FRONTEND_PORT = 5173
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"

backend_proc = None
frontend_proc = None


def wait_for_url(url, timeout=30, interval=1):
    """Poll a URL until it responds or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=3)
            return True
        except urllib.error.HTTPError:
            return True  # Server responded (even if error status)
        except Exception:
            time.sleep(interval)
    return False


def start_backend():
    """Start uvicorn backend as subprocess."""
    global backend_proc
    log_file = open(EVIDENCE_DIR / "backend_stdout.log", "w", encoding="utf-8")
    err_file = open(EVIDENCE_DIR / "backend_stderr.log", "w", encoding="utf-8")
    backend_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", "0.0.0.0", "--port", str(BACKEND_PORT),
        ],
        cwd=str(BACKEND_DIR),
        env=BACKEND_ENV,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    print(f"Backend started (PID {backend_proc.pid})")
    ready = wait_for_url(f"{BACKEND_URL}/docs", timeout=30)
    if ready:
        print("Backend READY")
    else:
        print("Backend FAILED to start within 30s")
    return ready


def start_frontend():
    """Start Vite dev server as subprocess."""
    global frontend_proc
    # node_modules was installed via pnpm in frontend/. Run the npm "dev"
    # script through cmd so the path with spaces and .bin resolution works.
    log_file = open(EVIDENCE_DIR / "frontend_stdout.log", "w", encoding="utf-8")
    frontend_proc = subprocess.Popen(
        f'cmd /c "npm run dev -- --host 127.0.0.1 --strictPort"',
        cwd=str(FRONTEND_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        shell=True,
    )
    print(f"Frontend started (PID {frontend_proc.pid})")
    ready = wait_for_url(FRONTEND_URL, timeout=90)
    if ready:
        print("Frontend READY")
    else:
        print("Frontend FAILED to start within 30s")
    return ready


def shutdown():
    """Cleanly shutdown backend and frontend."""
    global backend_proc, frontend_proc
    for name, proc in [("backend", backend_proc), ("frontend", frontend_proc)]:
        if proc and proc.poll() is None:
            print(f"Shutting down {name} (PID {proc.pid})...")
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            print(f"{name} stopped")


def run_identity_smoke():
    """Run the 6-case identity smoke test against the backend."""
    print("\n" + "=" * 70)
    print("Running Identity Smoke Test")
    print("=" * 70)

    # Import from the existing P25-EC identity smoke script
    sys.path.insert(0, str(BACKEND_DIR))
    from core.security import create_identity_token, create_contextual_token

    BASE_URL = BACKEND_URL
    ENDPOINT = "/api/v1/platform/p24/incident-closeouts"
    FULL_URL = BASE_URL + ENDPOINT

    OPERATOR_SECRET = "test-operator-secret"  # pragma: allowlist secret

    SMOKE_TENANT_ID = "00000000-0000-0000-0000-000000000099"
    SMOKE_USER_ID = "00000000-0000-0000-0000-000000000002"
    SMOKE_TENANT_SCHEMA = "t_smoke_r1"

    identity_jwt = create_identity_token(
        user_id="00000000-0000-0000-0000-000000000001",
        roles=["super_admin"],
    )
    tenant_jwt = create_contextual_token(
        user_id=SMOKE_USER_ID,
        roles=["super_admin"],
        tenant_id=SMOKE_TENANT_ID,
        tenant_schema=SMOKE_TENANT_SCHEMA,
    )

    cases = [
        ("operator_admit", {"X-Platform-Operator": OPERATOR_SECRET}, {200},
         "Valid X-Platform-Operator secret admitted"),
        ("test_override_reject", {"X-Platform-Test-Override": "test-platform-override-secret"}, {403},
         "X-Platform-Test-Override rejected in production env (403)"),
        ("identity_super_admin_admit", {"Authorization": "Bearer " + identity_jwt}, {200},
         "Identity-only super_admin Bearer admitted"),
        ("no_credentials_deny", {}, {401},
         "No credentials denied (401)"),
        ("wrong_operator_deny", {"X-Platform-Operator": "wrong-secret-value"}, {403},
         "Wrong operator secret denied (403)"),
        ("tenant_context_admin_deny", {"Authorization": "Bearer " + tenant_jwt}, {401, 403},
         "Tenant-context super_admin denied cleanly (401/403, NOT 500)"),
    ]

    results = []
    for name, headers, expected, desc in cases:
        req = urllib.request.Request(FULL_URL, method="GET")
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            status = resp.status
            body = resp.read().decode()[:300]
            passed = status in expected
        except urllib.error.HTTPError as e:
            status = e.code
            body = e.read().decode()[:300]
            passed = status in expected
        except Exception as e:
            status = -1
            body = str(e)[:300]
            passed = False

        marker = "PASS" if passed else "FAIL"
        print(f"  [{marker}] {name}: got {status} (expected {sorted(expected)})")
        results.append({
            "test": name,
            "description": desc,
            "expected_status": sorted(list(expected)),
            "actual_status": status,
            "passed": passed,
            "body_preview": body,
        })

    passed_count = sum(1 for r in results if r["passed"])
    print(f"\nIdentity Smoke: {passed_count}/{len(results)} passed")

    return {
        "test_suite": "P25-EF Identity Smoke",
        "endpoint": FULL_URL,
        "summary": {"total": len(results), "passed": passed_count, "failed": len(results) - passed_count},
        "cases": results,
    }


def run_route_smoke():
    """Run the 19-route Playwright browser smoke."""
    print("\n" + "=" * 70)
    print("Running 19-Route Playwright Browser Smoke")
    print("=" * 70)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  SKIP: playwright not installed")
        return {"test_suite": "P25-EF Route Smoke", "error": "playwright not installed"}

    from core.security import create_identity_token

    ROUTES = [
        {"path": "/platform", "name": "Platform Overview"},
        {"path": "/platform/system/health", "name": "System Health"},
        {"path": "/platform/tenants", "name": "Tenant Directory"},
        {"path": "/platform/tenants/smoke-tenant-1/health", "name": "Tenant Health"},
        {"path": "/platform/audit", "name": "Audit Events"},
        {"path": "/platform/registry", "name": "Registry"},
        {"path": "/platform/support", "name": "Support Console"},
        {"path": "/platform/ops/health", "name": "Ops Health"},
        {"path": "/platform/ops/errors", "name": "Ops Errors"},
        {"path": "/platform/ops/slow-routes", "name": "Ops Slow Routes"},
        {"path": "/platform/ops/resources", "name": "Ops Resources"},
        {"path": "/platform/ops/noisy-neighbors", "name": "Ops Noisy Neighbors"},
        {"path": "/platform/ops/incidents/triage", "name": "Incident Triage"},
        {"path": "/platform/controlled-actions", "name": "Controlled Actions"},
        {"path": "/platform/approvals", "name": "Approvals"},
        {"path": "/platform/durable-approvals", "name": "Durable Approvals"},
        {"path": "/platform/controlled-execution", "name": "Controlled Execution"},
        {"path": "/platform/operator-tasks", "name": "Operator Tasks"},
        {"path": "/platform/incident-closeouts", "name": "Incident Closeouts"},
    ]

    FORBIDDEN_SELECTORS = [
        'button:has-text("Execute")',
        'button:has-text("Delete")',
        'button:has-text("Destroy")',
        'button:has-text("Drop")',
        'button:has-text("Truncate")',
        'button:has-text("Purge")',
        'button:has-text("Restore")',
        'button:has-text("Run Migration")',
        'button:has-text("Deploy")',
    ]

    jwt_token = create_identity_token(
        user_id="00000000-0000-0000-0000-000000000001",
        roles=["super_admin"],
    )
    auth_json = json.dumps({
        "state": {
            "accessToken": jwt_token,
            "refreshToken": None,
            "user": {
                "id": "u-super",
                "email": "super@mpango.example",
                "full_name": "Super Admin",
                "tenant_id": None,
                "tenant_schema": None,
                "roles": ["super_admin"],
                "permissions": [],
            },
            "tenantCode": None,
        },
        "version": 0,
    })

    results = []

    with sync_playwright() as pw:
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        launch_opts = {"headless": True}
        if os.path.exists(chrome_path):
            launch_opts["executable_path"] = chrome_path
        elif os.path.exists(edge_path):
            launch_opts["executable_path"] = edge_path

        browser = pw.chromium.launch(**launch_opts)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        context.add_init_script(
            "try { localStorage.setItem('mpango-auth', " + json.dumps(auth_json) + "); } catch(e) {}"
        )
        page = context.new_page()

        for i, route in enumerate(ROUTES, 1):
            path = route["path"]
            full_url = FRONTEND_URL + path
            shot_name = path.strip("/").replace("/", "_") or "root"
            shot_path = SHOTS_DIR / (shot_name + ".png")

            console_errors = []
            page_errors = []

            def on_console(msg):
                if msg.type == "error":
                    console_errors.append(msg.text[:200])

            def on_page_err(err):
                page_errors.append(str(err)[:200])

            page.on("console", on_console)
            page.on("pageerror", on_page_err)

            try:
                response = page.goto(full_url, wait_until="domcontentloaded", timeout=20000)
                http_status = response.status if response else 0
            except Exception as e:
                http_status = -1
                console_errors.append("Nav error: " + str(e)[:200])
                response = None

            time.sleep(3)

            forbidden_found = []
            for sel in FORBIDDEN_SELECTORS:
                try:
                    count = page.locator(sel).count()
                    if count > 0:
                        forbidden_found.append(sel)
                except Exception:
                    pass

            try:
                title = page.title()
            except Exception:
                title = "(unknown)"
            try:
                final_url = page.url
            except Exception:
                final_url = full_url

            try:
                page.screenshot(path=str(shot_path), full_page=True)
                shot_ok = True
                shot_size = shot_path.stat().st_size
            except Exception:
                shot_ok = False
                shot_size = 0

            page.remove_listener("console", on_console)
            page.remove_listener("pageerror", on_page_err)

            redirected = final_url != full_url
            errs = len(console_errors) + len(page_errors)
            has_5xx = any("500" in e for e in console_errors)

            status_str = str(http_status)
            print(f"  [{i:2d}/19] {route['name']:<25s} HTTP {status_str:>3s} | errs={errs} | forbidden={len(forbidden_found)} | shot={'OK' if shot_ok else 'FAIL'}{' REDIR' if redirected else ''}")

            results.append({
                "route": path,
                "name": route["name"],
                "http_status": http_status,
                "redirected": redirected,
                "final_url": final_url,
                "title": title,
                "console_errors": console_errors,
                "page_errors": page_errors,
                "forbidden_controls": forbidden_found,
                "has_5xx": has_5xx,
                "screenshot": {"file": shot_name + ".png", "captured": shot_ok, "bytes": shot_size},
            })

        browser.close()

    total = len(results)
    ok = sum(1 for r in results if r["http_status"] == 200)
    redirected = sum(1 for r in results if r["redirected"])
    with_errors = sum(1 for r in results if r["console_errors"] or r["page_errors"])
    with_5xx = sum(1 for r in results if r["has_5xx"])
    with_forbidden = sum(1 for r in results if r["forbidden_controls"])
    shots_ok = sum(1 for r in results if r["screenshot"]["captured"])

    print(f"\nRoute Smoke Summary: {total} routes | HTTP-200={ok} | redirected={redirected} | errors={with_errors} | 5xx={with_5xx} | forbidden={with_forbidden} | shots={shots_ok}/{total}")

    return {
        "test_suite": "P25-EF Route Smoke",
        "base_url": FRONTEND_URL,
        "browser": "chromium (headless)",
        "auth": "identity-only super_admin JWT",
        "summary": {
            "total_routes": total,
            "http_200": ok,
            "redirected": redirected,
            "routes_with_errors": with_errors,
            "routes_with_5xx": with_5xx,
            "routes_with_forbidden": with_forbidden,
            "screenshots_captured": shots_ok,
        },
        "routes": results,
    }


def grep_backend_logs():
    """Grep backend logs for TenantContextMissingError and 500 errors."""
    print("\n" + "=" * 70)
    print("Grepping Backend Logs")
    print("=" * 70)

    log_path = EVIDENCE_DIR / "backend_stdout.log"
    if not log_path.exists():
        return {"error": "no backend log"}

    content = log_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()

    tcm_errors = [l for l in lines if "TenantContextMissingError" in l]
    http_500s = [l for l in lines if "500" in l and ("Internal Server Error" in l or "ERROR" in l)]
    tracebacks = [l for l in lines if "Traceback" in l or "raise " in l]

    print(f"  TenantContextMissingError occurrences: {len(tcm_errors)}")
    print(f"  HTTP 500 / ERROR lines: {len(http_500s)}")
    print(f"  Traceback lines: {len(tracebacks)}")

    for l in tcm_errors[:5]:
        print(f"  TCM: {l[:120]}")
    for l in http_500s[:5]:
        print(f"  500: {l[:120]}")

    return {
        "tenant_context_missing_errors": len(tcm_errors),
        "http_500_error_lines": len(http_500s),
        "traceback_lines": len(tracebacks),
        "tcm_samples": tcm_errors[:5],
        "http500_samples": http_500s[:5],
    }


def main():
    print("=" * 70)
    print("P25-EF: Real-Stack Smoke Orchestrator")
    print(f"Backend: {BACKEND_URL}  |  Frontend: {FRONTEND_URL}")
    print("=" * 70)

    # Apply backend env to THIS process so importing core.config / core.security
    # (needed for token generation) passes pydantic settings validation.
    for k, v in {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "MPANGO_ENV": "production",
        "DATABASE_URL": BACKEND_ENV["DATABASE_URL"],
        "REDIS_URL": BACKEND_ENV["REDIS_URL"],
        "SECRET_KEY": BACKEND_ENV["SECRET_KEY"],
        "PLATFORM_OPERATOR_SECRET": BACKEND_ENV["PLATFORM_OPERATOR_SECRET"],
        "PLATFORM_TEST_OVERRIDE_SECRET": BACKEND_ENV["PLATFORM_TEST_OVERRIDE_SECRET"],
        "ENABLE_METRICS": "false",
        "ENABLE_SQL_PROFILING": "false",
        "REPORTING_DATABASE_URL": BACKEND_ENV["REPORTING_DATABASE_URL"],
    }.items():
        os.environ[k] = v

    evidence = {
        "task": "P25-EF",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "backend_port": BACKEND_PORT,
        "frontend_port": FRONTEND_PORT,
    }

    try:
        # 1. Start backend
        if not start_backend():
            evidence["error"] = "Backend failed to start"
            evidence["backend_log_tail"] = (EVIDENCE_DIR / "backend_stdout.log").read_text(encoding="utf-8", errors="replace")[-2000:] if (EVIDENCE_DIR / "backend_stdout.log").exists() else ""
            (EVIDENCE_DIR / "smoke_result.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print("ABORT: Backend not ready")
            return

        # 2. Start frontend
        if not start_frontend():
            evidence["error"] = "Frontend failed to start"
            evidence["backend_log_tail"] = (EVIDENCE_DIR / "backend_stdout.log").read_text(encoding="utf-8", errors="replace")[-2000:]
            (EVIDENCE_DIR / "smoke_result.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print("ABORT: Frontend not ready")
            return

        # 3. Run identity smoke
        evidence["identity_smoke"] = run_identity_smoke()

        # 4. Run route smoke
        evidence["route_smoke"] = run_route_smoke()

        # 5. Grep logs
        evidence["log_grep"] = grep_backend_logs()

    finally:
        shutdown()

    # Write evidence
    out_path = EVIDENCE_DIR / "smoke_result.json"
    out_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"\nEvidence written to {out_path}")

    # Print verdict
    identity_ok = evidence.get("identity_smoke", {}).get("summary", {}).get("failed", 1) == 0
    route_summary = evidence.get("route_smoke", {}).get("summary", {})
    route_ok = route_summary.get("http_200", 0) == 19 and route_summary.get("routes_with_5xx", 1) == 0
    log_ok = evidence.get("log_grep", {}).get("tenant_context_missing_errors", 1) == 0

    print("\n" + "=" * 70)
    print("VERDICT:")
    print(f"  Identity smoke: {'PASS' if identity_ok else 'FAIL'}")
    print(f"  Route smoke 19/200: {'PASS' if route_ok else 'FAIL'}")
    print(f"  Log grep 0 TCM: {'PASS' if log_ok else 'FAIL'}")
    if identity_ok and route_ok and log_ok:
        print("  OVERALL: P25EF_AUDIT_RESULT_RECORDED_BOUNDARY_FIX")
    else:
        print("  OVERALL: ISSUES FOUND - see evidence")
    print("=" * 70)


if __name__ == "__main__":
    main()
