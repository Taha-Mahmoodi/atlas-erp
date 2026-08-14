/**
 * Create or edit a work center (STRUCTURE §4). Edit mode via
 * `/manufacturing/work-centers/$workCenterId`; create via `/manufacturing/work-centers/new`.
 * `code` is immutable after creation. No delete/deactivate action — active/inactive is just a
 * checkbox on this same form.
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateWorkCenter, useUpdateWorkCenter, useWorkCenter } from "@/modules/manufacturing/hooks";
import type { WorkCenterCreate, WorkCenterUpdate } from "@/modules/manufacturing/types";

function fieldsFor(isEdit: boolean): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    { name: "capacity_hours_per_day", label: "Capacity (hours/day)", type: "number", step: "0.01", span: 1 },
    { name: "efficiency_percent", label: "Efficiency (%)", type: "number", step: "0.01", span: 1 },
    { name: "description", label: "Description", type: "textarea", span: 2 },
    { name: "is_active", label: "Active", type: "checkbox", span: 1 },
  ];
}

export function WorkCenterFormPage() {
  const { workCenterId } = useParams({ strict: false });
  const isEdit = workCenterId !== undefined;
  const navigate = useNavigate();

  const workCenter = useWorkCenter(workCenterId);
  const createWorkCenter = useCreateWorkCenter();
  const updateWorkCenter = useUpdateWorkCenter(workCenterId ?? "");

  const [values, setValues] = useState<FormValues>({
    capacity_hours_per_day: "0",
    efficiency_percent: "100",
    is_active: true,
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (workCenter.data) {
      setValues({
        code: workCenter.data.code,
        name: workCenter.data.name,
        capacity_hours_per_day: workCenter.data.capacity_hours_per_day,
        efficiency_percent: workCenter.data.efficiency_percent,
        description: workCenter.data.description ?? "",
        is_active: workCenter.data.is_active,
      });
    }
  }, [workCenter.data]);

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        capacity_hours_per_day: String(values.capacity_hours_per_day ?? "0"),
        efficiency_percent: String(values.efficiency_percent ?? "100"),
        description: values.description ? String(values.description) : null,
        is_active: Boolean(values.is_active),
      };
      if (isEdit) {
        const payload: WorkCenterUpdate = shared;
        await updateWorkCenter.mutateAsync(payload);
      } else {
        const payload: WorkCenterCreate = { ...shared, code: String(values.code ?? "") };
        const created = await createWorkCenter.mutateAsync(payload);
        void navigate({ to: "/manufacturing/work-centers/$workCenterId", params: { workCenterId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the work center."));
    }
  };

  const busy = createWorkCenter.isPending || updateWorkCenter.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/manufacturing/work-centers">Work Centers</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit work center" : "New work center"}</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {isEdit ? "Edit work center" : "New work center"}
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
          submitLabel={isEdit ? "Save changes" : "Create work center"}
          busy={busy}
        />
      </div>
    </div>
  );
}
