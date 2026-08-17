# Provisioning Steps Status

Provisioned at: 2026-08-17T14:12:54.857509+00:00

Method: official lifecycle (signup -> verify-email -> owner setup-credential -> login -> select-tenant -> invitation -> retailer registration -> retailer credential setup) via ASGITransport against the task backend codebase with staging dev-sink token capture. No SQL writes; no hand-written hashes.

| Step | OK | Detail |
|---|---|---|
| w1:signup_create | YES |  |
| w1:verify_email_consume | YES |  |
| w1:owner_setup_credential_http | YES | {"status": 200, "expected": 200} |
| w1:login | YES | {"status": 200, "expected": 200, "tenants": 1} |
| w1:select_tenant | YES | {"status": 200, "expected": 200} |
| w2:signup_create | YES |  |
| w2:verify_email_consume | YES |  |
| w2:owner_setup_credential_http | YES | {"status": 200, "expected": 200} |
| w2:login | YES | {"status": 200, "expected": 200, "tenants": 1} |
| w2:select_tenant | YES | {"status": 200, "expected": 200} |
| invitation:ra@w1 | YES | {"code_len": 32} |
| invitation:rb@w1 | YES | {"code_len": 32} |
| invitation:ra@w2 | YES | {"code_len": 32} |
| ra:retailer_registration | YES | {"binding_wholesaler": "da085395-a4f7-4dde-83cd-79436a9348cc"} |
| rb:retailer_registration | YES | {"binding_wholesaler": "da085395-a4f7-4dde-83cd-79436a9348cc"} |
| ra:retailer_registration | YES | {"binding_wholesaler": "54fd0048-5b43-48a6-9354-b103e2630e44"} |
| ra:retailer_credential_setup_http | YES | {"status": 200, "expected": 200} |
| rb:retailer_credential_setup_http | YES | {"status": 200, "expected": 200} |

## Post-provision verification (live HTTP)

- RA@W1 login 200; RA@W2 login 200 (multi-tenant)
- RB@W1 login 200; RB@W2 401 (single-tenant isolation)
- Six server-derived client:* permissions incl. client:payments:declare on every retailer login
- GET /api/v1/client/declarations = 200 (no 403)
