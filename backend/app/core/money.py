"""D-015 exact money/quantity/rate representation on BOTH engines, plus allocation.

The financial engine's DB-level invariants (the balance trigger, the one-side CHECK,
valuation math) are only meaningful if storage is EXACT on both backends. PostgreSQL has a
native NUMERIC; SQLite does not — ``sa.Numeric`` round-trips through float there and silently
loses precision. So each TypeDecorator stores NUMERIC on Postgres and an INTEGER of scaled
minor units on SQLite (value × 10^scale), converting to/from ``decimal.Decimal`` in the bind/
result processors. Trigger SQL therefore only ever SUMs and COMPARES the stored representation
(ints on SQLite, NUMERIC on PG) — never divides or scales — so the asymmetric storage stays
semantically identical where it matters (D-015 trigger discipline).

Scales:
- ``MoneyType``      NUMERIC(18,6) / INTEGER micro-units (×10^6), scale 6 — headroom over the
  2/3 currency decimals so posting-time rounding has somewhere to live.
- ``QuantityType``   NUMERIC(18,6) / INTEGER micro-units (×10^6), scale 6 — UoM/FIFO math.
- ``RateType``       NUMERIC(20,10) / INTEGER nano-units (×10^10), scale 10 — FX rates keep
  full precision (rates are never quantized to currency decimals).

Python is Decimal-only — never float. The TypeDecorators are ``cache_ok = True`` (they carry
no per-instance state beyond the fixed class scale), so SQLAlchemy may cache compiled
statements that use them.

``allocate`` is the single largest-remainder splitter (D-015): tax/discount splits, payment
allocation, and the journal's functional-currency residual-cent balancing all route through it
so parts always sum EXACTLY to the total. ``quantize_money`` is the ROUND_HALF_UP boundary
rounding (commercial/SAP practice), keyed off a per-currency decimal-places lookup.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

# Scales (number of fractional decimal digits each type stores). ``MONEY_SCALE`` is public because
# a service that MAINTAINS a header total has to round each line to what the column will store
# before summing — quantizing the sum instead lets the stored lines and the stored total differ by
# a micro-unit (PLAN 19: the order-ticket line writer).
MONEY_SCALE = 6
_QUANTITY_SCALE = 6
_RATE_SCALE = 10


class _ScaledDecimalType(TypeDecorator[Decimal]):
    """Shared base for the three exact-decimal types (D-015).

    ``impl`` is NUMERIC so the default (Postgres) rendering is a true decimal; on SQLite the
    column is loaded as INTEGER and the bind/result processors translate Decimal <-> scaled
    integer minor units. The conversion is exact in both directions because a Decimal with at
    most ``scale`` fractional digits maps to an integer with no rounding (values carrying more
    digits than the scale are quantized HALF_UP on the way in — money/quantities are quantized
    at their boundary before storage, so this only ever trims trailing noise)."""

    # Required by TypeDecorator: the default (Postgres) decorated type. ``load_dialect_impl``
    # overrides it per dialect (BigInteger on SQLite, Numeric(precision, scale) on PG).
    impl = sa.Numeric
    cache_ok = True

    # Concrete subclasses set these; the base is abstract by virtue of unset class attrs.
    scale: int
    precision: int

    @property
    def python_type(self) -> type[Decimal]:
        return Decimal

    def load_dialect_impl(self, dialect: Dialect) -> sa.types.TypeEngine[object]:
        if dialect.name == "sqlite":
            # Scaled minor units fit a 64-bit integer for the demo/test value ranges (D-015).
            return dialect.type_descriptor(sa.BigInteger())
        return dialect.type_descriptor(sa.Numeric(self.precision, self.scale))

    @property
    def _quantum(self) -> Decimal:
        return Decimal(1).scaleb(-self.scale)

    def process_bind_param(self, value: Decimal | int | str | None, dialect: Dialect):
        if value is None:
            return None
        as_decimal = value if isinstance(value, Decimal) else Decimal(str(value))
        if dialect.name == "sqlite":
            # Decimal -> integer scaled minor units. Quantize first so a value with more than
            # ``scale`` digits cannot leave a fractional remainder when multiplied out.
            scaled = as_decimal.quantize(self._quantum, rounding=ROUND_HALF_UP)
            return int(scaled.scaleb(self.scale))
        return as_decimal

    def process_result_value(self, value: int | Decimal | None, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if dialect.name == "sqlite":
            # Integer scaled minor units -> Decimal at the type's scale (exact, no float).
            return (Decimal(int(value)) * self._quantum).quantize(self._quantum)
        return value if isinstance(value, Decimal) else Decimal(str(value))


class MoneyType(_ScaledDecimalType):
    """Monetary amount (D-015): NUMERIC(18,6) on Postgres, INTEGER micro-units on SQLite."""

    # cache_ok must be set on each concrete TypeDecorator class, not just the base.
    cache_ok = True
    scale = MONEY_SCALE
    precision = 18


class QuantityType(_ScaledDecimalType):
    """Inventory quantity (D-015): NUMERIC(18,6) on Postgres, INTEGER micro-units on SQLite.
    Same storage as MoneyType but a distinct type so quantity and money columns read clearly."""

    cache_ok = True
    scale = _QUANTITY_SCALE
    precision = 18


class RateType(_ScaledDecimalType):
    """FX/exchange rate (D-015): NUMERIC(20,10) on Postgres, INTEGER nano-units on SQLite.
    Scale 10 keeps full rate precision — rates are never quantized to currency decimals."""

    cache_ok = True
    scale = _RATE_SCALE
    precision = 20


# --- Currency decimals + boundary rounding ------------------------------------

# ISO 4217 fractional digits. Default is 2; non-2-decimal currencies are listed explicitly so
# the table can grow (JPY=0, BHD=3, ...). Stored journal amounts quantize to this at the
# posting/pricing boundary; unit prices/costs and FX rates keep full scale-6/10 precision.
_DEFAULT_CURRENCY_DECIMALS = 2
_CURRENCY_DECIMALS: dict[str, int] = {
    "JPY": 0,
    "KRW": 0,
    "BHD": 3,
    "KWD": 3,
    "OMR": 3,
    "TND": 3,
}


def currency_decimals(currency_code: str) -> int:
    """ISO 4217 fractional digits for ``currency_code`` (default 2). The amount-rounding
    boundary uses this so e.g. JPY rounds to whole units and BHD to three places (D-015)."""
    return _CURRENCY_DECIMALS.get(currency_code.upper(), _DEFAULT_CURRENCY_DECIMALS)


def quantize_money(value: Decimal, places: int = 2) -> Decimal:
    """Round ``value`` to ``places`` decimals HALF_UP (D-015 — commercial/SAP practice). Pass
    ``currency_decimals(code)`` for ``places`` to round to a currency's minor unit."""
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def quantize_quantity(value: Decimal) -> Decimal:
    """Round ``value`` to the D-015 quantity scale (6 dp) HALF_UP — what ``QuantityType`` stores.

    Derived quantities (a BOM explosion's scrap load, a recipe scaled to a ticket's portions) must
    not carry more precision than the column keeps, or the number a test asserts and the number the
    database returns differ in the last places."""
    return value.quantize(Decimal(1).scaleb(-_QUANTITY_SCALE), rounding=ROUND_HALF_UP)


