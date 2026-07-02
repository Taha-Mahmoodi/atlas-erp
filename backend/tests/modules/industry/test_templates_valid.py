"""PLAN 14.1 / D-060: every shipped template validates against _schema.yaml + is parseable, and the
five are MEANINGFULLY different.

Pure validation/parse tests (no DB): the loader reads each YAML, validates it against the
JSON-Schema in industry-templates/_schema.yaml, and parses it into IndustryTemplate. The
distinctness assertions pin the spec's "five meaningfully different templates" claim — different
terminology, modules, COA, custom fields and costing defaults — so a homogenising edit fails here.
"""

import pytest

from app.modules.industry.constants import SHIPPED_TEMPLATES
from app.modules.industry.loader import load_template
from app.modules.industry.schema_validator import IndustrySchemaError, validate_against_schema


@pytest.mark.parametrize("name", SHIPPED_TEMPLATES)
def test_every_shipped_template_validates_and_parses(name):
    """Each shipped template passes JSON-Schema validation and parses into IndustryTemplate with
    exactly one functional currency + a non-empty COA."""
    template = load_template(name)
    assert template.name == name
    functional = [c for c in template.currencies if c.is_functional]
    assert len(functional) == 1
    assert len(template.chart_of_accounts.accounts) >= 1


def test_loader_rejects_unknown_template():
    from app.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        load_template("nonexistent")


def test_schema_validator_rejects_unknown_top_level_key():
    """A template with an extra top-level key is rejected (additionalProperties:false), proving the
    JSON-Schema (not just Pydantic) gates structure."""
    from app.modules.industry.loader import _load_schema

    bad = {
        "name": "manufacturing",
        "display_name": "X",
        "description": "Y",
        "terminology": {},
        "chart_of_accounts": {
            "groups": [],
            "accounts": [{"code": "1", "name": "A", "account_type": "ASSET"}],
        },
        "currencies": [{"code": "USD", "name": "US Dollar"}],
        "modules": {"finance": True},
        "rogue_key": 1,
    }
    with pytest.raises(IndustrySchemaError) as exc:
        validate_against_schema(bad, _load_schema())
    assert "rogue_key" in exc.value.message


def test_schema_validator_rejects_unknown_terminology_term():
    """terminology keys are a CLOSED whitelist — an unknown canonical term is rejected so a typo
    never silently does nothing."""
    from app.modules.industry.loader import _load_schema

    bad = {
        "name": "manufacturing",
        "display_name": "X",
        "description": "Y",
        "terminology": {"made_up_term": "Label"},
        "chart_of_accounts": {
            "groups": [],
            "accounts": [{"code": "1", "name": "A", "account_type": "ASSET"}],
        },
        "currencies": [{"code": "USD", "name": "US Dollar"}],
        "modules": {"finance": True},
    }
    with pytest.raises(IndustrySchemaError):
        validate_against_schema(bad, _load_schema())


# --- the five are meaningfully different ---------------------------------------


def test_healthcare_has_no_manufacturing_and_a_patient_field():
    """Healthcare: customer -> Patient terminology, manufacturing OFF, an insurer/payer custom
    field on the customer (the spec's healthcare distinctives)."""
    template = load_template("healthcare")
    assert template.terminology["customer"] == "Patient"
    assert template.modules["manufacturing"] is False
    customer_fields = {
        f.field_key for f in template.custom_fields if f.entity_key == "sales.customer"
    }
    assert "insurer" in customer_fields


def test_retail_is_fifo_with_a_barcode_field_and_no_manufacturing():
    """Retail: FIFO costing default on its merchandise category, a barcode custom field on the
    item, manufacturing OFF, "Store" warehouse terminology."""
    template = load_template("retail")
    assert template.modules["manufacturing"] is False
    assert template.terminology["warehouse"] == "Store"
    methods = {c.default_costing_method for c in template.item_categories}
    assert methods == {"FIFO"}
    item_fields = {
        f.field_key for f in template.custom_fields if f.entity_key == "inventory.item"
    }
    assert "barcode" in item_fields


def test_manufacturing_is_full_platform_moving_average():
    """Manufacturing: ALL modules on, moving-average costing default — the full-platform base."""
    template = load_template("manufacturing")
    assert all(template.modules.values())
    assert template.modules["manufacturing"] is True
    methods = {c.default_costing_method for c in template.item_categories}
    assert methods == {"MOVING_AVERAGE"}


def test_construction_has_retainage_account_and_field_and_job_terminology():
    """Construction: a Retainage Receivable account in the COA, a retainage custom field, and
    project/production_order -> "Job" terminology."""
    template = load_template("construction")
    account_names = {a.name.lower() for a in template.chart_of_accounts.accounts}
    assert any("retainage" in name for name in account_names)
    all_fields = {f.field_key for f in template.custom_fields}
    assert "retainage_percent" in all_fields
    assert template.terminology["project"] == "Job"
    assert template.terminology["production_order"] == "Job"


def test_professional_services_has_no_inventory_and_billable_rate_field():
    """Professional services: inventory + manufacturing OFF, projects ON, a billable-rate custom
    field on the employee, "Engagement"/"Consultant" terminology."""
    template = load_template("professional-services")
    assert template.modules["inventory"] is False
    assert template.modules["manufacturing"] is False
    assert template.modules["projects"] is True
    assert template.terminology["project"] == "Engagement"
    assert template.terminology["employee"] == "Consultant"
    employee_fields = {
        f.field_key for f in template.custom_fields if f.entity_key == "hr.employee"
    }
    assert "billable_rate" in employee_fields


def test_the_five_terminologies_are_distinct():
    """No two templates ship the identical terminology map — the spec's "meaningfully different"
    requirement at the terminology level."""
    maps = [tuple(sorted(load_template(n).terminology.items())) for n in SHIPPED_TEMPLATES]
    assert len(set(maps)) == len(SHIPPED_TEMPLATES)
