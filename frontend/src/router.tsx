/**
 * Code-based TanStack Router tree (STRUCTURE §1: `router.tsx`). Root wraps every route in
 * AuthGate, which decides login-vs-shell; authenticated routes render inside AppShell. A
 * static route always wins over the dynamic `/$moduleKey` catch-all at the same path, so a
 * module registers its real routes here as its UI lands (15.4+) and the placeholder keeps
 * covering every module that hasn't shipped yet.
 */

import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";

import { App } from "@/App";
import { AdminHomePage } from "@/modules/admin/pages/AdminHomePage";
import { AuditLogListPage } from "@/modules/admin/pages/AuditLogListPage";
import { NumberSequenceListPage } from "@/modules/admin/pages/NumberSequenceListPage";
import { OnboardingWizardPage } from "@/modules/admin/pages/OnboardingWizardPage";
import { RoleDetailPage } from "@/modules/admin/pages/RoleDetailPage";
import { RoleFormPage } from "@/modules/admin/pages/RoleFormPage";
import { RoleListPage } from "@/modules/admin/pages/RoleListPage";
import { UserDetailPage } from "@/modules/admin/pages/UserDetailPage";
import { UserFormPage } from "@/modules/admin/pages/UserFormPage";
import { UserListPage } from "@/modules/admin/pages/UserListPage";
import { ExchangeRateFormPage } from "@/modules/finance/pages/ExchangeRateFormPage";
import { ExchangeRateListPage } from "@/modules/finance/pages/ExchangeRateListPage";
import { TaxCodeFormPage } from "@/modules/finance/pages/TaxCodeFormPage";
import { TaxCodeListPage } from "@/modules/finance/pages/TaxCodeListPage";
import { AccountFormPage } from "@/modules/finance/pages/AccountFormPage";
import { AccountListPage } from "@/modules/finance/pages/AccountListPage";
import { ApAgingPage } from "@/modules/finance/pages/ApAgingPage";
import { ArAgingPage } from "@/modules/finance/pages/ArAgingPage";
import { AssetDetailPage } from "@/modules/finance/pages/AssetDetailPage";
import { AssetFormPage } from "@/modules/finance/pages/AssetFormPage";
import { AssetListPage } from "@/modules/finance/pages/AssetListPage";
import { AssetRegisterPage } from "@/modules/finance/pages/AssetRegisterPage";
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
import { DepreciationRunDetailPage } from "@/modules/finance/pages/DepreciationRunDetailPage";
import { DepreciationRunFormPage } from "@/modules/finance/pages/DepreciationRunFormPage";
import { DepreciationRunListPage } from "@/modules/finance/pages/DepreciationRunListPage";
import { DunningRunPage } from "@/modules/finance/pages/DunningRunPage";
import { FinanceHomePage } from "@/modules/finance/pages/FinanceHomePage";
import { InventoryHomePage } from "@/modules/inventory/pages/InventoryHomePage";
import { ItemCategoryFormPage } from "@/modules/inventory/pages/ItemCategoryFormPage";
import { ItemCategoryListPage } from "@/modules/inventory/pages/ItemCategoryListPage";
import { ItemFormPage } from "@/modules/inventory/pages/ItemFormPage";
import { ItemListPage } from "@/modules/inventory/pages/ItemListPage";
import { StockCountDetailPage } from "@/modules/inventory/pages/StockCountDetailPage";
import { StockCountFormPage } from "@/modules/inventory/pages/StockCountFormPage";
import { StockCountListPage } from "@/modules/inventory/pages/StockCountListPage";
import { StockMoveDetailPage } from "@/modules/inventory/pages/StockMoveDetailPage";
import { StockMoveFormPage } from "@/modules/inventory/pages/StockMoveFormPage";
import { StockMoveListPage } from "@/modules/inventory/pages/StockMoveListPage";
import { StockOnHandPage } from "@/modules/inventory/pages/StockOnHandPage";
import { StockValuationPage } from "@/modules/inventory/pages/StockValuationPage";
import { UomFormPage } from "@/modules/inventory/pages/UomFormPage";
import { UomListPage } from "@/modules/inventory/pages/UomListPage";
import { WarehouseFormPage } from "@/modules/inventory/pages/WarehouseFormPage";
import { WarehouseListPage } from "@/modules/inventory/pages/WarehouseListPage";
import { ApprovalRuleFormPage } from "@/modules/procurement/pages/ApprovalRuleFormPage";
import { ApprovalRuleListPage } from "@/modules/procurement/pages/ApprovalRuleListPage";
import { GoodsReceiptDetailPage } from "@/modules/procurement/pages/GoodsReceiptDetailPage";
import { GoodsReceiptFormPage } from "@/modules/procurement/pages/GoodsReceiptFormPage";
import { GoodsReceiptListPage } from "@/modules/procurement/pages/GoodsReceiptListPage";
import { InvoiceMatchDetailPage } from "@/modules/procurement/pages/InvoiceMatchDetailPage";
import { InvoiceMatchFormPage } from "@/modules/procurement/pages/InvoiceMatchFormPage";
import { InvoiceMatchListPage } from "@/modules/procurement/pages/InvoiceMatchListPage";
import { MatchToleranceFormPage } from "@/modules/procurement/pages/MatchToleranceFormPage";
import { ProcurementHomePage } from "@/modules/procurement/pages/ProcurementHomePage";
import { PurchaseOrderDetailPage } from "@/modules/procurement/pages/PurchaseOrderDetailPage";
import { PurchaseOrderFormPage } from "@/modules/procurement/pages/PurchaseOrderFormPage";
import { PurchaseOrderListPage } from "@/modules/procurement/pages/PurchaseOrderListPage";
import { RequisitionDetailPage } from "@/modules/procurement/pages/RequisitionDetailPage";
import { RequisitionFormPage } from "@/modules/procurement/pages/RequisitionFormPage";
import { RequisitionListPage } from "@/modules/procurement/pages/RequisitionListPage";
import { RfqDetailPage } from "@/modules/procurement/pages/RfqDetailPage";
import { RfqFormPage } from "@/modules/procurement/pages/RfqFormPage";
import { RfqListPage } from "@/modules/procurement/pages/RfqListPage";
import { VendorFormPage as ProcurementVendorFormPage } from "@/modules/procurement/pages/VendorFormPage";
import { VendorListPage as ProcurementVendorListPage } from "@/modules/procurement/pages/VendorListPage";
import { BomFormPage } from "@/modules/manufacturing/pages/BomFormPage";
import { BomListPage } from "@/modules/manufacturing/pages/BomListPage";
import { ManufacturingHomePage } from "@/modules/manufacturing/pages/ManufacturingHomePage";
import { MrpRunDetailPage } from "@/modules/manufacturing/pages/MrpRunDetailPage";
import { MrpRunFormPage } from "@/modules/manufacturing/pages/MrpRunFormPage";
import { MrpRunListPage } from "@/modules/manufacturing/pages/MrpRunListPage";
import { ProductionOrderDetailPage } from "@/modules/manufacturing/pages/ProductionOrderDetailPage";
import { ProductionOrderFormPage } from "@/modules/manufacturing/pages/ProductionOrderFormPage";
import { ProductionOrderListPage } from "@/modules/manufacturing/pages/ProductionOrderListPage";
import { RoutingFormPage } from "@/modules/manufacturing/pages/RoutingFormPage";
import { RoutingListPage } from "@/modules/manufacturing/pages/RoutingListPage";
import { WorkCenterFormPage } from "@/modules/manufacturing/pages/WorkCenterFormPage";
import { WorkCenterListPage } from "@/modules/manufacturing/pages/WorkCenterListPage";
import { CustomerFormPage } from "@/modules/sales/pages/CustomerFormPage";
import { CustomerGroupFormPage } from "@/modules/sales/pages/CustomerGroupFormPage";
import { CustomerGroupListPage } from "@/modules/sales/pages/CustomerGroupListPage";
import { CustomerListPage } from "@/modules/sales/pages/CustomerListPage";
import { PriceListFormPage } from "@/modules/sales/pages/PriceListFormPage";
import { PriceListListPage } from "@/modules/sales/pages/PriceListListPage";
import { PriceQuoteLookupPage } from "@/modules/sales/pages/PriceQuoteLookupPage";
import { BillingDetailPage } from "@/modules/sales/pages/BillingDetailPage";
import { BillingFormPage } from "@/modules/sales/pages/BillingFormPage";
import { BillingListPage } from "@/modules/sales/pages/BillingListPage";
import { DeliveryDetailPage } from "@/modules/sales/pages/DeliveryDetailPage";
import { DeliveryFormPage } from "@/modules/sales/pages/DeliveryFormPage";
import { DeliveryListPage } from "@/modules/sales/pages/DeliveryListPage";
import { QuoteDetailPage } from "@/modules/sales/pages/QuoteDetailPage";
import { QuoteFormPage } from "@/modules/sales/pages/QuoteFormPage";
import { QuoteListPage } from "@/modules/sales/pages/QuoteListPage";
import { SalesHomePage } from "@/modules/sales/pages/SalesHomePage";
import { SalesOrderDetailPage } from "@/modules/sales/pages/SalesOrderDetailPage";
import { SalesOrderFormPage } from "@/modules/sales/pages/SalesOrderFormPage";
import { SalesOrderListPage } from "@/modules/sales/pages/SalesOrderListPage";
import { ReturnDetailPage } from "@/modules/sales/pages/ReturnDetailPage";
import { ReturnFormPage } from "@/modules/sales/pages/ReturnFormPage";
import { ReturnListPage } from "@/modules/sales/pages/ReturnListPage";
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
import { DashboardPage } from "@/modules/reporting/pages/DashboardPage";
import { ReportBuilderPage } from "@/modules/reporting/pages/ReportBuilderPage";
import { ReportingHomePage } from "@/modules/reporting/pages/ReportingHomePage";
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

