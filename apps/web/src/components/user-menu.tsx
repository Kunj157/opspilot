import { getCurrentUser } from "@/server/current-user";

const ROLE_LABELS: Record<string, string> = {
  viewer: "Viewer",
  operator: "Operator",
  "incident-commander": "Incident commander",
  administrator: "Administrator",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

export async function UserMenu() {
  const user = await getCurrentUser();
  return (
    <div className="surface-raised flex flex-col gap-3 rounded-card border border-border p-3">
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="grid size-8 shrink-0 place-items-center rounded-full border border-border-strong bg-accent-subtle font-mono text-xs font-medium text-accent"
        >
          {initials(user.display_name)}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium" data-testid="user-name">
            {user.display_name}
          </p>
          <p className="truncate font-mono text-xs text-fg-muted">{user.organization.slug}</p>
        </div>
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
          <li className="rounded-full border border-border px-2 py-0.5 text-xs text-fg-muted">No role</li>
        )}
      </ul>
      <form action="/auth/logout" method="post">
        <button
          type="submit"
          className="w-full rounded-sm border border-border px-3 py-1.5 text-sm text-fg-secondary transition-colors duration-(--duration-instant) hover:border-border-strong hover:bg-surface-3 hover:text-fg"
        >
          Sign out
        </button>
      </form>
    </div>
  );
}

export function UserMenuSkeleton() {
  return <div aria-hidden className="skeleton h-32 rounded-card" />;
}
