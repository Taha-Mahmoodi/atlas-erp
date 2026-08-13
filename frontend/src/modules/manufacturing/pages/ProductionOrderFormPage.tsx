/**
 * Create a production order (STRUCTURE §4). Create-only — the server explodes the BOM into
 * component reservations and snapshots the routing at create, so there is no edit mode; the
 * lifecycle advances on the detail workbench. BOM/routing are optional: omitted, the server
 * resolves the item's ACTIVE default (422 manufacturing.no_active_bom when there is none).
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useItemOptions, useWarehouseOptions } from "@/modules/inventory/hooks";
import { useBoms, useCreateProductionOrder, useRoutings } from "@/modules/manufacturing/hooks";
import type { ProductionOrderCreate } from "@/modules/manufacturing/types";

export function ProductionOrderFormPage() {
  const navigate = useNavigate();
  const items = useItemOptions();
  const warehouses = useWarehouseOptions();
  const createOrder = useCreateProductionOrder();

  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  const itemId = String(values.item_id ?? "");
  // Version pickers for the chosen item — optional overrides of the active default.
  const boms = useBoms(itemId ? { item_id: itemId } : {});
  const routings = useRoutings(itemId ? { item_id: itemId } : {});

  const itemOptions = (items.data?.items ?? []).map((item) => ({
    value: item.id,
    label: `${item.item_code} — ${item.name}`,
  }));
  const warehouseOptions = (warehouses.data?.items ?? []).map((warehouse) => ({
    value: warehouse.id,
    label: `${warehouse.code} — ${warehouse.name}`,
  }));
  const bomOptions = itemId
    ? (boms.data?.pages.flatMap((page) => page.items) ?? []).map((bom) => ({
        value: bom.id,
        label: `${bom.version} — ${bom.name}${bom.is_default ? " (default)" : ""}`,
      }))
    : [];
  const routingOptions = itemId
    ? (routings.data?.pages.flatMap((page) => page.items) ?? []).map((routing) => ({
        value: routing.id,
        label: `${routing.version} — ${routing.name}${routing.is_default ? " (default)" : ""}`,
      }))
    : [];

  const fields: FieldDef[] = [
    { name: "item_id", label: "Item", type: "select", options: itemOptions, required: true, span: 1 },
    { name: "quantity", label: "Quantity", type: "number", step: "0.000001", required: true, span: 1 },
    { name: "warehouse_id", label: "Warehouse", type: "select", options: warehouseOptions, required: true, span: 1, help: "Components issue from here; finished goods land here" },
    { name: "bom_id", label: "BOM", type: "select", options: bomOptions, span: 1, help: "Leave unset to use the item's active default BOM" },
    { name: "routing_id", label: "Routing", type: "select", options: routingOptions, span: 1, help: "Leave unset to use the active default routing (optional)" },
    { name: "planned_start_date", label: "Planned start", type: "date", span: 1 },
    { name: "planned_end_date", label: "Planned end", type: "date", span: 1 },
    { name: "notes", label: "Notes", type: "textarea", span: 2 },
  ];

  const submit = async () => {
    setError(null);
    try {
      const payload: ProductionOrderCreate = {
        item_id: itemId,
        quantity: String(values.quantity ?? ""),
        warehouse_id: String(values.warehouse_id ?? ""),
        bom_id: values.bom_id ? String(values.bom_id) : null,
        routing_id: values.routing_id ? String(values.routing_id) : null,
        planned_start_date: values.planned_start_date ? String(values.planned_start_date) : null,
        planned_end_date: values.planned_end_date ? String(values.planned_end_date) : null,
        notes: values.notes ? String(values.notes) : null,
      };
      const created = await createOrder.mutateAsync(payload);
      void navigate({ to: "/manufacturing/production-orders/$orderId", params: { orderId: created.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the production order."));
    }
  };

  const onChange = (name: string, value: string | boolean) => {
    setValues((prev) => {
      // Changing the item invalidates any picked BOM/routing version.
      if (name === "item_id" && value !== prev.item_id) {
        return { ...prev, item_id: value, bom_id: "", routing_id: "" };
      }
      return { ...prev, [name]: value };
    });
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold text-ink">New production order</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fields}
          values={values}
          onChange={onChange}
          onSubmit={() => void submit()}
          submitLabel="Create production order"
          busy={createOrder.isPending}
        />
      </div>
    </div>
  );
}
