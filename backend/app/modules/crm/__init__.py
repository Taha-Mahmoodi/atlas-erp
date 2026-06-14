"""CRM module (PLAN 12.1, the SINGLE Phase 12 plan) — the CRM-lite pre-sales pipeline.

PLAN 12.1 delivers the deliberately small CRM core (s4hana-parity §CRM/Sales-pipeline scope): LEADS
that QUALIFY and CONVERT into OPPORTUNITIES, an opportunity KANBAN whose STAGE is the column (moving
a
card = moving the stage), ACTIVITIES (calls/emails/meetings/tasks/notes) logged against a lead OR an
opportunity, and the headline CONVERT-TO-CUSTOMER+QUOTE that turns a won opportunity into a real
sales
Customer + Quote. Everything else CRM (campaigns, marketing automation, contact/account hierarchies,
forecasting/pipeline analytics, service tickets, opportunity teams/competitors) is explicitly OUT of
v1 — recorded in the parity doc (D-057).

THE CROSS-MODULE CONVERT MODEL (the load-bearing idea, D-057 / D-011 / STRUCTURE §5). The
opportunity → customer + quote conversion is a SALES write (a Customer + a Quote are sales-owned
documents). CRM MUST NOT import sales/service (STRUCTURE §5). So `convert_opportunity` PUBLISHES an
``OpportunityConverted`` event and SALES' ``handlers.py`` creates the Customer (if the opportunity
is
not already linked to one) AND the Quote through SALES' OWN service in the SAME transaction —
exactly
the billing → AR-invoice / planned-buy → requisition precedent (the publishing module never calls
the
owning module's service). CRM reads ``sales/queries`` DOWNWARD (``customer_exists`` — to skip
creating
a customer when one is already linked); SALES imports ``crm/events`` declaratively (the §5
events-only
allowance, D-011). finance/inventory/sales are OLDER modules that import nothing from crm, so
crm→{sales,inventory,finance,hr}/queries is one-directional and crm←sales/events is events-only — NO
cycle (verified, D-057).

THE THREE ENTITIES (D-057).

- ``Lead`` — an unqualified inbound contact (company/contact/email/phone, source, estimated value).
  ``status`` runs NEW → CONTACTED → QUALIFIED → CONVERTED (or DISQUALIFIED). A QUALIFIED lead
  converts
  to an opportunity: ``convert_lead_to_opportunity`` creates the ``Opportunity``, copies the
  company/contact/value, links ``source_lead_id`` + sets the lead's ``converted_opportunity_id`` +
  status CONVERTED. Auto-numbered LEAD-… for traceability (D-057).
- ``Opportunity`` — a qualified deal in the pipeline. ``stage`` IS THE KANBAN COLUMN: PROSPECTING →
  QUALIFICATION → PROPOSAL → NEGOTIATION → WON | LOST. ``move_stage`` is the kanban move (validated
  transitions; WON/LOST are terminal). Optional ``OpportunityLine`` rows (expected products) become
  the quote lines on convert. Auto-numbered OPP-….
- ``Activity`` — a logged interaction (CALL/EMAIL/MEETING/TASK/NOTE) against EXACTLY ONE of a lead
OR
  an opportunity (a service + DB CHECK enforce exactly-one-parent). ``status`` OPEN → COMPLETED |
  CANCELLED.

CROSS-MODULE IDS ARE OPAQUE (D-029/§5). ``owner_employee_id`` is an OPAQUE hr employee id (nullable,
validated via ``hr/queries.employee_exists`` when set). An opportunity's ``customer_id`` is an
OPAQUE
sales customer id (nullable, validated via ``sales/queries.customer_exists`` when set). An
opportunity
LINE's ``item_id`` is an OPAQUE inventory item id (validated via ``inventory/queries.item_exists``).
None of these is a cross-module FK. The ``converted_customer_id`` / ``converted_quote_id`` on a
converted opportunity are recorded for the API, but the DURABLE convert link is the docflow edge the
sales handler writes (opportunity → 'converted_to_customer'/'converted_to_quote'), not an FK — the
billing-side precedent.

Structure (each <400 lines, STRUCTURE §3/§8.4): ``constants.py``, ``models.py``, ``schemas.py``,
``service/`` (leads / opportunities / activities / convert), ``events.py``, ``queries.py``,
``router.py`` + sibling routers (ONE surface at ``/api/v1/crm``). No ``handlers.py`` here — CRM
publishes ``OpportunityConverted`` but subscribes to nothing; SALES owns the handler (D-057).
"""
