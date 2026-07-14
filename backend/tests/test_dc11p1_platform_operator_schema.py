"""DC-11P1-R1 Platform operator schema foundation tests.

R1 corrections:
- Portable DB gate (no hardcoded URL/credential).
- All queries filter table_schema='public'.
- Email normalization CHECK tested.
- ORM/catalog index parity test.
- Strengthened security column tests.
- Migration-history static checks (not byte-integrity).
"""
from __future__ import annotations

import os
import re

import pytest
from sqlalchemy import create_engine, text, Index
from sqlalchemy.exc import IntegrityError

# -- Portable DB gate --

_PROD_DB_NAMES = {"mpango_erp", "mpango", "mpango_prod"}


def _get_test_db_url():
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        return None
    # normalize to sync psycopg2 driver
    url = url.replace("+asyncpg", "")
    # refuse production names
    for name in _PROD_DB_NAMES:
        if f"/{name}" in url and "test" not in url.lower():
            pytest.fail(f"refusing to run against non-disposable DB: name contains '{name}'")
    return url


TEST_DB = _get_test_db_url()
SKIP_REASON = (
    "set TEST_DATABASE_URL or DATABASE_URL to a disposable PostgreSQL to run "
    "DC-11P1 schema tests"
)


pytestmark = pytest.mark.skipif(not TEST_DB, reason=SKIP_REASON)


@pytest.fixture(autouse=True)
def _clean_operator_tables():
    eng = create_engine(TEST_DB)
    with eng.connect() as conn:
        for t in [
            "platform_operator_setup_tokens",
            "platform_operator_reset_tokens",
            "platform_operator_recovery_credentials",
            "platform_operators",
        ]:
            conn.execute(text(f'DELETE FROM public."{t}"'))
        conn.commit()
    eng.dispose()
    yield
    eng2 = create_engine(TEST_DB)
    with eng2.connect() as conn:
        for t in [
            "platform_operator_setup_tokens",
            "platform_operator_reset_tokens",
            "platform_operator_recovery_credentials",
            "platform_operators",
        ]:
            conn.execute(text(f'DELETE FROM public."{t}"'))
        conn.commit()
    eng2.dispose()


def _engine():
    return create_engine(TEST_DB)


def _insert_operator(conn, email="test@example.com", **kw):
    cols = {"email": email}
    cols.update(kw)
    cl = ", ".join(cols.keys())
    pn = ", ".join(f":{k}" for k in cols.keys())
    r = conn.execute(text(
        f'INSERT INTO public.platform_operators ({cl}) VALUES ({pn}) RETURNING id'
    ), cols)
    conn.commit()
    return r.scalar()


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------

class TestMigrationStructure:

    def test_all_four_tables_in_public_schema(self):
        with _engine().connect() as c:
            r = c.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name IN ("
                "'platform_operators','platform_operator_setup_tokens',"
                "'platform_operator_reset_tokens',"
                "'platform_operator_recovery_credentials')"
            ))
            names = {row[0] for row in r}
            assert names == {
                "platform_operators",
                "platform_operator_setup_tokens",
                "platform_operator_reset_tokens",
                "platform_operator_recovery_credentials",
            }

    def test_no_operator_tables_in_tenant_schemas(self):
        with _engine().connect() as c:
            r = c.execute(text(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_name LIKE 'platform_operator%%' "
                "AND table_schema != 'public'"
            ))
            rows = list(r)
            assert rows == [], f"operator tables must not exist outside public: {rows}"

    def test_no_email_hash_column(self):
        with _engine().connect() as c:
            r = c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='platform_operators' "
                "AND column_name='email_hash'"
            ))
            assert r.fetchone() is None

    def test_platform_operators_has_all_columns(self):
        required = {
            "id", "email", "password_hash", "status", "role",
            "failed_login_attempts", "locked_until", "auth_version",
            "last_login_at", "revoked_at", "invited_by",
            "created_at", "updated_at", "is_deleted", "deleted_at",
        }
        with _engine().connect() as c:
            r = c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='platform_operators'"
            ))
            cols = {row[0] for row in r}
            assert required <= cols, f"missing: {required - cols}"

    def test_migration_revision_and_down_revision(self):
        import pathlib, ast
        f = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "034_platform_operators.py"
        source = f.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assigns = {n.targets[0].id: n.value.value for n in tree.body
                   if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                   and isinstance(n.value, ast.Constant)}
        assert assigns.get("revision") == "034_platform_operators"
        assert assigns.get("down_revision") == "033_order_status_enum_reconciliation"

    def test_migration_imports_no_runtime_models(self):
        import pathlib
        f = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "034_platform_operators.py"
        source = f.read_text(encoding="utf-8")
        assert "from models" not in source, "migration must not import runtime models"
        assert "from services" not in source, "migration must not import services"
        assert "from api" not in source, "migration must not import api"


