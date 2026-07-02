import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { KpiCard } from "./KpiCard";

describe("KpiCard", () => {
  it("renders label, value and secondary text", () => {
    render(<KpiCard label="Cash position" value="1,204,000.00 USD" secondary="as of today" />);
    expect(screen.getByText("Cash position")).toBeInTheDocument();
    expect(screen.getByText("1,204,000.00 USD")).toBeInTheDocument();
    expect(screen.getByText("as of today")).toBeInTheDocument();
  });

  it("colors the delta by favorability, not direction", () => {
    const { rerender } = render(
      <KpiCard label="Sales" value="10" delta={{ value: "+5%", direction: "up", positiveIsGood: true }} />,
    );
    expect(screen.getByText("+5%")).toHaveClass("text-success");
    rerender(
      <KpiCard label="AR overdue" value="10" delta={{ value: "+5%", direction: "up", positiveIsGood: false }} />,
    );
    expect(screen.getByText("+5%")).toHaveClass("text-danger");
    rerender(<KpiCard label="WIP" value="10" delta={{ value: "0%", direction: "flat" }} />);
    expect(screen.getByText("0%")).toHaveClass("text-ink-muted");
  });

  it("swaps the value for a skeleton while loading", () => {
    render(<KpiCard label="Cash" value="99" loading />);
    expect(screen.queryByText("99")).not.toBeInTheDocument();
  });

  it("becomes a button when onClick is provided", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<KpiCard label="Open orders" value="12" onClick={onClick} />);
    await user.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