// Fixed assets (slice 6)
const financeAssetsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/assets",
  component: AssetListPage,
});
const financeAssetNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/assets/new",
  component: AssetFormPage,
});
const financeAssetDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/assets/$assetId",
  component: AssetDetailPage,
});
const financeAssetEditRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/assets/$assetId/edit",
  component: AssetFormPage,
});
const financeDepreciationRunsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/depreciation-runs",
  component: DepreciationRunListPage,
});
const financeDepreciationRunNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/depreciation-runs/new",
  component: DepreciationRunFormPage,
});
const financeDepreciationRunDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/depreciation-runs/$runId",
  component: DepreciationRunDetailPage,
});
const financeAssetRegisterRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/asset-register",
  component: AssetRegisterPage,
});

// Settings: tax codes + exchange rates (PLAN 15.12)
const financeTaxCodesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/tax-codes",
  component: TaxCodeListPage,
});
const financeTaxCodeNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/tax-codes/new",
  component: TaxCodeFormPage,
});
const financeTaxCodeDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/tax-codes/$taxCodeId",
  component: TaxCodeFormPage,
});
const financeExchangeRatesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/exchange-rates",
  component: ExchangeRateListPage,
});
const financeExchangeRateNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/finance/exchange-rates/new",
  component: ExchangeRateFormPage,
});

