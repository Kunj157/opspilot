// One incident, looped: shared by the 3D scene and the status caption so they
// always agree. Durations in seconds.

export type Phase = "healthy" | "failing" | "investigating" | "remediating" | "recovered";

export const PHASES: { phase: Phase; seconds: number; caption: string }[] = [
  { phase: "healthy", seconds: 3, caption: "All five services healthy" },
  { phase: "failing", seconds: 3, caption: "Faulty checkout release · error rate 47 % · incident opened" },
  { phase: "investigating", seconds: 3.5, caption: "Agents investigating · evidence cited · rollback proposed" },
  { phase: "remediating", seconds: 2.5, caption: "Approved by the incident commander · rolling back" },
  { phase: "recovered", seconds: 3, caption: "Recovery verified against baseline · postmortem drafted" },
];

const TOTAL = PHASES.reduce((sum, p) => sum + p.seconds, 0);

export function phaseIndexAt(seconds: number): number {
  let t = seconds % TOTAL;
  for (let i = 0; i < PHASES.length; i++) {
    if (t < PHASES[i].seconds) return i;
    t -= PHASES[i].seconds;
  }
  return 0;
}

export const phaseAt = (seconds: number): Phase => PHASES[phaseIndexAt(seconds)].phase;
