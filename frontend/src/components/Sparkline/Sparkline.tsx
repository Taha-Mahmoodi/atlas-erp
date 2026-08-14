/**
 * The trend line on a stat card (register §3): 76×22, accent stroke, no fill, no axes, no
 * library. Decorative by definition — the number beside it carries the meaning, so this is
 * `aria-hidden` and never the only place a value appears.
 *
 * Degenerate inputs are the normal case in an ERP (a brand-new tenant has one data point, a
 * flat month has identical ones), so they render as a deliberate centred flat line rather
 * than dividing by zero.
 */

export interface SparklineProps {
  /** Oldest → newest. Fewer than two points renders nothing. */
  points: number[];
  width?: number;
  height?: number;
  className?: string;
}

export function Sparkline({ points, width = 76, height = 22, className }: SparklineProps) {
  if (points.length < 2) return null;

  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min;
  const stroke = 1.8;
  // Inset by half the stroke so the line never clips at the top or bottom edge.
  const usable = height - stroke;

  const coords = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * width;
      // A flat series has no range to scale against — centre it instead of NaN.
      const ratio = span === 0 ? 0.5 : (value - min) / span;
      const y = stroke / 2 + (1 - ratio) * usable;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      style={{ flexShrink: 0, overflow: "visible" }}
    >
      <polyline
        points={coords}
        fill="none"
        stroke="currentColor"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
