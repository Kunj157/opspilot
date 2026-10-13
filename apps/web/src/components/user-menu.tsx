import { getCurrentUser } from "@/server/current-user";

const ROLE_LABELS: Record<string, string> = {
  viewer: "Viewer",
  operator: "Operator",
  "incident-commander": "Incident commander",
  administrator: "Administrator",
};

export async function UserMenu() {
  const user = await getCurrentUser();
  return (
    <div className="flex items-center gap-3">
      <div className="hidden text-right sm:block">
        <p className="text-sm font-medium leading-tight" data-testid="user-name">
          {user.display_name}
        </p>
        <p className="font-mono text-xs text-fg-muted">{user.organization.slug}</p>
      </div>
      <ul aria-label="Your roles" className="flex flex-wrap gap-1.5">
        {user.roles.map((role) => (
          <li
            key={role}
            className="rounded-full border border-border-strong bg-surface-3 px-2 py-0.5 text-xs text-fg-secondary"
          >
            {ROLE_LABELS[role] ?? role}
          </li>
        ))}
        {user.roles.length === 0 && (
          <li className="rounded-full border border-border px-2 py-0.5 text-xs text-fg-muted">
            No role
          </li>
        )}
      </ul>
      <form action="/auth/logout" method="post">
        <button
          type="submit"
          className="rounded-card border border-border px-3 py-1.5 text-sm text-fg-secondary transition-colors duration-base hover:border-border-strong hover:text-fg"
        >
          Sign out
        </button>
      </form>
    </div>
  );
}

export function UserMenuSkeleton() {
  return <div aria-hidden className="h-8 w-48 animate-pulse rounded-card bg-surface-3" />;
}
