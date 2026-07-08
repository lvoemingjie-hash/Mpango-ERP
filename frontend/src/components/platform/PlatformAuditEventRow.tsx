/**
 * PlatformAuditEventRow — displays a single audit event in the list.
 *
 * Shows action, actor, scope, result, timestamp. Metadata is never
 * displayed as raw text (P11 forbidden rule).
 */
import { displayTimestamp } from '@/types/platform';
import type { PlatformAuditEvent } from '@/types/platform';

interface PlatformAuditEventRowProps {
  event: PlatformAuditEvent;
}

const resultStyles: Record<string, string> = {
  allowed: 'text-green-700',
  completed: 'text-green-700',
  denied: 'text-red-700',
  failed: 'text-yellow-700',
};

export function PlatformAuditEventRow({ event }: PlatformAuditEventRowProps) {
  const resultStyle = resultStyles[event.result] ?? 'text-gray-600';

  return (
    <tr className="border-b border-gray-100 last:border-0">
      <td className="px-4 py-3 text-sm text-gray-900 font-medium">
        {event.action}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">
        {event.actor_id ?? 'System'}
        {event.actor_role && (
          <span className="ml-1 text-xs text-gray-400">({event.actor_role})</span>
        )}
      </td>
      <td className="px-4 py-3 text-sm">
        <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
          {event.scope}
        </span>
      </td>
      <td className={`px-4 py-3 text-sm font-medium ${resultStyle}`}>
        {event.result}
      </td>
      <td className="px-4 py-3 text-sm text-gray-500">
        {displayTimestamp(event.created_at)}
      </td>
    </tr>
  );
}
