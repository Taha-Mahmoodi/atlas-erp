/**
 * Dashboard stat card, porcelain register §3: mono-caps label with an optional sparkline on
 * the same row, a 26px tabular value, and a delta whose colour depends on whether the
 * direction is GOOD (AR aging going up is bad; sales going up is good — the caller says
 * which), not on which way the arrow points.
 */

import type { ReactNode } from "react";

import { Sparkline } from "@/components/Sparkline";

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
  /** Oldest → newest. Renders the register's 76×22 accent trend line beside the label. */
  trend?: number[];
}

const ARROW = { up: "↑", down: "↓", flat: "→" } as const;

function deltaColor(delta: KpiDelta): string {
  if (delta.direction === "flat") return "text-ink-muted";
  const favorable = (delta.direction === "up") === (delta.positiveIsGood ?? true);
  return favorable ? "text-success" : "text-danger";
}

export function KpiCard({
  label,
  value,
  secondary,
  delta,
  loading,
  onClick,
  icon,
  trend,
}: KpiCardProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-3">
        <span className="mono-caps text-ink-muted">{label}</span>
        {trend && trend.length > 1 ? (
          <span className="text-primary">
            <Sparkline points={trend} />
          </span>
        ) : (
          icon && (
            <span aria-hidden="true" className="text-ink-muted">
              {icon}
            </span>
          )
        )}
      </div>
      {loading ? (
        <span className="atlas-skeleton mt-2.5 inline-block h-8 w-28 text-[26px]">…</span>
      ) : (
        <div className="mt-2 flex items-baseline gap-2">
          {/* The register's stat value is 26px, which fits a 240px card up to about 14
              characters. Real ERP money runs longer than that ("USD 12,345,678.00"), so long
              values step down rather than bleeding past the card edge. */}
          <span
            className={`font-[650] leading-8 tracking-[-0.01em] tabular-nums text-ink ${
              value.length > 14 ? "text-[21px]" : "text-[26px]"
            }`}
          >
            {value}
          </span>
        </div>
      )}
      {(delta || secondary) && !loading && (
        <p className="mt-1.5 flex items-center gap-1.5 text-[11.5px] text-ink-muted">
          {delta && (
            <span className={`font-medium tabular-nums ${deltaColor(delta)}`}>
              <span aria-hidden="true">{ARROW[delta.direction]} </span>
              {delta.value}
            </span>
          )}
          {secondary}
        </p>
      )}
    </>
  );

  const frame = "rounded-card border border-line bg-surface px-[18px] py-4 shadow-card";
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
