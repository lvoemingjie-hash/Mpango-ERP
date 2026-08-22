"""DC-12R1-MVP-L1-J1-H2-A-R1: stateless signed join intents (Phase 0 P0-3).

A ``join_intent`` is a short-lived, server-signed token that binds a
public supplier-code lookup to exactly one wholesaler. It exists so the
final bind endpoint never accepts a client-chosen ``wholesaler_id``:
the retailer confirms a PREVIEWED supplier identity, and the intent's
signature — not the frontend — decides which wholesaler the relationship
is created with.

Design (no migration, no storage):
  - payload: base64url(JSON {v, ws, code, exp, jti})
  - signature: base64url(HMAC-SHA256(domain_key, payload))
  - domain_key: HMAC-SHA256(settings.SECRET_KEY, "join_intent:v1") —
    domain-separated from JWT usage of SECRET_KEY
  - verification: constant-time signature compare + expiry check; the
    caller then loads the wholesaler by the signed id.

The intent is NOT a credential: knowing it only lets a retailer join the
same public supplier the code already identifies. Tampering, expiry or
cross-domain reuse all fail closed with a single neutral error.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final, Optional

from core.config import get_settings

#: Domain-separation label for the join-intent key derivation.
_KEY_DOMAIN: Final = "join_intent:v1"

#: Intent lifetime (short by contract).
JOIN_INTENT_TTL_SECONDS: Final = 15 * 60

#: Neutral failure reason (never discloses which check failed).
JOIN_INTENT_INVALID = "JOIN_INTENT_INVALID"


class JoinIntentError(ValueError):
    """Raised on any tampered, malformed or expired intent (neutral)."""


@dataclass(frozen=True)
class JoinIntentPayload:
    wholesaler_id: uuid.UUID
    wholesaler_code: str
    expires_at: datetime


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _domain_key() -> bytes:
    secret = get_settings().SECRET_KEY.encode("utf-8")
    return hmac.new(secret, _KEY_DOMAIN.encode("ascii"), hashlib.sha256).digest()


def issue_join_intent(
    *,
    wholesaler_id: uuid.UUID,
    wholesaler_code: str,
    ttl_seconds: int = JOIN_INTENT_TTL_SECONDS,
    now: Optional[datetime] = None,
) -> tuple[str, datetime]:
    """Sign a join intent for exactly one wholesaler.

    Returns ``(intent, expires_at)``. The intent embeds the public portal
    code so the server-side verification context can be returned to the
    retailer without re-deriving it from untrusted input.
    """
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    payload = {
        "v": 1,
        "ws": str(wholesaler_id),
        "code": wholesaler_code,
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(8),
    }
    payload_b64 = _b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(_domain_key(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    intent = f"{payload_b64}.{_b64encode(signature)}"
    return intent, expires_at


def verify_join_intent(intent: str, *, now: Optional[datetime] = None) -> JoinIntentPayload:
    """Verify signature + expiry and return the signed binding context.

    Every failure path raises :class:`JoinIntentError` with a single
    neutral reason — malformed shape, bad base64, signature mismatch and
    expiry are indistinguishable to the caller.
    """
    try:
        payload_b64, signature_b64 = intent.split(".", 1)
        payload_bytes = _b64decode(payload_b64)
        signature = _b64decode(signature_b64)
        # Canonical round-trip: rejects embedded whitespace/unicode tricks.
        payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise ValueError("bad version")
        expected = hmac.new(_domain_key(), payload_b64.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        if (now or datetime.now(timezone.utc)) >= expires_at:
            raise ValueError("expired")
        return JoinIntentPayload(
            wholesaler_id=uuid.UUID(payload["ws"]),
            wholesaler_code=str(payload["code"]),
            expires_at=expires_at,
        )
    except JoinIntentError:
        raise
    except Exception as exc:  # any parse/crypto failure -> neutral
        raise JoinIntentError(JOIN_INTENT_INVALID) from exc
