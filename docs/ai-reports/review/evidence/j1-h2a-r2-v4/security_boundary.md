# V4 security boundary record

- Candidate source byte-identical before/during/after: git tree 83eb1b09... at pre-gate,
  post-run and delivery; tracked worktree clean; backend/** and frontend/** untouched;
  .secrets.baseline untouched (scoped detect-secrets ran read-only against it, 0 new hits).
- Harness freeze: spec+config committed before the run; blob IDs recorded; disk==blob
  verified immediately before and after execution; executed in place (no copy/redaction/edit).
- No debug endpoint, no temporary product-source edit, no candidate/config/dependency/lockfile
  or protected-ref change.
- Tokens read only from the task-owned maildir outside the browser; token values never appear
  in committed evidence. Authorization header presence recorded as booleans only (J14).
- SECRET_KEY generated per-runtime (never committed); container credentials destroyed with the
  stack; zero password literals of any kind in the committed harness.
