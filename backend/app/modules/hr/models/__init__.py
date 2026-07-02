"""HR models package (STRUCTURE §3: one file per aggregate concern, each <400 lines).

PLAN 10.1's HCM masters live in ``org`` (the ``Department``, ``Position`` and ``Employee`` masters
with the D-009 masked compensation/PII). PLAN 10.2 adds ``leave`` (the ``LeaveType`` config, the
running ``LeaveBalance`` per employee per type, and the ``LeaveRequest`` document). PLAN 10.3 adds
``time`` (the ``Timesheet`` header + its ``TimeEntry`` lines, with project/cost-centre allocation).
PLAN 10.4 adds ``payroll`` (the ``PayrollRun`` header + its ``PayrollRunLine`` lines — the
simplistic flat-tax gross→net run that posts a consolidated finance journal via the event bus).
Re-exported here so call sites use one import (``from app.modules.hr.models import Employee``) and
the alembic env.py /
tenancy mapper-enumeration suite see every model through this package.

The package split (10.1 shipped a single ``models.py``) keeps each concern under the 400-line cap as
leave lands — a behaviour-preserving move, the manufacturing/inventory models/ precedent.
"""

from app.modules.hr.models.leave import LeaveBalance, LeaveRequest, LeaveType
from app.modules.hr.models.org import Department, Employee, Position
from app.modules.hr.models.payroll import PayrollRun, PayrollRunLine
from app.modules.hr.models.time import TimeEntry, Timesheet

__all__ = [
    "Department",
    "Employee",
    "LeaveBalance",
    "LeaveRequest",
    "LeaveType",
    "PayrollRun",
    "PayrollRunLine",
    "Position",
    "TimeEntry",
    "Timesheet",
]
