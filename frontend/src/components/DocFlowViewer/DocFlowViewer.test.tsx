import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { computeLevels, DocFlowViewer, type DocFlowEdge, type DocFlowNode } from "./DocFlowViewer";

const nodes: DocFlowNode[] = [
  { id: "po", kind: "Purchase order", number: "PO-001", status: "RECEIVED", statusTone: "success" },
  { id: "gr", kind: "Goods receipt", number: "GR-001", status: "POSTED", statusTone: "success" },
  { id: "match", kind: "Invoice match", number: "MATCH-001", status: "EXCEPTION", statusTone: "danger" },
];
const edges: DocFlowEdge[] = [
  { from: "po", to: "gr", label: "received_by" },
  { from: "gr", to: "match", label: "matched_by" },
];

describe("computeLevels", () => {
  it("levels a chain from its roots by longest path", () => {
    const levels = computeLevels(nodes, edges);
    expect(levels.get("po")).toBe(0);
    expect(levels.get("gr")).toBe(1);
    expect(levels.get("match")).toBe(2);
  });

  it("puts a diamond's join after its deepest parent", () => {
    // a → b → c and a → c directly: c must sit after b (level 2), not beside it.
    const diamond: DocFlowNode[] = ["a", "b", "c"].map((id) => ({ id, kind: id }));
    const levels = computeLevels(diamond, [
      { from: "a", to: "b" },
      { from: "b", to: "c" },
      { from: "a", to: "c" },
    ]);
    expect(levels.get("b")).toBe(1);
    expect(levels.get("c")).toBe(2);
  });

  it("terminates on a cycle instead of hanging", () => {
    const pair: DocFlowNode[] = ["x", "y"].map((id) => ({ id, kind: id }));
    const levels = computeLevels(pair, [
      { from: "x", to: "y" },
      { from: "y", to: "x" },
    ]);
    expect(levels.size).toBe(2);
  });
});

describe("DocFlowViewer", () => {
  it("renders nodes with statuses and inbound edge labels", () => {
    render(<DocFlowViewer nodes={nodes} edges={edges} />);
    expect(screen.getByText("PO-001")).toBeInTheDocument();
    // Statuses render through the shared StatusPill now (issue #182), which humanizes the
    // backend literal rather than shouting it: EXCEPTION → "Exception".
    expect(screen.getByText("Exception")).toBeInTheDocument();
    expect(screen.getByText(/received_by · from PO-001/)).toBeInTheDocument();
  });

  it("anchors the current node and reports clicks", async () => {
    const onNodeClick = vi.fn();
    const user = userEvent.setup();
    render(<DocFlowViewer nodes={nodes} edges={edges} currentId="gr" onNodeClick={onNodeClick} />);
    expect(screen.getByText("GR-001").closest("li")).toHaveAttribute("aria-current", "true");
    await user.click(screen.getByText("MATCH-001"));
    expect(onNodeClick).toHaveBeenCalledWith(nodes[2]);
  });

  it("teaches on the empty state", () => {
    render(<DocFlowViewer nodes={[]} edges={[]} />);
    expect(screen.getByText(/flow builds as this document is processed/i)).toBeInTheDocument();
  });

  // Issue #182 via #227: an omitted statusTone must fall through to the canonical word→tone
  // table, not to a forced grey. PARTIALLY_DELIVERED is `warn` there, so the pill must carry
  // the warn tint — under the old `tone: "mute"` fallback it renders the dashed mute outline
  // and this fails.
  it("resolves an omitted statusTone through the canonical StatusPill table", () => {
    render(
      <DocFlowViewer
        nodes={[{ id: "so", kind: "Sales order", number: "SO-1", status: "PARTIALLY_DELIVERED" }]}
        edges={[]}
      />,
    );
    const pill = screen.getByText("Partially delivered");
    expect(pill).toHaveClass("bg-warn-tint", "text-warn");
    expect(pill).not.toHaveClass("border-dashed");
  });

  // Issue #227: an audit trail must not answer "this document produced nothing" when the
  // request is still in flight or failed — both used to collapse into the empty state.
  it("shows loading and failure instead of the empty sentence", () => {
    const { rerender } = render(<DocFlowViewer nodes={[]} edges={[]} loading />);
    expect(screen.queryByText(/flow builds as this document is processed/i)).not.toBeInTheDocument();
    expect(screen.getByText("Loading…")).toBeInTheDocument();

    rerender(<DocFlowViewer nodes={[]} edges={[]} error="Unable to load the document flow." />);
    expect(screen.queryByText(/flow builds as this document is processed/i)).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load the document flow.");
  });
});
