/**
 * Create a CORRECTIVE maintenance order (STRUCTURE §4). Only ACTIVE equipment can be
 * targeted (422 otherwise). Giving a scheduled date makes the order born SCHEDULED;
 * leaving it blank creates a DRAFT to schedule later from the workbench. PREVENTIVE
 * orders are never created here — they come from a plan's generation run.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateMaintenanceOrder, useEquipmentOptions } from "@/modules/maintenance/hooks";
import type { MaintenanceOrderCreate } from "@/modules/maintenance/types";

export function MaintenanceOrderFormPage() {
  const navigate = useNavigate();
  const equipment = useEquipmentOptions();
  const createOrder = useCreateMaintenanceOrder();

  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  const fields: FieldDef[] = [
    {
      name: "equipment_id",
      label: "Equipment",
      type: "select",
      required: true,
      options: (equipment.data?.items ?? []).map((unit) => ({
        value: unit.id,
        label: `${unit.code} — ${unit.name}`,
      })),
      help: "Only ACTIVE equipment is listed — orders cannot target inactive or retired units.",
      span: 2,
    },
    { name: "description", label: "Description", type: "textarea", required: true, span: 2 },
    {
      name: "scheduled_date",
      label: "Scheduled date",
      type: "date",
      help: "Leave blank to create a draft and schedule it later.",
      span: 1,
    },
    { name: "estimated_cost", label: "Estimated cost", type: "number", step: "0.01", span: 1 },
    { name: "notes", label: "Notes", type: "textarea", span: 2 },
  ];

  const submit = async () => {
    setError(null);
    try {
      const payload: MaintenanceOrderCreate = {
        equipment_id: String(values.equipment_id ?? ""),
        description: String(values.description ?? ""),
        scheduled_date: values.scheduled_date ? String(values.scheduled_date) : null,
        estimated_cost: values.estimated_cost ? String(values.estimated_cost) : null,
        notes: values.notes ? String(values.notes) : null,
      };
      const created = await createOrder.mutateAsync(payload);
      void navigate({ to: "/maintenance/orders/$orderId", params: { orderId: created.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the maintenance order."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/maintenance/orders">Maintenance orders</Link> /{" "}
          <span className="text-ink">New corrective order</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">New corrective order</h1>
        </div>
      </header>
      {error && (
        <p role="alert" className="mb-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div>
        <FormBuilder
          fields={fields}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel="Create order"
          busy={createOrder.isPending}
        />
      </div>
    </div>
  );
}
