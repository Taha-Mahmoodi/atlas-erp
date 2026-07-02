"""The report-builder WHITELIST registry (PLAN 13.2, D-059): the ONLY entities and columns an
ad-hoc report may ever touch.

THE SECURITY MODEL (D-059, CRITICAL). The report builder must NOT allow querying arbitrary
tables/columns — that would be a SQL-injection / data-exfiltration surface. So every reportable
thing is declared HERE, as data: a ``ReportableEntity`` names a stable ``key``
(``"finance.journal_lines"``), the ORM model CLASS to query, the SOURCE module's read permission
that gates it (mirroring the dashboard's role-based gating, D-058), and a dict of allowed
``ReportColumn``s. A report request can ONLY name a registered entity, a SUBSET of its registered
columns, filters/group-by over columns flagged ``filterable``/``groupable``, and aggregations over
columns flagged ``is_aggregatable``. Anything else is a 400 — the builder never reflects on the
model beyond what the registry declares, and the column-name → ORM attribute lookup goes through
the registry's allow-list (never ``getattr`` on raw request input against the model).

THE MODEL-IMPORT EXCEPTION (D-059, STRUCTURE §5). Reporting is otherwise a LEAF that reads only
other modules' ``queries`` downward (D-058). This registry is the ONE place reporting imports the
models — a READ-ONLY query-construction need: the builder selects/filters/groups over the model
classes through the tenant-filtered session (so ``core/tenancy.do_orm_execute`` auto-scopes every
select, D-007). Reporting does NOT call the models' services and writes nothing. finance / inventory
/ sales / procurement / hr are all OLDER and import nothing from reporting — one-directional, NO
cycle (grep-verified, D-059).

THE MASKED-COLUMN EXCLUSION (D-009/D-052, D-059). MASKED / sensitive columns are EXCLUDED from the
whitelist outright — they have no ``ReportColumn`` entry, so they can never be selected, filtered,
grouped, or aggregated through the builder. The HR ``Employee`` entity exposes ONLY non-sensitive
columns (code, name, department/position id, status, type, hire_date); its compensation + PII
(``base_salary``, ``national_id``, ``tax_id``, ``date_of_birth``, ``bank_account``,
``currency_code``) are deliberately absent. Requesting one is a 400 ``reporting.invalid_report``
"unknown column" — masked data is not exposable through reports, by construction.

THE INITIAL WHITELIST (a SAFE cross-module starter set): finance journal lines + accounts,
inventory items + stock moves, sales orders, procurement purchase orders, and the masked-excluded HR
employee entity. Money/quantity columns are typed ``"number"`` (Decimal); the builder JSON-encodes
them as exact strings (D-015).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import InstrumentedAttribute

from app.modules.finance.constants import FINANCE_ACCOUNT_READ, FINANCE_JOURNAL_READ
from app.modules.finance.models import Account, JournalLine
from app.modules.hr.constants import HR_EMPLOYEE_READ
from app.modules.hr.models import Employee
from app.modules.inventory.constants import INVENTORY_ITEM_READ, INVENTORY_MOVE_READ
from app.modules.inventory.models import Item, StockMove
from app.modules.procurement.constants import PROCUREMENT_PO_READ
from app.modules.procurement.models import PurchaseOrder
from app.modules.sales.constants import SALES_ORDER_READ
from app.modules.sales.models import SalesOrder

# The column wire types. ``number`` covers MoneyType / QuantityType / Integer (Decimal or int on the
# Python side — JSON-encoded exact as strings for money/qty); ``str``/``date``/``bool`` map to the
# obvious Python types. The builder coerces a filter value to the column's type before binding it.
ColumnType = str  # one of: "str" | "number" | "date" | "bool"


@dataclass(frozen=True)
class ReportColumn:
    """One whitelisted column on a reportable entity (D-059). ``attr`` is the ORM attribute the
    builder selects/filters/groups on (a real :class:`InstrumentedAttribute`, resolved at
    registration — NEVER ``getattr`` on raw request input). ``label`` is the UI display name;
    ``type`` is the wire type (str/number/date/bool). The three flags are the per-column capability
    gates the builder enforces: ``filterable`` (may appear in a filter), ``groupable`` (may appear
    in group-by — its values must be low-cardinality / indexed), ``is_aggregatable`` (a numeric
    column SUM/AVG/MIN/MAX may target). A column absent from an entity's dict does not exist for
    the builder (the whitelist is closed)."""

    attr: InstrumentedAttribute[Any]
    label: str
    type: ColumnType
    filterable: bool = True
    groupable: bool = False
    is_aggregatable: bool = False


@dataclass(frozen=True)
class ReportableEntity:
    """One whitelisted reportable entity (D-059): a stable ``key``, the ORM ``model`` the builder
    queries (tenant-filtered via ``do_orm_execute``), the SOURCE module's read ``source_permission``
    that gates it (role-based, mirroring the dashboard), and its allowed ``columns`` keyed by the
    name a request uses. ``label`` is the UI display name; ``default_order_column`` is the stable
    sort key the builder ORDER-BYs (defaults to the model PK ``id`` when unset)."""

    key: str
    label: str
    model: type[Any]
    source_permission: str
    columns: dict[str, ReportColumn] = field(default_factory=dict)
    default_order_column: str | None = None


def _col(
    attr: InstrumentedAttribute[Any],
    label: str,
    type_: ColumnType,
    *,
    filterable: bool = True,
    groupable: bool = False,
    aggregatable: bool = False,
) -> ReportColumn:
    return ReportColumn(
        attr=attr,
        label=label,
        type=type_,
        filterable=filterable,
        groupable=groupable,
        is_aggregatable=aggregatable,
    )


# --- The whitelist (D-059) ----------------------------------------------------
# A SAFE initial cross-module set. NO masked/sensitive column appears anywhere here (the HR entity's
# exclusion is the explicit case; the others carry no masked columns). Group-by columns are
# low-cardinality / indexed (status, type, account_id, item_id, etc., per each model's indexes).

_ENTITIES: tuple[ReportableEntity, ...] = (
    ReportableEntity(
        key="finance.journal_lines",
        label="Journal Lines",
        model=JournalLine,
        source_permission=FINANCE_JOURNAL_READ,
        default_order_column="line_number",
        columns={
            "account_id": _col(JournalLine.account_id, "Account", "str", groupable=True),
            "posting_date": _col(
                JournalLine.posting_date, "Posting Date", "date", groupable=True
            ),
            "is_posted": _col(JournalLine.is_posted, "Posted", "bool", groupable=True),
            "currency_code": _col(
                JournalLine.currency_code, "Currency", "str", groupable=True
            ),
            "line_number": _col(JournalLine.line_number, "Line", "number", aggregatable=False),
            "transaction_debit_amount": _col(
                JournalLine.transaction_debit_amount, "Debit", "number", aggregatable=True
            ),
            "transaction_credit_amount": _col(
                JournalLine.transaction_credit_amount, "Credit", "number", aggregatable=True
            ),
            "functional_debit_amount": _col(
                JournalLine.functional_debit_amount, "Functional Debit", "number", aggregatable=True
            ),
            "functional_credit_amount": _col(
                JournalLine.functional_credit_amount,
                "Functional Credit",
                "number",
                aggregatable=True,
            ),
        },
    ),
    ReportableEntity(
        key="finance.accounts",
        label="Accounts",
        model=Account,
        source_permission=FINANCE_ACCOUNT_READ,
        default_order_column="code",
        columns={
            "code": _col(Account.code, "Code", "str"),
            "name": _col(Account.name, "Name", "str"),
            "account_type": _col(Account.account_type, "Type", "str", groupable=True),
            "normal_balance": _col(Account.normal_balance, "Normal Balance", "str", groupable=True),
            "is_postable": _col(Account.is_postable, "Postable", "bool", groupable=True),
            "is_active": _col(Account.is_active, "Active", "bool", groupable=True),
            "is_cash_equivalent": _col(
                Account.is_cash_equivalent, "Cash Equivalent", "bool", groupable=True
            ),
        },
    ),
    ReportableEntity(
        key="inventory.items",
        label="Items",
        model=Item,
        source_permission=INVENTORY_ITEM_READ,
        default_order_column="item_code",
        columns={
            "item_code": _col(Item.item_code, "Item Code", "str"),
            "name": _col(Item.name, "Name", "str"),
            "item_type": _col(Item.item_type, "Type", "str", groupable=True),
            "category_id": _col(Item.category_id, "Category", "str", groupable=True),
            "costing_method": _col(Item.costing_method, "Costing Method", "str", groupable=True),
            "tracking_mode": _col(Item.tracking_mode, "Tracking", "str", groupable=True),
            "is_active": _col(Item.is_active, "Active", "bool", groupable=True),
        },
    ),
    ReportableEntity(
        key="inventory.stock_moves",
        label="Stock Moves",
        model=StockMove,
        source_permission=INVENTORY_MOVE_READ,
        default_order_column="move_number",
        columns={
            "move_number": _col(StockMove.move_number, "Move Number", "str"),
            "move_type": _col(StockMove.move_type, "Move Type", "str", groupable=True),
            "item_id": _col(StockMove.item_id, "Item", "str", groupable=True),
            "move_date": _col(StockMove.move_date, "Move Date", "date", groupable=True),
            "quantity": _col(StockMove.quantity, "Quantity", "number", aggregatable=True),
            "unit_cost": _col(StockMove.unit_cost, "Unit Cost", "number", aggregatable=True),
        },
    ),
    ReportableEntity(
        key="sales.orders",
        label="Sales Orders",
        model=SalesOrder,
        source_permission=SALES_ORDER_READ,
        default_order_column="order_number",
        columns={
            "order_number": _col(SalesOrder.order_number, "Order Number", "str"),
            "status": _col(SalesOrder.status, "Status", "str", groupable=True),
            "customer_id": _col(SalesOrder.customer_id, "Customer", "str", groupable=True),
            "currency_code": _col(SalesOrder.currency_code, "Currency", "str", groupable=True),
            "order_date": _col(SalesOrder.order_date, "Order Date", "date", groupable=True),
            "requested_date": _col(SalesOrder.requested_date, "Requested Date", "date"),
            "total_amount": _col(SalesOrder.total_amount, "Total", "number", aggregatable=True),
        },
    ),
    ReportableEntity(
        key="procurement.purchase_orders",
        label="Purchase Orders",
        model=PurchaseOrder,
        source_permission=PROCUREMENT_PO_READ,
        default_order_column="po_number",
        columns={
            "po_number": _col(PurchaseOrder.po_number, "PO Number", "str"),
            "status": _col(PurchaseOrder.status, "Status", "str", groupable=True),
            "vendor_id": _col(PurchaseOrder.vendor_id, "Vendor", "str", groupable=True),
            "currency_code": _col(PurchaseOrder.currency_code, "Currency", "str", groupable=True),
            "order_date": _col(PurchaseOrder.order_date, "Order Date", "date", groupable=True),
            "expected_date": _col(PurchaseOrder.expected_date, "Expected Date", "date"),
            "total_amount": _col(PurchaseOrder.total_amount, "Total", "number", aggregatable=True),
        },
    ),
    # HR employees — the MASKED-EXCLUSION case (D-009/D-052/D-059): ONLY non-sensitive columns.
    # base_salary / currency_code / national_id / tax_id / date_of_birth / bank_account are
    # DELIBERATELY ABSENT, so the builder cannot select/filter/group/aggregate them — requesting one
    # is "unknown column" (400). Masked data is not exposable through reports, by construction.
    ReportableEntity(
        key="hr.employees",
        label="Employees",
        model=Employee,
        source_permission=HR_EMPLOYEE_READ,
        default_order_column="employee_code",
        columns={
            "employee_code": _col(Employee.employee_code, "Employee Code", "str"),
            "first_name": _col(Employee.first_name, "First Name", "str"),
            "last_name": _col(Employee.last_name, "Last Name", "str"),
            "department_id": _col(Employee.department_id, "Department", "str", groupable=True),
            "position_id": _col(Employee.position_id, "Position", "str", groupable=True),
            "status": _col(Employee.status, "Status", "str", groupable=True),
            "employment_type": _col(
                Employee.employment_type, "Employment Type", "str", groupable=True
            ),
            "hire_date": _col(Employee.hire_date, "Hire Date", "date", groupable=True),
        },
    ),
)

# Keyed by entity key for O(1) lookup; the builder + the entities-list endpoint read this.
REPORT_REGISTRY: dict[str, ReportableEntity] = {entity.key: entity for entity in _ENTITIES}


def get_entity(key: str) -> ReportableEntity | None:
    """The whitelisted entity for ``key``, or None (an unknown key → 400 in the builder)."""
    return REPORT_REGISTRY.get(key)


def list_entities() -> list[ReportableEntity]:
    """Every whitelisted entity in declaration order (the entities-list endpoint serves this; the
    router filters it to the entities the caller's role permits)."""
    return list(_ENTITIES)


__all__ = [
    "REPORT_REGISTRY",
    "ReportColumn",
    "ReportableEntity",
    "get_entity",
    "list_entities",
]
