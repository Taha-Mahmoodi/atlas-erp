/**
 * Code-based TanStack Router tree (STRUCTURE §1: `router.tsx`). 15.1 ships the root and a
 * placeholder index route; 15.3 replaces the index with the login + role-based home pages
 * and each module registers its routes under the root as its UI lands (15.4+).
 */

import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";

import { App } from "@/App";

const rootRoute = createRootRoute({
  component: () => (
    <App>
      <Outlet />
    </App>
  ),
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: IndexPage,
});

function IndexPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50">
      <div className="text-center">
        <h1 className="text-2xl font-semibold text-slate-900">Atlas ERP</h1>
        <p className="mt-2 text-sm text-slate-500">
          Frontend scaffold (PLAN 15.1) — the app shell arrives with 15.3.
        </p>
      </div>
    </main>
  );
}

const routeTree = rootRoute.addChildren([indexRoute]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
