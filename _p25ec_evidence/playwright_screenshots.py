"""
P25-EC Part D: 19-Route Playwright Chromium Real-Stack Browser Smoke.

Navigates to all 19 PLATFORM_ROUTES against the real Vite dev server (port 5173)
+ real backend (port 8000) + real Docker Postgres (port 5433). Captures:

  - HTTP response status (from the HTML document load)
  - Console errors (pageerror + console.error)
  - Landmarks (h1, h2, nav, main, table, [data-testid] count)
  - Forbidden-controls scan (dangerous action buttons that should be inert)
  - Full-page PNG screenshot per route

Auth state is injected into localStorage as an identity-only super_admin via the
zustand persist key ``mpango-auth`` (mirrors the real login flow).

Usage:
  cd backend
  python ../_p25ec_evidence/playwright_screenshots.py
"""
import json
import os
import sys
import time
from pathlib import Path

# Ensure backend imports resolve for JWT generation
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND_DIR)

from playwright.sync_api import sync_playwright

# -- Config ------------------------------------------------------------------

BASE_URL = "http://localhost:5173"
SHOTS_DIR = Path(__file__).parent / "screenshots"
SHOTS_DIR.mkdir(exist_ok=True)

# 19 routes from PLATFORM_ROUTES (readiness.tsx); tenant-health uses a dummy id.
ROUTES = [
    {"path": "/platform", "name": "Platform Overview", "group": "overview"},
    {"path": "/platform/system/health", "name": "System Health", "group": "health"},
    {"path": "/platform/tenants", "name": "Tenant Directory", "group": "registry"},
    {"path": "/platform/tenants/smoke-tenant-1/health", "name": "Tenant Health", "group": "health"},
    {"path": "/platform/audit", "name": "Audit Events", "group": "overview"},
    {"path": "/platform/registry", "name": "Registry", "group": "registry"},
    {"path": "/platform/support", "name": "Support Console", "group": "support"},
    {"path": "/platform/ops/health", "name": "Ops Health", "group": "ops"},
    {"path": "/platform/ops/errors", "name": "Ops Errors", "group": "ops"},
    {"path": "/platform/ops/slow-routes", "name": "Ops Slow Routes", "group": "ops"},
    {"path": "/platform/ops/resources", "name": "Ops Resources", "group": "ops"},
    {"path": "/platform/ops/noisy-neighbors", "name": "Ops Noisy Neighbors", "group": "ops"},
    {"path": "/platform/ops/incidents/triage", "name": "Incident Triage", "group": "ops"},
    {"path": "/platform/controlled-actions", "name": "Controlled Actions", "group": "actions"},
    {"path": "/platform/approvals", "name": "Approvals", "group": "approvals"},
    {"path": "/platform/durable-approvals", "name": "Durable Approvals", "group": "approvals"},
    {"path": "/platform/controlled-execution", "name": "Controlled Execution", "group": "execution"},
    {"path": "/platform/operator-tasks", "name": "Operator Tasks", "group": "tasks"},
    {"path": "/platform/incident-closeouts", "name": "Incident Closeouts", "group": "closeouts"},
]

