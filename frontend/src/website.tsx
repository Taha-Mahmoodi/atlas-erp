/**
 * Entry point for the GUEST site (`website.html`), the second of this package's two builds.
 *
 * It shares the repo, the toolchain and the hospitality module's types with the Atlas console and
 * nothing else: no router (the site is one page), no design system, no auth. `main.tsx` is the
 * console's entry and the two never import each other.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { WebsiteApp } from "@/modules/hospitality/website/WebsiteApp";

import "@/modules/hospitality/website/website.css";

// Its own client, not `lib/queryClient`: that one is configured for a logged-in operator (session
// invalidation, refetch on focus across dozens of screens). A guest opens one page.
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const container = document.getElementById("root");
if (!container) throw new Error("website.html is missing #root");

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <WebsiteApp />
    </QueryClientProvider>
  </StrictMode>,
);
