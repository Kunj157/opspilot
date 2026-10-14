import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Field } from "./field";
import { Checkbox, Input, Select, Textarea } from "./input";

describe("Field", () => {
  it("labels its control and shows the hint", () => {
    render(
      <Field label="Title" hint="Short and specific">
        {(c) => <Input {...c} />}
      </Field>,
    );
    const input = screen.getByRole("textbox", { name: "Title" });
    expect(input).toHaveAccessibleDescription("Short and specific");
    expect(input).not.toHaveAttribute("aria-invalid");
  });

  it("marks the control invalid and describes it with the error", () => {
    render(
      <Field label="Slug" error="Already taken" hint="Lowercase">
        {(c) => <Input {...c} />}
      </Field>,
    );
    const input = screen.getByRole("textbox", { name: "Slug" });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Already taken");
    expect(screen.queryByText("Lowercase")).not.toBeInTheDocument();
  });

  it("passes required through and shows a visual marker", () => {
    render(
      <Field label="Name" required>
        {(c) => <Input {...c} />}
      </Field>,
    );
    expect(screen.getByRole("textbox", { name: "Name" })).toBeRequired();
  });

  it("works with selects, textareas, and checkboxes", async () => {
    const user = userEvent.setup();
    render(
      <>
        <Field label="Severity">
          {(c) => (
            <Select {...c} defaultValue="low">
              <option value="low">Low</option>
              <option value="high">High</option>
            </Select>
          )}
        </Field>
        <Field label="Notes">{(c) => <Textarea {...c} />}</Field>
        <label>
          <Checkbox /> Mine
        </label>
      </>,
    );
    await user.selectOptions(screen.getByRole("combobox", { name: "Severity" }), "high");
    expect(screen.getByRole("combobox", { name: "Severity" })).toHaveValue("high");
    expect(screen.getByRole("textbox", { name: "Notes" })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Mine" }));
    expect(screen.getByRole("checkbox", { name: "Mine" })).toBeChecked();
  });
});
