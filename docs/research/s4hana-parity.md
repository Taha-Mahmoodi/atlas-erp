# SAP S/4HANA → Atlas Parity Map

This document benchmarks Atlas ERP against SAP S/4HANA, the de-facto reference for enterprise ERP scope. Its purpose is twofold: to define what "complete" means for each functional area by enumerating the capabilities practitioners consider essential in current S/4HANA (2025/2026 releases), and to record — capability by capability — what Atlas v1 implements in full, what it implements in reduced form, and what it deliberately leaves out. The Atlas v1 scope is derived directly from this benchmark: every cut is documented with its rationale and an intended later path, so the gaps are commitments, not omissions. Research for this map was conducted in June 2026.

**Methodology.** All twelve functional areas below were verified through live web research against current sources (SAP Help Portal, SAP Learning, SAP Community, SAP PRESS, and ERP consulting publications); no area was built from the embedded knowledge baseline alone. Five areas — Financial Accounting, Inventory Management & Warehousing, Quality Management & Plant Maintenance, Project System, and Cross-cutting platform concepts — supplemented web findings with embedded S/4HANA knowledge for specific subtopics or where source pages could not be fetched; these are flagged in the Sources appendix.

Reading the tables: capabilities that practitioners consider **essential** are shown in bold. The Notes column preserves, verbatim, the scoping rationale and the planned later path for every partial and out-of-scope capability — that record is the contract of this document.

---

## Mandatory design inheritances

Two S/4HANA architectural principles are hardcoded into Atlas and are non-negotiable across all modules:

1. **Universal Journal pattern.** Atlas maintains one append-only financial line-item table as the single source of truth for all accounting data — the analogue of S/4HANA's ACDOCA. Every FI and CO view (trial balance, cost center report, margin analysis, financial statements) is a projection over this table. Totals are never separately stored; there are no aggregate tables to reconcile, and FI/CO reconciliation is eliminated by construction.

2. **Document flow.** Every business document in Atlas records its predecessor and successor links (quote → order → delivery → invoice → journal entry, requisition → PO → goods receipt → supplier invoice, and so on), and the UI can render the full chain from any document in either direction — the analogue of S/4HANA's document flow and Document Relationship Browser.

---

## Summary

| S/4HANA area | Full | Partial | Out of scope | Total |
|---|---:|---:|---:|---:|
| Financial Accounting (FI) | 5 | 5 | 2 | 12 |
| Controlling (CO) | 4 | 4 | 3 | 11 |
| Procurement (MM-PUR) | 6 | 3 | 3 | 12 |
| Inventory Management & Warehousing (MM-IM / EWM) | 5 | 3 | 3 | 11 |
| Sales & Distribution (SD) | 2 | 6 | 4 | 12 |
| Production Planning (PP) | 4 | 3 | 5 | 12 |
| Quality Management & Plant Maintenance (QM / PM-EAM) | 1 | 4 | 7 | 12 |
| Human Capital Management (HCM / SuccessFactors) | 5 | 5 | 2 | 12 |
| Project System (PS) | 2 | 2 | 8 | 12 |
| Cross-cutting platform concepts | 5 | 3 | 3 | 11 |
| Fiori UX & Embedded Analytics | 3 | 6 | 3 | 12 |
| Industry Solutions approach | 3 | 4 | 3 | 10 |
| **Total** | **45** | **48** | **46** | **139** |

---

## Financial Accounting (FI)

SAP S/4HANA Financial Accounting centers on the Universal Journal (table ACDOCA), which merges general ledger, controlling, asset, and material-ledger line items into one multi-dimensional single source of truth, eliminating FI/CO reconciliation. Around that core sit Accounts Payable (vendor invoices, automatic payment runs), Accounts Receivable (customer invoices, dunning, incoming payments), Asset Accounting (ledger-based parallel valuation and depreciation), Bank and Cash Management, tax determination via tax codes and procedures, real-time financial statements drawn directly from the journal, and orchestrated period-end/year-end close. Distinctive S/4HANA traits practitioners flag as essential include parallel ledgers for multi-GAAP accounting, document splitting for dimension-complete balance sheets, up to 10 parallel currencies, and posting-period control.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **General Ledger on the Universal Journal (ACDOCA)** | Full | finance | — |
| **Chart of accounts and fiscal year / posting period control** | Full | finance | — |
| **Multi-currency accounting and foreign currency valuation** | Partial | finance | Atlas v1 (PLAN 4.3 done) has transaction + functional currency, a rates table (SPOT/CLOSING, direct-or-inverse lookup), posting-time translation with frozen functional amounts (largest-remainder residual balancing), purpose-keyed FX posting defaults, and an **unrealized**-FX revaluation run with auto-reversal. **Bounded out of v1:** group/additional parallel currencies; consolidation-style translation; **realized** FX (deferred to AP/AR clearing — purposes wired now); and **per-open-item** revaluation granularity — v1 revalues the per-account monetary foreign balance (accounts flagged `is_monetary` with a foreign `currency_code`), not individual uncleared AP/AR items. Later: add per-line extra currency columns + open-item-granular revaluation + realized FX at clearing, reusing the same rates-table and FX-account machinery. |
| **Accounts Payable (vendor invoices, payment runs, aging)** | Full | finance | Core AP (vendor bills, payment runs, aging) is planned; bank payment file formats (ISO 20022/NACHA) and withholding tax are not explicitly in v1. Later: Layer payment-media file generation and withholding tax codes onto the existing payment-run engine. |
| **Accounts Receivable (customer invoices, receipts, dunning, aging)** | Full | finance | — |
| **Asset Accounting (parallel valuation, full lifecycle)** | Partial | finance | Atlas v1 is "asset accounting lite": register plus straight-line and declining-balance depreciation runs posting journals; no parallel depreciation areas, transfers, retirements with gain/loss, revaluation, or assets under construction. Later: Extend the asset register with lifecycle events (transfer/retire/AuC settle) and per-ledger depreciation areas reusing the existing depreciation-run poster. |
| **Bank and Cash Management** | Partial | finance | Atlas v1 covers bank reconciliation via CSV statement import with match suggestions only; no standard bank formats (MT940/CAMT), no auto-clearing rules engine, no cash positioning or liquidity forecasting. Later: Add MT940/CAMT.053 parsers feeding the same import pipeline, then a cash-position report over bank-clearing accounts. |
| **Tax handling (tax codes, determination, compliance reporting)** | Partial | finance | Atlas v1 plans line-level configurable tax codes (rate, jurisdiction, inclusive/exclusive) — the calculation core — but no withholding tax, no statutory tax return reports, and no external tax engine integration. Later: Build tax-return reports as queries over tax-coded journal lines and add a pluggable external tax-calculation interface. |
| **Financial statements and real-time reporting** | Full | finance | — |
| **Period-end and year-end close** | Partial | finance | Atlas v1 has the enforcement primitives (period open/close at service and DB level, FX revaluation accounts, depreciation runs) but no year-end balance carryforward, accrual engine, GR/IR regrouping, or close task orchestration. Later: Add a balance-carryforward job and a simple checklist-style close task list on top of existing period states. |
| **Parallel ledgers and document splitting (multi-GAAP)** | Out of scope | — | Atlas v1 plans a single universal-journal ledger; no parallel/extension ledgers or document splitting — the boundary is single-GAAP, entity-level balance sheets only (dimensions exist on lines but are not balanced). Later: Introduce a ledger dimension on journal entries so postings can fan out to parallel ledgers, then add a splitting rule engine at posting time. |
| Credit, collections and dispute management (Receivables Management/FSCM) | Out of scope | — | Not in the Atlas v1 plan; v1 AR stops at invoices, receipts, dunning levels, and aging — credit/collections/disputes are S/4HANA add-on processes beyond core FI-AR. Later: Add credit limits on the customer master with a posting-time check, then collections worklists driven by the existing aging data. |

---

## Controlling (CO)

