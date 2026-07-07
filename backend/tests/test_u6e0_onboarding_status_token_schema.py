"""U6-E0 onboarding status token schema contract tests."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql

from api.v1.auth import router as auth_router
from models.tenant_onboarding import (
    EMAIL_VERIFICATION_TOKEN_PURPOSE,
    ONBOARDING_STATUS_TOKEN_PURPOSE,
    PASSWORD_RESET_TOKEN_PURPOSE,
    EmailVerificationToken,
    OnboardingStatusToken,
    PasswordResetToken,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "027_onboarding_status_tokens.py"
)


def _column_names(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def _index_names(model) -> set[str]:
    return {index.name for index in model.__table__.indexes}


def _constraint_names(model) -> set[str]:
    return {constraint.name for constraint in model.__table__.constraints if constraint.name}


def _constraint_sql(model, constraint_name: str) -> str:
    constraint = next(
        constraint
        for constraint in model.__table__.constraints
        if constraint.name == constraint_name
    )
    return str(
        constraint.sqltext.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _postgres_where(index) -> str:
    where = index.dialect_options["postgresql"].get("where")
    if where is None:
        return ""
    return str(where.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_migration_and_model_define_onboarding_status_tokens_table():
    assert MIGRATION_PATH.exists()
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "onboarding_status_tokens" in migration_source
    assert "026_tenant_onboarding_auth_contract" in migration_source

    assert OnboardingStatusToken.__table__.schema == "public"
    assert OnboardingStatusToken.__tablename__ == "onboarding_status_tokens"
    assert {
        "id",
        "registration_id",
        "token_hash",
        "purpose",
        "expires_at",
        "revoked_at",
        "created_at",
        "updated_at",
        "is_deleted",
        "deleted_at",
    }.issubset(_column_names(OnboardingStatusToken))


def test_onboarding_status_tokens_store_only_hashes():
    columns = _column_names(OnboardingStatusToken)

    assert "token_hash" in columns
    assert "token" not in columns
    assert "raw_token" not in columns
    assert "token_plaintext" not in columns
    assert "status_token" not in columns


def test_onboarding_status_token_hash_unique_index_exists():
    index = next(
        index
        for index in OnboardingStatusToken.__table__.indexes
        if index.name == "ux_onboarding_status_tokens_token_hash"
    )

    assert index.unique is True
    assert {column.name for column in index.columns} == {"token_hash"}


def test_onboarding_status_token_registration_fk_exists():
    registration_id = OnboardingStatusToken.__table__.c.registration_id
    foreign_keys = list(registration_id.foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "public.tenant_registrations.id"
    assert foreign_keys[0].ondelete == "CASCADE"


def test_onboarding_status_token_active_registration_index_exists():
    index_names = _index_names(OnboardingStatusToken)
    assert "ix_onboarding_status_tokens_registration_id" in index_names
    assert "ix_onboarding_status_tokens_registration_active" in index_names

    active_index = next(
        index
        for index in OnboardingStatusToken.__table__.indexes
        if index.name == "ix_onboarding_status_tokens_registration_active"
    )

    assert {column.name for column in active_index.columns} == {"registration_id"}
    where = _postgres_where(active_index)
    assert "revoked_at IS NULL" in where
    assert "is_deleted = false" in where


def test_onboarding_status_token_purpose_default_and_checks():
    assert ONBOARDING_STATUS_TOKEN_PURPOSE == "onboarding_status"
    assert OnboardingStatusToken.__table__.c.purpose.default.arg == ONBOARDING_STATUS_TOKEN_PURPOSE
    assert "'onboarding_status'" in str(OnboardingStatusToken.__table__.c.purpose.server_default.arg)
    assert "ck_onboarding_status_tokens_purpose" in _constraint_names(OnboardingStatusToken)
    assert "ck_onboarding_status_tokens_expires_after_created" in _constraint_names(
        OnboardingStatusToken
    )
    assert _constraint_sql(
        OnboardingStatusToken, "ck_onboarding_status_tokens_purpose"
    ) == "purpose = 'onboarding_status'"


def test_u6b_existing_token_tables_remain_unchanged():
    assert EMAIL_VERIFICATION_TOKEN_PURPOSE == "signup_email_verification"
    assert PASSWORD_RESET_TOKEN_PURPOSE == "password_reset"  # pragma: allowlist secret

    assert "used_at" in _column_names(EmailVerificationToken)
    assert "sent_to_email" in _column_names(EmailVerificationToken)
    assert "user_email_hash" in _column_names(PasswordResetToken)
    assert "tenant_schema" in _column_names(PasswordResetToken)

    assert "ux_email_verification_tokens_token_hash" in _index_names(EmailVerificationToken)
    assert "ux_password_reset_tokens_token_hash" in _index_names(PasswordResetToken)


def test_no_onboarding_status_endpoint_or_runtime_route_added():
    route_paths = {route.path for route in auth_router.routes}

    assert "/onboarding/status" not in route_paths
    assert "/api/v1/auth/onboarding/status" not in route_paths
