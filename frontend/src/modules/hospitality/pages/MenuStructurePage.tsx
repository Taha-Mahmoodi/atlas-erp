/**
 * Menu — the property's own arrangement of what it sells (#212, D-081).
 *
 * Reached from Inventory rather than Hospitality on purpose: a dish IS an inventory item, this is
 * where a manager already goes to create one, and asking them to finish the job in a different
 * module is how half a menu ends up unplaced. What the screen edits is hospitality state; where it
 * lives is wherever the person doing the work already is.
 *
 * The two axes sit side by side because they are edited together and mean different things: the
 * TREE is the running order of the menu and a dish sits in exactly one heading; the TAGS are flat
 * labels a dish carries any number of. Neither is the item's accounting category, which stays on
 * the item and decides how it is valued.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useItemCategories, useItems } from "@/modules/inventory/hooks";
import { MenuSectionTree } from "@/modules/hospitality/components/MenuSectionTree";
import { MenuDishRow } from "@/modules/hospitality/components/MenuDishRow";
import {
  useMenuPlacements,
  useMenuSections,
  useMenuTags,
} from "@/modules/hospitality/hooks";

export function MenuStructurePage() {
  const sections = useMenuSections();
  const placements = useMenuPlacements();
  const tags = useMenuTags();
  const categories = useItemCategories();
  // The table is every inventory item, ingredients included — a menu page that hid them would be
  // guessing which categories a property sells from. The category filter is the honest way to cut
  // the list down, because the property already told Atlas which category its dishes are in.
  const [categoryId, setCategoryId] = useState("");
  const items = useItems(categoryId ? { category_id: categoryId } : {});
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const placementByItem = new Map(
    (placements.data?.items ?? []).map((placement) => [placement.item_id, placement]),
  );
  const dishes = (items.data?.pages.flatMap((page) => page.items) ?? []).filter((item) => {
    if (selectedSection === null) return true;
    return placementByItem.get(item.id)?.section_id === selectedSection;
  });

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/inventory" className="hover:underline">
            Inventory
          </Link>{" "}
          / <span className="text-ink">Menu</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">Menu</h1>
        <p className="mt-1 text-[13px] text-ink-muted">
          How this property arranges what it sells. A dish sits under one heading and carries any
          number of tags — separate from its item category, which decides how it is costed and
          which accounts it posts to.
        </p>
      </header>

      {error && (
        <p role="alert" className="mb-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(260px,340px)_1fr]">
        <MenuSectionTree
          sections={sections.data ?? []}
          selectedId={selectedSection}
          onSelect={setSelectedSection}
          onError={setError}
        />

        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="mono-caps text-ink-muted">
              Dishes{selectedSection !== null && " in this section"}
            </h2>
            <label className="flex items-center gap-2 text-[12px] text-ink-muted">
              Category
              <select
                value={categoryId}
                onChange={(event) => setCategoryId(event.target.value)}
                className="rounded-control border border-line bg-surface px-2 py-1 text-[13px] text-ink"
              >
                <option value="">All items</option>
                {(categories.data?.pages.flatMap((page) => page.items) ?? []).map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.code} — {category.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-line text-left mono-caps text-ink-muted">
                <th className="py-2 pr-2">Item</th>
                <th className="py-2 pr-2">Section</th>
                <th className="py-2 pr-2">Tags</th>
                <th className="py-2 pr-2" />
              </tr>
            </thead>
            <tbody>
              {dishes.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-[13px] text-ink-muted">
                    {items.isPending ? "Loading…" : "No items here yet."}
                  </td>
                </tr>
              )}
              {dishes.map((item) => (
                <MenuDishRow
                  key={item.id}
                  item={item}
                  placement={placementByItem.get(item.id) ?? null}
                  sections={sections.data ?? []}
                  knownTags={tags.data ?? []}
                  onError={(message) =>
                    setError(message === null ? null : getErrorMessage(message, message))
                  }
                />
              ))}
            </tbody>
          </table>
          {items.hasNextPage && (
            <button
              type="button"
              onClick={() => void items.fetchNextPage()}
              disabled={items.isFetchingNextPage}
              className="btn-chip mt-3"
            >
              {items.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