# ---------------------------------------------------------------------------
# Email normalization CHECK
# ---------------------------------------------------------------------------

class TestEmailNormalization:

    def test_mixed_case_email_rejected(self):
        with _engine().connect() as c:
            with pytest.raises(IntegrityError):
                c.execute(text("INSERT INTO public.platform_operators (email) VALUES ('Mixed@Case.COM')"))
                c.commit()
            c.rollback()

    def test_surrounding_whitespace_rejected(self):
        with _engine().connect() as c:
            with pytest.raises(IntegrityError):
                c.execute(text("INSERT INTO public.platform_operators (email) VALUES ('  sp@example.com  ')"))
                c.commit()
            c.rollback()

    def test_empty_email_rejected(self):
        with _engine().connect() as c:
            with pytest.raises(IntegrityError):
                c.execute(text("INSERT INTO public.platform_operators (email) VALUES ('')"))
                c.commit()
            c.rollback()

    def test_whitespace_only_email_rejected(self):
        with _engine().connect() as c:
            with pytest.raises(IntegrityError):
                c.execute(text("INSERT INTO public.platform_operators (email) VALUES ('   ')"))
                c.commit()
            c.rollback()

    def test_normalized_email_accepted(self):
        with _engine().connect() as c:
            _insert_operator(c, "good@example.com")

    def test_duplicate_normalized_email_rejected(self):
        with _engine().connect() as c:
            _insert_operator(c, "dup@example.com")
            with pytest.raises(IntegrityError):
                c.execute(text("INSERT INTO public.platform_operators (email) VALUES ('dup@example.com')"))
                c.commit()
            c.rollback()


# ---------------------------------------------------------------------------
# Constraint tests
# ---------------------------------------------------------------------------

class TestOperatorConstraints:

    def test_invalid_status_rejected(self):
        with _engine().connect() as c:
            with pytest.raises(IntegrityError):
                c.execute(text("INSERT INTO public.platform_operators (email, status) VALUES ('b@example.com', 'bad')"))
                c.commit()
            c.rollback()

    def test_invalid_role_rejected(self):
        with _engine().connect() as c:
            with pytest.raises(IntegrityError):
                c.execute(text("INSERT INTO public.platform_operators (email, role) VALUES ('b@example.com', 'bad')"))
                c.commit()
            c.rollback()

    def test_negative_attempts_rejected(self):
        with _engine().connect() as c:
            with pytest.raises(IntegrityError):
                c.execute(text("INSERT INTO public.platform_operators (email, failed_login_attempts) VALUES ('b@example.com', -1)"))
                c.commit()
            c.rollback()

    def test_auth_version_zero_rejected(self):
        with _engine().connect() as c:
            with pytest.raises(IntegrityError):
                c.execute(text("INSERT INTO public.platform_operators (email, auth_version) VALUES ('b@example.com', 0)"))
                c.commit()
            c.rollback()

    def test_active_without_password_rejected(self):
        with _engine().connect() as c:
            with pytest.raises(IntegrityError):
                c.execute(text("INSERT INTO public.platform_operators (email, status) VALUES ('b@example.com', 'active')"))
                c.commit()
            c.rollback()

    def test_active_with_revoked_rejected(self):
        with _engine().connect() as c:
            with pytest.raises(IntegrityError):
                c.execute(text(
                    "INSERT INTO public.platform_operators (email, status, password_hash, revoked_at) "
                    "VALUES ('b@example.com', 'active', 'h', now())"
                ))
                c.commit()
            c.rollback()


# ---------------------------------------------------------------------------
# Token table constraints
# ---------------------------------------------------------------------------

