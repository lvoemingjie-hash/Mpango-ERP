"""
Finance Pydantic schemas for receivables API.

Provides stable typed response models for Phase 6.2 receivables endpoints:
- ReceivablesSummaryResponse: aggregate receivables summary by retailer
- ReceivableOrdersResponse: paginated receivables orders list
"""
from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field
from datetime import datetime


class RetailerSummaryItem(BaseModel):
    """
    Per-retailer receivables breakdown.

    Returned in the by_retailer list of ReceivablesSummaryResponse.
    """
    retailer_id: str = Field(..., description="Retailer UUID")
    retailer_name: str = Field(..., description="Retailer display name")
    outstanding_balance: float = Field(..., ge=0, description="Total outstanding balance from public binding")
    credit_receivables: float = Field(..., ge=0, description="Total credit payment exposure")
    unpaid_order_balance: float = Field(..., ge=0, description="Total unpaid order balances")
    order_count: int = Field(..., ge=0, description="Number of orders with receivable exposure")

    model_config = {"from_attributes": True}


class ReceivablesSummaryResponse(BaseModel):
    """
    Comprehensive receivables summary by retailer.

    Response for GET /finance/receivables/summary
    """
    total_outstanding: float = Field(..., ge=0, description="Sum of all retailer outstanding balances")
    retailer_count: int = Field(..., ge=0, description="Number of retailers with balances")
    order_count: int = Field(..., ge=0, description="Total orders with receivable exposure")
    credit_receivables: float = Field(..., ge=0, description="Total credit payment exposure")
    unpaid_order_balance: float = Field(..., ge=0, description="Total unpaid order balances")
    by_retailer: List[RetailerSummaryItem] = Field(..., description="Per-retailer breakdowns")

    model_config = {"from_attributes": True}


class ReceivableOrderItem(BaseModel):
    """
    Order with receivables exposure.

    Individual item in ReceivableOrdersResponse.items
    """
    order_id: str = Field(..., description="Order UUID")
    retailer_id: str = Field(..., description="Retailer UUID")
    retailer_name: str = Field(..., description="Retailer display name")
    status: str = Field(..., description="Order status (confirmed, partially_paid, paid)")
    classification: str | None = Field(None, description="Classification: credit_receivable or unpaid_order")
    payment_method: str = Field(..., description="Primary payment method (credit, cash)")
    total_amount: float = Field(..., ge=0, description="Order total amount")
    cash_paid: float = Field(..., ge=0, description="Cash/transfer amount paid")
    credit_amount: float = Field(..., ge=0, description="Credit amount charged")
    balance_due: float = Field(..., ge=0, description="Remaining balance (total_amount - cash_paid)")
    created_at: str | None = Field(None, description="Order creation timestamp (ISO 8601)")
    age_days: int = Field(..., ge=0, description="Days since order creation")

    model_config = {"from_attributes": True}


class ReceivableOrdersResponse(BaseModel):
    """
    Paginated receivables orders list.

    Response for GET /finance/receivables/orders
    """
    items: List[ReceivableOrderItem] = Field(..., description="Receivable orders")
    pagination: dict = Field(..., description="Pagination metadata with page, size, total, pages")

    model_config = {"from_attributes": True}
