"""Finance domain-event handlers package (D-011) — cross-module subscribers.

Finance is the bottom of the dependency order, so it is the natural home for the handlers that turn
ANOTHER module's published event into the finance GL effect (the publishing module never imports
finance/service — STRUCTURE §5). The single ``handlers.py`` reached the 400-line cap, so it split
along the §3/§8.4 package rule (the models/ + service/ precedent), one file per cross-module flow:

- ``inventory_cogs``: ``post_stock_valuation_journal`` — the COGS/inventory valuation journal for an
  inventory ``stock.valued`` event (PLAN 5.3, D-020).
- ``procure_to_pay``: ``create_bill_for_match`` — the AP vendor bill for a posted 3-way match (PLAN
  6.4, D-042).
- ``order_to_cash``: ``create_invoice_for_billing`` + ``create_credit_note_for_return`` — the AR
  customer invoice / credit note for a posted sales billing / return (PLAN 7.4, D-046).
- ``production``: ``post_production_variance`` — the residual WIP-variance entry on a
  production-order finish (PLAN 8.2, D-048).
- ``payroll``: ``create_payroll_journal`` — the consolidated payroll journal for a posted HR
  payroll run (PLAN 10.4, D-055).
- ``_shared``: ``_lines_from_postings`` — the signed-postings → balanced one-sided journal-lines
  helper the inventory-COGS and production handlers share.

Every handler builds its journal through the finance posting service (``create_draft_entry`` +
``post_entry``), NEVER raw inserts, so every invariant fires, and links the trigger's document to
the entry's document ('posts' edge). Registration: ``app.main.register_event_handlers`` subscribes
the handlers at the factory (the D-011 seam), so the test harness re-registers after its per-test
reset (D-025). Re-exported here so every ``from app.modules.finance.handlers import X`` import keeps
working from one surface.
"""

from app.modules.finance.handlers.inventory_cogs import post_stock_valuation_journal
from app.modules.finance.handlers.order_to_cash import (
    create_credit_note_for_return,
    create_invoice_for_billing,
)
from app.modules.finance.handlers.payroll import create_payroll_journal
from app.modules.finance.handlers.procure_to_pay import create_bill_for_match
from app.modules.finance.handlers.production import post_production_variance

__all__ = [
    "create_bill_for_match",
    "create_credit_note_for_return",
    "create_invoice_for_billing",
    "create_payroll_journal",
    "post_production_variance",
    "post_stock_valuation_journal",
]
