/**
 * The authenticated frame, in the porcelain register (runs/atlas-console/DIRECTION.md):
 * a 248px sidebar built from the caller's permissions, content to its right, the ⌘K palette
 * floating above both. Mounts once per session — module pages render inside `children`.
 *
 * Fixes #181: the previous shell was a fixed-width column at every viewport, so below about
 * 1024px it ate half the screen and clipped content off the right edge. The sidebar is now
 * static from `lg` up and an off-canvas drawer below it.
 *
 * Wraps `children` in RouteErrorBoundary — with `throwOnError` in lib/queryClient.ts that is
 * the single-point fix for #180, so a 4xx on any record read renders a designed error state
 * instead of a blank form or an endless spinner.
 */

import { useRouterState } from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";

import { Icon } from "@/components/Icon";
import { RouteErrorBoundary } from "@/components/ErrorState";
import { useMe } from "@/lib/session";
import { CommandPalette } from "@/shell/CommandPalette";
import { Sidebar } from "@/shell/Sidebar";
import { modulesFor } from "@/shell/moduleRegistry";

export function AppShell({ children }: { children: ReactNode }) {
  const me = useMe();
  const modules = modulesFor(me.data?.permissions ?? []);
  const currentPath = useRouterState({ select: (state) => state.location.pathname });
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Navigating dismisses the mobile drawer; leaving it open would cover the page just
  // navigated to.
  useEffect(() => setDrawerOpen(false), [currentPath]);

  return (
    <div className="min-h-screen bg-canvas">
      <a
        href="#main-content"
        className="sr-only rounded-control bg-ink px-4 py-2 text-[13px] font-medium text-surface focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60]"
      >
        Skip to content
      </a>

      {/* Static from lg up; an off-canvas drawer below it. */}
      <div className="fixed inset-y-0 left-0 z-40 hidden w-[248px] lg:block">
        <Sidebar
          modules={modules}
          me={me.data}
          currentPath={currentPath}
          onOpenPalette={() => setPaletteOpen(true)}
        />
      </div>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-ink/40"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 w-[248px] shadow-card">
            <Sidebar
              modules={modules}
              me={me.data}
              currentPath={currentPath}
              onOpenPalette={() => {
                setDrawerOpen(false);
                setPaletteOpen(true);
              }}
              onNavigate={() => setDrawerOpen(false)}
            />
          </div>
        </div>
      )}

      <div className="lg:pl-[248px]">
        {/* Mobile-only bar: the drawer needs an opener, and the brand needs to stay visible. */}
        <header className="flex h-14 items-center gap-3 border-b border-line bg-surface px-4 lg:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open navigation"
            aria-expanded={drawerOpen}
            className="flex size-10 items-center justify-center rounded-control text-ink-muted hover:bg-panel hover:text-ink"
          >
            <Icon name="menu" size={18} />
          </button>
          <span className="text-[13px] font-semibold text-ink">Atlas</span>
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            aria-label="Search or jump to"
            className="ml-auto flex size-10 items-center justify-center rounded-control text-ink-muted hover:bg-panel hover:text-ink"
          >
            <Icon name="search" size={18} />
          </button>
        </header>

        <main id="main-content" tabIndex={-1} className="px-5 py-6 sm:px-8 lg:px-9 lg:py-7">
          <RouteErrorBoundary resetKey={currentPath}>{children}</RouteErrorBoundary>
        </main>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}
