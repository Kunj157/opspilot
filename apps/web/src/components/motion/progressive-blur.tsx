/**
 * Content fading out under a stack of increasingly blurred layers (Progressive
 * Blur, after Motion Primitives) — used at the edge of sticky bars and
 * scrolling lists so content dissolves instead of being cut off.
 */
const LAYERS = [1, 2, 4, 8];

export function ProgressiveBlur({
  side = "bottom",
  placement,
  className,
}: {
  /** The edge where the blur is strongest. */
  side?: "top" | "bottom";
  /** Positioning classes; defaults to hugging `side` of the parent. */
  placement?: string;
  className?: string;
}) {
  const towards = side === "bottom" ? "to bottom" : "to top";
  const edge = placement ?? (side === "bottom" ? "bottom-0" : "top-0");
  return (
    <div aria-hidden className={`pointer-events-none absolute inset-x-0 ${edge} ${className ?? "h-8"}`}>
      {LAYERS.map((blur, i) => {
        const start = (i / LAYERS.length) * 100;
        const end = ((i + 1) / LAYERS.length) * 100;
        const mask = `linear-gradient(${towards}, transparent ${start}%, black ${end}%)`;
        return (
          <div
            key={blur}
            className="absolute inset-0"
            style={{ backdropFilter: `blur(${blur}px)`, maskImage: mask, WebkitMaskImage: mask }}
          />
        );
      })}
    </div>
  );
}
