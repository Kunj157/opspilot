import { demoRunbookParams } from "@/demo/static-params";

// Demo build only (page extension "demo.tsx"): the pages the static export pre-renders for this route.
export const generateStaticParams = demoRunbookParams;

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return children;
}
