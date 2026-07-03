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
import { ApAgingPage } from "@/modules/finance/pages/ApAgingPage";
import { ArAgingPage } from "@/modules/finance/pages/ArAgingPage";
import { BalanceSheetPage } from "@/modules/finance/pages/BalanceSheetPage";
import { BankStatementDetailPage } from "@/modules/finance/pages/BankStatementDetailPage";
import { BankStatementImportPage } from "@/modules/finance/pages/BankStatementImportPage";
import { BankStatementListPage } from "@/modules/finance/pages/BankStatementListPage";
import { CashFlowStatementPage } from "@/modules/finance/pages/CashFlowStatementPage";
import { CustomerInvoiceDetailPage } from "@/modules/finance/pages/CustomerInvoiceDetailPage";
import { CustomerInvoiceFormPage } from "@/modules/finance/pages/CustomerInvoiceFormPage";
import { CustomerInvoiceListPage } from "@/modules/finance/pages/CustomerInvoiceListPage";
import { CustomerReceiptFormPage } from "@/modules/finance/pages/CustomerReceiptFormPage";
import { CustomerReceiptListPage } from "@/modules/finance/pages/CustomerReceiptListPage";
import { DunningRunPage } from "@/modules/finance/pages/DunningRunPage";
import { FinanceHomePage } from "@/modules/finance/pages/FinanceHomePage";
import { ProfitAndLossPage } from "@/modules/finance/pages/ProfitAndLossPage";
import { TrialBalancePage } from "@/modules/finance/pages/TrialBalancePage";
import { JournalEntryDetailPage } from "@/modules/finance/pages/JournalEntryDetailPage";
import { JournalEntryFormPage } from "@/modules/finance/pages/JournalEntryFormPage";
import { JournalEntryListPage } from "@/modules/finance/pages/JournalEntryListPage";
import { VendorBillDetailPage } from "@/modules/finance/pages/VendorBillDetailPage";
import { VendorBillFormPage } from "@/modules/finance/pages/VendorBillFormPage";
import { VendorBillListPage } from "@/modules/finance/pages/VendorBillListPage";
import { VendorPaymentFormPage } from "@/modules/finance/pages/VendorPaymentFormPage";
import { VendorPaymentListPage } from "@/modules/finance/pages/VendorPaymentListPage";
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

// --- Finance (PLAN 15.4) -------------------------------------------------------------------

const financeHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance",
  component: FinanceHomePage,
});

// Chart of accounts (slice 1)
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

// Journal entries (slice 1)
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

// Accounts Payable (slice 2)
const financeVendorBillsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/vendor-bills",
  component: VendorBillListPage,
});
const financeVendorBillNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/vendor-bills/new",
  component: VendorBillFormPage,
});
const financeVendorBillDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/vendor-bills/$billId",
  component: VendorBillDetailPage,
});
const financeVendorPaymentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/vendor-payments",
  component: VendorPaymentListPage,
});
const financeVendorPaymentNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/vendor-payments/new",
  component: VendorPaymentFormPage,
});
const financeApAgingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/ap-aging",
  component: ApAgingPage,
});

// Accounts Receivable (slice 3)
const financeCustomerInvoicesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/customer-invoices",
  component: CustomerInvoiceListPage,
});
const financeCustomerInvoiceNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/customer-invoices/new",
  component: CustomerInvoiceFormPage,
});
const financeCustomerInvoiceDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/customer-invoices/$invoiceId",
  component: CustomerInvoiceDetailPage,
});
const financeCustomerReceiptsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/customer-receipts",
  component: CustomerReceiptListPage,
});
const financeCustomerReceiptNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/customer-receipts/new",
  component: CustomerReceiptFormPage,
});
const financeArAgingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/ar-aging",
  component: ArAgingPage,
});
const financeDunningRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/dunning",
  component: DunningRunPage,
});

// Financial statements (slice 4)
const financeTrialBalanceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/trial-balance",
  component: TrialBalancePage,
});
const financeProfitLossRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/profit-loss",
  component: ProfitAndLossPage,
});
const financeBalanceSheetRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/balance-sheet",
  component: BalanceSheetPage,
});
const financeCashFlowRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/cash-flow",
  component: CashFlowStatementPage,
});

// Bank reconciliation (slice 5)
const financeBankStatementsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/bank-statements",
  component: BankStatementListPage,
});
const financeBankStatementImportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/bank-statements/import",
  component: BankStatementImportPage,
});
const financeBankStatementDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/bank-statements/$statementId",
  component: BankStatementDetailPage,
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
  financeVendorBillsRoute,
  financeVendorBillNewRoute,
  financeVendorBillDetailRoute,
  financeVendorPaymentsRoute,
  financeVendorPaymentNewRoute,
  financeApAgingRoute,
  financeCustomerInvoicesRoute,
  financeCustomerInvoiceNewRoute,
  financeCustomerInvoiceDetailRoute,
  financeCustomerReceiptsRoute,
  financeCustomerReceiptNewRoute,
  financeArAgingRoute,
  financeDunningRoute,
  financeTrialBalanceRoute,
  financeProfitLossRoute,
  financeBalanceSheetRoute,
  financeCashFlowRoute,
  financeBankStatementsRoute,
  financeBankStatementImportRoute,
  financeBankStatementDetailRoute,
  moduleRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
