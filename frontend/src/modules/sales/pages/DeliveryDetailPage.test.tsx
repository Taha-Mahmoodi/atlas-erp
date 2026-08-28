/**
 * Regression test for issue #227: DocFlowViewer was built, tested and mounted NOWHERE — no
 * route rendered it and no file called `GET /documents/{id}/chain`, so document flow (a
 * headline feature, CLAUDE.md architecture rule 2) had no UI surface at all and the component
 * was tree-shaken out of the bundle. This test fails without the mount: it asserts the delivery
 * workbench fetches its own chain and renders the neighbouring documents, click-through
 * included.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { DeliveryDetail } from "@/modules/sales/types";

const navigate = vi.fn();
const apiGet = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  useParams: () => ({ deliveryId: "delivery-row-1" }),
  useNavigate: () => navigate,
  Link: ({ children }: { children: ReactNode }) => <a href="#">{children}</a>,
}));

vi.mock("@/lib/apiClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/apiClient")>()),
  api: { get: (path: string) => apiGet(path) },
}));

vi.mock("@/lib/session", () => ({ useMe: () => ({ data: { permissions: [] } }) }));

const emptyList = { data: { items: [] } };
vi.mock("@/modules/inventory/hooks", () => ({
  useItemLookup: () => emptyList,
  useBinLookup: () => emptyList,
  useWarehouseLookup: () => emptyList,
}));

const delivery: DeliveryDetail = {
  id: "delivery-row-1",
  delivery_number: "DLV-00007",
  status: "POSTED",
  sales_order_id: "order-row-1",
  customer_id: "customer-1",
  warehouse_id: "warehouse-1",
  delivery_date: "2026-08-01",
  shipping_address: null,
  notes: null,
  posted_at: "2026-08-01T09:00:00",
  document_id: "doc-delivery",
  created_at: "",
  updated_at: "",
  lines: [],
};

vi.mock("@/modules/sales/hooks", () => ({
  useDelivery: () => ({ isPending: false, data: delivery }),
  useCustomerOptions: () => emptyList,
  usePostDelivery: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useCancelDelivery: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));

// Imported after the mocks so the page picks them up.
const { DeliveryDetailPage } = await import("./DeliveryDetailPage");

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DeliveryDetailPage />
    </QueryClientProvider>,
  );
}

describe("DeliveryDetailPage document flow (issue #227)", () => {
  it("renders the delivery's chain and navigates to a clicked document", async () => {
    apiGet.mockResolvedValue({
      nodes: [
        {
          document_id: "doc-order",
          doc_type: "sales.order",
          doc_id: "order-row-1",
          doc_number: "SO-00042",
          status: "PARTIALLY_DELIVERED",
        },
        {
          document_id: "doc-delivery",
          doc_type: "sales.delivery",
          doc_id: "delivery-row-1",
          doc_number: "DLV-00007",
          status: "POSTED",
        },
      ],
      edges: [
        {
          predecessor_document_id: "doc-order",
          successor_document_id: "doc-delivery",
          link_type: "delivered_by",
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("SO-00042")).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith("/documents/doc-delivery/chain");
    // The predecessor's own kind and status render, and the delivery is the anchored node.
    const chain = within(screen.getByRole("group", { name: "Document flow" }));
    expect(chain.getByText("Sales order")).toBeInTheDocument();
    expect(chain.getByText("Partially delivered")).toBeInTheDocument();
    expect(chain.getByText("DLV-00007").closest("li")).toHaveAttribute("aria-current", "true");

    await userEvent.click(screen.getByText("SO-00042"));
    expect(navigate).toHaveBeenCalledWith({
      to: "/sales/orders/$orderId",
      params: { orderId: "order-row-1" },
    });
  });
});
