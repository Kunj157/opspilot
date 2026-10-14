/** Loading placeholder rows with the shimmer sweep; hidden from assistive technology. */
export function SkeletonRows({ rows = 4, className = "h-10" }: { rows?: number; className?: string }) {
  return (
    <div aria-hidden className="flex flex-col gap-2 p-5">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className={`skeleton rounded-sm ${className}`} />
      ))}
    </div>
  );
}
