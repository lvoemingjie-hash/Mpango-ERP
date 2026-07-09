"""Platform P24 -- Incident + Runbook Closeout (P24-B backend skeleton).

P24 is the closeout / materialization layer over P15 through P23. It owns the
incident closeout lifecycle and the runbook step model, and it materializes the
two P23 task types P23-C deliberately did not pull -- ``incident_followup_required``
and ``runbook_step_required`` -- from recorded PUSH intake events through the
existing P23 upsert seam.

This package is a NON-EXECUTING, NON-SENDING, IN-MEMORY backend skeleton. The
single invariant, repeated throughout:

    An incident closeout is a view, not an executor. A runbook step is a pointer,
    not an execution. A follow-up task is a record, not a repair.

No closeout transition, no runbook step change, and no task materialization
executes a P22 action, approves a P19/P20/P21 approval, sets or clears the P17
``incident_active`` flag, mutates a registry field, or sends any external message.
P24 mirrors the flag, the tasks, and the execution outcomes; it never changes
them. The flag clears only through P22 ``incident.flag_clear`` under its own
governed envelope. There is no worker, no scheduler, no drain loop, no real
queue, no migration, no frontend, and no auth/RBAC rewrite in P24-B.

P24 is PUSH intake only (the counterpart to P23-C's read-only PULL bridge). It
imports the P23 service seam (to materialize the two task types) and the P10
identity-only guard; it imports no P15 / P17 / P18 / P19 / P20 / P21 / P22 module
-- all flag / execution / approval / source state arrives as redacted, echo-safe
mirrors on recorded intake events. Omitting those read paths is the honest,
safe choice: P24 receives operator / lifecycle judgment, it never reaches into an
execution / approval / flag / registry path.

See docs/ai/PLATFORM_PRODUCT_P24_INCIDENT_RUNBOOK_CLOSEOUT_CONTRACT.md (P24-A).
"""
