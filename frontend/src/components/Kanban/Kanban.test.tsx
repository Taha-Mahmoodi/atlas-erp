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

  it("offers no move affordances when read-only", () => {
    render(
      <Kanban columns={columns} itemKey={(card) => card.id} renderItem={(card) => card.title} />,
    );
    expect(screen.queryByRole("button", { name: /move/i })).not.toBeInTheDocument();
  });
});
