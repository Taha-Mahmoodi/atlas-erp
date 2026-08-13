import { describe, expect, it } from "vitest";

import { treeOrder } from "@/modules/projects/components/wbsTree";

describe("treeOrder", () => {
  it("orders depth-first by code with correct depths and keeps orphans", () => {
    const nodes = [
      { id: "b", code: "B", parent_id: null },
      { id: "a", code: "A", parent_id: null },
      { id: "a2", code: "A.2", parent_id: "a" },
      { id: "a1", code: "A.1", parent_id: "a" },
      { id: "a11", code: "A.1.1", parent_id: "a1" },
      { id: "orphan", code: "X", parent_id: "missing" },
    ];
    const ordered = treeOrder(nodes);
    expect(ordered.map((entry) => entry.node.id)).toEqual(["a", "a1", "a11", "a2", "b", "orphan"]);
    expect(ordered.map((entry) => entry.depth)).toEqual([0, 1, 2, 1, 0, 0]);
  });
});
