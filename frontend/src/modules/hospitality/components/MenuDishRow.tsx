/**
 * One dish's place on the menu: the heading it sits under and the labels it carries (#212, D-081).
 *
 * Both are saved in ONE call because they are edited on one row, and a half-applied edit ("moved,
 * but the tags did not take") is the failure a manager would have to unpick by hand. The row only
 * writes when Save is pressed — a select that saved on change would fire a write for every stop on
 * the way to the heading somebody meant.
 *
 * Tags are typed comma-separated rather than picked from a list: the property invents its own
 * vocabulary, and the tags already in use are offered as a datalist so the second dish is one
 * keystroke rather than a guess at last week's spelling. The server trims, lower-cases and
 * de-duplicates, so "Vegan" and "vegan " cannot both exist.
 */

import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useSetMenuPlacement } from "@/modules/hospitality/hooks";
import type { MenuPlacement, MenuSection } from "@/modules/hospitality/types";
import type { Item } from "@/modules/inventory/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

export function MenuDishRow({
  item,
  placement,
  sections,
  knownTags,
  onError,
}: {
  item: Item;
  placement: MenuPlacement | null;
  sections: MenuSection[];
  knownTags: string[];
  onError: (message: string | null) => void;
}) {
  const save = useSetMenuPlacement();
  const [sectionId, setSectionId] = useState(placement?.section_id ?? "");
  const [tags, setTags] = useState((placement?.tags ?? []).join(", "));

  const stored = placement?.section_id ?? "";
  const storedTags = (placement?.tags ?? []).join(", ");
  const dirty = sectionId !== stored || tags !== storedTags;

  const commit = async () => {
    onError(null);
    try {
      await save.mutateAsync({
        itemId: item.id,
        payload: {
          section_id: sectionId || null,
          tags: tags
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
        },
      });
    } catch (caught) {
      onError(getErrorMessage(caught, `Unable to place ${item.item_code}.`));
    }
  };

  return (
    <tr className="border-b border-line last:border-b-0">
      <td className="py-1.5 pr-2 text-ink">
        {item.item_code} — {item.name}
      </td>
      <td className="py-1.5 pr-2">
        <select
          aria-label={`Section for ${item.item_code}`}
          value={sectionId}
          onChange={(event) => setSectionId(event.target.value)}
          className={CONTROL}
        >
          <option value="">Not on the menu</option>
          {sections.map((section) => (
            <option key={section.id} value={section.id}>
              {section.parent_id
                ? `${sections.find((parent) => parent.id === section.parent_id)?.name ?? "—"} / ${section.name}`
                : section.name}
            </option>
          ))}
        </select>
      </td>
      <td className="py-1.5 pr-2">
        <input
          aria-label={`Tags for ${item.item_code}`}
          value={tags}
          onChange={(event) => setTags(event.target.value)}
          placeholder="vegan, spicy"
          list="menu-known-tags"
          className={CONTROL}
        />
        <datalist id="menu-known-tags">
          {knownTags.map((tag) => (
            <option key={tag} value={tag} />
          ))}
        </datalist>
      </td>
      <td className="py-1.5 pr-2 text-right">
        <button
          type="button"
          onClick={() => void commit()}
          disabled={!dirty || save.isPending}
          className="btn-chip"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </td>
    </tr>
  );
}