In current S/4HANA, Controlling is no longer a separate ledger world: FI and CO are merged into the Universal Journal (ACDOCA), so every posting carries cost center, profit center, project/WBS, order, and profitability-segment dimensions, and all CO reporting is a real-time projection of that single table; cost elements have become G/L accounts. The practitioner-essential core comprises cost center accounting, profit center accounting, internal orders (deprecated in S/4HANA Cloud in favor of project cost collectors), product cost planning and cost object controlling, Margin Analysis (account-based CO-PA), universal allocations, activity types with internal activity allocation, and cost center planning/budgeting, with Material Ledger actual costing as an optional deepening. Atlas v1's design matches the architectural core and S/4HANA Cloud's direction (including replacing internal orders with projects), but leaves activity-rate machinery, planning/budgeting, variance decomposition, and multi-dimensional margin segments for later.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Universal Journal merge of FI and CO** | Full | finance | — |
| **Cost center accounting (CO-OM-CCA)** | Full | finance | — |
| **Profit center accounting** | Full | finance | — |
| **Internal orders (CO-OM-OPA)** | Partial | projects | Atlas deliberately mirrors S/4HANA Cloud's "Principle of One" by covering the cost-collector role with projects/WBS instead of a separate order object, but order-specific machinery (order types, statistical orders, settlement rules to cost centers/assets, budget availability control) is not stated in the plan. Later: Extend projects with settlement rules, budget/availability control, and settlement-to-asset postings rather than introducing a separate order object. |
| **Product cost planning (standard cost estimates)** | Partial | manufacturing | Atlas plans manufacturing-fed product costing (actual costs, WIP, finish-to-stock valuation) but does not state a BOM/routing cost-rollup engine, cost component split, or standard price release/costing-run machinery. Later: Add a cost-rollup service over BOM/routing data that produces standard costs with a component split, used to value finished-goods receipts and compute variances. |
| **Cost object controlling (WIP, variances, settlement)** | Partial | manufacturing | Atlas plans the core flow — WIP journals and finish-to-stock postings, which matches S/4HANA's modern event-based direction — but variance decomposition (input price/quantity, resource usage, lot size), scrap analysis, and settlement profiles are not planned. Later: Add variance categorization computed from journal deltas at order close, posting categorized variance lines to the ledger and the margin report. |
| **Margin analysis / profitability analysis (CO-PA)** | Partial | reporting | Atlas plans a margin-by-product report projected from the ledger — the right account-based architecture — but only the product dimension; customer/region/channel segments, COGS split by cost component, top-down distribution, and realignments are not planned. Later: Widen journal lines with additional market-segment attributes (customer, region, channel) derived at posting time and add segment-level margin reports over the same ledger projection. |
| **Allocations and assessments (universal allocation)** | Full | finance | Atlas plans allocation rules on cost centers and profit centers posting through the journal, which is the practitioner-essential core; allocation to margin-analysis segments and plan-data allocation are the main S/4 extras not mentioned. Later: Add margin-segment-context and plan-data allocation cycles on the same rule engine. |
| **Activity types and internal activity allocation** | Out of scope | — | No activity-type master, rate planning/calculation, or rate-based secondary cost postings appear in the Atlas plan; production cost capture is implied to be direct journal entries without rate machinery, so conversion-cost absorption from cost centers has no planned mechanism. Later: Add activity types with planned rates that generate secondary-cost journal lines from production confirmations, crediting the supplying cost center and debiting the order. |
| **Cost planning and budgeting (plan/actual)** | Out of scope | — | The Atlas v1 plan covers only actuals; no plan ledger, budget entry, or plan/actual comparison is mentioned, yet plan-versus-actual on cost centers is a core controlling activity for practitioners. Later: Add a plan-line ledger parallel to the journal and extend the cost-center and margin reports with plan/actual/variance columns. |
| Material Ledger / actual costing | Out of scope | — | Not mentioned in the Atlas plan; actual costing is an optional deepening in S/4HANA (mandatory only as the multi-currency valuation substructure), so omitting it from v1 is a defensible cut. Later: Add a periodic actual-cost roll-up job that recomputes inventory and COGS values from accumulated journal lines and posts revaluation entries. |

---

## Procurement (MM-PUR)

