import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { queryClient } from "@/lib/queryClient";
import { TicketDetailPage } from "@/modules/hospitality/pages/TicketDetailPage";
import type { OrderTicket, OrderTicketLine } from "@/modules/hospitality/types";

// The page is rendered outside a router, so only the two router bindings it uses are stubbed.
vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ ticketId: "tkt-1" }),
  Link: ({ children }: { children: ReactNode }) => <a href="#">{children}</a>,
}));

const ticket: OrderTicket = {
  id: "tkt-1",
  document_id: "doc-1",
  ticket_number: "TKT-2026-0007",
  status: "SERVED",
  opened_date: "2026-08-28",
  table_code: "12",
  guest_count: 4,
  fired_at: null,
  settled_at: null,
  cancelled_at: null,
  cancel_reason: null,
  total_amount: "42.00",
  notes: null,
};

const line: OrderTicketLine = {
  id: "line-1",
  line_number: 1,
  item_id: "itm-1",
  quantity: "2",
  unit_price: "21.00",
  line_amount: "42.00",
  seat_number: 1,
  notes: null,
};

afterEach(() => queryClient.clear());

/** Every read the page makes, served from the cache — no network, no api mocks. */
function seed(): void {
  queryClient.setQueryData(["auth", "me"], {
    id: "usr-1",
    tenant_id: "ten-1",
    tenant_name: "Kintsugi Hall",
    email: "server@kintsugi.test",
    full_name: null,
    permissions: [],
  });
  queryClient.setQueryData(["hospitality", "ticket", "tkt-1"], ticket);
  queryClient.setQueryData(["hospitality", "ticket-lines", "tkt-1"], [line]);
  queryClient.setQueryData(["hospitality", "menu"], { items: [], next_cursor: null });
  queryClient.setQueryData(["hospitality", "availability"], {
    pages: [{ items: [], next_cursor: null, as_of: "2026-08-28T00:00:00Z" }],
    pageParams: [undefined],
  });
  queryClient.setQueryData(["finance", "currencies", "functional"], {
    items: [{ code: "USD", is_functional: true }],
    next_cursor: null,
  });
}

describe("TicketDetailPage as printed paper (#211)", () => {
  it("prints the check as a receipt with the property's name on it", () => {
    seed();
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <TicketDetailPage />
      </QueryClientProvider>,
    );

    // The letterhead: on screen the shell says which property this is, on paper nothing does.
    expect(screen.getByText("Kintsugi Hall")).toBeInTheDocument();
    // The print stylesheet keys the receipt column off this value; plain `data-print-region`
    // prints a full-width report instead.
    expect(container.querySelector('[data-print-region="receipt"]')).not.toBeNull();

    // What has to survive onto the paper (#211): number, table, covers, service date, the lines
    // with quantities and prices, and a total that says it is pre-tax.
    expect(screen.getAllByText("TKT-2026-0007").length).toBeGreaterThan(0);
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Total (pre-tax)")).toBeInTheDocument();
    // Twice: the line's amount and the check's total.
    expect(screen.getAllByText("USD 42.00")).toHaveLength(2);
  });
});
