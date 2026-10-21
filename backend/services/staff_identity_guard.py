"""Small transaction-level credential mutex; no global identity catalogue."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def normalize_staff_email(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('STAFF_EMAIL_INVALID')
    result = value.strip().lower()
    if not result or len(result) > 255 or '@' not in result or any(c.isspace() for c in result):
        raise ValueError('STAFF_EMAIL_INVALID')
    return result


def credential_mutex_key(email: str) -> int:
    digest = hashlib.sha256(b'mpango/staff-credential/v1\0' + normalize_staff_email(email).encode('utf-8')).digest()
    return int.from_bytes(digest[:8], byteorder='big', signed=True)


async def lock_credential_emails(db: AsyncSession, emails: Iterable[str]) -> None:
    """Acquire the complete set before authority/user/token locks; held to commit."""
    keys = sorted({normalize_staff_email(value) for value in emails})
    await db.execute(text("SELECT set_config('lock_timeout','5s',true)"))
    for email in keys:
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': credential_mutex_key(email)})
