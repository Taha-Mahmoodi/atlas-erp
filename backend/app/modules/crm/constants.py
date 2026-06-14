"""CRM (CRM-lite) constants (STRUCTURE §3): the lead / opportunity / activity enums, permission
keys,
the auto-number sequences, and the convert docflow link types + the OpportunityConverted event key —
registered into the core RBAC catalog at import (D-009).

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap) — PLAN
12.1's
CRM-lite core sits well under that.

IDENTITY + NUMBERING (D-057). Both ``Lead`` and ``Opportunity`` are AUTO-NUMBERED with a gapless
per-tenant sequence claimed AT CREATION (the procurement-document precedent): a lead gets LEAD-…, an
opportunity OPP-…, so each is referenceable the moment it exists and the pipeline is traceable.
Neither registers a core_documents entry in v1 — the convert link to the sales customer/quote is a
docflow edge written by the sales handler, but the lead/opportunity themselves are CRM pipeline
rows,
not docflow documents (an opportunity gets a core_documents registration ONLY to carry the convert
docflow edges — see ``models.py`` ``Opportunity`` DocumentMixin).

THE KANBAN = THE OPPORTUNITY STAGE (D-057). ``OpportunityStage`` IS the set of kanban columns;
moving
a card from one column to another IS ``move_stage``. There is no separate "column" entity.

THE CONVERT IS A SALES WRITE VIA THE EVENT BUS (D-057, D-011, STRUCTURE §5). ``convert_opportunity``
publishes ``OpportunityConverted`` (key below); SALES' handlers.py creates the customer (if new) +
the
quote and writes the convert docflow edges. CRM never imports sales/service.
"""

from enum import StrEnum

from app.core.rbac import register_permissions


class LeadStatus(StrEnum):
    """Lifecycle of a LEAD (PLAN 12.1, D-057). The service owns every transition (CLAUDE.md rule 7).

    - **NEW** — just captured (the default at creation).
    - **CONTACTED** — first outreach made.
    - **QUALIFIED** — vetted as a real opportunity-in-waiting; a QUALIFIED lead may convert to an
      opportunity.
    - **DISQUALIFIED** — not a fit; terminal.
    - **CONVERTED** — turned into an opportunity (``convert_lead_to_opportunity`` set this and the
      ``converted_opportunity_id``); terminal.
    """

    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    CONVERTED = "CONVERTED"


class OpportunityStage(StrEnum):
    """The KANBAN COLUMNS of the opportunity pipeline (PLAN 12.1, D-057). The stage IS the column;
    ``move_stage`` moves the card. The service owns the allowed transitions:

    - **PROSPECTING** — initial interest (the default at creation).
    - **QUALIFICATION** — qualifying the deal.
    - **PROPOSAL** — a proposal/quote is out.
    - **NEGOTIATION** — negotiating terms.
    - **WON** — closed-won; TERMINAL. ``convert_opportunity`` sets WON (a won deal becomes a
    customer +
      quote). A WON opportunity cannot move stage again.
    - **LOST** — closed-lost; TERMINAL.

    Allowed moves (D-057): any OPEN stage (PROSPECTING/QUALIFICATION/PROPOSAL/NEGOTIATION) may move
    to
    any other OPEN stage (forward or backward — a deal can slip back) or to WON/LOST (closing it). A
    terminal stage (WON/LOST) cannot move — the deal is closed (reopening would be a new
    opportunity).
    """

    PROSPECTING = "PROSPECTING"
    QUALIFICATION = "QUALIFICATION"
    PROPOSAL = "PROPOSAL"
    NEGOTIATION = "NEGOTIATION"
    WON = "WON"
    LOST = "LOST"


# The OPEN (non-terminal) stages — a card in one of these may move freely; the terminal stages
# (WON/LOST) close the deal. The kanban board renders a column per stage in THIS declared order.
OPEN_OPPORTUNITY_STAGES: tuple[OpportunityStage, ...] = (
    OpportunityStage.PROSPECTING,
    OpportunityStage.QUALIFICATION,
    OpportunityStage.PROPOSAL,
    OpportunityStage.NEGOTIATION,
)
TERMINAL_OPPORTUNITY_STAGES: tuple[OpportunityStage, ...] = (
    OpportunityStage.WON,
    OpportunityStage.LOST,
)
# The full column order the kanban board returns (open columns then the closed columns).
KANBAN_STAGE_ORDER: tuple[OpportunityStage, ...] = (
    *OPEN_OPPORTUNITY_STAGES,
    *TERMINAL_OPPORTUNITY_STAGES,
)


