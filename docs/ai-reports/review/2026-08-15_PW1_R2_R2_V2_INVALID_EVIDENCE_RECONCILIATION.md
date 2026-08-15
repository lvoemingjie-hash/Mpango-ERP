# INVALID_EVIDENCE_RECONCILIATION — OpenCode V2 Full Browser Report

**Supersedes**: `reports/dc12r1-mvp-l1-pw1-r2-r2-v2-opencode-full-browser-2026-08-15` (ba9da9b)
**Date**: 2026-08-15 (PW1-R3)
**Status**: INVALID_EVIDENCE_RECONCILIATION — superseded; preserved as historical evidence.

## Why the V2 evidence chain is invalid

1. **JUnit contains ZERO failure cases** despite the report claiming 82 failed
   nodes (`evidence/pw1-r2-r2-v2/junit.xml` has no `<failure>` elements at
   all). The claimed node-level outcomes are not backed by the machine-derived
   JUnit accounting.
2. **No raw Playwright JSON** — `results.json` is a hand-built summary
   (verdict/reason/stats), not machine-derived per-node evidence.
3. The "all 82 failures are HTTP 429" attribution is therefore **unproven at
   node level**; the per-spec breakdown (auth-matrix 2 fail, phase1 3 fail,
   phase2 1 fail, ...) cannot be reconciled with the "all 429" claim from the
   committed artifacts.
4. The browser environment was also unsound for the intended comparison: the
   authenticated browser sessions were being rate-limited on the anonymous
   per-IP bucket (limit 100/min) because the middleware order defect
   (PW1-R3 root cause) left every request — authenticated or not — on
   `rate_limit:ip:{ip}`. A full 162-node run under that defect measures the
   defect, not the product.

## Disposition

- The V2 branch and its artifacts remain untouched as historical evidence.
- PW1-R3 closes the underlying product defect (authenticated contextual
  requests now use `rate_limit:tenant:{tenant_id}:{user_id}` limit 1000;
  anonymous/identity-only stay on the IP bucket limit 100; rejected auth is
  rate-limited on the same IP bucket so no unlimited bypass exists).
- Browser acceptance reruns (162/162 with machine-derived JUnit accounting)
  are to be executed by OpenCode after the PW1-R3 Kilo bounded source review.
