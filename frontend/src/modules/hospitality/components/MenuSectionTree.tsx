/**
 * The section tree, and the row that adds a heading to it (#212, D-081).
 *
 * The API returns the tree FLAT and this nests it, which is why the wire shape stays stable when a
 * third level appears. Sections render in the property's own running order — desserts come last
 * because the restaurant says so, not because D sorts after M.
 *
 * A delete is offered on every heading and refused by the backend while anything still hangs off
 * it (409 `menu_section_not_empty`). The refusal is surfaced rather than pre-empted: hiding the
 * button would leave a manager guessing why a section cannot go, while the error names the count.
 */

import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import {
  useCreateMenuSection,
  useDeleteMenuSection,
  useUpdateMenuSection,
} from "@/modules/hospitality/hooks";
import type { MenuSection } from "@/modules/hospitality/types";

const CONTROL =
  "rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

/** Children of `parentId`, already in the order the API sorted them. */
function childrenOf(sections: MenuSection[], parentId: string | null): MenuSection[] {
  return sections.filter((section) => section.parent_id === parentId);
}

export function MenuSectionTree({
  sections,
  selectedId,
  onSelect,
  onError,
}: {
  sections: MenuSection[];
  /** The heading whose dishes the table beside this is filtered to; null means "all dishes". */
  selectedId: string | null;
  onSelect: (sectionId: string | null) => void;
  onError: (message: string | null) => void;
}) {
  const create = useCreateMenuSection();
  const update = useUpdateMenuSection();
  const remove = useDeleteMenuSection();
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const add = async () => {
    onError(null);
    if (!name.trim()) return;
    try {
      await create.mutateAsync({
        name: name.trim(),
        parent_id: parentId || null,
        // New headings land at the end of their level; reordering is its own edit.
        sort_order: childrenOf(sections, parentId || null).length + 1,
      });
      setName("");
    } catch (caught) {
      onError(getErrorMessage(caught, "Unable to add the section."));
    }
  };

  const rename = async (sectionId: string) => {
    onError(null);
    try {
      await update.mutateAsync({ sectionId, payload: { name: draft.trim() } });
      setRenaming(null);
    } catch (caught) {
      onError(getErrorMessage(caught, "Unable to rename the section."));
    }
  };

  const drop = async (sectionId: string) => {
    onError(null);
    try {
      await remove.mutateAsync(sectionId);
      if (selectedId === sectionId) onSelect(null);
    } catch (caught) {
      onError(getErrorMessage(caught, "Unable to delete the section."));
    }
  };

  const row = (section: MenuSection, depth: number) => (
    <li key={section.id}>
      <div
        className="flex items-center gap-2 rounded-control px-2 py-1.5 hover:bg-panel"
        style={{ paddingLeft: `${8 + depth * 18}px` }}
      >
        {renaming === section.id ? (
          <>
            <input
              autoFocus
              value={draft}
              maxLength={80}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void rename(section.id);
                if (event.key === "Escape") setRenaming(null);
              }}
              className={`${CONTROL} flex-1`}
            />
            <button type="button" onClick={() => void rename(section.id)} className="btn-chip">
              Save
            </button>
            <button type="button" onClick={() => setRenaming(null)} className="btn-chip">
              Cancel
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => onSelect(selectedId === section.id ? null : section.id)}
              className={`flex-1 text-left text-[13px] ${
                selectedId === section.id ? "font-medium text-ink" : "text-ink"
              }`}
            >
              {section.name}
              <span className="ml-2 tabular-nums text-ink-muted">{section.dish_count}</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setRenaming(section.id);
                setDraft(section.name);
              }}
              className="btn-chip"
            >
              Rename
            </button>
            <button type="button" onClick={() => void drop(section.id)} className="btn-chip">
              Delete
            </button>
          </>
        )}
      </div>
      {childrenOf(sections, section.id).length > 0 && (
        <ul>{childrenOf(sections, section.id).map((child) => row(child, depth + 1))}</ul>
      )}
    </li>
  );

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="mono-caps text-ink-muted">Sections</h2>
        <button
          type="button"
          onClick={() => onSelect(null)}
          className={`text-[12px] ${selectedId === null ? "text-ink" : "text-ink-muted hover:text-ink"}`}
        >
          Show all dishes
        </button>
      </div>
      {sections.length === 0 ? (
        <p className="rounded-card border border-dashed border-line px-3 py-6 text-center text-[13px] text-ink-muted">
          No sections yet. Starters, Main courses, Desserts — whatever this menu is organised by.
        </p>
      ) : (
        <ul className="rounded-card border border-line bg-surface py-1">
          {childrenOf(sections, null).map((section) => row(section, 0))}
        </ul>
      )}

      <div className="mt-3 flex flex-wrap items-end gap-2">
        <div className="flex-1">
          <label htmlFor="section-name" className="mb-1 block text-xs font-medium text-ink-muted">
            New section
          </label>
          <input
            id="section-name"
            value={name}
            maxLength={80}
            placeholder="Starters"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void add();
            }}
            className={`${CONTROL} w-full`}
          />
        </div>
        <div>
          <label htmlFor="section-parent" className="mb-1 block text-xs font-medium text-ink-muted">
            Under
          </label>
          <select
            id="section-parent"
            value={parentId}
            onChange={(event) => setParentId(event.target.value)}
            className={CONTROL}
          >
            <option value="">Nothing — a course</option>
            {sections.map((section) => (
              <option key={section.id} value={section.id}>
                {section.name}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={() => void add()}
          disabled={create.isPending || !name.trim()}
          className="btn-chip"
        >
          {create.isPending ? "Adding…" : "Add"}
        </button>
      </div>
    </div>
  );
}
