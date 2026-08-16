# DC-12R1-MVP-L1-PW1-R4-B4-V3-E2 — Evidence Encoding and Manifest Closure

**Task**: DC-12R1-MVP-L1-PW1-R4-B4-V3-E2
**Baseline**: `0b6153e547d487294b7289c7b9718edad6882917`
**Kilo STOP**: `8c314cf`
**Status**: CLOSED

## 1. Findings Addressed

Kilo STOP (`8c314cf`) identified two packaging-only issues in the E1 evidence
pack that required no test re-run:

1. **`full_browser_console.txt`** was authored by Playwright as UTF-16 LE with BOM
   and CRLF line endings. On Windows with `core.autocrlf=true`, the index blob
   stored CRLF-converted bytes, producing a different SHA-256 than a clean LF blob.
   This was a Git encoding artefact, not a content change.

2. **`sha256_manifest.txt`** was generated from working-tree (CRLF) bytes rather
   than committed (LF) blob bytes, causing manifest mismatch against the actual
   stored blobs.

## 2. Fix 1 — Console Encoding

| Property | Before | After |
|---|---|---|
| Encoding | UTF-16 LE with BOM | UTF-8, no BOM |
| Line endings | CRLF (\r\n) | LF (\n) |
| Source size | 61,112 bytes | 32,258 bytes |
| Text content | 30,555 chars | 30,555 chars (identical) |

Conversion method: decode UTF-16 (BOM auto-detected), normalize `\r\n` → `\n`,
re-encode UTF-8 without BOM.

**Content identity proof**: after decoding both versions and normalizing line
endings, the text is byte-for-byte identical. No characters were added,
removed, rewritten, or filtered.

**Scans**:
- Mojibake (null bytes, U+FFFD): 0
- Scoped secrets (JWT, Bearer, API key, env secrets): 0

`git diff --check` flags: 4 trailing-whitespace warnings at lines 168, 197,
227, 228 — all in original Playwright test failure descriptions. Not filtered
per E2 scope (no log content modification).

## 3. Fix 2 — Manifest Rebuild

The manifest was rebuilt using a Python script that called `git show :<path>`
(index blob) and `git show HEAD:<path>` (committed blob) for each file, then
computed SHA-256 over the raw blob bytes returned by Git. This guarantees the
hashes match exactly what Git stores, regardless of `core.autocrlf` settings.

Coverage: 18 files (all evidence files excluding the manifest itself).
Ordering: alphabetical by filename (stable sort).

## 4. Non-Actions (Explicit)

- No tests were re-run.
- No JSON, JUnit, CSV, reconciliation, failure_set, or required_greens
  files were modified.
- Product, harness, provisioning evidence, and CLEANUP_CLOSURE.md unchanged.
- 160/2 verdict unchanged.
- Kilo review branch not modified.

## 5. Post-Commit Verification

After committing, a detached HEAD checkout was used to re-read actual committed
file bytes and recompute SHA-256 for every manifest entry. Result:

- missing: 0
- extra: 0
- mismatch: 0

## 6. Quality Gates

- `git diff --check`: only 4 expected trailing-whitespace in console (Playwright
  output, not filtered)
- All evidence text: strict UTF-8
- BOM: none
- Mojibake: 0
- Scoped detect-secrets: 0
- Manifest verified from clean detached checkout
- Product, harness, and protected refs unchanged
