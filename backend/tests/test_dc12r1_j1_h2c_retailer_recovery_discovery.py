"""DC-12R1-MVP-L1-J1-H2-C-R1: retailer recovery discovery backend contract.

Proves the H2-C backend half against the REAL test database:

  HC11  the retailer reset email link carries the public portal code in the
        FRAGMENT: /retailer/reset-password#resetToken=<SECRET>&w=<CODE>
        (resetToken stays fragment-only; no query string anywhere).
  HC17  the w code in the email is the CANONICAL wholesaler code from the
        matched DB row — a lowercase caller input still matches (the DB
        predicate is lower(w.code) = lower(:code)) but the email NEVER
        echoes the caller's raw casing.
  LEGACY build_retailer_reset_link keeps its exact pre-H2-C shape when no
        code is provided, so previously issued links remain valid.

Mutation anchors (each must go RED when the implementation regresses):
  M4  dropping w from the email link -> HC11/HC17 assertions fail.
  M5  echoing the caller's raw lowercase code -> HC17 assertion fails.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from services.email_delivery import (
    clear_dev_email_deliveries,
    get_dev_retailer_email_deliveries,
)
from services.onboarding_service import build_retailer_reset_link
from services.retailer_provisioning_service import RetailerProvisioningService

# Reuse the S1 lifecycle helpers so the fixture table cleanup patterns match
# the existing S1 suite (codes prefixed S1T% are cleaned by the fixture).
from tests.test_dc12r1_s1_retailer_identity import (  # noqa: F401
    _create_invitation,
    _make_tenant,
    s1_db,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Unit contract: build_retailer_reset_link shapes (legacy + H2-C)
# ---------------------------------------------------------------------------

async def test_reset_link_legacy_shape_unchanged_without_code():
    """No wholesaler_code -> EXACT legacy shape (M4 anchor: old links valid)."""
    token = "raw-reset-token-1"
    link = build_retailer_reset_link(token)
    assert link == f"/retailer/reset-password#resetToken=raw-reset-token-1"
    assert "?" not in link
    assert "w=" not in link


async def test_reset_link_with_canonical_code_keeps_fragment_only():
    """HC11: w joins resetToken in the FRAGMENT; never a query param."""
    link = build_retailer_reset_link("tok 1", wholesaler_code="H2CAB01")
    # The token is url-encoded inside the fragment; the public code follows.
    assert link.startswith("/retailer/reset-password#resetToken=")
    assert link.endswith("&w=H2CAB01")
    assert "?" not in link
    head, fragment = link.split("#", 1)
    assert head == "/retailer/reset-password"
    assert fragment.startswith("resetToken=tok%201&")


# ---------------------------------------------------------------------------
# Integration contract: the email carries the DB-canonical code (HC11/HC17)
# ---------------------------------------------------------------------------

async def _established_retailer(db, *, code: str) -> tuple[str, str, str]:
    """Official lifecycle: tenant -> invitation -> register -> setup password.

    Returns (email, wholesaler_id, canonical_code).
    """
    ws_id, _schema = await _make_tenant(db, code=code)
    phone = "+15552901"
    email = f"h2c-{uuid.uuid4().hex[:8]}@example.com"
    invitation = await _create_invitation(db, wholesaler_id=ws_id, phone=phone)
    svc = RetailerProvisioningService(db)
    await svc.register_with_invitation(invitation_code=invitation, phone=phone, email=email)
    await db.commit()
    await svc.consume_setup_token(get_dev_retailer_email_deliveries(email)[0].token, "OldPass1!")
    await db.commit()
    canonical = (
        await db.execute(text("SELECT code FROM public.wholesalers WHERE id = :i"), {"i": ws_id})
    ).scalar_one()
    return email, ws_id, canonical


async def test_forgot_password_email_carries_db_canonical_uppercase_code(s1_db):
    """HC17 + M5 anchor: lowercase caller input -> email w is the CANONICAL
    DB code (uppercase), never the caller's raw casing. M4 anchor: w must be
    present at all."""
    email, ws_id, canonical = await _established_retailer(
        s1_db, code=f"S1T{uuid.uuid4().hex[:5].upper()}"
    )
    assert canonical == canonical.upper()

    clear_dev_email_deliveries()
    svc = RetailerProvisioningService(s1_db)
    issued = await svc.request_password_reset(
        email=email, wholesaler_code=canonical.lower()
    )
    await s1_db.commit()
    assert issued is True

    deliveries = get_dev_retailer_email_deliveries(email)
    assert len(deliveries) == 1
    link = deliveries[0].link
    # HC11: fragment-only shape with the secret first, then the public code.
    assert link.startswith("/retailer/reset-password#resetToken=")
    assert f"&w={canonical}" in link
    assert "?" not in link
    # HC17 / M5: the email never echoes the caller's lowercase input.
    assert f"&w={canonical.lower()}" not in link
    # The secret token itself must not leak into a query string.
    assert "resetToken" not in link.split("#", 1)[0]


async def test_forgot_password_email_w_matches_case_insensitive_lookup(s1_db):
    """The case-insensitive DB match still finds the retailer for a mixed-case
    caller code, and the delivered link w equals the canonical code exactly."""
    email, ws_id, canonical = await _established_retailer(
        s1_db, code=f"S1T{uuid.uuid4().hex[:5].upper()}"
    )
    clear_dev_email_deliveries()
    svc = RetailerProvisioningService(s1_db)
    mixed = canonical[0] + canonical[1:].lower()
    issued = await svc.request_password_reset(email=email, wholesaler_code=mixed)
    await s1_db.commit()
    assert issued is True
    link = get_dev_retailer_email_deliveries(email)[0].link
    assert f"&w={canonical}" in link