class TestTokenConstraints:

    def test_setup_used_and_revoked_rejected(self):
        with _engine().connect() as c:
            oid = _insert_operator(c, "t1@example.com")
            with pytest.raises(IntegrityError):
                c.execute(text(
                    "INSERT INTO public.platform_operator_setup_tokens "
                    "(operator_id, token_hash, expires_at, used_at, revoked_at) "
                    "VALUES (:o, 'h1', now() + interval '1 hour', now(), now())"
                ), {"o": oid})
                c.commit()
            c.rollback()

    def test_duplicate_active_setup_rejected(self):
        with _engine().connect() as c:
            oid = _insert_operator(c, "t2@example.com")
            c.execute(text(
                "INSERT INTO public.platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at) VALUES (:o, 'h2', now() + interval '1 hour')"
            ), {"o": oid})
            c.commit()
            with pytest.raises(IntegrityError):
                c.execute(text(
                    "INSERT INTO public.platform_operator_setup_tokens "
                    "(operator_id, token_hash, expires_at) VALUES (:o, 'h3', now() + interval '1 hour')"
                ), {"o": oid})
                c.commit()
            c.rollback()

    def test_used_setup_allows_replacement(self):
        with _engine().connect() as c:
            oid = _insert_operator(c, "t3@example.com")
            c.execute(text(
                "INSERT INTO public.platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at, used_at) "
                "VALUES (:o, 'h4', now() + interval '1 hour', now())"
            ), {"o": oid})
            c.commit()
            c.execute(text(
                "INSERT INTO public.platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at) VALUES (:o, 'h5', now() + interval '1 hour')"
            ), {"o": oid})
            c.commit()

    def test_expired_setup_still_blocks_index(self):
        with _engine().connect() as c:
            oid = _insert_operator(c, "t4@example.com")
            c.execute(text(
                "INSERT INTO public.platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at) "
                "VALUES (:o, 'h6', now() - interval '1 hour')"
            ), {"o": oid})
            c.commit()
            with pytest.raises(IntegrityError):
                c.execute(text(
                    "INSERT INTO public.platform_operator_setup_tokens "
                    "(operator_id, token_hash, expires_at) VALUES (:o, 'h7', now() + interval '1 hour')"
                ), {"o": oid})
                c.commit()
            c.rollback()

    def test_duplicate_active_reset_rejected(self):
        with _engine().connect() as c:
            oid = _insert_operator(c, "t5@example.com")
            c.execute(text(
                "INSERT INTO public.platform_operator_reset_tokens "
                "(operator_id, token_hash, expires_at) VALUES (:o, 'rh1', now() + interval '1 hour')"
            ), {"o": oid})
            c.commit()
            with pytest.raises(IntegrityError):
                c.execute(text(
                    "INSERT INTO public.platform_operator_reset_tokens "
                    "(operator_id, token_hash, expires_at) VALUES (:o, 'rh2', now() + interval '1 hour')"
                ), {"o": oid})
                c.commit()
            c.rollback()

    def test_token_hash_globally_unique_within_table(self):
        """token_hash is unique within each token table."""
        with _engine().connect() as c:
            o1 = _insert_operator(c, "u1@example.com")
            o2 = _insert_operator(c, "u2@example.com")
            c.execute(text(
                "INSERT INTO public.platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at) VALUES (:o, 'shared_h', now() + interval '1 hour')"
            ), {"o": o1})
            c.commit()
            with pytest.raises(IntegrityError):
                c.execute(text(
                    "INSERT INTO public.platform_operator_setup_tokens "
                    "(operator_id, token_hash, expires_at) VALUES (:o, 'shared_h', now() + interval '1 hour')"
                ), {"o": o2})
                c.commit()
            c.rollback()


# ---------------------------------------------------------------------------
# Recovery credential constraints
# ---------------------------------------------------------------------------

class TestRecoveryConstraints:

    def test_active_ok(self):
        with _engine().connect() as c:
            oid = _insert_operator(c, "r1@example.com")
            c.execute(text(
                "INSERT INTO public.platform_operator_recovery_credentials "
                "(operator_id, credential_hash) VALUES (:o, 'ch1')"
            ), {"o": oid})
            c.commit()

    def test_used_with_revoked_rejected(self):
        with _engine().connect() as c:
            oid = _insert_operator(c, "r2@example.com")
            with pytest.raises(IntegrityError):
                c.execute(text(
                    "INSERT INTO public.platform_operator_recovery_credentials "
                    "(operator_id, credential_hash, status, used_at, revoked_at) "
                    "VALUES (:o, 'ch2', 'used', now(), now())"
                ), {"o": oid})
                c.commit()
            c.rollback()

    def test_active_with_used_at_rejected(self):
        with _engine().connect() as c:
            oid = _insert_operator(c, "r3@example.com")
            with pytest.raises(IntegrityError):
                c.execute(text(
                    "INSERT INTO public.platform_operator_recovery_credentials "
                    "(operator_id, credential_hash, status, used_at) "
                    "VALUES (:o, 'ch3', 'active', now())"
                ), {"o": oid})
                c.commit()
            c.rollback()

    def test_duplicate_active_recovery_rejected(self):
        with _engine().connect() as c:
            oid = _insert_operator(c, "r4@example.com")
            c.execute(text(
                "INSERT INTO public.platform_operator_recovery_credentials "
                "(operator_id, credential_hash) VALUES (:o, 'ch4')"
            ), {"o": oid})
            c.commit()
            with pytest.raises(IntegrityError):
                c.execute(text(
                    "INSERT INTO public.platform_operator_recovery_credentials "
                    "(operator_id, credential_hash) VALUES (:o, 'ch5')"
                ), {"o": oid})
                c.commit()
            c.rollback()

    def test_credential_hash_globally_unique(self):
        with _engine().connect() as c:
            o1 = _insert_operator(c, "r5@example.com")
            o2 = _insert_operator(c, "r6@example.com")
            c.execute(text(
                "INSERT INTO public.platform_operator_recovery_credentials "
                "(operator_id, credential_hash) VALUES (:o, 'dup_hash')"
            ), {"o": o1})
            c.commit()
            with pytest.raises(IntegrityError):
                c.execute(text(
                    "INSERT INTO public.platform_operator_recovery_credentials "
                    "(operator_id, credential_hash) VALUES (:o, 'dup_hash')"
                ), {"o": o2})
                c.commit()
            c.rollback()