class ActivityType(StrEnum):
    """The kind of an ACTIVITY (PLAN 12.1, D-057) — a logged interaction. Informational typing only;
    every type follows the same OPEN → COMPLETED/CANCELLED lifecycle.

    CALL | EMAIL | MEETING | TASK | NOTE. A NOTE is typically created already COMPLETED (a recorded
    fact), the others usually OPEN (a planned action) — but the service imposes no type→status rule.
    """

    CALL = "CALL"
    EMAIL = "EMAIL"
    MEETING = "MEETING"
    TASK = "TASK"
    NOTE = "NOTE"


class ActivityStatus(StrEnum):
    """Lifecycle of an ACTIVITY (PLAN 12.1, D-057).

    - **OPEN** — planned / outstanding (the default at creation).
    - **COMPLETED** — done (``complete_activity`` stamps ``completed_date``); terminal.
    - **CANCELLED** — abandoned; terminal.
    """

    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# --- Numbering (D-057, D-012/D-040): auto LEAD- / OPP- gapless per-tenant sequences --------------
# Claimed AT CREATION (the procurement-document precedent) so a lead/opportunity is referenceable
# the
# moment it exists; year-resetting (LEAD-2026-00001 / OPP-2026-00001). Gaplessness for committed
# rows
# falls out of ACID (creation is the committing transaction).
LEAD_SEQUENCE_NAME = "crm.lead"
LEAD_NUMBER_PREFIX = "LEAD"
LEAD_NUMBER_PADDING = 5

OPPORTUNITY_SEQUENCE_NAME = "crm.opportunity"
OPPORTUNITY_NUMBER_PREFIX = "OPP"
OPPORTUNITY_NUMBER_PADDING = 5

# An opportunity registers a core_documents entry (doc_type below) so the SALES convert handler can
# write the convert docflow edge to the quote document (opportunity → quote). The opportunity's
# gapless
# number is its registry doc_number. A lead is NOT a docflow document (no registry entry).
OPPORTUNITY_DOC_TYPE = "crm.opportunity"

# Convert docflow link type (D-012 vocabulary, D-057). The edge is predecessor → successor named
# from
# the predecessor's (the opportunity's) point of view: the opportunity is "converted_to_quote" the
# sales quote it created — written by SALES' handler when it creates the quote (the durable convert
# link is docflow, NOT a cross-module FK; the billing → invoice precedent). There is NO opportunity
# →
# customer edge: a sales Customer is a MASTER (not a docflow document), so the customer link is the
# opportunity's recorded opaque ``converted_customer_id`` only.
OPPORTUNITY_CONVERTED_TO_QUOTE_LINK = "converted_to_quote"

# The CRM domain event the convert action publishes (D-011/D-057): SALES' handlers.py subscribes and
# creates the customer (if new) + the quote in the SAME transaction (the sanctioned cross-module
# mechanism — CRM never imports sales/service). Mirrors the billing → AR-invoice / planned-buy →
# requisition precedent.
OPPORTUNITY_CONVERTED_EVENT_KEY = "crm.opportunity.converted"


# --- Permissions (D-009): one key per guarded endpoint action -----------------
# Lead / opportunity / activity each split read/manage (the master-data precedent). The CONVERT
# action
# gets its OWN distinct key (opportunity.convert) — converting a won deal into a real customer +
# quote
# is a higher-privilege action than editing an opportunity (segregation of duties), exactly as the
# task requires.
CRM_LEAD_READ = "crm.lead.read"
CRM_LEAD_MANAGE = "crm.lead.manage"
CRM_OPPORTUNITY_READ = "crm.opportunity.read"
CRM_OPPORTUNITY_MANAGE = "crm.opportunity.manage"
CRM_OPPORTUNITY_CONVERT = "crm.opportunity.convert"
CRM_ACTIVITY_READ = "crm.activity.read"
CRM_ACTIVITY_MANAGE = "crm.activity.manage"

register_permissions(
    CRM_LEAD_READ,
    CRM_LEAD_MANAGE,
    CRM_OPPORTUNITY_READ,
    CRM_OPPORTUNITY_MANAGE,
    CRM_OPPORTUNITY_CONVERT,
    CRM_ACTIVITY_READ,
    CRM_ACTIVITY_MANAGE,
    descriptions={
        CRM_LEAD_READ: "Read leads",
        CRM_LEAD_MANAGE: "Create, edit, qualify and convert leads",
        CRM_OPPORTUNITY_READ: "Read opportunities and the kanban board",
        CRM_OPPORTUNITY_MANAGE: "Create, edit and move opportunities through the pipeline",
        CRM_OPPORTUNITY_CONVERT: "Convert a won opportunity into a customer and quote",
        CRM_ACTIVITY_READ: "Read activities",
        CRM_ACTIVITY_MANAGE: "Create, edit and complete activities",
    },
)
