"""Playwright E2E test configuration for Mpango ERP.

Uses system chromium-browser to avoid large browser downloads.
"""
from pathlib import Path

base_url = "http://localhost:8000"

projects = [
    {
        "name": "chromium",
        "use": {
            "base_url": base_url,
            "browser_name": "chromium",
            "channel": "chromium",
            "executable_path": "/usr/bin/chromium-browser",
            "headless": True,
            "viewport": {"width": 1280, "height": 720},
        },
    },
]
