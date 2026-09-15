# R3 machine evidence (sanitized) — with run-from-repo generators

Produced on 2026-09-15 by the Kimi R3 executor
(CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-R3-TLS-EVIDENCE-TRUTH-2026-09-15).

| file | content |
|---|---|
| `per_node_r3.txt` | per-node nodeids regenerated from junit XML (333 nodes, verbatim parameters) |
| `nodeid_reconciliation_r3.json` | collect set == result set proof (333 == 333, equal=True) with both set sha256s |
| `mutation_evidence_r3.json` | 8 mutations (M1-M5 retained, M6-M8 the three TLS-guard layers) with detectors and restore sha256 |
| `guard_negatives_r3.json` | G1-G6 misconfiguration refusals incl. unprepared-database zero-direct-DDL proof |
| `cluster_identity_counterexample_r3.json` | C1/C2 unproven-cluster refusals with zero-write proof; X1 guard load-bearing proof |
| `cleanup_evidence_r3.json` | post-run residue inspection (read-only) of the task database |
| `scan_evidence_r3.txt` | detect-secrets hook, mypy, git diff --check, UTF-8/LF and forbidden-pattern outputs |
| `focused_files_r3.txt` | the exact 28-file focused list (no placeholder) |
| `generators/` | run-from-repo generators (env-parameterized); see README |

## Rebuildability (corrects the R2 bundle README claim)

The R2 bundle's README claimed every file could be regenerated from the repository.
That claim was untrue: the R2 generators were task-local and uncommitted. It is
retracted here (see the R3 errata ledger). For R3 this is fixed by publishing the
generators under `generators/` and verifying them by running the *published* copies
from this repository against the task database:

```bash
export KIMI_SMTP_BACKEND_DIR=<checkout>/backend
export KIMI_SMTP_EVIDENCE_DIR=<output dir>
export KIMI_SMTP_TASK_DATABASE_URL=... KIMI_SMTP_TASK_CLUSTER_ID=...
export TEST_DATABASE_URL=... REPORTING_USER_PASSWORD=...
python generators/nodeid_reconciliation.py   # needs focused_files_r3.txt in the output dir
python generators/mutation_harness.py        # mutates sources, restores from memory
python generators/guard_negatives.py
python generators/cluster_identity_counterexample.py
python generators/cleanup_evidence.py        # writes JSON to stdout
```

What cannot be rebuilt from the repository alone: the task database contents and the
cluster (they are environment inputs, identified by KIMI_SMTP_TASK_DATABASE_URL and
the cluster system_identifier), and the live V4 runtime (never claimed here).

Integrity digests are published in grouped form (eight groups of eight hex chars;
join with spaces removed). Nothing is allowlisted and `.secrets.baseline` is unchanged.

Evidence class: SOURCE_PREPARATION. FULL_SUITE_RESULT=NOT_RUN,
LIVE_RUNTIME_RESULT=NOT_RUN, FORMAL_SKU_IMPORT_INVOCATIONS=0.
