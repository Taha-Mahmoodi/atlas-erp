"""Hospitality domain-event handlers (D-011) — the fire → background-depletion bridge.

``submit_ticket_depletion`` subscribes to hospitality's OWN ``RestaurantOrderFired``. A same-module
handler is unusual, and it is deliberate: firing is reachable from a staff terminal and from the
website, and hanging the depletion off the EVENT means neither route can forget it — the same reason
the COGS journal hangs off ``StockValued`` instead of being called by every mover.

It runs inside the fire's ``run_in_uow``, so the PENDING job row commits with the ticket's
SENT_TO_KITCHEN status: a D-013 replay of the fire returns the SAME job id rather than depleting
twice (core/jobs.py). It costs ONE dispatch and issues no stock — the explosion is three reads, and
the 38-statements-per-ingredient writes all happen in the job.

The job still has to be SCHEDULED after the uow commits, which only the router can do; the ids are
stashed on the session and drained by ``depletion.take_depletion_jobs`` (see that function).

Registration: ``app.main.register_event_handlers`` subscribes this at the app factory (the
deterministic D-011 seam), so the test harness re-registers it after its per-test
``clear_subscriptions`` reset.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import actor_user_id_ctx
from app.core.jobs import submit_job
from app.modules.hospitality.constants import DEPLETE_TICKET_JOB
from app.modules.hospitality.events import RestaurantOrderFired
from app.modules.hospitality.service import depletion


async def submit_ticket_depletion(session: AsyncSession, event: RestaurantOrderFired) -> None:
    """Submit the background ingredient depletion for a fired ticket (Q4), in the fire's
    transaction.

    Explodes and aggregates the ticket's recipes here rather than in the job, so the job payload
    SNAPSHOTS what the ticket actually consumed and a pathological aggregate can be split across
    several jobs before any of them opens a transaction.

    The moves are posted on the ticket's FIRE date, not the date the job happens to drain, so a
    ticket fired at 23:58 depletes on that service's date. ``submitted_by`` is the firing user, whom
    the runner restores as the D-010 actor so the ISSUE moves are audited to a person rather than to
    nobody.
    """
    components = await depletion.aggregate_components(session, event.tenant_id, event.ticket_id)
    if not components:
        return
    move_date = datetime.fromisoformat(event.fired_at).date()
    for payload in depletion.job_payloads(event.ticket_id, components, move_date=move_date):
        job = await submit_job(
            session,
            event.tenant_id,
            DEPLETE_TICKET_JOB,
            payload,
            submitted_by=actor_user_id_ctx.get(),
        )
        depletion.remember_job(session, job.id)


__all__ = ["submit_ticket_depletion"]
