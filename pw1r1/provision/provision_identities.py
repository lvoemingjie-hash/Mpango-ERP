#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PW1_R1 Phase 3 — Canonical Identity Provisioning harness (task-private).

Frozen source: d2e7e44cf23e91cabfab545c494abd342fec3062 (unmodified).
Runs against the staging backend (MPANGO_ENV=staging, real JwtAuthStrategy).

Design constraints (documented for the CTO review):
  * dev_sink email tokens live in the issuing process's memory. The staging
    backend's tokens are therefore unreachable over HTTP; the harness drives
    the signup/verify slices through the SAME service functions the HTTP
    endpoints wrap (frozen code, no modification), and reads the raw tokens
    from its own in-process sink. Every consumption step (setup-credential,
    login, select-tenant, /me, invitations, retailer register, retailer
    setup-credential, client login) is executed as a REAL HTTP call against
    the staging backend and asserts the documented status codes.
  * NO direct INSERT of users/roles/permissions; NO hand-written password
    hashes. Passwords are hashed by the product's own hash_password inside
    OwnerCredentialSetupService / RetailerProvisioningService.
  * Identities created fresh; old PW1 test credentials are never reused.
  * Passwords are written ONLY to identities.json (task-private, never in
    reports or git).
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# 0. Environment (must precede any backend import)
# ---------------------------------------------------------------------------
DEPLOY = Path(r"C:\Users\Jeff0\dc12r1_mvp_l1_r0_deploy_1779289316")
BACKEND = DEPLOY / "backend"
sys.path.insert(0, str(BACKEND))

