/**
 * Command palette matching: every query character must appear in order.
 * Scores favour matches at the start of the label or of a word and runs of
 * consecutive characters, so "inc" ranks "Incidents" above "Runbook index".
 */
export function score(query: string, text: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 1;
  const t = text.toLowerCase();
  let total = 0;
  let from = 0;
  let previous = -2;
  for (const char of q) {
    if (char === " ") continue;
    const at = t.indexOf(char, from);
    if (at < 0) return 0;
    let points = 1;
    if (at === 0) points += 8;
    else if (/[\s\-_/.·]/.test(t[at - 1])) points += 5;
    if (at === previous + 1) points += 3;
    total += points;
    previous = at;
    from = at + 1;
  }
  // Shorter labels win ties: the match covers more of them.
  return total + q.length / t.length;
}

export type PaletteItem = {
  id: string;
  group: string;
  label: string;
  /** Extra words that should match but are not shown, e.g. an incident's service. */
  keywords?: string;
  hint?: string;
};

/** Items that match, best first, keeping group order stable for equal scores. */
export function filterItems<T extends PaletteItem>(items: T[], query: string): T[] {
  if (!query.trim()) return items;
  return items
    .map((item, index) => ({
      item,
      index,
      score: Math.max(score(query, item.label), score(query, `${item.label} ${item.keywords ?? ""}`) * 0.8),
    }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map((entry) => entry.item);
}
