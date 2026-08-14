import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusPill, humanizeStatus, toneFor } from "./StatusPill";

describe("StatusPill", () => {
  it("gives one status word one tone across every module (issue #182)", () => {
    // The regression this component exists to prevent: CLOSED rendered green in Procurement
    // and grey in Sales, and RECEIVED/CLOSED shared a colour inside one list.
    expect(toneFor("CLOSED")).toBe(toneFor("RECEIVED"));
    expect(toneFor("CLOSED")).toBe("ok");
  });

  it("buckets by meaning, not by module", () => {
    expect(toneFor("REJECTED")).toBe("bad");
    expect(toneFor("PARTIALLY_DELIVERED")).toBe("warn");
    expect(toneFor("DRAFT")).toBe("mute");
    expect(toneFor("SENT")).toBe("info");
  });

  it("falls back to neutral for unknown words instead of inventing a colour", () => {
    expect(toneFor("SOME_FUTURE_STATE")).toBe("mute");
  });

  it("humanizes every underscore, not just the first", () => {
    expect(humanizeStatus("PARTIALLY_RECONCILED")).toBe("Partially reconciled");
    expect(humanizeStatus("POSTED")).toBe("Posted");
  });

  it("never signals by colour alone — the label always renders", () => {
    render(<StatusPill status="PENDING_APPROVAL" />);
    expect(screen.getByText("Pending approval")).toBeInTheDocument();
  });

  it("honours an explicit tone override", () => {
    render(<StatusPill status="CLOSED" tone="bad" label="Closed early" />);
    expect(screen.getByText("Closed early")).toHaveClass("text-danger");
  });
});
