"""DC-12R1-MVP-L1-J1-H2-A-R1: public dual-entry join endpoints.

Lives in its own router (NOT api/v1/wholesalers.py — that file is under a
u6h2 governance no-edit contract) while serving the public supplier-code
lookup under the canonical /api/v1/wholesalers/lookup-code path.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from db.tenant_filter import run_as_system
from models.wholesaler import Wholesaler
from schemas.common import DataResponse
from schemas.wholesaler import WholesalerCodeLookupRequest, WholesalerJoinPreviewData

router = APIRouter()


@router.post(
    "/wholesalers/lookup-code",
    response_model=DataResponse[WholesalerJoinPreviewData],
    status_code=status.HTTP_200_OK,
)
async def lookup_wholesaler_by_code(
    request: Request,
    payload: WholesalerCodeLookupRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Public supplier-code lookup (dual-entry entry B, Phase 0 P0-2/P0-3).

    Returns a SAFE preview (name, region summary, masked contact) plus a
    short-lived signed join intent bound to the resolved wholesaler. The
    code is a public supplier locator, NOT a credential. Unknown codes get
    a uniform neutral response (no identity disclosure); endpoint-scoped
    rate limiting (on top of the global bucket) is the anti-enumeration
    control.
    """
    from core.rate_limiter import get_rate_limiter

    await get_rate_limiter().check_endpoint_rate_limit(
        request, namespace="lookup_code", limit=10
    )

    normalized = payload.code.strip().upper()
    if not normalized.isalnum():
        return DataResponse(
            success=True,
            data=WholesalerJoinPreviewData(found=False),
            timestamp=datetime.utcnow(),
        )

    with run_as_system(reason="public_wholesaler_code_lookup"):
        result = await db.execute(select(Wholesaler).where(Wholesaler.code == normalized))
        wholesaler = result.scalar_one_or_none()

    if wholesaler is None or wholesaler.is_deleted:
        # Uniform neutral miss: same shape, same status, no reason echo.
        return DataResponse(
            success=True,
            data=WholesalerJoinPreviewData(found=False),
            timestamp=datetime.utcnow(),
        )

    from core.join_intent import issue_join_intent

    join_intent, expires_at = issue_join_intent(
        wholesaler_id=wholesaler.id, wholesaler_code=wholesaler.code
    )
    data = WholesalerJoinPreviewData(
        found=True,
        name=wholesaler.name,
        region=_region_summary(wholesaler.address),
        contact_masked=_mask_contact(wholesaler.contact),
        join_intent=join_intent,
        expires_at=expires_at,
    )
    return DataResponse(success=True, data=data, timestamp=datetime.utcnow())


def _region_summary(address: str | None) -> str | None:
    """Coarse address summary: first line, truncated. Never full detail."""
    if not address:
        return None
    first_line = address.strip().splitlines()[0].strip()
    return first_line[:80] if first_line else None


def _mask_contact(contact: str | None) -> str | None:
    """Mask a contact string: keep at most first 2 / last 2 alphanumeric
    characters of the most alphanumeric token; never the full value."""
    if not contact:
        return None
    tokens = [t for t in contact.replace("-", " ").split() if t]
    if not tokens:
        return None
    token = max(tokens, key=lambda t: sum(c.isalnum() for c in t))
    alnum = [c for c in token if c.isalnum()]
    if len(alnum) <= 5:
        return "*" * len(alnum) if alnum else None
    return f"{alnum[0]}{alnum[1]}{'*' * (len(alnum) - 4)}{alnum[-2]}{alnum[-1]}"
