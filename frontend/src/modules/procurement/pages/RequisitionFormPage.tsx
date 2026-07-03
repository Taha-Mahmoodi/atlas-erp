/**
 * Create or edit a purchase requisition (STRUCTURE §4). Edit mode via
 * `/procurement/requisitions/$requisitionId/edit`; create via `/procurement/requisitions/new`.
 * Only a DRAFT requisition can be edited (enforced server-side) — PATCH replaces the whole
 * line set wholesale, so this page always submits the full current line array, never a diff.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useItemOptions, useUomOptions } from "@/modules/inventory/hooks";
import { RequisitionLinesEditor } from "@/modules/procurement/components/RequisitionLinesEditor";
import { useCreateRequisition, useRequisition, useUpdateRequisition } from "@/modules/procurement/hooks";
import type { RequisitionLineCreate } from "@/modules/procurement/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function RequisitionFormPage() {
  const { requisitionId } = useParams({ strict: false });
  const isEdit = requisitionId !== undefined;
  const navigate = useNavigate();

  const requisition = useRequisition(requisitionId);
  const items = useItemOptions();
  const uoms = useUomOptions();
  const createRequisition = useCreateRequisition();
  const updateRequisition = useUpdateRequisition(requisitionId ?? "");

  const [neededByDate, setNeededByDate] = useState(today());
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<RequisitionLineCreate[]>([
    { item_id: "", quantity: "", uom_id: "", currency_code: "USD" },
  ]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (requisition.data) {
      setNeededByDate(requisition.data.needed_by_date ?? "");
      setNotes(requisition.data.notes ?? "");
      setLines(
        requisition.data.lines.map((line) => ({
          item_id: line.item_id,
          description: line.description,
          quantity: line.quantity,
          uom_id: line.uom_id,
          estimated_unit_cost: line.estimated_unit_cost,
          currency_code: line.currency_code,
        })),
      );
    }
  }, [requisition.data]);

  const validLines = lines.filter((line) => line.item_id && line.uom_id && (Number(line.quantity) || 0) > 0);
  const canSubmit = validLines.length > 0;

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        needed_by_date: neededByDate || null,
        notes: notes || null,
        lines: validLines,
      };
      if (isEdit) {
        await updateRequisition.mutateAsync(shared);
        void navigate({ to: "/procurement/requisitions/$requisitionId", params: { requisitionId } });
      } else {
        const created = await createRequisition.mutateAsync(shared);
        void navigate({ to: "/procurement/requisitions/$requisitionId", params: { requisitionId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the requisition."));
    }
  };

  const busy = createRequisition.isPending || updateRequisition.isPending;

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-xl font-semibold text-ink">{isEdit ? "Edit requisition" : "New requisition"}</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="needed-by" className="mb-1 block text-xs font-medium text-ink-muted">
            Needed by
          </label>
          <input
            id="needed-by"
            type="date"
            value={neededByDate}
            onChange={(event) => setNeededByDate(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="notes" className="mb-1 block text-xs font-medium text-ink-muted">
            Notes
          </label>
          <input
            id="notes"
            type="text"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            className={CONTROL}
          />
        </div>
      </div>

      <div className="mt-6">
        <RequisitionLinesEditor
          lines={lines}
          items={items.data?.items ?? []}
          uoms={uoms.data?.items ?? []}
          onChange={setLines}
        />
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || busy}
        className="mt-6 rounded-control bg-primary px-4 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
      >
        {busy ? "Saving…" : isEdit ? "Save changes" : "Create draft"}
      </button>
    </div>
  );
}
