import Link from "next/link";
import { Suspense } from "react";

import { AppNav, AppNavSkeleton } from "@/components/app-nav";
import { UserMenu, UserMenuSkeleton } from "@/components/user-menu";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <header className="border-b border-border bg-surface-1/60 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5 rounded-sm">
            <span aria-hidden className="size-3 rotate-45 rounded-[3px] bg-accent shadow-[0_0_12px_var(--accent-subtle)]" />
            <span className="text-sm font-semibold tracking-tight">OpsPilot</span>
          </Link>
          <div className="order-last w-full sm:order-none sm:w-auto sm:flex-1">
            <Suspense fallback={<AppNavSkeleton />}>
              <AppNav />
            </Suspense>
          </div>
          <div className="ml-auto sm:ml-0">
            <Suspense fallback={<UserMenuSkeleton />}>
              <UserMenu />
            </Suspense>
          </div>
        </div>
      </header>
      {children}
    </>
  );
}
