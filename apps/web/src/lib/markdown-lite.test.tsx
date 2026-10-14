import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarkdownLite } from "./markdown-lite";

describe("MarkdownLite", () => {
  it("renders paragraphs, bullet and numbered lists, code, and bold", () => {
    render(
      <MarkdownLite
        text={[
          "Check **checkout** first.",
          "",
          "- `kubectl -n demo get pods`",
          "- read the logs",
          "",
          "1. Roll back.",
          "2. Verify.",
        ].join("\n")}
      />,
    );

    expect(screen.getByText("checkout", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("kubectl -n demo get pods", { selector: "code" })).toBeInTheDocument();
    const [bullets, steps] = screen.getAllByRole("list");
    expect(bullets.tagName).toBe("UL");
    expect(steps.tagName).toBe("OL");
    expect(steps.children).toHaveLength(2);
  });

  it("joins wrapped list items and never renders raw html", () => {
    render(<MarkdownLite text={"- first line\n  continues here\n- <img src=x onerror=alert(1)>"} />);

    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("first line continues here");
    expect(items[1]).toHaveTextContent("<img src=x onerror=alert(1)>");
    expect(document.querySelector("img")).toBeNull();
  });
});