def quantize_for_currency(value: Decimal, currency_code: str) -> Decimal:
    """Round ``value`` to ``currency_code``'s minor unit HALF_UP (D-015)."""
    return quantize_money(value, currency_decimals(currency_code))


def allocate(total: Decimal, weights: list[Decimal], places: int = 2) -> list[Decimal]:
    """Split ``total`` across ``weights`` so the parts sum EXACTLY to ``total`` (D-015).

    Largest-remainder method: each part is ``total × weight / Σweights`` rounded DOWN to
    ``places`` decimals, then the rounding residual (``total`` minus the sum of floored parts)
    is distributed one minor unit at a time to the parts with the largest fractional remainder,
    ties broken by original index. Deterministic, and the parts ALWAYS reconstitute the total —
    used for FX residual-cent absorption, tax splits, discount splits and payment allocation.

    A zero or empty total returns zeros; zero total weight (all weights zero) splits ``total``
    evenly via equal unit weights so the result still sums to ``total`` rather than dropping it.
    """
    quantum = Decimal(1).scaleb(-places)
    n = len(weights)
    if n == 0:
        return []
    total_weight = sum(weights, Decimal(0))
    if total_weight == 0:
        # Degenerate: no weight to distribute by. Fall back to equal weights so the total is
        # still allocated exactly (never silently dropped).
        weights = [Decimal(1)] * n
        total_weight = Decimal(n)

    exact = [total * weight / total_weight for weight in weights]
    floored = [part.quantize(quantum, rounding=ROUND_DOWN) for part in exact]
    remainders = [exact[i] - floored[i] for i in range(n)]

    allocated = sum(floored, Decimal(0))
    residual = total - allocated
    # Number of whole minor units still to hand out (can be negative if total is negative).
    units = int((residual / quantum).to_integral_value(rounding=ROUND_HALF_UP))

    # Distribute to the largest remainders first; for a negative residual hand out negative
    # units to the SMALLEST remainders (those rounded least-down) so the result stays balanced.
    order = sorted(range(n), key=lambda i: (remainders[i], -i), reverse=units >= 0)
    step = quantum if units >= 0 else -quantum
    for k in range(abs(units)):
        floored[order[k % n]] += step
    return floored


__all__ = [
    "MONEY_SCALE",
    "MoneyType",
    "QuantityType",
    "RateType",
    "allocate",
    "currency_decimals",
    "quantize_for_currency",
    "quantize_money",
    "quantize_quantity",
]
