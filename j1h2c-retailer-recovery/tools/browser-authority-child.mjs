#!/usr/bin/env node
/**
 * Fixed browser-authority child process (B1-R6-R3-R1).
 *
 * This is intentionally tiny for the source-level authority gate: the
 * entrypoint proves a REAL child process boundary, exact stdout schema,
 * parent-observed pid/exit matching, and reconciliation truth without running
 * Playwright/product/PG/Redis. A later browser-authorized gate can replace the
 * child implementation behind the same fixed argv-array contract.
 */

import { readSync, writeSync } from 'node:fs';

const INPUT_SCHEMA = 'j1h2c/browser-authority-child-input/1';
const RESULT_SCHEMA = 'j1h2c/browser-authority-child-result/1';
const MAX_STDIN_BYTES = 1048576;

function readStdinText() {
  const chunks = [];
  let total = 0;
  const buffer = Buffer.alloc(65536);
  for (;;) {
    const read = readSync(0, buffer, 0, buffer.length, null);
    if (read <= 0) break;
    chunks.push(buffer.subarray(0, read));
    total += read;
    if (total > MAX_STDIN_BYTES) break;
  }
  return Buffer.concat(chunks, total).toString('utf8');
}

function writeResult(exitCode, complete) {
  writeSync(
    1,
    Buffer.from(
      JSON.stringify({
        schema: RESULT_SCHEMA,
        pid: process.pid,
        exit: exitCode,
        reconciliation: { complete },
      }) + '\n',
      'utf8',
    ),
  );
  process.exit(exitCode);
}

let inputValid = false;
try {
  const input = JSON.parse(readStdinText());
  inputValid =
    input !== null &&
    typeof input === 'object' &&
    !Array.isArray(input) &&
    input.schema === INPUT_SCHEMA &&
    typeof input.input_sha === 'string' &&
    /^[0-9a-f]{64}$/.test(input.input_sha) &&
    typeof input.cwd_sha === 'string' &&
    /^[0-9a-f]{64}$/.test(input.cwd_sha) &&
    input.values !== null &&
    typeof input.values === 'object' &&
    !Array.isArray(input.values);
} catch {
  inputValid = false;
}

writeResult(inputValid ? 0 : 3, inputValid);
