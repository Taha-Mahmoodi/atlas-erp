/**
 * Document-flow chain viewer (D-012, DESIGN.md): predecessor→successor edges rendered as
 * left→right LEVELS (roots first), status-chipped nodes, edge labels on the receiving node,
 * current-node highlight, node click. Pure layout from (nodes, edges) — no ERP semantics;
 * the caller maps document types/statuses to labels and tones.
 */

import { StatusPill, type StatusTone } from "@/components/StatusPill";

export interface DocFlowNode {
  id: string;
  /** Display heading, e.g. "Sales order". */
  kind: string;
  /** Document number, e.g. "SO-00042". */
  number?: string;
  status?: string;
  statusTone?: "neutral" | "success" | "warn" | "danger";
  meta?: string;
}

export interface DocFlowEdge {
  from: string;
  to: string;
  /** Link type, e.g. "delivered_by" — shown on the successor. */
  label?: string;
}

export interface DocFlowViewerProps {
  nodes: DocFlowNode[];
  edges: DocFlowEdge[];
  /** The document whose page we're on — visually anchored. */
  currentId?: string;
  onNodeClick?: (node: DocFlowNode) => void;
}

/** The viewer's caller-facing tone vocabulary, mapped onto the shared pill's (issue #182). */
const TONE: Record<NonNullable<DocFlowNode["statusTone"]>, StatusTone> = {
  neutral: "mute",
  success: "ok",
  warn: "warn",
  danger: "bad",
};

/** Longest-path level per node: roots at 0, every edge pushes its successor deeper. */
export function computeLevels(nodes: DocFlowNode[], edges: DocFlowEdge[]): Map<string, number> {
  const levels = new Map<string, number>();
  const ids = new Set(nodes.map((node) => node.id));
  const targets = new Set(edges.map((edge) => edge.to));
  for (const node of nodes) if (!targets.has(node.id)) levels.set(node.id, 0);
  if (levels.size === 0 && nodes[0]) levels.set(nodes[0].id, 0); // cycle fallback: anchor one
  // Relaxation, bounded by node count — a document chain is tiny.
  for (let pass = 0; pass < nodes.length; pass += 1) {
    let changed = false;
    for (const edge of edges) {
      if (!ids.has(edge.from) || !ids.has(edge.to)) continue;
      const from = levels.get(edge.from);
      if (from === undefined) continue;
      const proposed = from + 1;
      if ((levels.get(edge.to) ?? -1) < proposed) {
        levels.set(edge.to, proposed);
        changed = true;
      }
    }
    if (!changed) break;
  }
  for (const node of nodes) if (!levels.has(node.id)) levels.set(node.id, 0);
  return levels;
}

export function DocFlowViewer({ nodes, edges, currentId, onNodeClick }: DocFlowViewerProps) {
  if (nodes.length === 0) {
    return (
      <p className="rounded-card border border-dashed border-line p-6 text-center text-sm text-ink-muted">
        No linked documents yet — the flow builds as this document is processed.
      </p>
    );
  }
  const levels = computeLevels(nodes, edges);
  const depth = Math.max(...levels.values());
  const columns = Array.from({ length: depth + 1 }, (_, level) =>
    nodes.filter((node) => levels.get(node.id) === level),
  );
  const inbound = new Map<string, DocFlowEdge[]>();
  for (const edge of edges) {
    inbound.set(edge.to, [...(inbound.get(edge.to) ?? []), edge]);
  }
  const numberOf = (id: string) => nodes.find((node) => node.id === id)?.number ?? id;

  return (
    <div className="flex items-start gap-2 overflow-x-auto pb-2" role="group" aria-label="Document flow">
      {columns.map((column, level) => (
        <div key={level} className="flex items-center gap-2">
          {level > 0 && (
            <span aria-hidden="true" className="mt-6 shrink-0 text-lg text-ink-faint">
              →
            </span>
          )}
          <ol className="flex w-52 shrink-0 flex-col gap-2">
            {column.map((node) => {
              const isCurrent = node.id === currentId;
              const links = inbound.get(node.id) ?? [];
              const frame = `w-full rounded-card border bg-surface p-3 text-left shadow-card transition-colors duration-150 ${
                isCurrent ? "border-primary ring-1 ring-primary" : "border-line"
              } ${onNodeClick ? "hover:border-primary" : ""}`;
              const body = (
                <>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-ink-muted">{node.kind}</span>
                    {node.status && <StatusPill status={node.status} tone={TONE[node.statusTone ?? "neutral"]} />}
                  </div>
                  <div className="mt-0.5 text-sm font-semibold text-ink">{node.number ?? node.id}</div>
                  {node.meta && <div className="mt-0.5 text-xs text-ink-faint">{node.meta}</div>}
                  {links.map((edge) => (
                    <div key={`${edge.from}-${edge.label ?? ""}`} className="mt-1 text-[11px] text-ink-faint">
                      {edge.label ? `${edge.label} · ` : ""}from {numberOf(edge.from)}
                    </div>
                  ))}
                </>
              );
              return (
                <li key={node.id} {...(isCurrent ? { "aria-current": "true" as const } : {})}>
                  {onNodeClick ? (
                    <button type="button" onClick={() => onNodeClick(node)} className={frame}>
                      {body}
                    </button>
                  ) : (
                    <div className={frame}>{body}</div>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      ))}
    </div>
  );
}
