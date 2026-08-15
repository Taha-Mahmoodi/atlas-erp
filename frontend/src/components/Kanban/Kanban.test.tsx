import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Kanban, type KanbanColumn } from "./Kanban";

interface Card {
  id: string;
  title: string;
}

const columns: KanbanColumn<Card>[] = [
  { key: "new", title: "New", items: [{ id: "l1", title: "Lead one" }] },
  { key: "won", title: "Won", items: [] },
];

describe("Kanban", () => {
  it("renders columns with counts and a hint for empty columns", () => {
    render(
      <Kanban columns={columns} itemKey={(card) => card.id} renderItem={(card) => card.title} />,
    );
    expect(screen.getByRole("region", { name: "New" })).toBeInTheDocument();
    expect(screen.getByText("Lead one")).toBeInTheDocument();
    expect(screen.getByText("No items")).toBeInTheDocument();
  });

  it("moves an item between columns via the keyboard menu", async () => {
    const onItemMove = vi.fn();
    const user = userEvent.setup();
    render(
      <Kanban
        columns={columns}
        itemKey={(card) => card.id}
        renderItem={(card) => card.title}
        onItemMove={onItemMove}
      />,
    );
    await user.click(screen.getByRole("button", { name: /move l1/i }));
    await user.click(screen.getByRole("menuitem", { name: "Move to Won" }));
    expect(onItemMove).toHaveBeenCalledWith("l1", "new", "won");
  });

  it("moves an item via drag and drop", () => {
    const onItemMove = vi.fn();
    render(
      <Kanban
        columns={columns}
        itemKey={(card) => card.id}
        renderItem={(card) => card.title}
        onItemMove={onItemMove}
      />,
    );
    const card = screen.getByText("Lead one").closest("li");
    const target = screen.getByRole("region", { name: "Won" });
    const dataTransfer = {
      data: new Map<string, string>(),
      setData(type: string, value: string) {
        this.data.set(type, value);
      },
      getData(type: string) {
        return this.data.get(type) ?? "";
      },
      effectAllowed: "",
    };
    fireEvent.dragStart(card as HTMLElement, { dataTransfer });
    fireEvent.dragOver(target, { dataTransfer });
    fireEvent.drop(target, { dataTransfer });
    expect(onItemMove).toHaveBeenCalledWith("l1", "new", "won");
  });

  it("keeps headerExtra out of the section aria-label and the move menu (#163)", async () => {
    const user = userEvent.setup();
    render(
      <Kanban
        columns={[
          { key: "new", title: "New", items: [{ id: "l1", title: "Lead one" }] },
          { key: "won", title: "Won", headerExtra: "USD 60,000.00", items: [] },
        ]}
        itemKey={(card) => card.id}
        renderItem={(card) => card.title}
        onItemMove={vi.fn()}
      />,
    );
    expect(screen.getByText("USD 60,000.00")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Won" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /move l1/i }));
    expect(screen.getByRole("menuitem", { name: "Move to Won" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /60,000/ })).not.toBeInTheDocument();
  });

  it("labels the move button with itemLabel instead of the raw key (#163)", () => {
    render(
      <Kanban
        columns={columns}
        itemKey={(card) => card.id}
        itemLabel={(card) => card.title}
        renderItem={(card) => card.title}
        onItemMove={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Move Lead one to another column" }),
    ).toBeInTheDocument();
  });

  it("offers no move affordances when read-only", () => {
    render(
      <Kanban columns={columns} itemKey={(card) => card.id} renderItem={(card) => card.title} />,
    );
    expect(screen.queryByRole("button", { name: /move/i })).not.toBeInTheDocument();
  });
});
