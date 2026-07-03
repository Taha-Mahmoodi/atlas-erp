/**
 * Gates the whole app on session state (PLAN 15.3). On mount, attempts ONE silent refresh
 * against the HttpOnly cookie (D-008) so a page reload resumes an existing session without
 * re-entering credentials — the access token itself lives in memory only (lib/auth.ts) and
 * does not survive a reload on its own. While that resolves, nothing renders but a blank
 * canvas (sub-second in practice); afterward, unauthenticated sessions see LoginPage and
 * authenticated ones get the full AppShell around the routed content.
 */

import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { refreshAccessToken } from "@/lib/auth";
import { useIsAuthenticated } from "@/lib/session";
import { AppShell } from "@/shell/AppShell";
import { LoginPage } from "@/shell/LoginPage";

export function AuthGate({ children }: { children: ReactNode }) {
  const [booting, setBooting] = useState(true);
  const authenticated = useIsAuthenticated();

  useEffect(() => {
    let cancelled = false;
    void refreshAccessToken().finally(() => {
      if (!cancelled) setBooting(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (booting) return <div className="min-h-screen bg-canvas" />;
  if (!authenticated) return <LoginPage />;
  return <AppShell>{children}</AppShell>;
}
