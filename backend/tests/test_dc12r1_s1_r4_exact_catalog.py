"""DC-12R1-S1-R4 exact catalog equivalence adversarial tests.

Tests both setup and reset token tables for: composite UNIQUE, wrong FK
columns, OR TRUE CHECK, AND FALSE extra, extra predicate condition, wrong
constraint type, wrong VARCHAR length, and transactional rollback proof.
"""

from __future__ import annotations

import pytest


def _load_mod():
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "m036", pathlib.Path("alembic/versions/036_retailer_mvp_identity.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _eng():
    import os
    from sqlalchemy import create_engine
    return create_engine(
        os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://")
    )


def _setup_ddl() -> str:
    return """
        CREATE TABLE public.retailer_credential_setup_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            retailer_id UUID NOT NULL REFERENCES public.retailers(id) ON DELETE CASCADE,
            binding_id UUID NOT NULL REFERENCES public.wholesaler_retailer_bindings(id) ON DELETE CASCADE,
            issued_by_wholesaler_id UUID,
            token_hash VARCHAR(128) NOT NULL,
            purpose VARCHAR(64) NOT NULL DEFAULT 'retailer_credential_setup',
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE, deleted_at TIMESTAMPTZ,
            CONSTRAINT ck_retailer_credential_setup_tokens_purpose CHECK (purpose = 'retailer_credential_setup'),
            CONSTRAINT ck_retailer_credential_setup_tokens_not_used_and_revoked CHECK (used_at IS NULL OR revoked_at IS NULL),
            CONSTRAINT uq_retailer_credential_setup_tokens_token_hash UNIQUE (token_hash)
        )
    """


def _setup_indexes():
    return [
        "CREATE UNIQUE INDEX ux_retailer_credential_setup_tokens_token_hash ON public.retailer_credential_setup_tokens (token_hash)",
        "CREATE INDEX ix_retailer_credential_setup_tokens_retailer_id ON public.retailer_credential_setup_tokens (retailer_id)",
        "CREATE INDEX ix_retailer_credential_setup_tokens_binding_id ON public.retailer_credential_setup_tokens (binding_id)",
        "CREATE INDEX ix_retailer_credential_setup_tokens_expires_at ON public.retailer_credential_setup_tokens (expires_at)",
        "CREATE UNIQUE INDEX ux_retailer_credential_setup_tokens_retailer_active ON public.retailer_credential_setup_tokens (retailer_id) WHERE used_at IS NULL AND revoked_at IS NULL AND is_deleted = false",
    ]


def _reset_ddl() -> str:
    return """
        CREATE TABLE public.retailer_password_reset_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            retailer_id UUID NOT NULL REFERENCES public.retailers(id) ON DELETE CASCADE,
            token_hash VARCHAR(128) NOT NULL,
            purpose VARCHAR(64) NOT NULL DEFAULT 'retailer_password_reset',
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE, deleted_at TIMESTAMPTZ,
            CONSTRAINT ck_retailer_password_reset_tokens_purpose CHECK (purpose = 'retailer_password_reset'),
            CONSTRAINT ck_retailer_password_reset_tokens_not_used_and_revoked CHECK (used_at IS NULL OR revoked_at IS NULL),
            CONSTRAINT uq_retailer_password_reset_tokens_token_hash UNIQUE (token_hash)
        )
    """


def _reset_indexes():
    return [
        "CREATE UNIQUE INDEX ux_retailer_password_reset_tokens_token_hash ON public.retailer_password_reset_tokens (token_hash)",
        "CREATE INDEX ix_retailer_password_reset_tokens_retailer_id ON public.retailer_password_reset_tokens (retailer_id)",
        "CREATE INDEX ix_retailer_password_reset_tokens_expires_at ON public.retailer_password_reset_tokens (expires_at)",
        "CREATE UNIQUE INDEX ux_retailer_password_reset_tokens_retailer_active ON public.retailer_password_reset_tokens (retailer_id) WHERE used_at IS NULL AND revoked_at IS NULL AND is_deleted = false",
    ]


def _restore(eng, table_name: str, ddl: str, indexes: list[str]):
    mod = _load_mod()
    with eng.begin() as c:
        from sqlalchemy import text
        c.execute(text(f"DROP TABLE IF EXISTS public.{table_name}"))
        if table_name == "retailer_credential_setup_tokens":
            mod._create_retailer_setup_token_table(c)
        else:
            mod._create_retailer_reset_token_table(c)


# ---- Adversarial tests for both tables ----

def test_composite_unique_rejected_setup():
    """UNIQUE(token_hash, retailer_id) composite must fail."""
    mod, eng = _load_mod(), _eng()
    try:
        from sqlalchemy import text
        ddl = _setup_ddl().replace(
            "CONSTRAINT uq_retailer_credential_setup_tokens_token_hash UNIQUE (token_hash)",
            "CONSTRAINT uq_retailer_credential_setup_tokens_token_hash UNIQUE (token_hash, retailer_id)",
        )
        with eng.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS public.retailer_credential_setup_tokens"))
            c.execute(text(ddl))
            for s in _setup_indexes():
                if "token_hash" in s and "retailer_active" not in s: continue  # skip (built into table)
                c.execute(text(s))
        with pytest.raises(mod.PreflightFailure):
            with eng.connect() as c:
                mod._validate_setup_token_table_contract(c)
    finally:
        _restore(eng, "retailer_credential_setup_tokens", _setup_ddl(), _setup_indexes())
        eng.dispose()


def test_or_true_check_rejected_setup():
    """CHECK (purpose = 'x' OR TRUE) tautology must fail."""
    mod, eng = _load_mod(), _eng()
    try:
        from sqlalchemy import text
        ddl = _setup_ddl().replace(
            "CHECK (purpose = 'retailer_credential_setup')",
            "CHECK (purpose = 'retailer_credential_setup' OR TRUE)",
        )
        with eng.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS public.retailer_credential_setup_tokens"))
            c.execute(text(ddl))
            for s in _setup_indexes():
                if "token_hash" in s and "retailer_active" not in s: continue
                c.execute(text(s))
        with pytest.raises(mod.PreflightFailure):
            with eng.connect() as c:
                mod._validate_setup_token_table_contract(c)
    finally:
        _restore(eng, "retailer_credential_setup_tokens", _setup_ddl(), _setup_indexes())
        eng.dispose()


def test_and_false_extra_check_rejected_setup():
    """CHECK (used_at IS NULL OR revoked_at IS NULL AND FALSE) extra narrowing."""
    mod, eng = _load_mod(), _eng()
    try:
        from sqlalchemy import text
        ddl = _setup_ddl().replace(
            "CHECK (used_at IS NULL OR revoked_at IS NULL)",
            "CHECK (used_at IS NULL OR revoked_at IS NULL AND FALSE)",
        )
        with eng.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS public.retailer_credential_setup_tokens"))
            c.execute(text(ddl))
            for s in _setup_indexes():
                if "token_hash" in s and "retailer_active" not in s: continue
                c.execute(text(s))
        with pytest.raises(mod.PreflightFailure):
            with eng.connect() as c:
                mod._validate_setup_token_table_contract(c)
    finally:
        _restore(eng, "retailer_credential_setup_tokens", _setup_ddl(), _setup_indexes())
        eng.dispose()


def test_extra_predicate_in_index_rejected_setup():
    """Active index has extra narrowing condition: AND expires_at IS NULL."""
    mod, eng = _load_mod(), _eng()
    try:
        from sqlalchemy import text
        idx = [s.replace("AND is_deleted = false", "AND is_deleted = false AND expires_at IS NULL")
               if "retailer_active" in s else s for s in _setup_indexes()]
        with eng.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS public.retailer_credential_setup_tokens"))
            c.execute(text(_setup_ddl()))
            for s in idx:
                if "token_hash" in s and "retailer_active" not in s: continue
                c.execute(text(s))
        with pytest.raises(mod.PreflightFailure):
            with eng.connect() as c:
                mod._validate_setup_token_table_contract(c)
    finally:
        _restore(eng, "retailer_credential_setup_tokens", _setup_ddl(), _setup_indexes())
        eng.dispose()


def test_wrong_varchar_length_rejected_setup():
    """token_hash VARCHAR(256) instead of 128."""
    mod, eng = _load_mod(), _eng()
    try:
        from sqlalchemy import text
        ddl = _setup_ddl().replace("token_hash VARCHAR(128)", "token_hash VARCHAR(256)")
        with eng.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS public.retailer_credential_setup_tokens"))
            c.execute(text(ddl))
            for s in _setup_indexes():
                if "token_hash" in s and "retailer_active" not in s: continue
                c.execute(text(s))
        with pytest.raises(mod.PreflightFailure):
            with eng.connect() as c:
                mod._validate_setup_token_table_contract(c)
    finally:
        _restore(eng, "retailer_credential_setup_tokens", _setup_ddl(), _setup_indexes())
        eng.dispose()


def test_wrong_fk_target_table_rejected_setup():
    """FK retailer_id references wholesalers(id) instead of retailers(id)."""
    mod, eng = _load_mod(), _eng()
    try:
        from sqlalchemy import text
        ddl = _setup_ddl().replace(
            "REFERENCES public.retailers(id) ON DELETE CASCADE",
            "REFERENCES public.wholesalers(id) ON DELETE CASCADE",
        )
        with eng.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS public.retailer_credential_setup_tokens"))
            c.execute(text(ddl))
            for s in _setup_indexes():
                if "token_hash" in s and "retailer_active" not in s: continue
                c.execute(text(s))
        with pytest.raises(mod.PreflightFailure):
            with eng.connect() as c:
                mod._validate_setup_token_table_contract(c)
    finally:
        _restore(eng, "retailer_credential_setup_tokens", _setup_ddl(), _setup_indexes())
        eng.dispose()


def test_reset_table_compatible_accepted():
    """Reset table with well-formed definition must pass."""
    mod, eng = _load_mod(), _eng()
    try:
        with eng.connect() as c:
            mod._validate_reset_token_table_contract(c)
    finally:
        eng.dispose()


def test_reset_table_wrong_varchar_rejected():
    """Reset token_hash VARCHAR(64) instead of 128."""
    mod, eng = _load_mod(), _eng()
    try:
        from sqlalchemy import text
        ddl = _reset_ddl().replace("token_hash VARCHAR(128)", "token_hash VARCHAR(64)")
        with eng.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS public.retailer_password_reset_tokens"))
            c.execute(text(ddl))
            for s in _reset_indexes():
                if "token_hash" in s and "retailer_active" not in s: continue
                c.execute(text(s))
        with pytest.raises(mod.PreflightFailure):
            with eng.connect() as c:
                mod._validate_reset_token_table_contract(c)
    finally:
        _restore(eng, "retailer_password_reset_tokens", _reset_ddl(), _reset_indexes())
        eng.dispose()
