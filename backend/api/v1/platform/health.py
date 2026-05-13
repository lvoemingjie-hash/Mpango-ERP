"""
Platform Track P0 - Health and metadata endpoints.

This module provides safe, read-only platform endpoints that do NOT:
- Mutate business data
- Access tenant schemas
- Change authentication or authorization behavior
"""
from __future__ import annotations

from fastapi import APIRouter
from datetime import datetime

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


@router.get("/health")
async def platform_health():
    """Platform layer health check - confirms platform routing is active."""
    return {
        "status": "ok",
        "track": "platform-p0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/info")
async def platform_info():
    """Platform metadata - describes current platform track status."""
    return {
        "track": "platform-p0",
        "phase": "alignment-foundation",
        "version": "0.2.0",
        "boundaries": {
            "allowed": [
                "Platform routing scaffold",
                "Platform health/info endpoints",
                "Platform boundary documentation",
                "Platform ledger entries",
            ],
            "forbidden": [
                "Auth model changes",
                "Schema-per-tenant changes",
                "Business table modifications",
                "Product API behavior changes",
                "Cross-tenant write behavior",
                "Platform billing implementation",
                "Subscription engine",
            ],
        },
        "documentation": "See docs/arch/platform-boundary-note.md",
    }
