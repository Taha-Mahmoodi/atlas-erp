"""D-013 idempotency keys: reservation + atomic completion via route capture.

The mechanism, exactly as D-013 prescribes, in two phases:

* **Phase 1 (reserve).** ``Idempotent("endpoint")`` reads the ``Idempotency-Key`` header,
  hashes the canonical request body, and calls :func:`reserve`, which opens a SEPARATE
  short-lived session, INSERTs an ``IN_PROGRESS`` row, and COMMITs immediately. Two concurrent
  duplicates therefore collide on the natural composite PK ``(tenant_id, endpoint, key)`` — PG's
  unique index arbitrates, SQLite's single-writer lock serializes. On collision the existing row
  decides the outcome: ``COMPLETED`` + matching hash → REPLAY the stored response verbatim with
  header ``Idempotency-Replayed: true`` and no business logic; ``COMPLETED`` + different hash →
  422 ``idempotency.key_reuse`` (a client bug reusing a key for a different body); ``IN_PROGRESS``
  → 409 ``idempotency.in_progress`` (a concurrent duplicate is still running).

* **Phase 2 (capture).** The dependency YIELDS an :class:`IdempotencyContext` bound to the
  request's BUSINESS session. The handler's last act is ``idem.capture(read_schema)`` — it
  ``model_dump``s the exact schema FastAPI will serialize and STAGES the completion UPDATE
  (status → COMPLETED, response_status, response_body, completed_at) on the business session, so
  the document and the replay record commit ATOMICALLY in one ``run_in_uow`` transaction. The
  cardinal invariant: a replayable response exists iff the document exists.

* **Fail-closed.** On a BUSINESS EXCEPTION, the dependency's teardown deletes the dangling
  IN_PROGRESS reservation (committed in its own session) so the client may retry the same key, and
  re-raises — the app's exception handlers render the proper error envelope. (Atlas commits the
  business work via ``run_in_uow`` INSIDE the handler, so a failed handler has already rolled the
  document AND the staged capture UPDATE back; only the separately-committed reservation needs
  cleanup.) On a FORGOTTEN ``capture()`` (handler returned 2xx but never captured), the teardown
  deletes the dangling reservation and logs a server error; it cannot convert the already-sent 2xx
  to a 500 because the run_in_uow commit precedes teardown — a documented deviation from D-013's
  literal "teardown rolls back", which assumed a deferred session-dependency commit (DECISIONS.md).

Replay short-circuit mechanism (FastAPI-idiomatic): :func:`reserve` raises
:class:`IdempotencyReplay` carrying the stored response. ``IdempotencyReplay`` is an
``AtlasError`` subtype whose dedicated handler in ``app.main`` writes the stored
status+body+header — so a completed-key replay never reaches the handler body and the side
effect cannot run twice. A first-time request instead yields the context normally.
"""

import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import json_safe
from app.core.db import get_session, get_session_factory
from app.core.exceptions import AtlasError, ConflictError, ValidationFailedError
from app.core.models import JSON_VARIANT, Base, TenantMixin, tenant_fk
from app.core.tenancy import get_current_tenant_id, system_context

# This module imports core/db (for the get_session / get_session_factory dependencies the
# Idempotent guard composes), so unlike numbering.py / docflow.py it is registered on
# Base.metadata from the BOTTOM of core/db.py — AFTER db, audit and tenancy finish loading —
# rather than via core/models' trailing import, which would run mid-cycle and dead-lock on the
# db -> audit -> models chain. The registration site is documented there.

logger = logging.getLogger("atlas")

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"

# Header marking a replayed response (D-013): clients can tell a fresh execution from a replay.
REPLAYED_HEADER = "Idempotency-Replayed"


