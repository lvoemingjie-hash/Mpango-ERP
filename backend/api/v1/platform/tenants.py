"""
Platform Track P0 - Read-only tenant lifecycle visibility endpoints.

These endpoints provide platform administrators with visibility into
tenant lifecycle status WITHOUT allowing mutations.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from models.wholesaler import Wholesaler
from models.platform_tenant import PlatformTenant

router = APIRouter(prefix="/api/v1/platform/tenants", tags=["platform-tenants"])


@router.get("/")
async def list_tenants(db: AsyncSession = Depends(get_db)):
    """List all tenants with platform lifecycle status (read-only)."""
    result = await db.execute(
        select(Wholesaler).where(Wholesaler.is_deleted == False).order_by(Wholesaler.created_at.desc())
    )
    wholesalers = result.scalars().all()

    tenants = []
    for w in wholesalers:
        # Fetch platform tenant record if it exists
        pt_result = await db.execute(
            select(PlatformTenant).where(PlatformTenant.wholesaler_id == w.id)
        )
        pt = pt_result.scalar_one_or_none()

        tenants.append({
            "id": str(w.id),
            "code": w.code,
            "name": w.name,
            "status": w.status,
            "provisioned_at": w.provisioned_at.isoformat() if w.provisioned_at else None,
            "suspended_at": w.suspended_at.isoformat() if w.suspended_at else None,
            "suspension_reason": w.suspension_reason,
            "plan_type": w.plan_type,
            "provisioning_status": pt.provisioning_status if pt else None,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        })

    return {"tenants": tenants, "count": len(tenants)}


@router.get("/{wholesaler_id}")
async def get_tenant(wholesaler_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed platform lifecycle info for a single tenant (read-only)."""
    result = await db.execute(
        select(Wholesaler).where(Wholesaler.id == wholesaler_id)
    )
    w = result.scalar_one_or_none()
    if w is None:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Tenant not found"})

    pt_result = await db.execute(
        select(PlatformTenant).where(PlatformTenant.wholesaler_id == w.id)
    )
    pt = pt_result.scalar_one_or_none()

    return {
        "id": str(w.id),
        "code": w.code,
        "name": w.name,
        "address": w.address,
        "contact": w.contact,
        "status": w.status,
        "provisioned_at": w.provisioned_at.isoformat() if w.provisioned_at else None,
        "suspended_at": w.suspended_at.isoformat() if w.suspended_at else None,
        "suspension_reason": w.suspension_reason,
        "plan_type": w.plan_type,
        "tenant_schema": w.get_tenant_schema(),
        "provisioning": {
            "status": pt.provisioning_status if pt else None,
            "log": pt.provisioning_log if pt else None,
            "activated_at": pt.activated_at.isoformat() if pt and pt.activated_at else None,
        } if pt else None,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }
