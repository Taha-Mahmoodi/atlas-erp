/**
 * Create or edit a warehouse (STRUCTURE §4). Edit mode via
 * `/inventory/warehouses/$warehouseId`; create via `/inventory/warehouses/new`. `code` is
 * immutable after creation. Bins are managed inline below once the warehouse exists (mirrors
 * ItemFormPage's UoM-conversions section) — "exactly one default bin per warehouse" is a
 * service convention, not a DB constraint, so this UI doesn't assume/enforce uniqueness either.
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import {
  useBins,
  useCreateBin,
  useCreateWarehouse,
  useUpdateWarehouse,
  useWarehouse,
} from "@/modules/inventory/hooks";
import type { WarehouseCreate, WarehouseUpdate } from "@/modules/inventory/types";

function fieldsFor(isEdit: boolean): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    { name: "is_active", label: "Active", type: "checkbox", span: 2 },
  ];
}

function BinsSection({ warehouseId }: { warehouseId: string }) {
  const bins = useBins({ warehouse_id: warehouseId });
  const createBin = useCreateBin();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rows = bins.data?.pages.flatMap((page) => page.items) ?? [];

  const add = async () => {
    setError(null);
    try {
      await createBin.mutateAsync({ warehouse_id: warehouseId, code, name, is_default: isDefault });
      setCode("");
      setName("");
      setIsDefault(false);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to add the bin."));
    }
  };

  return (
    <div className="mt-8 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
      <h2 className="mb-3.5 mono-caps text-ink-muted">Bins</h2>
      {error && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <table className="mt-3 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-1.5 pr-2">Code</th>
            <th className="py-1.5 pr-2">Name</th>
            <th className="py-1.5 pr-2">Default</th>
            <th className="py-1.5 pr-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((bin) => (
            <tr key={bin.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{bin.code}</td>
              <td className="py-1.5 pr-2 text-ink">{bin.name}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{bin.is_default ? "Yes" : "—"}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{bin.is_active ? "Active" : "Inactive"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-3 flex items-end gap-2">
        <div className="flex-1">
          <label htmlFor="bin-code" className="mb-1 block text-xs font-medium text-ink-muted">
            Code
          </label>
          <input
            id="bin-code"
            type="text"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <div className="flex-1">
          <label htmlFor="bin-name" className="mb-1 block text-xs font-medium text-ink-muted">
            Name
          </label>
          <input
            id="bin-name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <label className="mb-2 flex items-center gap-1.5 text-sm text-ink">
          <input type="checkbox" checked={isDefault} onChange={(event) => setIsDefault(event.target.checked)} />
          Default
        </label>
        <button
          type="button"
          onClick={() => void add()}
          disabled={!code || !name || createBin.isPending}
          className="btn-ink"
        >
          Add
        </button>
      </div>
    </div>
  );
}

export function WarehouseFormPage() {
  const { warehouseId } = useParams({ strict: false });
  const isEdit = warehouseId !== undefined;
  const navigate = useNavigate();

  const warehouse = useWarehouse(warehouseId);
  const createWarehouse = useCreateWarehouse();
  const updateWarehouse = useUpdateWarehouse(warehouseId ?? "");

  const [values, setValues] = useState<FormValues>({ is_active: true });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (warehouse.data) {
      setValues({ code: warehouse.data.code, name: warehouse.data.name, is_active: warehouse.data.is_active });
    }
  }, [warehouse.data]);

  const submit = async () => {
    setError(null);
    try {
      if (isEdit) {
        const payload: WarehouseUpdate = { name: String(values.name ?? ""), is_active: Boolean(values.is_active) };
        await updateWarehouse.mutateAsync(payload);
        void navigate({ to: "/inventory/warehouses/$warehouseId", params: { warehouseId: warehouseId! } });
      } else {
        const payload: WarehouseCreate = {
          code: String(values.code ?? ""),
          name: String(values.name ?? ""),
          is_active: Boolean(values.is_active),
        };
        const created = await createWarehouse.mutateAsync(payload);
        void navigate({ to: "/inventory/warehouses/$warehouseId", params: { warehouseId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the warehouse."));
    }
  };

  const busy = createWarehouse.isPending || updateWarehouse.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/inventory/warehouses">Warehouses</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit warehouse" : "New warehouse"}</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {isEdit ? "Edit warehouse" : "New warehouse"}
        </h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create warehouse"}
          busy={busy}
        />
      </div>

      {isEdit && <BinsSection warehouseId={warehouseId} />}
    </div>
  );
}
