/**
 * 86 a dish or start a countdown on it (spec Q2) — the write half of the availability board.
 *
 * It offers LIMITED and EIGHTY_SIXED only, deliberately. AVAILABLE is spelled by the ABSENCE of a
 * row (the backend's `clear_86` deletes rather than flips), so putting it in this dropdown would
 * give "back on the menu" two spellings, one of which leaves a row behind. The board's Clear
 * action is the other half of this component.
 */

import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { endOfLocalDay, localDateInput } from "@/modules/hospitality/components/availabilityDates";
import { useMenu, useSetAvailability } from "@/modules/hospitality/hooks";
import type { AvailabilityState, MenuAvailability } from "@/modules/hospitality/types";

export function AvailabilityEditor({
  existing,
  onDone,
}: {
  /** The row being edited; absent means a new override, and the item becomes selectable. */
  existing?: MenuAvailability;
  onDone: () => void;
}) {
  const menu = useMenu();
  const setAvailability = useSetAvailability();
  const [values, setValues] = useState<FormValues>({
    item_id: existing?.item_id ?? "",
    state: existing?.state === "LIMITED" ? "LIMITED" : "EIGHTY_SIXED",
    remaining_qty: existing?.remaining_qty ?? "",
    available_until: existing?.available_until ? localDateInput(existing.available_until) : "",
    reason: existing?.reason ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const fields: FieldDef[] = [
    {
      name: "item_id",
      label: "Dish",
      type: "select",
      required: true,
      disabled: existing !== undefined,
      span: 2,
      options: (menu.data?.items ?? []).map((item) => ({
        value: item.item_id,
        label: `${item.item_code} — ${item.name}`,
      })),
    },
    {
      name: "state",
      label: "State",
      type: "select",
      required: true,
      options: [
        { value: "EIGHTY_SIXED", label: "86'd — off the menu" },
        { value: "LIMITED", label: "Limited — countdown" },
      ],
    },
    {
      name: "remaining_qty",
      label: "Portions left",
      type: "number",
      step: "0.000001",
      help: "Required for a countdown. Every order burns one; the dish 86s itself at zero.",
    },
    {
      name: "available_until",
      label: "In effect through",
      type: "date",
      help: "The override lapses at the end of this date, local time. Blank keeps it until cleared.",
    },
    { name: "reason", label: "Reason", type: "text", span: 2, placeholder: "Out of feta" },
  ];

  const submit = async () => {
    const itemId = String(values.item_id ?? "");
    const state = String(values.state ?? "") as AvailabilityState;
    const remaining = String(values.remaining_qty ?? "").trim();
    const until = String(values.available_until ?? "").trim();
    const reason = String(values.reason ?? "").trim();

    // Checked here, not by FormBuilder's `required` flag, which is decorative until #164 — and
    // the backend refuses this pair twice over (schema + service `countdown_required`), so
    // catching it now saves a round trip rather than replacing a guard.
    const found: Record<string, string> = {};
    if (!itemId) found.item_id = "Pick the dish this applies to.";
    if (state === "LIMITED" && !remaining) {
      found.remaining_qty = "A countdown needs a portion count — without one it could never flip.";
    }
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setError(null);
    try {
      await setAvailability.mutateAsync({
        itemId,
        payload: {
          state,
          remaining_qty: state === "LIMITED" ? remaining : null,
          available_until: until ? endOfLocalDay(until) : null,
          reason: reason || null,
        },
      });
      onDone();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to set the availability."));
    }
  };

  return (
    <div className="mt-6 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
      <h2 className="mb-3.5 mono-caps text-ink-muted">
        {existing ? "Update availability" : "Set availability"}
      </h2>
      {error && (
        <p role="alert" className="mb-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <FormBuilder
        fields={fields}
        values={values}
        errors={errors}
        onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
        onSubmit={() => void submit()}
        submitLabel="Save"
        busy={setAvailability.isPending}
        footer={
          <button type="button" onClick={onDone} className="btn-chip">
            Cancel
          </button>
        }
      />
    </div>
  );
}
