/**
 * The authenticated frame (PLAN 15.3): a Fiori-style top bar + left nav built from the
 * caller's role (moduleRegistry filtered by /me's permissions), content outlet on the
 * right. Mounts once per session — module pages render inside `children`.
 */

import { Link, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { logout } from "@/lib/auth";
import { useMe } from "@/lib/session";
import { modulesFor } from "@/shell/moduleRegistry";
import { ModuleLink } from "@/shell/ModuleLink";

export function AppShell({ children }: { children: ReactNode }) {
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const modules = modulesFor(permissions);
  const currentPath = useRouterState({ select: (state) => state.location.pathname });

  return (
    <div className="flex min-h-screen bg-canvas">
      <nav aria-label="Modules" className="flex w-56 shrink-0 flex-col border-r border-line bg-panel">
        <div className="border-b border-line px-4 py-4">
          <span className="text-sm font-semibold text-ink">Atlas ERP</span>
        </div>
        <ul className="flex-1 overflow-y-auto py-2">
          <li>
            <Link
              to="/"
              className={`block px-4 py-2 text-sm transition-colors duration-150 ${
                currentPath === "/" ? "bg-primary-tint font-medium text-primary" : "text-ink-muted hover:bg-surface hover:text-ink"
              }`}
            >
              Home
            </Link>
          </li>
          {modules.map((entry) => {
            const active = currentPath === `/${entry.key}` || currentPath.startsWith(`/${entry.key}/`);
            return (
              <li key={entry.key}>
                <ModuleLink
                  entry={entry}
                  className={`block px-4 py-2 text-sm transition-colors duration-150 ${
                    active ? "bg-primary-tint font-medium text-primary" : "text-ink-muted hover:bg-surface hover:text-ink"
                  }`}
                >
                  {entry.label}
                </ModuleLink>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface px-6">
          <span className="text-sm text-ink-muted">{me.data?.email}</span>
          <button
            type="button"
            onClick={() => void logout()}
            className="rounded-control px-3 py-1.5 text-sm text-ink-muted transition-colors duration-150 hover:bg-panel hover:text-ink"
          >
            Sign out
          </button>
        </header>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
