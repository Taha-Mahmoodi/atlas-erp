/**
 * The 86 editor's date field ↔ the API's UTC instant. Both halves live here, together, because
 * they are one round trip: the date a manager picks has to come back as the SAME date when the
 * override is re-opened, or every save pushes the expiry another day out.
 */

/** A `<input type="date">` value → the END of that day in UTC. End, not start: a kitchen 86s a
 * dish "for tonight", so picking today has to mean "through today" rather than "already lapsed". */
export function endOfLocalDay(isoDate: string): string {
  return new Date(`${isoDate}T23:59:59`).toISOString();
}

/** The inverse: a UTC instant → the LOCAL calendar date, for seeding the input again. Slicing the
 * ISO string would read the UTC date instead, which for an end-of-evening instant is already
 * tomorrow anywhere west of Greenwich — so re-saving an untouched row would extend it by a day,
 * every time, while the grid's `formatDateTime` beside it still showed the right one. */
export function localDateInput(isoTimestamp: string): string {
  const value = new Date(isoTimestamp);
  if (Number.isNaN(value.getTime())) return "";
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}
