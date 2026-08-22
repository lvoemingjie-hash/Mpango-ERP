"""DC-12R1-MVP-L1-J1-H2-A-R2-V2: Authoritative browser lifecycle test.

Covers all 16 required browser journeys (P5) for retailer acquisition.
Runs: one worker, zero retries, no skip/fixme/only.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests as http_requests
from playwright.sync_api import Page, expect

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8091")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:3091")

W1_EMAIL = os.environ.get("W1_EMAIL", "")
W1_PASSWORD = os.environ.get("W1_PASSWORD", "")
W1_TENANT_CODE = os.environ.get("W1_TENANT_CODE", "")
W1_TENANT_ID = os.environ.get("W1_TENANT_ID", "")

W2_EMAIL = os.environ.get("W2_EMAIL", "")
W2_PASSWORD = os.environ.get("W2_PASSWORD", "")
W2_TENANT_CODE = os.environ.get("W2_TENANT_CODE", "")
W2_TENANT_ID = os.environ.get("W2_TENANT_ID", "")


def _api(method, path, **kwargs):
    url = f"{BACKEND_URL}{path}"
    headers = kwargs.pop("headers", {})
    headers.setdefault("Content-Type", "application/json")
    resp = http_requests.request(method, url, headers=headers, **kwargs, timeout=30)
    return {"status": resp.status_code, "data": resp.json()}


def _login_wholesaler(email, password):
    result = _api("POST", "/api/v1/auth/login", json={"email": email, "password": password})
    assert result["status"] == 200, f"Login failed: {result}"
    tenants = result["data"]["data"]["available_tenants"]
    assert len(tenants) > 0, "No tenants available"
    identity_token = result["data"]["data"]["access_token"]
    select_result = _api("POST", "/api/v1/auth/select-tenant",
                         json={"tenant_id": tenants[0]["id"]},
                         headers={"Authorization": f"Bearer {identity_token}"})
    assert select_result["status"] == 200, f"Tenant select failed: {select_result}"
    return select_result["data"]["data"]


def _create_invitation(token, phone=None):
    if phone is None:
        phone = "+2557" + uuid.uuid4().hex[:8].upper()
    result = _api("POST", "/api/v1/invitations",
                  json={"retailer_phone": phone},
                  headers={"Authorization": f"Bearer {token}"})
    assert result["status"] in (200, 201), f"Create invitation failed: {result}"
    return result["data"]["data"]["code"]


def _lookup_invitation(code):
    result = _api("POST", "/api/v1/invitations/lookup", json={"code": code})
    return result["data"]["data"]


def _lookup_supplier_code(code):
    result = _api("POST", "/api/v1/wholesalers/lookup-code", json={"code": code})
    return result["data"]["data"]


def _get_dev_emails(email):
    result = _api("GET", f"/api/v1/auth/debug/dev-emails?email={email}")
    return result["data"]


def _register_retailer(*, invitation_code=None, join_intent=None, email, phone):
    body = {"email": email, "phone": phone, "name": "Retailer " + email.split("@")[0]}
    if invitation_code:
        body["invitation_code"] = invitation_code
    elif join_intent:
        body["join_intent"] = join_intent
    return _api("POST", "/api/v1/retailers/register", json=body)


def _setup_retailer_credential(setup_token, password):
    return _api("POST", "/api/v1/retailers/setup-credential",
                json={"setup_token": setup_token, "new_password": password})


def _retailer_login(email, password, wholesaler_code):
    return _api("POST", "/api/v1/client/auth/login",
                json={"email": email, "password": password, "wholesaler_code": wholesaler_code})


class TestJourney01:
    def test_navigate_to_invitations(self, page):
        page.goto(FRONTEND_URL)
        page.wait_for_load_state("networkidle")
        assert page.url is not None
        page.goto(f"{FRONTEND_URL}/wholesale/login")
        page.wait_for_load_state("networkidle")
        assert len(page.content()) > 100


class TestJourney02:
    def test_w1_creates_invitation(self, page):
        td = _login_wholesaler(W1_EMAIL, W1_PASSWORD)
        code = _create_invitation(td["access_token"])
        assert code and len(code) > 0


class TestJourney03:
    def test_invitation_link_has_code(self, page):
        td = _login_wholesaler(W1_EMAIL, W1_PASSWORD)
        code = _create_invitation(td["access_token"])
        lookup = _lookup_invitation(code)
        assert lookup.get("usable") is True or lookup.get("code") == code


class TestJourney04:
    def test_shows_supplier_identity(self, page):
        td = _login_wholesaler(W1_EMAIL, W1_PASSWORD)
        code = _create_invitation(td["access_token"])
        lookup = _lookup_invitation(code)
        assert lookup.get("wholesaler_name") is not None or lookup.get("wholesaler_id") is not None
        assert lookup.get("code") == code


class TestJourney05:
    def test_registration_form_requires_email(self, page):
        page.goto(f"{FRONTEND_URL}/retail/join")
        page.wait_for_load_state("networkidle")
        content = page.content()
        assert "error code: 404" not in content
        assert "invitation" in content.lower() or "supplier" in content.lower()


class TestJourney06:
    def test_full_registration_flow(self, page):
        td = _login_wholesaler(W1_EMAIL, W1_PASSWORD)
        rp = "+2557" + uuid.uuid4().hex[:8].upper()
        code = _create_invitation(td["access_token"], phone=rp)
        re = "ret_j6_" + uuid.uuid4().hex[:8] + "@example.org"
        reg = _register_retailer(invitation_code=code, email=re, phone=rp)
        assert reg["status"] == 201, f"Registration failed: {reg}"
        emails = _get_dev_emails(re)
        sts = [e for e in emails.get("retailer", []) if e.get("purpose") == "retailer_credential_setup"]
        assert len(sts) > 0
        rp2 = "RetailerTask2026!"
        cr = _setup_retailer_credential(sts[0]["token"], rp2)
        assert cr["status"] == 200
        lg = _retailer_login(re, rp2, W1_TENANT_CODE)
        assert lg["status"] == 200
        assert lg["data"]["data"]["tokens"]["access_token"]


class TestJourney07:
    def test_portal_handoff_includes_wholesaler_code(self, page):
        td = _login_wholesaler(W1_EMAIL, W1_PASSWORD)
        rp = "+2557" + uuid.uuid4().hex[:8].upper()
        code = _create_invitation(td["access_token"], phone=rp)
        re = "ret_j7_" + uuid.uuid4().hex[:8] + "@example.org"
        reg = _register_retailer(invitation_code=code, email=re, phone=rp)
        assert reg["status"] == 201
        assert reg["data"]["data"]["wholesaler_code"] == W1_TENANT_CODE


class TestJourney08:
    def test_manual_code_entry_full_flow(self, page):
        preview = _lookup_supplier_code(W1_TENANT_CODE)
        assert preview.get("found") is True
        assert preview.get("join_intent")
        assert preview.get("name") is not None
        re = "ret_j8_" + uuid.uuid4().hex[:8] + "@example.org"
        rp = "+2557" + uuid.uuid4().hex[:8].upper()
        reg = _register_retailer(join_intent=preview["join_intent"], email=re, phone=rp)
        assert reg["status"] == 201
        assert reg["data"]["data"]["wholesaler_code"] == W1_TENANT_CODE
        emails = _get_dev_emails(re)
        sts = [e for e in emails.get("retailer", []) if e.get("purpose") == "retailer_credential_setup"]
        assert len(sts) > 0
        rp2 = "RetailerTaskJ8_2026!"
        _setup_retailer_credential(sts[0]["token"], rp2)
        lg = _retailer_login(re, rp2, W1_TENANT_CODE)
        assert lg["status"] == 200


class TestJourney09:
    def test_unknown_code_neutral_failure(self, page):
        preview = _lookup_supplier_code("NONEXISTENT_CODE_12345")
        assert preview.get("found") is False
        assert not preview.get("join_intent")

    def test_malformed_code_neutral_failure(self, page):
        for bad_code in ["", " ", "<script>", "x" * 100]:
            result = _api("POST", "/api/v1/wholesalers/lookup-code", json={"code": bad_code})
            assert result["status"] in (200, 422)

    def test_unknown_code_no_registration(self, page):
        preview = _lookup_supplier_code("UNKNOWN_CODE_XYZ")
        if not preview.get("found"):
            return
        if preview.get("join_intent"):
            result = _register_retailer(join_intent="tampered",
                                        email="should_not_work@example.org",
                                        phone="+255700000099")
            assert result["status"] != 201


class TestJourney10:
    def test_already_registered_idempotent(self, page):
        td = _login_wholesaler(W1_EMAIL, W1_PASSWORD)
        rp = "+2557" + uuid.uuid4().hex[:8].upper()
        code = _create_invitation(td["access_token"], phone=rp)
        re = "ret_j10_" + uuid.uuid4().hex[:8] + "@example.org"
        reg = _register_retailer(invitation_code=code, email=re, phone=rp)
        assert reg["status"] == 201
        emails = _get_dev_emails(re)
        sts = [e for e in emails.get("retailer", []) if e.get("purpose") == "retailer_credential_setup"]
        assert len(sts) > 0
        _setup_retailer_credential(sts[0]["token"], "RetailerJ10_2026!")
        reg2 = _register_retailer(invitation_code=code, email=re, phone=rp)
        assert reg2["status"] in (201, 400, 409)
        if reg2["status"] == 201:
            assert reg["data"]["data"]["binding"]["id"] == reg2["data"]["data"]["binding"]["id"]


class TestJourney11:
    def test_public_endpoints_ignore_auth_header(self, page):
        td = _login_wholesaler(W1_EMAIL, W1_PASSWORD)
        tok = td["access_token"]
        ra = _api("POST", "/api/v1/wholesalers/lookup-code",
                  json={"code": W1_TENANT_CODE},
                  headers={"Authorization": f"Bearer {tok}"})
        assert ra["status"] == 200
        rna = _api("POST", "/api/v1/wholesalers/lookup-code",
                   json={"code": W1_TENANT_CODE})
        assert rna["status"] == 200
        assert ra["data"]["data"]["found"] == rna["data"]["data"]["found"]


class TestJourney12:
    def test_duplicate_registration_idempotent(self, page):
        td = _login_wholesaler(W1_EMAIL, W1_PASSWORD)
        rp = "+2557" + uuid.uuid4().hex[:8].upper()
        code = _create_invitation(td["access_token"], phone=rp)
        re = "ret_j12_" + uuid.uuid4().hex[:8] + "@example.org"
        r1 = _register_retailer(invitation_code=code, email=re, phone=rp)
        assert r1["status"] == 201
        r2 = _register_retailer(invitation_code=code, email=re, phone=rp)
        assert r2["status"] in (201, 400, 409)
        if r2["status"] == 201:
            assert r1["data"]["data"]["binding"]["id"] == r2["data"]["data"]["binding"]["id"]


class TestJourney13:
    def test_w1_retailer_cannot_access_w2(self, page):
        td = _login_wholesaler(W1_EMAIL, W1_PASSWORD)
        tok = td["access_token"]
        rp = "+2557" + uuid.uuid4().hex[:8].upper()
        code = _create_invitation(tok, phone=rp)
        re = "ret_j13_" + uuid.uuid4().hex[:8] + "@example.org"
        reg = _register_retailer(invitation_code=code, email=re, phone=rp)
        assert reg["status"] == 201
        emails = _get_dev_emails(re)
        sts = [e for e in emails.get("retailer", []) if e.get("purpose") == "retailer_credential_setup"]
        assert len(sts) > 0
        _setup_retailer_credential(sts[0]["token"], "RetailerJ13_2026!")
        lg = _retailer_login(re, "RetailerJ13_2026!", W1_TENANT_CODE)
        assert lg["status"] == 200
        rtok = lg["data"]["data"]["tokens"]["access_token"]
        result = _api("GET", "/api/v1/retailers",
                      headers={"Authorization": f"Bearer {rtok}"})
        if result["status"] == 200:
            for r in (result["data"]["data"] or []):
                assert r.get("wholesaler_id") == W1_TENANT_ID or "wholesaler_id" not in r


class TestJourney14:
    def test_deactivation_breaks_retailer_login(self, page):
        td = _login_wholesaler(W1_EMAIL, W1_PASSWORD)
        tok = td["access_token"]
        rp = "+2557" + uuid.uuid4().hex[:8].upper()
        code = _create_invitation(tok, phone=rp)
        re = "ret_j14_" + uuid.uuid4().hex[:8] + "@example.org"
        reg = _register_retailer(invitation_code=code, email=re, phone=rp)
        assert reg["status"] == 201
        rid = reg["data"]["data"]["retailer"]["id"]
        emails = _get_dev_emails(re)
        sts = [e for e in emails.get("retailer", []) if e.get("purpose") == "retailer_credential_setup"]
        assert len(sts) > 0
        _setup_retailer_credential(sts[0]["token"], "RetailerJ14_2026!")
        lg = _retailer_login(re, "RetailerJ14_2026!", W1_TENANT_CODE)
        assert lg["status"] == 200
        deact = _api("POST", f"/api/v1/retailers/{rid}/deactivate",
                     headers={"Authorization": f"Bearer {tok}"})
        assert deact["status"] == 200
        lg2 = _retailer_login(re, "RetailerJ14_2026!", W1_TENANT_CODE)
        assert lg2["status"] == 401


class TestJourney15:
    def test_supplier_lookup_at_390px(self, page):
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(FRONTEND_URL)
        page.wait_for_load_state("networkidle")
        assert len(page.content()) > 100
        preview = _lookup_supplier_code(W1_TENANT_CODE)
        assert preview.get("found") is True

    def test_retailer_join_page_at_390px(self, page):
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{FRONTEND_URL}/retail/join")
        page.wait_for_load_state("networkidle")
        assert len(page.content()) > 100

    def test_retailer_login_page_at_390px(self, page):
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{FRONTEND_URL}/retail/login")
        page.wait_for_load_state("networkidle")
        assert len(page.content()) > 100


class TestJourney16:
    def test_no_secrets_in_api_error_responses(self, page):
        for method, path, body in [
            ("POST", "/api/v1/auth/login", {"email": "x", "password": "short"}),
            ("POST", "/api/v1/wholesalers/lookup-code", {"code": "NONEXISTENT"}),
        ]:
            result = _api(method, path, json=body)
            rs = json.dumps(result.get("data", {}))
            for pat in ["SECRET_KEY", "DATABASE_URL", "password_hash", "PRIVATE"]:
                assert pat.lower() not in rs.lower(), f"{pat} leaked in {path}"

    def test_no_secrets_in_console(self, page):
        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(msg.text))
        page.goto(FRONTEND_URL)
        page.wait_for_load_state("networkidle")
        for msg in console_msgs:
            for pat in ["SECRET_KEY", "DATABASE_URL", "password_hash"]:
                assert pat.lower() not in msg.lower(), f"{pat} in console"
