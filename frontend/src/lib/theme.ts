/**
 * Light/dark theme, stored per browser (DIRECTION.md: the two palettes are equals, not a
 * default plus an afterthought). "system" follows the OS and keeps following it when the OS
 * flips mid-session.
 *
 * The class is applied by the inline boot script in index.html BEFORE first paint — this
 * module only handles changes after that, so there is never a light flash on load.
 */

import { useSyncExternalStore } from "react";

export type ThemePreference = "light" | "dark" | "system";

const STORAGE_KEY = "atlas.theme";
const listeners = new Set<() => void>();
const media = typeof window === "undefined" ? null : window.matchMedia("(prefers-color-scheme: dark)");

function read(): ThemePreference {
  const stored = typeof localStorage === "undefined" ? null : localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

/** The theme actually painted right now, with "system" resolved against the OS. */
export function resolveTheme(preference: ThemePreference): "light" | "dark" {
  if (preference !== "system") return preference;
  return media?.matches ? "dark" : "light";
}

function apply(preference: ThemePreference): void {
  document.documentElement.classList.toggle("dark", resolveTheme(preference) === "dark");
}

export function setTheme(preference: ThemePreference): void {
  if (preference === "system") localStorage.removeItem(STORAGE_KEY);
  else localStorage.setItem(STORAGE_KEY, preference);
  apply(preference);
  listeners.forEach((listener) => listener());
}

// An OS-level flip only repaints while the preference is "system"; an explicit choice wins.
media?.addEventListener("change", () => {
  if (read() === "system") {
    apply("system");
    listeners.forEach((listener) => listener());
  }
});

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): ThemePreference {
  return useSyncExternalStore(subscribe, read, () => "system" as const);
}
