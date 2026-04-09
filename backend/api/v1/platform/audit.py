"""
Platform Track P0 — Read-only audit log query endpoints.

NO write endpoint is exposed — audit entries are written via internal
services/platform_audit_service.py only.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from models.platform_audit_log import PlatformAuditLog

router = APIRouter(prefix='/api/v1/platform/audit', tags=['platform-audit'])


@router.get('/')
async def list_audit_logs(
    wholesaler_id: Optional[str] = Query(None, description='Filter by affected tenant'),
    action: Optional[str] = Query(None, description='Filter by action type'),
    actor_type: Optional[str] = Query(None, description='Filter by actor type'),
    limit: int = Query(50, ge=1, le=200, description='Max results'),
    offset: int = Query(0, ge=0, description='Offset for pagination'),
    db: AsyncSession = Depends(get_db),
):
    """List platform audit log entries (read-only, paginated)."""
    query = select(PlatformAuditLog).order_by(PlatformAuditLog.created_at.desc())

    if wholesaler_id:
        query = query.where(PlatformAuditLog.wholesaler_id == wholesaler_id)
    if action:
        query = query.where(PlatformAuditLog.action == action)
    if actor_type:
        query = query.where(PlatformAuditLog.actor_type == actor_type)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    entries = result.scalars().all()

    return {
        'items': [
            {
                'id': str(e.id),
                'actor_type': e.actor_type,
                'actor_id': str(e.actor_id) if e.actor_id else None,
                'wholesaler_id': str(e.wholesaler_id) if e.wholesaler_id else None,
                'action': e.action,
                'resource': e.resource,
                'audit_metadata': e.audit_metadata,
                'created_at': e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
        'total': total,
        'limit': limit,
        'offset': offset,
    }


@router.get('/{log_id}')
async def get_audit_log(log_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single audit log entry (read-only)."""
    result = await db.execute(
        select(PlatformAuditLog).where(PlatformAuditLog.id == log_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail='Audit log entry not found')

    return {
        'id': str(entry.id),
        'actor_type': entry.actor_type,
        'actor_id': str(entry.actor_id) if entry.actor_id else None,
        'wholesaler_id': str(entry.wholesaler_id) if entry.wholesaler_id else None,
        'action': entry.action,
        'resource': entry.resource,
        'audit_metadata': entry.audit_metadata,
        'created_at': entry.created_at.isoformat() if entry.created_at else None,
    }
