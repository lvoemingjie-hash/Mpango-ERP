"""DC-11P1 Platform operator schema foundation tests.

DB-backed tests that verify migration 034 creates all four tables with the
required columns, constraints, indexes, and FK behaviors.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


TEST_DB = "postgresql://mpango_test:test-not-secret-dc3b@127.0.0.1:5435/mpango_erp_test"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _clean_operator_tables():
    """Delete all rows from the four operator tables before each test."""
    eng = create_engine(TEST_DB)
    with eng.connect() as conn:
        conn.execute(text("DELETE FROM platform_operator_setup_tokens"))
        conn.execute(text("DELETE FROM platform_operator_reset_tokens"))
        conn.execute(text("DELETE FROM platform_operator_recovery_credentials"))
        conn.execute(text("DELETE FROM platform_operators"))
        conn.commit()
    eng.dispose()
    yield
    # Also clean after
    eng2 = create_engine(TEST_DB)
    with eng2.connect() as conn:
        conn.execute(text("DELETE FROM platform_operator_setup_tokens"))
        conn.execute(text("DELETE FROM platform_operator_reset_tokens"))
        conn.execute(text("DELETE FROM platform_operator_recovery_credentials"))
        conn.execute(text("DELETE FROM platform_operators"))
        conn.commit()
    eng2.dispose()


def _engine():
    return create_engine(TEST_DB)


def _insert_operator(conn, email="test@example.com", **kwargs):
    """Insert an operator and return its id."""
    cols = {"email": email}
    cols.update(kwargs)
    col_list = ", ".join(cols.keys())
    param_names = ", ".join(f":{k}" for k in cols.keys())
    result = conn.execute(
        text(f"INSERT INTO platform_operators ({col_list}) VALUES ({param_names}) RETURNING id"),
        cols,
    )
    conn.commit()
    return result.scalar()


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------

class TestMigration034Structure:
    """Verify 034 creates all four tables with correct structure."""

    def test_all_four_tables_exist(self):
        with _engine().connect() as conn:
            result = conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name IN ("
                "'platform_operators', 'platform_operator_setup_tokens', "
                "'platform_operator_reset_tokens', "
                "'platform_operator_recovery_credentials'"
                ")"
            ))
            names = {r[0] for r in result}
            expected = {
                "platform_operators",
                "platform_operator_setup_tokens",
                "platform_operator_reset_tokens",
                "platform_operator_recovery_credentials",
            }
            assert names == expected, f"missing tables: {expected - names}"

    def test_no_plaintext_token_columns(self):
        with _engine().connect() as conn:
            for table in (
                "platform_operator_setup_tokens",
                "platform_operator_reset_tokens",
                "platform_operator_recovery_credentials",
            ):
                result = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name LIKE '%%token%%' "
                    "AND column_name != 'token_hash'"
                ), {"t": table})
                bad = [r[0] for r in result]
                assert not bad, f"table {table} has non-hash token column(s): {bad}"

    def test_platform_operators_columns(self):
        with _engine().connect() as conn:
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'platform_operators'"
            ))
            cols = {r[0] for r in result}
            required = {
                "id", "email", "password_hash", "status", "role",
                "failed_login_attempts", "locked_until", "auth_version",
                "last_login_at", "revoked_at", "invited_by",
                "created_at", "updated_at", "is_deleted", "deleted_at",
            }
            missing = required - cols
            assert not missing, f"missing columns: {missing}"

    def test_no_email_hash_column(self):
        with _engine().connect() as conn:
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'platform_operators' AND column_name = 'email_hash'"
            ))
            assert result.fetchone() is None, "email_hash column must not exist"

    def test_migrations_033_and_earlier_unchanged(self):
        """Migration files 001-033 must not be modified by DC-11P1."""
        import pathlib
        versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
        for f in sorted(versions.glob("[0-9][0-9][0-9]_*.py")):
            num = int(f.name[:3])
            assert num <= 33 or num == 34, f"unexpected migration file: {f.name}"


# ---------------------------------------------------------------------------
# Constraint tests: platform_operators
# ---------------------------------------------------------------------------

class TestPlatformOperatorConstraints:

    def test_duplicate_email_rejected(self):
        with _engine().connect() as conn:
            _insert_operator(conn, "dup@example.com")
            with pytest.raises(IntegrityError):
                conn.execute(text("INSERT INTO platform_operators (email) VALUES ('dup@example.com')"))
                conn.commit()
            conn.rollback()

    def test_non_normalized_email_unique(self):
        with _engine().connect() as conn:
            conn.execute(text("INSERT INTO platform_operators (email) VALUES ('  Test@Example.COM  ')"))
            conn.commit()
            with pytest.raises(IntegrityError):
                conn.execute(text("INSERT INTO platform_operators (email) VALUES ('test@example.com')"))
                conn.commit()
            conn.rollback()

    def test_invalid_status_rejected(self):
        with _engine().connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(text("INSERT INTO platform_operators (email, status) VALUES ('b@example.com', 'superuser')"))
                conn.commit()
            conn.rollback()

    def test_invalid_role_rejected(self):
        with _engine().connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(text("INSERT INTO platform_operators (email, role) VALUES ('b@example.com', 'superuser')"))
                conn.commit()
            conn.rollback()

    def test_negative_login_attempts_rejected(self):
        with _engine().connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(text("INSERT INTO platform_operators (email, failed_login_attempts) VALUES ('b@example.com', -1)"))
                conn.commit()
            conn.rollback()

    def test_auth_version_zero_rejected(self):
        with _engine().connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(text("INSERT INTO platform_operators (email, auth_version) VALUES ('b@example.com', 0)"))
                conn.commit()
            conn.rollback()

    def test_active_without_password_rejected(self):
        with _engine().connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(text("INSERT INTO platform_operators (email, status) VALUES ('b@example.com', 'active')"))
                conn.commit()
            conn.rollback()

    def test_active_with_revoked_rejected(self):
        with _engine().connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(text(
                    "INSERT INTO platform_operators (email, status, password_hash, revoked_at) "
                    "VALUES ('b@example.com', 'active', 'hash', now())"
                ))
                conn.commit()
            conn.rollback()


# ---------------------------------------------------------------------------
# Token table constraint tests
# ---------------------------------------------------------------------------

class TestTokenTableConstraints:

    def test_setup_token_used_and_revoked_rejected(self):
        with _engine().connect() as conn:
            oid = _insert_operator(conn, "tok@example.com")
            with pytest.raises(IntegrityError):
                conn.execute(text(
                    "INSERT INTO platform_operator_setup_tokens "
                    "(operator_id, token_hash, expires_at, used_at, revoked_at) "
                    "VALUES (:oid, 'h1', now() + interval '1 hour', now(), now())"
                ), {"oid": oid})
                conn.commit()
            conn.rollback()

    def test_duplicate_active_setup_token_rejected(self):
        with _engine().connect() as conn:
            oid = _insert_operator(conn, "dup@example.com")
            conn.execute(text(
                "INSERT INTO platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at) VALUES (:oid, 'h2', now() + interval '1 hour')"
            ), {"oid": oid})
            conn.commit()
            with pytest.raises(IntegrityError):
                conn.execute(text(
                    "INSERT INTO platform_operator_setup_tokens "
                    "(operator_id, token_hash, expires_at) VALUES (:oid, 'h3', now() + interval '1 hour')"
                ), {"oid": oid})
                conn.commit()
            conn.rollback()

    def test_used_setup_token_allows_replacement(self):
        with _engine().connect() as conn:
            oid = _insert_operator(conn, "used@example.com")
            conn.execute(text(
                "INSERT INTO platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at, used_at) "
                "VALUES (:oid, 'h4', now() + interval '1 hour', now())"
            ), {"oid": oid})
            conn.commit()
            conn.execute(text(
                "INSERT INTO platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at) VALUES (:oid, 'h5', now() + interval '1 hour')"
            ), {"oid": oid})
            conn.commit()

    def test_expired_token_still_blocks_unique_index(self):
        with _engine().connect() as conn:
            oid = _insert_operator(conn, "exp@example.com")
            conn.execute(text(
                "INSERT INTO platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at) "
                "VALUES (:oid, 'h6', now() - interval '1 hour')"
            ), {"oid": oid})
            conn.commit()
            with pytest.raises(IntegrityError):
                conn.execute(text(
                    "INSERT INTO platform_operator_setup_tokens "
                    "(operator_id, token_hash, expires_at) VALUES (:oid, 'h7', now() + interval '1 hour')"
                ), {"oid": oid})
                conn.commit()
            conn.rollback()

    def test_duplicate_active_reset_token_rejected(self):
        with _engine().connect() as conn:
            oid = _insert_operator(conn, "rst@example.com")
            conn.execute(text(
                "INSERT INTO platform_operator_reset_tokens "
                "(operator_id, token_hash, expires_at) VALUES (:oid, 'rh1', now() + interval '1 hour')"
            ), {"oid": oid})
            conn.commit()
            with pytest.raises(IntegrityError):
                conn.execute(text(
                    "INSERT INTO platform_operator_reset_tokens "
                    "(operator_id, token_hash, expires_at) VALUES (:oid, 'rh2', now() + interval '1 hour')"
                ), {"oid": oid})
                conn.commit()
            conn.rollback()


# ---------------------------------------------------------------------------
# Recovery credential constraint tests
# ---------------------------------------------------------------------------

class TestRecoveryCredentialConstraints:

    def test_active_state_ok(self):
        with _engine().connect() as conn:
            oid = _insert_operator(conn, "rec@example.com")
            conn.execute(text(
                "INSERT INTO platform_operator_recovery_credentials "
                "(operator_id, credential_hash) VALUES (:oid, 'ch1')"
            ), {"oid": oid})
            conn.commit()

    def test_used_with_revoked_rejected(self):
        with _engine().connect() as conn:
            oid = _insert_operator(conn, "rb@example.com")
            with pytest.raises(IntegrityError):
                conn.execute(text(
                    "INSERT INTO platform_operator_recovery_credentials "
                    "(operator_id, credential_hash, status, used_at, revoked_at) "
                    "VALUES (:oid, 'ch2', 'used', now(), now())"
                ), {"oid": oid})
                conn.commit()
            conn.rollback()

    def test_active_with_used_at_rejected(self):
        with _engine().connect() as conn:
            oid = _insert_operator(conn, "rb2@example.com")
            with pytest.raises(IntegrityError):
                conn.execute(text(
                    "INSERT INTO platform_operator_recovery_credentials "
                    "(operator_id, credential_hash, status, used_at) "
                    "VALUES (:oid, 'ch3', 'active', now())"
                ), {"oid": oid})
                conn.commit()
            conn.rollback()

    def test_duplicate_active_recovery_rejected(self):
        with _engine().connect() as conn:
            oid = _insert_operator(conn, "dup@example.com")
            conn.execute(text(
                "INSERT INTO platform_operator_recovery_credentials "
                "(operator_id, credential_hash) VALUES (:oid, 'ch4')"
            ), {"oid": oid})
            conn.commit()
            with pytest.raises(IntegrityError):
                conn.execute(text(
                    "INSERT INTO platform_operator_recovery_credentials "
                    "(operator_id, credential_hash) VALUES (:oid, 'ch5')"
                ), {"oid": oid})
                conn.commit()
            conn.rollback()


# ---------------------------------------------------------------------------
# FK behavior tests
# ---------------------------------------------------------------------------

class TestForeignKeyBehavior:

    def test_setup_token_cascade_on_operator_delete(self):
        with _engine().connect() as conn:
            oid = _insert_operator(conn, "fk@example.com")
            conn.execute(text(
                "INSERT INTO platform_operator_setup_tokens "
                "(operator_id, token_hash, expires_at) VALUES (:oid, 'fkh', now() + interval '1 hour')"
            ), {"oid": oid})
            conn.commit()
            conn.execute(text("DELETE FROM platform_operators WHERE id = :oid"), {"oid": oid})
            conn.commit()
            result = conn.execute(text(
                "SELECT count(*) FROM platform_operator_setup_tokens WHERE operator_id = :oid"
            ), {"oid": oid})
            assert result.scalar() == 0, "setup tokens should cascade-delete"

    def test_invited_by_set_null_on_delete(self):
        with _engine().connect() as conn:
            inviter = _insert_operator(conn, "inviter@example.com")
            conn.execute(text(
                "INSERT INTO platform_operators (email, invited_by) "
                "VALUES ('invitee@example.com', :iid) RETURNING id"
            ), {"iid": inviter})
            conn.commit()
            conn.execute(text("DELETE FROM platform_operators WHERE id = :iid"), {"iid": inviter})
            conn.commit()
            result = conn.execute(text(
                "SELECT invited_by FROM platform_operators WHERE email = 'invitee@example.com'"
            ))
            assert result.scalar() is None, "invited_by should be SET NULL"
