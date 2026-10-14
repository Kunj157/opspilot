/**
 * A blurred halo behind an element whose state is actively changing (Glow
 * Effect, after Motion Primitives). Static by default; `breathing` adds a slow
 * CSS pulse that the global reduced-motion rule stops.
 */
export function GlowEffect({
  tone = "accent",
  breathing = false,
  className,
}: {
  tone?: "accent" | "critical";
  breathing?: boolean;
  className?: string;
}) {
  const color = tone === "critical" ? "bg-critical-glow" : "bg-accent-glow";
  return (
    <span
      aria-hidden
      className={`pointer-events-none absolute -inset-1 -z-10 rounded-[inherit] blur-xl ${color} ${
        breathing ? "animate-[glow-breathe_2.8s_var(--ease-in-out)_infinite]" : "opacity-70"
      } ${className ?? ""}`}
    />
  );
}
