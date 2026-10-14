import Link from "next/link";
import { Suspense } from "react";

import { AppMobileNav, AppNav, AppNavSkeleton } from "@/components/app-nav";
import { ProgressiveBlur } from "@/components/motion/progressive-blur";
import { Breadcrumbs } from "@/components/shell/breadcrumbs";
import { CommandPaletteProvider, CommandPaletteTrigger } from "@/components/shell/command-palette-context";
import { UserMenu, UserMenuSkeleton } from "@/components/user-menu";

function Logo() {
  return (
    <Link href="/" className="group flex items-center gap-2.5 rounded-sm">
      <span
        aria-hidden
        className="size-3 rotate-45 rounded-[3px] bg-accent shadow-glow-accent transition-transform duration-(--duration-base) ease-out group-hover:rotate-[135deg]"
      />
      <span className="text-sm font-semibold tracking-tight">OpsPilot</span>
    </Link>
  );
}

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <CommandPaletteProvider>
      <div className="flex min-h-full flex-1">
        <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-8 border-r border-border bg-surface-1/70 bg-(image:--surface-sheen) p-4 backdrop-blur md:flex">
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
        {/* Sticky table headers sit below the 3rem top bar. */}
        <div className="flex min-w-0 flex-1 flex-col [--sticky-top:3rem]">
          <header className="sticky top-0 z-30 flex h-12 items-center justify-between gap-4 border-b border-border bg-surface-glass px-4 backdrop-blur-md sm:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <span className="md:hidden">
                <Logo />
              </span>
              <span className="hidden min-w-0 md:block">
                <Suspense fallback={null}>
                  <Breadcrumbs />
                </Suspense>
              </span>
            </div>
            {/* Content dissolves under the bar instead of meeting a hard edge. */}
            <ProgressiveBlur side="top" placement="top-full" className="h-6" />
            <div className="flex items-center gap-2">
              <CommandPaletteTrigger />
              <span className="md:hidden">
                <Suspense fallback={<div className="size-9" />}>
                  <AppMobileNav />
                </Suspense>
              </span>
            </div>
          </header>
          {children}
        </div>
      </div>
    </CommandPaletteProvider>
  );
}
