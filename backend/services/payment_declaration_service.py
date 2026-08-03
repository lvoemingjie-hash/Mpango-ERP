"""Payment declaration runtime service (DC-12R1-S3-S2B-I2B).

Encapsulates the three declaration lifecycle operations:

* ``submit_declaration`` — retailer submission, ZERO financial effect.
* ``confirm_declaration`` — cashier confirmation, delegates the entire financial
  write path to ``CanonicalPaymentService.confirm_payment`` with
  ``skip_prechecks=False, force_completed=True, allocate_receipt=True``. This
  service performs NO financial-rule replication.
* ``reject_declaration`` — cashier rejection, terminal, zero financial effect.

Confirmation reuses the canonical payment service's full default precheck path
(payment idempotency, order lock, balance/state/duplicate-transfer checks). The
canonical idempotency key is derived deterministically as
``decl-confirm-{declaration_id.hex}`` and is in a reserved namespace isolated
from user-submitted direct-payment keys.

All financial mutation occurs inside the single caller-owned transaction; this
service never commits or rolls back. Confirmation replay returns the existing
declaration + payment + receipt with zero new writes.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Mapping

from fastapi import HTTPException, status

from core.domain.order_state import OrderState
from models.order import Order as OrderModel
from repositories.payment_declaration_repository import PaymentDeclarationRepository
from repositories.payment_repository import PaymentRepository
from services.canonical_payment_service import (
    CanonicalPaymentMutationHttpError,
    CanonicalPaymentResult,
    CanonicalPaymentService,
    _is_valid_receipt_number,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


DECLARATION_CONFIRMATION_KEY_PREFIX = "decl-confirm-"
ALLOWED_DECLARATION_METHODS = {"cash", "transfer"}
MAX_TRANSFER_REFERENCE_LENGTH = 128


def _declaration_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _is_invalid_amount(amount: Decimal) -> bool:
    """True when the amount must be rejected. Short-circuits so NaN's
    InvalidOperation on ``<= 0`` can never escape."""
    return amount.is_nan() or amount.is_infinite() or amount <= 0


class PaymentDeclarationService:
    def __init__(self) -> None:
        self._repo = PaymentDeclarationRepository()
        self._payment_repo = PaymentRepository()
        self._canonical = CanonicalPaymentService()

    # ------------------------------------------------------------------
    # Submission (zero financial effect)
    # ------------------------------------------------------------------
    async def submit_declaration(
        self,
        *,
        db: AsyncSession,
        order_id: str,
        retailer_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
        submitted_by: uuid.UUID,
        declared_amount: Decimal,
        method: str,
        transfer_reference: str | None,
        idempotency_key: str,
    ) -> tuple[Mapping[str, Any], bool]:
        """Return ``(record, replayed)``. ``replayed`` is True when an existing
        declaration with the same (retailer, key, payload) was returned unchanged."""
        # Explicit amount guard BEFORE any SQL. NaN/Infinity/zero/negative
        # rejected with a controlled 400.
        if declared_amount is None or _is_invalid_amount(declared_amount):
            raise _declaration_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_DECLARED_AMOUNT",
                "Declared amount must be a positive finite number",
            )

        if method not in ALLOWED_DECLARATION_METHODS:
            raise _declaration_error(
                status.HTTP_400_BAD_REQUEST,
                "DECLARATION_METHOD_INVALID",
                "Declaration method must be one of: cash, transfer",
            )

        # transfer_reference: trim, validate 1-128 for transfer, NULL for cash.
        normalized_ref: str | None = None
        if transfer_reference is not None:
            normalized_ref = transfer_reference.strip()
        if method == "transfer":
            if not normalized_ref:
                raise _declaration_error(
                    status.HTTP_400_BAD_REQUEST,
                    "DECLARATION_TRANSFER_REFERENCE_REQUIRED",
                    "Transfer reference is required for transfer declarations",
                )
            if len(normalized_ref) > MAX_TRANSFER_REFERENCE_LENGTH:
                raise _declaration_error(
                    status.HTTP_400_BAD_REQUEST,
                    "DECLARATION_TRANSFER_REFERENCE_TOO_LONG",
                    "Transfer reference must not exceed 128 characters",
                )
        else:
            # cash: reference must be NULL
            normalized_ref = None

        # Verify the order exists and belongs to this (retailer, wholesaler)
        # binding before anything is written. Malformed/unknown order_id -> 404.
        order = await self._get_order_for_declaration(
            db, order_id=order_id, retailer_id=retailer_id, wholesaler_id=wholesaler_id
        )
        if order is None:
            raise _declaration_error(
                status.HTTP_404_NOT_FOUND,
                "ORDER_NOT_FOUND",
                f"Order with ID '{order_id}' not found for this relationship",
            )

        # Idempotency: same (retailer, key) + same payload -> return existing.
        existing = await self._repo.get_by_retailer_idempotency(
            db, retailer_id=retailer_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            if self._same_declaration_request(
                existing,
                order_id=str(order.id),
                declared_amount=declared_amount,
                method=method,
                transfer_reference=normalized_ref,
            ):
                return existing, True
            raise _declaration_error(
                status.HTTP_409_CONFLICT,
                "DECLARATION_IDEMPOTENCY_KEY_CONFLICT",
                "Declaration idempotency key was already used with a different request",
            )

        record = await self._repo.create(
            db,
            order_id=order.id,
            retailer_id=retailer_id,
            wholesaler_id=wholesaler_id,
            declared_amount=declared_amount,
            method=method,
            transfer_reference=normalized_ref,
            idempotency_key=idempotency_key,
            submitted_by=submitted_by,
        )
        return record, False

    # ------------------------------------------------------------------
    # Confirmation (delegates financial write to the canonical service)
    # ------------------------------------------------------------------
    async def confirm_declaration(
        self,
        *,
        db: AsyncSession,
        declaration_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
        confirmed_by: uuid.UUID,
    ) -> tuple[Mapping[str, Any], CanonicalPaymentResult]:
        # Lock by (declaration_id, wholesaler_id) for ownership enforcement.
        # A wrong wholesaler gets a neutral 404, never a 403.
        declaration = await self._repo.get_for_update_by_wholesaler(
            db, declaration_id=declaration_id, wholesaler_id=wholesaler_id
        )
        if declaration is None:
            raise _declaration_error(
                status.HTTP_404_NOT_FOUND,
                "DECLARATION_NOT_FOUND",
                "Declaration not found",
            )

        decl_status = declaration["status"]
        if decl_status == "confirmed":
            existing_result = await self._resolve_confirmed_replay(db, declaration, wholesaler_id)
            return declaration, existing_result
        if decl_status == "rejected":
            raise _declaration_error(
                status.HTTP_409_CONFLICT,
                "DECLARATION_NOT_PENDING",
                "Cannot confirm a declaration that has already been rejected",
            )

        # Verify order ownership and active binding under the same transaction.
        await self._verify_ownership_and_binding(
            db,
            order_id=uuid.UUID(str(declaration["order_id"])),
            retailer_id=uuid.UUID(str(declaration["retailer_id"])),
            wholesaler_id=wholesaler_id,
        )

        # pending -> proceed.
        canonical_key = f"{DECLARATION_CONFIRMATION_KEY_PREFIX}{declaration_id.hex}"
        transaction_id = declaration["transfer_reference"] or None

        result = await self._canonical.confirm_payment(
            db=db,
            order_id=str(declaration["order_id"]),
            amount=declaration["declared_amount"],
            method=declaration["method"],
            transaction_id=transaction_id,
            idempotency_key=canonical_key,
            created_by=str(confirmed_by),
            force_completed=True,
            skip_prechecks=False,
            allocate_receipt=True,
        )

        payment_id = uuid.UUID(str(result.payment_record["id"]))
        await self._repo.mark_confirmed(
            db,
            declaration_id=declaration_id,
            wholesaler_id=wholesaler_id,
            confirmed_by=confirmed_by,
            confirmation_payment_id=payment_id,
        )
        declaration = await self._repo.get_by_wholesaler_dual_key(
            db, declaration_id=declaration_id, wholesaler_id=wholesaler_id
        )
        return declaration, result

    # ------------------------------------------------------------------
    # Rejection (terminal, zero financial effect)
    # ------------------------------------------------------------------
    async def reject_declaration(
        self,
        *,
        db: AsyncSession,
        declaration_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
        rejected_by: uuid.UUID,
        reason: str,
    ) -> Mapping[str, Any]:
        declaration = await self._repo.get_for_update_by_wholesaler(
            db, declaration_id=declaration_id, wholesaler_id=wholesaler_id
        )
        if declaration is None:
            raise _declaration_error(
                status.HTTP_404_NOT_FOUND,
                "DECLARATION_NOT_FOUND",
                "Declaration not found",
            )

        decl_status = declaration["status"]
        if decl_status != "pending":
            raise _declaration_error(
                status.HTTP_409_CONFLICT,
                "DECLARATION_NOT_PENDING",
                "Cannot reject a declaration that is no longer pending",
            )

        await self._repo.mark_rejected(
            db,
            declaration_id=declaration_id,
            wholesaler_id=wholesaler_id,
            rejected_by=rejected_by,
            reason=reason,
        )
        declaration = await self._repo.get_by_wholesaler_dual_key(
            db, declaration_id=declaration_id, wholesaler_id=wholesaler_id
        )
        return declaration

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _verify_ownership_and_binding(
        self,
        db: AsyncSession,
        *,
        order_id: uuid.UUID,
        retailer_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
    ) -> None:
        """Verify the order exists, is not soft-deleted, belongs to the same
        (wholesaler, retailer), and the binding is active. Fails closed with
        a neutral 404 on any mismatch."""
        order = await self._get_order_by_id(db, order_id)
        if order is None or getattr(order, "is_deleted", False):
            raise _declaration_error(
                status.HTTP_404_NOT_FOUND, "ORDER_NOT_FOUND",
                "Order not found",
            )
        if (
            getattr(order, "wholesaler_id", None) != wholesaler_id
            or getattr(order, "retailer_id", None) != retailer_id
        ):
            raise _declaration_error(
                status.HTTP_404_NOT_FOUND, "DECLARATION_NOT_FOUND",
                "Declaration not found",
            )
        # Verify active binding.
        result = await db.execute(
            text(
                "SELECT status FROM public.wholesaler_retailer_bindings "
                "WHERE wholesaler_id = :wid AND retailer_id = :rid "
                "AND is_deleted IS FALSE LIMIT 1"
            ),
            {"wid": str(wholesaler_id), "rid": str(retailer_id)},
        )
        binding = result.fetchone()
        if binding is None or binding.status != "active":
            raise _declaration_error(
                status.HTTP_404_NOT_FOUND, "DECLARATION_NOT_FOUND",
                "Declaration not found",
            )

    async def _resolve_confirmed_replay(
        self,
        db: AsyncSession,
        declaration: Mapping[str, Any],
        wholesaler_id: uuid.UUID,
    ) -> CanonicalPaymentResult:
        """Build a CanonicalPaymentResult for an already-confirmed declaration.

        Zero new writes. Fails closed if the linked order is missing,
        soft-deleted, or does not match the declaration's wholesaler/retailer.
        Never returns order=None or empty order_state.
        """
        payment_id_raw = declaration.get("confirmation_payment_id")
        if payment_id_raw is None:
            raise _declaration_error(
                status.HTTP_409_CONFLICT,
                "DECLARATION_CONFIRMATION_KEY_CONFLICT",
                "Confirmed declaration is missing its canonical payment link",
            )
        payment_id = uuid.UUID(str(payment_id_raw))
        payment = await self._payment_repo.get_by_id_with_receipt(db, payment_id=payment_id)
        if payment is None:
            raise _declaration_error(
                status.HTTP_409_CONFLICT,
                "DECLARATION_CONFIRMATION_KEY_CONFLICT",
                "Confirmed declaration links to a missing payment",
            )
        receipt = payment.get("receipt_number")
        if not _is_valid_receipt_number(receipt):
            raise _declaration_error(
                status.HTTP_409_CONFLICT,
                "DECLARATION_CONFIRMATION_KEY_CONFLICT",
                "Confirmed declaration links to a payment without a valid receipt",
            )

        order = await self._get_order_by_id(db, uuid.UUID(str(declaration["order_id"])))
        if order is None or getattr(order, "is_deleted", False):
            raise _declaration_error(
                status.HTTP_409_CONFLICT,
                "DECLARATION_CONFIRMATION_KEY_CONFLICT",
                "Order for confirmed declaration no longer exists",
            )
        if (
            getattr(order, "wholesaler_id", None) != uuid.UUID(str(declaration["wholesaler_id"]))
            or getattr(order, "retailer_id", None) != uuid.UUID(str(declaration["retailer_id"]))
        ):
            raise _declaration_error(
                status.HTTP_409_CONFLICT,
                "DECLARATION_CONFIRMATION_KEY_CONFLICT",
                "Order ownership does not match confirmed declaration",
            )

        order_state = getattr(order.status, "value", "")
        return CanonicalPaymentResult(
            order=order,
            payment_record=payment,
            replayed=True,
            order_state=str(order_state),
        )

    async def _get_order_by_id(self, db: AsyncSession, order_id: uuid.UUID) -> OrderModel | None:
        result = await db.execute(
            select(OrderModel)
            .where(OrderModel.id == order_id)
            .where(OrderModel.is_deleted == False)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def _get_order_for_declaration(
        self,
        db: AsyncSession,
        *,
        order_id: str,
        retailer_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
    ) -> OrderModel | None:
        try:
            order_uuid = uuid.UUID(order_id)
        except (TypeError, ValueError):
            return None
        result = await db.execute(
            select(OrderModel)
            .where(OrderModel.id == order_uuid)
            .where(OrderModel.is_deleted == False)  # noqa: E712
            .where(OrderModel.retailer_id == retailer_id)
            .where(OrderModel.wholesaler_id == wholesaler_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _same_declaration_request(
        existing: Mapping[str, Any],
        *,
        order_id: str,
        declared_amount: Decimal,
        method: str,
        transfer_reference: str | None,
    ) -> bool:
        return (
            str(existing["order_id"]) == str(order_id)
            and Decimal(str(existing["declared_amount"])) == declared_amount
            and str(existing["method"]) == method
            and (existing.get("transfer_reference") or None) == (transfer_reference or None)
        )
