# E1 — Evidence Packaging Correction (M1-V1)

Date: 2026-08-21 · Scope: this document + `manifest_sha256.txt` only.

## What was corrected

1. **Removed a stale manifest row.** The prior manifest listed
   `full_browser_console.log` with the SHA-256 of an empty file. That file
   was never committed at evidence commit `ca070667` (the pre-commit
   end-of-file-fixer run had removed it before the commit). The row was
   void and is deleted.
2. **Regenerated the sorted SHA-256 manifest** from the **12 real
   non-manifest blobs as committed at `ca070667`**, recomputed via
   `git cat-file blob` (not working-tree bytes).
3. **Corrected the artifact count: 12 evidence artifacts + 1 manifest**
   (13 files total in this directory after this correction).

## What was NOT changed

- `signup_browser.json`, `signup_browser_junit.xml`, `full_browser.json`,
  `full_browser_junit.xml`, `findings.csv`, `reconciliation.json`,
  `failure_set.json`, both test lists, and the three narrative docs are
  byte-identical to `ca070667` (verified below).

## Disclosure — temporary signup suite and launcher were NOT committed

The Phase-3 signup browser contract (6/6) and the staging backend launcher
were **task-temporary source**: a Playwright spec
(`signup-suite/tests/signup-contract.spec.ts`), a task config, and a
launcher script (`serve_backend.py`) that added a loopback-only
`/__task_mail` route at runtime. They lived in the task runtime directory,
were never committed, and were **deleted in M1-V1 cleanup**. Per the E1
mandate they are neither reconstructed nor claimed to be recovered.

Consequently: the 6/6 signup result stands as **runner evidence** — machine
JSON/JUnit artifacts whose assertions (including the passwordless signup
payload interception) are auditable in `signup_browser.json` /
`signup_browser_junit.xml` — and is **not** an independent
source-authenticity approval of the deleted temporary test code. The
162/162 frozen-harness result remains fully source-authentic: harness
`pw1r4b` is verbatim from git ref `db84b132`.

## Detached verification protocol (see report commit for executed output)

`git ls-tree` + `git cat-file blob` at the corrected commit must yield:
manifest entries = 12, directory non-manifest files = 12,
**missing = 0, extra = 0, hash mismatch = 0**.