# Forbidden control patterns: buttons/links that should NOT be active in a
# read-only / non-executing platform surface.
FORBIDDEN_CONTROL_SELECTORS = [
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

# Landmark selectors for structural validation.
LANDMARK_SELECTORS = {
    "h1": "h1",
    "h2": "h2",
    "nav": "nav",
    "main": "main, [role=main]",
    "table": "table",
    "cards": "[class*='card'], [class*='Card']",
    "testids": "[data-testid]",
    "buttons": "button",
    "links": "a",
}


def generate_auth_jwt():
    """Generate an identity-only super_admin JWT for localStorage injection."""
    from core.security import create_identity_token
    return create_identity_token(
        user_id="00000000-0000-0000-0000-000000000001",
        roles=["super_admin"],
    )


def build_auth_storage(jwt_token: str) -> str:
    """Build the zustand persist JSON for localStorage key 'mpango-auth'."""
    return json.dumps({
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


def scan_route(page, route_entry):
    """Navigate to one route, capture metrics, return a result dict."""
    path = route_entry["path"]
    full_url = BASE_URL + path
    screenshot_name = path.strip("/").replace("/", "_") or "root"
    screenshot_path = SHOTS_DIR / f"{screenshot_name}.png"

    console_errors = []
    page_errors = []

    def on_console_msg(msg):
        if msg.type == "error":
            console_errors.append(msg.text[:200])

    def on_page_error(err):
        page_errors.append(str(err)[:200])

    page.on("console", on_console_msg)
    page.on("pageerror", on_page_error)

    # Navigate
    try:
        response = page.goto(full_url, wait_until="domcontentloaded", timeout=20000)
        http_status = response.status if response else 0
    except Exception as e:
        http_status = -1
        console_errors.append(f"Navigation error: {str(e)[:200]}")
        response = None

    # Wait for React hydration + async data fetches to settle
    time.sleep(3)

    # Landmarks
    landmarks = {}
    for name, selector in LANDMARK_SELECTORS.items():
        try:
            landmarks[name] = page.locator(selector).count()
        except Exception:
            landmarks[name] = -1

    # Forbidden controls
    forbidden_found = []
    for sel in FORBIDDEN_CONTROL_SELECTORS:
        try:
            count = page.locator(sel).count()
            if count > 0:
                forbidden_found.append({"selector": sel, "count": count})
        except Exception:
            pass

    # Page title
    try:
        title = page.title()
    except Exception:
        title = "(unknown)"

    # Final URL (may have redirected)
    try:
        final_url = page.url
    except Exception:
        final_url = full_url

    # Screenshot
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        screenshot_ok = True
        screenshot_size = screenshot_path.stat().st_size
    except Exception as e:
        screenshot_ok = False
        screenshot_size = 0
        console_errors.append(f"Screenshot error: {str(e)[:200]}")

    # Clean up listeners
    page.remove_listener("console", on_console_msg)
    page.remove_listener("pageerror", on_page_error)

    redirected = final_url != full_url

    return {
        "route": path,
        "name": route_entry["name"],
        "group": route_entry["group"],
        "url": full_url,
        "final_url": final_url,
        "redirected": redirected,
        "http_status": http_status,
        "title": title,
        "landmarks": landmarks,
        "forbidden_controls": forbidden_found,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshot": {
            "file": screenshot_name + ".png",
            "captured": screenshot_ok,
            "bytes": screenshot_size,
        },
    }


def main():
    print("=" * 70)
    print("P25-EC Part D: 19-Route Playwright Browser Smoke")
    print(f"Target: {BASE_URL}")
    print(f"Routes: {len(ROUTES)}")
    print("=" * 70)

    jwt_token = generate_auth_jwt()
    auth_json = build_auth_storage(jwt_token)
    print(f"Generated identity-only super_admin JWT ({len(jwt_token)} chars)")

    results = []

    with sync_playwright() as pw:
        # Use system-installed Chrome (Playwright CDN blocked by SSL in this env)
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        launch_opts = {"headless": True}
        if os.path.exists(chrome_path):
            launch_opts["executable_path"] = chrome_path
            print(f"Using system Chrome: {chrome_path}")
        elif os.path.exists(edge_path):
            launch_opts["executable_path"] = edge_path
            print(f"Using system Edge: {edge_path}")
        browser = pw.chromium.launch(**launch_opts)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )

        # Inject auth into localStorage before any page loads
        context.add_init_script(f"""
            try {{
                localStorage.setItem('mpango-auth', {json.dumps(auth_json)});
            }} catch(e) {{}}
        """)

        page = context.new_page()

        for i, route in enumerate(ROUTES, 1):
            print(f"[{i:2d}/{len(ROUTES)}] {route['name']:30s} {route['path']}", end=" ... ")
            result = scan_route(page, route)
            results.append(result)
            status_str = str(result["http_status"])
            errs = len(result["console_errors"]) + len(result["page_errors"])
            forbidden = len(result["forbidden_controls"])
            shot = "OK" if result["screenshot"]["captured"] else "FAIL"
            redir = " REDIR" if result["redirected"] else ""
            print(f"HTTP {status_str:>3} | errors={errs} | forbidden={forbidden} | shot={shot}{redir}")

        browser.close()

    # Summary
    total = len(results)
    ok = sum(1 for r in results if r["http_status"] == 200)
    redirected = sum(1 for r in results if r["redirected"])
    with_errors = sum(1 for r in results if r["console_errors"] or r["page_errors"])
    with_forbidden = sum(1 for r in results if r["forbidden_controls"])
    screenshots_ok = sum(1 for r in results if r["screenshot"]["captured"])

    print("=" * 70)
    print(f"Summary: {total} routes | HTTP-200={ok} | redirected={redirected} | "
          f"with_errors={with_errors} | with_forbidden={with_forbidden} | "
          f"screenshots={screenshots_ok}/{total}")
    print("=" * 70)

    output = {
        "test_suite": "P25-EC Part D: Playwright Browser Smoke",
        "base_url": BASE_URL,
        "browser": "chromium (headless)",
        "viewport": {"width": 1440, "height": 900},
        "auth": "identity-only super_admin JWT (injected via localStorage mpango-auth)",
        "summary": {
            "total_routes": total,
            "http_200": ok,
            "redirected": redirected,
            "routes_with_errors": with_errors,
            "routes_with_forbidden_controls": with_forbidden,
            "screenshots_captured": screenshots_ok,
        },
        "routes": results,
    }

    output_path = Path(__file__).parent / "playwright_screenshots_result.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed JSON: {output_path}")
    print(f"Screenshots dir: {SHOTS_DIR}")


if __name__ == "__main__":
    main()
