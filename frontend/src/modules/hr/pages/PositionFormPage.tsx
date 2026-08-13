/**
 * Create or edit a position (STRUCTURE §4). Edit via `/hr/positions/$positionId`; create via
 * `/hr/positions/new`. `code` is immutable after creation.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import {
  useCreatePosition,
  useDepartmentOptions,
  usePosition,
  useUpdatePosition,
} from "@/modules/hr/hooks";
import type { PositionCreate, PositionUpdate } from "@/modules/hr/types";

function fieldsFor(isEdit: boolean, departmentOptions: { value: string; label: string }[]): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "title", label: "Title", type: "text", required: true, span: 1 },
    { name: "department_id", label: "Department", type: "select", options: departmentOptions, span: 1 },
    { name: "is_active", label: "Active", type: "checkbox", span: 1 },
    { name: "description", label: "Description", type: "textarea", span: 2 },
  ];
}

export function PositionFormPage() {
  const { positionId } = useParams({ strict: false });
  const isEdit = positionId !== undefined;
  const navigate = useNavigate();

  const position = usePosition(positionId);
  const departments = useDepartmentOptions();
  const createPosition = useCreatePosition();
  const updatePosition = useUpdatePosition(positionId ?? "");

  const [values, setValues] = useState<FormValues>({ is_active: true });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (position.data) {
      setValues({
        code: position.data.code,
        title: position.data.title,
        department_id: position.data.department_id ?? "",
        is_active: position.data.is_active,
        description: position.data.description ?? "",
      });
    }
  }, [position.data]);

  const departmentOptions = (departments.data?.items ?? []).map((d) => ({
    value: d.id,
    label: `${d.code} — ${d.name}`,
  }));

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        title: String(values.title ?? ""),
        description: values.description ? String(values.description) : null,
        department_id: values.department_id ? String(values.department_id) : null,
        is_active: values.is_active === true,
      };
      if (isEdit) {
        const payload: PositionUpdate = shared;
        await updatePosition.mutateAsync(payload);
      } else {
        const payload: PositionCreate = { ...shared, code: String(values.code ?? "") };
        const created = await createPosition.mutateAsync(payload);
        void navigate({ to: "/hr/positions/$positionId", params: { positionId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the position."));
    }
  };

  const busy = createPosition.isPending || updatePosition.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold text-ink">{isEdit ? "Edit position" : "New position"}</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, departmentOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create position"}
          busy={busy}
        />
      </div>
    </div>
  );
}
