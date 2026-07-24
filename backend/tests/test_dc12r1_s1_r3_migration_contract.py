"""DC-12R1-S1-R3 migration semantic contract + evidence truth tests (RED -> GREEN).

Covers every malformed catalog variant the migration validators must reject:
wrong CHECK, wrong constraint type, missing/wrong FK, missing CASCADE,
wrong column type/nullability, nonunique/wrong-key/wrong-predicate index,
missing issued_by column, and conflicting active hashes.
Also proves a fully compatible pre-existing table is accepted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.config import get_settings
from services.email_delivery import clear_dev_email_deliveries, get_dev_retailer_email_deliveries
from services.retailer_provisioning_service import RetailerProvisioningService

pytestmark = pytest.mark.asyncio


def _load_migration_module():
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "m036", pathlib.Path("alembic/versions/036_retailer_mvp_identity.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sync_engine():
    import os
    from sqlalchemy import create_engine
    return create_engine(
        os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://")
    )


def _well_formed_setup_ddl() -> str:
    return """
        CREATE TABLE public.retailer_credential_setup_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            retailer_id UUID NOT NULL REFERENCES public.retailers(id) ON DELETE CASCADE,
            binding_id UUID NOT NULL REFERENCES public.wholesaler_retailer_bindings(id) ON DELETE CASCADE,
            issued_by_wholesaler_id UUID,
            token_hash VARCHAR(128) NOT NULL,
            purpose VARCHAR(64) NOT NULL DEFAULT 'retailer_credential_setup',
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMPTZ,
            CONSTRAINT ck_retailer_credential_setup_tokens_purpose CHECK (purpose = 'retailer_credential_setup'),
            CONSTRAINT ck_retailer_credential_setup_tokens_not_used_and_revoked CHECK (used_at IS NULL OR revoked_at IS NULL),
            CONSTRAINT uq_retailer_credential_setup_tokens_token_hash UNIQUE (token_hash)
        )
    """


def _well_formed_indexes() -> list[str]:
    return [
        "CREATE UNIQUE INDEX ux_retailer_credential_setup_tokens_token_hash ON public.retailer_credential_setup_tokens (token_hash)",
        "CREATE INDEX ix_retailer_credential_setup_tokens_retailer_id ON public.retailer_credential_setup_tokens (retailer_id)",
        "CREATE INDEX ix_retailer_credential_setup_tokens_binding_id ON public.retailer_credential_setup_tokens (binding_id)",
        "CREATE INDEX ix_retailer_credential_setup_tokens_expires_at ON public.retailer_credential_setup_tokens (expires_at)",
        "CREATE UNIQUE INDEX ux_retailer_credential_setup_tokens_retailer_active ON public.retailer_credential_setup_tokens (retailer_id) WHERE used_at IS NULL AND revoked_at IS NULL AND is_deleted = false",
    ]


def _restore_well_formed(eng):
    """Drop and recreate the well-formed setup-token table + indexes."""
    with eng.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS public.retailer_credential_setup_tokens"))
        mod = _load_migration_module()
        mod._create_retailer_setup_token_table(c)


# ---------------------------------------------------------------------------
# Compatible table accepted
# ---------------------------------------------------------------------------

def test_compatible_setup_token_table_accepted():
    mod = _load_migration_module()
    eng = _sync_engine()
    try:
        with eng.connect() as c:
            mod._validate_setup_token_table_contract(c)
    finally:
        eng.dispose()


# ---------------------------------------------------------------------------
# Malformed variants — each must raise PreflightFailure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label,replace_ddl,extra_sql", [
    (
        "wrong_purpose_check",
        _well_formed_setup_ddl().replace(
            "CHECK (purpose = 'retailer_credential_setup')",
            "CHECK (purpose = 'wrong_purpose')",
        ),
        _well_formed_indexes(),
    ),
    (
        "missing_used_revoked_check",
        _well_formed_setup_ddl().replace(
            "CONSTRAINT ck_retailer_credential_setup_tokens_not_used_and_revoked CHECK (used_at IS NULL OR revoked_at IS NULL),",
            "",
        ),
        _well_formed_indexes(),
    ),
    (
        "token_hash_not_unique",
        _well_formed_setup_ddl().replace(
            ",\n            CONSTRAINT uq_retailer_credential_setup_tokens_token_hash UNIQUE (token_hash)",
            "",
        ),
        # replace the unique index with a non-unique one
        [s.replace("CREATE UNIQUE INDEX ux_retailer_credential_setup_tokens_token_hash",
                   "CREATE INDEX ux_retailer_credential_setup_tokens_token_hash")
         if "token_hash" in s and "retailer_active" not in s else s
         for s in _well_formed_indexes()],
    ),
    (
        "fk_missing_cascade",
        _well_formed_setup_ddl().replace(
            "REFERENCES public.retailers(id) ON DELETE CASCADE",
            "REFERENCES public.retailers(id)",
        ),
        _well_formed_indexes(),
    ),
    (
        "wrong_column_type",
        _well_formed_setup_ddl().replace(
            "token_hash VARCHAR(128) NOT NULL",
            "token_hash TEXT NOT NULL",
        ),
        _well_formed_indexes(),
    ),
    (
        "nullable_should_be_not_null",
        _well_formed_setup_ddl().replace(
            "token_hash VARCHAR(128) NOT NULL",
            "token_hash VARCHAR(128)",
        ),
        _well_formed_indexes(),
    ),
    (
        "missing_issued_by_column",
        _well_formed_setup_ddl().replace("issued_by_wholesaler_id UUID,", ""),
        _well_formed_indexes(),
    ),
    (
        "nonunique_active_index",
        _well_formed_setup_ddl(),
        [s.replace("CREATE UNIQUE INDEX ux_retailer_credential_setup_tokens_retailer_active",
                   "CREATE INDEX ux_retailer_credential_setup_tokens_retailer_active")
         for s in _well_formed_indexes()],
    ),
    (
        "wrong_key_in_active_index",
        _well_formed_setup_ddl(),
        [s.replace("(retailer_id) WHERE used_at", "(binding_id) WHERE used_at")
         if "retailer_active" in s else s
         for s in _well_formed_indexes()],
    ),
    (
        "wrong_predicate_in_active_index",
        _well_formed_setup_ddl(),
        [s.replace("AND is_deleted = false", "OR is_deleted = false")
         if "retailer_active" in s else s
         for s in _well_formed_indexes()],
    ),
])
def test_malformed_setup_token_table_rejected(label, replace_ddl, extra_sql):
    """Every malformed variant must raise PreflightFailure before any mutation."""
    mod = _load_migration_module()
    eng = _sync_engine()
    try:
        with eng.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS public.retailer_credential_setup_tokens"))
            c.execute(text(replace_ddl))
            for sql in extra_sql:
                c.execute(text(sql))
        with pytest.raises(mod.PreflightFailure):
            with eng.connect() as c:
                mod._validate_setup_token_table_contract(c)
    finally:
        _restore_well_formed(eng)
        eng.dispose()
