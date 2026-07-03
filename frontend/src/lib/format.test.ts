import { describe, expect, it } from "vitest";

import { formatMoney } from "@/lib/format";

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
