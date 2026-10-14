import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActiveHighlight } from "./animated-background";
import { InView } from "./in-view";
import { MotionScope } from "./motion-provider";
import { TextShimmer } from "./text-shimmer";
import { TransitionPanel } from "./transition-panel";

describe("motion content primitives", () => {
  it("renders text and panels as real content inside the motion root", () => {
    render(
      <MotionScope>
        <TextShimmer>Investigating</TextShimmer>
        <InView>Revealed</InView>
        <TransitionPanel activeKey="logs">Log panel</TransitionPanel>
        <span className="relative">
          <ActiveHighlight layoutId="tab" />
          Selected
        </span>
      </MotionScope>,
    );
    expect(screen.getByText("Investigating")).toHaveClass("text-shimmer");
    expect(screen.getByText("Revealed")).toBeInTheDocument();
    expect(screen.getByText("Log panel")).toBeInTheDocument();
    expect(screen.getByText("Selected").querySelector("[aria-hidden]")).toBeInTheDocument();
  });
});
