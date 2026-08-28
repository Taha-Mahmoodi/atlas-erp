/**
 * #237: the functional-currency read is a money LABEL gated by `finance.fx.manage` — an admin
 * permission no read-only persona holds — so under the global throwOnError it took down every
 * page that formats money (a check, a stock valuation, a project, a maintenance order). The
 * guard lives in the hook because all 15 call sites want the same thing.
 */

import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/apiClient";
import { queryClient } from "@/lib/queryClient";
import { RouteErrorBoundary } from "@/components/ErrorState";
import { listCurrencies } from "@/modules/finance/api";
import { useFunctionalCurrency } from "@/modules/finance/hooks";

vi.mock("@/modules/finance/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/modules/finance/api")>()),
  listCurrencies: vi.fn(),
}));

/** Stands in for any of the 15 pages: a total, and the `?? "—"` fallback they all carry. */
function MoneyLabel() {
  const currency = useFunctionalCurrency();
  return (
    <p>
      Total 12.00 {currency.data ?? "—"}
      {currency.isError ? " (currency unavailable)" : ""}
    </p>
  );
}

afterEach(() => {
  queryClient.clear();
  vi.mocked(listCurrencies).mockReset();
});

describe("useFunctionalCurrency without finance.fx.manage", () => {
  it("leaves the page standing and degrades the label", async () => {
    vi.mocked(listCurrencies).mockRejectedValue(
      new ApiError(403, { code: "auth.forbidden", message: "Forbidden" }),
    );

    // The shared queryClient is used deliberately — its throwOnError default is the thing under
    // test, and this 403 used to replace the whole route with the error state.
    render(
      <QueryClientProvider client={queryClient}>
        <RouteErrorBoundary resetKey="/hospitality/tickets/tkt-1">
          <MoneyLabel />
        </RouteErrorBoundary>
      </QueryClientProvider>,
    );

    // Only rendered once the 403 has landed, and only if the boundary did not eat the page.
    expect(await screen.findByText(/Total 12.00 — \(currency unavailable\)/)).toBeInTheDocument();
  });
});
