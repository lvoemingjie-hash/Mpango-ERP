"""Pydantic schemas for the payment declaration runtime (DC-12R1-S3-S2B-I2B).

A declaration is NOT a payment: it has zero financial effect until a wholesaler
cashier confirms it. These schemas cover retailer submission, cashier
confirm/reject, and retailer/cashier read views.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

from schemas.base import CamelModel


class DeclarationMethodValues:
    CASH = "cash"
    TRANSFER = "transfer"


class DeclarationSubmitRequest(CamelModel):
    """Retailer payment-declaration submission body.

    Fields are optional at schema level so the route can emit controlled error
    codes rather than 422 Pydantic tracebacks; the route enforces presence and
    performs the explicit declared_amount NaN/Infinity/zero/negative guard
    before any SQL.
    """

    declared_amount: Optional[Decimal] = Field(
        None,
        description="Declared payment amount (must be a positive finite number)",
    )
    method: Optional[str] = Field(
        None,
        description="Declaration method: cash or transfer (credit is not allowed)",
    )
    transfer_reference: Optional[str] = Field(
        None,
        description="External transfer reference (required for transfer, NULL for cash)",
    )

    model_config = {"from_attributes": True}


class DeclarationRejectRequest(CamelModel):
    """Cashier rejection body. Validation (1-256 chars, sanitized, no HTML) is
    performed by the route via the authoritative server-side validator. Pydantic
    constraints are intentionally omitted to prevent 422 from preempting the
    controlled 400 INVALID_REJECTION_REASON."""

    reason: str | None = Field(
        None,
        description="Sanitized rejection reason (route-validated 1-256 characters)",
    )

    model_config = {"from_attributes": True}


class DeclarationView(BaseModel):
    """Cashier-facing declaration view (wholesaler side)."""

    id: str
    order_id: str
    retailer_id: str
    wholesaler_id: str
    declared_amount: Decimal
    method: str
    transfer_reference: Optional[str] = None
    status: str
    submitted_at: datetime
    confirmed_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    reason: Optional[str] = None
    confirmation_payment_id: Optional[str] = None
    receipt_number: Optional[str] = None
    order_status: Optional[str] = None
    currency: Optional[str] = None
    currency_status: str = 'LEGACY_CURRENCY_UNVERIFIED'

    model_config = {"from_attributes": True}


class ClientDeclarationView(BaseModel):
    """Retailer-safe declaration view.

    Omits internal cashier user ids and the internal payment row id. Receipt
    number is resolved from the linked canonical payment and is present only for
    confirmed declarations."""

    id: str
    order_id: str
    declared_amount: Decimal
    method: str
    transfer_reference: Optional[str] = None
    status: str
    submitted_at: datetime
    confirmed_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    reason: Optional[str] = None
    receipt_number: Optional[str] = None
    order_status: Optional[str] = None
    currency: Optional[str] = None
    currency_status: str = 'LEGACY_CURRENCY_UNVERIFIED'

    model_config = {"from_attributes": True}


class DeclarationConfirmResponse(BaseModel):
    """Response for POST /api/v1/declarations/{id}/confirm (and replay)."""

    id: str
    order_id: str
    status: str
    confirmation_payment_id: str
    receipt_number: str
    order_status: str
    confirmed_at: datetime

    model_config = {"from_attributes": True}


class ContextSubjectView(BaseModel):
    tenant_id: str
    user_id: str


class BusinessIdentityView(BaseModel):
    id: str
    name: str | None
    name_resolution: Literal["RESOLVED", "MISSING"]


class SupplierIdentityView(BusinessIdentityView):
    code: str


class ActiveBindingView(BaseModel):
    id: str
    status: Literal["active"]


class ReviewDeclarationView(BaseModel):
    id: str
    order_id: str
    status: Literal["pending", "confirmed", "rejected"]
    declared_amount: str
    method: Literal["cash", "transfer"]
    transfer_reference: str | None


class ReviewOrderView(BaseModel):
    id: str
    status: str


class ReviewMoneyView(BaseModel):
    currency: Literal["KES", "UGX"] | None
    currency_status: Literal["KNOWN", "LEGACY_CURRENCY_UNVERIFIED", "UNSUPPORTED"]
    balance_due: str | None
    balance_status: Literal["VERIFIED", "UNVERIFIED"]


class CashierReviewContext(BaseModel):
    context: ContextSubjectView
    declaration: ReviewDeclarationView
    order: ReviewOrderView
    supplier: SupplierIdentityView
    retailer: BusinessIdentityView
    binding: ActiveBindingView
    money: ReviewMoneyView
    review_state: Literal["READY", "UNRESOLVED", "NOT_ACTIONABLE"]
    reason_codes: list[str]
    observed_at: datetime


class StatementLineView(BaseModel):
    """A single line item on the retailer statement.

    A line is either a confirmed declaration's canonical payment or a direct
    canonical payment for the retailer. No opening/closing balance is computed
    (deferred per contract DD-06)."""

    date: datetime
    order_id: str
    amount: Decimal
    method: str
    receipt_number: Optional[str] = None
    description: str

    model_config = {"from_attributes": True}
