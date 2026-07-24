"""DC-12R1-S1 retailer provisioning & credential lifecycle service.

Implements the atomic invitation-acceptance transaction (CTO order B) and the
retailer-owned credential setup/reset/reissue flows. Trust model (D-R2):
  * credentials + verified email are retailer-owned;
  * a wholesaler can only suspend its own binding and reissue setup while the
    retailer has no established password;
  * there is NO wholesaler password-reset or verified-email-change path.

Key invariants:
- One PostgreSQL transaction wraps provisioning; SMTP happens before commit and
  its failure rolls back every row (including the invitation consume).
- retailer_id is never inferred from email/schema/user strings. Credential
  tokens bind to the public identity (retailer_id [+ binding_id for setup]).
- Pending (first-setup) tenant users are created is_active=false with an
  unrecoverable random-secret hash; setup activates them. password_hash stays
  NOT NULL everywhere (CTO correction D).
- Unified credentials: a setup/reset writes the hash to every tenant user
  mapped to the same retailer_id, never to unrelated same-email users.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.security import hash_password
from db.sql_safety import validate_identifier
from db.tenant_filter import mark_session_as_system, run_as_system
from models.binding import WholesalerRetailerBinding
from models.invitation import Invitation
from models.retailer import Retailer
from models.retailer_credentials import (
    RETAILER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
    RETAILER_PASSWORD_RESET_TOKEN_PURPOSE,
    RetailerCredentialSetupToken,
    RetailerPasswordResetToken,
)
from models.wholesaler import Wholesaler
from services.email_delivery import (
    EmailDeliveryNotConfiguredError,
    record_retailer_reset_email,
    record_retailer_setup_email,
)
from services.onboarding_service import (
    build_retailer_reset_link,
    build_retailer_setup_link,
    generate_verification_token,
    hash_token,
    validate_password_policy,
)

logger = logging.getLogger(__name__)

RETAILER_OPERATOR_ROLE = "retailer_operator"
SETUP_TOKEN_TTL = timedelta(hours=24)
RESET_TOKEN_TTL = timedelta(hours=1)

# Controlled error codes (neutral where noted).
INVITATION_NOT_FOUND = "INVITATION_NOT_FOUND"
INVITATION_NOT_ACTIVE = "INVITATION_NOT_ACTIVE"
INVITATION_EXPIRED = "INVITATION_EXPIRED"
INVITATION_REVOKED = "INVITATION_REVOKED"
INVITATION_ALREADY_USED = "INVITATION_ALREADY_USED"
INVITATION_PHONE_MISMATCH = "INVITATION_PHONE_MISMATCH"
RETAILER_IDENTITY_CONFLICT = "RETAILER_IDENTITY_CONFLICT"
RETAILER_CREDENTIAL_CONFLICT = "RETAILER_CREDENTIAL_CONFLICT"
SETUP_EMAIL_DELIVERY_FAILED = "SETUP_EMAIL_DELIVERY_FAILED"
CREDENTIAL_ALREADY_ESTABLISHED = "CREDENTIAL_ALREADY_ESTABLISHED"
SETUP_TOKEN_INVALID = "SETUP_TOKEN_INVALID"
RESET_TOKEN_INVALID = "RESET_TOKEN_INVALID"
RETAILER_CREDENTIAL_NEUTRAL = "RETAILER_CREDENTIAL_NEUTRAL"  # response-only


class RetailerProvisioningError(Exception):
    """Controlled provisioning failure carrying a neutral code."""

    def __init__(self, code: str, *, http_status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.http_status = http_status


class RetailerCredentialTokenInvalidError(Exception):
    """Raised for invalid/expired/used/revoked retailer credential tokens."""


@dataclass(frozen=True)
class ProvisioningResult:
    """Outcome of an invitation acceptance (internal; API maps to a response)."""

    invitation: Invitation
    retailer: Retailer
    binding: WholesalerRetailerBinding
    setup_token_issued: bool


@dataclass(frozen=True)
class RetailerCredentialConsumeResult:
    action: str
    updated_user_count: int


def _normalize_email(email: Optional[str]) -> Optional[str]:
    if email is None:
        return None
    cleaned = email.strip().lower()
    return cleaned or None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tenant_schema_for(wholesaler: Wholesaler) -> str:
    schema = wholesaler.get_tenant_schema()
    validate_identifier(schema, "tenant schema")
    return schema


class RetailerProvisioningService:
    """Atomic invitation acceptance + retailer credential lifecycle."""

    def __init__(self, db: AsyncSession, *, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------
    # Atomic invitation acceptance (CTO order B)
    # ------------------------------------------------------------------

    async def register_with_invitation(
        self,
        *,
        invitation_code: str,
        phone: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
    ) -> ProvisioningResult:
        """Accept an invitation in one transaction (CTO order B).

        Order: lock invitation -> validate -> retailer -> binding+user+mapping+
        role -> setup token -> SMTP before commit -> mark used -> commit.
        Any failure rolls back everything, including the invitation state.
        Raises RetailerProvisioningError on controlled failures.
        """
        mark_session_as_system(self.db, reason="retailer_invitation_accept")
        with run_as_system(reason="retailer_invitation_accept"):
            # 1. SELECT invitation FOR UPDATE by code.
            invitation = await self._lock_invitation(invitation_code)
            # 2. Validate active / expiry / revoke / phone match.
            self._validate_invitation(invitation, phone)
            # 3. Select/create retailer (canonical identity R_id).
            retailer = await self._resolve_or_create_retailer(
                phone=phone, name=name, email=email, address=address
            )
            # 4. Resolve/create binding + tenant user; write mapping; grant role.
            wholesaler = await self._load_wholesaler(invitation.wholesaler_id)
            tenant_schema = _tenant_schema_for(wholesaler)
            binding, setup_token_raw = await self._provision_relationship(
                wholesaler=wholesaler,
                tenant_schema=tenant_schema,
                invitation=invitation,
                retailer=retailer,
            )
            # 5-6. Create setup token already done inside _provision_relationship
            #      (returns the raw token or None). Send SMTP before commit.
            if setup_token_raw is not None:
                await self._send_setup_email(
                    retailer=retailer, raw_token=setup_token_raw
                )
            # 7. Mark invitation used with used_retailer_id (R_id exists now).
            await self._mark_invitation_used(invitation, retailer.id)
            await self.db.flush()
        return ProvisioningResult(
            invitation=invitation,
            retailer=retailer,
            binding=binding,
            setup_token_issued=setup_token_raw is not None,
        )

    async def _lock_invitation(self, code: str) -> Invitation:
        result = await self.db.execute(
            select(Invitation)
            .where(Invitation.code == code)
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        invitation = result.scalar_one_or_none()
        if invitation is None:
            raise RetailerProvisioningError(INVITATION_NOT_FOUND, http_status=404)
        return invitation

    def _validate_invitation(self, invitation: Invitation, phone: str) -> None:
        now = _now()
        if invitation.status == "revoked" or invitation.revoked_at is not None:
            raise RetailerProvisioningError(INVITATION_REVOKED, http_status=410)
        if invitation.status == "used" or invitation.used_at is not None:
            raise RetailerProvisioningError(INVITATION_ALREADY_USED, http_status=410)
        if invitation.status != "active":
            raise RetailerProvisioningError(INVITATION_NOT_ACTIVE, http_status=410)
        if invitation.expires_at is not None and invitation.expires_at <= now:
            raise RetailerProvisioningError(INVITATION_EXPIRED, http_status=410)
        if invitation.retailer_phone and invitation.retailer_phone != phone:
            raise RetailerProvisioningError(INVITATION_PHONE_MISMATCH, http_status=409)

    async def _resolve_or_create_retailer(
        self,
        *,
        phone: str,
        name: Optional[str],
        email: Optional[str],
        address: Optional[str],
    ) -> Retailer:
        normalized_email = _normalize_email(email)
        result = await self.db.execute(
            select(Retailer).where(Retailer.phone == phone).execution_options(ignore_tenant=True)
        )
        retailer = result.scalar_one_or_none()
        if retailer is None:
            retailer = Retailer(
                phone=phone, name=name, email=normalized_email, address=address
            )
            self.db.add(retailer)
            await self.db.flush()
            return retailer
        # Existing retailer (matched by phone): submitted email must be consistent
        # with the canonical email (CTO constraint #4, fail-closed).
        if normalized_email is not None:
            if retailer.email_verified_at is not None:
                # Verified canonical email is immutable via this path.
                if (retailer.email or "").strip().lower() != normalized_email:
                    raise RetailerProvisioningError(
                        RETAILER_IDENTITY_CONFLICT, http_status=409
                    )
            else:
                # Unverified/legacy email: do NOT silently overwrite. Only adopt
                # the submitted email if the canonical email is currently NULL.
                if retailer.email is None:
                    retailer.email = normalized_email
                elif retailer.email.strip().lower() != normalized_email:
                    raise RetailerProvisioningError(
                        RETAILER_IDENTITY_CONFLICT, http_status=409
                    )
        return retailer

    async def _load_wholesaler(self, wholesaler_id: uuid.UUID) -> Wholesaler:
        result = await self.db.execute(
            select(Wholesaler)
            .where(Wholesaler.id == wholesaler_id)
            .execution_options(ignore_tenant=True)
        )
        wholesaler = result.scalar_one_or_none()
        if wholesaler is None:
            raise RetailerProvisioningError(INVITATION_NOT_FOUND, http_status=404)
        return wholesaler

    async def _provision_relationship(
        self,
        *,
        wholesaler: Wholesaler,
        tenant_schema: str,
        invitation: Invitation,
        retailer: Retailer,
    ) -> tuple[WholesalerRetailerBinding, Optional[str]]:
        """Steps 4-6: binding + tenant user + mapping + role + optional setup token."""
        # Binding (respect (wholesaler_id, retailer_id) uniqueness).
        binding = await self._get_or_create_binding(
            wholesaler_id=wholesaler.id, retailer_id=retailer.id
        )

        # Resolve unified credential state across mapped copies for this retailer.
        cred_state = await self._resolve_unified_credential(retailer.id)
        now = _now()
        setup_token_raw: Optional[str] = None

        if cred_state.conflict:
            raise RetailerProvisioningError(
                RETAILER_CREDENTIAL_CONFLICT, http_status=409
            )

        if binding.tenant_user_id is not None:
            # Re-bind to an existing relationship: no new user/token needed.
            return binding, None

        # Create the tenant-local user for this relationship.
        if cred_state.identical_hash is not None:
            # Copy existing identical hash; user is active immediately.
            user_id = await self._create_tenant_user(
                tenant_schema=tenant_schema,
                email=retailer.email,
                password_hash=cred_state.identical_hash,
                is_active=True,
            )
        else:
            # No mapped password yet: pending user (is_active=false) with an
            # unrecoverable random-secret hash. Setup will activate + set real pw.
            placeholder_hash = hash_password(secrets.token_urlsafe(32))
            user_id = await self._create_tenant_user(
                tenant_schema=tenant_schema,
                email=retailer.email,
                password_hash=placeholder_hash,
                is_active=False,
            )

        # Write back the authoritative mapping.
        await self._set_binding_tenant_user(binding.id, user_id)
        binding.tenant_user_id = user_id

        # Grant retailer_operator role in the tenant.
        await self._grant_retailer_operator(tenant_schema=tenant_schema, user_id=user_id)

        # Issue a setup token only when the retailer has no established password.
        if cred_state.identical_hash is None:
            setup_token_raw = generate_verification_token()
            self.db.add(
                RetailerCredentialSetupToken(
                    retailer_id=retailer.id,
                    binding_id=binding.id,
                    issued_by_wholesaler_id=wholesaler.id,
                    token_hash=hash_token(setup_token_raw, self.settings),
                    purpose=RETAILER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
                    expires_at=now + SETUP_TOKEN_TTL,
                )
            )
            await self.db.flush()

        return binding, setup_token_raw

    async def _get_or_create_binding(
        self, *, wholesaler_id: uuid.UUID, retailer_id: uuid.UUID
    ) -> WholesalerRetailerBinding:
        result = await self.db.execute(
            select(WholesalerRetailerBinding)
            .where(
                WholesalerRetailerBinding.wholesaler_id == wholesaler_id,
                WholesalerRetailerBinding.retailer_id == retailer_id,
                WholesalerRetailerBinding.is_deleted.is_(False),
            )
            .execution_options(ignore_tenant=True)
        )
        binding = result.scalar_one_or_none()
        if binding is not None:
            return binding
        binding = WholesalerRetailerBinding(
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
            status="active",
            tenant_user_id=None,
        )
        self.db.add(binding)
        await self.db.flush()
        return binding

    async def _set_binding_tenant_user(
        self, binding_id: uuid.UUID, tenant_user_id: uuid.UUID
    ) -> None:
        await self.db.execute(
            text(
                "UPDATE public.wholesaler_retailer_bindings "
                "SET tenant_user_id = :tuid, updated_at = now() WHERE id = :bid"
            ),
            {"tuid": tenant_user_id, "bid": binding_id},
            execution_options={"ignore_tenant": True},
        )

    async def _create_tenant_user(
        self,
        *,
        tenant_schema: str,
        email: Optional[str],
        password_hash: str,
        is_active: bool,
    ) -> uuid.UUID:
        validate_identifier(tenant_schema, "tenant schema")
        if email is None:
            # A retailer without an email cannot get a login identity.
            raise RetailerProvisioningError(
                RETAILER_IDENTITY_CONFLICT, http_status=409
            )
        result = await self.db.execute(
            text(
                f'INSERT INTO "{tenant_schema}".users '
                "(email, password_hash, is_active) "
                "VALUES (:email, :password_hash, :is_active) RETURNING id"
            ),
            {"email": email, "password_hash": password_hash, "is_active": is_active},
        )
        row = result.first()
        if row is None:
            raise RetailerProvisioningError(
                "RETAILER_EMAIL_ALREADY_BOUND", http_status=409
            )
        return uuid.UUID(str(row[0]))

    async def _grant_retailer_operator(
        self, *, tenant_schema: str, user_id: uuid.UUID
    ) -> None:
        validate_identifier(tenant_schema, "tenant schema")
        await self.db.execute(
            text(
                f'INSERT INTO "{tenant_schema}".user_roles (user_id, role_id) '
                f"SELECT :user_id, r.id FROM \"{tenant_schema}\".roles r "
                "WHERE r.name = :role_name "
                "AND NOT EXISTS ("
                f"SELECT 1 FROM \"{tenant_schema}\".user_roles ur "
                "WHERE ur.user_id = :user_id AND ur.role_id = r.id)"
            ),
            {"user_id": user_id, "role_name": RETAILER_OPERATOR_ROLE},
        )

    async def _mark_invitation_used(
        self, invitation: Invitation, retailer_id: uuid.UUID
    ) -> None:
        now = _now()
        await self.db.execute(
            text(
                "UPDATE public.invitations SET status = 'used', "
                "used_retailer_id = :rid, used_at = :used_at, updated_at = now() "
                "WHERE id = :iid"
            ),
            {"iid": invitation.id, "rid": retailer_id, "used_at": now},
            execution_options={"ignore_tenant": True},
        )

    async def _send_setup_email(
        self, *, retailer: Retailer, raw_token: str
    ) -> None:
        """SMTP before commit (CTO constraint #5). Failure rolls back the txn."""
        if retailer.email is None:
            # Should not happen (setup tokens are only issued when email exists);
            # fail closed rather than silently skip.
            raise RetailerProvisioningError(
                SETUP_EMAIL_DELIVERY_FAILED, http_status=503
            )
        try:
            record_retailer_setup_email(
                settings=self.settings,
                to_email=retailer.email,
                token=raw_token,
                setup_link=build_retailer_setup_link(raw_token, self.settings),
            )
        except EmailDeliveryNotConfiguredError as exc:
            # Controlled: roll back provisioning; invitation stays reusable.
            raise RetailerProvisioningError(
                SETUP_EMAIL_DELIVERY_FAILED, http_status=503
            ) from exc

    # ------------------------------------------------------------------
    # Unified credential resolution
    # ------------------------------------------------------------------

    @dataclass
    class _CredentialState:
        identical_hash: Optional[str]
        conflict: bool

    async def _resolve_unified_credential(
        self, retailer_id: uuid.UUID
    ) -> "_CredentialState":
        """Inspect mapped tenant-user copies for the retailer (§2.2).

        None-with-password -> issue setup token (identical_hash=None).
        Identical hashes   -> copy (identical_hash set, no setup token).
        Conflicting hashes -> fail closed RETAILER_CREDENTIAL_CONFLICT.
        """
        mappings = await self._mapped_tenant_users(retailer_id)
        hashes: list[str] = []
        for _binding_id, schema, user_id in mappings:
            validate_identifier(schema, "tenant schema")
            row = (
                await self.db.execute(
                    text(
                        f'SELECT password_hash FROM "{schema}".users '
                        "WHERE id = :uid AND is_deleted = false"
                    ),
                    {"uid": user_id},
                )
            ).first()
            if row is not None and row[0]:
                hashes.append(str(row[0]))
        unique = set(hashes)
        if len(unique) > 1:
            return self._CredentialState(identical_hash=None, conflict=True)
        if len(unique) == 1:
            return self._CredentialState(
                identical_hash=next(iter(unique)), conflict=False
            )
        return self._CredentialState(identical_hash=None, conflict=False)

    async def _mapped_tenant_users(
        self, retailer_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str, uuid.UUID]]:
        """Return (binding_id, tenant_schema, user_id) for mapped copies.

        Resolves the tenant schema from the binding's wholesaler. The user_id
        comes from binding.tenant_user_id (the authoritative mapping).
        """
        result = await self.db.execute(
            select(
                WholesalerRetailerBinding.id,
                WholesalerRetailerBinding.tenant_user_id,
                WholesalerRetailerBinding.wholesaler_id,
            )
            .where(
                WholesalerRetailerBinding.retailer_id == retailer_id,
                WholesalerRetailerBinding.tenant_user_id.isnot(None),
                WholesalerRetailerBinding.is_deleted.is_(False),
            )
            .execution_options(ignore_tenant=True)
        )
        out: list[tuple[uuid.UUID, str, uuid.UUID]] = []
        for binding_id, tuid, wholesaler_id in result.all():
            ws = (
                await self.db.execute(
                    select(Wholesaler).where(Wholesaler.id == wholesaler_id)
                )
            ).scalar_one_or_none()
            if ws is None:
                continue
            schema = _tenant_schema_for(ws)
            out.append((binding_id, schema, uuid.UUID(str(tuid))))
        return out

    async def _retailer_has_established_password(self, retailer_id: uuid.UUID) -> bool:
        """True if any mapped copy has a real (non-placeholder) password.

        Because a setup token is only issued when no copy has a password, and
        setup writes a real password + activates the user, "established" is
        equivalent to "any mapped copy is_active=true with a password_hash".
        """
        for _binding_id, schema, user_id in await self._mapped_tenant_users(retailer_id):
            validate_identifier(schema, "tenant schema")
            row = (
                await self.db.execute(
                    text(
                        f'SELECT is_active FROM "{schema}".users '
                        "WHERE id = :uid AND is_deleted = false"
                    ),
                    {"uid": user_id},
                )
            ).first()
            if row is not None and row[0]:
                return True
        return False

    # ------------------------------------------------------------------
    # Credential setup consumption
    # ------------------------------------------------------------------

    async def consume_setup_token(
        self, raw_token: str, new_password: str
    ) -> RetailerCredentialConsumeResult:
        validate_password_policy(new_password)
        token_row = await self._actionable_setup_token(raw_token)
        retailer_id = token_row.retailer_id
        new_hash = hash_password(new_password)
        updated = await self._write_hash_to_mapped_copies(
            retailer_id=retailer_id, new_hash=new_hash, activate=True
        )
        # Mark canonical email verified.
        await self.db.execute(
            text(
                "UPDATE public.retailers SET email_verified_at = now(), "
                "updated_at = now() WHERE id = :rid"
            ),
            {"rid": retailer_id},
            execution_options={"ignore_tenant": True},
        )
        await self._consume_setup_token_row(token_row)
        await self.db.flush()
        return RetailerCredentialConsumeResult(action="setup", updated_user_count=updated)

    async def _actionable_setup_token(self, raw_token: str) -> RetailerCredentialSetupToken:
        th = hash_token(raw_token, self.settings)
        now = _now()
        result = await self.db.execute(
            select(RetailerCredentialSetupToken)
            .where(RetailerCredentialSetupToken.token_hash == th)
            .where(
                RetailerCredentialSetupToken.purpose
                == RETAILER_CREDENTIAL_SETUP_TOKEN_PURPOSE
            )
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        token_row = result.scalar_one_or_none()
        if not self._is_actionable(token_row, now):
            raise RetailerCredentialTokenInvalidError(SETUP_TOKEN_INVALID)
        return token_row

    async def _consume_setup_token_row(
        self, token_row: RetailerCredentialSetupToken
    ) -> None:
        now = _now()
        result = await self.db.execute(
            text(
                "UPDATE public.retailer_credential_setup_tokens SET used_at = :now "
                "WHERE id = :tid AND used_at IS NULL AND revoked_at IS NULL"
            ),
            {"now": now, "tid": token_row.id},
            execution_options={"ignore_tenant": True},
        )
        if result.rowcount == 0:
            raise RetailerCredentialTokenInvalidError(SETUP_TOKEN_INVALID)

    # ------------------------------------------------------------------
    # Setup reissue (tenant-scoped, restricted)
    # ------------------------------------------------------------------

    async def reissue_setup_token(
        self,
        *,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
        issued_by_user_id: uuid.UUID,
    ) -> str:
        """Reissue a setup token ONLY while the retailer has no established password.

        Tenant-scoped: the caller must prove wholesaler_id owns a binding for
        retailer_id. Returns the raw token (memory-only; handed to SMTP). Raises
        RetailerProvisioningError(CREDENTIAL_ALREADY_ESTABLISHED) otherwise.
        """
        binding = await self._verify_tenant_owns_retailer(
            wholesaler_id=wholesaler_id, retailer_id=retailer_id
        )
        if await self._retailer_has_established_password(retailer_id):
            raise RetailerProvisioningError(
                CREDENTIAL_ALREADY_ESTABLISHED, http_status=409
            )
        now = _now()
        # Revoke any prior active setup token for this retailer.
        await self.db.execute(
            text(
                "UPDATE public.retailer_credential_setup_tokens SET revoked_at = :now "
                "WHERE retailer_id = :rid AND used_at IS NULL AND revoked_at IS NULL "
                "AND is_deleted = false"
            ),
            {"now": now, "rid": retailer_id},
            execution_options={"ignore_tenant": True},
        )
        raw_token = generate_verification_token()
        self.db.add(
            RetailerCredentialSetupToken(
                retailer_id=retailer_id,
                binding_id=binding.id,
                issued_by_wholesaler_id=wholesaler_id,
                token_hash=hash_token(raw_token, self.settings),
                purpose=RETAILER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
                expires_at=now + SETUP_TOKEN_TTL,
            )
        )
        await self.db.flush()
        # Send to canonical email only.
        retailer = await self._load_retailer(retailer_id)
        if retailer.email is None or retailer.email_verified_at is not None:
            raise RetailerProvisioningError(
                CREDENTIAL_ALREADY_ESTABLISHED, http_status=409
            )
        try:
            record_retailer_setup_email(
                settings=self.settings,
                to_email=retailer.email,
                token=raw_token,
                setup_link=build_retailer_setup_link(raw_token, self.settings),
            )
        except EmailDeliveryNotConfiguredError as exc:
            raise RetailerProvisioningError(
                SETUP_EMAIL_DELIVERY_FAILED, http_status=503
            ) from exc
        return raw_token

    async def _verify_tenant_owns_retailer(
        self, *, wholesaler_id: uuid.UUID, retailer_id: uuid.UUID
    ) -> WholesalerRetailerBinding:
        result = await self.db.execute(
            select(WholesalerRetailerBinding)
            .where(
                WholesalerRetailerBinding.wholesaler_id == wholesaler_id,
                WholesalerRetailerBinding.retailer_id == retailer_id,
                WholesalerRetailerBinding.is_deleted.is_(False),
            )
            .execution_options(ignore_tenant=True)
        )
        binding = result.scalar_one_or_none()
        if binding is None:
            # Neutral 404 — do not disclose the relationship exists (CTO #2).
            raise RetailerProvisioningError("RETAILER_NOT_FOUND", http_status=404)
        return binding

    async def _load_retailer(self, retailer_id: uuid.UUID) -> Retailer:
        result = await self.db.execute(
            select(Retailer)
            .where(Retailer.id == retailer_id)
            .execution_options(ignore_tenant=True)
        )
        retailer = result.scalar_one_or_none()
        if retailer is None:
            raise RetailerProvisioningError("RETAILER_NOT_FOUND", http_status=404)
        return retailer

    # ------------------------------------------------------------------
    # Retailer self-service forgot/reset (truly neutral)
    # ------------------------------------------------------------------

    async def request_password_reset(
        self, *, email: str, wholesaler_code: str
    ) -> bool:
        """Neutral forgot-password. Returns whether a token was issued (internal).

        Always-neutral: no-account / unverified-email / wrong-wholesaler-code /
        SMTP-failure all behave identically to the caller. SMTP failure rolls
        back the token and is logged sanitized (CTO constraint #3).
        """
        normalized = _normalize_email(email) or ""
        retailer = await self._find_verified_retailer_for_wholesaler(
            normalized=normalized, wholesaler_code=wholesaler_code
        )
        if retailer is None:
            return False
        if not await self._retailer_has_established_password(retailer.id):
            return False
        now = _now()
        await self.db.execute(
            text(
                "UPDATE public.retailer_password_reset_tokens SET revoked_at = :now "
                "WHERE retailer_id = :rid AND used_at IS NULL AND revoked_at IS NULL "
                "AND is_deleted = false"
            ),
            {"now": now, "rid": retailer.id},
            execution_options={"ignore_tenant": True},
        )
        raw_token = generate_verification_token()
        self.db.add(
            RetailerPasswordResetToken(
                retailer_id=retailer.id,
                token_hash=hash_token(raw_token, self.settings),
                purpose=RETAILER_PASSWORD_RESET_TOKEN_PURPOSE,
                expires_at=now + RESET_TOKEN_TTL,
            )
        )
        await self.db.flush()
        try:
            record_retailer_reset_email(
                settings=self.settings,
                to_email=retailer.email,
                token=raw_token,
                reset_link=build_retailer_reset_link(raw_token, self.settings),
            )
        except EmailDeliveryNotConfiguredError:
            # Roll back the token; log sanitized (no email/token/link). The API
            # returns the same neutral response as the no-account case.
            logger.warning(
                "retailer reset email delivery failed (retailer_id masked); "
                "token rolled back"
            )
            raise
        return True

    async def consume_password_reset(
        self, raw_token: str, new_password: str
    ) -> RetailerCredentialConsumeResult:
        validate_password_policy(new_password)
        token_row = await self._actionable_reset_token(raw_token)
        retailer_id = token_row.retailer_id
        new_hash = hash_password(new_password)
        updated = await self._write_hash_to_mapped_copies(
            retailer_id=retailer_id, new_hash=new_hash, activate=True
        )
        now = _now()
        result = await self.db.execute(
            text(
                "UPDATE public.retailer_password_reset_tokens SET used_at = :now "
                "WHERE id = :tid AND used_at IS NULL AND revoked_at IS NULL"
            ),
            {"now": now, "tid": token_row.id},
            execution_options={"ignore_tenant": True},
        )
        if result.rowcount == 0:
            raise RetailerCredentialTokenInvalidError(RESET_TOKEN_INVALID)
        await self.db.flush()
        return RetailerCredentialConsumeResult(action="reset", updated_user_count=updated)

    async def _actionable_reset_token(self, raw_token: str) -> RetailerPasswordResetToken:
        th = hash_token(raw_token, self.settings)
        now = _now()
        result = await self.db.execute(
            select(RetailerPasswordResetToken)
            .where(RetailerPasswordResetToken.token_hash == th)
            .where(
                RetailerPasswordResetToken.purpose
                == RETAILER_PASSWORD_RESET_TOKEN_PURPOSE
            )
            .with_for_update()
            .execution_options(ignore_tenant=True),
        )
        token_row = result.scalar_one_or_none()
        if not self._is_actionable(token_row, now):
            raise RetailerCredentialTokenInvalidError(RESET_TOKEN_INVALID)
        return token_row

    async def _find_verified_retailer_for_wholesaler(
        self, *, normalized: str, wholesaler_code: str
    ) -> Optional[Retailer]:
        """A match requires a verified-email retailer bound to that wholesaler."""
        if not normalized:
            return None
        row = (
            await self.db.execute(
                text(
                    """
                    SELECT r.id FROM public.retailers r
                    JOIN public.wholesaler_retailer_bindings b
                      ON b.retailer_id = r.id AND b.is_deleted = false
                    JOIN public.wholesalers w ON w.id = b.wholesaler_id
                    WHERE lower(r.email) = :email
                      AND r.email_verified_at IS NOT NULL
                      AND r.is_deleted = false
                      AND lower(w.code) = lower(:code)
                      AND w.is_deleted = false
                    LIMIT 1
                    """
                ),
                {"email": normalized, "code": wholesaler_code},
                execution_options={"ignore_tenant": True},
            )
        ).first()
        if row is None:
            return None
        result = await self.db.execute(
            select(Retailer).where(Retailer.id == row[0]).execution_options(ignore_tenant=True)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _write_hash_to_mapped_copies(
        self, *, retailer_id: uuid.UUID, new_hash: str, activate: bool
    ) -> int:
        """Write the new hash to every tenant user mapped to retailer_id.

        Never touches unrelated same-email users — the update is keyed on the
        binding's tenant_user_id, not on users.email (CTO correction D-R2 #2/#4).
        """
        updated = 0
        for _binding_id, schema, user_id in await self._mapped_tenant_users(retailer_id):
            validate_identifier(schema, "tenant schema")
            try:
                async with self.db.begin_nested():
                    res = await self.db.execute(
                        text(
                            f'UPDATE "{schema}".users '
                            "SET password_hash = :h, is_active = true, "
                            "is_deleted = false, deleted_at = NULL, updated_at = now() "
                            "WHERE id = :uid"
                        ),
                        {"h": new_hash, "uid": user_id},
                    )
                    updated += res.rowcount
            except Exception:
                # Isolate per-tenant failures via SAVEPOINT rollback (mirrors
                # password_reset_service). Do not abort the whole reset.
                continue
        return updated

    @staticmethod
    def _is_actionable(token_row, now: datetime) -> bool:
        if token_row is None:
            return False
        if token_row.is_deleted:
            return False
        if token_row.used_at is not None:
            return False
        if token_row.revoked_at is not None:
            return False
        if token_row.expires_at <= now:
            return False
        return True