_env = {}
with open(BACKEND / ".env", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            _env[k.strip()] = v.strip()
for k, v in _env.items():
    os.environ.setdefault(k, v)
# Explicit override: staging + real JWT semantics for any service that branches.
os.environ["MPANGO_ENV"] = "staging"
os.environ["PYTHONIOENCODING"] = "utf-8"

WORKSPACE = Path(r"C:\Users\Jeff0\playwright_pw1_r1_2026-08-14")
OUT_IDENTITIES = WORKSPACE / "provision" / "identities.json"
OUT_EVIDENCE = WORKSPACE / "provision" / "provision_evidence.json"

API = "http://127.0.0.1:8000/api/v1"

# ---------------------------------------------------------------------------
# 1. HTTP helper (stdlib only)
# ---------------------------------------------------------------------------

class HttpResult:
    def __init__(self, status: int, body: dict | None):
        self.status = status
        self.body = body or {}

    def __repr__(self) -> str:
        return f"HttpResult(status={self.status})"


def http(method: str, url: str, *, body: dict | None = None, token: str | None = None) -> HttpResult:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return HttpResult(resp.status, json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {}
        return HttpResult(e.code, parsed)


def http_assert(step: str, res: HttpResult, want: int | tuple) -> dict:
    ok = res.status == want if isinstance(want, int) else res.status in want
    record = {"step": step, "status": res.status, "expected": want, "ok": ok}
    if not ok:
        raise RuntimeError(f"{step}: HTTP {res.status} expected {want} body={json.dumps(res.body)[:300]}")
    return record


# ---------------------------------------------------------------------------
# 2. Backend service imports (frozen code)
# ---------------------------------------------------------------------------
from database.session import AsyncSessionLocal
from schemas.auth_signup import SignupRequest
from services.onboarding_service import (
    create_signup_registration,
    verify_email_token,
)
from services.email_delivery import (
    get_dev_email_deliveries,
    get_dev_retailer_email_deliveries,
)
from services.owner_credential_service import OwnerCredentialSetupService
from services.retailer_provisioning_service import RetailerProvisioningService
from db.tenant_filter import set_current_tenant, reset_current_tenant


def _sink_token(kind: str, email: str) -> str:
    if kind == "owner":
        deliveries = get_dev_email_deliveries(email)
        for d in reversed(deliveries):
            if d.purpose == "owner_setup":
                return d.token
    elif kind == "verification":
        deliveries = get_dev_email_deliveries(email)
        for d in reversed(deliveries):
            if d.purpose == "email_verification":
                return d.token
    elif kind == "retailer_setup":
        deliveries = get_dev_retailer_email_deliveries(email)
        if deliveries:
            return deliveries[-1].token
    raise RuntimeError(f"no {kind} token in dev sink for {email}")


# ---------------------------------------------------------------------------
# 3. Provisioning steps
# ---------------------------------------------------------------------------

async def provision_owner(db, *, company_name: str, email: str, password: str) -> dict:
    """Signup -> verify (in-process token handoff) -> HTTP setup-credential.

    Mirrors the HTTP endpoint session lifecycle (get_db commits on success):
    explicit commits after verify and after any service issuance. Rerun-safe:
    if a live registration already exists (e.g. interrupted earlier run), a
    fresh owner setup token is issued via OwnerCredentialSetupService.
    """
    evidence = []
    # 3a. Signup (service slice; same code as POST /auth/signup)
    req = SignupRequest(
        companyName=company_name,
        country="KE",
        email=email,
        password=password,
        phone="+254700000000",
        businessType="wholesale",
    )
    result = await create_signup_registration(db=db, request=req)

    if result.registration_id is not None:
        evidence.append({"step": "signup_create", "registration_id": str(result.registration_id), "ok": True})
        verify_token = _sink_token("verification", email)
        # 3b. Verify email (service slice; same code as POST /auth/verify-email).
        #     Provisions the tenant schema + wholesaler and issues the owner
        #     setup token (recorded into this process's dev sink).
        await verify_email_token(db=db, token=verify_token)
        await db.commit()
        evidence.append({"step": "verify_email_consume", "ok": True})
        setup_token = _sink_token("owner", email)
        registration_id = str(result.registration_id)
    else:
        # Rerun path: existing live registration (already verified+provisioned).
        from models.tenant_onboarding import TenantRegistration
        from sqlalchemy import select
        row = (
            await db.execute(
                select(TenantRegistration)
                .where(TenantRegistration.owner_email == email)
                .where(TenantRegistration.status == "active")
                .execution_options(ignore_tenant=True)
            )
        ).scalar_one_or_none()
        assert row is not None, "rerun recovery: no active registration found"
        registration_id = str(row.id)
        issued = await OwnerCredentialSetupService(db).issue_setup_token(row.id)
        assert issued.action == "issued" and issued.raw_token, "rerun recovery: setup token issue failed"
        await db.commit()
        evidence.append({"step": "signup_reused_existing_registration", "registration_id": registration_id, "ok": True})
        setup_token = issued.raw_token

    # 3c. HTTP setup-credential against the staging backend (real process).
    res = http("POST", f"{API}/auth/onboarding/setup-credential",
               body={"setup_token": setup_token, "password": password})
    evidence.append(http_assert("owner_setup_credential_http", res, 200))
    return {"registration_id": registration_id, "evidence": evidence}


async def login_identity(db, *, email: str, password: str) -> dict:
    res = http("POST", f"{API}/auth/login", body={"email": email, "password": password})
    ev = [http_assert("login", res, 200)]
    data = res.body.get("data", {})
    tenants = data.get("available_tenants", [])
    id_token = data.get("access_token")
    assert id_token, "login returned no access_token"
    assert data.get("token_type") == "bearer", "login token_type != bearer"

    st = http("POST", f"{API}/auth/select-tenant",
              body={"tenant_id": tenants[0]["id"]}, token=id_token)
    ev.append(http_assert("select_tenant", st, 200))
    ctx = st.body.get("data", {})
    ctx_token = ctx.get("access_token")
    assert ctx_token, "select-tenant returned no access_token"
    assert ctx.get("tenant_schema"), "select-tenant returned no tenant_schema"

    me = http("GET", f"{API}/auth/me", token=ctx_token)
    ev.append(http_assert("me", me, 200))
    me_data = me.body.get("data", {})

    return {
        "identity_token": id_token,
        "contextual_token": ctx_token,
        "tenant_id": ctx.get("tenant_id"),
        "tenant_schema": ctx.get("tenant_schema"),
        "roles": me_data.get("roles", []),
        "available_tenants": [{"id": t["id"], "code": t["code"], "name": t["name"]} for t in tenants],
        "evidence": ev,
    }


async def provision_retailer(db, *, admin_token: str, wholesaler_id: str, tenant_schema: str,
                             invitation_code: str, phone: str, name: str, email: str, password: str) -> dict:
    """HTTP register -> in-process token reissue -> HTTP setup-credential."""
    evidence = []
    res = http("POST", f"{API}/retailers/register",
               body={"invitation_code": invitation_code, "phone": phone,
                     "name": name, "email": email, "address": "Nairobi"})
    evidence.append(http_assert("retailer_register_http", res, 201))
    retailer_id = res.body.get("data", {}).get("retailer", {}).get("id")
    assert retailer_id, "register response missing retailer.id"

    # Token handoff: reissue (revokes the backend-issued token; returns raw).
    # The HTTP middleware normally sets the tenant context from the JWT; the
    # harness replicates that for the service calls (same code path).
    svc = RetailerProvisioningService(db)
    ctx = set_current_tenant(tenant_id=str(wholesaler_id), tenant_schema=tenant_schema)
    try:
        if await svc._retailer_has_established_password(retailer_id):
            # Rerun after a successful setup: credential already established.
            evidence.append({"step": "retailer_credential_already_established", "ok": True})
            return {"evidence": evidence, "retailer_id": retailer_id}
        raw = await svc.reissue_setup_token(
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
            issued_by_user_id=retailer_id,
        )
    finally:
        reset_current_tenant(*ctx)
    await db.commit()
    evidence.append({"step": "retailer_setup_token_reissue", "ok": bool(raw)})

    res = http("POST", f"{API}/retailers/setup-credential",
               body={"setup_token": raw, "new_password": password})
    evidence.append(http_assert("retailer_setup_credential_http", res, 200))
    return {"evidence": evidence, "retailer_id": retailer_id}


async def create_invitation(admin_token: str, *, phone: str) -> str:
    res = http("POST", f"{API}/invitations", body={"retailer_phone": phone}, token=admin_token)
    http_assert("invitation_create_http", res, 201)
    code = res.body.get("data", {}).get("code")
    assert code, "invitation response missing code"
    return code


def _gen_password() -> str:
    return "Pw1r1!" + secrets.token_urlsafe(10)


def _load_saved() -> dict:
    """Reuse passwords/phones from a prior partial run (rerun determinism).

    Random per-run phones previously caused a second retailer row for the same
    email (duplicate users_email_key). Saved identities keep reruns stable.
    """
    if OUT_IDENTITIES.exists():
        try:
            return json.loads(OUT_IDENTITIES.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(identities: dict) -> None:
    OUT_IDENTITIES.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_IDENTITIES, "w", encoding="utf-8") as f:
        json.dump(identities, f, indent=2)


async def main() -> None:
    print("== PW1_R1 identity provisioning (staging, real JWT) ==")
    suffix = "r1"  # fixed: reruns reuse the same identities (recovery paths below)
    saved = _load_saved()
    identities = {}
    evidence_all = {"provisioned_at": "2026-08-14", "identity_emails": {}, "steps": []}

    async with AsyncSessionLocal() as db:
        # ---------------- W1: single-tenant wholesaler admin ----------------
        w1_email = f"pw1r1.w1.{suffix}@pw1r1.dev"
        w1_pw = saved.get("w1", {}).get("password") or _gen_password()
        w1 = await provision_owner(db, company_name="PW1R1 W1 Wholesale", email=w1_email, password=w1_pw)
        w1_login = await login_identity(db, email=w1_email, password=w1_pw)
        assert len(w1_login["available_tenants"]) == 1, "W1 must be single-tenant"
        identities["w1"] = {"email": w1_email, "password": w1_pw,
                            "tenant_id": w1_login["tenant_id"],
                            "tenant_schema": w1_login["tenant_schema"],
                            "tenant_code": w1_login["available_tenants"][0]["code"],
                            "token": w1_login["contextual_token"]}
        evidence_all["identity_emails"]["w1"] = w1_email
        evidence_all["steps"] += w1["evidence"] + w1_login["evidence"]
        _save(identities)
        print(f"[w1] tenant={w1_login['available_tenants'][0]['code']} roles={w1_login['roles']}")

        # ---------------- W2: second wholesaler (for multi-tenant + isolation) ----------------
        w2_email = f"pw1r1.w2.{suffix}@pw1r1.dev"
        w2_pw = saved.get("w2", {}).get("password") or _gen_password()
        w2 = await provision_owner(db, company_name="PW1R1 W2 Wholesale", email=w2_email, password=w2_pw)
        w2_login = await login_identity(db, email=w2_email, password=w2_pw)
        assert len(w2_login["available_tenants"]) == 1
        identities["w2"] = {"email": w2_email, "password": w2_pw,
                            "tenant_id": w2_login["tenant_id"],
                            "tenant_schema": w2_login["tenant_schema"],
                            "tenant_code": w2_login["available_tenants"][0]["code"],
                            "token": w2_login["contextual_token"]}
        evidence_all["identity_emails"]["w2"] = w2_email
        evidence_all["steps"] += w2["evidence"] + w2_login["evidence"]
        _save(identities)
        print(f"[w2] tenant={w2_login['available_tenants'][0]['code']} roles={w2_login['roles']}")

        # ---------------- Retailer A: bound to W1 AND W2 (multi-tenant) ----------------
        ra_email = f"pw1r1.ra.{suffix}@pw1r1.dev"
        ra_pw = saved.get("ra", {}).get("password") or _gen_password()
        ra_phone = saved.get("ra", {}).get("phone") or "+25471000001"
        ra_name = "PW1R1 Retailer A"
        inv_a1 = await create_invitation(identities["w1"]["token"], phone=ra_phone)
        ra = await provision_retailer(db, admin_token=identities["w1"]["token"],
                                      wholesaler_id=identities["w1"]["tenant_id"],
                                      tenant_schema=identities["w1"]["tenant_schema"],
                                      invitation_code=inv_a1, phone=ra_phone, name=ra_name,
                                      email=ra_email, password=ra_pw)
        ra_id = ra["retailer_id"]
        evidence_all["steps"] += ra["evidence"]
        # second binding to W2 (multi-tenant identity via formal lifecycle)
        inv_a2 = await create_invitation(identities["w2"]["token"], phone=ra_phone)
        res = http("POST", f"{API}/retailers/register",
                   body={"invitation_code": inv_a2, "phone": ra_phone, "name": ra_name,
                         "email": ra_email, "address": "Nairobi"})
        http_assert("retailer_register_w2_http", res, 201)

        ra_login = await login_identity(db, email=ra_email, password=ra_pw)
        assert len(ra_login["available_tenants"]) == 2, "RA must be multi-tenant"
        identities["ra"] = {"email": ra_email, "password": ra_pw,
                            "phone": ra_phone, "retailer_name": ra_name,
                            "tenant_ids": [t["id"] for t in ra_login["available_tenants"]],
                            "tenant_codes": [t["code"] for t in ra_login["available_tenants"]],
                            "tenant_schema": ra_login["tenant_schema"],
                            "token": ra_login["contextual_token"]}
        evidence_all["identity_emails"]["ra"] = ra_email
        evidence_all["steps"] += ra_login["evidence"]
        _save(identities)
        print(f"[ra] tenants={ra_login['available_tenants']} roles={ra_login['roles']}")

        # ---------------- Retailer B: bound to W1 only ----------------
        rb_email = f"pw1r1.rb.{suffix}@pw1r1.dev"
        rb_pw = saved.get("rb", {}).get("password") or _gen_password()
        rb_phone = saved.get("rb", {}).get("phone") or "+25472000002"
        rb_name = "PW1R1 Retailer B"
        inv_b1 = await create_invitation(identities["w1"]["token"], phone=rb_phone)
        rb = await provision_retailer(db, admin_token=identities["w1"]["token"],
                                      wholesaler_id=identities["w1"]["tenant_id"],
                                      tenant_schema=identities["w1"]["tenant_schema"],
                                      invitation_code=inv_b1, phone=rb_phone, name=rb_name,
                                      email=rb_email, password=rb_pw)
        evidence_all["steps"] += rb["evidence"]
        rb_login = await login_identity(db, email=rb_email, password=rb_pw)
        assert len(rb_login["available_tenants"]) == 1, "RB must be single-tenant"
        identities["rb"] = {"email": rb_email, "password": rb_pw,
                            "phone": rb_phone, "retailer_name": rb_name,
                            "tenant_id": rb_login["tenant_id"],
                            "tenant_code": rb_login["available_tenants"][0]["code"],
                            "token": rb_login["contextual_token"]}
        evidence_all["identity_emails"]["rb"] = rb_email
        evidence_all["steps"] += rb_login["evidence"]
        _save(identities)
        print(f"[rb] tenant={rb_login['available_tenants'][0]['code']} roles={rb_login['roles']}")

        # ---------------- Negative proof: wrong password -> 401 ----------------
        neg = http("POST", f"{API}/auth/login", body={"email": w1_email, "password": "DefinitelyWrong!"})
        http_assert("negative_login_wrong_password_401", neg, 401)
        evidence_all["steps"].append({"step": "negative_login_wrong_password_401", "status": 401, "ok": True})

        # ---------------- Client (retailer portal) login ----------------
        cl = http("POST", f"{API}/client/auth/login",
                  body={"email": ra_email, "password": ra_pw, "wholesaler_code": identities["w1"]["tenant_code"]})
        http_assert("client_login_ra_w1", cl, 200)
        assert cl.body.get("data", {}).get("tokens", {}).get("access_token"), "client login missing token"
        evidence_all["steps"].append({"step": "client_login_ra_w1", "status": 200, "ok": True})

        cl_bad = http("POST", f"{API}/client/auth/login",
                      body={"email": ra_email, "password": "WrongPass!", "wholesaler_code": identities["w1"]["tenant_code"]})
        http_assert("client_login_wrong_password_401", cl_bad, 401)
        evidence_all["steps"].append({"step": "client_login_wrong_password_401", "status": 401, "ok": True})

    # ---------------- Persist (private) ----------------
    _save(identities)
    with open(OUT_EVIDENCE, "w", encoding="utf-8") as f:
        json.dump(evidence_all, f, indent=2, ensure_ascii=False)
    print("== provisioning complete ==")
    print("identities:", {k: v["email"] for k, v in identities.items()})


if __name__ == "__main__":
    asyncio.run(main())
