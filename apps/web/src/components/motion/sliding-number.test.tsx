import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SlidingNumber } from "./sliding-number";

describe("SlidingNumber", () => {
  it("announces the plain value and hides the digit strips", () => {
    const { container } = render(<SlidingNumber value={42} />);
    expect(screen.getByText("42")).toHaveClass("sr-only");
    const strips = container.querySelector("[aria-hidden]")!;
    expect(strips.children).toHaveLength(2);
  });

  it("adds a column when the count grows", () => {
    const { container, rerender } = render(<SlidingNumber value={9} />);
    rerender(<SlidingNumber value={10} />);
    expect(container.querySelector("[aria-hidden]")!.children).toHaveLength(2);
    expect(screen.getByText("10")).toBeInTheDocument();
  });
});
