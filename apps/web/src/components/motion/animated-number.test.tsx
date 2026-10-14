import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnimatedNumber } from "./animated-number";

function prefersReducedMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduce && query.includes("reduce"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("AnimatedNumber", () => {
  it("renders the value as plain text", () => {
    render(<AnimatedNumber value={7} />);
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("counts up to the value and settles on it", async () => {
    prefersReducedMotion(false);
    const { container } = render(<AnimatedNumber value={12} from={0} />);
    expect(container).toHaveTextContent("0");
    await waitFor(() => expect(container).toHaveTextContent("12"), { timeout: 3000 });
  });

  it("jumps straight to new values under reduced motion", () => {
    prefersReducedMotion(true);
    const { container, rerender } = render(<AnimatedNumber value={3} from={0} format={(n) => `${n.toFixed(0)}m`} />);
    expect(container).toHaveTextContent("3m");
    rerender(<AnimatedNumber value={9} from={0} format={(n) => `${n.toFixed(0)}m`} />);
    expect(container).toHaveTextContent("9m");
  });
});
