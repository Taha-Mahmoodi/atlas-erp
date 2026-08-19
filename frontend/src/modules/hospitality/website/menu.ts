/**
 * Assembling the menu a guest reads out of the four resources Atlas serves it as.
 *
 * The API deliberately splits them because they change on four different clocks — structure when
 * a manager rewrites the menu, price on a reprice, placement when a dish moves course, and
 * availability when a table orders the last portion. Joining them is the client's job, and it is
 * pure functions here rather than logic inside a component so the two rules that matter can be
 * tested without a DOM:
 *
 * 1. **Absence from the 86 board means AVAILABLE.** The board carries only items the kitchen has
 *    said something about; treating a missing row as "unknown" (and hiding the dish) would empty
 *    a healthy menu the first time the board came back empty.
 * 2. **Only PLACED dishes are on the menu.** `GET /menu` unfiltered is every active item in the
 *    tenant, ingredients included — the contract says so. A placement under a section is what
 *    makes an item a dish, so an unplaced item is silently not part of the guest's menu. This is
 *    also why the site needs no `category_id`: the section tree already answers the question.
 */

import type { MenuAvailability, MenuItem, MenuPlacement, MenuSection } from "@/modules/hospitality/types";

export interface MenuDish extends MenuItem {
  tags: string[];
  availability: MenuAvailability | null;
  /** False when the kitchen has 86'd it, or when nothing prices it today (contract: an unpriced
   * dish is listed and NOT orderable — a misconfiguration surfaced rather than hidden). */
  orderable: boolean;
}

export interface MenuCourse {
  section: MenuSection;
  dishes: MenuDish[];
  children: MenuCourse[];
}

/** How many portions are left, or null when the dish is not on a countdown. */
export function remainingPortions(dish: MenuDish): number | null {
  const remaining = dish.availability?.remaining_qty;
  if (dish.availability?.state !== "LIMITED" || !remaining) return null;
  return Number(remaining);
}

export function buildMenu(
  items: MenuItem[],
  sections: MenuSection[],
  placements: MenuPlacement[],
  availability: MenuAvailability[],
): MenuCourse[] {
  const availabilityByItem = new Map(availability.map((row) => [row.item_id, row]));
  const placementByItem = new Map(placements.map((row) => [row.item_id, row]));

  const dishesBySection = new Map<string, MenuDish[]>();
  for (const item of items) {
    const placement = placementByItem.get(item.item_id);
    if (!placement?.section_id) continue; // an ingredient, or a dish taken off the menu
    const row = availabilityByItem.get(item.item_id) ?? null;
    const dish: MenuDish = {
      ...item,
      tags: placement.tags,
      availability: row,
      orderable: row?.state !== "EIGHTY_SIXED" && item.price !== null,
    };
    const bucket = dishesBySection.get(placement.section_id);
    if (bucket) bucket.push(dish);
    else dishesBySection.set(placement.section_id, [dish]);
  }

  // The property's own running order, then alphabetical inside a course so two dishes a manager
  // never explicitly ordered do not swap places between requests.
  const ordered = [...sections].sort(
    (a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name),
  );
  const courses = new Map<string, MenuCourse>(
    ordered.map((section) => [
      section.id,
      {
        section,
        dishes: (dishesBySection.get(section.id) ?? []).sort((a, b) => a.name.localeCompare(b.name)),
        children: [],
      },
    ]),
  );

  const roots: MenuCourse[] = [];
  for (const course of courses.values()) {
    const parent = course.section.parent_id ? courses.get(course.section.parent_id) : undefined;
    // A section whose parent is missing is rendered as a root rather than dropped: losing a whole
    // course because one heading was reparented mid-request is the worse failure.
    if (parent) parent.children.push(course);
    else roots.push(course);
  }
  return roots.filter((course) => hasDishes(course));
}

/** An empty heading is not shown — a guest reading "Desserts" under nothing learns nothing. */
function hasDishes(course: MenuCourse): boolean {
  course.children = course.children.filter((child) => hasDishes(child));
  return course.dishes.length > 0 || course.children.length > 0;
}
