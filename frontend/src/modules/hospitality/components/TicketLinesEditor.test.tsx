import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/apiClient";
import { queryClient } from "@/lib/queryClient";
import { RouteErrorBoundary } from "@/components/ErrorState";
import { TicketLinesEditor } from "@/modules/hospitality/components/TicketLinesEditor";
import type { OrderTicketLine } from "@/modules/hospitality/types";

// Only the menu read is faked; the rest of the module's api is untouched and never called here.
vi.mock("@/modules/hospitality/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/modules/hospitality/api")>()),
  listMenu: () =>
    Promise.reject(new ApiError(403, { code: "auth.forbidden", message: "Forbidden" })),
}));

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

afterEach(() => queryClient.clear());

describe("TicketLinesEditor without hospitality.menu.read", () => {
  it("still shows the check, with item ids for names", async () => {
    // The module's own persona split (HospitalityHomePage): a server holds `ticket.*` and no
    // `menu.*`. The shared queryClient is used deliberately — its throwOnError default is the
    // thing under test, and a 403 here used to replace the whole route with the error state.
    render(
      <QueryClientProvider client={queryClient}>
        <RouteErrorBoundary resetKey="/hospitality/tickets/tkt-1">
          <TicketLinesEditor ticketId="tkt-1" lines={[line]} currencyCode="USD" editable={false} />
        </RouteErrorBoundary>
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/cannot read the menu/)).toBeInTheDocument();
    expect(screen.getByText("itm-1")).toBeInTheDocument();
  });
});
