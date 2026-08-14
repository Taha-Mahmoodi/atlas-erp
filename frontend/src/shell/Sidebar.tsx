/**
 * The porcelain sidebar (register §3): brand block, ⌘K trigger, permission-filtered nav
 * grouped under mono-caps section labels, user card pinned to the bottom.
 *
 * Two deliberate departures from the comp, both recorded rather than silently taken:
 *  - the brand block has no chevron. The comp drew a workspace *switcher*, but Atlas binds a
 *    session to one tenant, so a switcher would be an affordance that does nothing.
 *  - nav rows carry no count badge. Real counts would cost one query per module and the
 *    alternative is inventing numbers, which the design rules out outright.
 */

import { Link } from "@tanstack/react-router";

import { Icon } from "@/components/Icon";
import { logout } from "@/lib/auth";
import type { Me } from "@/lib/session";
import { SHORTCUT_LABEL } from "@/shell/CommandPalette";
import { ThemeToggle } from "@/shell/ThemeToggle";
import { ModuleLink } from "@/shell/ModuleLink";
import { MODULE_GROUPS, type ModuleEntry } from "@/shell/moduleRegistry";

const NAV_ROW = "flex h-[38px] items-center gap-2.5 rounded-[9px] px-2.5 text-[13.5px] transition-colors duration-150";
const NAV_REST = "text-ink-muted hover:bg-panel hover:text-ink";
const NAV_ACTIVE = "bg-primary-tint font-[550] text-primary";

function initials(me: Me | undefined): string {
  const source = me?.full_name?.trim() || me?.email || "";
  const parts = source.split(/[\s@.]+/).filter(Boolean);
  const first = parts[0];
  if (!first) return "—";
  return (first[0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export interface SidebarProps {
  modules: ModuleEntry[];
  me: Me | undefined;
  currentPath: string;
  /** Opens the ⌘K palette by synthesising the shortcut — one owner for that behaviour. */
  onOpenPalette: () => void;
  /** Mobile only: dismiss the drawer after navigating. */
  onNavigate?: () => void;
}

export function Sidebar({ modules, me, currentPath, onOpenPalette, onNavigate }: SidebarProps) {
  return (
    <div className="flex h-full flex-col border-r border-line bg-surface px-3 py-4">
      <div className="flex items-center gap-2.5 rounded-[10px] border border-line px-2.5 py-2">
        <span
          aria-hidden="true"
          className="flex size-[26px] items-center justify-center rounded-[7px] bg-ink text-[12px] font-bold text-surface"
        >
          A
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[13px] font-semibold text-ink">Atlas</span>
          <span className="block truncate text-[11px] text-ink-muted">{me?.email ?? "—"}</span>
        </span>
      </div>

      <button
        type="button"
        onClick={onOpenPalette}
        className="mt-3 flex h-[38px] items-center gap-2.5 rounded-[10px] border border-line px-2.5 text-[13px] text-ink-muted transition-colors duration-150 hover:bg-panel hover:text-ink"
      >
        <Icon name="search" size={15} />
        <span className="flex-1 text-left">Search or jump to…</span>
        <kbd className="kbd">{SHORTCUT_LABEL}</kbd>
      </button>

      {/* Scrolls when the caller's role reaches into enough modules to overflow — pb-2 keeps
          the last row from ending flush against the user card as if it were clipped. */}
      <nav aria-label="Primary" className="mt-1 flex-1 overflow-y-auto pb-2">
        <p className="mono-caps mt-3.5 mb-1.5 px-2.5 text-ink-muted">Overview</p>
        <Link
          to="/"
          onClick={onNavigate}
          className={`${NAV_ROW} ${currentPath === "/" ? NAV_ACTIVE : NAV_REST}`}
          {...(currentPath === "/" ? { "aria-current": "page" as const } : {})}
        >
          <Icon name="home" size={15} />
          Home
        </Link>

        {MODULE_GROUPS.map((group) => {
          const inGroup = modules.filter((entry) => entry.group === group);
          // A group with nothing the caller may open is not rendered empty.
          if (inGroup.length === 0) return null;
          return (
            <div key={group}>
              <p className="mono-caps mt-3.5 mb-1.5 px-2.5 text-ink-muted">{group}</p>
              {inGroup.map((entry) => {
                const active =
                  currentPath === `/${entry.key}` || currentPath.startsWith(`/${entry.key}/`);
                return (
                  <ModuleLink
                    key={entry.key}
                    entry={entry}
                    className={`${NAV_ROW} ${active ? NAV_ACTIVE : NAV_REST}`}
                  >
                    <Icon name={entry.icon} size={15} />
                    {entry.label}
                  </ModuleLink>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="mt-3 rounded-xl border border-line p-2.5">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="flex size-[30px] shrink-0 items-center justify-center rounded-full bg-primary-tint text-[11px] font-[650] text-primary"
          >
            {initials(me)}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-semibold text-ink">
              {me?.full_name ?? me?.email ?? "Signed in"}
            </span>
            <span className="block truncate text-[11px] text-ink-muted">
              {me?.full_name ? me.email : "Signed in"}
            </span>
          </span>
        </div>
        <div className="mt-2 flex items-center gap-1">
          <ThemeToggle />
          <button
            type="button"
            onClick={() => void logout()}
            className="flex h-8 flex-1 items-center justify-center gap-1.5 rounded-[8px] text-[12px] text-ink-muted transition-colors duration-150 hover:bg-panel hover:text-ink"
          >
            <Icon name="sign-out" size={14} />
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
