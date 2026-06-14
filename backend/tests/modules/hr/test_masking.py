"""THE key D-009 masking test (PLAN 10.1, D-052): the headline integration of the field-level read
masking serializer on the employee's compensation/PII.

Two complementary angles:
- SERIALIZER-LEVEL (the contract): the same ``EmployeeRead`` serialized with the
  ``current_permissions`` ContextVar holding ``hr.employee.read_compensation`` shows the real
  salary/national_id/etc.; serialized WITHOUT it shows them masked (None). Exercised via the
  ``permissions_context`` fixture both ways, asserting the masking is PER-REQUEST (the ContextVar),
  not stored on the row — the same model instance yields different output under different contexts.
- WRITE-SIDE (the D-009 convention): the masked fields are EXCLUDED from ``EmployeeUpdate`` and
  present on ``EmployeeRead`` / ``EmployeeCreate`` / the dedicated ``EmployeeCompensationUpdate``.

The over-the-wire RBAC angle (a manager WITHOUT read_compensation gets masked reads through the API)
lives in test_hr_api.py; here we pin the serializer mechanics directly.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

from app.modules.hr.constants import HR_EMPLOYEE_READ_COMPENSATION
from app.modules.hr.models import Employee
from app.modules.hr.schemas import (
    EmployeeCompensationUpdate,
    EmployeeCreate,
    EmployeeRead,
    EmployeeUpdate,
)

_SENSITIVE_FIELDS = (
    "base_salary",
    "national_id",
    "tax_id",
    "date_of_birth",
    "bank_account",
)


def _employee_row() -> Employee:
    """An ORM employee carrying real compensation/PII — never committed; just a source for
    ``EmployeeRead.model_validate`` so the masking runs over realistic field values."""
    return Employee(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        employee_code="EMP-MASK",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@acme.test",
        status="ACTIVE",
        employment_type="FULL_TIME",
        hire_date=date(2020, 1, 1),
        base_salary=Decimal("123456"),
        currency_code="USD",
        national_id="NID-SECRET",
        tax_id="TAX-SECRET",
        date_of_birth=date(1990, 5, 4),
        bank_account="BANK-SECRET",
        # The TimestampMixin defaults fire only on flush; this row is never committed, so set them
        # explicitly for the schema's required datetime fields.
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
        updated_at=datetime(2020, 1, 1, tzinfo=UTC),
    )


def test_compensation_visible_with_permission(
    permissions_context: Callable[[frozenset[str]], None],
) -> None:
    """A viewer WITH hr.employee.read_compensation sees the real salary + PII."""
    permissions_context(frozenset({HR_EMPLOYEE_READ_COMPENSATION}))
    read = EmployeeRead.model_validate(_employee_row())
    dumped = read.model_dump()
    assert dumped["base_salary"] == Decimal("123456")
    assert dumped["currency_code"] == "USD"
    assert dumped["national_id"] == "NID-SECRET"
    assert dumped["tax_id"] == "TAX-SECRET"
    assert dumped["date_of_birth"] == date(1990, 5, 4)
    assert dumped["bank_account"] == "BANK-SECRET"
    # The non-sensitive fields are always present regardless of the permission.
    assert dumped["first_name"] == "Ada"
    assert dumped["employee_code"] == "EMP-MASK"


def test_compensation_masked_without_permission(
    permissions_context: Callable[[frozenset[str]], None],
) -> None:
    """The SAME employee serialized WITHOUT the permission shows the sensitive fields as None, while
    the non-sensitive fields stay visible."""
    permissions_context(frozenset())
    read = EmployeeRead.model_validate(_employee_row())
    dumped = read.model_dump()
    assert dumped["base_salary"] is None
    assert dumped["currency_code"] is None
    assert dumped["national_id"] is None
    assert dumped["tax_id"] is None
    assert dumped["date_of_birth"] is None
    assert dumped["bank_account"] is None
    # Structural fields remain visible — masking is field-level, not row-level.
    assert dumped["first_name"] == "Ada"
    assert dumped["employee_code"] == "EMP-MASK"


def test_masking_is_per_request_not_stored(
    permissions_context: Callable[[frozenset[str]], None],
) -> None:
    """Masking is a per-request serialization concern (the ContextVar), NOT a property of the row:
    ONE model instance yields the real values under a permitted context and None under an
    unpermitted one. Switching the context between dumps flips the output on the same object."""
    read = EmployeeRead.model_validate(_employee_row())

    permissions_context(frozenset({HR_EMPLOYEE_READ_COMPENSATION}))
    assert read.model_dump()["base_salary"] == Decimal("123456")

    permissions_context(frozenset())
    assert read.model_dump()["base_salary"] is None

    permissions_context(frozenset({HR_EMPLOYEE_READ_COMPENSATION}))
    assert read.model_dump()["base_salary"] == Decimal("123456")


def test_masking_fails_closed_with_unrelated_permissions(
    permissions_context: Callable[[frozenset[str]], None],
) -> None:
    """Holding OTHER hr permissions (read, manage) but NOT read_compensation still masks the
    sensitive fields — the serializer checks the SPECIFIC compensation key, not "any hr access". A
    manager who can edit an employee cannot thereby see their pay (D-052)."""
    permissions_context(frozenset({"hr.employee.read", "hr.employee.manage"}))
    read = EmployeeRead.model_validate(_employee_row())
    dumped = read.model_dump()
    for field in _SENSITIVE_FIELDS:
        assert dumped[field] is None, field
    assert dumped["currency_code"] is None


def test_masked_fields_excluded_from_update_schema() -> None:
    """D-009 write-side convention: the masked compensation/PII fields are ABSENT from
    ``EmployeeUpdate`` (so a general update can never null pay), but present on ``EmployeeRead``,
    ``EmployeeCreate`` and the dedicated ``EmployeeCompensationUpdate``."""
    for field in _SENSITIVE_FIELDS:
        assert field not in EmployeeUpdate.model_fields, field
        assert field in EmployeeRead.model_fields, field
        assert field in EmployeeCreate.model_fields, field
        assert field in EmployeeCompensationUpdate.model_fields, field
    # currency_code is likewise excluded from the general update but on the compensation payload.
    assert "currency_code" not in EmployeeUpdate.model_fields
    assert "currency_code" in EmployeeCompensationUpdate.model_fields
