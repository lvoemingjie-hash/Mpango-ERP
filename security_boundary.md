# V3 security boundary record

- Candidate source byte-identical before/during/after runtime: git tree hash
  83eb1b09c6eea7145b3d5069323ee2ffb54cc63d at pre-gate, post-run and delivery; tracked worktree clean.
- No product file modified; no debug endpoint added; launcher/provisioning/env files are task-owned
  and uncommitted.
- Verification/setup tokens obtained ONLY from the task-owned maildir outside the browser; token
  values never appear in any committed evidence file (assertions are behavioral).
- Journey 14 records ONLY the boolean presence of an Authorization header on public calls; header
  values are never captured, printed, or committed.
- Secrets: SECRET_KEY generated per-runtime via secrets.token_urlsafe(32); database credentials are
  throwaway container credentials destroyed with the stack; neither is committed.
