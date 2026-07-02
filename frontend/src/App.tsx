/**
 * The application frame: providers only for now (TanStack Query). The 15.3 app shell
 * (navigation, login gate, role-based home) mounts inside this component so providers
 * never re-mount across route changes.
 */

import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { queryClient } from "@/lib/queryClient";

export function App({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
