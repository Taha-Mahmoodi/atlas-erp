import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DataGrid, type DataGridColumn } from "./DataGrid";

interface Row {
  id: string;
  name: string;
  amount: string;
}

const columns: DataGridColumn<Row>[] = [
  { key: "name", header: "Name", render: (row) => row.name, sortable: true },
  { key: "amount", header: "Amount", render: (row) => row.amount, align: "right" },
];
const rows: Row[] = [
  { id: "1", name: "Alpha", amount: "100.00" },
  { id: "2", name: "Beta", amount: "250.00" },
];

describe("DataGrid", () => {
  it("renders rows and right-aligns numeric columns", () => {
    render(<DataGrid columns={columns} rows={rows} rowKey={(row) => row.id} label="Items" />);
    expect(screen.getByRole("table", { name: "Items" })).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("250.00")).toHaveClass("text-right");
  });

  it("reports sort toggles through onSortChange with asc/desc cycling", async () => {
    const onSortChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <DataGrid columns={columns} rows={rows} rowKey={(row) => row.id} onSortChange={onSortChange} />,
    );
    await user.click(screen.getByRole("button", { name: /name/i }));
    expect(onSortChange).toHaveBeenLastCalledWith({ key: "name", direction: "asc" });
    rerender(
      <DataGrid
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        sort={{ key: "name", direction: "asc" }}
        onSortChange={onSortChange}
      />,
    );
    expect(screen.getByRole("columnheader", { name: /name/i })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    await user.click(screen.getByRole("button", { name: /name/i }));
    expect(onSortChange).toHaveBeenLastCalledWith({ key: "name", direction: "desc" });
  });

  it("fires onRowClick from mouse and keyboard", async () => {
    const onRowClick = vi.fn();
    const user = userEvent.setup();
    render(
      <DataGrid columns={columns} rows={rows} rowKey={(row) => row.id} onRowClick={onRowClick} />,
    );
    await user.click(screen.getByText("Alpha"));
    expect(onRowClick).toHaveBeenCalledWith(rows[0]);
    screen.getAllByRole("button").at(-1)?.focus();
    await user.keyboard("{Enter}");
    expect(onRowClick).toHaveBeenCalledWith(rows[1]);
  });

  it("shows the teaching empty state only when not loading", () => {
    const { rerender } = render(
      <DataGrid columns={columns} rows={[]} rowKey={(row: Row) => row.id} emptyMessage="Post your first journal" />,
    );
    expect(screen.getByText("Post your first journal")).toBeInTheDocument();
    rerender(<DataGrid columns={columns} rows={[]} rowKey={(row: Row) => row.id} loading />);
    expect(screen.queryByText("Post your first journal")).not.toBeInTheDocument();
  });

  it("renders load-more when a next cursor exists and disables it while loading more", async () => {
    const onLoadMore = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <DataGrid columns={columns} rows={rows} rowKey={(row) => row.id} hasMore onLoadMore={onLoadMore} />,
    );
    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(onLoadMore).toHaveBeenCalledOnce();
    rerender(
      <DataGrid columns={columns} rows={rows} rowKey={(row) => row.id} hasMore onLoadMore={onLoadMore} loadingMore />,
    );
    expect(screen.getByRole("button", { name: "Loading…" })).toBeDisabled();
  });
});
