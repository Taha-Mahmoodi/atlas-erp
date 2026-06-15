"""Industry-template Pydantic models (PLAN 14.1 / D-060) — the parsed, type-checked shape of a
template, mirroring ``industry-templates/_schema.yaml``.

Two-layer validation (D-060): the loader FIRST validates a template's raw dict against the
JSON-Schema in ``_schema.yaml`` (the declarative single source of truth — closed whitelists for
terminology terms, module keys, enums), THEN parses it into ``IndustryTemplate`` here for typed
access in the apply path. The JSON-Schema catches structural / whitelist errors with precise
JSON-pointer paths; these Pydantic models give the loader/handlers attribute access and enforce the
few cross-field rules a JSON-Schema is awkward at (exactly one functional currency).

Decimal-bearing wire values (tax rate_percent, approval thresholds, custom-field DECIMAL defaults)
stay STRINGS here (D-015 no-float): the finance/inventory handlers parse them via ``Decimal`` when
they create the rows, never as JSON floats.

These are READ/parse schemas, not request bodies — the apply endpoint takes only a template NAME
(the content is the shipped file), so there is no Create/Update variant.
"""

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Mirrors core.custom_fields.CustomFieldType + the COA/costing enums; kept as literals so the
# schema file and these models stay the single declarative pair (no runtime import of the enums
# here — the handlers map the strings to the enums when they write).
_CUSTOM_FIELD_TYPES = frozenset({"STRING", "NUMBER", "DECIMAL", "BOOL", "DATE"})
_ACCOUNT_TYPES = frozenset({"ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"})
_CASH_FLOW_CATEGORIES = frozenset({"OPERATING", "INVESTING", "FINANCING"})
_COSTING_METHODS = frozenset({"MOVING_AVERAGE", "FIFO"})


class _StrictModel(BaseModel):
    """Forbid unknown keys so a typo in a template surfaces here too (the JSON-Schema's
    additionalProperties:false is the primary gate; this is the parse-side backstop)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AccountGroupSpec(_StrictModel):
    code: str
    name: str
    parent_code: str | None = None
    sort_order: int = 0


class AccountSpec(_StrictModel):
    code: str
    name: str
    account_type: str
    group_code: str | None = None
    is_postable: bool = True
    cash_flow_category: str | None = None
    is_cash_equivalent: bool = False

    @field_validator("account_type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        if value not in _ACCOUNT_TYPES:
            raise ValueError(f"unknown account_type {value!r}")
        return value

    @field_validator("cash_flow_category")
    @classmethod
    def _check_cash_flow(cls, value: str | None) -> str | None:
        if value is not None and value not in _CASH_FLOW_CATEGORIES:
            raise ValueError(f"unknown cash_flow_category {value!r}")
        return value


class ChartOfAccountsSpec(_StrictModel):
    groups: list[AccountGroupSpec] = []
    accounts: list[AccountSpec]


class TaxCodeSpec(_StrictModel):
    code: str
    name: str
    rate_percent: str  # a percentage as a string (D-015): "20" == 20%
    jurisdiction: str | None = None
    is_inclusive: bool = False


class CurrencySpec(_StrictModel):
    code: str
    name: str
    decimal_places: int = 2
    is_functional: bool = False


class UomSpec(_StrictModel):
    code: str
    name: str


class ItemCategorySpec(_StrictModel):
    code: str
    name: str
    default_costing_method: str = "MOVING_AVERAGE"

    @field_validator("default_costing_method")
    @classmethod
    def _check_method(cls, value: str) -> str:
        if value not in _COSTING_METHODS:
            raise ValueError(f"unknown default_costing_method {value!r}")
        return value


class CustomFieldSpec(_StrictModel):
    entity_key: str
    field_key: str
    label: str
    type: str
    required: bool = False
    default: str | None = None

    @field_validator("type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        if value not in _CUSTOM_FIELD_TYPES:
            raise ValueError(f"unknown custom-field type {value!r}")
        return value


class ApprovalPresetsSpec(_StrictModel):
    purchase_order_threshold: str | None = None
    requisition_threshold: str | None = None
    currency_code: str | None = None


class NumberingFormatSpec(_StrictModel):
    prefix: str
    padding: int
    year_reset: bool = False


class IndustryTemplate(_StrictModel):
    """One fully-parsed industry template (D-060). The loader builds this AFTER the raw dict passes
    the JSON-Schema, so the per-field validators here are a typed backstop, not the primary gate."""

    name: str
    display_name: str
    description: str
    terminology: dict[str, str] = {}
    chart_of_accounts: ChartOfAccountsSpec
    tax_codes: list[TaxCodeSpec] = []
    currencies: list[CurrencySpec]
    uoms: list[UomSpec] = []
    item_categories: list[ItemCategorySpec] = []
    modules: dict[str, bool]
    custom_fields: list[CustomFieldSpec] = []
    approval_presets: ApprovalPresetsSpec | None = None
    numbering_formats: dict[str, NumberingFormatSpec] = {}

    @model_validator(mode="after")
    def _exactly_one_functional_currency(self) -> "IndustryTemplate":
        functional = [currency for currency in self.currencies if currency.is_functional]
        if len(functional) != 1:
            raise ValueError(
                "a template must declare exactly one functional currency, "
                f"got {len(functional)}"
            )
        return self
