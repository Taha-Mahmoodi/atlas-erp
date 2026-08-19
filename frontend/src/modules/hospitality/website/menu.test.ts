import { describe, expect, it } from "vitest";

import type { MenuAvailability, MenuItem, MenuPlacement, MenuSection } from "@/modules/hospitality/types";
import { buildMenu, remainingPortions } from "@/modules/hospitality/website/menu";

function section(id: string, name: string, sort: number, parent: string | null = null): MenuSection {
  return { id, name, parent_id: parent, sort_order: sort, dish_count: 0 };
}
function item(id: string, name: string, price: string | null = "10.00"): MenuItem {
  return {
    item_id: id,
    item_code: id.toUpperCase(),
    name,
    description: null,
    category_id: "cat",
    price,
    currency_code: price ? "USD" : null,
  };
}
function placed(itemId: string, sectionId: string | null, tags: string[] = []): MenuPlacement {
  return { item_id: itemId, section_id: sectionId, tags };
}
function board(itemId: string, state: MenuAvailability["state"], qty: string | null = null): MenuAvailability {
  return {
    item_id: itemId,
    state,
    remaining_qty: qty,
    available_until: null,
    reason: null,
    source: "MANUAL",
  };
}


/** `noUncheckedIndexedAccess` is on: an assertion that the thing exists is part of the test. */
function only<T>(values: T[], index = 0): T {
  const value = values[index];
  if (value === undefined) throw new Error(`expected an element at ${index}, got ${values.length}`);
  return value;
}

describe("buildMenu", () => {
  const sections = [section("starters", "Starters", 10), section("mains", "Mains", 20), section("grill", "From the Grill", 10, "mains")];

  it("puts only PLACED items on the menu — an ingredient is never a dish", () => {
    const courses = buildMenu(
      [item("burrata", "Burrata"), item("beef", "Ribeye Steak (kg)", null)],
      sections,
      [placed("burrata", "starters")],
      [],
    );
    expect(courses.map((c) => c.section.name)).toEqual(["Starters"]);
    expect(only(courses).dishes.map((d) => d.name)).toEqual(["Burrata"]);
  });

  it("treats absence from the 86 board as available, and an 86'd dish as listed-not-orderable", () => {
    const courses = buildMenu(
      [item("burrata", "Burrata"), item("bass", "Sea Bass")],
      sections,
      [placed("burrata", "starters"), placed("bass", "starters")],
      [board("bass", "EIGHTY_SIXED")],
    );
    const dishes = new Map(only(courses).dishes.map((d) => [d.name, d]));
    expect(dishes.get("Burrata")?.orderable).toBe(true);
    expect(dishes.get("Sea Bass")?.orderable).toBe(false);
    expect(only(courses).dishes).toHaveLength(2); // listed, not hidden
  });

  it("refuses to make an unpriced dish orderable", () => {
    const courses = buildMenu([item("tart", "Tart", null)], sections, [placed("tart", "starters")], []);
    expect(only(only(courses).dishes).orderable).toBe(false);
  });

  it("nests sub-headings under their course and drops empty ones", () => {
    const courses = buildMenu(
      [item("ribeye", "Ribeye")],
      sections,
      [placed("ribeye", "grill")],
      [],
    );
    expect(courses.map((c) => c.section.name)).toEqual(["Mains"]);
    expect(only(courses).dishes).toEqual([]);
    const grill = only(only(courses).children);
    expect(grill.section.name).toBe("From the Grill");
    expect(only(grill.dishes).name).toBe("Ribeye");
  });

  it("keeps a section whose parent is missing rather than losing its dishes", () => {
    const courses = buildMenu([item("ribeye", "Ribeye")], [only(sections, 2)], [placed("ribeye", "grill")], []);
    expect(only(courses).section.name).toBe("From the Grill");
  });

  it("reads the countdown only when the dish is on one", () => {
    const limited = only(
      only(buildMenu([item("ribeye", "Ribeye")], sections, [placed("ribeye", "starters")], [board("ribeye", "LIMITED", "4.000000")])).dishes,
    );
    expect(remainingPortions(limited)).toBe(4);
    const plain = only(
      only(buildMenu([item("burrata", "Burrata")], sections, [placed("burrata", "starters")], [])).dishes,
    );
    expect(remainingPortions(plain)).toBeNull();
  });
});
