/**
 * ALL display formatting goes through here (STRUCTURE §4) — never inline `toFixed`.
 * Backend money/quantity values arrive as decimal STRINGS (exactness over the wire);
 * these helpers format them for display without ever doing float arithmetic on them.
 */

const LOCALE = undefined; // browser locale; industry templates may pin one later

/**
 * "1,234.50 USD" — money is a decimal string + its currency code, never a float.
 * An unconfigured tenant's dashboard sends a non-ISO placeholder currency ("—", D-058's
 * documented "well-formed zero KPIs instead of a 500") — `Intl.NumberFormat` throws
 * `RangeError` on that, so fall back to a plain number + the raw code rather than crash.
 */
export function formatMoney(amount: string | number, currencyCode: string): string {
  const value = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(value)) return `${amount} ${currencyCode}`;
  try {
    return new Intl.NumberFormat(LOCALE, {
      style: "currency",
      currency: currencyCode,
      currencyDisplay: "code",
    }).format(value);
  } catch {
    return `${new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 }).format(value)} ${currencyCode}`;
  }
}

/** Quantities keep up to 6 fractional digits (QuantityType) but trim trailing zeros. */
export function formatQuantity(quantity: string | number): string {
  const value = typeof quantity === "number" ? quantity : Number(quantity);
  if (!Number.isFinite(value)) return String(quantity);
  return new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 6 }).format(value);
}

/** ISO "2026-07-02" → localized medium date ("Jul 2, 2026"). */
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) return isoDate;
  return new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium" }).format(
    new Date(year, month - 1, day),
  );
}

/** ISO timestamp → localized date + time ("Jul 2, 2026, 14:03"). */
export function formatDateTime(isoTimestamp: string): string {
  const value = new Date(isoTimestamp);
  if (Number.isNaN(value.getTime())) return isoTimestamp;
  return new Intl.DateTimeFormat(LOCALE, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(value);
}

/** "12.5%" from a decimal-string percent (e.g. tax rate_percent "12.50"). */
export function formatPercent(percent: string | number): string {
  const value = typeof percent === "number" ? percent : Number(percent);
  if (!Number.isFinite(value)) return `${percent}%`;
  return `${new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 }).format(value)}%`;
}
