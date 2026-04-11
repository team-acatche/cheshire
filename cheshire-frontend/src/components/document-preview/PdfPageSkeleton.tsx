import { Skeleton } from "@/components/ui/skeleton";

export function PdfPageSkeleton({ zoomLevel = 1 }: { zoomLevel?: number }) {
  return (
    <div className="flex justify-center py-6">
      <div
        className="w-full max-w-[700px] rounded-md border bg-white p-6 shadow-lg overflow-hidden"
        style={{
          height: `${950 * zoomLevel}px`,
        }}
      >
        <div className="flex flex-col gap-3">
          <Skeleton className="h-6 w-1/2" />

          {Array.from({ length: Math.floor(18 * zoomLevel) }).map((_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}