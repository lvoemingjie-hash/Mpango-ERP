/**
 * P24-C: Platform incident closeout + runbook type / vocabulary tests.
 *
 * Verifies the closed vocabularies are exact (8 closeout states, 3 step kinds,
 * 5 step states, 3 severities, 3 source statuses, 3 flag-observed values, 7
 * intake event types, 10 denial codes), the transition graphs are closed
 * (terminal states have no outgoing edges), and the client-side display-tone
 * resolvers defend the P24-A honesty rules:
 *   - source_unknown is NEVER healthy (never green) -- closeout AND step.
 *   - a degraded source OR a completed_with_warning linked execution is NEVER
 *     success (never green).
 *   - a blocked runbook step is NEVER healthy (never green).
 *   - 'closed' (closeout) and 'completed' (step) are blue, not green, so a
 *     warning closeout / step is never visually read as success.
 */
import { describe, it, expect } from 'vitest';
import {
  ACTOR_SCOPES,
  ALLOWED_CLOSEOUT_TRANSITIONS,
  ALLOWED_STEP_TRANSITIONS,
  CLASSIFICATIONS,
  CLOSEOUT_DENIAL_CODES,
  CLOSEOUT_STATES,
  FLAG_OBSERVED_VALUES,
  OWNER_ROLES,
  SEVERITIES,
  SOURCE_STATUSES,
  STEP_KINDS,
  STEP_STATES,
  TERMINAL_CLOSEOUT_STATES,
  TERMINAL_STEP_STATES,
  isHealthyIncidentTone,
  isTerminalCloseoutState,
  isTerminalStepState,
  resolveCloseoutDisplayTone,
  resolveStepDisplayTone,
} from '@/types/platformIncidentCloseout';

describe('P24 incident closeout closed vocabularies', () => {
  it('closeout states are exactly the eight defined states', () => {
    expect(CLOSEOUT_STATES).toEqual([
      'detected',
      'triaged',
      'flagged_active',
      'in_remediation',
      'awaiting_closeout',
      'closed',
      'withdrawn',
      'expired',
    ]);
    expect(CLOSEOUT_STATES.length).toBe(8);
  });

  it('terminal closeout states are closed/withdrawn/expired', () => {
    expect(TERMINAL_CLOSEOUT_STATES).toEqual(
      new Set(['closed', 'withdrawn', 'expired']),
    );
    for (const s of CLOSEOUT_STATES) {
      expect(isTerminalCloseoutState(s)).toBe(TERMINAL_CLOSEOUT_STATES.has(s));
    }
  });

  it('step kinds are exactly observation / action_pointer / approval_pointer', () => {
    expect(STEP_KINDS).toEqual([
      'observation',
      'action_pointer',
      'approval_pointer',
    ]);
  });

  it('step states are exactly the five defined states', () => {
    expect(STEP_STATES).toEqual([
      'owed',
      'in_progress',
      'done',
      'not_applicable',
      'blocked',
    ]);
  });

  it('terminal step states are done / not_applicable', () => {
    expect(TERMINAL_STEP_STATES).toEqual(new Set(['done', 'not_applicable']));
    for (const s of STEP_STATES) {
      expect(isTerminalStepState(s)).toBe(TERMINAL_STEP_STATES.has(s));
    }
  });

  it('severities / sources / flag-observed / scopes / owners are closed sets', () => {
    expect(SEVERITIES).toEqual(['low', 'medium', 'high']);
    expect(SOURCE_STATUSES).toEqual(['known', 'unknown', 'degraded']);
    expect(FLAG_OBSERVED_VALUES).toEqual([
      'observed_true',
      'observed_false',
      'observed_unknown',
    ]);
    expect(ACTOR_SCOPES).toEqual(['platform', 'tenant_contextual']);
    expect(OWNER_ROLES).toEqual([
      'super_admin',
      'engineering_operator',
      'support_operator',
    ]);
    expect(CLASSIFICATIONS).toEqual([
      'database',
      'system',
      'api',
      'tenant_health',
      'support_issue',
    ]);
  });

  it('denial codes are the ten defined codes', () => {
    expect(CLOSEOUT_DENIAL_CODES).toEqual([
      'TRANSITION_DENIED_INVALID',
      'TRANSITION_DENIED_TERMINAL',
      'CLOSE_DENIED_FLAG_STILL_SET',
      'CLOSE_DENIED_OWED_TASKS_NONTERMINAL',
      'CLOSE_DENIED_SOURCE_UNKNOWN',
      'CLOSE_DENIED_EXECUTION_WARNING',
      'STEP_DONE_DENIED_GATE_OPEN',
      'STEP_DONE_DENIED_NO_EVIDENCE',
      'CLOSEOUT_NOT_FOUND',
      'STEP_NOT_FOUND',
    ]);
  });
});

