"""M1 authority and employment metadata; native users/RBAC remain authoritative."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class StaffAuthority(Base):
    __tablename__ = 'staff_authority'
    __table_args__ = (
        CheckConstraint('singleton = 1', name='ck_staff_authority_singleton'),
        CheckConstraint('authz_revision > 0', name='ck_staff_authority_revision'),
        CheckConstraint("(state='unmapped' AND owner_user_id IS NULL AND source IS NULL AND evidence_digest IS NULL) OR "
                        "(state='verified' AND owner_user_id IS NOT NULL AND tenant_id IS NOT NULL AND "
                        "registration_id IS NOT NULL AND source IS NOT NULL AND evidence_digest IS NOT NULL AND "
                        "source IN ('owner_setup','approved_mapping') AND "
                        "evidence_digest ~ '^[0-9a-f]{64}$')", name='ck_staff_authority_shape'),
    )
    singleton: Mapped[int] = mapped_column(Integer, primary_key=True, server_default=text('1'))
    tenant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    # Runtime owns tenant DDL but has no REFERENCES on migration-owned public
    # registration tables. The locked service verifies the complete identity.
    registration_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    owner_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'), unique=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'unmapped'"))
    source: Mapped[str | None] = mapped_column(String(32))
    evidence_digest: Mapped[str | None] = mapped_column(String(64))
    authz_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('1'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class StaffRoleTemplate(Base):
    __tablename__ = 'staff_role_templates'
    __table_args__ = (
        CheckConstraint("template_key IN ('warehouse','sales','finance')", name='ck_staff_template_key'),
        CheckConstraint('version > 0', name='ck_staff_template_version'),
    )
    template_key: Mapped[str] = mapped_column(String(16), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('roles.id', ondelete='RESTRICT'), unique=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('1'))


class StaffMembership(Base):
    __tablename__ = 'staff_memberships'
    __table_args__ = (
        CheckConstraint("credential_state IN ('pending','ready')", name='ck_staff_membership_state'),
        CheckConstraint('version > 0', name='ck_staff_membership_version'),
        CheckConstraint("employment_state IN ('invited','active','disabled')", name='ck_staff_employment_state'),
        CheckConstraint("employment_state <> 'active' OR credential_state='ready'", name='ck_staff_ready_active'),
    )
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'), primary_key=True)
    template_key: Mapped[str] = mapped_column(String(16), ForeignKey('staff_role_templates.template_key', ondelete='RESTRICT'))
    credential_state: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    employment_state: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'invited'"))
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('1'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))


class StaffCredentialSetupToken(Base):
    __tablename__ = 'staff_credential_setup_tokens'
    __table_args__ = (
        CheckConstraint("purpose='staff_credential_setup'", name='ck_staff_token_purpose'),
        CheckConstraint('membership_version > 0', name='ck_staff_token_version'),
        CheckConstraint('used_at IS NULL OR revoked_at IS NULL', name='ck_staff_token_terminal'),
        CheckConstraint('expires_at > created_at', name='ck_staff_token_expiry'),
        CheckConstraint('email=lower(btrim(email)) AND email NOT LIKE \'% %\'', name='ck_staff_token_email'),
        Index('ux_staff_token_active', 'tenant_id', 'user_id', unique=True,
              postgresql_where=text('used_at IS NULL AND revoked_at IS NULL')),
        {'schema': 'public'},
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('public.wholesalers.id', ondelete='RESTRICT'))
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    membership_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'staff_credential_setup'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StaffStockAuditEvent(Base):
    __tablename__ = 'staff_stock_audit_events'
    __table_args__ = ({'schema': 'public'},)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=text('gen_random_uuid()'))
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('public.wholesalers.id', ondelete='RESTRICT'))
    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    subject_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
