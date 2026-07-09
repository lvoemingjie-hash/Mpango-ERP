"""
Platform Track P0 - Health and metadata endpoints.

P11-C0: These endpoints remain UNAUTHENTICATED by explicit design.
They expose only non-sensitive platform status and boundary metadata.
No tenant data, no audit data, no operational metrics are exposed.

Sensitive P0 endpoints (tenants, audit, stats) have been guarded with
require_platform_operator in their respective modules.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from datetime import datetime

from api.middleware.rbac import RequirePlatformAdmin
from core.security import TokenPayload

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


@router.get("/health")
async def platform_health(
    token: TokenPayload = Depends(RequirePlatformAdmin()),
):
    """Platform layer health check - confirms platform routing is active."""
    return {
        "status": "ok",
        "track": "platform-p0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/info")
async def platform_info(
    token: TokenPayload = Depends(RequirePlatformAdmin()),
):
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
