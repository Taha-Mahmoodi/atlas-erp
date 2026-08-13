import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { JournalLinesEditor } from "./JournalLinesEditor";
import type { WbsElement } from "@/modules/projects/types";

const wbs: WbsElement = {
  id: "wbs-1",
  project_id: "prj-1",
  code: "PRJ-1.1",
  name: "Foundations",
  parent_id: null,
  status: "OPEN",
  is_billable: true,
  budget_amount: null,
  created_at: "",
  updated_at: "",
};

const line = { account_id: "", transaction_debit_amount: "", transaction_credit_amount: "" };

describe("JournalLinesEditor WBS picker (issue #162)", () => {
  it("tags the line's project_id with the chosen WBS element", async () => {
    const onChange = vi.fn();
    render(<JournalLinesEditor lines={[line]} accounts={[]} wbsElements={[wbs]} onChange={onChange} />);

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "WBS element" }), "wbs-1");
    expect(onChange).toHaveBeenLastCalledWith([{ ...line, project_id: "wbs-1" }]);
  });

  it("clears the dimension back to null when None is re-selected", async () => {
    const onChange = vi.fn();
    render(
      <JournalLinesEditor lines={[{ ...line, project_id: "wbs-1" }]} accounts={[]} wbsElements={[wbs]} onChange={onChange} />,
    );

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "WBS element" }), "");
    expect(onChange).toHaveBeenLastCalledWith([{ ...line, project_id: null }]);
  });

  it("disables the picker when no WBS options are available", () => {
    render(<JournalLinesEditor lines={[line]} accounts={[]} wbsElements={[]} onChange={vi.fn()} />);
    expect(screen.getByRole("combobox", { name: "WBS element" })).toBeDisabled();
  });
});
