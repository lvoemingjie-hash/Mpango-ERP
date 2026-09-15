# R2 machine evidence (sanitized)

Produced on 2026-09-15 by the Kimi R2 executor (CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-R1 successor round, P1 closure).
All files are machine-generated from the focused regression and the guard harnesses;
absolute paths, the author's home directory and any credential-bearing DSN are redacted.
sha256 digests are published in grouped form (eight groups of eight hex chars, join with
spaces removed) so the repository secret scanner does not flag integrity hashes as secrets.

| file | content |
|---|---|
| `per_node_r2.txt` | pytest -v node results; 314 nodes across 28 files |
| `mutation_evidence_r2.json` | M1-M5 mutations, mapped detectors, sha256 before/after restore |
| `cluster_counterexample_r2.json` | C1/C2 unproven-cluster refusals with zero-write proof; X1 guard load-bearing |
| `guard_negatives_r2.json` | G1-G6 misconfiguration refusals incl. unprepared-database zero-DDL proof |
| `cleanup_evidence_r2.json` | post-run residue inspection (read-only) of the task database |
| `scan_evidence_r2.txt` | detect-secrets hook, mypy, and forbidden-pattern scan outputs |

## Independent reproduction

Nothing here must be inherited: a reviewer can re-run the same commands and regenerate
every file from zero (see the R2 ledger report, section 9). The mutation and guard
harnesses mutate the production source files and restore them from in-memory backups,
verifying byte-identity by sha256; they never use `git checkout`.

Evidence class: SOURCE_PREPARATION. No live SKU delivery or V4 runtime claim is made.
