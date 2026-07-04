/**
 * Create or edit a vendor (STRUCTURE §4). Edit mode via `/procurement/vendors/$vendorId`;
 * create via `/procurement/vendors/new`. `vendor_code` is immutable after creation. Approved
 * items are managed inline below once the vendor exists (mirrors inventory's UoM-conversions/
 * warehouse-bins pattern) — a PO line's item must be an active approved item for its vendor,
 * so this is where that gets set up, not a separate route.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useItemOptions } from "@/modules/inventory/hooks";
import {
  useCreateVendor,
  useCreateVendorApprovedItem,
  useDeleteVendorApprovedItem,
  useUpdateVendor,
  useVendor,
  useVendorApprovedItems,
} from "@/modules/procurement/hooks";
import type { VendorCreate, VendorStatus, VendorUpdate } from "@/modules/procurement/types";

function fieldsFor(isEdit: boolean): FieldDef[] {
  return [
    { name: "vendor_code", label: "Vendor code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    { name: "default_currency_code", label: "Default currency", type: "text", required: true, span: 1 },
    { name: "payment_terms_days", label: "Payment terms (days)", type: "number", span: 1 },
    {
      name: "status",
      label: "Status",
      type: "select",
      options: [
        { value: "ACTIVE", label: "Active" },
        { value: "BLOCKED", label: "Blocked" },
        { value: "INACTIVE", label: "Inactive" },
      ],
      span: 1,
    },
    { name: "tax_reference", label: "Tax reference", type: "text", span: 1 },
    { name: "email", label: "Email", type: "text", span: 1 },
    { name: "phone", label: "Phone", type: "text", span: 1 },
    { name: "address", label: "Address", type: "textarea", span: 2 },
    { name: "notes", label: "Notes", type: "textarea", span: 2 },
  ];
}

function ApprovedItemsSection({ vendorId }: { vendorId: string }) {
  const approvedItems = useVendorApprovedItems(vendorId);
  const items = useItemOptions();
  const createApprovedItem = useCreateVendorApprovedItem(vendorId);
  const deleteApprovedItem = useDeleteVendorApprovedItem(vendorId);
  const [itemId, setItemId] = useState("");
  const [vendorItemCode, setVendorItemCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    setError(null);
    try {
      await createApprovedItem.mutateAsync({ item_id: itemId, vendor_item_code: vendorItemCode || null });
      setItemId("");
      setVendorItemCode("");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to add the approved item."));
    }
  };

  const remove = async (approvedItemId: string) => {
    setError(null);
    try {
      await deleteApprovedItem.mutateAsync(approvedItemId);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to remove the approved item."));
    }
  };

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };

  return (
    <div className="mt-8 rounded-card border border-line bg-surface p-4 shadow-card">
      <h2 className="text-sm font-semibold text-ink">Approved items</h2>
      <p className="mt-1 text-xs text-ink-muted">
        A PO line's item must be an active approved item for its vendor — this is where that's set up.
      </p>
      {error && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <table className="mt-3 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-1.5 pr-2">Item</th>
            <th className="py-1.5 pr-2">Vendor's item code</th>
            <th className="py-1.5 pr-2">Status</th>
            <th className="py-1.5 pr-2" />
          </tr>
        </thead>
        <tbody>
          {(approvedItems.data ?? []).map((approved) => (
            <tr key={approved.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(approved.item_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{approved.vendor_item_code ?? "—"}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{approved.is_active ? "Active" : "Inactive"}</td>
              <td className="py-1.5 pr-2">
                <button
                  type="button"
                  onClick={() => void remove(approved.id)}
                  className="text-xs font-medium text-danger hover:underline"
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-3 flex items-end gap-2">
        <div className="flex-1">
          <label htmlFor="approved-item" className="mb-1 block text-xs font-medium text-ink-muted">
            Item
          </label>
          <select
            id="approved-item"
            value={itemId}
            onChange={(event) => setItemId(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option value="">Select item</option>
            {(items.data?.items ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.item_code} — {item.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label htmlFor="vendor-item-code" className="mb-1 block text-xs font-medium text-ink-muted">
            Vendor's item code (optional)
          </label>
          <input
            id="vendor-item-code"
            type="text"
            value={vendorItemCode}
            onChange={(event) => setVendorItemCode(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <button
          type="button"
          onClick={() => void add()}
          disabled={!itemId || createApprovedItem.isPending}
          className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
        >
          Add
        </button>
      </div>
    </div>
  );
}

export function VendorFormPage() {
  const { vendorId } = useParams({ strict: false });
  const isEdit = vendorId !== undefined;
  const navigate = useNavigate();

  const vendor = useVendor(vendorId);
  const createVendor = useCreateVendor();
  const updateVendor = useUpdateVendor(vendorId ?? "");

  const [values, setValues] = useState<FormValues>({ status: "ACTIVE", payment_terms_days: "30" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (vendor.data) {
      setValues({
        vendor_code: vendor.data.vendor_code,
        name: vendor.data.name,
        default_currency_code: vendor.data.default_currency_code,
        payment_terms_days: String(vendor.data.payment_terms_days),
        status: vendor.data.status,
        tax_reference: vendor.data.tax_reference ?? "",
        email: vendor.data.email ?? "",
        phone: vendor.data.phone ?? "",
        address: vendor.data.address ?? "",
        notes: vendor.data.notes ?? "",
      });
    }
  }, [vendor.data]);

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        default_currency_code: String(values.default_currency_code ?? "").toUpperCase(),
        payment_terms_days: Number(values.payment_terms_days ?? 30),
        status: values.status as VendorStatus,
        tax_reference: values.tax_reference ? String(values.tax_reference) : null,
        email: values.email ? String(values.email) : null,
        phone: values.phone ? String(values.phone) : null,
        address: values.address ? String(values.address) : null,
        notes: values.notes ? String(values.notes) : null,
      };
      if (isEdit) {
        const payload: VendorUpdate = shared;
        await updateVendor.mutateAsync(payload);
      } else {
        const payload: VendorCreate = { ...shared, vendor_code: String(values.vendor_code ?? "") };
        const created = await createVendor.mutateAsync(payload);
        void navigate({ to: "/procurement/vendors/$vendorId", params: { vendorId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the vendor."));
    }
  };

  const busy = createVendor.isPending || updateVendor.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold text-ink">{isEdit ? "Edit vendor" : "New vendor"}</h1>
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
          submitLabel={isEdit ? "Save changes" : "Create vendor"}
          busy={busy}
        />
      </div>

      {isEdit && <ApprovedItemsSection vendorId={vendorId} />}
    </div>
  );
}
