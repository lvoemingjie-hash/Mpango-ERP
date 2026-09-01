/**
 * Global setup: fail-closed mode resolution + invocation accounting, then
 * fail-closed preflight, then SHARED identity provisioning.
 *
 * Only immutable shared identities are created here (tenant A/B owners and
 * sessions, retailer identity/binding/session, local-mail prerequisites).
 * Per-execution catalog resources are created by each test through
 * provisionExecutionResources() in a deterministic namespace.
 *
 * Any PRECONDITION_FAIL / VOID aborts the whole run before any browser
 * launches (browser launch count stays 0; browser nodes NOT_RUN).
 */
import * as fs from 'fs';
import * as path from 'path';
import { runPreflight } from './preflight';
import { provisionShared } from './provision';
import {
  RETRIES,
  WORKERS,
  beginInvocation,
  clearGeneratedRuntimeOutputs,
  requireRuntimeMode,
  writeLiveExecutionContract,
  PREFLIGHT_VERDICT,
} from './runtime';
import { HARNESS_CONFIG } from '../playwright.config';

export default async function globalSetup(): Promise<void> {
  requireRuntimeMode();
  const mode = beginInvocation(HARNESS_CONFIG.candidateSha, WORKERS, RETRIES);
  clearGeneratedRuntimeOutputs();
  writeLiveExecutionContract(mode, HARNESS_CONFIG.candidateSha, WORKERS, RETRIES);

  const repoRoot = path.resolve(__dirname, '..', '..');
  const { outcome } = await runPreflight(repoRoot);

  const write = (payload: unknown) => {
    fs.writeFileSync(PREFLIGHT_VERDICT, JSON.stringify(payload, null, 2));
  };

  if (outcome.kind !== 'OK') {
    write({ outcome });
    if (outcome.kind === 'PRECONDITION_FAIL') {
      throw new Error(
        `PRECONDITION_FAIL (browser nodes NOT_RUN, browser launch count 0): ${outcome.reasons.join('; ')}`,
      );
    }
    throw new Error(
      `VOID (browser nodes NOT_RUN, browser launch count 0): ${outcome.reasons.join('; ')}`,
    );
  }

  const raw = fs.readFileSync(HARNESS_PROVISIONING, 'utf-8');
  await provisionShared(JSON.parse(raw));
  write({
    outcome: { kind: 'OK' },
    sharedIdentitiesOnly: true,
  });
}

const HARNESS_PROVISIONING = path.resolve(__dirname, '..', 'provisioning', 'official.json');
