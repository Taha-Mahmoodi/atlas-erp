/**
 * Create or edit a preventive maintenance plan (STRUCTURE §4). Edit via
 * `/maintenance/plans/$planId`; create via `/maintenance/plans/new`. `code` and the target
 * equipment are immutable after creation; a changed interval applies from the NEXT advance —
 * it never retro-shifts next_due_date. Activate/deactivate live here (a paused plan is
 * skipped by the generation run).
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDate } from "@/lib/format";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import {
  useActivateMaintenancePlan,
  useCreateMaintenancePlan,
  useDeactivateMaintenancePlan,
  useEquipmentOptions,
  useMaintenancePlan,
  useUpdateMaintenancePlan,
} from "@/modules/maintenance/hooks";
import type {
  IntervalUnit,
  MaintenancePlanCreate,
  MaintenancePlanUpdate,
} from "@/modules/maintenance/types";

/** MoneyType decimal strings arrive as "45.000000" — trim trailing zeros for the
 * number-input prefill (string ops only, no float math on money). */
function trimCostInput(cost: string | null): string {
  return (cost ?? "").replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

export function MaintenancePlanFormPage() {
  const { planId } = useParams({ strict: false });
  const isEdit = planId !== undefined;
  const navigate = useNavigate();

  const plan = useMaintenancePlan(planId);
  const equipment = useEquipmentOptions();
  const createPlan = useCreateMaintenancePlan();
  const updatePlan = useUpdateMaintenancePlan(planId ?? "");
  const activatePlan = useActivateMaintenancePlan(planId ?? "");
  const deactivatePlan = useDeactivateMaintenancePlan(planId ?? "");

  const [values, setValues] = useState<FormValues>({ interval_unit: "MONTHS" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (plan.data) {
      setValues({
        code: plan.data.code,
        name: plan.data.name,
        equipment_id: plan.data.equipment_id,
        interval_value: String(plan.data.interval_value),
        interval_unit: plan.data.interval_unit,
        task_description: plan.data.task_description,
        estimated_cost: trimCostInput(plan.data.estimated_cost),
      });
    }
  }, [plan.data]);

  const fields: FieldDef[] = [
    { name: "code", label: "Plan code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    {
      name: "equipment_id",
      label: "Equipment",
      type: "select",
      required: true,
      disabled: isEdit,
      options: (equipment.data?.items ?? []).map((unit) => ({
        value: unit.id,
        label: `${unit.code} — ${unit.name}`,
      })),
      span: 2,
    },
    { name: "interval_value", label: "Interval", type: "number", required: true, span: 1 },
    {
      name: "interval_unit",
      label: "Interval unit",
      type: "select",
      // A plan always has an interval unit — required stops the "—" empty option
      // from reaching the API as "" (422).
      required: true,
      options: [
        { value: "DAYS", label: "Days" },
        { value: "WEEKS", label: "Weeks" },
        { value: "MONTHS", label: "Months" },
      ],
      ...(isEdit
        ? { help: "A changed interval applies from the next advance — it never shifts the current due date." }
        : {}),
      span: 1,
    },
    { name: "task_description", label: "Task description", type: "textarea", required: true, span: 2 },
    ...(isEdit
      ? []
      : [
          {
            name: "start_date",
            label: "Start date",
            type: "date",
            help: "The first due date is one interval after this date. Leave blank to count from today.",
            span: 1,
          } as FieldDef,
        ]),
    { name: "estimated_cost", label: "Estimated cost", type: "number", step: "0.01", span: 1 },
  ];

  const submit = async () => {
    setError(null);
    try {
      if (isEdit) {
        const payload: MaintenancePlanUpdate = {
          name: String(values.name ?? ""),
          interval_value: Number(values.interval_value ?? 1),
          interval_unit: values.interval_unit as IntervalUnit,
          task_description: String(values.task_description ?? ""),
          estimated_cost: values.estimated_cost ? String(values.estimated_cost) : null,
        };
        await updatePlan.mutateAsync(payload);
      } else {
        const payload: MaintenancePlanCreate = {
          code: String(values.code ?? ""),
          name: String(values.name ?? ""),
          equipment_id: String(values.equipment_id ?? ""),
          interval_value: Number(values.interval_value ?? 1),
          interval_unit: values.interval_unit as IntervalUnit,
          task_description: String(values.task_description ?? ""),
          start_date: values.start_date ? String(values.start_date) : null,
          estimated_cost: values.estimated_cost ? String(values.estimated_cost) : null,
        };
        const created = await createPlan.mutateAsync(payload);
        void navigate({ to: "/maintenance/plans/$planId", params: { planId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the plan."));
    }
  };

  const toggleStatus = async () => {
    setError(null);
    try {
      if (plan.data?.status === "ACTIVE") {
        await deactivatePlan.mutateAsync();
      } else {
        await activatePlan.mutateAsync();
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to change the plan's status."));
    }
  };

  const busy = createPlan.isPending || updatePlan.isPending;
  const toggling = activatePlan.isPending || deactivatePlan.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/maintenance/plans">Preventive plans</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit plan" : "New preventive plan"}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">
            {isEdit ? "Edit plan" : "New preventive plan"}
          </h1>
          <div className="flex items-center gap-2.5">
            {isEdit && plan.data && (
              <button
                type="button"
                onClick={() => void toggleStatus()}
                disabled={toggling}
                className="btn-chip"
              >
                {toggling ? "Saving…" : plan.data.status === "ACTIVE" ? "Deactivate" : "Activate"}
              </button>
            )}
          </div>
        </div>
        {isEdit && plan.data && (
          <p className="mt-1 text-[13px] text-ink-muted">
            {plan.data.status === "ACTIVE" ? "Active" : "Inactive (skipped by the run)"} · next due{" "}
            {formatDate(plan.data.next_due_date)}
            {plan.data.last_generated_date && ` · last generated ${formatDate(plan.data.last_generated_date)}`}
          </p>
        )}
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
          submitLabel={isEdit ? "Save changes" : "Create plan"}
          busy={busy}
        />
      </div>
    </div>
  );
}
