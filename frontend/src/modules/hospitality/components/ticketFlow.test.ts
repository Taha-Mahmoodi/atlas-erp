import { describe, expect, it } from "vitest";

import {
  canCancelTicket,
  isNextStatus,
  nextTicketStatus,
} from "@/modules/hospitality/components/ticketFlow";

describe("ticketFlow", () => {
  it("offers exactly one next state, and nothing after SETTLED", () => {
    expect(nextTicketStatus("OPEN")).toBe("SENT_TO_KITCHEN");
    expect(nextTicketStatus("SENT_TO_KITCHEN")).toBe("IN_PREP");
    expect(nextTicketStatus("SERVED")).toBe("SETTLED");
    expect(nextTicketStatus("SETTLED")).toBeNull();
  });

  it("refuses a skip past SENT_TO_KITCHEN, the one point ingredients are committed", () => {
    // Skipping it would be revenue with no depletion at all — the reason the backend's own
    // lifecycle is strictly sequential rather than merely forward-only.
    expect(isNextStatus("OPEN", "IN_PREP")).toBe(false);
    expect(isNextStatus("OPEN", "SERVED")).toBe(false);
    expect(isNextStatus("SENT_TO_KITCHEN", "READY")).toBe(false);
  });

  it("refuses going backwards and standing still", () => {
    expect(isNextStatus("READY", "IN_PREP")).toBe(false);
    expect(isNextStatus("SETTLED", "OPEN")).toBe(false);
    expect(isNextStatus("IN_PREP", "IN_PREP")).toBe(false);
  });

  it("allows each adjacent step", () => {
    expect(isNextStatus("SENT_TO_KITCHEN", "IN_PREP")).toBe(true);
    expect(isNextStatus("IN_PREP", "READY")).toBe(true);
    expect(isNextStatus("READY", "SERVED")).toBe(true);
  });
});

describe("cancellation (#206, D-080)", () => {
  it("offers cancel only while the check is OPEN", () => {
    expect(canCancelTicket("OPEN")).toBe(true);
    for (const status of ["SENT_TO_KITCHEN", "IN_PREP", "READY", "SERVED", "SETTLED"] as const) {
      expect(canCancelTicket(status)).toBe(false);
    }
  });

  it("offers nothing after a check is cancelled", () => {
    // CANCELLED is not in TICKET_FLOW, so indexOf returns -1; without the guard the +1 lands on
    // TICKET_FLOW[0] and the UI would offer to fire a cancelled check.
    expect(nextTicketStatus("CANCELLED")).toBeNull();
    expect(canCancelTicket("CANCELLED")).toBe(false);
  });
});
