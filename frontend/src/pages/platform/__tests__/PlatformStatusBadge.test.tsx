/**
 * P11-D: PlatformStatusBadge component tests.
 *
 * TC-008: Shows unknown as gray, distinct from green healthy.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PlatformStatusBadge } from '@/components/platform/PlatformStatusBadge';

describe('PlatformStatusBadge', () => {
  it('shows healthy as green', () => {
    render(<PlatformStatusBadge status="healthy" />);
    const badge = screen.getByText('healthy');
    expect(badge.className).toContain('bg-green-100');
    expect(badge.className).toContain('text-green-800');
  });

  it('shows degraded as yellow/amber', () => {
    render(<PlatformStatusBadge status="degraded" />);
    const badge = screen.getByText('degraded');
    expect(badge.className).toContain('bg-yellow-100');
    expect(badge.className).toContain('text-yellow-800');
  });

  it('shows unhealthy as red', () => {
    render(<PlatformStatusBadge status="unhealthy" />);
    const badge = screen.getByText('unhealthy');
    expect(badge.className).toContain('bg-red-100');
    expect(badge.className).toContain('text-red-800');
  });

  it('TC-008: shows unknown as gray, distinct from green healthy', () => {
    // Render unknown badge
    const { unmount } = render(<PlatformStatusBadge status="unknown" />);
    const unknownBadge = screen.getByText('unknown');
    expect(unknownBadge.className).toContain('bg-gray-100');
    expect(unknownBadge.className).toContain('text-gray-600');
    // Must NOT be green
    expect(unknownBadge.className).not.toContain('bg-green');
    expect(unknownBadge.className).not.toContain('text-green');
    // Has tooltip for "Data unavailable"
    expect(unknownBadge.getAttribute('title')).toBe('Data unavailable');

    // Clean up and render healthy separately to compare
    unmount();
    render(<PlatformStatusBadge status="healthy" />);
    const healthyBadge = screen.getByText('healthy');
    expect(healthyBadge.className).toContain('bg-green-100');
    // Confirm the unknown badge's class was NOT the same as healthy
    expect(unknownBadge.className).not.toBe(healthyBadge.className);
  });

  it('shows down as red', () => {
    render(<PlatformStatusBadge status="down" />);
    const badge = screen.getByText('down');
    expect(badge.className).toContain('bg-red-100');
  });
});
