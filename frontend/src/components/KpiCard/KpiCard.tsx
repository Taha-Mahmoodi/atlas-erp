/**
 * Dashboard tile (DESIGN.md): label, tabular value, optional delta whose color depends on
 * whether the direction is GOOD (AR aging going up is bad; sales going up is good — the
 * caller says which), skeleton loading, optional drill-through click.
 */

import type { ReactNode } from "react";

export interface KpiDelta {
  /** Preformatted display value, e.g. "+4.2%" or "−12,300.00 USD". */
  value: string;
  direction: "up" | "down" | "flat";
  /** Whether the movement is favorable — drives color, not direction. */
  positiveIsGood?: boolean;
}

export interface KpiCardProps {
  label: string;
  /** Preformatted (lib/format.ts) — this component never formats numbers. */
  value: string;
  secondary?: string;
  delta?: KpiDelta;
  loading?: boolean;
  onClick?: () => void;
  icon?: ReactNode;
}

const ARROW = { up: "↑", down: "↓", flat: "→" } as const;

function deltaColor(delta: KpiDelta): string {
  if (delta.direction === "flat") return "text-ink-muted";
  const favorable = (delta.direction === "up") === (delta.positiveIsGood ?? true);
  return favorable ? "text-success" : "text-danger";
}

export function KpiCard({ label, value, secondary, delta, loading, onClick, icon }: KpiCardProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-ink-muted">{label}</span>
        {icon && (
          <span aria-hidden="true" className="text-ink-faint">
            {icon}
          </span>
        )}
      </div>
      {loading ? (
        <span className="atlas-skeleton mt-2 inline-block h-7 w-28 text-2xl">…</span>
      ) : (
        <div className="mt-1.5 flex items-baseline gap-2">
          <span className="text-2xl font-semibold tabular-nums text-ink">{value}</span>
          {delta && (
            <span className={`text-xs font-medium tabular-nums ${deltaColor(delta)}`}>
              <span aria-hidden="true">{ARROW[delta.direction]} </span>
              {delta.value}
            </span>
          )}
        </div>
      )}
      {secondary && !loading && <p className="mt-1 text-xs text-ink-faint">{secondary}</p>}
    </>
  );

  const frame = "rounded-card border border-line bg-surface p-4 shadow-card";
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`${frame} block w-full text-left transition-colors duration-150 hover:border-primary`}
      >
        {body}
      </button>
    );
  }
  return <div className={frame}>{body}</div>;
}