class IdempotencyKey(TenantMixin, Base):
    """Reservation row (D-013). The PRIMARY KEY is the NATURAL composite
    ``(tenant_id, endpoint, key)`` exactly as D-013 prescribes — deliberately NOT UuidPKMixin:
    the composite key IS the collision point that serializes concurrent duplicates, so a surrogate
    id plus a UNIQUE would be redundant indirection. TenantMixin still applies (the row is
    tenant-scoped and the D-007 filter/stamp run on it); tenant_id participates in the PK so the
    composite is already tenant-unique. Not AuditMixin: reservation rows are request-control
    infrastructure, not business state (auditing them would be noise — documented exclusion).

    NO PRINCIPAL COLUMN, deliberately: the namespace is the TENANT's, so every principal in a
    tenant shares it. Since the Phase 18 machine credential (spec Q1) an EXTERNAL client sits in
    that namespace beside the tenant's staff. Two principals presenting the same key value on the
    same endpoint therefore meet on one row: same body replays the FIRST principal's stored
    response verbatim, a different body is 422 key_reuse, and an unfinished one is 409
    in_progress. Bounded, and measured in tests/core/test_api_key_concurrency.py: the route's
    require_permission dependency is solved BEFORE this guard, so a replay never crosses the RBAC
    line — but it does skip serialization, so a masked field (D-009) in an idempotent endpoint's
    response would cross unmasked. That endpoint does not exist yet and a gate test keeps it that
    way; adding one means adding a principal column here instead."""

    __tablename__ = "core_idempotency_keys"
    __table_args__ = (tenant_fk("adm_tenants"),)

    # Override TenantMixin's tenant_id to make it part of the composite PK (the mixin declares it
    # non-PK). All three PK members carry primary_key=True so the mapper's PK matches the
    # migration's PrimaryKeyConstraint(tenant_id, endpoint, key) — the natural key D-013 mandates.
    # index=True preserves the mixin's standalone tenant_id index (the D-007 mapper-enumeration
    # invariant requires every tenant-scoped table to carry one, uniform across the schema even
    # though the composite PK already leads with tenant_id).
    tenant_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, index=True)
    endpoint: Mapped[str] = mapped_column(sa.String(200), primary_key=True)
    key: Mapped[str] = mapped_column(sa.String(200), primary_key=True)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    response_body: Mapped[Any] = mapped_column(JSON_VARIANT, nullable=True)
    # index=True: the retention purge (core/job_sweeper.py) scans by AGE across tenants, so this
    # index does not lead with tenant_id — expiry is an age question, not a tenancy one.
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


def compute_request_hash(body: bytes) -> str:
    """sha256 hex of the canonical request bytes (D-013). Raw bytes are the canonical form here:
    a replay must present the byte-identical request, and hashing bytes avoids re-serialization
    ambiguity. An empty body hashes to the sha256 of b'' — stable and well-defined, which is why
    the guard feeds it the request TARGET followed by the body rather than the body alone (see
    ``Idempotent.__call__``: an action route's body is empty and its identity is in its path)."""
    return hashlib.sha256(body).hexdigest()


class IdempotencyReplay(AtlasError):
    """Raised by reserve() when a COMPLETED key with a matching hash is replayed. NOT an error
    in the user sense — its dedicated handler in app.main writes the stored response verbatim
    (status + body + Idempotency-Replayed header), short-circuiting the route so the side effect
    never runs twice. status_code/details carry the stored response across to the handler."""

    def __init__(self, response_status: int, response_body: Any) -> None:
        super().__init__(
            code="idempotency.replayed",
            message="Replaying a previously completed idempotent response",
            status_code=response_status,
        )
        self.response_body = response_body


@dataclass
class IdempotencyContext:
    """Yielded to the handler (Phase 2). ``capture`` stages the completion UPDATE on the BUSINESS
    session so document + replay record commit atomically; ``captured`` lets the teardown detect a
    forgotten capture (fail-closed). ``factory`` + identity are kept so the teardown can run the
    separate-session cleanup that deletes the reservation on a forgotten-capture or business
    failure."""

    session: AsyncSession
    factory: async_sessionmaker[AsyncSession]
    tenant_id: uuid.UUID
    endpoint: str
    key: str
    captured: bool = False

    async def capture[T](self, response: T, *, status_code: int = 200) -> T:
        """Write ``UPDATE ... SET status='completed', response_status, response_body,
        completed_at=now()`` on the BUSINESS session (no commit) and return ``response``
        UNCHANGED. Call it INSIDE the ``run_in_uow`` work, right after the document is created::

            async def work() -> None:
                doc = create_document(...)
                await session.flush()
                holder['read'] = await idem.capture(DocRead.model_validate(doc))
            await run_in_uow(session, work)
            return holder['read']

        The UPDATE joins the request's open transaction, so ``run_in_uow``'s single commit persists
        the document AND this replay record atomically — they commit or roll back together
        (D-013's cardinal invariant: a replayable response exists iff the document exists). The
        body is serialized to the exact JSON FastAPI will emit, so a future replay reproduces it
        verbatim.

        A Core UPDATE under system_context: the reservation is addressed by its full composite PK,
        so no tenant filter is needed and bypassing the ORM stamp keeps it a pure data write."""
        body = _serialize_response(response)
        with system_context():
            await self.session.execute(
                sa.update(IdempotencyKey.__table__)
                .where(
                    IdempotencyKey.__table__.c.tenant_id == self.tenant_id,
                    IdempotencyKey.__table__.c.endpoint == self.endpoint,
                    IdempotencyKey.__table__.c.key == self.key,
                )
                .values(
                    status=STATUS_COMPLETED,
                    response_status=status_code,
                    response_body=body,
                    completed_at=datetime.now(UTC),
                )
            )
        self.captured = True
        return response


