/**
 * The designed failure and empty states (issue #180, comp 07-error-state).
 *
 * What this replaces: a bad or deleted record id used to render the edit form with every
 * field blank — indistinguishable from a wiped record, and editable, so an operator could
 * fill it in and save against something that does not exist. Vendor bills spun on "Loading…"
 * forever. Both failures were silent; the 4xx only appeared in the devtools console.
 *
 * The rule here is that a failure says what happened, says whether anything changed, and
 * offers a way out — never a spinner, never a blank form.
 */

import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/apiClient";
import { Icon, type IconName } from "@/components/Icon";

interface StateShellProps {
  icon: IconName;
  title: string;
  body: ReactNode;
  action?: ReactNode;
  /** `alert` for failures a person needs to notice; empty states are not alerts. */
  isAlert?: boolean;
}

function StateShell({ icon, title, body, action, isAlert }: StateShellProps) {
  return (
    <div
      {...(isAlert ? { role: "alert" } : {})}
      className="mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-16 text-center"
    >
      <span className="flex size-11 items-center justify-center rounded-full bg-panel text-ink-muted">
        <Icon name={icon} size={20} />
      </span>
      <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
      <p className="text-[13px] leading-5 text-ink-muted">{body}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Human copy per failure class. Deliberately plain: no apology, no error code as a headline. */
function describe(error: unknown): { icon: IconName; title: string; body: string } {
  const status = error instanceof ApiError ? error.status : 0;

  if (status === 403) {
    return {
      icon: "shield-check",
      title: "You don't have access to this",
      body: "Your role doesn't include this record. Ask an administrator if you need it.",
    };
  }
  if (status === 404 || status === 410) {
    return {
      icon: "search",
      title: "This record wasn't found",
      body: "It may have been deleted, or the link may be wrong. Nothing was changed.",
    };
  }
  if (status >= 400 && status < 500) {
    // The #180 case: a malformed id 422s on the way in.
    return {
      icon: "search",
      title: "This record couldn't be opened",
      body: "The link points at something Atlas can't read. Nothing was changed.",
    };
  }
  return {
    icon: "alert",
    title: "Something went wrong",
    body: "Atlas couldn't load this. Nothing was changed — try again in a moment.",
  };
}

export interface ErrorStateProps {
  error: unknown;
  /** Retry affordance, wired to the boundary's reset or a query refetch. */
  onRetry?: () => void;
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  const { icon, title, body } = describe(error);
  const serverSide = !(error instanceof ApiError) || error.status >= 500;

  return (
    <StateShell
      isAlert
      icon={icon}
      title={title}
      body={body}
      action={
        <div className="flex items-center gap-2">
          {/* Retry only where retrying can plausibly help — a 404 will 404 again. */}
          {serverSide && onRetry && (
            <button type="button" onClick={onRetry} className="btn-chip btn-tall">
              Try again
            </button>
          )}
          <Link to="/" className="btn-ink btn-tall">
            Back to home
          </Link>
        </div>
      }
    />
  );
}

export interface EmptyStateProps {
  title: string;
  body: ReactNode;
  action?: ReactNode;
  icon?: IconName;
}

/**
 * The nothing-here-yet state. Distinct from a *filtered*-empty state, which must say so and
 * offer to clear the filter — `DataGrid` handles that distinction for lists.
 */
export function EmptyState({ title, body, action, icon = "box" }: EmptyStateProps) {
  return <StateShell icon={icon} title={title} body={body} action={action} />;
}
