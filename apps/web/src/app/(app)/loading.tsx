export default function Loading() {
  return (
    <main aria-busy="true" className="w-full max-w-5xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <div className="h-3 w-28 skeleton rounded" />
      <div className="mt-4 h-9 w-64 skeleton rounded" />
      <div className="mt-10 h-64 skeleton rounded-card" />
    </main>
  );
}
