"""
DC-12R1-S3-S2B-I2C-I1 — Printable record response schemas (Contracts A-C).

Read-only print views for:
  A. Order document
  B. Payment declaration document
  C. Confirmed receipt

Truth contract (I2C-D/R2):
- All money is server-authoritative; no client/request recomputation.
- Timestamps are returned as authoritative aware UTC plus a server-derived
  fixed ``Africa/Nairobi`` display timestamp labelled ``EAT``. There is no
  tenant-configurable timezone in the MVP.
- A pending or rejected declaration is never a receipt. Only a confirmed
  declaration whose receipt eligibility predicate passes exposes receipt
  content.
- No internal identifiers (payment row UUID, cashier user id,
  ``tenant_user_id``) are exposed.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PrintOrderItemView(BaseModel):
    """A single line item on a printable order document."""

    product_name: str = Field(..., description="Product name at order time")
    sku_code: str = Field(..., description="SKU code at order time")
    quantity: int = Field(..., description="Quantity ordered")
    unit_price: Decimal = Field(..., description="Server-authoritative unit price (KES)")
    subtotal: Decimal = Field(..., description="Server-authoritative line subtotal (KES)")

    model_config = {"from_attributes": True}


class OrderPrintView(BaseModel):
    """Contract A — printable order document (server-authoritative)."""

    document_type: str = Field("order", description="Document discriminator")
    order_id: str = Field(..., description="Order identifier")
    status: str = Field(..., description="Client-mapped order status")
    supplier_name: str = Field(..., description="Wholesaler/supplier business name")
    retailer_name: str = Field(..., description="Retailer business name")
    items: List[PrintOrderItemView] = Field(default_factory=list)
    total_amount: Decimal = Field(..., description="Server-authoritative order total (KES)")
    item_count: int = Field(..., description="Number of line items")
    notes: Optional[str] = Field(None, description="Order notes (sanitized text)")
    created_at: datetime = Field(..., description="Authoritative UTC creation timestamp")
    created_at_eat: datetime = Field(..., description="Fixed Africa/Nairobi (EAT) display timestamp")

    model_config = {"from_attributes": True}


class DeclarationPrintView(BaseModel):
    """Contract B — printable payment declaration document.

    ``is_receipt`` is true only when the declaration is confirmed AND the
    receipt eligibility predicate passes. Pending/rejected declarations carry
    a prominent ``non_receipt_notice`` and ``is_receipt=False``.
    """

    document_type: str = Field("payment_declaration", description="Document discriminator")
    declaration_id: str = Field(..., description="Declaration identifier")
    order_id: str = Field(..., description="Originating order identifier")
    supplier_name: str = Field(..., description="Wholesaler/supplier business name")
    retailer_name: str = Field(..., description="Retailer business name")
    status: str = Field(..., description="Declaration status: pending|confirmed|rejected")
    declared_amount: Decimal = Field(..., description="Declared amount (KES)")
    method: str = Field(..., description="Declared method: cash|transfer")
    transfer_reference: Optional[str] = Field(None, description="Transfer reference (transfer only)")
    is_receipt: bool = Field(False, description="True only when receipt eligibility passes")
    non_receipt_notice: Optional[str] = Field(
        None, description="Prominent notice for pending/rejected (NOT A RECEIPT)"
    )
    rejection_reason: Optional[str] = Field(
        None, description="Sanitized rejection reason (rejected only, plain text)"
    )
    submitted_at: datetime = Field(..., description="Authoritative UTC submission timestamp")
    submitted_at_eat: datetime = Field(..., description="Fixed Africa/Nairobi (EAT) display timestamp")
    confirmed_at: Optional[datetime] = Field(None, description="Authoritative UTC confirmation timestamp")
    confirmed_at_eat: Optional[datetime] = Field(None, description="Fixed Africa/Nairobi (EAT) display timestamp")
    rejected_at: Optional[datetime] = Field(None, description="Authoritative UTC rejection timestamp")
    rejected_at_eat: Optional[datetime] = Field(None, description="Fixed Africa/Nairobi (EAT) display timestamp")
    order_status: Optional[str] = Field(None, description="Client-mapped order status")

    model_config = {"from_attributes": True}


class ReceiptPrintView(BaseModel):
    """Contract C — confirmed receipt (receipt-eligible only).

    Available only for a completed canonical payment. The ``receipt_number``
    is the canonical ``RCT-YYYYMMDD-NNNNNN`` identifier, rendered verbatim.
    """

    document_type: str = Field("receipt", description="Document discriminator")
    declaration_id: str = Field(..., description="Originating declaration identifier")
    order_id: str = Field(..., description="Originating order identifier")
    supplier_name: str = Field(..., description="Wholesaler/supplier business name")
    retailer_name: str = Field(..., description="Retailer business name")
    receipt_number: str = Field(..., description="Canonical receipt number RCT-YYYYMMDD-NNNNNN")
    confirmed_amount: Decimal = Field(..., description="Confirmed/settled amount (KES)")
    method: str = Field(..., description="Payment method: cash|transfer")
    confirmed_at: datetime = Field(..., description="Authoritative UTC confirmation timestamp")
    confirmed_at_eat: datetime = Field(..., description="Fixed Africa/Nairobi (EAT) display timestamp")
    declared_amount: Decimal = Field(..., description="Originally declared amount (KES)")
    order_status: Optional[str] = Field(None, description="Client-mapped order status")
    order_total_amount: Optional[Decimal] = Field(None, description="Server-authoritative order total (KES)")

    model_config = {"from_attributes": True}


# ===========================================================================
# Contract D — relationship account statement (printable, read-only)
# ===========================================================================


class StatementMovementView(BaseModel):
    """A single receivable ledger movement on the statement.

    ``signed_amount`` is the verbatim ledger ``amount`` (positive = charge,
    negative = collection); ``kind`` classifies it as ``charge``/``collection``
    and ``display_amount`` is the absolute value for rendering. No internal
    ledger entry id is exposed (R1 rule 2 — the printable DOM shows only short
    references). The ``reference_type``/``reference_id`` expose the ledger
    reference (always an order_id for receivable rows); no payment id is ever
    exposed or associated here.
    """

    kind: Literal["charge", "collection"] = Field(..., description="Movement direction: charge|collection")
    date: datetime = Field(..., description="Authoritative UTC transaction date")
    date_eat: datetime = Field(..., description="Fixed Africa/Nairobi (EAT) display timestamp")
    signed_amount: Decimal = Field(..., description="Signed amount: +charge / -collection (KES)")
    display_amount: Decimal = Field(..., description="abs(signed_amount) (KES)")
    description: Optional[str] = Field(None, description="Ledger entry description (sanitized)")
    reference_type: str = Field(..., description="Ledger reference type: order|refund")
    reference_id: str = Field(..., description="Order identifier referenced by the movement")

    model_config = {"from_attributes": True}


class StatementSettledPaymentView(BaseModel):
    """A canonical completed settlement on the statement.

    Independent of movements (rule 6): never associated by amount, timestamp or
    order_id. Carries the canonical receipt number verbatim. No internal
    payment id is exposed (R1 rule 2).
    """

    date: datetime = Field(..., description="Authoritative UTC payment created_at")
    date_eat: datetime = Field(..., description="Fixed Africa/Nairobi (EAT) display timestamp")
    order_id: str = Field(..., description="Order identifier of the settled payment")
    amount: Decimal = Field(..., description="Settled amount (KES)")
    method: str = Field(..., description="Payment method: cash|transfer")
    receipt_number: Optional[str] = Field(None, description="Canonical receipt number, if present")

    model_config = {"from_attributes": True}


class StatementPendingDeclarationView(BaseModel):
    """A non-accounting pending/rejected declaration (only when explicitly requested).

    Never enters any balance or settled total.
    """

    declaration_id: str = Field(..., description="Declaration identifier")
    order_id: str = Field(..., description="Order identifier")
    declared_amount: Decimal = Field(..., description="Declared amount (KES)")
    method: str = Field(..., description="Declared method: cash|transfer")
    status: str = Field(..., description="Declaration status: pending|rejected")
    submitted_at: datetime = Field(..., description="Authoritative UTC submission timestamp")
    submitted_at_eat: datetime = Field(..., description="Fixed Africa/Nairobi (EAT) display timestamp")
    transfer_reference: Optional[str] = Field(None, description="Transfer reference, if present")

    model_config = {"from_attributes": True}


class StatementPrintView(BaseModel):
    """Contract D — printable relationship account statement.

    Ledger-derived, server-authoritative. ``opening_balance`` and
    ``closing_balance`` are receivable ledger sums; ``charge_total``,
    ``collection_total`` and ``net_movement`` derive ONLY from ``movements[]``;
    ``settled_payments[]`` is an independent canonical-completed-payment list.
    Money is ``Decimal`` end-to-end (Postgres/Python); the frontend renders the
    server strings verbatim.
    """

    document_type: str = Field("statement", description="Document discriminator")
    supplier_name: str = Field(..., description="Wholesaler/supplier business name")
    retailer_name: str = Field(..., description="Retailer business name")
    period_from: date = Field(..., description="Inclusive period start (EAT calendar day)")
    period_to: date = Field(..., description="Inclusive period end (EAT calendar day)")
    opening_balance: Decimal = Field(..., description="Receivable sum strictly before the period (KES)")
    closing_balance: Decimal = Field(..., description="opening + net_movement (KES)")
    charge_total: Decimal = Field(..., description="Sum of positive movements (KES)")
    collection_total: Decimal = Field(..., description="Absolute sum of negative movements (KES)")
    net_movement: Decimal = Field(..., description="charge_total - collection_total, signed (KES)")
    settled_total: Decimal = Field(..., description="Sum of settled_payments[].amount only (KES)")
    movements: List[StatementMovementView] = Field(default_factory=list)
    settled_payments: List[StatementSettledPaymentView] = Field(default_factory=list)
    pending_declarations: List[StatementPendingDeclarationView] = Field(
        default_factory=list,
        description="Non-accounting pending/rejected declarations (only when requested).",
    )
    generated_at: datetime = Field(..., description="Authoritative UTC generation timestamp")
    generated_at_eat: datetime = Field(..., description="Fixed Africa/Nairobi (EAT) display timestamp")

    model_config = {"from_attributes": True}
