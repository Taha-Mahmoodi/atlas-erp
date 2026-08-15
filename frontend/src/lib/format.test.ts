import { describe, expect, it } from "vitest";

import { formatElapsed, formatMoney } from "@/lib/format";

describe("formatMoney", () => {
  it("formats a normal ISO currency", () => {
    expect(formatMoney("1234.5", "USD")).toContain("1,234.50");
  });

  it("degrades gracefully on the backend's unset-currency sentinel instead of throwing", () => {
    // D-058: an unconfigured tenant's dashboard sends "—" rather than a real ISO code so the
    // response stays well-formed (no 500) — Intl.NumberFormat throws RangeError on that.
    expect(() => formatMoney("0", "—")).not.toThrow();
    expect(formatMoney("0", "—")).toBe("0 —");
  });
});

describe("formatElapsed", () => {
  const now = new Date("2026-08-15T20:00:00Z");

  it("counts minutes, then hours and minutes — the kitchen's unit is the minute", () => {
    expect(formatElapsed("2026-08-15T19:59:20Z", now)).toBe("0m");
    expect(formatElapsed("2026-08-15T19:53:00Z", now)).toBe("7m");
    expect(formatElapsed("2026-08-15T18:35:00Z", now)).toBe("1h 25m");
  });

  it("clamps a clock skew to zero rather than counting backwards", () => {
    // The timestamp is the server's and the clock is the browser's; a display saying a ticket
    // fired "-2m" ago would read as a bug in the kitchen, not as a clock difference.
    expect(formatElapsed("2026-08-15T20:02:00Z", now)).toBe("0m");
  });

  it("returns an em dash for an unparseable timestamp instead of NaN", () => {
    expect(formatElapsed("not a timestamp", now)).toBe("—");
  });
});