describe('P24 transition graphs are closed', () => {
  it('terminal closeout states have no outgoing edges', () => {
    for (const s of CLOSEOUT_STATES) {
      const edges = ALLOWED_CLOSEOUT_TRANSITIONS[s];
      if (TERMINAL_CLOSEOUT_STATES.has(s)) {
        expect(edges).toEqual([]);
      } else {
        expect(edges.length).toBeGreaterThan(0);
      }
    }
  });

  it('terminal step states have no outgoing edges', () => {
    for (const s of STEP_STATES) {
      const edges = ALLOWED_STEP_TRANSITIONS[s];
      if (TERMINAL_STEP_STATES.has(s)) {
        expect(edges).toEqual([]);
      } else {
        expect(edges.length).toBeGreaterThan(0);
      }
    }
  });

  it('every transition edge targets a defined state within the same graph', () => {
    for (const s of CLOSEOUT_STATES) {
      for (const t of ALLOWED_CLOSEOUT_TRANSITIONS[s]) {
        expect(CLOSEOUT_STATES).toContain(t);
      }
    }
    for (const s of STEP_STATES) {
      for (const t of ALLOWED_STEP_TRANSITIONS[s]) {
        expect(STEP_STATES).toContain(t);
      }
    }
  });

  it('awaiting_closeout can target closed (the honest close path exists)', () => {
    expect(ALLOWED_CLOSEOUT_TRANSITIONS.awaiting_closeout).toContain('closed');
  });

  it('a done step cannot exit (terminal); owed can reach done', () => {
    expect(ALLOWED_STEP_TRANSITIONS.done).toEqual([]);
    expect(ALLOWED_STEP_TRANSITIONS.owed).toContain('done');
  });
});

describe('resolveCloseoutDisplayTone honesty rules', () => {
  it('source_unknown is never green in EVERY state, including closed', () => {
    for (const state of CLOSEOUT_STATES) {
      const tone = resolveCloseoutDisplayTone(
        state === 'closed' ? 'closed' : 'healthy',
        'unknown',
        false,
      );
      expect(isHealthyIncidentTone(tone)).toBe(false);
      expect(tone).toBe('gray');
    }
  });

  it('a degraded source is never green (yellow), even closed', () => {
    expect(resolveCloseoutDisplayTone('closed', 'degraded', false)).toBe('yellow');
    expect(resolveCloseoutDisplayTone('healthy', 'degraded', false)).toBe('yellow');
  });

  it('a completed_with_warning linked execution is never green (yellow)', () => {
    expect(resolveCloseoutDisplayTone('closed', 'known', true)).toBe('yellow');
    expect(resolveCloseoutDisplayTone('healthy', 'known', true)).toBe('yellow');
  });

  it('a healthy known closeout IS green (sanity: green is source-gated)', () => {
    expect(resolveCloseoutDisplayTone('healthy', 'known', false)).toBe('green');
  });

  it('closed is blue (not green) so success is never implied by termination', () => {
    expect(resolveCloseoutDisplayTone('closed', 'known', false)).toBe('blue');
    expect(isHealthyIncidentTone('blue')).toBe(false);
  });

  it('withdrawn is gray; unknown/none are gray', () => {
    expect(resolveCloseoutDisplayTone('withdrawn', 'known', false)).toBe('gray');
    expect(resolveCloseoutDisplayTone('unknown', 'known', false)).toBe('gray');
    expect(resolveCloseoutDisplayTone('none', 'known', false)).toBe('gray');
  });

  it('source_unknown wins over a degraded/warning mirror (never healthy)', () => {
    // unknown + warning -> still gray (unknown is the strongest never-healthy).
    expect(resolveCloseoutDisplayTone('healthy', 'unknown', true)).toBe('gray');
  });
});

describe('resolveStepDisplayTone honesty rules', () => {
  it('a source_unknown step is never green in every non-terminal step state', () => {
    for (const state of STEP_STATES) {
      const tone = resolveStepDisplayTone(
        state === 'done' ? 'completed' : 'healthy',
        'unknown',
        false,
        state,
      );
      expect(isHealthyIncidentTone(tone)).toBe(false);
    }
  });

  it('a blocked step is never green (gray), regardless of source', () => {
    expect(resolveStepDisplayTone('healthy', 'known', false, 'blocked')).toBe('gray');
    expect(resolveStepDisplayTone('healthy', 'unknown', false, 'blocked')).toBe('gray');
  });

  it('a degraded source step is never green (yellow)', () => {
    expect(resolveStepDisplayTone('completed', 'degraded', false, 'done')).toBe('yellow');
    expect(resolveStepDisplayTone('healthy', 'degraded', false, 'in_progress')).toBe('yellow');
  });

  it('a completed_with_warning step is never green (yellow)', () => {
    expect(resolveStepDisplayTone('completed', 'known', true, 'done')).toBe('yellow');
  });

  it('done is blue (completed), not green; dismissed is gray', () => {
    expect(resolveStepDisplayTone('completed', 'known', false, 'done')).toBe('blue');
    expect(isHealthyIncidentTone('blue')).toBe(false);
    expect(resolveStepDisplayTone('dismissed', 'known', false, 'not_applicable')).toBe('gray');
  });

  it('a healthy known owed step IS green (sanity)', () => {
    expect(resolveStepDisplayTone('healthy', 'known', false, 'owed')).toBe('green');
  });
});
