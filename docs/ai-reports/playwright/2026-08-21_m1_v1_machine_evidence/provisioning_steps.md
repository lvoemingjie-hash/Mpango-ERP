# M1-V1 Identity Provisioning (formal lifecycles only)

All identities provisioned through supported product APIs; no SQL inserts,
no hand-written hashes. Emails/phones unique per task run.

1. W1 / W2 wholesaler admins (per identity):
   POST /auth/signup (passwordless) -> maildir email_verification token ->
   POST /auth/verify-email -> maildir owner_setup token ->
   POST /auth/onboarding/setup-credential (THE password) ->
   POST /auth/login (200, single tenant) -> POST /auth/select-tenant.
2. RA multi-tenant retailer (canonical display name "PW1R1 Retailer A"):
   W1 invitation (POST /invitations) -> POST /retailers/register ->
   W2 invitation -> POST /retailers/register (same phone+email) ->
   single retailer_credential_setup token consumed once
   (activates both bindings, documented product design).
3. RB single-tenant retailer ("PW1R1 Retailer B"): W1 invitation ->
   register -> setup-credential.
4. Proofs: RA login returns 2 available tenants (W1+W2); RB 1 tenant;
   wrong-password 401 verified.
5. Initial provisioning used non-canonical display names; the phase5
   isolation assertions expect canonical "PW1R1 Retailer A/B", which
   produced the invalidated 159/162 pre-run (see reconciliation.json).
   Re-provisioning with canonical names used the identical formal
   lifecycles. identities.json is task-private (deleted in cleanup).

Signup-contract per-viewport identities (Phase 3) were created inside the
browser run itself: unique email per viewport, full passwordless lifecycle
through the real UI.
