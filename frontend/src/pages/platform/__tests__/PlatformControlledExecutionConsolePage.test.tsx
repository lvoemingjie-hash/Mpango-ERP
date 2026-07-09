/**
 * P22-C: Controlled Execution Console page component tests.
 *
 * Verifies the non-executing operator-console contract:
 *   - the catalog renders exactly seven allowlisted actions
 *   - excluded actions are visible but never selectable
 *   - a passed dry-run unlocks the record section; a blocked dry-run does not
 *   - recording requires the typed acknowledgement
 *   - a recorded request shows dry_run_passed + executed=false
 *   - the idempotency digest is shown but the raw key is never echoed back
 *   - list / read works; API errors surface as non-crashing operator feedback
 *   - no button or label commands execution; no product/payment business wording
 */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock api to prevent real network calls (both get and post are exercised).
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

import { api } from '@/services/api';
import { PlatformControlledExecutionConsolePage } from '@/pages/platform/PlatformControlledExecutionConsolePage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/platform/controlled-execution']}>
      <Routes>
        <Route
          path="/platform/controlled-execution"
          element={<PlatformControlledExecutionConsolePage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

// Realistic catalog fixture (matches backend build_catalog): 7 allowlisted
// actions + the explicit exclusion list.
const CATALOG = {
  items: [
    { action_type: 'support_mode.on', action_class: 'write', executor: 'super_admin (identity-only)', reversible: true, reversibility_via: 'support_mode.off', tenant_business_mutation: 'none' },
    { action_type: 'support_mode.off', action_class: 'write', executor: 'super_admin (identity-only)', reversible: true, reversibility_via: 'support_mode.on', tenant_business_mutation: 'none' },
    { action_type: 'incident.flag_set', action_class: 'write', executor: 'super_admin (identity-only)', reversible: true, reversibility_via: 'incident.flag_clear', tenant_business_mutation: 'none' },
    { action_type: 'incident.flag_clear', action_class: 'write', executor: 'super_admin (identity-only)', reversible: true, reversibility_via: 'incident.flag_set', tenant_business_mutation: 'none' },
    { action_type: 'provisioning.recheck', action_class: 'read', executor: 'super_admin (identity-only)', reversible: false, reversibility_via: null, tenant_business_mutation: 'none' },
    { action_type: 'backup.check', action_class: 'read', executor: 'super_admin (identity-only)', reversible: false, reversibility_via: null, tenant_business_mutation: 'none' },
    { action_type: 'backup.restore_test_request', action_class: 'write_request', executor: 'super_admin (identity-only)', reversible: false, reversibility_via: null, tenant_business_mutation: 'none' },
  ],
  exclusions: [
    { action_type: 'tenant.pause', reason: 'destructive lifecycle (blocks tenant logins / writes); excluded from v0.' },
    { action_type: 'tenant.resume', reason: 'destructive lifecycle (moves tenant out of paused / suspended); excluded from v0.' },
    { action_type: 'lifecycle.transition', reason: 'generic destructive lifecycle transition; excluded from v0.' },
    { action_type: 'real restore', reason: 'restoring real tenant data; only backup.restore_test_request (test-only) is allowlisted.' },
    { action_type: 'schema migration', reason: 'any DDL / alembic / schema change; excluded from v0 forever.' },
    { action_type: 'data deletion', reason: 'any deletion of tenant or platform records; excluded from v0 forever.' },
    { action_type: 'payment / billing', reason: 'any payment, billing, invoice, or financial-record action; excluded from v0.' },
    { action_type: 'tenant business records', reason: 'any read / write of orders, payments, invoices, customers, inventory, ledgers.' },
    { action_type: 'arbitrary shell / SQL / script', reason: 'no general code-execution surface exists or is introduced in any P22 phase.' },
  ],
  total: 7,
  contract: 'P22-A',
  storage: 'memory',
  executed: false,
};

function dryRunResponse(over: Record<string, unknown> = {}) {
  return {
    data: {
      dry_run_id: 'dry-1',
      durable_approval_id: 'appr-1',
      action_type: 'backup.check',
      tenant_id: null,
      requested_state: null,
      executable: true,
      verdict: 'passed',
      block_reasons: [],
      expected_audit_shape: { execution_dry_run_passed: ['event_id'] },
      execution_mode: 'sync',
      source_status: 'known',
      reversible: false,
      redaction_applied: true,
      idempotency_key_digest: 'digest-abc',
      storage: 'memory',
      executed: false,
      execution_started: false,
      execution_allowed: false,
      created_at: '2026-07-02T00:00:00Z',
      ...over,
    },
  };
}

function recordResponse(over: Record<string, unknown> = {}) {
  return {
    data: {
      execution_request_id: 'req-1',
      durable_approval_id: 'appr-1',
      action_type: 'backup.check',
      tenant_id: null,
      requested_state: null,
      reason_redacted: 'routine review',
      idempotency_key_digest: 'digest-abc',
      payload_digest: 'payload-def',
      actor_id: 'actor-1',
      actor_role: 'super_admin',
      identity_context: 'identity_only',
      execution_mode: 'sync',
      dry_run_ref: 'dry-1',
      execution_ack: true,
      correlation_id: null,
      metadata_redacted: null,
      redaction_applied: true,
      result_state: 'dry_run_passed',
      block_reasons: [],
      result: 'recorded',
      message: 'Recorded: the request was recorded at dry_run_passed and was NOT executed.',
      storage: 'memory',
      executed: false,
      execution_started: false,
      execution_allowed: false,
      created_at: '2026-07-02T00:00:00Z',
      updated_at: '2026-07-02T00:00:00Z',
      ...over,
    },
  };
}

const RAW_KEY = 'RAW-SECRET-KEY-XYZ';

function fillDryRunForm() {
  fireEvent.change(screen.getByTestId('p22-approval-input'), { target: { value: 'appr-1' } });
  fireEvent.change(screen.getByTestId('p22-reason-input'), { target: { value: 'routine review' } });
  fireEvent.change(screen.getByTestId('p22-idempotency-input'), { target: { value: RAW_KEY } });
}

async function passDryRun() {
  await screen.findAllByTestId('p22-catalog-item');
  fillDryRunForm();
  vi.mocked(api.post).mockResolvedValueOnce(dryRunResponse());
  fireEvent.click(screen.getByTestId('p22-dry-run-btn'));
  expect(await screen.findByTestId('p22-record-section')).toBeInTheDocument();
}

/** Pass a dry-run, then check the acknowledgement so the record button is enabled. */
async function passDryRunAndAck() {
  await passDryRun();
  fireEvent.click(screen.getByTestId('p22-ack-input'));
  expect(screen.getByTestId('p22-record-btn')).not.toBeDisabled();
}

/**
 * Assert the record section has disappeared after a payload edit: the record
 * section is gone, the disabled placeholder is shown (a fresh dry-run is
 * required), and the acknowledgement was cleared with it.
 */
function expectRecordUnavailableAfterEdit() {
  expect(screen.queryByTestId('p22-record-section')).not.toBeInTheDocument();
  expect(screen.queryByTestId('p22-record-btn')).not.toBeInTheDocument();
  expect(screen.queryByTestId('p22-ack-input')).not.toBeInTheDocument();
  expect(screen.getByTestId('p22-record-disabled')).toBeInTheDocument();
}

describe('PlatformControlledExecutionConsolePage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({ data: CATALOG });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
  });

  it('P22-P01: catalog loads and shows exactly seven allowlisted actions', async () => {
    renderPage();
    const items = await screen.findAllByTestId('p22-catalog-item');
    expect(items).toHaveLength(7);
    expect(screen.getByTestId('p22-catalog-summary').textContent).toContain('7 allowlisted actions');
    // All seven action types render.
    for (const at of CATALOG.items.map((i) => i.action_type)) {
      expect(screen.getAllByText(at).length).toBeGreaterThan(0);
    }
  });

  it('P22-P02: excluded actions are visible and cannot be selected as executable options', async () => {
    renderPage();
    await screen.findAllByTestId('p22-catalog-item');
    // Excluded actions are visible in the separated area.
    const excluded = screen.getAllByTestId('p22-excluded-item');
    expect(excluded.length).toBeGreaterThan(0);
    expect(screen.getByText('tenant.pause')).toBeInTheDocument();
    // The action select only contains the seven allowlisted actions.
    const select = screen.getByTestId('p22-action-select') as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((o) => o.value);
    expect(optionValues).toEqual(CATALOG.items.map((i) => i.action_type));
    // No excluded action is selectable.
    for (const ex of ['tenant.pause', 'tenant.resume', 'lifecycle.transition']) {
      expect(optionValues).not.toContain(ex);
    }
  });

  it('P22-P03: a passed dry-run enables the record request section', async () => {
    renderPage();
    await passDryRun();
    // Record section is present; the record button exists but requires the ack.
    expect(screen.getByTestId('p22-record-btn')).toBeDisabled();
    // Check the acknowledgement -> the record button becomes enabled.
    fireEvent.click(screen.getByTestId('p22-ack-input'));
    expect(screen.getByTestId('p22-record-btn')).not.toBeDisabled();
  });

  it('P22-P04: a blocked dry-run shows block reasons and keeps recording unavailable', async () => {
    renderPage();
    await screen.findAllByTestId('p22-catalog-item');
    fillDryRunForm();
    vi.mocked(api.post).mockResolvedValueOnce(
      dryRunResponse({
        dry_run_id: null,
        executable: false,
        verdict: 'blocked',
        block_reasons: ['approval_not_found', 'source_unknown_for_write'],
        source_status: 'unknown',
      }),
    );
    fireEvent.click(screen.getByTestId('p22-dry-run-btn'));
    // Block reasons render.
    const reasons = await screen.findByTestId('p22-block-reasons');
    expect(reasons.textContent).toContain('approval_not_found');
    expect(reasons.textContent).toContain('source_unknown_for_write');
    // The record section is NOT shown; the disabled placeholder is.
    expect(screen.queryByTestId('p22-record-section')).not.toBeInTheDocument();
    expect(screen.getByTestId('p22-record-disabled')).toBeInTheDocument();
  });

  it('P22-P05: missing/invalid required fields keep the dry-run disabled and show validation', async () => {
    renderPage();
    await screen.findAllByTestId('p22-catalog-item');
    // Disabled before the required fields are filled.
    expect(screen.getByTestId('p22-dry-run-btn')).toBeDisabled();
    expect(screen.getByTestId('p22-form-hint')).toBeInTheDocument();
    // Fill the required fields.
    fillDryRunForm();
    expect(screen.getByTestId('p22-dry-run-btn')).not.toBeDisabled();
    // Invalid metadata re-disables the button and shows a message.
    fireEvent.change(screen.getByTestId('p22-metadata-input'), { target: { value: '{not json' } });
    expect(screen.getByTestId('p22-dry-run-btn')).toBeDisabled();
    expect(screen.getByTestId('p22-metadata-error')).toBeInTheDocument();
    // Clearing metadata re-enables.
    fireEvent.change(screen.getByTestId('p22-metadata-input'), { target: { value: '' } });
    expect(screen.getByTestId('p22-dry-run-btn')).not.toBeDisabled();
  });

  it('P22-P06: recording requires the explicit acknowledgement', async () => {
    renderPage();
    await passDryRun();
    // Without ack the record button is disabled.
    expect(screen.getByTestId('p22-record-btn')).toBeDisabled();
    expect(screen.getByTestId('p22-record-hint')).toBeInTheDocument();
    // The acknowledgement is required text is present.
    expect(screen.getByTestId('p22-ack-label').textContent?.toLowerCase()).toContain('acknowledge');
    // Checking it enables the button.
    fireEvent.click(screen.getByTestId('p22-ack-input'));
    expect(screen.getByTestId('p22-record-btn')).not.toBeDisabled();
  });

  it('P22-P07: record success shows dry_run_passed and executed=false', async () => {
    renderPage();
    await passDryRun();
    fireEvent.click(screen.getByTestId('p22-ack-input'));
    vi.mocked(api.post).mockResolvedValueOnce(recordResponse());
    fireEvent.click(screen.getByTestId('p22-record-btn'));
    const result = await screen.findByTestId('p22-record-result');
    expect(within(result).getByTestId('p22-result-state').textContent).toContain('dry_run_passed');
    expect(within(result).getByTestId('p22-not-executed').textContent).toContain('executed=false');
    expect(within(result).getByTestId('p22-result-badge').textContent).toContain('recorded');
  });

  it('P22-P08: the idempotency digest is shown but the raw key is not echoed after response', async () => {
    renderPage();
    await passDryRun();
    fireEvent.click(screen.getByTestId('p22-ack-input'));
    vi.mocked(api.post).mockResolvedValueOnce(recordResponse());
    fireEvent.click(screen.getByTestId('p22-record-btn'));
    const result = await screen.findByTestId('p22-record-result');
    // The digest is displayed.
    expect(within(result).getByTestId('p22-idempotency-digest').textContent).toContain('digest-abc');
    // The raw key is NOT echoed in the response panel.
    expect(within(result).queryByText(RAW_KEY)).not.toBeInTheDocument();
    expect(result.textContent).not.toContain(RAW_KEY);
  });

  it('P22-P09: list and read recorded requests work', async () => {
    renderPage();
    await screen.findAllByTestId('p22-catalog-item');
    // List / queue.
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        items: [recordResponse().data],
        total: 1,
        limit: 50,
        offset: 0,
        storage: 'memory',
        executed: false,
      },
    });
    fireEvent.click(screen.getByTestId('p22-refresh-queue-btn'));
    expect(await screen.findByTestId('p22-queue-item')).toBeInTheDocument();
    expect(screen.getByTestId('p22-queue-summary').textContent).toContain('1 recorded requests');
    expect(screen.getByTestId('p22-queue-item').textContent).toContain('backup.check');
    expect(screen.getByTestId('p22-queue-item').textContent).toContain('executed=false');

    // Read one by id.
    vi.mocked(api.get).mockResolvedValueOnce(recordResponse());
    fireEvent.change(screen.getByTestId('p22-read-input'), { target: { value: 'req-1' } });
    fireEvent.click(screen.getByTestId('p22-read-btn'));
    expect(await screen.findByTestId('p22-read-result')).toBeInTheDocument();
    expect(screen.getByTestId('p22-read-result').textContent).toContain('backup.check');
  });

  it('P22-P10: API errors show non-crashing operator feedback', async () => {
    renderPage();
    await screen.findAllByTestId('p22-catalog-item');
    fillDryRunForm();
    vi.mocked(api.post).mockRejectedValueOnce(new Error('network down'));
    fireEvent.click(screen.getByTestId('p22-dry-run-btn'));
    const err = await screen.findByTestId('p22-error');
    expect(err.textContent).toContain('network down');
    // The page did not crash; the dry-run form is still present.
    expect(screen.getByTestId('p22-dry-run-form')).toBeInTheDocument();
  });

  it('P22-P11: no button or label says "Execute" as an action command', async () => {
    renderPage();
    await screen.findAllByTestId('p22-catalog-item');
    // No button's command verb is "execute" (bare "Execute" or starts with "Execute").
    for (const btn of screen.queryAllByRole('button')) {
      const text = (btn.textContent ?? '').trim().toLowerCase();
      expect(text).not.toMatch(/^\s*execute\b/);
    }
    expect(screen.queryByRole('button', { name: /^execute$/i })).not.toBeInTheDocument();
    // The explanatory non-execution copy IS present (this is required, not forbidden).
    expect(screen.getByTestId('p22-subtitle').textContent?.toLowerCase()).toContain('non-executing');
  });

  it('P22-P12: no product/payment/business wording as actionable; every action is mutation=none', async () => {
    renderPage();
    await screen.findAllByTestId('p22-catalog-item');
    // Every catalog action declares no tenant business mutation.
    const mutations = screen.getAllByTestId('p22-catalog-mutation').map((m) => m.textContent);
    expect(mutations.every((m) => m === 'none')).toBe(true);
    // No button commands a product/payment/business action.
    const productWords = /order|invoice|payment|customer|inventory|ledger|billing/i;
    for (const btn of screen.queryAllByRole('button')) {
      expect(productWords.test(btn.textContent ?? '')).toBe(false);
    }
    // The form input labels do not promise product/payment mutation.
    const formText = screen.getByTestId('p22-dry-run-form').textContent ?? '';
    expect(productWords.test(formText)).toBe(false);
  });

  // -- R1: editing ANY payload field after a passed dry-run invalidates it ----

  it('P22-P13: editing reason after a passed dry-run forces a fresh dry-run', async () => {
    renderPage();
    await passDryRunAndAck();
    fireEvent.change(screen.getByTestId('p22-reason-input'), {
      target: { value: 'changed reason for re-dry-run' },
    });
    expectRecordUnavailableAfterEdit();
  });

  it('P22-P14: editing the idempotency key after a passed dry-run forces a fresh dry-run', async () => {
    renderPage();
    await passDryRunAndAck();
    fireEvent.change(screen.getByTestId('p22-idempotency-input'), {
      target: { value: 'DIFFERENT-RAW-KEY-456' },
    });
    expectRecordUnavailableAfterEdit();
  });

  it('P22-P15: editing metadata after a passed dry-run forces a fresh dry-run', async () => {
    renderPage();
    await passDryRunAndAck();
    fireEvent.change(screen.getByTestId('p22-metadata-input'), {
      target: { value: '{"note":"changed metadata"}' },
    });
    expectRecordUnavailableAfterEdit();
  });

  it('P22-P16: editing correlation id after a passed dry-run forces a fresh dry-run', async () => {
    renderPage();
    await passDryRunAndAck();
    fireEvent.change(screen.getByTestId('p22-correlation-input'), {
      target: { value: 'corr-changed-789' },
    });
    expectRecordUnavailableAfterEdit();
  });
});

