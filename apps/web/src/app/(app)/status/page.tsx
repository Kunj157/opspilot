import { SystemStatus } from "@/components/system-status";
import { PageHeader } from "@/components/ui/page-header";

export const metadata = { title: "System status · OpsPilot" };

export default function StatusPage() {
  return (
    <main className="w-full max-w-6xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <PageHeader
        eyebrow="Platform"
        title="System status"
        description="Live readiness of the OpsPilot platform and the dependencies it needs to detect and investigate incidents."
      />

      <div className="mt-10 max-w-xl">
        <SystemStatus />
      </div>
    </main>
  );
}
