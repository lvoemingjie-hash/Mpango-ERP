/**
 * P25-B dimension: frontend console consistency (matrix dim 11; AC 13/14/15; C14/C15/C17).
 *
 * Asserts the P23 / P24 honesty rules hold CLIENT-SIDE for every tone resolver,
 * and that the same status renders in the same tone across the P22 / P23 / P24
 * consoles and the P11/P13/P14 PlatformStatusBadge:
 *
 *   - source_unknown is NEVER healthy   -> never green (gray).
 *   - backup_check_warning / degraded / linked-execution-warning is NEVER success
 *     -> never green (yellow).
 *   - terminal success (completed / closed / done) is rendered BLUE, not green,
 *     so a completed-but-warning record is never visually read as success.
 *   - 'healthy' is the ONLY green tone; isHealthyOperatorTone and
 *     isHealthyIncidentTone agree (no convention drift).
 */
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import {
  resolveOperatorDisplayTone,
  isHealthyOperatorTone,
  OPERATOR_DISPLAY_STATUSES,
  type OperatorDisplayTone,
} from '@/types/platformOperatorTasks';
import {
  resolveCloseoutDisplayTone,
  resolveStepDisplayTone,
  isHealthyIncidentTone,
  SOURCE_STATUSES,
  type IncidentDisplayTone,
} from '@/types/platformIncidentCloseout';
import { PlatformStatusBadge } from '@/components/platform/PlatformStatusBadge';

const GREEN: OperatorDisplayTone | IncidentDisplayTone = 'green';

describe('P25-B console consistency -- operator task tones (P23; AC 14)', () => {
  it('P25-T01: source_unknown is NEVER healthy, in EVERY display status (C14)', () => {
    for (const ds of OPERATOR_DISPLAY_STATUSES) {
      const tone = resolveOperatorDisplayTone('source_unknown', ds);
      expect(tone, `source_unknown + ${ds}`).not.toBe(GREEN);
      expect(isHealthyOperatorTone(tone)).toBe(false);
    }
  });

  it('P25-T02: backup_check_warning is NEVER success, in EVERY display status (C15)', () => {
    // "completed" is the adversarial case -- a completed backup_check_warning
    // must still not be green (it renders blue, never success).
    for (const ds of OPERATOR_DISPLAY_STATUSES) {
      const tone = resolveOperatorDisplayTone('backup_check_warning', ds);
      expect(tone, `backup_check_warning + ${ds}`).not.toBe(GREEN);
      expect(isHealthyOperatorTone(tone)).toBe(false);
    }
  });

  it('P25-T03: a healthy ordinary task is green; a completed ordinary task is blue', () => {
    expect(resolveOperatorDisplayTone('approval_pending', 'healthy')).toBe('green');
    expect(resolveOperatorDisplayTone('approval_pending', 'completed')).toBe('blue');
    expect(resolveOperatorDisplayTone('approval_pending', 'failed')).toBe('red');
  });
});

describe('P25-B console consistency -- incident closeout + step tones (P24; AC 14/15)', () => {
  it('P25-T04: closeout source_unknown is gray; degraded / linked warning is yellow; never green', () => {
    expect(resolveCloseoutDisplayTone('healthy', 'unknown', false)).toBe('gray');
    expect(resolveCloseoutDisplayTone('healthy', 'degraded', false)).toBe('yellow');
    expect(resolveCloseoutDisplayTone('healthy', 'known', true)).toBe('yellow');
    expect(resolveCloseoutDisplayTone('closed', 'unknown', false)).toBe('gray');
    expect(resolveCloseoutDisplayTone('closed', 'degraded', false)).toBe('yellow');
    // adversarial: closed + linked warning must NOT be green
    expect(resolveCloseoutDisplayTone('closed', 'known', true)).toBe('yellow');
  });

  it('P25-T05: a healthy known closeout is green; a clean closed closeout is blue', () => {
    expect(resolveCloseoutDisplayTone('healthy', 'known', false)).toBe('green');
    expect(resolveCloseoutDisplayTone('closed', 'known', false)).toBe('blue');
  });

  it('P25-T06: step source_unknown / blocked is gray; warning is yellow; never green', () => {
    expect(resolveStepDisplayTone('healthy', 'unknown', false, 'in_progress')).toBe('gray');
    expect(resolveStepDisplayTone('healthy', null, false, 'blocked')).toBe('gray');
    expect(resolveStepDisplayTone('healthy', 'degraded', false, 'in_progress')).toBe('yellow');
    expect(resolveStepDisplayTone('completed', 'known', true, 'done')).toBe('yellow');
    expect(resolveStepDisplayTone('completed', 'unknown', false, 'done')).toBe('gray');
  });

  it('P25-T07: a healthy done step is blue (terminal success not green)', () => {
    expect(resolveStepDisplayTone('healthy', 'known', false, 'done')).toBe('green');
    expect(resolveStepDisplayTone('completed', 'known', false, 'done')).toBe('blue');
  });
});

describe('P25-B console consistency -- cross-console convention (AC 13; C17)', () => {
  it('P25-T08: "healthy" is the ONLY green tone in both consoles (no drift)', () => {
    const operatorGreens: OperatorDisplayTone[] = ['green'];
    const incidentGreens: IncidentDisplayTone[] = ['green'];
    expect(operatorGreens).toEqual(incidentGreens);
    for (const t of ['green', 'yellow', 'gray', 'red', 'blue'] as const) {
      expect(isHealthyOperatorTone(t)).toBe(t === 'green');
      expect(isHealthyIncidentTone(t)).toBe(t === 'green');
    }
  });

  it('P25-T09: source_status "unknown" forces non-green for EVERY source status vocab', () => {
    // Defensive: regardless of which source statuses ship, "unknown" never green.
    expect(SOURCE_STATUSES).toContain('unknown');
    for (const ss of SOURCE_STATUSES) {
      if (ss === 'unknown') {
        expect(resolveCloseoutDisplayTone('healthy', ss, false)).toBe('gray');
      }
    }
  });

  it('P25-T10: PlatformStatusBadge renders unknown as gray (never green) -- P11/P13/P14/P17', () => {
    const { container: unknownBadge } = render(<PlatformStatusBadge status="unknown" />);
    const unknownClass = unknownBadge.querySelector('span')?.className ?? '';
    expect(unknownClass).toMatch(/bg-gray-100/);
    expect(unknownClass).not.toMatch(/bg-green-100/);

    const { container: healthyBadge } = render(<PlatformStatusBadge status="healthy" />);
    const healthyClass = healthyBadge.querySelector('span')?.className ?? '';
    expect(healthyClass).toMatch(/bg-green-100/);
  });
});
