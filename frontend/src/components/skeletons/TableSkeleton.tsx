import { Skeleton } from '@/components/ui/Skeleton';

export function TableSkeleton() {
    return (
        <div className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
            <div className="border-b border-gray-200 bg-gray-50 px-4 py-3">
                <div className="flex gap-4">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-4 w-full" />
                </div>
            </div>
            {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="flex gap-4 border-b border-gray-100 px-4 py-4 items-center">
                    <Skeleton className="h-4 w-1/6" />
                    <Skeleton className="h-4 w-1/4" />
                    <Skeleton className="h-4 w-1/3" />
                    <Skeleton className="h-4 w-1/6" />
                </div>
            ))}
        </div>
    );
}
