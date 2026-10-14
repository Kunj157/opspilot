import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Card } from "./card";

function mockReducedMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduce && query.includes("reduce"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

function pointAt(element: HTMLElement, x: number, y: number) {
  element.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 100 }) as DOMRect;
  fireEvent.pointerMove(element, { clientX: x, clientY: y });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Card", () => {
  it("tilts toward the pointer by at most four degrees and resets on leave", () => {
    mockReducedMotion(false);
    render(
      <Card tilt data-testid="card">
        Body
      </Card>,
    );
    const card = screen.getByTestId("card");

    pointAt(card, 200, 0);
    expect(card.style.transform).toBe("perspective(800px) rotateX(4deg) rotateY(4deg)");

    fireEvent.pointerLeave(card);
    expect(card.style.transform).toBe("");
  });

  it("does not tilt when the user prefers reduced motion", () => {
    mockReducedMotion(true);
    render(
      <Card tilt data-testid="card">
        Body
      </Card>,
    );
    const card = screen.getByTestId("card");

    pointAt(card, 200, 0);

    expect(card.style.transform).toBe("");
  });

  it("renders as another element when asked", () => {
    mockReducedMotion(false);
    render(
      <Card as="section" aria-label="Summary">
        Body
      </Card>,
    );

    expect(screen.getByRole("region", { name: "Summary" })).toHaveTextContent("Body");
  });
});
