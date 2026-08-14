"""Hospitality HTTP layer (thin): parse -> call service -> return schema (PLAN 19).

STAFF-facing routes only. The property's WEBSITE is a separate principal on a separate router
(``website_router.py``, Task 7) because the two surfaces have different cache policies and a
different credential (D-069 API key vs a staff JWT), and mixing them would put a
``Cache-Control: private`` menu read next to an unbounded staff query.

This file exists ahead of its routes for one concrete reason, not as scaffolding: mounting a
module's router in ``core/bootstrap.py`` is what IMPORTS the module, and importing the module is
what runs ``constants.py``'s ``register_permissions`` — so a hospitality key can only reach
``rbac.catalog_keys()``, and therefore only ever be granted to a tenant, through this mount (D-009).
The alternative — importing ``constants`` directly from bootstrap — would invent a second module
wiring convention beside the one all thirteen other modules use. Routes land here in Task 6.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/hospitality", tags=["hospitality"])
