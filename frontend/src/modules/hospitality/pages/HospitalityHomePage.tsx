/**
 * The hospitality module's landing page (STRUCTURE §4), in the InventoryHomePage tile shape.
 *
 * Unlike the other module homes this one FILTERS its tiles by permission, because hospitality
 * splits read access two ways that a single property really does hand to different people: a chef
 * holds `menu.*` and a server holds `ticket.*`. Showing a server the 86 board would be a tile that
 * 403s. The backend is still the guard — this only hides an affordance nobody can use.
 */

import { Link } from "@tanstack/react-router";

import { useMe } from "@/lib/session";

const SECTIONS = [
  {
    to: "/hospitality/menu",
    label: "Menu availability",
    description: "The 86 board: what is off, what is counting down",
    permission: "hospitality.menu.read",
  },
  {
    to: "/hospitality/at-risk",
    label: "At risk",
    description: "Dishes the storeroom only covers a few more portions of",
    permission: "hospitality.menu.read",
  },
  {
    to: "/hospitality/tickets",
    label: "Tickets",
    description: "Open a check, add dishes, fire it, settle it",
    permission: "hospitality.ticket.read",
  },
  {
    to: "/hospitality/kitchen",
    label: "Kitchen display",
    description: "The pass: what is queued, cooking and ready",
    permission: "hospitality.ticket.read",
  },
] as const;

export function HospitalityHomePage() {
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const sections = SECTIONS.filter((section) => permissions.includes(section.permission));

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Hospitality</h1>
      </header>
      <section className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
        {sections.map((section) => (
          <Link
            key={section.to}
            to={section.to}
            className="rounded-card border border-line bg-surface p-4 shadow-card transition-colors duration-150 hover:border-primary"
          >
            <span className="block text-sm font-medium text-ink">{section.label}</span>
            <span className="mt-0.5 block text-xs text-ink-muted">{section.description}</span>
          </Link>
        ))}
      </section>
    </div>
  );
}
