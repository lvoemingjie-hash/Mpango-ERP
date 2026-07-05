"""U6-B tenant onboarding schema contract tests."""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from models.tenant_onboarding import (
    EMAIL_VERIFICATION_TOKEN_PURPOSE,
    PASSWORD_RESET_TOKEN_PURPOSE,
    TERMINAL_PASSWORD_CLEANUP_STATES,
    TENANT_REGISTRATION_STATUSES,
    EmailVerificationToken,
    PasswordResetToken,
    TenantRegistration,
)


def _column_names(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def _index_names(model) -> set[str]:
    return {index.name for index in model.__table__.indexes}


def _constraint_names(model) -> set[str]:
    return {constraint.name for constraint in model.__table__.constraints if constraint.name}


def _postgres_where(index) -> str:
    where = index.dialect_options["postgresql"].get("where")
    if where is None:
        return ""
    return str(where.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_registration_table_matches_u6b_public_schema_contract():
    assert TenantRegistration.__table__.schema == "public"
    assert TenantRegistration.__tablename__ == "tenant_registrations"

    assert {
        "id",
        "company_name",
        "tenant_code",
        "country",
        "business_type",
        "phone",
        "owner_email",
        "owner_full_name",
        "password_hash",
        "password_hash_cleared_at",
        "password_hash_cleanup_reason",
        "status",
        "email_verified_at",
        "provisioning_started_at",
        "provisioning_completed_at",
        "failed_at",
        "failure_code",
        "failure_message",
        "retry_allowed_until",
        "wholesaler_id",
        "tenant_schema",
        "idempotency_key_hash",
        "request_fingerprint_hash",
        "expires_at",
        "created_at",
        "updated_at",
        "is_deleted",
        "deleted_at",
    }.issubset(_column_names(TenantRegistration))

    assert set(TENANT_REGISTRATION_STATUSES) == {
        "pending_email_verification",
        "email_verified",
        "provisioning",
        "active",
        "failed",
        "cancelled",
        "expired",
    }
    assert set(TERMINAL_PASSWORD_CLEANUP_STATES) == {"active", "cancelled", "expired"}
    assert TenantRegistration.__table__.c.password_hash.nullable is True
    assert "ck_tenant_registrations_status" in _constraint_names(TenantRegistration)
    assert "ck_tenant_registrations_owner_email_normalized" in _constraint_names(TenantRegistration)
    assert "ck_tenant_registrations_terminal_password_hash_cleared" in _constraint_names(
        TenantRegistration
    )
    assert "ck_tenant_registrations_failed_password_hash_retry_bound" in _constraint_names(
        TenantRegistration
    )


def test_registration_indexes_prevent_live_duplicate_email_and_support_replay_lookup():
    index_names = _index_names(TenantRegistration)
    assert {
        "ux_tenant_registrations_owner_email_live",
        "ux_tenant_registrations_tenant_code_reserved",
        "ux_tenant_registrations_wholesaler_id",
        "ux_tenant_registrations_tenant_schema",
        "ux_tenant_registrations_idempotency_key_hash",
        "ix_tenant_registrations_status",
        "ix_tenant_registrations_expires_at",
        "ix_tenant_registrations_request_fingerprint_hash",
    }.issubset(index_names)

    live_email_index = next(
        index
        for index in TenantRegistration.__table__.indexes
        if index.name == "ux_tenant_registrations_owner_email_live"
    )
    where = _postgres_where(live_email_index)
    assert "owner_email" in {column.name for column in live_email_index.columns}
    assert "pending_email_verification" in where
    assert "email_verified" in where
    assert "provisioning" in where
    assert "active" in where
    assert "failed" in where
    assert "cancelled" not in where
    assert "expired" not in where


def test_token_tables_store_only_hashes_and_single_use_lifecycle_fields():
    assert EmailVerificationToken.__table__.schema == "public"
    assert PasswordResetToken.__table__.schema == "public"
    assert EMAIL_VERIFICATION_TOKEN_PURPOSE == "signup_email_verification"
    assert PASSWORD_RESET_TOKEN_PURPOSE == "password_reset"  # pragma: allowlist secret

    assert {
        "id",
        "registration_id",
        "token_hash",
        "purpose",
        "expires_at",
        "used_at",
        "revoked_at",
        "sent_to_email",
        "send_count",
        "last_sent_at",
        "request_fingerprint_hash",
        "created_at",
        "updated_at",
        "is_deleted",
        "deleted_at",
    }.issubset(_column_names(EmailVerificationToken))
    assert {
        "id",
        "user_email_hash",
        "tenant_id",
        "tenant_schema",
        "token_hash",
        "purpose",
        "expires_at",
        "used_at",
        "revoked_at",
        "request_fingerprint_hash",
        "created_at",
        "updated_at",
        "is_deleted",
        "deleted_at",
    }.issubset(_column_names(PasswordResetToken))

    for model in (EmailVerificationToken, PasswordResetToken):
        columns = _column_names(model)
        assert "token_hash" in columns
        assert "token" not in columns
        assert "raw_token" not in columns
        assert "token_plaintext" not in columns


def test_token_indexes_enforce_hash_uniqueness_and_active_token_lookup():
    assert {
        "ux_email_verification_tokens_token_hash",
        "ux_email_verification_tokens_registration_active",
        "ix_email_verification_tokens_registration_id",
        "ix_email_verification_tokens_expires_at",
        "ix_email_verification_tokens_request_fingerprint_hash",
    }.issubset(_index_names(EmailVerificationToken))
    assert {
        "ux_password_reset_tokens_token_hash",
        "ux_password_reset_tokens_email_active_global",
        "ux_password_reset_tokens_email_tenant_active",
        "ix_password_reset_tokens_user_email_hash",
        "ix_password_reset_tokens_tenant_id",
        "ix_password_reset_tokens_expires_at",
        "ix_password_reset_tokens_request_fingerprint_hash",
    }.issubset(_index_names(PasswordResetToken))

    verification_active_index = next(
        index
        for index in EmailVerificationToken.__table__.indexes
        if index.name == "ux_email_verification_tokens_registration_active"
    )
    assert "used_at IS NULL" in _postgres_where(verification_active_index)
    assert "revoked_at IS NULL" in _postgres_where(verification_active_index)


def test_onboarding_schema_has_no_query_string_status_token_storage_design():
    table_columns = set()
    for model in (TenantRegistration, EmailVerificationToken, PasswordResetToken):
        table_columns.update(_column_names(model))

    assert "status_token" not in table_columns
    assert "status_token_query" not in table_columns
    assert "query_status_token" not in table_columns
