import { Skeleton } from '@/components/ui/Skeleton';

export function DashboardSkeleton() {
    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="space-y-2">
                <Skeleton className="h-8 w-48" />
                <Skeleton className="h-4 w-64" />
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="rounded-xl border border-gray-200 p-5 bg-white">
                        <Skeleton className="h-4 w-24 mb-3" />
                        <Skeleton className="h-8 w-16" />
                    </div>
                ))}
            </div>

            {/* Chart Area */}
            <div className="rounded-xl border border-gray-200 bg-white p-6 h-80">
                <Skeleton className="h-6 w-48 mb-6" />
                <div className="flex items-end gap-2 h-56">
                    {[...Array(12)].map((_, i) => (
                        <Skeleton key={i} className="w-full" style={{ height: `${Math.random() * 80 + 20}%` }} />
                    ))}
                </div>
            </div>
        </div>
    );
}
