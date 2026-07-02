"""Domain events CRM PUBLISHES (D-011/D-057). Declarative data only — no logic, no models — so
SALES'
``handlers.py`` may import these typed classes (the STRUCTURE §5 events.py allowance: an event
carries
no behaviour, so a subscriber in another module imports it without any logic).

``OpportunityConverted`` is the SANCTIONED cross-module mechanism for the opportunity → customer +
quote conversion (D-057), the MIRROR of sales' billing → AR-invoice and procurement's
planned-buy → requisition events. CRM OWNS the opportunity; converting it creates a SALES Customer
(if
the opportunity is not already linked to one) AND a SALES Quote — both sales-owned writes. CRM MUST
NOT
call sales' service directly (STRUCTURE §5 forbids importing another module's service). So
``convert_opportunity`` publishes this event carrying everything sales needs, and SALES'
``handlers.py`` subscribes, creates the customer (via sales' OWN customer service, with the supplied
``new_customer_id``) when ``existing_customer_id`` is None + the quote (via sales' OWN quote
service,
with the supplied ``quote_id``), and writes the convert docflow edges (opportunity document →
'converted_to_customer' → customer document; opportunity document → 'converted_to_quote' → quote
document). The handler shares the session, so the customer + quote land in the SAME transaction as
the
convert — all-or-nothing (D-011): any handler failure (a duplicate customer code, an unknown item,
an
unpriceable line) rolls the WHOLE convert back.

WHY CRM PRE-GENERATES THE IDS. CRM records ``converted_customer_id`` / ``converted_quote_id`` on the
opportunity. So it pre-generates the new customer id (for a prospect) + the quote id and passes them
here; the handler creates the customer/quote WITH those exact ids. That lets CRM know both ids
before
the handler runs — no read-back, and SALES never imports crm/queries (no cycle, D-057). The DURABLE
convert link is still the docflow edge the handler writes, NOT a cross-module FK.
"""

import uuid
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.events import DomainEvent
from app.modules.crm.constants import OPPORTUNITY_CONVERTED_EVENT_KEY


class ConvertedQuoteLine(BaseModel):
    """One opportunity line's worth of quote line (D-057), the payload sales' handler turns into a
    quote line. Plain frozen data: the opaque inventory item + base UoM ids (D-029), the quantity,
    and
    the unit price (the opportunity line's estimated unit price). The handler passes these straight
    to
    the sales quote service (which validates the item/UoM and computes the line amount)."""

    model_config = ConfigDict(frozen=True)

    item_id: uuid.UUID
    uom_id: uuid.UUID
    quantity: Decimal
    unit_price: Decimal
    description: str | None = None


class OpportunityConverted(DomainEvent):
    """An opportunity was converted to a customer + quote (D-057). SALES' ``handlers.py`` subscribes
    and, in the SAME transaction: creates the sales Customer when ``existing_customer_id`` is None
    (with id ``new_customer_id``, from ``company_name`` / ``contact_name`` / ``email`` /
    ``currency_code`` + the ``customer_code``), then creates the sales Quote (with id ``quote_id``)
    for
    that customer (existing or just-created) from ``lines``, and writes the convert docflow edges
    (opportunity document → customer document / → quote document).

    - ``opportunity_id`` + ``opportunity_number`` + ``document_id`` — the opportunity
    (``document_id``
      is the core_documents id the handler links the customer/quote documents to).
    - ``existing_customer_id`` — the OPAQUE sales customer id when the opportunity already links an
      EXISTING customer (then the handler skips customer creation and only quotes); None for a
      prospect.
    - ``new_customer_id`` — the id the handler creates the NEW customer with (CRM pre-generated it
    so it
      can record ``converted_customer_id``); None when ``existing_customer_id`` is set.
    - ``quote_id`` — the id the handler creates the quote with (CRM pre-generated it so it can
    record
      ``converted_quote_id``).
    - ``customer_code`` — the code the handler creates the NEW customer with (deterministic from the
      opportunity number; unused when ``existing_customer_id`` set).
    - ``company_name`` / ``contact_name`` / ``email`` — the new customer's master fields.
    - ``currency_code`` — the customer's default currency + the quote's currency.
    - ``lines`` — the per-line quote specs (see ``ConvertedQuoteLine``), non-empty (CRM rejects a
      no-line convert up front, so the handler always has at least one line)."""

    key: ClassVar[str] = OPPORTUNITY_CONVERTED_EVENT_KEY

    opportunity_id: uuid.UUID
    opportunity_number: str
    document_id: uuid.UUID
    existing_customer_id: uuid.UUID | None
    new_customer_id: uuid.UUID | None
    quote_id: uuid.UUID
    customer_code: str
    company_name: str
    contact_name: str | None
    email: str | None
    currency_code: str
    lines: tuple[ConvertedQuoteLine, ...]


__all__ = [
    "ConvertedQuoteLine",
    "OpportunityConverted",
]
