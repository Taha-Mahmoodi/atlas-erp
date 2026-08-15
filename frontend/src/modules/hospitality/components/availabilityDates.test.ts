import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { endOfLocalDay, localDateInput } from "@/modules/hospitality/components/availabilityDates";

// Pinned west of Greenwich on purpose: the bug this guards (reading the UTC date back out of the
// stored instant) is invisible at UTC+0, which is exactly where CI's clock sits.
const originalTz = process.env.TZ;
beforeAll(() => {
  process.env.TZ = "America/New_York";
});
afterAll(() => {
  process.env.TZ = originalTz;
});

describe("availability dates", () => {
  it("stores the end of the picked day, in UTC", () => {
    // 2026-08-15T23:59:59-04:00 — already the 16th in UTC, which is the whole trap.
    expect(endOfLocalDay("2026-08-15")).toBe("2026-08-16T03:59:59.000Z");
  });

  it("round-trips, so re-saving an untouched override does not extend it", () => {
    for (const date of ["2026-08-15", "2026-01-01", "2026-12-31"]) {
      expect(localDateInput(endOfLocalDay(date))).toBe(date);
    }
  });

  it("seeds nothing from an unparseable timestamp instead of NaN-NaN-NaN", () => {
    expect(localDateInput("not a date")).toBe("");
  });
});
