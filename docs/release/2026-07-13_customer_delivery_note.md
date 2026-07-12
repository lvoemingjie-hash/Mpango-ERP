# Mpango ERP Customer Delivery Note

| Field | Value |
|---|---|
| Release date | 2026-07-13 |
| Release tag | `release-2026-07-13` |
| Delivery commit | `547b0b294aa387d6179f53eca3ec162532a1e29e` |

## What Is Included

This release delivers the Mpango ERP platform with the following capabilities:

- **Tenant onboarding with email verification**: new tenants sign up, verify
  their email address, and the system automatically provisions their tenant
  schema.
- **Owner credential setup**: after provisioning, the owner receives a setup
  link to set their administrator password and create the first admin RBAC
  role.
- **Forgot / reset password**: self-service password recovery via email. The
  user requests a reset link, receives it by email, and sets a new password
  through the reset page.
- **Login / select tenant**: the user logs in with email + password, then
  selects their tenant to get a tenant-scoped session.
- **SKU catalog / data intake MVP**: import SKU catalog data via the data
  intake flow. This creates catalog records only (see limitations below).
- **Orders / payments MVP**: create orders, confirm them, and process
  structured payments with ledger balancing.
- **Export hardening**: data export endpoints are permission-gated and
  fail-closed on malformed input.
- **Platform / product merged baseline**: the platform operations surface
  (P10-P25) and the product business surface are merged into a single delivery
  baseline.

## Known MVP Limitations

1. **Catalog import is catalog-only**: importing SKU data creates catalog
   records but does NOT create inventory, pricing, barcode lookup, image
   assets, or sellable order readiness. After import, adjust stock and
   retailer prices before creating orders.
2. **JWT browser storage**: authentication tokens are stored in browser
   localStorage. This is accepted for MVP and will be hardened post-delivery.
3. **Non-admin role mapping**: role-based access control is implemented for
   the admin role and MVP-tested paths. Additional role mapping may be needed
   for non-admin users.
4. **Frontend build warnings**: the production build emits non-blocking
   warnings (React act, bundle size). These do not affect functionality.

## Basic User Flows

### New tenant onboarding

1. Sign up at the registration page with company name, email, and password.
2. Check your email for a verification link and click it.
3. After verification, you will receive an owner setup email.
4. Click the setup link and set your administrator password.
5. Log in with your email and password.
6. Select your tenant to access the dashboard.

### Password reset

1. Go to the login page and click "Forgot password".
2. Enter your email address.
3. Check your email for a reset link.
4. Click the reset link and set a new password.
5. Log in with your new password.

## Support and Rollback References

| Reference | Location |
|---|---|
| DC-7 final signoff pack | `ai-ledger/release/2026-07-13_dc7_final_delivery_signoff_pack.md` |
| DC-8 independent signoff | `origin/reports/lubuntu-validation @ 2a860d0` |
| DC-6C backup evidence | 461,831 bytes, SHA256 prefix `3b263368ac08` |
| Rollback runbook | DC-1C pattern: application-version rollback + DB restore from verified backup |
| MVP limitations | `docs/MVP_LIMITATIONS.md` |

## Contact

For support, refer to the rollback runbook and contact the operations team.
Do not attempt manual database changes without explicit approval.
