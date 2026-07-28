"""Client Auth API — Retailer authentication and credential recovery.

DC-12R1-S1: forgot-password / reset-password (public, neutral responses).
DC-12R1-S2: supplier-scoped retailer login (public, neutral on mismatch).

All credential redemptions accept tokens ONLY in the JSON body.  Responses are
neutral (no account / relationship / role existence disclosure).  Unexpected
DB / runtime exceptions propagate to the existing sanitized error boundary;
they are NOT swallowed as INVALID_CREDENTIALS.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from core.error_codes import ErrorCode, MpangoAPIException
from core.security import create_contextual_token, verify_password
from db.sql_safety import validate_identifier
from models.wholesaler import Wholesaler
from schemas.retailer_credentials import (
    WHOLESALER_CODE_RE,
    RetailerCredentialResponse,
    RetailerCredentialResponseData,
    RetailerForgotPasswordRequest,
    RetailerLoginRequest,
    RetailerLoginResponse,
    RetailerLoginData,
    RetailerLoginTokens,
    RetailerLoginUser,
    RetailerLoginRetailer,
    RetailerLoginWholesaler,
    RetailerResetPasswordRequest,
)
from services.email_delivery import EmailDeliveryNotConfiguredError
from services.retailer_provisioning_service import (
    RESET_TOKEN_INVALID,
    RetailerCredentialTokenInvalidError,
    RetailerProvisioningService,
)

router = APIRouter()

NEUTRAL_RETAILER_CREDENTIAL_MESSAGE = (
    "Retailer credential result is not disclosed through this endpoint."
)

# Neutral 401 for all well-formed authentication mismatches.  The same
# contract is returned whether the email, wholesaler, binding, role, or
# password was wrong — no information leaks.
#
# DC-12R1-S2-R2: raised as the narrow MpangoAPIException contract (not a
# bare HTTPException with a dict detail) so the production
# mpango_exception_handler emits the exact public body
#   {"code": "INVALID_CREDENTIALS", "message": "Invalid credentials",
#    "request_id": "..."}
# with NO Python dict repr leaking into the message field.
INVALID_CREDENTIALS_MESSAGE = "Invalid credentials"


def _raise_invalid_credentials() -> None:
    """Raise the single neutral 401 used for all authentication mismatches.

    Uses MpangoAPIException (the production error contract) so the serialized
    body is the exact public envelope above — never a str(dict) repr.
    """
    raise MpangoAPIException(
        error_code=ErrorCode.INVALID_CREDENTIALS,
        message=INVALID_CREDENTIALS_MESSAGE,
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


# ---------------------------------------------------------------------------
# POST /login — Supplier-scoped retailer login (DC-12R1-S2)
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=RetailerLoginResponse,
    status_code=status.HTTP_200_OK,
)
async def retailer_login(
    request: RetailerLoginRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Authenticate a retailer against a single supplier portal.

    Flow (all within the single requested wholesaler's context):

    Registry/schema fail-closed (no tenant SQL runs before these pass):
    1. Normalize email and wholesaler_code (uppercase preference).
    2. Validate wholesaler_code format (regex). Malformed → 422, zero SQL.
    3. Resolve exactly one active registration via
       ``public.tenant_registrations JOIN public.wholesalers`` requiring
       ``tr.is_deleted IS FALSE``, ``tr.status = 'active'``, an active
       wholesaler and a non-null tenant_schema.
    4. Reject duplicate active registrations for the same wholesaler.
    5. ``validate_identifier(tenant_schema)`` (SQL-injection guard).
    6. Require ``tenant_schema == Wholesaler.derive_schema_from_id(w.id)``.

    Principal lifecycle (all must be live before any JWT is issued):
    7. Query **only** the requested wholesaler's tenant schema for a
       non-deleted, active user; verify the password.
    8. Resolve a non-deleted, active binding.
    9. Require a non-deleted retailer_operator role/membership.
    10. Load and validate a non-deleted retailer row BEFORE issuing tokens.

    Token issuance: contextual access + refresh JWTs via
    ``create_contextual_token`` (tenant_id, tenant_schema, roles only — no
    tmap/identity/available_tenants).

    All well-formed mismatches return the same neutral 401 INVALID_CREDENTIALS.
    Unexpected DB/runtime exceptions propagate (not swallowed).

    Scope gate: never calls ``find_user_across_tenants``.
    """
    # --- 1. Normalize -------------------------------------------------------
    normalized_email = str(request.email).strip().lower()
    # Uppercase preference: portal codes follow the DB regex ^[A-Z0-9]+$.
    # A lowercase code is normalized (not rejected) so users typing "abc123"
    # are treated as "ABC123"; genuine format errors (symbols, empty) still 422.
    raw_code = request.wholesaler_code.strip().upper()

    # --- 2. Format gate (no SQL) --------------------------------------------
    if not WHOLESALER_CODE_RE.match(raw_code):
        # DC-12R1-S2-R2: MpangoAPIException contract (not HTTPException w/ dict
        # detail) so the public 422 body is the exact envelope, no repr leak.
        raise MpangoAPIException(
            error_code=ErrorCode.INVALID_INPUT,
            message="Wholesaler code must be alphanumeric (A-Z, 0-9).",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # --- 3. Resolve registration via tenant_registrations + wholesalers -----
    # Authoritative public query: joins the registration (confirming active
    # onboarding state and not soft-deleted) with the wholesaler (confirming
    # active tenant state and not soft-deleted). A NULL tenant_schema is
    # never accepted.
    reg_rows = (
        await db.execute(
            text(
                """
                SELECT w.id, w.code, w.name, w.status,
                       tr.id AS registration_id, tr.tenant_schema
                FROM public.tenant_registrations tr
                JOIN public.wholesalers w
                  ON tr.wholesaler_id = w.id
                WHERE w.code = :code
                  AND w.is_deleted IS FALSE
                  AND w.status = 'active'
                  AND tr.is_deleted IS FALSE
                  AND tr.status = 'active'
                  AND tr.tenant_schema IS NOT NULL
                """
            ),
            {"code": raw_code},
        )
    ).fetchall()

    # No active registration+wholesaler pair → neutral 401.
    if not reg_rows:
        _raise_invalid_credentials()

    # --- 4. Reject duplicate active registrations ---------------------------
    # Fail-closed: more than one live registration for the same wholesaler is
    # an integrity violation. We never pick one arbitrarily; we refuse to
    # authenticate and surface a neutral 401 (no leakage).
    if len(reg_rows) > 1:
        _raise_invalid_credentials()

    reg = reg_rows[0]
    wholesaler_id = str(reg.id)
    tenant_schema = reg.tenant_schema

    # --- 5. SQL-injection guard on the tenant schema identifier ------------
    # validate_identifier raises ValueError on anything outside
    # ^[a-zA-Z_][a-zA-Z0-9_]{0,62}$. A ValueError here is an unexpected
    # condition (the registry stored an unsafe identifier) and must propagate
    # to the error boundary — it is NOT a credential mismatch.
    validate_identifier(tenant_schema, "tenant_schema")

    # --- 6. Schema must match the wholesaler's own derived schema -----------
    # Prevents a stale/tampered tenant_registrations row from pointing login
    # at the wrong schema. derive_schema_from_id is the authoritative source.
    if tenant_schema != Wholesaler.derive_schema_from_id(wholesaler_id):
        _raise_invalid_credentials()

    # --- 7. Query only the single wholesaler tenant schema (live user) -----
    user_row = await db.execute(
        text(
            f'SELECT id, email, full_name, password_hash, is_active '
            f'FROM "{tenant_schema}".users '
            f'WHERE email = :email '
            f'  AND is_deleted IS FALSE '
            f'LIMIT 1'
        ),
        {"email": normalized_email},
    )
    user = user_row.fetchone()

    if user is None:
        _raise_invalid_credentials()

    if not user.is_active:
        _raise_invalid_credentials()

    if not verify_password(request.password, user.password_hash):
        _raise_invalid_credentials()

    tenant_user_id = str(user.id)

    # --- 8. Resolve binding (non-deleted, active) --------------------------
    bind_row = await db.execute(
        text(
            """
            SELECT b.retailer_id, b.status
            FROM public.wholesaler_retailer_bindings b
            WHERE b.wholesaler_id = :wholesaler_id
              AND b.tenant_user_id = :tenant_user_id
              AND b.is_deleted IS FALSE
            LIMIT 1
            """
        ),
        {"wholesaler_id": wholesaler_id, "tenant_user_id": tenant_user_id},
    )
    binding = bind_row.fetchone()

    if binding is None:
        _raise_invalid_credentials()

    if binding.status != "active":
        _raise_invalid_credentials()

    # --- 9. Verify non-deleted retailer_operator role/membership ------------
    role_row = await db.execute(
        text(
            f'SELECT r.name '
            f'FROM "{tenant_schema}".roles r '
            f'JOIN "{tenant_schema}".user_roles ur ON ur.role_id = r.id '
            f'WHERE ur.user_id = :user_id '
            f'  AND r.name = :role_name '
            f'  AND r.is_deleted IS FALSE '
            f'LIMIT 1'
        ),
        {"user_id": tenant_user_id, "role_name": "retailer_operator"},
    )
    if role_row.fetchone() is None:
        _raise_invalid_credentials()

    # --- 10. Load + validate the retailer row BEFORE issuing tokens ---------
    # The binding must point at a non-deleted retailer. A missing/soft-deleted
    # retailer row is an integrity failure treated as a neutral 401.
    retailer_row = await db.execute(
        text(
            "SELECT id, name FROM public.retailers "
            "WHERE id = :rid AND is_deleted IS FALSE LIMIT 1"
        ),
        {"rid": binding.retailer_id},
    )
    retailer = retailer_row.fetchone()
    if retailer is None:
        _raise_invalid_credentials()

    # --- 11. Issue contextual tokens via create_contextual_token ------------
    access_token = create_contextual_token(
        user_id=tenant_user_id,
        roles=["retailer_operator"],
        tenant_id=wholesaler_id,
        tenant_schema=tenant_schema,
        token_type="access",
    )
    refresh_token = create_contextual_token(
        user_id=tenant_user_id,
        roles=["retailer_operator"],
        tenant_id=wholesaler_id,
        tenant_schema=tenant_schema,
        token_type="refresh",
    )

    # --- 12. Build response -------------------------------------------------
    return RetailerLoginResponse(
        success=True,
        data=RetailerLoginData(
            tokens=RetailerLoginTokens(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                user_id=tenant_user_id,
                tenant_id=wholesaler_id,
                tenant_schema=tenant_schema,
                roles=["retailer_operator"],
            ),
            user=RetailerLoginUser(
                id=tenant_user_id,
                email=user.email,
                full_name=user.full_name,
            ),
            retailer=RetailerLoginRetailer(
                id=str(binding.retailer_id),
                name=retailer.name,
            ),
            wholesaler=RetailerLoginWholesaler(
                id=wholesaler_id,
                code=reg.code,
                name=reg.name,
            ),
        ),
        timestamp=datetime.utcnow(),
    )


def _reject_query_token(http_request: Request, keys: tuple[str, ...]) -> None:
    """Reject any sensitive value in the query string (anti-leakage)."""
    if http_request is not None and any(k in http_request.query_params for k in keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": RESET_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
            },
        )