def _serialize_response(response: Any) -> Any:
    """Coerce a route's return value (a Pydantic model, a dict, or a primitive) to the
    JSON-safe form FastAPI would serialize, so a replay reproduces it byte-for-byte."""
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    return json_safe(response)


async def reserve(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    endpoint: str,
    key: str,
    request_hash: str,
) -> None:
    """Phase 1 (D-013). Open a SEPARATE session, INSERT the IN_PROGRESS reservation, and COMMIT
    immediately so two concurrent duplicates collide on the composite PK. On collision, load the
    existing row and decide: replay (raise IdempotencyReplay), key-reuse (422), or in-progress
    (409). Runs under system_context so the explicit-tenant_id insert/select bypass ORM stamping
    on this out-of-band session; the composite-FK backstop still rejects a bogus tenant_id."""
    async with factory() as session:
        try:
            with system_context():
                await session.execute(
                    sa.insert(IdempotencyKey.__table__).values(
                        tenant_id=tenant_id,
                        endpoint=endpoint,
                        key=key,
                        status=STATUS_IN_PROGRESS,
                        request_hash=request_hash,
                    )
                )
                await session.commit()
            return
        except IntegrityError:
            await session.rollback()

        # Collision: a row already exists for (tenant, endpoint, key). Load and arbitrate.
        with system_context():
            existing = (
                await session.execute(
                    select(IdempotencyKey).where(
                        IdempotencyKey.tenant_id == tenant_id,
                        IdempotencyKey.endpoint == endpoint,
                        IdempotencyKey.key == key,
                    )
                )
            ).scalar_one()

    if existing.status == STATUS_COMPLETED:
        if existing.request_hash == request_hash:
            raise IdempotencyReplay(existing.response_status or 200, existing.response_body)
        raise ValidationFailedError(
            message="Idempotency-Key was reused with a different request body",
            code="idempotency.key_reuse",
        )
    # IN_PROGRESS: a concurrent duplicate is still running its business work.
    raise ConflictError(
        message="A request with this Idempotency-Key is already in progress",
        code="idempotency.in_progress",
    )


async def _cleanup_reservation(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    endpoint: str,
    key: str,
) -> None:
    """Delete an IN_PROGRESS reservation in its OWN committed session (D-013 fail-closed). Run
    when the handler failed or forgot to capture, so the client may retry the same key. Only
    deletes while status is still IN_PROGRESS — never removes a COMPLETED replay record."""
    async with factory() as session:
        with system_context():
            await session.execute(
                sa.delete(IdempotencyKey.__table__).where(
                    IdempotencyKey.__table__.c.tenant_id == tenant_id,
                    IdempotencyKey.__table__.c.endpoint == endpoint,
                    IdempotencyKey.__table__.c.key == key,
                    IdempotencyKey.__table__.c.status == STATUS_IN_PROGRESS,
                )
            )
            await session.commit()


