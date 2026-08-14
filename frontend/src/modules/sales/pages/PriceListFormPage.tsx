/**
 * Create or edit a price list (STRUCTURE §4). Edit mode via `/sales/price-lists/$priceListId`;
 * create via `/sales/price-lists/new`. `code` is immutable after creation. Line items (item +
 * unit price + minimum quantity) are managed inline below once the list exists — mirrors
 * procurement's vendor-approved-items pattern.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatQuantity } from "@/lib/format";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useItemOptions } from "@/modules/inventory/hooks";
import {
  useCreatePriceList,
  useCreatePriceListItem,
  useCustomerGroupOptions,
  useDeletePriceListItem,
  usePriceList,
  usePriceListItems,
  useUpdatePriceList,
} from "@/modules/sales/hooks";
import type { PriceListCreate, PriceListStatus, PriceListUpdate } from "@/modules/sales/types";

function fieldsFor(isEdit: boolean, groupOptions: { value: string; label: string }[]): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    { name: "currency_code", label: "Currency", type: "text", required: true, span: 1 },
    { name: "priority", label: "Priority", type: "number", span: 1 },
    {
      name: "customer_group_id",
      label: "Customer group",
      type: "select",
      options: groupOptions,
      help: "Leave unset to apply to every customer.",
      span: 1,
    },
    {
      name: "status",
      label: "Status",
      type: "select",
      options: [
        { value: "ACTIVE", label: "Active" },
        { value: "INACTIVE", label: "Inactive" },
      ],
      span: 1,
    },
    { name: "valid_from", label: "Valid from", type: "date", required: true, span: 1 },
    { name: "valid_to", label: "Valid to", type: "date", help: "Leave unset for open-ended.", span: 1 },
  ];
}

function PriceListItemsSection({ priceListId, currencyCode }: { priceListId: string; currencyCode: string }) {
  const priceListItems = usePriceListItems(priceListId);
  const items = useItemOptions();
  const createItem = useCreatePriceListItem(priceListId);
  const deleteItem = useDeletePriceListItem(priceListId);
  const [itemId, setItemId] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [minQuantity, setMinQuantity] = useState("0");
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    setError(null);
    try {
      await createItem.mutateAsync({ item_id: itemId, unit_price: unitPrice, min_quantity: minQuantity });
      setItemId("");
      setUnitPrice("");
      setMinQuantity("0");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to add the price."));
    }
  };

  const remove = async (lineItemId: string) => {
    setError(null);
    try {
      await deleteItem.mutateAsync(lineItemId);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to remove the price."));
    }
  };

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };

  return (
    <div className="mt-8 rounded-card border border-line bg-surface p-4 shadow-card">
      <h2 className="text-sm font-semibold text-ink">Prices</h2>
      <p className="mt-1 text-xs text-ink-muted">
        One flat price per item; the minimum quantity is the only quantity break this list supports.
      </p>
      {error && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <table className="mt-3 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-1.5 pr-2">Item</th>
            <th className="py-1.5 pr-2 text-right">Unit price</th>
            <th className="py-1.5 pr-2 text-right">Min. quantity</th>
            <th className="py-1.5 pr-2" />
          </tr>
        </thead>
        <tbody>
          {(priceListItems.data ?? []).map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.unit_price, currencyCode)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.min_quantity)}</td>
              <td className="py-1.5 pr-2">
                <button
                  type="button"
                  onClick={() => void remove(line.id)}
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
          <label htmlFor="price-item" className="mb-1 block text-xs font-medium text-ink-muted">
            Item
          </label>
          <select
            id="price-item"
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
        <div className="w-32">
          <label htmlFor="price-unit-price" className="mb-1 block text-xs font-medium text-ink-muted">
            Unit price
          </label>
          <input
            id="price-unit-price"
            type="number"
            step="0.01"
            value={unitPrice}
            onChange={(event) => setUnitPrice(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <div className="w-32">
          <label htmlFor="price-min-quantity" className="mb-1 block text-xs font-medium text-ink-muted">
            Min. quantity
          </label>
          <input
            id="price-min-quantity"
            type="number"
            step="0.000001"
            value={minQuantity}
            onChange={(event) => setMinQuantity(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <button
          type="button"
          onClick={() => void add()}
          disabled={!itemId || !unitPrice || createItem.isPending}
          className="btn-ink"
        >
          Add
        </button>
      </div>
    </div>
  );
}

export function PriceListFormPage() {
  const { priceListId } = useParams({ strict: false });
  const isEdit = priceListId !== undefined;
  const navigate = useNavigate();

  const priceList = usePriceList(priceListId);
  const groups = useCustomerGroupOptions();
  const createPriceList = useCreatePriceList();
  const updatePriceList = useUpdatePriceList(priceListId ?? "");

  const [values, setValues] = useState<FormValues>({ status: "ACTIVE", priority: "0" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (priceList.data) {
      setValues({
        code: priceList.data.code,
        name: priceList.data.name,
        currency_code: priceList.data.currency_code,
        priority: String(priceList.data.priority),
        customer_group_id: priceList.data.customer_group_id ?? "",
        status: priceList.data.status,
        valid_from: priceList.data.valid_from,
        valid_to: priceList.data.valid_to ?? "",
      });
    }
  }, [priceList.data]);

  const groupOptions = (groups.data?.items ?? []).map((group) => ({
    value: group.id,
    label: `${group.code} — ${group.name}`,
  }));

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        currency_code: String(values.currency_code ?? "").toUpperCase(),
        priority: Number(values.priority ?? 0),
        customer_group_id: values.customer_group_id ? String(values.customer_group_id) : null,
        status: values.status as PriceListStatus,
        valid_from: String(values.valid_from ?? ""),
        valid_to: values.valid_to ? String(values.valid_to) : null,
      };
      if (isEdit) {
        const payload: PriceListUpdate = shared;
        await updatePriceList.mutateAsync(payload);
      } else {
        const payload: PriceListCreate = { ...shared, code: String(values.code ?? "") };
        const created = await createPriceList.mutateAsync(payload);
        void navigate({ to: "/sales/price-lists/$priceListId", params: { priceListId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the price list."));
    }
  };

  const busy = createPriceList.isPending || updatePriceList.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{isEdit ? "Edit price list" : "New price list"}</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, groupOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create price list"}
          busy={busy}
        />
      </div>

      {isEdit && (
        <PriceListItemsSection priceListId={priceListId} currencyCode={priceList.data?.currency_code ?? "—"} />
      )}
    </div>
  );
}