@router.post(
    "/forgot-password",
    response_model=RetailerCredentialResponse,
    status_code=status.HTTP_200_OK,
)
async def retailer_forgot_password(
    request: RetailerForgotPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    http_request: Request = None,
):
    """Request a retailer password-reset link.

    Always returns a neutral 200. A reset token is issued only when a verified
    retailer with an established password exists for the (email, wholesaler_code)
    pair. Production fails closed: SMTP failure rolls back the token and the
    response stays identical to the no-match case. No raw email/token/link is
    logged.
    """
    _reject_query_token(http_request, ("email", "wholesaler_code", "token"))
    service = RetailerProvisioningService(db)
    try:
        await service.request_password_reset(
            email=request.email, wholesaler_code=request.wholesaler_code
        )
    except EmailDeliveryNotConfiguredError:
        await db.rollback()
    except Exception:
        # Never leak account existence; respond neutral.
        await db.rollback()
    return RetailerCredentialResponse(
        data=RetailerCredentialResponseData(),
        message=NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
        timestamp=datetime.utcnow(),
    )


@router.post(
    "/reset-password",
    response_model=RetailerCredentialResponse,
    status_code=status.HTTP_200_OK,
)
async def retailer_reset_password(
    request: RetailerResetPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    http_request: Request = None,
):
    """Consume a retailer reset token and set a new password.

    Token must arrive in the body only; query-string token/password params are
    rejected. On success the new password is applied to every tenant user
    mapped to the same retailer_id (unified credential), never to unrelated
    same-email users. Invalid/expired/used/revoked tokens return a neutral 401.
    """
    _reject_query_token(
        http_request,
        ("reset_token", "resetToken", "new_password", "newPassword", "token"),
    )
    if not request.reset_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": RESET_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
            },
        )
    service = RetailerProvisioningService(db)
    try:
        await service.consume_password_reset(request.reset_token, request.new_password)
        await db.commit()
    except RetailerCredentialTokenInvalidError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": RESET_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
            },
        )
    except ValueError:
        # Password policy violation — surface as neutral 401 (no leak).
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": RESET_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
            },
        )
    return RetailerCredentialResponse(
        data=RetailerCredentialResponseData(),
        message=NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
        timestamp=datetime.utcnow(),
    )
