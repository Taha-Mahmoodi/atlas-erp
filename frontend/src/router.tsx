/**
 * Code-based TanStack Router tree (STRUCTURE §1: `router.tsx`). Root wraps every route in
 * AuthGate, which decides login-vs-shell; authenticated routes render inside AppShell. A
 * static route always wins over the dynamic `/$moduleKey` catch-all at the same path, so a
 * module registers its real routes here as its UI lands (15.4+) and the placeholder keeps
 * covering every module that hasn't shipped yet.
 */

import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";

import { App } from "@/App";
import { AccountFormPage } from "@/modules/finance/pages/AccountFormPage";
import { AccountListPage } from "@/modules/finance/pages/AccountListPage";
import { FinanceHomePage } from "@/modules/finance/pages/FinanceHomePage";
import { JournalEntryDetailPage } from "@/modules/finance/pages/JournalEntryDetailPage";
import { JournalEntryFormPage } from "@/modules/finance/pages/JournalEntryFormPage";
import { JournalEntryListPage } from "@/modules/finance/pages/JournalEntryListPage";
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

// --- Finance (PLAN 15.4, first slice: chart of accounts + journal entries) ----------------

const financeHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance",
  component: FinanceHomePage,
});

const financeAccountsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/accounts",
  component: AccountListPage,
});

const financeAccountNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/accounts/new",
  component: AccountFormPage,
});

const financeAccountDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/accounts/$accountId",
  component: AccountFormPage,
});

const financeJournalEntriesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/journal-entries",
  component: JournalEntryListPage,
});

const financeJournalEntryNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/journal-entries/new",
  component: JournalEntryFormPage,
});

const financeJournalEntryDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/journal-entries/$entryId",
  component: JournalEntryDetailPage,
});

// --- Every other module: placeholder until its own slice lands ----------------------------

const moduleRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/$moduleKey",
  component: ModulePlaceholderPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  financeHomeRoute,
  financeAccountsRoute,
  financeAccountNewRoute,
  financeAccountDetailRoute,
  financeJournalEntriesRoute,
  financeJournalEntryNewRoute,
  financeJournalEntryDetailRoute,
  moduleRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
