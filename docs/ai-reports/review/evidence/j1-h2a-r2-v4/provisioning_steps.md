# V4 provisioning (API, BEFORE the browser run)

Per wholesaler (W1 = "V4 Supplier W1", W2 = "V4 Supplier W2"):
1. POST /auth/signup {companyName, country: UG, email} -> 202
2. verify-email token from the task-owned maildir -> POST /auth/verify-email -> 200
3. setup-credential token from the task-owned maildir -> POST /auth/onboarding/setup-credential -> 200
4. POST /auth/login -> identity JWT; POST /auth/select-tenant -> contextual JWT
5. Auth matrix read-only check: admin role holds invitations:create and retailers:deactivate.

Retailer passwords for J08/J09/J11/J16/J17 were generated per-runtime (secrets module) and
injected as environment variables (R1_PASSWORD/R2_PASSWORD/R3_PASSWORD); they appear in no
committed file. Every retailer-side artifact was produced through the browser journeys. The
only APIRequestContext uses are the read-only GET /retailers postconditions in J14 and J15.
