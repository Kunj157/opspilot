import { getCurrentUser } from "@/server/current-user";

import { MobileNav } from "./shell/mobile-nav";
import { type NavItem, NAV_ITEMS } from "./shell/nav-items";
import { SidebarNav } from "./shell/sidebar-nav";
import { UserMenu } from "./user-menu";

/** Navigation filtered by the user's permissions; the API enforces them regardless. */
async function permittedItems(): Promise<NavItem[]> {
  const { permissions } = await getCurrentUser();
  return NAV_ITEMS.filter((item) => !item.permission || permissions.includes(item.permission)).map(
    ({ href, label, icon }) => ({ href, label, icon }),
  );
}

export async function AppNav() {
  return <SidebarNav items={await permittedItems()} />;
}

export async function AppMobileNav() {
  return <MobileNav items={await permittedItems()} footer={<UserMenu />} />;
}

export function AppNavSkeleton() {
  return (
    <div aria-hidden className="flex flex-col gap-2">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="skeleton h-8 rounded-sm" />
      ))}
    </div>
  );
}
