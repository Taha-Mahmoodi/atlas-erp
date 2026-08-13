import { describe, expect, it } from "vitest";

import { filterValue } from "./ReportBuilderPage";

describe("filterValue", () => {
  it("passes scalar operators through as the raw string", () => {
    expect(filterValue({ column: "status", operator: "eq", value: "posted" })).toBe("posted");
  });

  it("splits IN into a trimmed list, dropping empties", () => {
    expect(filterValue({ column: "status", operator: "in", value: "a, b, ,c" })).toEqual([
      "a",
      "b",
      "c",
    ]);
  });

  it("splits BETWEEN into a [low, high] pair", () => {
    expect(
      filterValue({ column: "total", operator: "between", value: "10, 20" }),
    ).toEqual(["10", "20"]);
  });

  it("maps IS_NULL to a bool ('false' means not empty)", () => {
    expect(filterValue({ column: "ref", operator: "is_null", value: "true" })).toBe(true);
    expect(filterValue({ column: "ref", operator: "is_null", value: "false" })).toBe(false);
  });
});
