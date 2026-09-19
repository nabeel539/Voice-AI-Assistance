import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground animate-pulse p-4 space-y-4">
      {/* Header bar skeleton */}
      <div className="h-14 border-b border-border flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <Skeleton className="w-8 h-8 rounded-lg" />
          <div className="space-y-1">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-48" />
          </div>
        </div>
        <Skeleton className="h-8 w-28 rounded-md" />
      </div>

      {/* Voice bar skeleton */}
      <div className="h-10 border-b border-border/80 px-4 flex items-center justify-between">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-5 w-24" />
      </div>

      {/* Main layout skeleton */}
      <div className="flex-1 max-w-7xl w-full mx-auto flex flex-col lg:flex-row gap-4">
        <div className="w-full lg:w-80 space-y-4 shrink-0">
          <Skeleton className="h-[380px] w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
        <div className="flex-1 space-y-4">
          <Skeleton className="h-16 w-full rounded-xl" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 h-[420px]">
            <Skeleton className="h-full w-full rounded-xl" />
            <Skeleton className="h-full w-full rounded-xl" />
          </div>
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      </div>
    </div>
  );
}
