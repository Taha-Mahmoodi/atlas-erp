/**
 * Create or edit a BOM (STRUCTURE §4). Edit mode via `/manufacturing/boms/$bomId`; create via
 * `/manufacturing/boms/new`. Identity is (item_id, version) — both are immutable after
 * creation, `version` is a free-text field the operator picks (e.g. "1", "REV-A"), not server-
 * assigned. Only DRAFT is header-editable and only DRAFT can gain/lose components. Activating
 * requires >=1 component and demotes any prior ACTIVE+default version of the SAME item to
 * default=false (their status stays ACTIVE) — so at most one (ACTIVE, default) version exists
 * per item at a time. Deactivating clears both status->INACTIVE and default->false.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useItemOptions, useUomOptions } from "@/modules/inventory/hooks";
import {
  useActivateBom,
  useBom,
  useBomComponents,
  useCreateBom,
  useCreateBomComponent,
  useDeactivateBom,
  useDeleteBomComponent,
  useUpdateBom,
} from "@/modules/manufacturing/hooks";
import type { BomCreate, BomUpdate } from "@/modules/manufacturing/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function fieldsFor(
  isEdit: boolean,
  itemOptions: { value: string; label: string }[],
  uomOptions: { value: string; label: string }[],
): FieldDef[] {
  return [
    { name: "item_id", label: "Item", type: "select", options: itemOptions, required: true, disabled: isEdit, span: 1 },
    { name: "version", label: "Version", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    { name: "base_quantity", label: "Base quantity", type: "number", step: "0.000001", span: 1 },
    { name: "uom_id", label: "UoM", type: "select", options: uomOptions, required: true, span: 1 },
    { name: "notes", label: "Notes", type: "textarea", span: 2 },
  ];
}

function BomComponentsSection({ bomId, isDraft }: { bomId: string; isDraft: boolean }) {
  const components = useBomComponents(bomId);
  const items = useItemOptions();
  const uoms = useUomOptions();
  const createComponent = useCreateBomComponent(bomId);
  const deleteComponent = useDeleteBomComponent(bomId);
  const [componentItemId, setComponentItemId] = useState("");
  const [quantityPer, setQuantityPer] = useState("");
  const [uomId, setUomId] = useState("");
  const [scrapPercent, setScrapPercent] = useState("0");
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    setError(null);
    try {
      await createComponent.mutateAsync({
        component_item_id: componentItemId,
        quantity_per: quantityPer,
        uom_id: uomId,
        scrap_percent: scrapPercent,
      });
      setComponentItemId("");
      setQuantityPer("");
      setUomId("");
      setScrapPercent("0");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to add the component."));
    }
  };

  const remove = async (componentId: string) => {
    setError(null);
    try {
      await deleteComponent.mutateAsync(componentId);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to remove the component."));
    }
  };

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const uomLabel = (id: string) => {
    const uom = uoms.data?.items.find((u) => u.id === id);
    return uom ? uom.code : id;
  };

  return (
    <div className="mt-8 rounded-card border border-line bg-surface p-4 shadow-card">
      <h2 className="text-sm font-semibold text-ink">Components</h2>
      <p className="mt-1 text-xs text-ink-muted">
        Single-level only — a component's own BOM (if any) is resolved recursively at MRP explosion time.
      </p>
      {error && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <table className="mt-3 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-1.5 pr-2">Line</th>
            <th className="py-1.5 pr-2">Component</th>
            <th className="py-1.5 pr-2 text-right">Qty per</th>
            <th className="py-1.5 pr-2">UoM</th>
            <th className="py-1.5 pr-2 text-right">Scrap %</th>
            {isDraft && <th className="py-1.5 pr-2" />}
          </tr>
        </thead>
        <tbody>
          {(components.data ?? []).map((component) => (
            <tr key={component.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{component.line_number}</td>
              <td className="py-1.5 pr-2 text-ink">{itemLabel(component.component_item_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(component.quantity_per)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{uomLabel(component.uom_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(component.scrap_percent)}</td>
              {isDraft && (
                <td className="py-1.5 pr-2">
                  <button
                    type="button"
                    onClick={() => void remove(component.id)}
                    className="text-xs font-medium text-danger hover:underline"
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {isDraft && (
        <div className="mt-3 flex items-end gap-2">
          <div className="flex-1">
            <label htmlFor="component-item" className="mb-1 block text-xs font-medium text-ink-muted">
              Component
            </label>
            <select
              id="component-item"
              value={componentItemId}
              onChange={(event) => setComponentItemId(event.target.value)}
              className={CONTROL}
            >
              <option value="">Select item</option>
              {(items.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.item_code} — {item.name}
                </option>
              ))}
            </select>
          </div>
          <div className="w-28">
            <label htmlFor="qty-per" className="mb-1 block text-xs font-medium text-ink-muted">
              Qty per
            </label>
            <input
              id="qty-per"
              type="number"
              step="0.000001"
              value={quantityPer}
              onChange={(event) => setQuantityPer(event.target.value)}
              className={CONTROL}
            />
          </div>
          <div className="w-28">
            <label htmlFor="component-uom" className="mb-1 block text-xs font-medium text-ink-muted">
              UoM
            </label>
            <select
              id="component-uom"
              value={uomId}
              onChange={(event) => setUomId(event.target.value)}
              className={CONTROL}
            >
              <option value="">Select UoM</option>
              {(uoms.data?.items ?? []).map((uom) => (
                <option key={uom.id} value={uom.id}>
                  {uom.code}
                </option>
              ))}
            </select>
          </div>
          <div className="w-24">
            <label htmlFor="scrap-percent" className="mb-1 block text-xs font-medium text-ink-muted">
              Scrap %
            </label>
            <input
              id="scrap-percent"
              type="number"
              step="0.01"
              value={scrapPercent}
              onChange={(event) => setScrapPercent(event.target.value)}
              className={CONTROL}
            />
          </div>
          <button
            type="button"
            onClick={() => void add()}
            disabled={!componentItemId || !quantityPer || !uomId || createComponent.isPending}
            className="btn-ink"
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}

export function BomFormPage() {
  const { bomId } = useParams({ strict: false });
  const isEdit = bomId !== undefined;
  const navigate = useNavigate();

  const bom = useBom(bomId);
  const items = useItemOptions();
  const uoms = useUomOptions();
  const createBom = useCreateBom();
  const updateBom = useUpdateBom(bomId ?? "");
  const activateBom = useActivateBom(bomId ?? "");
  const deactivateBom = useDeactivateBom(bomId ?? "");

  const [values, setValues] = useState<FormValues>({ base_quantity: "1" });
  const [error, setError] = useState<string | null>(null);

  const itemOptions = (items.data?.items ?? []).map((item) => ({
    value: item.id,
    label: `${item.item_code} — ${item.name}`,
  }));
  const uomOptions = (uoms.data?.items ?? []).map((uom) => ({ value: uom.id, label: uom.code }));

  useEffect(() => {
    if (bom.data) {
      setValues({
        item_id: bom.data.item_id,
        version: bom.data.version,
        name: bom.data.name,
        base_quantity: bom.data.base_quantity,
        uom_id: bom.data.uom_id,
        notes: bom.data.notes ?? "",
      });
    }
  }, [bom.data]);

  const isDraft = !isEdit || bom.data?.status === "DRAFT";
  const isActive = bom.data?.status === "ACTIVE";

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        base_quantity: String(values.base_quantity ?? "1"),
        uom_id: String(values.uom_id ?? ""),
        notes: values.notes ? String(values.notes) : null,
      };
      if (isEdit) {
        const payload: BomUpdate = shared;
        await updateBom.mutateAsync(payload);
      } else {
        const payload: BomCreate = {
          ...shared,
          item_id: String(values.item_id ?? ""),
          version: String(values.version ?? ""),
        };
        const created = await createBom.mutateAsync(payload);
        void navigate({ to: "/manufacturing/boms/$bomId", params: { bomId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the BOM."));
    }
  };

  const activate = async () => {
    setError(null);
    try {
      await activateBom.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to activate the BOM."));
    }
  };

  const deactivate = async () => {
    setError(null);
    try {
      await deactivateBom.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to deactivate the BOM."));
    }
  };

  const busy = createBom.isPending || updateBom.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{isEdit ? "Edit BOM" : "New BOM"}</h1>
        {isEdit && bom.data && (
          <div className="flex gap-2">
            {isDraft && (
              <button
                type="button"
                onClick={() => void activate()}
                disabled={activateBom.isPending}
                className="btn-ink"
              >
                {activateBom.isPending ? "Activating…" : "Activate"}
              </button>
            )}
            {isActive && (
              <button
                type="button"
                onClick={() => void deactivate()}
                disabled={deactivateBom.isPending}
                className="btn-chip hover:border-danger hover:text-danger"
              >
                Deactivate
              </button>
            )}
          </div>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, itemOptions, uomOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create BOM"}
          busy={busy}
        />
      </div>

      {isEdit && bomId && <BomComponentsSection bomId={bomId} isDraft={Boolean(isDraft)} />}
    </div>
  );
}
