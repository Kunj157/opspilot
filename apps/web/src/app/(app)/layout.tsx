import Link from "next/link";
import { Suspense } from "react";

import { AppMobileNav, AppNav, AppNavSkeleton } from "@/components/app-nav";
import { UserMenu, UserMenuSkeleton } from "@/components/user-menu";

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5 rounded-sm">
      <span
        aria-hidden
        className="size-3 rotate-45 rounded-[3px] bg-accent shadow-[0_0_12px_var(--accent-subtle)]"
      />
      <span className="text-sm font-semibold tracking-tight">OpsPilot</span>
    </Link>
  );
}

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-full flex-1">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-8 border-r border-border bg-surface-1/70 p-4 backdrop-blur md:flex">
        <div className="px-2 pt-1">
          <Logo />
        </div>
        <Suspense fallback={<AppNavSkeleton />}>
          <AppNav />
        </Suspense>
        <div className="mt-auto">
          <Suspense fallback={<UserMenuSkeleton />}>
            <UserMenu />
          </Suspense>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-surface-1/70 px-4 py-2 backdrop-blur md:hidden">
          <Logo />
          <Suspense fallback={<div className="size-9" />}>
            <AppMobileNav />
          </Suspense>
        </header>
        {children}
      </div>
    </div>
  );
}
