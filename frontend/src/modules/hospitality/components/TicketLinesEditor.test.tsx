import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/apiClient";
import { queryClient } from "@/lib/queryClient";
import { RouteErrorBoundary } from "@/components/ErrorState";
import { listAvailability, listMenu } from "@/modules/hospitality/api";
import { TicketLinesEditor } from "@/modules/hospitality/components/TicketLinesEditor";
import type { OrderTicketLine } from "@/modules/hospitality/types";

// Only the two `menu.read` reads are faked — one permission gates both, so a persona test has to
// move them together. The rest of the module's api is untouched and never called here.
vi.mock("@/modules/hospitality/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/modules/hospitality/api")>()),
  listMenu: vi.fn(),
  listAvailability: vi.fn(),
}));

const forbidden = () =>
  Promise.reject(new ApiError(403, { code: "auth.forbidden", message: "Forbidden" }));

const line: OrderTicketLine = {
  id: "line-1",
  line_number: 1,
  item_id: "itm-1",
  quantity: "1",
  unit_price: "9.00",
  line_amount: "9.00",
  seat_number: null,
  notes: null,
};

function renderEditor(editable = false) {
  // The shared queryClient is used deliberately — its throwOnError default is the thing under
  // test in the 403 cases, and a 403 here used to replace the whole route with the error state.
  render(
    <QueryClientProvider client={queryClient}>
      <RouteErrorBoundary resetKey="/hospitality/tickets/tkt-1">
        <TicketLinesEditor ticketId="tkt-1" lines={[line]} currencyCode="USD" editable={editable} />
      </RouteErrorBoundary>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  queryClient.clear();
  vi.mocked(listMenu).mockReset();
  vi.mocked(listAvailability).mockReset();
});

describe("TicketLinesEditor without hospitality.menu.read", () => {
  it("still shows the check, with item ids for names", async () => {
    // The module's own persona split (docs §9): a server holds `ticket.*` and no `menu.*`. BOTH
    // reads 403 for them, and neither may take the check down.
    vi.mocked(listMenu).mockImplementation(forbidden);
    vi.mocked(listAvailability).mockImplementation(forbidden);

    renderEditor();

    expect(await screen.findByText(/cannot read the menu/)).toBeInTheDocument();
    expect(screen.getByText("itm-1")).toBeInTheDocument();
  });
});

describe("TicketLinesEditor dish picker (#208)", () => {
  it("offers priced dishes only, and disables an 86'd one with its reason", async () => {
    vi.mocked(listMenu).mockResolvedValue({
      items: [
        {
          item_id: "itm-1",
          item_code: "DISH-BURGER",
          name: "Cheeseburger",
          description: null,
          category_id: "cat-1",
          price: "9.00",
          currency_code: "USD",
        },
        {
          // The unfiltered menu read returns every ACTIVE item, ingredients included — honest for
          // the website, useless on a POS picker. No price list covers it, so it has no price.
          item_id: "itm-2",
          item_code: "ING-BUN",
          name: "Brioche Bun",
          description: null,
          category_id: "cat-2",
          price: null,
          currency_code: null,
        },
      ],
      next_cursor: null,
      limit: 200,
    });
    vi.mocked(listAvailability).mockResolvedValue({
      items: [
        {
          item_id: "itm-1",
          state: "EIGHTY_SIXED",
          remaining_qty: null,
          available_until: null,
          reason: "Out of cheese",
          source: "MANUAL",
        },
      ],
      next_cursor: null,
      limit: 200,
      as_of: "2026-08-17T18:00:00Z",
    });

    renderEditor(true);

    const dish = await screen.findByRole("option", { name: /Cheeseburger/ });
    expect(dish).toHaveTextContent("86'd: Out of cheese");
    expect(dish).toBeDisabled();
    expect(screen.queryByRole("option", { name: /Brioche Bun/ })).not.toBeInTheDocument();
  });
});
