/**
 * Create or edit an item (STRUCTURE §4). Edit mode via `/inventory/items/$itemId`; create via
 * `/inventory/items/new`. `item_code` and `item_type` are immutable after creation. UoM
 * conversions are managed inline below the form once the item exists (they nest under the
 * item, `/items/{id}/uom-conversions`, so there's nothing to show until it's saved).
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import {
  useCreateItem,
  useCreateUomConversion,
  useItem,
  useItemCategoryOptions,
  useUomConversions,
  useUomOptions,
  useUpdateItem,
} from "@/modules/inventory/hooks";
import type { CostingMethod, ItemCreate, ItemType, ItemUpdate, TrackingMode } from "@/modules/inventory/types";

function fieldsFor(
  isEdit: boolean,
  categoryOptions: { value: string; label: string }[],
  uomOptions: { value: string; label: string }[],
): FieldDef[] {
  return [
    { name: "item_code", label: "Item code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    { name: "description", label: "Description", type: "textarea", span: 2 },
    {
      name: "item_type",
      label: "Type",
      type: "select",
      required: true,
      disabled: isEdit,
      options: [
        { value: "STOCKED", label: "Stocked" },
        { value: "NON_STOCKED", label: "Non-stocked" },
        { value: "SERVICE", label: "Service" },
      ],
      span: 1,
    },
    {
      name: "tracking_mode",
      label: "Tracking mode",
      type: "select",
      options: [
        { value: "NONE", label: "None" },
        { value: "LOT", label: "Lot" },
        { value: "SERIAL", label: "Serial" },
      ],
      span: 1,
    },
    { name: "category_id", label: "Category", type: "select", required: true, options: categoryOptions, span: 1 },
    { name: "base_uom_id", label: "Base UoM", type: "select", required: true, options: uomOptions, span: 1 },
    {
      name: "costing_method",
      label: "Costing method",
      type: "select",
      options: [
        { value: "MOVING_AVERAGE", label: "Moving average" },
        { value: "FIFO", label: "FIFO" },
      ],
      help: "Leave unset to inherit the category's default.",
      span: 1,
    },
    { name: "is_active", label: "Active", type: "checkbox", span: 1 },
    { name: "reorder_point", label: "Reorder point", type: "number", step: "0.01", span: 1 },
    { name: "reorder_quantity", label: "Reorder quantity", type: "number", step: "0.01", span: 1 },
  ];
}

function UomConversionsSection({ itemId }: { itemId: string }) {
  const conversions = useUomConversions(itemId);
  const uoms = useUomOptions();
  const createConversion = useCreateUomConversion(itemId);
  const [altUomId, setAltUomId] = useState("");
  const [factor, setFactor] = useState("");
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    setError(null);
    try {
      await createConversion.mutateAsync({ alt_uom_id: altUomId, factor_to_base: factor });
      setAltUomId("");
      setFactor("");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to add the conversion."));
    }
  };

  return (
    <div className="mt-8 rounded-card border border-line bg-surface p-4 shadow-card">
      <h2 className="text-sm font-semibold text-ink">UoM conversions</h2>
      <p className="mt-1 text-xs text-ink-muted">
        1 alt unit = factor × base unit (e.g. base EA, alt BOX, factor 12 ⇒ 1 BOX = 12 EA).
      </p>
      {error && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <table className="mt-3 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-1.5 pr-2">Alt UoM</th>
            <th className="py-1.5 pr-2 text-right">Factor to base</th>
          </tr>
        </thead>
        <tbody>
          {(conversions.data ?? []).map((conversion) => (
            <tr key={conversion.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">
                {uoms.data?.items.find((u) => u.id === conversion.alt_uom_id)?.code ?? conversion.alt_uom_id}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums text-ink">{conversion.factor_to_base}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-3 flex items-end gap-2">
        <div className="flex-1">
          <label htmlFor="alt-uom" className="mb-1 block text-xs font-medium text-ink-muted">
            Alt UoM
          </label>
          <select
            id="alt-uom"
            value={altUomId}
            onChange={(event) => setAltUomId(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option value="">Select…</option>
            {(uoms.data?.items ?? []).map((uom) => (
              <option key={uom.id} value={uom.id}>
                {uom.code} — {uom.name}
              </option>
            ))}
          </select>
        </div>
        <div className="w-32">
          <label htmlFor="factor" className="mb-1 block text-xs font-medium text-ink-muted">
            Factor
          </label>
          <input
            id="factor"
            type="number"
            step="0.000001"
            value={factor}
            onChange={(event) => setFactor(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <button
          type="button"
          onClick={() => void add()}
          disabled={!altUomId || !factor || createConversion.isPending}
          className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
        >
          Add
        </button>
      </div>
    </div>
  );
}

export function ItemFormPage() {
  const { itemId } = useParams({ strict: false });
  const isEdit = itemId !== undefined;
  const navigate = useNavigate();

  const item = useItem(itemId);
  const categories = useItemCategoryOptions();
  const uoms = useUomOptions();
  const createItem = useCreateItem();
  const updateItem = useUpdateItem(itemId ?? "");

  const [values, setValues] = useState<FormValues>({ tracking_mode: "NONE", is_active: true });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (item.data) {
      setValues({
        item_code: item.data.item_code,
        name: item.data.name,
        description: item.data.description ?? "",
        item_type: item.data.item_type,
        tracking_mode: item.data.tracking_mode,
        category_id: item.data.category_id,
        base_uom_id: item.data.base_uom_id,
        costing_method: item.data.costing_method,
        is_active: item.data.is_active,
        reorder_point: item.data.reorder_point ?? "",
        reorder_quantity: item.data.reorder_quantity ?? "",
      });
    }
  }, [item.data]);

  const categoryOptions = (categories.data?.items ?? []).map((category) => ({
    value: category.id,
    label: `${category.code} — ${category.name}`,
  }));
  const uomOptions = (uoms.data?.items ?? []).map((uom) => ({ value: uom.id, label: `${uom.code} — ${uom.name}` }));

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        description: values.description ? String(values.description) : null,
        category_id: String(values.category_id ?? ""),
        base_uom_id: String(values.base_uom_id ?? ""),
        tracking_mode: values.tracking_mode as TrackingMode,
        is_active: Boolean(values.is_active),
        reorder_point: values.reorder_point ? String(values.reorder_point) : null,
        reorder_quantity: values.reorder_quantity ? String(values.reorder_quantity) : null,
        ...(values.costing_method
          ? { costing_method: values.costing_method as CostingMethod }
          : {}),
      };
      if (isEdit) {
        const payload: ItemUpdate = shared;
        await updateItem.mutateAsync(payload);
      } else {
        const payload: ItemCreate = {
          ...shared,
          item_code: String(values.item_code ?? ""),
          item_type: values.item_type as ItemType,
        };
        const created = await createItem.mutateAsync(payload);
        void navigate({ to: "/inventory/items/$itemId", params: { itemId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the item."));
    }
  };

  const busy = createItem.isPending || updateItem.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold text-ink">{isEdit ? "Edit item" : "New item"}</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, categoryOptions, uomOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create item"}
          busy={busy}
        />
      </div>

      {isEdit && <UomConversionsSection itemId={itemId} />}
    </div>
  );
}
