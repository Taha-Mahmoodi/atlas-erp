/**
 * The icon set, as one inline SVG sprite (DESIGN.md / PRINCIPLES §7 "own every asset" — no
 * icon-font, no CDN, no runtime dependency). `IconSprite` mounts once at the app root and the
 * `Icon` component references symbols out of it, so N icons on screen cost one definition each.
 *
 * Geometry is uniform on purpose: 24×24 viewBox, stroke-only, 1.7px stroke, round caps and
 * joins (register §3). Adding an icon means adding one symbol below and one key to `IconName`.
 */

export type IconName =
  | "home"
  | "dollar"
  | "box"
  | "cart"
  | "tag"
  | "factory"
  | "shield-check"
  | "wrench"
  | "users"
  | "layers"
  | "spark"
  | "chart"
  | "gear"
  | "search"
  | "plus"
  | "bell"
  | "chevron-down"
  | "chevron-right"
  | "sun"
  | "moon"
  | "monitor"
  | "menu"
  | "close"
  | "alert"
  | "arrow-left"
  | "file"
  | "help"
  | "sign-out";

/** One <symbol> per name. Kept terse — these are drawings, not logic. */
export function IconSprite() {
  return (
    <svg aria-hidden="true" style={{ display: "none" }}>
      <symbol id="atlas-home" viewBox="0 0 24 24">
        <rect x="3.5" y="3.5" width="7" height="7" rx="1.6" />
        <rect x="13.5" y="3.5" width="7" height="7" rx="1.6" />
        <rect x="3.5" y="13.5" width="7" height="7" rx="1.6" />
        <rect x="13.5" y="13.5" width="7" height="7" rx="1.6" />
      </symbol>
      <symbol id="atlas-dollar" viewBox="0 0 24 24">
        <path d="M12 2.5v19M16.5 6.5c0-1.7-2-3-4.5-3s-4.5 1.3-4.5 3 1.6 2.6 4.5 3.2c3.1.6 4.8 1.7 4.8 3.6 0 1.9-2.1 3.2-4.8 3.2s-4.7-1.3-4.7-3" />
      </symbol>
      <symbol id="atlas-box" viewBox="0 0 24 24">
        <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" />
        <path d="M4 7.5l8 4.5 8-4.5M12 12v9" />
      </symbol>
      <symbol id="atlas-cart" viewBox="0 0 24 24">
        <circle cx="9" cy="20" r="1.4" />
        <circle cx="17" cy="20" r="1.4" />
        <path d="M3 4h2.5l2.2 11h10.6l2-8H6.1" />
      </symbol>
      <symbol id="atlas-tag" viewBox="0 0 24 24">
        <path d="M3 11V3h8l10 10-8 8L3 11z" />
        <circle cx="8" cy="8" r="1.5" />
      </symbol>
      <symbol id="atlas-factory" viewBox="0 0 24 24">
        <path d="M3 21V9l6 4V9l6 4V6l6 3v12H3z" />
        <path d="M7 21v-4h4v4" />
      </symbol>
      <symbol id="atlas-shield-check" viewBox="0 0 24 24">
        <path d="M12 2.8l7.5 3v6.4c0 4.4-3 7.6-7.5 9-4.5-1.4-7.5-4.6-7.5-9V5.8l7.5-3z" />
        <path d="M8.8 12.2l2.3 2.3 4.1-4.4" />
      </symbol>
      <symbol id="atlas-wrench" viewBox="0 0 24 24">
        <path d="M15.5 3.3a5.6 5.6 0 00-4.4 8.3L3.4 19.3a1.4 1.4 0 002 2l7.7-7.7a5.6 5.6 0 007.4-6.8l-3 3-2.8-.7-.7-2.8 3-3a5.7 5.7 0 00-1.5-.3z" />
      </symbol>
      <symbol id="atlas-users" viewBox="0 0 24 24">
        <circle cx="9" cy="8" r="3.4" />
        <path d="M2.8 20c.6-3.4 3.1-5.4 6.2-5.4s5.6 2 6.2 5.4" />
        <path d="M16 5.2a3.4 3.4 0 010 5.9M18.5 14.9c1.7.8 2.8 2.4 3.2 4.6" />
      </symbol>
      <symbol id="atlas-layers" viewBox="0 0 24 24">
        <path d="M12 3l9 4.5-9 4.5-9-4.5L12 3z" />
        <path d="M3 12.5l9 4.5 9-4.5M3 17l9 4.5 9-4.5" />
      </symbol>
      <symbol id="atlas-spark" viewBox="0 0 24 24">
        <path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4L12 3z" />
        <path d="M18.5 16.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2z" />
      </symbol>
      <symbol id="atlas-chart" viewBox="0 0 24 24">
        <path d="M4 20V10M10 20V4M16 20v-7M21 20H3" />
      </symbol>
      <symbol id="atlas-gear" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="3.2" />
        <path d="M12 2.8l1.2 2.6 2.8-.6 1 2.7 2.8.7-.6 2.8 2 2-2 2 .6 2.8-2.8.7-1 2.7-2.8-.6L12 21.2l-1.2-2.6-2.8.6-1-2.7-2.8-.7.6-2.8-2-2 2-2-.6-2.8 2.8-.7 1-2.7 2.8.6L12 2.8z" />
      </symbol>
      <symbol id="atlas-search" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="6.5" />
        <path d="M20.5 20.5l-4.8-4.8" />
      </symbol>
      <symbol id="atlas-plus" viewBox="0 0 24 24">
        <path d="M12 5v14M5 12h14" />
      </symbol>
      <symbol id="atlas-bell" viewBox="0 0 24 24">
        <path d="M18 9.5c0-3.3-2.7-6-6-6s-6 2.7-6 6c0 6-2.5 6.7-2.5 6.7h17S18 15.5 18 9.5z" />
        <path d="M10 19.5a2.2 2.2 0 004 0" />
      </symbol>
      <symbol id="atlas-chevron-down" viewBox="0 0 24 24">
        <path d="M6 9l6 6 6-6" />
      </symbol>
      <symbol id="atlas-chevron-right" viewBox="0 0 24 24">
        <path d="M9 6l6 6-6 6" />
      </symbol>
      <symbol id="atlas-sun" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6" />
      </symbol>
      <symbol id="atlas-moon" viewBox="0 0 24 24">
        <path d="M20 14.5A8.5 8.5 0 019.5 4a8.5 8.5 0 1010.5 10.5z" />
      </symbol>
      <symbol id="atlas-monitor" viewBox="0 0 24 24">
        <rect x="2.8" y="4" width="18.4" height="12.5" rx="2" />
        <path d="M8.5 20.5h7M12 16.5v4" />
      </symbol>
      <symbol id="atlas-menu" viewBox="0 0 24 24">
        <path d="M4 7h16M4 12h16M4 17h16" />
      </symbol>
      <symbol id="atlas-close" viewBox="0 0 24 24">
        <path d="M6 6l12 12M18 6L6 18" />
      </symbol>
      <symbol id="atlas-alert" viewBox="0 0 24 24">
        <path d="M12 3.5l9 15.5H3l9-15.5z" />
        <path d="M12 9.5v4.2M12 16.6v.1" />
      </symbol>
      <symbol id="atlas-arrow-left" viewBox="0 0 24 24">
        <path d="M20 12H4M10 6l-6 6 6 6" />
      </symbol>
      <symbol id="atlas-file" viewBox="0 0 24 24">
        <path d="M6 2.8h8L20 8.8v12.4H6V2.8z" />
        <path d="M14 3v6h6" />
      </symbol>
      <symbol id="atlas-help" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="9" />
        <path d="M9.3 9.2a2.8 2.8 0 015.4 1c0 1.9-2.7 2.3-2.7 4M12 17.4v.1" />
      </symbol>
      <symbol id="atlas-sign-out" viewBox="0 0 24 24">
        <path d="M9 21H4V3h5M15 16l5-4-5-4M20 12H9" />
      </symbol>
    </svg>
  );
}

export interface IconProps {
  name: IconName;
  /** Pixel size; the register's nav/control icons are 15px, page-level ones 18px. */
  size?: number;
  className?: string;
}

export function Icon({ name, size = 15, className }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{ flexShrink: 0 }}
    >
      <use href={`#atlas-${name}`} />
    </svg>
  );
}
