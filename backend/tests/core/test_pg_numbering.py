"""The counter-seeding read on the REAL engine (run with `-m pg` against a real PostgreSQL).

What SQLite cannot prove: `_highest_issued` CASTs a number's tail to INTEGER, and Postgres
REJECTS a tail that is not a bare integer (`invalid input syntax for type integer:
"2026-000001"`) where SQLite prefix-parses it to 2026 and carries on. Both halves are wrong, so
the SQLite suite's `test_a_flat_sequence_ignores_the_year_segment_of_a_prefix_it_shares` already
fails without the guard — but only Postgres shows that the un-guarded query is a 500 on the
counter-creation path rather than an off-by-a-lot, and only Postgres proves the guard is what
keeps the two engines answering the same thing (D-003).

Skipped automatically unless ATLAS_DATABASE_URL points at PostgreSQL, exactly like
test_pg_migrations.py; CI's Postgres step sets that URL and selects `-m pg`.
"""

import os
import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import build_session_factory
from app.core.docflow import register_document
from app.core.numbering import claim_number, ensure_sequence
from app.core.tenancy import tenant_context

pytestmark = pytest.mark.pg

_URL = os.environ.get("ATLAS_DATABASE_URL", "")

if not _URL.startswith("postgresql"):
    pytest.skip("pg-marked tests require a PostgreSQL ATLAS_DATABASE_URL", allow_module_level=True)


async def test_a_flat_sequences_counter_opens_on_postgres_beside_a_year_resetting_prefix() -> None:
    """A `year_reset=False` sequence whose prefix is shared with a year-resetting one: its head
    is `'PFX-'`, so `'PFX-2026-000001'` matches it and its tail is not an integer. Un-guarded,
    opening the flat sequence's counter raises InvalidTextRepresentationError here — a 500 on the
    only path that creates a counter. Guarded, the foreign number drops out and the flat series
    opens at 1, the same answer the SQLite suite asserts."""
    engine = create_async_engine(_URL)
    tenant_id = uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO adm_tenants (id, slug, name) "
                    "VALUES (:id, :slug, 'PG numbering tenant')"
                ),
                {"id": tenant_id, "slug": f"pg-num-{tenant_id.hex[:12]}"},
            )

        async with build_session_factory(engine)() as session:
            with tenant_context(tenant_id):
                await ensure_sequence(session, tenant_id, "projects.phase", "PFX", 6, True)
                await register_document(
                    session,
                    tenant_id,
                    "projects.phase",
                    uuid.uuid4(),
                    doc_number="PFX-2026-000001",
                    status="open",
                )
                await session.commit()

                # Opening the flat sequence's counter runs the seeding read on that number.
                await ensure_sequence(session, tenant_id, "projects.project", "PFX", 6, False)
                claimed = await claim_number(
                    session, tenant_id, "projects.project", on_date=date(2026, 6, 1)
                )
                await session.commit()

        assert claimed == "PFX-000001"
    finally:
        async with engine.begin() as conn:
            for table in (
                "core_documents",
                "core_number_sequence_counters",
                "core_number_sequences",
                "adm_tenants",
            ):
                column = "id" if table == "adm_tenants" else "tenant_id"
                await conn.execute(
                    text(f"DELETE FROM {table} WHERE {column} = :tid"), {"tid": tenant_id}
                )
        await engine.dispose()
