/**
 * The one error boundary the app was missing (CURRENT.md: "no ErrorBoundary exists anywhere
 * in the source tree" — an unexpected render error had no designed fallback at all).
 *
 * Paired with `throwOnError` in lib/queryClient.ts, this is the single-point fix for #180:
 * a detail query that 4xxs throws here instead of leaving the page to render a blank form or
 * an endless spinner, so all ~250 pages get the designed error state without per-page edits.
 *
 * `resetKey` is the route path — navigating anywhere clears the error, otherwise a failure on
 * one record would strand the operator on the error screen for the rest of the session.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorState } from "./ErrorState";

interface Props {
  children: ReactNode;
  resetKey: string;
}

interface State {
  error: unknown;
}

export class RouteErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error };
  }

  componentDidUpdate(previous: Props): void {
    if (previous.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    // Kept: without it a caught error leaves no trace anywhere, which is how the silent
    // failures in #180 stayed invisible for so long.
    console.error("Unhandled error while rendering a route", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return <ErrorState error={this.state.error} onRetry={() => this.setState({ error: null })} />;
    }
    return this.props.children;
  }
}
