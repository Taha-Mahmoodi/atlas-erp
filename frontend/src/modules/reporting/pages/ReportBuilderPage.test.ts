import { describe, expect, it } from "vitest";

import { filterValue, resultHeaders } from "./ReportBuilderPage";

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

describe("resultHeaders (#166)", () => {
  it("shows the backend's display labels, not the wire column names", () => {
    expect(
      resultHeaders({
        columns: ["status", "sum_total_amount"],
        column_labels: ["Status", "Sum of Total"],
      }),
    ).toEqual(["Status", "Sum of Total"]);
  });

  it("falls back to the wire name when a label is missing", () => {
    // A pre-#166 server (or a stale cached response) sends no column_labels; the grid must still
    // name every column rather than render a row of blanks.
    expect(resultHeaders({ columns: ["order_number", "status"] })).toEqual([
      "order_number",
      "status",
    ]);
    expect(resultHeaders({ columns: ["status", "n"], column_labels: ["Status"] })).toEqual([
      "Status",
      "n",
    ]);
  });

  it("is empty with no result, so the grid renders no headers", () => {
    expect(resultHeaders(undefined)).toEqual([]);
  });
});
