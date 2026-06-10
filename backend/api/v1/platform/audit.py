"""
Platform Track P0 — Read-only audit log query endpoints.

P11-C0: These endpoints now require P10 platform operator credentials.
Identity-only super_admin Bearer tokens, X-Platform-Operator secret,
or test override (test env only) are accepted.

NO write endpoint is exposed — audit entries are written via internal
services/platform_audit_service.py only.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.v1.platform.p10.guard import require_platform_operator
from models.platform_audit_log import PlatformAuditLog

router = APIRouter(prefix='/api/v1/platform/audit', tags=['platform-audit'])

# Default: 7 days ago, Max: 90 days
DEFAULT_SINCE_DAYS = 7
MAX_RANGE_DAYS = 90


def _parse_datetime(value: Optional[str], param_name: str) -> Optional[datetime]:
    """Parse ISO datetime string to timezone-aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        # Ensure timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {param_name} format. Use ISO 8601 (e.g., 2026-04-01T00:00:00Z)"
        )


def _get_default_since() -> datetime:
    """Get default 'since' = 7 days ago."""
    return datetime.now(timezone.utc) - timedelta(days=DEFAULT_SINCE_DAYS)


@router.get('/')
async def list_audit_logs(
    since: Optional[str] = Query(
        None,
        description=f"Filter entries created after this ISO datetime (default: {DEFAULT_SINCE_DAYS} days ago)"
    ),
    before: Optional[str] = Query(
        None,
        description="Filter entries created before this ISO datetime"
    ),
    wholesaler_id: Optional[str] = Query(None, description='Filter by affected tenant'),
    action: Optional[str] = Query(None, description='Filter by action type'),
    actor_type: Optional[str] = Query(None, description='Filter by actor type'),
    limit: int = Query(50, ge=1, le=200, description='Max results'),
    offset: int = Query(0, ge=0, description='Offset for pagination'),
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_platform_operator),
):
    """List platform audit log entries (read-only, paginated, time-range filterable)."""
    # Parse and validate time range
    since_dt = _parse_datetime(since, "since")
    before_dt = _parse_datetime(before, "before")

    # Apply defaults if neither specified
    if since_dt is None and before_dt is None:
        since_dt = _get_default_since()

    # Validate range
    if since_dt and before_dt and since_dt >= before_dt:
        raise HTTPException(
            status_code=400,
            detail="'since' must be earlier than 'before'"
        )

    # Cap range to MAX_RANGE_DAYS
    if since_dt and before_dt:
        range_days = (before_dt - since_dt).days
        if range_days > MAX_RANGE_DAYS:
            raise HTTPException(
                status_code=400,
                detail=f"Time range cannot exceed {MAX_RANGE_DAYS} days"
            )

    query = select(PlatformAuditLog).order_by(PlatformAuditLog.created_at.desc())

    # Time range filters
    if since_dt:
        query = query.where(PlatformAuditLog.created_at >= since_dt)
    if before_dt:
        query = query.where(PlatformAuditLog.created_at < before_dt)

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
        'since': since_dt.isoformat() if since_dt else None,
        'before': before_dt.isoformat() if before_dt else None,
    }


@router.get('/summary')
async def audit_summary(
    since: Optional[str] = Query(
        None,
        description=f"Start of period (default: {DEFAULT_SINCE_DAYS} days ago)"
    ),
    before: Optional[str] = Query(None, description="End of period"),
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_platform_operator),
):
    """Get action-grouped activity counts for a time period (read-only)."""
    # Parse and validate time range (same logic as list endpoint)
    since_dt = _parse_datetime(since, "since")
    before_dt = _parse_datetime(before, "before")

    if since_dt is None and before_dt is None:
        since_dt = _get_default_since()

    if since_dt and before_dt and since_dt >= before_dt:
        raise HTTPException(
            status_code=400,
            detail="'since' must be earlier than 'before'"
        )

    if since_dt and before_dt:
        range_days = (before_dt - since_dt).days
        if range_days > MAX_RANGE_DAYS:
            raise HTTPException(
                status_code=400,
                detail=f"Time range cannot exceed {MAX_RANGE_DAYS} days"
            )

    # Build query for action counts
    query = select(
        PlatformAuditLog.action,
        func.count(PlatformAuditLog.id).label('count')
    )

    if since_dt:
        query = query.where(PlatformAuditLog.created_at >= since_dt)
    if before_dt:
        query = query.where(PlatformAuditLog.created_at < before_dt)

    query = query.group_by(PlatformAuditLog.action).order_by(func.count(PlatformAuditLog.id).desc())

    result = await db.execute(query)
    rows = result.all()

    action_counts = {row.action: row.count for row in rows}
    total = sum(action_counts.values())

    return {
        'period': {
            'since': since_dt.isoformat() if since_dt else None,
            'before': before_dt.isoformat() if before_dt else None,
        },
        'action_counts': action_counts,
        'total': total,
    }


@router.get('/{log_id}')
async def get_audit_log(
    log_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_platform_operator),
):
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
