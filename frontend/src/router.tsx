/**
 * Code-based TanStack Router tree (STRUCTURE §1: `router.tsx`). Root wraps every route in
 * AuthGate, which decides login-vs-shell; authenticated routes render inside AppShell. Module
 * routes are ONE dynamic `/$moduleKey` until each module's real pages land (15.4-15.12), at
 * which point that module gets its own static route registered here ahead of the dynamic one.
 */

import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";

import { App } from "@/App";
import { AuthGate } from "@/shell/AuthGate";
import { HomePage } from "@/shell/HomePage";
import { ModulePlaceholderPage } from "@/shell/ModulePlaceholderPage";

const rootRoute = createRootRoute({
  component: () => (
    <App>
      <AuthGate>
        <Outlet />
      </AuthGate>
    </App>
  ),
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: HomePage,
});

const moduleRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/$moduleKey",
  component: ModulePlaceholderPage,
});

const routeTree = rootRoute.addChildren([indexRoute, moduleRoute]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
