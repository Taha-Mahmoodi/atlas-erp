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
    expect(screen.getByText("EXCEPTION")).toBeInTheDocument();
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
});
