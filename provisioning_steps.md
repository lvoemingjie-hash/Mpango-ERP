# V3 provisioning (API, BEFORE the browser run; hard rule 4)

Per wholesaler (W1, W2):
1. POST /auth/signup {companyName, country: UG, email} -> 202
2. verify-email token read from task maildir -> POST /auth/verify-email -> 200
3. setup-credential token read from task maildir -> POST /auth/onboarding/setup-credential -> 200
4. POST /auth/login -> identity JWT; POST /auth/select-tenant -> contextual JWT
5. Read-only permission check (auth matrix): admin role holds invitations:create and retailers:deactivate.

No retailer identity, invitation, binding, or credential was created by API: every retailer-side
artifact in the evidence was produced through the browser journeys. The single APIRequestContext
use inside the spec is the read-only GET /retailers postcondition of J15.
