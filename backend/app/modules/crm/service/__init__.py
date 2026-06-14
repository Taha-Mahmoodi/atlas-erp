"""CRM service package (STRUCTURE §3: one file per aggregate, each <400 lines — the projects /
maintenance precedent). The routers and test factories import from this package surface (``from
app.modules.crm import service`` then ``service.create_lead(...)``), so the split into ``leads``
(the
lead pipeline + convert-to-opportunity), ``opportunities`` (the opportunity CRUD + lines + kanban
move/board + the from-lead builder), ``activities`` (the logged interactions) and ``convert`` (the
headline opportunity → customer + quote) is an internal detail. Re-exported here so call sites use
one
import.
"""

from app.modules.crm.service.activities import (
    cancel_activity,
    complete_activity,
    create_activity,
    get_activity,
    list_activities,
    update_activity,
)
from app.modules.crm.service.convert import convert_opportunity
from app.modules.crm.service.leads import (
    convert_lead_to_opportunity,
    create_lead,
    disqualify_lead,
    get_lead,
    list_leads,
    qualify_lead,
    update_lead,
)
from app.modules.crm.service.opportunities import (
    create_opportunity,
    get_opportunity,
    get_opportunity_lines,
    kanban_board,
    list_opportunities,
    move_stage,
    update_opportunity,
)

__all__ = [
    "cancel_activity",
    "complete_activity",
    "convert_lead_to_opportunity",
    "convert_opportunity",
    "create_activity",
    "create_lead",
    "create_opportunity",
    "disqualify_lead",
    "get_activity",
    "get_lead",
    "get_opportunity",
    "get_opportunity_lines",
    "kanban_board",
    "list_activities",
    "list_leads",
    "list_opportunities",
    "move_stage",
    "qualify_lead",
    "update_activity",
    "update_lead",
    "update_opportunity",
]
