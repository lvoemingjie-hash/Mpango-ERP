/**
 * Global setup: fail-closed preflight, then public-API provisioning.
 *
 * Any PRECONDITION_FAIL / VOID aborts the whole run before any browser
 * launches (browser launch count stays 0; browser nodes NOT_RUN).
 */
import * as child_process from 'child_process';
import * as path from 'path';
import { runPreflight } from './preflight';
import { provisionAll } from './provision';

export default async function globalSetup(): Promise<void> {
  const repoRoot = path.resolve(__dirname, '..', '..');
  const { outcome, provisioning } = await runPreflight(repoRoot);

  const verdictFile = path.resolve(__dirname, '..', 'results', 'preflight-verdict.json');
  const write = (payload: unknown) => {
    require('fs').writeFileSync(verdictFile, JSON.stringify(payload, null, 2));
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

  await provisionAll();
  write({
    outcome: { kind: 'OK' },
    candidateSha: child_process
      .execSync('git rev-parse HEAD', { cwd: repoRoot })
      .toString()
      .trim(),
    provisionedAt: 'provisioning content is run state, not a node identity',
  });
  void provisioning;
}
