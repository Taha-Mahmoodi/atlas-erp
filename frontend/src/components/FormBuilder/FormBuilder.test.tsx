import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FormBuilder, type FieldDef } from "./FormBuilder";

const fields: FieldDef[] = [
  { name: "code", label: "Code", type: "text", required: true },
  { name: "amount", label: "Amount", type: "number", step: "0.01" },
  { name: "currency", label: "Currency", type: "select", options: [{ value: "USD", label: "USD" }] },
  { name: "active", label: "Active", type: "checkbox" },
];

describe("FormBuilder", () => {
  it("renders every field type with its label wired to the control", () => {
    render(
      <FormBuilder fields={fields} values={{}} onChange={vi.fn()} onSubmit={vi.fn()} />,
    );
    expect(screen.getByLabelText(/code/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Amount")).toHaveAttribute("type", "number");
    expect(screen.getByLabelText("Currency")).toBeInstanceOf(HTMLSelectElement);
    expect(screen.getByLabelText("Active")).toHaveAttribute("type", "checkbox");
  });

  it("reports typing and checkbox toggles through onChange", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<FormBuilder fields={fields} values={{}} onChange={onChange} onSubmit={vi.fn()} />);
    await user.type(screen.getByLabelText(/code/i), "A");
    expect(onChange).toHaveBeenCalledWith("code", "A");
    await user.click(screen.getByLabelText("Active"));
    expect(onChange).toHaveBeenCalledWith("active", true);
  });

  it("submits via the button and never while busy", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <FormBuilder fields={fields} values={{ code: "A" }} onChange={vi.fn()} onSubmit={onSubmit} />,
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onSubmit).toHaveBeenCalledOnce();
    rerender(
      <FormBuilder fields={fields} values={{ code: "A" }} onChange={vi.fn()} onSubmit={onSubmit} busy />,
    );
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByLabelText(/code/i)).toBeDisabled();
  });

  it("wires errors as alerts with aria-invalid and described-by", () => {
    render(
      <FormBuilder
        fields={fields}
        values={{}}
        errors={{ code: "Code is required" }}
        onChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    const input = screen.getByLabelText(/code/i);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Code is required");
    expect(input).toHaveAttribute("aria-describedby", "field-code-error");
  });

  it("blocks submit on an empty required field and names it under the control", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<FormBuilder fields={fields} values={{}} onChange={vi.fn()} onSubmit={onSubmit} />);

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Code is required.");
    const input = screen.getByLabelText(/code/i);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby", "field-code-error");
    // The first offending field takes focus so a keyboard user lands on the thing to fix.
    expect(input).toHaveFocus();
  });

  it("clears the required message as soon as the field changes", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<FormBuilder fields={fields} values={{}} onChange={vi.fn()} onSubmit={onSubmit} />);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Code is required.");

    await user.type(screen.getByLabelText(/code/i), "A");

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("lets a caller-supplied error win over the client-side required message", async () => {
    const user = userEvent.setup();
    render(
      <FormBuilder
        fields={fields}
        values={{}}
        errors={{ code: "Code is already taken." }}
        onChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Code is already taken.");
  });

  it("never blocks on a disabled required field or an unchecked required checkbox", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <FormBuilder
        fields={[
          // An edit form's immutable key: required, disabled, and still loading its value.
          { name: "code", label: "Code", type: "text", required: true, disabled: true },
          { name: "active", label: "Active", type: "checkbox", required: true },
        ]}
        values={{}}
        onChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("marks required controls required for assistive tech, checkboxes excepted", () => {
    render(
      <FormBuilder
        fields={[
          { name: "code", label: "Code", type: "text", required: true },
          { name: "notes", label: "Notes", type: "textarea", required: true },
          { name: "active", label: "Active", type: "checkbox", required: true },
        ]}
        values={{}}
        onChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByLabelText(/code/i)).toBeRequired();
    expect(screen.getByLabelText(/notes/i)).toBeRequired();
    expect(screen.getByLabelText("Active")).not.toBeRequired();
  });
});
