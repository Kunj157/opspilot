import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BorderTrail } from "./border-trail";
import { GlowEffect } from "./glow-effect";
import { Spotlight } from "./spotlight";

function prefersReducedMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduce && query.includes("reduce"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("motion effects", () => {
  it("shows the border trail only when motion is allowed", () => {
    prefersReducedMotion(false);
    const { unmount } = render(<BorderTrail />);
    expect(screen.getByTestId("border-trail")).toHaveAttribute("aria-hidden", "true");
    unmount();

    prefersReducedMotion(true);
    render(<BorderTrail />);
    expect(screen.queryByTestId("border-trail")).not.toBeInTheDocument();
  });

  it("lights the spotlight for a mouse but not under reduced motion", () => {
    prefersReducedMotion(false);
    const { unmount } = render(<Spotlight>Panel</Spotlight>);
    fireEvent.pointerMove(screen.getByText("Panel"), { pointerType: "mouse", clientX: 10, clientY: 10 });
    expect(screen.getByTestId("spotlight")).toBeInTheDocument();
    unmount();

    prefersReducedMotion(true);
    render(<Spotlight>Quiet</Spotlight>);
    fireEvent.pointerMove(screen.getByText("Quiet"), { pointerType: "mouse", clientX: 10, clientY: 10 });
    expect(screen.queryByTestId("spotlight")).not.toBeInTheDocument();
  });

  it("keeps decorative layers away from assistive technology", () => {
    const { container } = render(<GlowEffect tone="critical" breathing />);
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });
});
