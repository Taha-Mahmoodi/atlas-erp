/**
 * Document-flow chain client (D-012) — the console half of `core/docflow_router.py`.
 *
 * Mirrors the backend's own split, and for the same reason `lib/jobs.ts` sits here: the
 * document registry is a cross-cutting platform concern owned by no business module, so
 * `/api/v1/documents/{id}/chain` has no module `api.ts` to live in. Keeping the registry
 * vocabulary (doc_type labels, doc_type → console route) here is also what lets
 * `components/DocFlowViewer` stay ERP-ignorant, as STRUCTURE §4 requires.
 */

import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

import type { DocFlowViewerProps } from "@/components/DocFlowViewer";
import { humanizeStatus } from "@/components/StatusPill";
import { api, getErrorMessage } from "@/lib/apiClient";

/** Mirrors backend `DocChainNode` (core/schemas.py), snake_case untranslated. */
export interface DocChainNode {
  document_id: string;
  doc_type: string;
  doc_id: string;
  doc_number: string | null;
  status: string | null;
}

/** Mirrors backend `DocChainEdge`. */
export interface DocChainEdge {
  predecessor_document_id: string;
  successor_document_id: string;
  link_type: string | null;
}

/** Mirrors backend `DocChainResponse`: the connected component around one document. */
export interface DocChain {
  nodes: DocChainNode[];
  edges: DocChainEdge[];
}

/**
 * `"sales.delivery"` → `"Sales delivery"`. Derived rather than tabled: a doc_type is already
 * `<module>.<snake_case_document>`, so the StatusPill humanizer does the whole job once the
 * dot is normalised to an underscore — and every module's types, including ones added later,
 * render without a map anyone has to remember to extend.
 */
export function docTypeLabel(docType: string): string {
  return humanizeStatus(docType.replaceAll(".", "_"));
}

/**
 * doc_type → the console route for its business row, for chain click-through. Only types whose
 * detail page actually exists are listed; a node of any other type still renders, it just
 * isn't a link. `finance.customer_credit_note` shares the customer-invoice page because a
 * credit note IS a `CustomerInvoice` row (finance/service/credit_notes.py).
 */
const DOC_ROUTES: Record<string, { to: string; param: string }> = {
  "sales.quote": { to: "/sales/quotes/$quoteId", param: "quoteId" },
  "sales.order": { to: "/sales/orders/$orderId", param: "orderId" },
  "sales.delivery": { to: "/sales/deliveries/$deliveryId", param: "deliveryId" },
  "sales.billing": { to: "/sales/billings/$billingId", param: "billingId" },
  "sales.return": { to: "/sales/returns/$returnId", param: "returnId" },
  "finance.customer_invoice": { to: "/finance/customer-invoices/$invoiceId", param: "invoiceId" },
  "finance.customer_credit_note": {
    to: "/finance/customer-invoices/$invoiceId",
    param: "invoiceId",
  },
  "finance.journal_entry": { to: "/finance/journal-entries/$entryId", param: "entryId" },
  "finance.vendor_bill": { to: "/finance/vendor-bills/$billId", param: "billId" },
  "inventory.stock_move": { to: "/inventory/stock-moves/$moveId", param: "moveId" },
  "procurement.purchase_order": {
    to: "/procurement/purchase-orders/$purchaseOrderId",
    param: "purchaseOrderId",
  },
  "procurement.goods_receipt": {
    to: "/procurement/goods-receipts/$goodsReceiptId",
    param: "goodsReceiptId",
  },
};

/** The chain around one document, mapped straight into `DocFlowViewer`'s props. Spread it:
 * `<DocFlowViewer {...useDocumentFlow(delivery.document_id)} />`. Node clicks navigate to the
 * clicked document's own detail page when one exists. Status tone is left to the viewer, which
 * resolves it through the canonical StatusPill table (issue #182).
 *
 * Fetch state is passed through rather than swallowed (#227): `queryClient`'s #180 rule only
 * escalates 4xx, so a 5xx or a dropped connection stays inline here — and collapsing that into
 * an empty chain would make the viewer state, in writing, that a document produced no
 * successors when the truth is that nobody asked successfully. `isLoading`, not `isPending`:
 * with no `documentId` the query is disabled and `isPending` never clears. */
export function useDocumentFlow(documentId: string | undefined): DocFlowViewerProps {
  const navigate = useNavigate();
  const chain = useQuery({
    queryKey: ["documents", documentId, "chain"],
    queryFn: () => api.get<DocChain>(`/documents/${documentId}/chain`),
    enabled: Boolean(documentId),
  });

  const chainNodes = chain.data?.nodes ?? [];
  return {
    nodes: chainNodes.map((node) => ({
      id: node.document_id,
      kind: docTypeLabel(node.doc_type),
      ...(node.doc_number ? { number: node.doc_number } : {}),
      ...(node.status ? { status: node.status } : {}),
    })),
    edges: (chain.data?.edges ?? []).map((edge) => ({
      from: edge.predecessor_document_id,
      to: edge.successor_document_id,
      ...(edge.link_type ? { label: humanizeStatus(edge.link_type).toLowerCase() } : {}),
    })),
    ...(documentId ? { currentId: documentId } : {}),
    loading: chain.isLoading,
    ...(chain.isError ? { error: getErrorMessage(chain.error, "Unable to load the document flow.") } : {}),
    onNodeClick: (clicked) => {
      const source = chainNodes.find((node) => node.document_id === clicked.id);
      const route = source ? DOC_ROUTES[source.doc_type] : undefined;
      if (!source || !route) return;
      void navigate({ to: route.to, params: { [route.param]: source.doc_id } });
    },
  };
}
