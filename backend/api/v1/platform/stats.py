"""
Platform Track — Read-only operational reporting endpoint.

P11-C0: This endpoint now requires P10 platform operator credentials.
Identity-only super_admin Bearer tokens, X-Platform-Operator secret,
or test override (test env only) are accepted.

Aggregates existing public-schema data (wholesalers, platform_tenants,
platform_audit_logs) into a compact platform-wide summary.

No writes, no migrations, no tenant-schema access.
"""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.v1.platform.p10.guard import require_platform_operator
from models.wholesaler import Wholesaler
from models.platform_tenant import PlatformTenant
from models.platform_audit_log import PlatformAuditLog

router = APIRouter(prefix='/api/v1/platform/stats', tags=['platform-stats'])


@router.get('/')
async def platform_stats(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_platform_operator),
):
    """Platform-wide operational summary (read-only)."""
    # 1. Tenant counts by status (from wholesalers)
    tenant_total_q = await db.execute(
        select(func.count()).select_from(
            select(Wholesaler.id).where(Wholesaler.is_deleted == False).subquery()
        )
    )
    tenant_total = tenant_total_q.scalar() or 0

    tenant_active_q = await db.execute(
        select(func.count()).select_from(
            select(Wholesaler.id).where(
                Wholesaler.is_deleted == False,
                Wholesaler.status == 'active',
            ).subquery()
        )
    )
    tenant_active = tenant_active_q.scalar() or 0

    tenant_suspended_q = await db.execute(
        select(func.count()).select_from(
            select(Wholesaler.id).where(
                Wholesaler.is_deleted == False,
                Wholesaler.status == 'suspended',
            ).subquery()
        )
    )
    tenant_suspended = tenant_suspended_q.scalar() or 0

    # 2. Provisioning counts (from platform_tenants)
    prov_complete_q = await db.execute(
        select(func.count()).select_from(
            select(PlatformTenant.id).where(
                PlatformTenant.provisioning_status == 'seed_complete'
            ).subquery()
        )
    )
    prov_complete = prov_complete_q.scalar() or 0

    prov_pending_q = await db.execute(
        select(func.count()).select_from(
            select(PlatformTenant.id).where(
                PlatformTenant.provisioning_status.in_(['pending', 'schema_created'])
            ).subquery()
        )
    )
    prov_pending = prov_pending_q.scalar() or 0

    prov_failed_q = await db.execute(
        select(func.count()).select_from(
            select(PlatformTenant.id).where(
                PlatformTenant.provisioning_status == 'failed'
            ).subquery()
        )
    )
    prov_failed = prov_failed_q.scalar() or 0

    # 3. Audit volume summary (from platform_audit_logs)
    audit_total_q = await db.execute(
        select(func.count(PlatformAuditLog.id))
    )
    audit_total = audit_total_q.scalar() or 0

    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    audit_24h_q = await db.execute(
        select(func.count(PlatformAuditLog.id)).where(
            PlatformAuditLog.created_at >= cutoff
        )
    )
    audit_24h = audit_24h_q.scalar() or 0

    return {
        'tenants': {
            'total': tenant_total,
            'active': tenant_active,
            'suspended': tenant_suspended,
            'other': tenant_total - tenant_active - tenant_suspended,
        },
        'provisioning': {
            'complete': prov_complete,
            'pending': prov_pending,
            'failed': prov_failed,
        },
        'audit': {
            'total_entries': audit_total,
            'last_24h': audit_24h,
        },
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