// ---------------------------------------------------------------------------
// P22-E4: backup.check source status (read-only probe surfaced in the console).
// ---------------------------------------------------------------------------

/** Build a BackupCheckSourceRead-shaped axios response body. */
function backupSourceResponse(over: Record<string, unknown> = {}) {
  return {
    data: {
      action_type: 'backup.check',
      action_class: 'read',
      binding: 'read_only_source_probe',
      adapter_result: 'not_implemented',
      source_status: 'known',
      source_summary: 'fresh_success',
      last_backup_status: 'success',
      last_backup_at: '2026-07-04T00:00:00Z',
      restore_test_status: 'passed',
      last_restore_test_at: '2026-07-03T00:00:00Z',
      failure_reason_redacted: null,
      export_available: true,
      retention_policy: '7 daily',
      p17_backup_source_status: 'available',
      realizes_execution: false,
      executed: false,
      execution_started: false,
      execution_allowed: false,
      result_state: 'blocked',
      read_only: true,
      redaction_applied: true,
      reason: null,
      checked_at: '2026-07-04T00:00:00Z',
      ...over,
    },
  };
}

describe('PlatformControlledExecutionConsolePage -- backup.check source (P22-E4)', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({ data: CATALOG });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
  });

  /** Render, wait for mount, queue a source response, and click refresh. */
  async function refreshSource(sourceOver: Record<string, unknown> = {}) {
    renderPage();
    await screen.findAllByTestId('p22-catalog-item');
    vi.mocked(api.get).mockResolvedValueOnce(backupSourceResponse(sourceOver));
    fireEvent.click(screen.getByTestId('p22-backup-check-refresh'));
    await screen.findByTestId('p22-backup-check-result');
  }

  it('P22-E4-P01: a fresh-success source is visible as known and stays non-executing', async () => {
    await refreshSource({ source_status: 'known', source_summary: 'fresh_success' });
    const section = screen.getByTestId('p22-backup-check-source');
    expect(within(section).getByTestId('p22-backup-check-status').textContent).toBe('known');
    expect(within(section).getByTestId('p22-backup-check-summary').textContent).toBe(
      'fresh_success',
    );
    expect(within(section).getByTestId('p22-backup-check-last-status').textContent).toBe(
      'success',
    );
    // Non-executing flags are surfaced and all false.
    const nonexec = within(section).getByTestId('p22-backup-check-nonexec').textContent ?? '';
    expect(nonexec).toContain('realizes_execution=false');
    expect(nonexec).toContain('executed=false');
    expect(nonexec).toContain('execution_allowed=false');
    expect(nonexec).toContain('result_state=blocked');
    // No execution-violation warning.
    expect(within(section).queryByTestId('p22-backup-check-exec-violation')).not.toBeInTheDocument();
  });

  it('P22-E4-P02: a stale source is degraded and never shown as success', async () => {
    await refreshSource({
      source_status: 'degraded',
      source_summary: 'stale',
      last_backup_status: 'stale',
    });
    const section = screen.getByTestId('p22-backup-check-source');
    expect(within(section).getByTestId('p22-backup-check-status').textContent).toBe('degraded');
    expect(within(section).getByTestId('p22-backup-check-summary').textContent).toBe('stale');
    expect(within(section).getByTestId('p22-backup-check-last-status').textContent).toBe('stale');
    // Never implied healthy.
    expect(within(section).getByTestId('p22-backup-check-status').textContent).not.toBe('known');
  });

  it('P22-E4-P03: a no-outcome source is unknown and never healthy', async () => {
    await refreshSource({
      source_status: 'unknown',
      source_summary: 'unknown',
      last_backup_status: null,
      last_backup_at: null,
      export_available: null,
      reason: 'No backup outcome has been recorded; status is unknown.',
    });
    const section = screen.getByTestId('p22-backup-check-source');
    expect(within(section).getByTestId('p22-backup-check-status').textContent).toBe('unknown');
    expect(within(section).getByTestId('p22-backup-check-summary').textContent).toBe('unknown');
    // A null last_backup_status renders the placeholder, never 'success'.
    expect(within(section).getByTestId('p22-backup-check-last-status').textContent).toBe('-');
    expect(within(section).getByTestId('p22-backup-check-status').textContent).not.toBe('known');
  });

  it('P22-E4-P04: an unavailable (fail-closed) source is shown as unknown, never healthy, no crash', async () => {
    await refreshSource({
      source_status: 'unknown',
      source_summary: 'unavailable',
      last_backup_status: null,
      last_backup_at: null,
      export_available: null,
      p17_backup_source_status: 'unavailable',
      reason: 'Backup source read failed; status is unavailable.',
    });
    const section = screen.getByTestId('p22-backup-check-source');
    expect(within(section).getByTestId('p22-backup-check-status').textContent).toBe('unknown');
    expect(within(section).getByTestId('p22-backup-check-summary').textContent).toBe(
      'unavailable',
    );
    // Unavailable must never look healthy.
    expect(within(section).getByTestId('p22-backup-check-status').textContent).not.toBe('known');
  });

  it('P22-E4-P05: a transport failure surfaces an operator error and no result (no crash)', async () => {
    renderPage();
    await screen.findAllByTestId('p22-catalog-item');
    vi.mocked(api.get).mockRejectedValueOnce(new Error('network down'));
    fireEvent.click(screen.getByTestId('p22-backup-check-refresh'));
    expect(await screen.findByTestId('p22-backup-check-error')).toBeInTheDocument();
    expect(screen.queryByTestId('p22-backup-check-result')).not.toBeInTheDocument();
  });

  it('P22-E4-P06: the section exposes NO execute / run / dispatch control and no raw failure text', async () => {
    // A failed backup carries only the allowlisted reason code; the raw text
    // ('Traceback...') must never be displayed.
    await refreshSource({
      source_status: 'degraded',
      source_summary: 'failed',
      last_backup_status: 'failed',
      failure_reason_redacted: 'backup_incomplete',
    });
    const section = screen.getByTestId('p22-backup-check-source');
    // The only button in the section is the read-only refresh; it offers no
    // execution / dispatch / restore / dump affordance.
    const buttons = within(section).getAllByRole('button');
    expect(buttons).toHaveLength(1);
    expect(buttons[0].textContent).toMatch(/refresh source status/i);
    expect(buttons[0].textContent).not.toMatch(/execute|run|dispatch|restore|dump/i);
    // No link or extra control invites execution either.
    expect(within(section).queryByRole('link')).not.toBeInTheDocument();
    // The allowlisted reason is shown; a raw stack trace is never present.
    expect(within(section).getByTestId('p22-backup-check-failure-reason').textContent).toBe(
      'backup_incomplete',
    );
    expect(section.textContent ?? '').not.toContain('Traceback');
  });

  it('P22-E4-P07: forwarding a tenant_id reaches the query param', async () => {
    renderPage();
    await screen.findAllByTestId('p22-catalog-item');
    vi.mocked(api.get).mockResolvedValueOnce(backupSourceResponse({ source_status: 'known' }));
    fireEvent.change(screen.getByTestId('p22-backup-check-tenant-id'), {
      target: { value: 'tenant-xyz' },
    });
    fireEvent.click(screen.getByTestId('p22-backup-check-refresh'));
    await screen.findByTestId('p22-backup-check-result');
    expect(vi.mocked(api.get)).toHaveBeenCalledWith('/platform/p22/backup-check/source', {
      params: { tenant_id: 'tenant-xyz' },
    });
  });
});