// --- Inventory (PLAN 15.5) -----------------------------------------------------------------

const inventoryHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory",
  component: InventoryHomePage,
});

// Item masters (slice 1)
const inventoryItemCategoriesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/item-categories",
  component: ItemCategoryListPage,
});
const inventoryItemCategoryNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/item-categories/new",
  component: ItemCategoryFormPage,
});
const inventoryItemCategoryDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/item-categories/$categoryId",
  component: ItemCategoryFormPage,
});
const inventoryUomsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/uoms",
  component: UomListPage,
});
const inventoryUomNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/uoms/new",
  component: UomFormPage,
});
const inventoryUomDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/uoms/$uomId",
  component: UomFormPage,
});
const inventoryItemsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/items",
  component: ItemListPage,
});
const inventoryItemNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/items/new",
  component: ItemFormPage,
});
const inventoryItemDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/items/$itemId",
  component: ItemFormPage,
});

// Warehouses/bins + stock moves + on-hand + valuation (slice 2)
const inventoryWarehousesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/warehouses",
  component: WarehouseListPage,
});
const inventoryWarehouseNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/warehouses/new",
  component: WarehouseFormPage,
});
const inventoryWarehouseDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/warehouses/$warehouseId",
  component: WarehouseFormPage,
});
const inventoryStockMovesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/stock-moves",
  component: StockMoveListPage,
});
const inventoryStockMoveNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/stock-moves/new",
  component: StockMoveFormPage,
});
const inventoryStockMoveDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/stock-moves/$moveId",
  component: StockMoveDetailPage,
});
const inventoryStockOnHandRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/stock-on-hand",
  component: StockOnHandPage,
});
const inventoryStockValuationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/stock-valuation",
  component: StockValuationPage,
});

