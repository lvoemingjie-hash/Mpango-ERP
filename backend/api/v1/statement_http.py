"""Shared statement-result → HTTP mapper (DC-12R1-MVP-R0-R1 / WPR-004).

Single source of truth for translating a :class:`StatementResult` produced by
``services.print_service.build_statement_print`` into either a
``StatementPrintView`` (success) or the precise controlled ``HTTPException``
(status code + ``{"code", "message"}`` detail) used by BOTH the supplier
(``api/v1/statements.py``) and retailer (``api/v1/client/statements.py``)
Contract D print routes.

Before this helper the two routes each carried a byte-equivalent private
``_map_statement_result`` copy, so a one-sided edit could silently drift the
supplier and retailer public contracts apart. Both routes now call this one
function; the byte-contract parity is enforced by the supplier/client parity
tests in ``tests/test_dc12r1_contract_d_statement_print.py`` (a one-sided
mutation must turn those tests RED).

Contract preserved EXACTLY (do not change any status/code/message here without
updating both routes and the parity tests):

    view present              -> return res.view
    res.not_found             -> 404 STATEMENT_NOT_AVAILABLE
    StatementPeriodError      -> 400 INVALID_DATE_RANGE
    StatementRangeTooLarge    -> 400 STATEMENT_RANGE_TOO_LARGE
    StatementLedgerScopeIncomplete -> 409 STATEMENT_LEDGER_SCOPE_INCOMPLETE
    StatementInternalInconsistent   -> 409 STATEMENT_INTERNAL_INCONSISTENT
    StatementReconciliationFailed   -> 409 STATEMENT_RECONCILIATION_FAILED
    fallback (any other error)      -> 404 STATEMENT_NOT_AVAILABLE

Integrity failures are NOT downgraded to a neutral 404 — they surface their
exact 409 codes. The global error handler in ``core/error_codes.py`` adds the
``request_id``; routes only raise ``HTTPException(detail={"code","message"})``.
"""
from __future__ import annotations

from fastapi import HTTPException, status

from repositories.statement_repository import (
    StatementInternalInconsistent,
    StatementLedgerScopeIncomplete,
    StatementPeriodError,
    StatementRangeTooLarge,
    StatementReconciliationFailed,
)
from schemas.print import StatementPrintView
from services.print_service import StatementResult


def map_statement_result(res: StatementResult) -> StatementPrintView:
    """Map a ``StatementResult`` to a view or raise the precise HTTP status.

    No partial document is returned after a fail-closed condition. Integrity
    failures surface their exact 409 codes (never downgraded to a neutral 404).
    """
    if res.view is not None:
        return res.view
    if res.not_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "STATEMENT_NOT_AVAILABLE", "message": "Statement not available"},
        )
    err = res.error
    if isinstance(err, StatementPeriodError):
        # Defensive: routes pre-validate via the shared parser (R1 rule 3).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_DATE_RANGE", "message": "Invalid date range."},
        )
    if isinstance(err, StatementRangeTooLarge):
        # Aggregate line cap exceeded — controlled 400, zero partial document.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "STATEMENT_RANGE_TOO_LARGE",
                "message": "Statement range is too large. Choose a shorter date range.",
            },
        )
    if isinstance(err, StatementLedgerScopeIncomplete):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STATEMENT_LEDGER_SCOPE_INCOMPLETE",
                "message": "Statement ledger scope is incomplete.",
            },
        )
    if isinstance(err, StatementInternalInconsistent):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STATEMENT_INTERNAL_INCONSISTENT",
                "message": "Statement internal arithmetic is inconsistent.",
            },
        )
    if isinstance(err, StatementReconciliationFailed):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STATEMENT_RECONCILIATION_FAILED",
                "message": "Statement reconciliation failed.",
            },
        )
    # Defensive: any other error -> neutral 404 (no internal disclosure).
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "STATEMENT_NOT_AVAILABLE", "message": "Statement not available"},
    )