# ---------------------------------------------------------------------------
# FK behavior
# ---------------------------------------------------------------------------

class TestForeignKeyBehavior:

    def test_setup_cascade_on_delete(self):
        with _engine().connect() as c:
            oid = _insert_operator(c, "fk1@example.com")
            c.execute(text(
                "INSERT INTO public.platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at) VALUES (:o, 'fh', now() + interval '1 hour')"
            ), {"o": oid})
            c.commit()
            c.execute(text("DELETE FROM public.platform_operators WHERE id = :o"), {"o": oid})
            c.commit()
            r = c.execute(text(
                "SELECT count(*) FROM public.platform_operator_setup_tokens WHERE operator_id = :o"
            ), {"o": oid})
            assert r.scalar() == 0

    def test_invited_by_set_null(self):
        with _engine().connect() as c:
            inv = _insert_operator(c, "inv@example.com")
            c.execute(text(
                "INSERT INTO public.platform_operators (email, invited_by) "
                "VALUES ('ite@example.com', :i)"
            ), {"i": inv})
            c.commit()
            c.execute(text("DELETE FROM public.platform_operators WHERE id = :i"), {"i": inv})
            c.commit()
            r = c.execute(text(
                "SELECT invited_by FROM public.platform_operators WHERE email = 'ite@example.com'"
            ))
            assert r.scalar() is None


# ---------------------------------------------------------------------------
# Security column tests
# ---------------------------------------------------------------------------

class TestSecurityColumns:

    FORBIDDEN_TOKEN_COLS = {"token", "raw_token", "plaintext", "secret", "token_value"}
    FORBIDDEN_RECOVERY_COLS = {"credential", "raw_credential", "plaintext", "secret", "credential_value"}

    def test_setup_tokens_no_plaintext_cols(self):
        with _engine().connect() as c:
            r = c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='platform_operator_setup_tokens'"
            ))
            cols = {row[0] for row in r}
            bad = self.FORBIDDEN_TOKEN_COLS & cols
            assert not bad, f"forbidden columns: {bad}"
            assert "token_hash" in cols

    def test_reset_tokens_no_plaintext_cols(self):
        with _engine().connect() as c:
            r = c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='platform_operator_reset_tokens'"
            ))
            cols = {row[0] for row in r}
            bad = self.FORBIDDEN_TOKEN_COLS & cols
            assert not bad, f"forbidden columns: {bad}"
            assert "token_hash" in cols

    def test_recovery_no_plaintext_cols(self):
        with _engine().connect() as c:
            r = c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='platform_operator_recovery_credentials'"
            ))
            cols = {row[0] for row in r}
            bad = self.FORBIDDEN_RECOVERY_COLS & cols
            assert not bad, f"forbidden columns: {bad}"
            assert "credential_hash" in cols


# ---------------------------------------------------------------------------
# ORM/catalog index parity
# ---------------------------------------------------------------------------

class TestORMCatalogParity:

    EXPECTED_INDEXES = {
        "platform_operator_setup_tokens": {"ux_setup_tokens_operator_active"},
        "platform_operator_reset_tokens": {"ux_reset_tokens_operator_active"},
        "platform_operator_recovery_credentials": {"ux_recovery_credentials_operator_active"},
    }

    def test_partial_unique_indexes_exist_in_catalog(self):
        with _engine().connect() as c:
            for table, expected_indexes in self.EXPECTED_INDEXES.items():
                r = c.execute(text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = :t"
                ), {"t": table})
                actual = {row[0] for row in r}
                missing = expected_indexes - actual
                assert not missing, f"missing indexes on {table}: {missing}"

    def test_orm_declares_matching_indexes(self):
        from models.platform_operator import (
            PlatformOperatorSetupToken,
            PlatformOperatorResetToken,
            PlatformOperatorRecoveryCredential,
        )
        for model, expected in [
            (PlatformOperatorSetupToken, "ux_setup_tokens_operator_active"),
            (PlatformOperatorResetToken, "ux_reset_tokens_operator_active"),
            (PlatformOperatorRecoveryCredential, "ux_recovery_credentials_operator_active"),
        ]:
            index_names = {idx.name for idx in model.__table_args__ if hasattr(idx, "name") and isinstance(idx, Index)}
            assert expected in index_names, f"ORM {model.__name__} missing index {expected}"