// Stock counts (slice 3)
const inventoryStockCountsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/stock-counts",
  component: StockCountListPage,
});
const inventoryStockCountNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/stock-counts/new",
  component: StockCountFormPage,
});
const inventoryStockCountDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inventory/stock-counts/$countId",
  component: StockCountDetailPage,
});

// --- Procurement (PLAN 15.6) ---------------------------------------------------------------

const procurementHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement",
  component: ProcurementHomePage,
});

// Vendors + approval rules (slice 1)
const procurementVendorsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/vendors",
  component: ProcurementVendorListPage,
});
const procurementVendorNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/vendors/new",
  component: ProcurementVendorFormPage,
});
const procurementVendorDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/vendors/$vendorId",
  component: ProcurementVendorFormPage,
});
// Requisitions (slice 2)
const procurementRequisitionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/requisitions",
  component: RequisitionListPage,
});
const procurementRequisitionNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/requisitions/new",
  component: RequisitionFormPage,
});
const procurementRequisitionDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/requisitions/$requisitionId",
  component: RequisitionDetailPage,
});
const procurementRequisitionEditRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/requisitions/$requisitionId/edit",
  component: RequisitionFormPage,
});

// RFQs + purchase orders (slice 3)
const procurementRfqsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/rfqs",
  component: RfqListPage,
});
const procurementRfqNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/rfqs/new",
  component: RfqFormPage,
});
const procurementRfqDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/rfqs/$rfqId",
  component: RfqDetailPage,
});
const procurementPurchaseOrdersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/purchase-orders",
  component: PurchaseOrderListPage,
});
const procurementPurchaseOrderNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/purchase-orders/new",
  component: PurchaseOrderFormPage,
});
const procurementPurchaseOrderDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/purchase-orders/$purchaseOrderId",
  component: PurchaseOrderDetailPage,
});

// Goods receipts (slice 4)
const procurementGoodsReceiptsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/goods-receipts",
  component: GoodsReceiptListPage,
});
const procurementGoodsReceiptNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/goods-receipts/new",
  component: GoodsReceiptFormPage,
});
const procurementGoodsReceiptDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/goods-receipts/$goodsReceiptId",
  component: GoodsReceiptDetailPage,
});

// Invoice matches + match tolerance (slice 5, FINAL)
const procurementInvoiceMatchesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/invoice-matches",
  component: InvoiceMatchListPage,
});
const procurementInvoiceMatchNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/invoice-matches/new",
  component: InvoiceMatchFormPage,
});
const procurementInvoiceMatchDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/invoice-matches/$invoiceMatchId",
  component: InvoiceMatchDetailPage,
});
const procurementMatchTolerancesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/match-tolerances",
  component: MatchToleranceFormPage,
});

const procurementApprovalRulesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/approval-rules",
  component: ApprovalRuleListPage,
});
const procurementApprovalRuleNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/approval-rules/new",
  component: ApprovalRuleFormPage,
});
const procurementApprovalRuleDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/procurement/approval-rules/$ruleId",
  component: ApprovalRuleFormPage,
});

// --- Sales (PLAN 15.7) ----------------------------------------------------------------------

const salesHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales",
  component: SalesHomePage,
});

// Customers + customer groups + pricing (slice 1)
const salesCustomersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/customers",
  component: CustomerListPage,
});
const salesCustomerNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/customers/new",
  component: CustomerFormPage,
});
const salesCustomerDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/customers/$customerId",
  component: CustomerFormPage,
});
const salesCustomerGroupsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/customer-groups",
  component: CustomerGroupListPage,
});
const salesCustomerGroupNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/customer-groups/new",
  component: CustomerGroupFormPage,
});
const salesCustomerGroupDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/customer-groups/$customerGroupId",
  component: CustomerGroupFormPage,
});
const salesPriceListsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/price-lists",
  component: PriceListListPage,
});
const salesPriceListNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/price-lists/new",
  component: PriceListFormPage,
});
const salesPriceListDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/price-lists/$priceListId",
  component: PriceListFormPage,
});
const salesPriceQuoteRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/price-quote",
  component: PriceQuoteLookupPage,
});

