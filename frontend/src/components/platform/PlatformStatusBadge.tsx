/**
 * PlatformStatusBadge — displays health/status with correct color semantics.
 *
 * P11 rule: unknown != healthy. Unknown is gray, distinct from green.
 */
import type { HealthStatus, ComponentStatus } from '@/types/platform';

type StatusValue = HealthStatus | ComponentStatus;

interface PlatformStatusBadgeProps {
  status: StatusValue;
}

const statusStyles: Record<StatusValue, string> = {
  healthy: 'bg-green-100 text-green-800',
  degraded: 'bg-yellow-100 text-yellow-800',
  unhealthy: 'bg-red-100 text-red-800',
  down: 'bg-red-100 text-red-800',
  unknown: 'bg-gray-100 text-gray-600',
};

export function PlatformStatusBadge({ status }: PlatformStatusBadgeProps) {
  const style = statusStyles[status] ?? statusStyles.unknown;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}
      title={status === 'unknown' ? 'Data unavailable' : undefined}
    >
      {status}
    </span>
  );
}
