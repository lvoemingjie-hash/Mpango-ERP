import { Skeleton } from '@/components/ui/Skeleton';

export function CardGridSkeleton() {
    return (
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="rounded-lg border border-gray-200 bg-white p-4">
                    <div className="flex justify-between items-start mb-4">
                        <div className="space-y-2">
                            <Skeleton className="h-5 w-32" />
                            <Skeleton className="h-3 w-20" />
                        </div>
                        <Skeleton className="h-6 w-16 rounded-full" />
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                        <div className="space-y-1">
                            <Skeleton className="h-3 w-12" />
                            <Skeleton className="h-4 w-8" />
                        </div>
                        <div className="space-y-1">
                            <Skeleton className="h-3 w-12" />
                            <Skeleton className="h-4 w-8" />
                        </div>
                        <div className="space-y-1">
                            <Skeleton className="h-3 w-12" />
                            <Skeleton className="h-4 w-8" />
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
}