// Quotes + sales orders (slice 2)
const salesQuotesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/quotes",
  component: QuoteListPage,
});
const salesQuoteNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/quotes/new",
  component: QuoteFormPage,
});
const salesQuoteDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/quotes/$quoteId",
  component: QuoteDetailPage,
});
const salesQuoteEditRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/quotes/$quoteId/edit",
  component: QuoteFormPage,
});
const salesOrdersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/orders",
  component: SalesOrderListPage,
});
const salesOrderNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/orders/new",
  component: SalesOrderFormPage,
});
const salesOrderDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/orders/$orderId",
  component: SalesOrderDetailPage,
});
const salesOrderEditRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/orders/$orderId/edit",
  component: SalesOrderFormPage,
});

// Deliveries (slice 3)
const salesDeliveriesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/deliveries",
  component: DeliveryListPage,
});
const salesDeliveryNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/deliveries/new",
  component: DeliveryFormPage,
});
const salesDeliveryDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/deliveries/$deliveryId",
  component: DeliveryDetailPage,
});

// Billing + returns (slice 4, FINAL)
const salesBillingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/billings",
  component: BillingListPage,
});
const salesBillingNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/billings/new",
  component: BillingFormPage,
});
const salesBillingDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/billings/$billingId",
  component: BillingDetailPage,
});
const salesReturnsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/returns",
  component: ReturnListPage,
});
const salesReturnNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/returns/new",
  component: ReturnFormPage,
});
const salesReturnDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sales/returns/$returnId",
  component: ReturnDetailPage,
});

// --- Reporting (PLAN 15.12) ----------------------------------------------------------------

const reportingHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reporting",
  component: ReportingHomePage,
});
const reportingDashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reporting/dashboard",
  component: DashboardPage,
});
const reportingReportBuilderRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reporting/report-builder",
  component: ReportBuilderPage,
});

// --- Admin (PLAN 15.12) ---------------------------------------------------------------------

const adminHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin",
  component: AdminHomePage,
});
const adminOnboardingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/onboarding",
  component: OnboardingWizardPage,
});
const adminUsersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/users",
  component: UserListPage,
});
const adminUserNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/users/new",
  component: UserFormPage,
});
const adminUserDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/users/$userId",
  component: UserDetailPage,
});
const adminRolesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/roles",
  component: RoleListPage,
});
const adminRoleNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/roles/new",
  component: RoleFormPage,
});
const adminRoleDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/roles/$roleId",
  component: RoleDetailPage,
});
const adminAuditLogsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/audit-logs",
  component: AuditLogListPage,
});
const adminNumberSequencesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/number-sequences",
  component: NumberSequenceListPage,
});

// --- Manufacturing (PLAN 15.8) -------------------------------------------------------------

const manufacturingHomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing",
  component: ManufacturingHomePage,
});

// Masters: work centers, BOMs, routings (slice 1)
const manufacturingWorkCentersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/work-centers",
  component: WorkCenterListPage,
});
const manufacturingWorkCenterNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/work-centers/new",
  component: WorkCenterFormPage,
});
const manufacturingWorkCenterDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/work-centers/$workCenterId",
  component: WorkCenterFormPage,
});
const manufacturingBomsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/boms",
  component: BomListPage,
});
const manufacturingBomNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/boms/new",
  component: BomFormPage,
});
const manufacturingBomDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/boms/$bomId",
  component: BomFormPage,
});
const manufacturingRoutingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/routings",
  component: RoutingListPage,
});
const manufacturingRoutingNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/routings/new",
  component: RoutingFormPage,
});
const manufacturingRoutingDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/routings/$routingId",
  component: RoutingFormPage,
});

// Production orders (slice 2)
const manufacturingProductionOrdersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/production-orders",
  component: ProductionOrderListPage,
});
const manufacturingProductionOrderNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/production-orders/new",
  component: ProductionOrderFormPage,
});
const manufacturingProductionOrderDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/production-orders/$orderId",
  component: ProductionOrderDetailPage,
});