In current S/4HANA (2025/2026), Sourcing and Procurement covers the full procure-to-pay cycle: business-partner-based supplier master data, purchasing info records, purchase requisitions (now with Fiori self-service apps), RFQs and quotation comparison, purchase orders, goods receipt, and logistics invoice verification with 3-way match, tolerances, and payment blocking. Approvals run through either classic classification-based release strategies or the newer flexible workflow. Framework agreements (quantity/value contracts, scheduling agreements), source determination, and supplier evaluation round out the area; certification weightings confirm master data, the PR-to-PO process, and GR/invoice verification as the practitioner-essential core. Atlas v1 plans the essential discrete P2P chain end-to-end but deliberately defers outline agreements, automated source assignment, and supplier evaluation.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Supplier/vendor master (Business Partner)** | Full | procurement | **Done (PLAN 6.1):** `proc_vendors` (vendor_code unique per tenant, status ACTIVE/BLOCKED/INACTIVE, default currency validated against finance, payment_terms_days net-days driving AP due dates, contact/tax fields); the vendor `id` IS finance AP's opaque `partner_id` (D-029). Later: add partner functions (ordering address vs. invoicing party) and granular block levels. |
| **Purchasing info records (vendor-material data)** | Partial | procurement | **Done (PLAN 6.1, info-record-lite):** `proc_vendor_approved_items` captures the vendor↔item link (opaque item id validated via inventory/queries, plus the vendor's own SKU) but **no** time-dependent pricing/lead-time conditions. Later: Extend the vendor approved-items table with price, valid-from/to, and lead-time fields and use them to default PO lines. |
| **Purchase requisitions** | Full | procurement | **Done (PLAN 6.2):** `proc_requisitions`/`_lines` (DocumentMixin, `PR-` number at creation, DRAFT→SUBMITTED→APPROVED/REJECTED + CONVERTED/CANCELLED; submit consults the value-threshold rule). Later: MRP-generated requisitions arrive when the manufacturing/planning module lands. |
| **RFQs and supplier quotation comparison** | Full | procurement | **Done (PLAN 6.2):** `proc_rfqs`/`_lines` (one-vendor RFQ, DRAFT→SENT→QUOTED→CLOSED, record-quote fills per-line prices, convert-from-approved-requisition). Later: Multi-bidder price-comparison views and rejection letters can be layered onto the v1 RFQ document. |
| **Purchase orders** | Full | procurement | **Done (PLAN 6.2):** `proc_purchase_orders`/`_lines` (DocumentMixin, `PO-` number at creation, vendor-ACTIVE + approved-items enforced, terms/currency snapshot, line/total amounts; convert from requisition or quoted RFQ with docflow links; send gated by the value-threshold rule → PENDING_APPROVAL/auto-approve→SENT). |
| **Goods receipt against purchase order** | Full | inventory | Later: Atlas plans GR in the v1 chain; stock/valuation postings are owned by the inventory module. |
| **Invoice verification and 3-way match (MM-IV/LIV)** | Full | procurement | Later: Configurable tolerance groups, invoice-release workflow, and ERS (evaluated receipt settlement) are natural follow-ons; AP posting itself lives in finance. |
| **Approval/release strategies and flexible workflow** | Partial | procurement | **Done (PLAN 6.2, data-driven value-threshold rules only):** `proc_approval_rules` — one active single-characteristic (amount) rule per (tenant, document_type ∈ {REQUISITION, PURCHASE_ORDER}); a requisition submit / PO send at-or-above the threshold awaits an approver (distinct `.approve` key), below auto-approves; no rule / inactive / currency-mismatch ⇒ no gate. S/4HANA's essential release strategy also keys on multiple characteristics (plant, material group, document type), supports multi-step approver chains, and applies to more document types than the PR/PO chain. Later: Generalize the threshold-rule schema into condition records (field/operator/value) with ordered multi-approver steps applied per document type. |
| **Purchasing contracts (quantity/value outline agreements)** | Out of scope | — | Explicitly excluded from the Atlas v1 list; v1 covers only the discrete requisition-to-PO chain with no outline-agreement document type or drawdown tracking. Later: Add a contract document type referencing vendor and items with committed qty/value, and let POs reference it as release orders that consume the commitment. |
| **Scheduling agreements with delivery schedules** | Out of scope | — | Explicitly excluded from Atlas v1; no document exists for schedule lines or releases, so repetitive direct-procurement scenarios are not supported in v1. Later: Model as a contract variant carrying dated schedule lines that goods receipts consume directly, added alongside MRP integration. |
| **Source determination (source lists, quota arrangements)** | Partial | procurement | Atlas v1's vendor-master "approved items" provide manual approved-source data, but there is no automatic source proposal on requisitions, no quota arrangements, and no contract/info-record sources to determine against. Later: Add a source-assignment service that matches open requisition lines to approved vendor items (later contracts) and supports one-click or automatic PO creation. |
| Supplier evaluation and procurement analytics | Out of scope | — | Not in the Atlas v1 plan; classed by SAP itself as an advanced feature (15-20% certification weighting) and not required to run the core P2P cycle. Later: Compute supplier scorecards from existing GR (on-time/quantity) and invoice (price variance) history in the reporting module. |

---

## Inventory Management & Warehousing (MM-IM / EWM)

In current S/4HANA (2025), MM-IM covers the material/product master, all goods movements recorded in the unified MATDOC table, stock types and special stocks, physical inventory with cycle counting, and material valuation through the now-mandatory Material Ledger (standard price, moving average, FIFO/balance-sheet valuation), plus batch and serial number management and reorder-point replenishment. Warehousing is handled by embedded or decentralized EWM, whose basic tier covers storage-type/bin structures, putaway and stock-removal strategies, and handling units, while waves, slotting, labor management and MFS sit in the advanced (separately licensed) tier. Atlas v1 covers the transactional inventory core well (moves as single source of truth, MAV+FIFO costing, counts, lot/serial, reorder points) but deliberately stops short of stock-status/special-stock dimensions, standard costing, and the EWM execution layer.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Material / product master with item types and multi-UoM** | Full | inventory | Later: Richer attribute views (classification, plant-specific MRP data) can be layered onto the item entity later. |
| **Goods movements with movement types (GR, GI, transfer posting, stock transfer)** | Full | inventory | — |
| **Stock types and special stocks (unrestricted / QI / blocked; consignment, subcontracting, in-transit)** | Partial | inventory | Atlas v1 tracks quantity per warehouse/bin via stock moves but plans no stock-status dimension (QI/blocked) and no special-stock ownership categories such as consignment or subcontractor stock. Later: Add status and ownership dimensions to stock quants/move lines, with status-change moves reusing the existing move ledger. |
| **Physical inventory and cycle counting with difference posting** | Full | inventory | Later: Sampling-based inventory and ABC-driven count scheduling can be added on top of the count engine later. |
| **Material valuation: moving average, standard price, FIFO (Material Ledger)** | Partial | inventory | Atlas v1 plans moving average AND FIFO per item category with event-driven COGS posting, but omits standard costing with variance (price-difference) postings, which manufacturers treat as essential. Later: Add a standard-cost method to the per-item-category costing engine, posting purchase/production variances to dedicated variance accounts. |
| **Batch (lot) and serial number management** | Full | inventory | Later: Automatic batch determination (FEFO, characteristics-based selection) and shelf-life blocking can be added as picking-time rules later. |
| **Reorder point / consumption-based replenishment planning** | Full | inventory | Later: Full MRP (time-phased, BOM-driven) belongs to a later manufacturing module; v1 reorder-point-to-draft-requisition covers the inventory-side core. |
| **Warehouse structure: warehouses, storage types/sections, storage bins and quants** | Partial | inventory | Atlas v1 plans multi-warehouse and multi-bin stock keeping, but only a flat warehouse-to-bin model: no storage-type/section hierarchy, capacity checks, or activity areas. Later: Introduce an optional storage-type/zone layer and capacity attributes on bins without changing the move ledger. |
| **Putaway and picking (stock removal) strategies** | Out of scope | — | Explicitly excluded from Atlas v1: bins are chosen manually on stock moves; no strategy engine suggests or enforces source/destination bins. Later: Add a rule-based bin-determination service invoked at stock-move creation, starting with fixed-bin and FIFO/FEFO rules. |
| Wave management and warehouse task/order processing | Out of scope | — | Explicitly excluded from v1; Atlas moves are executed directly with no intermediate task/wave layer. In SAP this is an advanced-EWM (extra license) feature, so it is not basic-tier core. Later: Introduce a warehouse-task layer between documents and stock moves, then add wave grouping and release rules on top. |
| **Handling unit management (packing, nested HUs, SSCC labeling)** | Out of scope | — | Explicitly excluded from Atlas v1; stock is tracked as loose quantities per bin with no pack/container object, even though HU management is part of SAP's basic EWM tier and core for shipping-heavy operations. Later: Add an HU entity that wraps stock quants with pack/unpack/move-HU operations reusing the existing stock-move ledger. |

---

## Sales & Distribution (SD)

In current S/4HANA (2025/2026), Sales covers the full order-to-cash cycle: business-partner-based customer master, condition-technique pricing, pre-sales documents and contracts, sales order processing, (advanced) available-to-promise with backorder processing, outbound delivery and goods issue, billing with FI integration, FSCM-based credit management, and Advanced Returns Management, plus condition contract settlement (rebates), output management, intercompany/third-party flows, and Fiori-based fulfillment monitoring. The Atlas v1 plan covers the essential transactional spine (quote → order → delivery → invoice with partial shipments, backorders, simple ATP, a credit-limit block, and RMA returns with credit notes) but deliberately simplifies the pricing engine, delivery execution, billing variants, and credit management, and omits contracts/scheduling agreements, output management, rebates, and intercompany/third-party processing.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Customer master (Business Partner)** | Partial | sales | Atlas v1 plans a customer master with core sales data, but not S/4HANA's multi-role business partner model with distinct partner functions (separate ship-to/payer/bill-to per document). Later: Evolve the customer record into a party model with role assignments and per-order partner function overrides. |
| **Pricing and condition technique** | Partial | sales | Atlas v1 plans condition-style price lists by currency/customer group/date range plus discounts, but not the generalized access-sequence/pricing-procedure engine, quantity scales, freight/tax condition types, or price-approval workflows. Later: Generalize price tables into condition tables with a pluggable access-sequence resolver and an ordered pricing procedure. |
| **Sales quotations and order management** | Full | sales | **Done (PLAN 7.2):** `sales_quotes`/`_lines` (DocumentMixin, `QUO-` number, DRAFT→SENT→ACCEPTED/REJECTED, EXPIRED on lapse, CONVERTED, CANCELLED; lines priced from the condition resolver + per-line discounts) → `sales_orders`/`_lines` (DocumentMixin, `SO-` number, created from scratch or by converting an ACCEPTED quote with docflow + `source_quote_id`; CONFIRMED via the ATP+credit gate; PARTIALLY_DELIVERED/DELIVERED/INVOICED/CLOSED declared for 7.3/7.4). Later: contracts/scheduling agreements + output management. |
| **CRM pre-sales: leads → opportunity pipeline (kanban) + activities + convert** | Partial (CRM-lite) | crm | **Done (PLAN 12.1, the CRM-lite module, D-057):** `crm_leads` (`LEAD-` number, NEW→CONTACTED→QUALIFIED→CONVERTED/DISQUALIFIED; qualify→convert builds an opportunity), `crm_opportunities` (`OPP-` number + DocumentMixin; the **stage IS the kanban column** PROSPECTING→QUALIFICATION→PROPOSAL→NEGOTIATION→WON/LOST; `move_stage` is the card move) + optional `crm_opportunity_lines` (expected products → the quote lines on convert), `crm_activities` (CALL/EMAIL/MEETING/TASK/NOTE against **exactly one** of a lead or opportunity). The headline **convert-to-customer+quote** publishes `OpportunityConverted` → sales' handler creates a sales `Customer` (if new) + `Quote` in the same transaction (the event bus, §5). No campaigns/marketing automation, contact-account (business-partner) hierarchies, forecasting/pipeline analytics, service tickets, opportunity teams/competitors, lead scoring/assignment, or email/calendar integration. Later: add a contact/account party model, campaign objects, lead-scoring/assignment rules, and pipeline forecasting on top of the opportunity stages. |
| **Available-to-promise (ATP) and backorder processing** | Partial | sales | **Done (PLAN 7.2, simple ATP):** `atp_check` = on-hand (`inventory/queries.total_on_hand`) − committed (confirmed-undelivered order lines) + on-order (`procurement/queries.open_incoming_quantity`); a short line is flagged **backordered** but does **NOT** block confirmation (the hard block is credit). No product allocation/quotas, alternative-plant/substitution confirmation, supply protection, or prioritized mass BOP runs. Later: Add a scheduled re-promising (backorder run) job and allocation buckets on top of the existing availability query. |
| **Shipping and outbound deliveries** | Partial | sales | **Done (PLAN 7.3, the v1 scope):** `sales_deliveries`/`_lines` (DocumentMixin, `DN-` number, DRAFT→POSTED; created against a CONFIRMED/PARTIALLY_DELIVERED order with partial shipments + backorders = undelivered open lines) → on POST the goods issue runs via the event bus (`DeliveryShipped` → inventory ISSUE moves → finance **Dr COGS / Cr Inventory** at moving-average cost, COGS the default issue offset, D-045), `delivered_quantity` advances the order PARTIALLY_DELIVERED/DELIVERED, atomic + closed-period rollback, order→delivery→move docflow chain. No picking/packing/handling units, shipping point or route determination, wave processing, or warehouse/transportation integration. Later: Layer pick lists, packing/handling units, and shipping-point/route rules onto the delivery document later. |
| **Billing and invoicing** | Partial | sales | Atlas v1 plans per-delivery invoicing with FI posting and credit notes, but not collective billing runs, invoice split/merge rules, milestone or recurring billing plans, or preliminary billing. Later: Add a collective billing-due-list job with split/merge rules, then billing plans as a follow-on. |
| **Credit management** | Partial | sales | **Done (PLAN 7.2, static limit at confirmation):** a HARD block at order confirmation when exposure (open AR + open confirmed orders + this order) > `credit_limit` (0 = cash-only) → CREDIT_BLOCKED; a `sales.order.credit_release` user releases past the limit → CONFIRMED. No scoring or recheck at delivery; the exposure aggregation is open AR + open confirmed orders only (no finance-owned exposure ledger, no full delivery/open-order pipeline). Later: Introduce a finance-owned exposure ledger and a blocked-documents release queue, rechecking at delivery creation. |
| **Returns processing (RMA / Advanced Returns Management)** | Full | sales | Later: Inspection dispositions, refund-determination rules, and vendor-return chains can be added on the RMA later. |
| **Sales contracts and scheduling agreements** | Out of scope | — | Atlas v1 covers only the quote → order flow; no long-term agreement document types or release-order consumption against contracted quantities/values exist in the plan. Later: Add a contract document type with copy control to orders and quantity/value drawdown tracking. |
| **Output management (order confirmations, delivery notes, invoices)** | Out of scope | — | The Atlas v1 sales plan defines transactional documents but says nothing about rendering or transmitting them to customers, which practitioners treat as mandatory for go-live. Later: Add template-based PDF/email rendering keyed by document type and customer as a cross-module output service. |
| Rebates / condition contract settlement | Out of scope | — | No rebate accruals or settlement against sales volumes are in the Atlas v1 plan; only immediate order-level discounts are covered. Later: Build on the condition engine later: accrue per qualifying invoice and settle periodically via credit memo. |
| Intercompany and third-party (drop-ship) sales | Out of scope | — | Atlas v1 assumes a single selling entity shipping its own stock; no cross-company document pairing or vendor drop-ship triggering from sales orders is planned. Later: Add order-triggered purchase requisitions (drop-ship) first, then paired intercompany order/invoice generation. |

---

## Production Planning (PP)

S/4HANA PP covers manufacturing master data (material master, multi-level BOMs, work centers, routings, production versions), demand management with planning strategies and planned independent requirements, MRP including the in-memory MRP Live engine, production order execution with shop floor control and confirmations, and capacity evaluation/leveling. It additionally ships lean/order-less execution models (kanban, repetitive manufacturing), process-industry variants (PP-PI), and embedded PP/DS for finite detailed scheduling and optimization. Atlas v1's plan covers the discrete-manufacturing core well (BOMs, work centers, routings, production orders with WIP accounting, a deterministic MRP run, rough capacity check) while deliberately omitting forecast-based demand management, operation-level confirmations, capacity leveling, kanban, repetitive manufacturing, PP-PI, and PP/DS-class finite scheduling — the same areas v1-grade systems typically defer.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Bill of materials (multi-level, versioned)** | Full | manufacturing | Later: Alternative BOMs, engineering change management, and variant configuration can be layered on the versioned BOM model later. |
| **Work centers** | Full | manufacturing | Later: Shift calendars, capacity categories, and cost-center activity rates can be added incrementally. |
| **Routings / operation sequences** | Full | manufacturing | Later: Sub-operations, parallel/alternative sequences, and external-processing (subcontract) operations can be added to the routing model later. |
| **Production order lifecycle (shop floor control)** | Full | manufacturing | Later: Rework orders, co-products, availability checks at release, and order splitting can be added on the same order object. |
| **Order confirmations (operation-level time/quantity recording)** | Partial | manufacturing | Atlas v1 plans only order-level completion (issue to WIP, finish to stock, WIP journals); per-operation confirmations with actual time capture and scrap recording are not planned. Later: Add a confirmation entity keyed to routing operations that posts actual times/quantities into the existing WIP journals. |
| **MRP and MRP Live** | Partial | manufacturing | The core deterministic run (sales-order demand + reorder points exploded against supply, producing planned orders) is planned; exception/rescheduling messages, MRP areas, multi-plant scope, net-change planning, and MRP-Live-class in-memory performance are not. Later: Layer exception messages, pegging, and net-change/multi-plant runs onto the same planning engine without schema changes. |
| **Capacity planning (evaluation and leveling)** | Partial | manufacturing | Atlas v1 plans capacity evaluation only (rough load vs available hours per work center); interactive leveling, dispatching, and finite scheduling are not planned. Later: Add a dispatching board that re-dates order operations against a finite work-center calendar using the existing load data. |
| **Demand management and planning strategies (PIRs, MTS/MTO)** | Out of scope | — | Atlas v1 MRP consumes only direct sales-order demand and reorder points; forecast-based PIRs, planning strategies, and forecast-consumption logic are not planned, so make-to-stock forecast planning is impossible in v1. Later: Add a PIR table with strategy/consumption rules as an additional demand source feeding the existing MRP run. |
| Kanban (pull-based replenishment) | Out of scope | — | No pull/lean replenishment is planned; Atlas v1 is purely push-based (MRP plus reorder points), which is the typical v1-grade boundary. Later: Add kanban control cycles whose status changes generate the existing supply elements (production orders/purchase orders/transfers). |
| Repetitive manufacturing (REM) | Out of scope | — | Atlas v1 supports only discrete production orders; period/rate-based order-less execution and product cost collectors are not planned. Later: Add run-schedule headers on production versions with backflush postings reusing BOM/routing and inventory movement logic. |
| Embedded PP/DS (detailed scheduling and optimization) | Out of scope | — | Atlas v1 stops at rough infinite-capacity load checks; finite scheduling, optimizers, and planning boards are deliberately omitted, as in virtually all v1-grade ERPs. Later: Bolt on a finite-scheduler service consuming routings, work-center calendars, and order operations via the existing APIs. |
| Process manufacturing (PP-PI: master recipes, process orders) | Out of scope | — | Atlas v1 targets discrete manufacturing only; recipe/process-order semantics, PI sheets, and phase-based execution are not planned. Later: Model recipes and process orders as specializations of routings/production orders in a later industry add-on. |

---

## Quality Management & Plant Maintenance (QM / PM-EAM)

In current S/4HANA (2025/2026), QM covers quality planning (inspection plans, master inspection characteristics, sampling), quality inspection (inspection lots auto-created at goods receipt, in production, and at delivery), characteristic-level results recording, coded usage decisions that drive stock postings out of quality-inspection stock, and quality notifications/CAPA, plus certificates and supplier quality. PM-EAM centers on technical objects (equipment installed on hierarchical functional locations), maintenance notifications feeding corrective maintenance orders with a phase-based lifecycle, preventive maintenance plans (time-, performance/counter-, and strategy-based) scheduled against task lists, and measurement points/counters for condition readings. Against the Atlas v1 plan, the GR-inspection-to-disposition flow, equipment register, and corrective/interval-based preventive orders cover a credible minimal core, but inspection plans, results recording, quality and maintenance notifications, functional locations, and measurement points are genuine gaps practitioners will notice.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Inspection lots** | Partial | quality | Only GR-origin lots via an inspection flag are planned; production/in-process, delivery, and manual lot origins plus sampling/sample-size logic are not. Later: Extend the existing lot object with additional origins (production order, delivery, manual) and sampling procedures. |
| **Inspection plans and master inspection characteristics** | Out of scope | — | Explicitly excluded from the v1 list; v1 lots are plan-less binary accept/reject with no characteristic or sampling master data. Later: Introduce inspection plan + characteristic master data and assign plans to lots at creation. |
| **Results recording** | Out of scope | — | Depends on inspection plans/characteristics, which are cut; v1 captures only a lot-level accept/reject outcome, not measured values. Later: After plans/characteristics exist, add a characteristic-level results entry screen with auto-valuation. |
| **Usage decisions with stock disposition** | Partial | quality | Binary accept/reject with a stock move is planned, but coded UD catalogs, quality scores, and split-quantity postings (scrap/sample/return) are not. Later: Add UD code catalogs and multi-bucket quantity split posting on top of the existing accept/reject action. |
| **Quality notifications (defects/complaints/CAPA)** | Out of scope | — | No defect/complaint workflow in v1; a rejected lot only moves stock and does not open a tracked quality issue. Later: Add a generic notification/issue object (shared with maintenance notifications) linkable to lots, suppliers, and materials. |
| Quality certificates and supplier quality | Out of scope | — | Not in the v1 plan; mainly needed in regulated industries and dependent on results recording, which is also cut. Later: Generate certificate documents from recorded results and add a vendor-material quality status check in procurement. |
| **Equipment and functional locations (technical objects)** | Partial | maintenance | **Done (PLAN 9.2, the v1 scope, D-051):** `pm_equipment` (`Equipment`) — a FLAT register keyed by a user-supplied `code` unique per tenant, status ACTIVE/INACTIVE/RETIRED, a FREE-TEXT `location` label, nameplate fields, and an optional opaque finance `cost_center_id` (D-029). Functional-location hierarchies, install/dismantle, and structure-based reporting are explicitly excluded. Later: Add a functional location entity with hierarchy codes and equipment installation/dismantle links. |
| **Maintenance notifications** | Out of scope | — | v1 creates corrective orders directly with no notification/request stage, losing breakdown reporting and MTBF/MTTR-style analysis. Later: Add a lightweight notification object convertible to an order, reusing the shared notification model. |
| **Corrective maintenance orders** | Full | maintenance | **Done (PLAN 9.2, D-051):** `pm_maintenance_orders` (`MaintenanceOrder`, DocumentMixin + gapless `MNT-` number) created ad-hoc against ACTIVE equipment, with a DRAFT → SCHEDULED → IN_PROGRESS → COMPLETED (+ CANCELLED) lifecycle. Completion records `actual_cost` on the order (record-only — no GL posting in v1; a maintenance-expense journal through the cost centre is a documented later). |
| **Preventive maintenance plans and scheduling** | Partial | maintenance | **Done (PLAN 9.2, the v1 scope, D-051):** `pm_maintenance_plans` (`MaintenancePlan`) — interval-based (DAYS/WEEKS/MONTHS, time only) recurring plans on a piece of equipment; a generate-due-orders RUN (`POST /maintenance-plans/run-preventive`) creates one PREVENTIVE order per due plan (set-based scan, the **generate-one-advance-to-next-future** overdue rule, idempotent same-day). Counter/performance-based and strategy plans are impossible without measurement points. Later: Once counters exist, extend the scheduler with performance-based cycles and packaged strategy plans. |
| **Measurement points and counters** | Out of scope | — | Explicitly excluded from the v1 list; no condition readings or counter-driven triggers are planned. Later: Add a measuring point entity on equipment with reading documents that feed maintenance plan scheduling. |
| **Maintenance task lists** | Out of scope | — | Not in the v1 plan; v1 preventive/corrective orders would carry free-text work instead of reusable standardized operations. Later: Add a task list master assignable to maintenance plan items and copyable into orders. |

---

## Human Capital Management (HCM / SuccessFactors)

In current S/4HANA, HR is delivered as "SAP HCM for SAP S/4HANA" (H4S4) — switched on by default from the S/4HANA 2025 release, with the old HCM compatibility pack retired — while SAP's strategic, go-forward HCM is the SuccessFactors cloud suite (Employee Central, EC Payroll, Time Tracking, Recruiting, Onboarding, Learning, Performance, Compensation, Succession). H4S4 carries forward essentially the full SAP ERP HCM scope: Personnel Administration, Organizational Management, Time Management (work schedules, time evaluation, CATS timesheet with cost-center/WBS allocation), localized gross-to-net Payroll with retro calculation and posting to FI/CO, plus ESS/MSS, benefits, compensation and some talent functions. Atlas v1's plan covers the org, employee-master and leave cores well, covers timesheet capture and payroll-to-GL in reduced form, and deliberately leaves out talent, recruiting, benefits and jurisdiction-compliant payroll — the main honest gaps versus what HR practitioners consider a complete HCM suite.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Employee master data (Personnel Administration)** | Full | hr | **Done (PLAN 10.1, D-052):** `hr_employees` (`Employee`) — user-coded employee master with department/position/manager/optional-login links and MASKED compensation/PII (`base_salary`, `national_id`, `tax_id`, `date_of_birth`, `bank_account` behind `hr.employee.read_compensation` via the D-009 `Masked` serializer; written only at create + the dedicated `PATCH /employees/{id}/compensation`). Later: Add date-effective history and formal hire/transfer/terminate actions on the existing employee entity. |
| **Organizational management (org units, positions, org chart)** | Full | hr | **Done (PLAN 10.1, D-052):** `hr_departments` (`Department`, self-FK hierarchy + cost-centre link + soft manager link) + `hr_positions` (`Position`) + the reporting ORG CHART (`Employee.manager_id` self-FK; `GET /employees/org-chart`, bounded recursive build). Department hierarchy and manager reporting line are both cycle-guarded. Later: Extend later with date-effective org structures and job catalogs if needed. |
| **Leave and absence management** | Full | hr | Later: Later add collision checks with work schedules and quota carryover rules. |
| **Time recording with account assignment (CATS-style timesheet)** | Full | hr | Later: Planned core (capture + project/cost-center allocation) matches CATS; approval/transfer-to-costing flows can be hardened later. |
| **Time evaluation and work schedules** | Partial | hr | Atlas v1 plans timesheet capture and leave only; no work-schedule rules, shift planning or rule-based evaluation of overtime/premiums. Later: Add work-schedule calendars and a rules-based time evaluation step that feeds payroll inputs. |
| **Payroll (localized gross-to-net with retro calculation)** | Partial | hr | Atlas v1 plans only a simple gross-to-net calculation explicitly flagged as not jurisdiction-compliant; no country legal rules, retro accounting, payment files or statutory reporting. Later: Integrate certified third-party/localized payroll engines via connector, or ship country compliance packs incrementally. |
| **Payroll posting to finance (FI/CO integration)** | Full | hr | Later: Later refine with configurable wage-type-to-account mapping and accrual postings. |
| **Employee and manager self-service (ESS/MSS)** | Partial | hr | Leave approvals and time entry imply basic self-service, but no planned employee self-service for personal data, payslips, or manager team dashboards. Later: Add ESS/MSS screens on top of existing HR APIs in the frontend once core records and payroll outputs exist. |
| **Compensation management (pay structures and review cycles)** | Partial | hr | **Partial (PLAN 10.1, D-052):** Atlas v1 stores only static MASKED compensation fields on the employee (`base_salary` + `currency_code`, gated by `hr.employee.read_compensation`, written via the dedicated compensation endpoint); no pay-grade structures or compensation review cycles. Later: Add pay-grade/salary-band tables and a periodic comp review workflow over the masked fields. |
| **Talent management (recruiting, onboarding, learning, performance, succession)** | Out of scope | — | Explicitly excluded from the v1 list; v1 targets core HR/time/payroll-lite, and even SAP treats talent as a separate cloud suite rather than ERP core. Later: Add as a separate talent module or integrate an open-source ATS/LMS against the employee and org APIs. |
| **Benefits administration** | Out of scope | — | Explicitly excluded from v1; meaningful benefits administration depends on compliant payroll deductions, which v1 also lacks. Later: Add plan/eligibility/enrollment objects feeding deduction lines once payroll gains real deduction handling. |
| **HR reporting and analytics** | Partial | reporting | v1 plan includes the org chart and operational record views but no HR KPI analytics (headcount trends, absence rates, labor cost). Later: Build headcount/absence/labor-cost reports on the shared reporting module over HR and journal data. |

---

## Project System (PS)

S/4HANA Project System manages internal, capital-investment, and customer projects through hierarchical work breakdown structures (WBS) and optional networks/activities, covering structure planning, scheduling, cost and revenue planning, budgeting with availability control, execution postings (time via CATS, procurement, goods movements), and period-end close via settlement and results analysis / event-based revenue recognition. In current S/4HANA (2025/2026) the area spans classic PS (on-premise/private cloud) and the Fiori-based Enterprise Projects and Professional Services Projects in Enterprise Portfolio and Project Management (public cloud). The Atlas v1 plan (WBS as costing objects, time and purchases postable to WBS, a project cost report) covers the execution-side core — structures and actual-cost collection — but deliberately omits the planning and financial-close layers: networks/scheduling, cost planning, budgeting/availability control, settlement, results analysis/revenue recognition, and customer-project billing are all out of scope for v1.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Project definitions and WBS structures** | Full | projects | Later: Templates, status management, and mass-change tooling can be layered on the same WBS entity later. |
| **Networks, activities, and relationships** | Out of scope | — | Atlas v1 explicitly excludes networks; the v1 model is WBS-only cost collection with no activity/task layer. Later: Add an activity entity under WBS elements with relationships and confirmations, then attach scheduling and material components. |
| **Project scheduling and milestones** | Out of scope | — | Scheduling is explicitly not in the v1 list and depends on the network/activity layer, which is also excluded. Later: Introduce basic/forecast dates on WBS and activities plus a scheduling engine and Gantt view once networks exist. |
| **Project cost planning** | Out of scope | — | Atlas v1 collects only actual costs on WBS; no plan versions or planned-cost entry are in the plan, so the cost report has no plan/actual comparison. Later: Add a plan-cost table keyed by WBS element and period, then extend the project cost report to plan-vs-actual. |
| **Project budgeting and availability control** | Out of scope | — | Budgeting controls are explicitly excluded from the v1 list; v1 has no budget object and no posting-time funds check. Later: Add a budget amount per WBS with tolerance rules evaluated in the posting pipeline before actuals commit. |
| **Time recording to projects (CATS-style)** | Full | projects | Later: Approval workflows and posting to network activities can follow once those features exist. |
| **Procurement and expense postings to projects** | Partial | projects | Atlas v1 plans actual purchase and expense postings to WBS, but PR/PO commitment tracking and project stock / project MRP are not planned. Later: Derive commitment records from open purchase orders assigned to WBS, then add project-stock segments in inventory. |
| **Project settlement** | Out of scope | — | Settlement is explicitly excluded from v1; collected costs remain on the WBS with no period-end transfer to receivers. Later: Add settlement rules per WBS and a periodic settlement run reusing the finance allocation/posting engine. |
| **Results analysis / event-based revenue recognition** | Out of scope | — | No revenue recognition or WIP/POC valuation of project costs is planned in v1; v1 projects are pure cost collectors. Later: Implement event-based recognition postings in the finance module triggered by project cost and billing events. |
| **Customer project billing integration** | Out of scope | — | Not in the v1 list; there is no planned sales-order-to-WBS link or billing generated from project time/expenses. Later: Link sales order lines to WBS elements, then generate resource-related billing proposals from posted time and expenses. |
| **Project cost reporting and analytics** | Partial | projects | v1 plans a project cost report over actuals by WBS, but without plan or commitment columns and without the broader drilldown/overview suite, it is a reduced subset. Later: Extend the report with commitment and plan columns and line-item drilldown as those data objects are added. |
| Progress analysis / earned value management | Out of scope | — | Depends on cost planning, budgets, and scheduling, none of which are in v1; also not considered core by most practitioners outside EPC/engineering industries. Later: Compute POC and earned value from plan-cost and confirmation data once planning and scheduling layers exist. |

---

## Cross-cutting platform concepts

Cross-cutting platform concepts in S/4HANA (2025/2026) are the architectural primitives every functional module relies on: the Universal Journal (ACDOCA) as the single financial line-item table; document flow with predecessor/successor links viewable in the Document Relationship Browser; the mandatory unified Business Partner model (CVI-synchronized customer/vendor views); the BRF+/Adobe Forms output management framework; configurable number ranges per document type; the roles/profiles authorization concept (PFCG on-premise, business roles with restrictions in Cloud); and the client (MANDT) field on nearly every table on-premise, replaced by tenant isolation in S/4HANA Cloud SaaS. Atlas v1 deliberately inherits the two load-bearing patterns (Universal Journal, document flow) and covers tenancy, RBAC, audit, and numbering, while consciously deviating on the Business Partner model and deferring output management, workflow, and extensibility.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Universal Journal (ACDOCA) as single source of truth** | Full | finance | — |
| **Document flow / Document Relationship Browser** | Full | core | — |
| **Unified Business Partner model (BP + CVI)** | Partial | core | Deliberate deviation: Atlas v1 keeps separate vendor and customer master tables; customer/vendor master data itself is planned, but there is no unified party object, no shared roles/relationships, and no single identity for an entity that is both customer and supplier. Later: Introduce a thin party/business-partner table that links existing customer and vendor records as roles, without restructuring the two masters. |
| **Output management (determination rules, channels, form templates)** | Partial | core | Atlas v1 plans only basic document rendering; the rule-based determination framework, multi-channel dispatch (email/EDI), template management, and output status/retry queue are explicitly not in the v1 list. Later: Add a rule-driven output determination service (document attributes → channel + template + recipient) with pluggable channel adapters and a retryable output queue. |
| **Number ranges (document numbering)** | Full | core | Later: Add external number assignment and per-fiscal-year ranges later if conversion/legal scenarios demand them. |
| **Authorization concept (roles, profiles, restrictions)** | Partial | admin | Atlas v1 plans the RBAC core (JWT auth, roles → permissions → resources stored as data), but S/4HANA's field/org-value restrictions (scoping a permission to specific company codes, plants, etc.) and segregation-of-duties analysis are not in the v1 list. Later: Extend permission records with attribute/scope filters (org-unit values) evaluated alongside the tenant filter, then layer SoD rule checks on role assignments. |
| **Multi-client architecture / SaaS multi-tenancy** | Full | core | — |
| **Audit trail / change documents** | Full | core | Later: Add read-access logging for sensitive fields as a later compliance increment. |
| **Extensibility framework (custom fields, key-user and side-by-side extensions)** | Out of scope | — | No custom-field or extension mechanism appears anywhere in the Atlas v1 plan; v1 ships fixed schemas only. Later: Add JSONB custom-field columns with metadata-driven validation on core entities, plus webhook/event hooks per document type. |
| **Workflow engine (flexible approval workflows)** | Out of scope | — | No approval/workflow capability is in the Atlas v1 plan; documents post directly without configurable release strategies, which practitioners consider a core control in procurement and finance. Later: Add a generic approval service (document type + condition → ordered approver steps) driving a status field that blocks posting until approved. |
| **Released APIs and event-based integration** | Out of scope | — | The Atlas v1 cross-cutting scope defines internal patterns (journal, flow, tenancy, auth) but lists no public API contract or event emission for external integration. Later: Publish the existing internal REST endpoints as a versioned public API and emit domain events (document created/changed) to a message bus or webhooks. |

---

## Fiori UX & Embedded Analytics

In current S/4HANA (2025/2026), this area covers the Fiori design system (Horizon theme, SAPUI5/Fiori elements controls), the role-based launchpad organized into spaces and pages with app/KPI/insight tiles, standard floorplans (list report, object page, overview page, analytical list page, worklist), and embedded analytics built on the CDS virtual data model: analytical queries, Smart Business KPI tiles with thresholds and drill-down, multidimensional reports, and self-service query creation — all running live on transactional data with insight-to-action navigation into transactions. The 2025 release adds Fiori 4.0 touches: AI-assisted enterprise search, Joule integration, smart summarization, and AI-personalized My Home insight cards. Atlas v1 covers the essential core of the role-based home page, role dashboards, and tabular self-service reporting; it plans reduced subsets of the component library, floorplan patterns, semantic layer, KPI framework, and drill-down analytics; and it omits enterprise search, per-user personalization/variants, and AI-assisted UX entirely.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Role-based launchpad home with spaces/pages and app/KPI tiles** | Full | frontend | — |
| **Fiori design system and UI component library (Horizon, SAPUI5 controls)** | Partial | frontend | Atlas plans a focused in-house kit (data grid, form builder, kanban, dashboard cards, document-flow viewer), not a full design system with theming tokens, accessibility standards, and the breadth of SAPUI5 controls. Later: Grow the kit into a documented design system: theme tokens, a11y audit, and new controls added as app screens demand them. |
| **List report + object page floorplans (transactional work pattern)** | Partial | frontend | Atlas's data grid and form builder cover hand-built list+detail screens, but there is no metadata-driven floorplan generator, draft persistence, or saved table variants. Later: Add a schema-driven page generator that renders list+detail CRUD pages from entity metadata, then layer in drafts and variants. |
| **Overview pages / role-based dashboards** | Full | reporting | — |
| **Analytical list page and multidimensional reporting** | Partial | reporting | Atlas's report builder yields a flat group-by grid with CSV export; no interactive pivoting, drill-down paths, or combined chart+table analysis UI is planned. Later: Add a pivot/drill-down UI and chart rendering on top of existing report-builder queries. |
| **CDS virtual data model and analytical queries (live semantic layer)** | Partial | reporting | Atlas's report builder queries raw entities directly, which preserves the live-on-transactional-data principle, but there is no reusable layered view model, calculated/restricted measures, or hierarchies. Later: Introduce a versioned semantic layer (named reusable views and measures) that the report builder, dashboards, and KPI tiles all consume. |
| **Smart Business KPI framework (Manage KPIs and Reports)** | Partial | reporting | Atlas ships a fixed set of KPI tiles and dashboard cards; end-user KPI authoring, threshold/target rules, color states, and publish-to-home are not planned. Later: Add a "manage KPIs" admin screen where a KPI = saved report query + threshold rules, publishable as a home-page tile. |
| **Self-service query creation and export (Query Browser, custom analytical queries)** | Full | reporting | — |
| **Insight-to-action and intent-based cross-app navigation** | Partial | frontend | Atlas plans a document-flow viewer component, but no generic deep-link/intent framework wiring dashboard cards and report rows to the owning app screens. Later: Define per-entity URL route conventions (deep links) and wire dashboard cards, KPI tiles, and report rows to them. |
| **Enterprise search across business objects** | Out of scope | — | Atlas v1 plans only per-report filters; no global cross-entity search or app finder exists anywhere in the plan. Later: Add a global search endpoint over key entities plus a header omnibox that deep-links into list/detail pages. |
| **Personalization and key-user UI adaptation** | Out of scope | — | Atlas v1 home pages, dashboards, and grids are role-defined and static; no per-user variants, tile rearrangement, or screen adaptation is planned. Later: Persist per-user grid/filter variants and home-tile layout as JSON preference records keyed by user and screen. |
| Joule and AI-assisted UX (NL navigation, smart summarization, easy filter) | Out of scope | — | Flagship 2025 differentiator but not yet baseline-essential, and largely premium/optional even in S/4HANA; nothing AI-related is in the Atlas v1 plan. Later: Once report-builder and search APIs exist, attach an LLM assistant that translates natural language into report definitions and deep links. |

---

## Industry Solutions approach

SAP's S/4HANA industry approach folded most former IS add-ons into a single codebase ("industry to core"), covering roughly 25 industries whose functionality is activated per system through business function sets and the switch framework — activation is largely irreversible, one industry function set per instance, and industry-specific LoB functions are licensed separately from the Enterprise Management core. What the industry layer actually varies is substantial: terminology (Article vs Material, Site vs Plant), industry master data models (retail article/site, patient, equipment), entire vertical process suites (merchandise management, EC&O Equipment & Tools Management, professional-services Commercial Project Management, IS-U billing), regulatory content, and preconfigured SAP Best Practices content applied at setup. The current 2025/2026 direction adds a clean-core posture where deep vertical needs increasingly move to SAP Industry Cloud partner extensions on BTP — notably SAP is discontinuing healthcare IS-H by 2030 in favor of partner solutions. Atlas v1's YAML template layer maps well to the configuration-content slice of this area but plans none of the vertical process logic, industry master data objects, regulatory content, or partner extension ecosystem that practitioners associate with SAP industry solutions.

| S/4HANA capability | Atlas v1 | Atlas module | Notes |
|---|---|---|---|
| **Single-core delivery with industry activation (business function sets / switch framework)** | Partial | industry | Atlas templates toggle modules and apply presets at tenant creation, but there is no deep switch layer that changes the behavior of shared module code per industry (e.g., retail switch altering core MM logistics flows). Later: Add a feature-flag/behavior-variant layer inside modules keyed off the tenant's industry template. |
| **Industry-specific terminology overrides** | Full | industry | — |
| **Industry-specific master data models** | Partial | industry | Typed custom fields (JSONB + metadata registry) extend core entities, but Atlas v1 plans no first-class industry entities such as article variant matrices, store hierarchies, or a patient demographics object. Later: Ship industry entities as optional modules built on the metadata registry, starting with retail article/site. |
| **Industry-specific end-to-end business processes** | Out of scope | — | Atlas v1 templates only configure existing horizontal modules; no industry-specific process logic of any kind is planned. Later: Post-v1 industry process packs as optional modules layered on core (e.g., a retail pack adding assortment/promotion flows). |
| **Preconfigured industry best-practice content applied at provisioning** | Full | industry | — |
| **Metadata-driven field extensibility surfaced across the UI** | Full | core | — |
| **Industry regulatory and statutory compliance** | Out of scope | — | Atlas v1 templates carry only default tax codes; no industry- or country-specific statutory logic, regulated billing, or POC revenue recognition is planned in the industry layer. Later: Country/industry compliance packs per module once a localization framework exists, prioritized by shipped templates. |
| **Breadth of industry coverage (~25 verticals)** | Partial | industry | Atlas v1 ships 5 templates (manufacturing, retail, professional-services, healthcare, construction); deep verticals like utilities, banking, or oil & gas need far more than configuration templates. Later: Grow template coverage via community-contributed YAML templates, pairing deep verticals with later process-pack modules. |
| **Partner and industry-cloud extension ecosystem** | Out of scope | — | Atlas v1 plans no plugin/extension API or marketplace through which third parties could ship industry functionality; templates are first-party YAML only. Later: Define a stable plugin API plus template packaging so third parties can publish installable industry packs. |
| **Lifecycle-safe industry configuration management** | Partial | industry | Idempotent template application at tenant creation is planned, but there is no template versioning or safe re-application/upgrade of templates to existing live tenants. Later: Version templates and add a migration-aware re-apply command that diffs template state against live tenant config. |

---

## Sources

All areas were researched against live web sources in June 2026. Areas marked with a supplementation note additionally drew on embedded S/4HANA knowledge for specific subtopics or where pages could not be fetched; no area relied on the embedded baseline alone.

### Financial Accounting (FI)

*Web research supplemented by embedded knowledge of standard FI transactions.*

- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/651d8af3ea974ad1a4d74449122c620e/523b8a55559ad007e10000000a44538d.html
- https://www.erpresearch.com/en-us/sap-s4-hana-finance-accounting-module
- https://sapinsider.org/articles/mastering-acdoca-7-essential-universal-journal-insights-for-sap-s-4hana-consultants-2025-edition/
- https://learning.sap.com/learning-journeys/implementing-financial-accounting-in-sap-s-4hana
- https://www.ibm.com/think/insights/advanced-financial-closing-and-sap-s4hana
- https://learning.sap.com/courses/customizing-core-settings-in-financial-accounting-in-sap-s4hana/maintaining-taxes-and-tax-codes

### Controlling (CO)

- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/5e23dc8fe9be4fd496f8ab556667ea05/5cd170526837214fe10000000a445394.html
- https://blog.sap-press.com/account-based-co-pa-in-sap-s4hana-how-margin-analysis-works-in-the-universal-journal
- https://blog.sap-press.com/universal-allocation-in-sap-s4hana
- https://community.sap.com/t5/technology-blog-posts-by-members/the-ultimate-guide-to-product-costing-in-sap-s-4hana/ba-p/14223308
- https://www.iqxbusiness.com/iqx-blog/migrating-from-internal-orders-to-sap-wbs-elements-in-s-4hana/
- https://www.pikon.com/en/blog/co-pa-in-s4hana/

### Procurement (MM-PUR)

- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/b54d76b535b74e4aaa852fe31a7974ee/17c6b65334e6b54ce10000000a174cb4.html
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/af9ef57f504840d2b81be8667206d485/4f7eb65334e6b54ce10000000a174cb4.html
- https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-sap/sap-s-4hana-cloud-erp-private-2025-key-innovations-in-sourcing-and/ba-p/14369929
- https://community.sap.com/t5/technology-blog-posts-by-members/flexible-workflows-for-procurement-in-sap-s-4hana/ba-p/14234315
- https://www.certification.guru/certifications/sap-s4hana-cloud-private-edition-sourcing-procurement-certification/
- https://portsapblogging.com/2024/05/15/sap-s-4hana-business-partner-for-mm-p2p-what-changes-why-it-matters-and-how-to-get-it-right/

### Inventory Management & Warehousing (MM-IM / EWM)

*Web research cross-checked against embedded knowledge.*

- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/91b21005dded4984bcccf4a69ae1300c/38b1ba53422bb54ce10000000a174cb4.html
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/9832125c23154a179bfa1784cdc9577a/4ecb88b8b2422afee10000000a42189e.html
- https://www.erpresearch.com/en-us/sap-s4-hana-inventory-management-module
- https://community.sap.com/t5/supply-chain-management-blog-posts-by-members/a-comprehensive-guide-to-sap-s-4hana-extended-warehouse-management-ewm/ba-p/14225196
- https://learning.sap.com/courses/product-cost-planning-in-sap-s-4hana/describing-material-ledger
- https://blog.sap-press.com/an-overview-of-ewm-with-sap-s4hana-embedded-decentralized-and-stock-room-management

### Sales & Distribution (SD)

- https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-sap/sap-s-4hana-2025-key-innovations-in-sales-for-the-cloud-private-edition/ba-p/14317037
- https://blog.sap-press.com/key-functionality-of-sap-s4hana-sales
- https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-sap/sap-s-4hana-advanced-returns-management-a-guide-to-complex-return-setup/ba-p/14184205
- https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-members/advanced-available-to-promise-aatp-in-s-4hana-version-2023/ba-p/13857242
- https://www.proexcellency.com/blogs/sap-online-training/what-s-new-in-sap-sd-in-s-4hana-compared-to-ecc-complete-2025-guide
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/c7894a248ca14f74aca67f97528e5ad7/cb1fbf53f106b44ce10000000a174cb4.html

### Production Planning (PP)

- https://noeldcosta.com/sap-pp-production-planning/
- https://community.sap.com/t5/supply-chain-management-blog-posts-by-sap/overview-of-the-key-functionality-production-planning-and-detailed/ba-p/13409001
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/f899ce30af9044299d573ea30b533f1c/aa35c95360267514e10000000a174cb4.html
- https://blog.sap-press.com/how-does-production-planning-differ-between-sap-erp-and-sap-s4hana
- https://learning.sap.com/learning-journeys/exploring-business-processes-in-sap-s-4hana-production-planning/exploring-principles-and-tools-for-demand-planning
- https://learning.sap.com/courses/configuring-sap-s-4hana-cloud-public-edition-manufacturing-execution/outlining-repetitive-manufacturing

### Quality Management & Plant Maintenance (QM / PM-EAM)

*Web research supplemented by embedded S/4HANA knowledge where pages could not be fetched (SAP Help body content and one SAP Community post returned errors).*

- https://learning.sap.com/learning-journeys/configuring-sap-s-4hana-quality-management
- https://www.erpresearch.com/en-us/sap-s4-hana-quality-management-qms
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/2bc3ee8d1c83404e8cf62418640004f2/cbc48c570c9b7010e10000000a441470.html
- https://www.asug.com/insights/the-evolution-and-enhanced-capabilities-of-sap-s-4hana-asset-management
- https://www.nrx.com/sap-s-4hana-transforms-plant-maintenance/
- https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-sap/asset-management-in-sap-cloud-erp-private-2025-release/ba-p/14240607

### Human Capital Management (HCM / SuccessFactors)

- https://community.sap.com/t5/human-capital-management-blog-posts-by-sap/sap-hcm-for-sap-s-4hana-2025/ba-p/14181762
- https://www.js-soft.com/en/sap-h4s4/
- https://blog.sap-press.com/how-does-sap-successfactors-compare-to-sap-human-capital-management-for-sap-s4hana
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/7c1ef52f3fea49d1944b266772379e52/d33dba53422bb54ce10000000a174cb4.html
- https://www.epiuselabs.com/lets-talk-hcm/bridge-options-sap-successfactors-what-is-h4s4-sap-hcm-for-s4hana-on-premise

### Project System (PS)

*Web research supplemented by embedded S/4HANA knowledge for structuring.*

- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/4dd8cb7b1c484b4b93af84d00f60fdb8/1ad4b65334e6b54ce10000000a174cb4.html
- https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-sap/enterprise-portfolio-and-project-management-in-sap-s-4hana-cloud-public/ba-p/14174389
- https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-sap/the-two-project-control-possibilities-in-sap-s-4hana-cloud-enterprise/ba-p/13577297
- https://blog.sap-press.com/wbss-and-network-structures-in-saps-project-system
- https://blog.sap-press.com/principles-of-event-based-revenue-recognition-ebrr-in-sap-s4hana
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/4dd8cb7b1c484b4b93af84d00f60fdb8/a1e600518c19c557e10000000a44176d.html

### Cross-cutting platform concepts

*Web research supplemented by embedded S/4HANA knowledge for change documents, workflow, and extensibility.*

- https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-sap/understanding-the-universal-journal-in-sap-s-4hana/ba-p/13345726
- https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-sap/faq-cvi-customer-vendor-integration-for-system-conversion-to-sap-s-4hana/ba-p/13740757
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/29b076e23a9f4b0b9d41c5af9c6f7da0/5b2b9cedb9ac455dbe219701e556d98d.html
- https://blogs.sap.com/2016/05/05/moving-to-s4-what-about-your-output-management/
- https://help.sap.com/docs/SAP_S4HANA_CLOUD/b249d650b15e4b3d9fc2077ee921abd0/12032b657e104bb7ac4da02b2d3b3313.html
- https://help.sap.com/docs/SAP_S4HANA_CLOUD/0fa84c9d9c634132b7c4abb9ffdd8f06/4460d7531a4d424de10000000a174cb4.html

### Fiori UX & Embedded Analytics

- https://community.sap.com/t5/technology-blog-posts-by-sap/sap-user-experience-update-what-s-new-for-sap-s-4hana-2025-private-cloud/ba-p/14257694
- https://www.pikon.com/en/blog/what-does-s4hana-embedded-analytics-offer-for-reporting/
- https://www.sap.com/design-system/fiori-design-web/v1-136/page-types/floorplans/when-to-use-which-floorplan
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/6b356c79dea443c4bbeeaf0865e04207/c53deb5765c7be12e10000000a4450e5.html
- https://avotechs.com/blog/sap-fiori-for-s4hana-2025-release/
- https://www.heflo.com/blog/sap-fiori-launchpad-explained

### Industry Solutions approach

- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/8308e6d301d54584a33cd04a9861bc52/f387d66462764ffebb7238244de136e4.html
- https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-sap/business-functions-capability-model-fiori-apps-the-commercial-structure-in/ba-p/13631130
- https://ktern.com/article/sap-business-functions-before-s4hana-move/
- https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/77c07c8d30664260a0b3ff864e6b5e78/d8968357e4879f2de10000000a44147b.html
- https://www.seppmed.com/2026/01/26/hospital-it-sap-is-h-discontinued-in-2030/
- https://www.cbs-consulting.com/us/industry-specific-solutions-in-sap-s-4hana-tailoring-the-platform-to-your-business/