class Idempotent:
    """FastAPI dependency factory (D-013). A guarded route declares it AFTER the principal
    dependency (so the D-007 tenant context is set when reserve runs) and captures inside the uow::

        @router.post("/journal-entries/{id}/post")
        async def post_journal(
            current: CurrentUserDep,
            session: SessionDep,
            idem: IdempotentDep = Depends(Idempotent("finance.journal.post")),
        ):
            holder = {}
            async def work() -> None:
                entry = await post_entry(session, ...)        # create the document
                holder['read'] = await idem.capture(JournalEntryRead.model_validate(entry))
            await run_in_uow(session, work)                   # commits document + replay record
            return holder['read']

    The ``endpoint`` string is the stable D-013 route identifier (METHOD + template, or a chosen
    key) that scopes reservations per endpoint, so one client UUID per form submission is safe."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    async def __call__(
        self,
        request: Request,
        session: Annotated[AsyncSession, Depends(get_session)],
        factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> AsyncIterator[IdempotencyContext]:
        if not idempotency_key:
            raise ValidationFailedError(
                message="The Idempotency-Key header is required for this endpoint",
                code="idempotency.key_required",
            )
        # tenant_id from the D-007 ContextVar that get_current_user set. A guarded route declares
        # the principal dependency BEFORE this one (the codebase convention: every router lists
        # ``current: CurrentUserDep`` first), so the context is established when reserve() runs. We
        # read the ContextVar rather than importing CurrentUserDep here to avoid the deps -> db ->
        # idempotency import cycle (this module is registered from core/db at load time).
        tenant_id = get_current_tenant_id()
        if tenant_id is None:  # pragma: no cover - guarded routes always run authenticated
            raise ValidationFailedError(
                message="Idempotency requires an active tenant context",
                code="idempotency.tenant_required",
            )

        # Read the raw body here and hash it (D-013). Starlette caches the body on request.body()
        # (request._body), so the route handler's own body parsing still works after this read —
        # the stream is not consumed out from under it. A replay with a different body therefore
        # produces a different hash and is rejected as key-reuse.
        #
        # The request TARGET is hashed WITH the body, because on an action route the body is empty
        # and the identity of the thing being acted on is entirely in the path: every
        # POST /tickets/{id}/fire, /journal-entries/{id}/post, /purchase-orders/{id}/send hashes
        # b'' otherwise, so one key spent on one document would REPLAY that document's response for
        # a different one — a 200 for an action that never ran, which is exactly the failure the
        # different-body 422 exists to prevent and the only case it cannot see. Query string
        # included for the same reason. The endpoint string stays the coarse namespace it always
        # was; this narrows the hash within it, and a genuine retry (same key, same target, same
        # body) still replays untouched.
        target = f"{request.url.path}?{request.url.query}".encode()
        request_hash = compute_request_hash(target + b"\n" + await request.body())
        await reserve(factory, tenant_id, self.endpoint, idempotency_key, request_hash)

        context = IdempotencyContext(
            session=session,
            factory=factory,
            tenant_id=tenant_id,
            endpoint=self.endpoint,
            key=idempotency_key,
        )
        try:
            yield context
        except Exception:
            # Business work failed (D-013 fail-closed): the document was rolled back by run_in_uow
            # (the staged capture UPDATE with it), but the IN_PROGRESS reservation was committed in
            # reserve()'s SEPARATE session, so it would otherwise linger. Delete it in its own
            # committed session so the SAME key is immediately retryable, then re-raise — the app's
            # exception handlers turn the re-raised error into the proper envelope (verified: a
            # generic Exception still routes through _handle_unexpected_error to a 500 envelope).
            await _cleanup_reservation(factory, tenant_id, self.endpoint, idempotency_key)
            raise
        else:
            if not context.captured:
                # Forgotten capture: the handler returned 2xx without calling capture(), so the
                # reservation never reached COMPLETED. The 2xx response has already been sent (in
                # this build the business commit lives in run_in_uow inside the handler, BEFORE
                # this teardown — D-013's literal "teardown rolls back" assumed a deferred session
                # commit), so the response can no longer be changed. We delete the dangling
                # reservation so the key is retryable and log a server error — the missing replay
                # record is the signal a guarded route forgot its capture() one-liner. Deviation
                # from D-013's rollback-on-forgotten-capture is documented in DECISIONS.md.
                await _cleanup_reservation(factory, tenant_id, self.endpoint, idempotency_key)
                logger.error(
                    "Idempotent endpoint %r returned 2xx without calling capture(); reservation "
                    "cleaned up but no replay record was stored",
                    self.endpoint,
                )


# Type alias a guarded route annotates its captured-context parameter with, e.g.
# ``idem: IdempotentDep = Depends(Idempotent("finance.journal.post"))``.
IdempotentDep = IdempotencyContext

__all__ = [
    "REPLAYED_HEADER",
    "Idempotent",
    "IdempotencyContext",
    "IdempotencyKey",
    "IdempotencyReplay",
    "IdempotentDep",
    "compute_request_hash",
    "reserve",
]
