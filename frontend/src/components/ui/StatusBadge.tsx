type StatusType =
    | 'draft'
    | 'pending'
    | 'confirmed'
    | 'paid'
    | 'partially_paid'
    | 'fulfilled'
    | 'cancelled'
    | 'returned'
    | 'voided'
    | string;

interface StatusBadgeProps {
    status: StatusType;
    className?: string; // Allow additional styling if needed used carefully
}

export function StatusBadge({ status, className = '' }: StatusBadgeProps) {
    // Normalize status for consistent mapping (e.g. unexpected case)
    const normalizedStatus = status.toLowerCase();

    let colorClasses = 'bg-gray-100 text-gray-800'; // Default / Draft

    switch (normalizedStatus) {
        case 'confirmed':
        case 'active':
            colorClasses = 'bg-blue-100 text-blue-800';
            break;
        case 'paid':
        case 'completed':
        case 'success':
            colorClasses = 'bg-green-100 text-green-800';
            break;
        case 'partially_paid':
            colorClasses = 'bg-yellow-100 text-yellow-800';
            break;
        case 'fulfilled':
        case 'shipped':
        case 'delivered':
            colorClasses = 'bg-purple-100 text-purple-800';
            break;
        case 'cancelled':
        case 'voided':
        case 'failed':
        case 'returned':
        case 'inactive':
            colorClasses = 'bg-red-100 text-red-800';
            break;
        case 'pending':
        case 'processing':
            colorClasses = 'bg-amber-100 text-amber-800';
            break;
        default:
            // Fallback to gray
            break;
    }

    // Format label: replace underscores with spaces and capitalize first letter
    const label = status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

    return (
        <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colorClasses} ${className}`}
        >
            {label}
        </span>
    );
}
