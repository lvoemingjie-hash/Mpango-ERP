"""Wholesaler cashier declaration routes (DC-12R1-S3-S2B-I2B).

Cashier (admin with ``payments:confirm_declaration``) confirms or rejects
retailer payment declarations. Confirmation delegates the entire financial
write path to ``PaymentDeclarationService.confirm_declaration`` which calls
``CanonicalPaymentService.confirm_payment(skip_prechecks=False,
force_completed=True, allocate_receipt=True)``.

Confirm replay on an already-confirmed declaration returns 200 with the same
payment and receipt, zero new writes. The declaration service owns rollback of
its own mutation flow; transaction ownership stays with the caller/middleware.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.orders import _restore_tenant_search_path_after_rollback
from core.domain.order_state import (
    InvalidStateTransitionError as DomainInvalidStateTransitionError,
    OrderInvariantViolation,
)
from core.security import TokenPayload
from crud.order import InvalidStateTransitionError
from repositories.payment_declaration_repository import PaymentDeclarationRepository
from schemas.common import DataResponse, Pagination
from schemas.declaration import (
    DeclarationConfirmResponse,
    DeclarationRejectRequest,
    DeclarationView,
)
from schemas.order import validate_no_html_tags
from services.canonical_payment_service import CanonicalPaymentMutationHttpError
from services.payment_declaration_service import PaymentDeclarationService


router = APIRouter()


_ALLOWED_STATUSES = {"pending", "confirmed", "rejected"}


def _to_view(row) -> DeclarationView:
    return DeclarationView(
        id=str(row["id"]),
        order_id=str(row["order_id"]),
        retailer_id=str(row["retailer_id"]),
        wholesaler_id=str(row["wholesaler_id"]),
        declared_amount=row["declared_amount"],
        method=row["method"],
        transfer_reference=row.get("transfer_reference"),
        status=row["status"],
        submitted_at=row["submitted_at"],
        confirmed_at=row.get("confirmed_at"),
        rejected_at=row.get("rejected_at"),
        reason=row.get("reason"),
        confirmation_payment_id=str(row["confirmation_payment_id"]) if row.get("confirmation_payment_id") else None,
        receipt_number=row.get("receipt_number"),
        order_status=str(row["order_status"]) if row.get("order_status") is not None else None,
    )


def _tenant_wholesaler_id(token: TokenPayload) -> uuid.UUID:
    if not token.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PERMISSION_DENIED", "message": "Tenant context required"},
        )
    try:
        return uuid.UUID(token.tenant_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PERMISSION_DENIED", "message": "Invalid tenant context"},
        )


@router.get("", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def list_declarations(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    declaration_status: Optional[str] = Query(None, alias="status"),
    token: TokenPayload = Depends(RequirePermission("payments:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    wholesaler_id = _tenant_wholesaler_id(token)
    status_filter = declaration_status.lower() if declaration_status else None
    if status_filter is not None and status_filter not in _ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_DECLARATION_STATUS", "message": "Invalid status filter"},
        )
    rows, total = await PaymentDeclarationRepository().list_by_wholesaler(
        db,
        wholesaler_id=wholesaler_id,
        page=page,
        size=size,
        status=status_filter,
        retailer_id=None,
    )
    pages = ceil(total / size) if total > 0 else 0
    return DataResponse(
        success=True,
        data={
            "items": [_to_view(r).model_dump(mode="json") for r in rows],
            "pagination": Pagination(page=page, size=size, total=total, pages=pages).model_dump(),
        },
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/{declaration_id}", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def get_declaration(
    declaration_id: str,
    token: TokenPayload = Depends(RequirePermission("payments:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    wholesaler_id = _tenant_wholesaler_id(token)
    try:
        did = uuid.UUID(declaration_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DECLARATION_NOT_FOUND", "message": "Declaration not found"},
        )
    row = await PaymentDeclarationRepository().get_detail_by_wholesaler(
        db,
        declaration_id=did,
        wholesaler_id=wholesaler_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DECLARATION_NOT_FOUND", "message": "Declaration not found"},
        )
    return DataResponse(
        success=True,
        data=_to_view(row).model_dump(mode="json"),
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/{declaration_id}/confirm", response_model=DataResponse[DeclarationConfirmResponse], status_code=status.HTTP_200_OK)
async def confirm_declaration(
    declaration_id: str,
    token: TokenPayload = Depends(RequirePermission("payments:confirm_declaration")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        did = uuid.UUID(declaration_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DECLARATION_NOT_FOUND", "message": "Declaration not found"},
        )
    confirmed_by = uuid.UUID(token.user_id) if token.user_id else None
    wholesaler_id = _tenant_wholesaler_id(token)

    service = PaymentDeclarationService()
    try:
        declaration, result = await service.confirm_declaration(
            db=db,
            declaration_id=did,
            wholesaler_id=wholesaler_id,
            confirmed_by=confirmed_by,  # type: ignore[arg-type]
        )
    except CanonicalPaymentMutationHttpError as exc:
        await db.rollback()
        await _restore_tenant_search_path_after_rollback(db)
        raise exc.http_exception
    except (InvalidStateTransitionError, DomainInvalidStateTransitionError, OrderInvariantViolation):
        await db.rollback()
        await _restore_tenant_search_path_after_rollback(db)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE_TRANSITION", "message": "Payment cannot transition the order from its current state"},
        )
    except IntegrityError:
        await db.rollback()
        await _restore_tenant_search_path_after_rollback(db)
        raise
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        await _restore_tenant_search_path_after_rollback(db)
        raise

    receipt_number = result.payment_record.get("receipt_number")
    payment_id = result.payment_record.get("id")
    return DataResponse(
        success=True,
        data=DeclarationConfirmResponse(
            id=str(declaration["id"]),
            order_id=str(declaration["order_id"]),
            status=declaration["status"],
            confirmation_payment_id=str(payment_id),
            receipt_number=str(receipt_number),
            order_status=str(result.order_state),
            confirmed_at=declaration["confirmed_at"],
        ),
        message="Declaration confirmed" if not result.replayed else "Declaration confirmation replayed",
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/{declaration_id}/reject", response_model=DataResponse[DeclarationView], status_code=status.HTTP_200_OK)
async def reject_declaration(
    declaration_id: str,
    body: DeclarationRejectRequest,
    token: TokenPayload = Depends(RequirePermission("payments:confirm_declaration")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    # Backend-owned reason validation (Pydantic enforces 1-256; centralised HTML validator).
    reason = (body.reason or "").strip()
    if not reason or len(reason) > 256:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_REJECTION_REASON", "message": "Rejection reason must be 1-256 characters"},
        )
    try:
        reason = validate_no_html_tags(reason)
        if not reason.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_REJECTION_REASON", "message": "Rejection reason is required"},
            )
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_REJECTION_REASON", "message": "Rejection reason contains forbidden content"},
        )
    try:
        did = uuid.UUID(declaration_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DECLARATION_NOT_FOUND", "message": "Declaration not found"},
        )
    rejected_by = uuid.UUID(token.user_id) if token.user_id else None
    wholesaler_id = _tenant_wholesaler_id(token)

    service = PaymentDeclarationService()
    try:
        declaration = await service.reject_declaration(
            db=db,
            declaration_id=did,
            wholesaler_id=wholesaler_id,
            rejected_by=rejected_by,  # type: ignore[arg-type]
            reason=reason,
        )
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        await _restore_tenant_search_path_after_rollback(db)
        raise

    # Re-fetch via exact dual-key lookup for joined columns.
    repo = PaymentDeclarationRepository()
    row = await repo.get_detail_by_wholesaler(
        db,
        declaration_id=did,
        wholesaler_id=wholesaler_id,
    )
    view_row = row if row is not None else declaration
    return DataResponse(
        success=True,
        data=_to_view(view_row).model_dump(mode="json"),
        message="Declaration rejected",
        timestamp=datetime.now(timezone.utc),
    )