// MRP (slice 3, FINAL)
const manufacturingMrpRunsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/mrp/runs",
  component: MrpRunListPage,
});
const manufacturingMrpRunNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/mrp/runs/new",
  component: MrpRunFormPage,
});
const manufacturingMrpRunDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manufacturing/mrp/runs/$runId",
  component: MrpRunDetailPage,
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
  financeAssetsRoute,
  financeAssetNewRoute,
  financeAssetDetailRoute,
  financeAssetEditRoute,
  financeDepreciationRunsRoute,
  financeDepreciationRunNewRoute,
  financeDepreciationRunDetailRoute,
  financeAssetRegisterRoute,
  financeTaxCodesRoute,
  financeTaxCodeNewRoute,
  financeTaxCodeDetailRoute,
  financeExchangeRatesRoute,
  financeExchangeRateNewRoute,
  inventoryHomeRoute,
  inventoryItemCategoriesRoute,
  inventoryItemCategoryNewRoute,
  inventoryItemCategoryDetailRoute,
  inventoryUomsRoute,
  inventoryUomNewRoute,
  inventoryUomDetailRoute,
  inventoryItemsRoute,
  inventoryItemNewRoute,
  inventoryItemDetailRoute,
  inventoryWarehousesRoute,
  inventoryWarehouseNewRoute,
  inventoryWarehouseDetailRoute,
  inventoryStockMovesRoute,
  inventoryStockMoveNewRoute,
  inventoryStockMoveDetailRoute,
  inventoryStockOnHandRoute,
  inventoryStockValuationRoute,
  inventoryStockCountsRoute,
  inventoryStockCountNewRoute,
  inventoryStockCountDetailRoute,
  procurementHomeRoute,
  procurementVendorsRoute,
  procurementVendorNewRoute,
  procurementVendorDetailRoute,
  procurementRequisitionsRoute,
  procurementRequisitionNewRoute,
  procurementRequisitionDetailRoute,
  procurementRequisitionEditRoute,
  procurementRfqsRoute,
  procurementRfqNewRoute,
  procurementRfqDetailRoute,
  procurementPurchaseOrdersRoute,
  procurementPurchaseOrderNewRoute,
  procurementPurchaseOrderDetailRoute,
  procurementGoodsReceiptsRoute,
  procurementGoodsReceiptNewRoute,
  procurementGoodsReceiptDetailRoute,
  procurementInvoiceMatchesRoute,
  procurementInvoiceMatchNewRoute,
  procurementInvoiceMatchDetailRoute,
  procurementMatchTolerancesRoute,
  procurementApprovalRulesRoute,
  procurementApprovalRuleNewRoute,
  procurementApprovalRuleDetailRoute,
  salesHomeRoute,
  salesCustomersRoute,
  salesCustomerNewRoute,
  salesCustomerDetailRoute,
  salesCustomerGroupsRoute,
  salesCustomerGroupNewRoute,
  salesCustomerGroupDetailRoute,
  salesPriceListsRoute,
  salesPriceListNewRoute,
  salesPriceListDetailRoute,
  salesPriceQuoteRoute,
  salesQuotesRoute,
  salesQuoteNewRoute,
  salesQuoteDetailRoute,
  salesQuoteEditRoute,
  salesOrdersRoute,
  salesOrderNewRoute,
  salesOrderDetailRoute,
  salesOrderEditRoute,
  salesDeliveriesRoute,
  salesDeliveryNewRoute,
  salesDeliveryDetailRoute,
  salesBillingsRoute,
  salesBillingNewRoute,
  salesBillingDetailRoute,
  salesReturnsRoute,
  salesReturnNewRoute,
  salesReturnDetailRoute,
  reportingHomeRoute,
  reportingDashboardRoute,
  reportingReportBuilderRoute,
  adminHomeRoute,
  adminOnboardingRoute,
  adminUsersRoute,
  adminUserNewRoute,
  adminUserDetailRoute,
  adminRolesRoute,
  adminRoleNewRoute,
  adminRoleDetailRoute,
  adminAuditLogsRoute,
  adminNumberSequencesRoute,
  manufacturingHomeRoute,
  manufacturingWorkCentersRoute,
  manufacturingWorkCenterNewRoute,
  manufacturingWorkCenterDetailRoute,
  manufacturingBomsRoute,
  manufacturingBomNewRoute,
  manufacturingBomDetailRoute,
  manufacturingRoutingsRoute,
  manufacturingRoutingNewRoute,
  manufacturingRoutingDetailRoute,
  manufacturingProductionOrdersRoute,
  manufacturingProductionOrderNewRoute,
  manufacturingProductionOrderDetailRoute,
  manufacturingMrpRunsRoute,
  manufacturingMrpRunNewRoute,
  manufacturingMrpRunDetailRoute,
  moduleRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
