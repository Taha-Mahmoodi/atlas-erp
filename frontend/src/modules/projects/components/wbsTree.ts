/**
 * Depth-first ordering of a flat WBS set (parent_id adjacency) for indented tree rendering —
 * shared by the WBS panel and the cost report. Siblings sort by code; a node whose parent is
 * missing from the set (defensive) is appended at depth 0 rather than dropped.
 */

export interface WbsNode {
  id: string;
  code: string;
  parent_id: string | null;
}

export function treeOrder<T extends WbsNode>(nodes: T[]): { node: T; depth: number }[] {
  const byParent = new Map<string | null, T[]>();
  for (const node of nodes) {
    const bucket = byParent.get(node.parent_id) ?? [];
    bucket.push(node);
    byParent.set(node.parent_id, bucket);
  }
  for (const bucket of byParent.values()) bucket.sort((a, b) => a.code.localeCompare(b.code));

  const ordered: { node: T; depth: number }[] = [];
  const walk = (parentId: string | null, depth: number) => {
    for (const node of byParent.get(parentId) ?? []) {
      ordered.push({ node, depth });
      walk(node.id, depth + 1);
    }
  };
  walk(null, 0);

  if (ordered.length < nodes.length) {
    const seen = new Set(ordered.map((entry) => entry.node.id));
    for (const node of nodes) if (!seen.has(node.id)) ordered.push({ node, depth: 0 });
  }
  return ordered;
}
