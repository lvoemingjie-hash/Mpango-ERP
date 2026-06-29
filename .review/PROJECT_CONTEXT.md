# Mpango Platform Review Bus Context

This directory defines the file-based Review Bus pilot for the Mpango ERP SaaS
platform track.

## Roles

- Codex CTO: defines objectives, scope, forbidden changes, validation gates,
  stop conditions, final review, and merge decisions.
- Claude Worker: implements approved tasks in isolated branches/worktrees and
  writes structured completion reports.
- Goose Middleman: dispatches task packets, records status, and writes audit
  logs. Goose is not a reviewer, not a gatekeeper, and not a merger.

## Authority Rules

1. Codex is the only final gate.
2. Goose must not change product or platform runtime code.
3. Goose must not merge, push `platform-dev`, write approval markers, or decide
   that a task is accepted.
4. Goose may only write under `.review/outbox`, `.review/inbox`,
   `.review/audit`, and `.review/state` during the shadow pilot.
5. Any stop condition, unclear state, command failure, or worker scope drift must
   be recorded in the audit log and escalated to Codex/user.

## Current Pilot

P21-D0 is a shadow pilot. It tests whether Goose can read a structured task,
produce a Claude handoff packet, and write an audit log without doing real
dispatch, code changes, merge, push, or final approval.
