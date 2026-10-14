import type { ReactNode } from "react";

/**
 * Text with a light band sweeping across it (Text Shimmer, after Motion
 * Primitives), used only for live agent activity. Pure CSS, so it costs no
 * JavaScript; the global reduced-motion rule leaves the text static.
 */
export function TextShimmer({
  as: Component = "span",
  children,
  className,
}: {
  as?: "span" | "p" | "div";
  children: ReactNode;
  className?: string;
}) {
  return <Component className={`text-shimmer ${className ?? ""}`}>{children}</Component>;
}
