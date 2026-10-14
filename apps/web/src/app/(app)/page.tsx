import { CommandCenter } from "@/components/command-center";
import { PageHeader } from "@/components/ui/page-header";

export const metadata = { title: "Command center · OpsPilot" };

export default function CommandCenterPage() {
  return (
    <main className="w-full max-w-6xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <PageHeader
        eyebrow="Command center"
        title="Overview"
        description="What needs attention right now across your services."
      />
      <div className="mt-10">
        <CommandCenter />
      </div>
    </main>
  );
}
