/** Compact duration: "<1m", "6m", "1h 12m", "2d 3h"; "—" when unknown. */
export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const minutes = Math.max(0, Math.floor(seconds / 60));
  if (minutes === 0) return "<1m";
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${mins}m`;
  return `${mins}m`;
}
