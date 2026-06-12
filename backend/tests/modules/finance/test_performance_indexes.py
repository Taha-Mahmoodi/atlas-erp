"""Regression for #25 (PERFORMANCE §1): the AP/AR hot-list filter indexes must exist.

These assertions run against the migrated template schema, so they fail if migration
0016 is reverted or a future batch rebuild of either table silently drops the index.
"""

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

_EXPECTED = {
    "fin_vendor_bills": (
        "ix_fin_vendor_bills_list_filters",
        ["tenant_id", "partner_id", "status", "bill_date"],
    ),
    "fin_customer_invoices": (
        "ix_fin_customer_invoices_list_filters",
        ["tenant_id", "partner_id", "status", "invoice_date"],
    ),
}


@pytest.mark.parametrize("table", sorted(_EXPECTED))
async def test_hot_list_filter_index_exists(db_engine: AsyncEngine, table: str) -> None:
    """#25: the tenant-led composite for the dominant list-filter combination is present."""
    name, columns = _EXPECTED[table]
    async with db_engine.connect() as conn:
        indexes = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_indexes(table))
    by_name = {ix["name"]: ix["column_names"] for ix in indexes}
    assert name in by_name, f"missing index {name} on {table} (have: {sorted(by_name)})"
    assert by_name[name] == columns
