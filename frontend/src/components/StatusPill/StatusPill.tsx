/**
 * The one status pill for the whole app (issue #182).
 *
 * Before this component, 53 pages each declared their own `STATUS_TONE` map, and they
 * disagreed: `CLOSED` was green in Procurement and grey in Sales; `RECEIVED` and `CLOSED`
 * shared one colour inside a single list. Colour therefore carried no reliable meaning.
 * The fix is one canonical word→tone table that every caller routes through — so a status
 * means the same thing in every module, by construction rather than by discipline.
 *
 * Never colour alone (DIRECTION.md / WCAG 1.4.1): the pill always carries its label, and the
 * tones differ in shape too — `mute` is a dashed outline with no dot, the rest are filled
 * tints with a dot.
 */

export type StatusTone = "ok" | "warn" | "bad" | "info" | "mute";

/**
 * Canonical tone per status word, keyed by the backend's own uppercase literals.
 *
 * The five buckets:
 *   ok    — settled, complete, healthy. The lifecycle ended well.
 *   info  — acknowledged and moving; nothing is wrong and nothing is owed.
 *   warn  — in flight and awaiting someone, or only partially done.
 *   bad   — failed, blocked, rejected, or past due.
 *   mute  — not yet real (draft) or deliberately void (cancelled, reversed, inactive).
 *
 * `info` is an extension beyond the register's four variants, recorded in DECISIONS.md:
 * without it, "APPROVED" and "SENT" would have to render amber and read as needing
 * attention when they need none.
 */
const TONE_BY_STATUS: Record<string, StatusTone> = {
  // ok — settled and healthy
  POSTED: "ok",
  ACTIVE: "ok",
  PAID: "ok",
  COMPLETED: "ok",
  FINISHED: "ok",
  RECEIVED: "ok",
  CLOSED: "ok",
  DELIVERED: "ok",
  INVOICED: "ok",
  RECONCILED: "ok",
  CLEARED: "ok",
  MATCHED: "ok",
  CONFIRMED: "ok",
  ACCEPTED: "ok",
  APPROVED: "ok",
  CONVERTED: "ok",
  QUALIFIED: "ok",
  WON: "ok",
  INSERT: "ok",

  // info — acknowledged, in motion, nothing owed
  SENT: "info",
  RELEASED: "info",
  FIRMED: "info",
  SCHEDULED: "info",
  PLANNED: "info",
  PLANNING: "info",
  IMPORTED: "info",
  QUOTED: "info",
  NEW: "info",
  CONTACTED: "info",
  UPDATE: "info",

  // warn — waiting on a person, or partially done
  PENDING_APPROVAL: "warn",
  SUBMITTED: "warn",
  OPEN: "warn",
  IN_PROGRESS: "warn",
  RUNNING: "warn",
  COUNTING: "warn",
  SUGGESTED: "warn",
  PARTIALLY_PAID: "warn",
  PARTIALLY_RECEIVED: "warn",
  PARTIALLY_DELIVERED: "warn",
  PARTIALLY_RECONCILED: "warn",
  QUALIFICATION: "warn",
  PROSPECTING: "warn",
  PROPOSAL: "warn",
  NEGOTIATION: "warn",
  ON_LEAVE: "warn",
  // A bank line nobody has reconciled yet is work outstanding, not a failure.
  UNMATCHED: "warn",

  // bad — failed, blocked, or past due
  REJECTED: "bad",
  FAILED: "bad",
  EXCEPTION: "bad",
  BLOCKED: "bad",
  CREDIT_BLOCKED: "bad",
  DISQUALIFIED: "bad",
  LOST: "bad",
  EXPIRED: "bad",
  TERMINATED: "bad",
  OVERDUE: "bad",
  DELETE: "bad",

  // mute — not yet real, or deliberately void
  DRAFT: "mute",
  CANCELLED: "mute",
  INACTIVE: "mute",
  REVERSED: "mute",
  RETIRED: "mute",
  FULLY_DEPRECIATED: "mute",
};

/** Unknown words stay neutral rather than inventing a colour they haven't earned. */
export function toneFor(status: string): StatusTone {
  return TONE_BY_STATUS[status.toUpperCase()] ?? "mute";
}

/** `PARTIALLY_DELIVERED` → `Partially delivered`. Every underscore, not just the first. */
export function humanizeStatus(status: string): string {
  const words = status.replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const TONE_CLASS: Record<StatusTone, string> = {
  ok: "bg-success-tint text-success",
  warn: "bg-warn-tint text-warn",
  bad: "bg-danger-tint text-danger",
  info: "bg-primary-tint text-primary",
  // Shape, not just colour: a dashed outline reads as "not committed yet" in greyscale.
  mute: "border border-dashed border-line text-ink-muted",
};

export interface StatusPillProps {
  /** The backend status literal, e.g. `PARTIALLY_DELIVERED`. */
  status: string;
  /** Override the canonical tone. Use only where a module genuinely inverts the meaning. */
  tone?: StatusTone;
  /** Override the displayed text; defaults to the humanized status. */
  label?: string;
}

export function StatusPill({ status, tone, label }: StatusPillProps) {
  const resolved = tone ?? toneFor(status);
  return (
    <span
      className={`inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium ${TONE_CLASS[resolved]}`}
    >
      {resolved !== "mute" && (
        <span aria-hidden="true" className="size-[7px] rounded-full bg-current" />
      )}
      {label ?? humanizeStatus(status)}
    </span>
  );
}
