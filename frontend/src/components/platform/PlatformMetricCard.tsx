/**
 * PlatformMetricCard — displays a single metric with label, value, and optional status.
 *
 * Handles unknown/null values: displays "N/A" with tooltip, never "0" for null.
 */
import { displayCount } from '@/types/platform';

interface PlatformMetricCardProps {
  label: string;
  value: number | null;
  suffix?: string;
  children?: React.ReactNode;
}

export function PlatformMetricCard({ label, value, suffix, children }: PlatformMetricCardProps) {
  const display = displayCount(value);
  const isUnknown = value === null;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-sm font-medium text-gray-500">{label}</p>
      <p
        className={`mt-1 text-2xl font-semibold ${isUnknown ? 'text-gray-400' : 'text-gray-900'}`}
        title={isUnknown ? 'Data unavailable' : undefined}
      >
        {display}
        {suffix && !isUnknown && <span className="ml-1 text-sm font-normal text-gray-500">{suffix}</span>}
      </p>
      {children}
    </div>
  );
}
