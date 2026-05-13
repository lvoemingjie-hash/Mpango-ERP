# Platform Track P0 - Information Model Draft

**Date**: 2026-04-07
**Agent**: Platform AI (Vibecoder)
**Branch**: platform-dev
**Track**: Platform P0 - Platform information model draft

---

## Work Completed

1. **Current public schema inventory**: Documented all 7 existing public tables with ownership and purpose
2. **Wholesalers extension proposal**: 6 candidate fields (status, tier, trial_ends_at, suspended_at, suspension_reason, provisioned_at) with category classification
3. **New platform tables proposal**: 2 candidate tables (platform_tenants, platform_audit_logs) with full field definitions
4. **Explicit "must not store here" rules**: Defined for both wholesalers and platform tables
5. **Naming convention**: Proposed `platform_` prefix to distinguish from product (`sys_`) tables
6. **Relationship diagram**: Mapped all public schema table relationships
7. **Implementation recommendation**: Proposed safest first slice (wholesalers extension + platform_tenants creation)
8. **Open questions**: 4 questions for CTO decision

## Files Changed
- docs/arch/platform-information-model-draft.md (new, 200 lines)
- ai-ledger/platform/2026-04-07_p0_information_model_draft.md (this file)

## Scope Respect
- No tenant-schema migrations
- No product table changes (draft only)
- No auth changes
- No billing/subscription implementation
- No speculative microservice split
- No duplication of tenant identity outside wholesalers.id

## Key Design Decisions in Draft
1. `status` on wholesalers is intrinsic (not in separate table)
2. `platform_tenants` is separate because provisioning is async multi-step
3. `platform_audit_logs` is separate from `sys_audit_logs` (different domain)
4. `platform_` prefix convention for clear ownership boundaries

## What Remains Blocked
- Actual implementation of any proposed model changes
- Billing fields (tier, trial_ends_at) pending CTO decision
- Audit log table pending CTO decision
- All subsequent slices pending CTO approval of this draft

## Next Step
Await CTO review of the draft and answers to the 4 open questions.
