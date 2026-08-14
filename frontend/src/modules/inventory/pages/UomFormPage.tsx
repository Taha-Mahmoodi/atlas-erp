/**
 * Create or edit a unit of measure (STRUCTURE §4). Edit mode via `/inventory/uoms/$uomId`;
 * create via `/inventory/uoms/new`. `code` is immutable after creation.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateUom, useUom, useUpdateUom } from "@/modules/inventory/hooks";
import type { UomCreate, UomUpdate } from "@/modules/inventory/types";

function fieldsFor(isEdit: boolean): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
  ];
}

export function UomFormPage() {
  const { uomId } = useParams({ strict: false });
  const isEdit = uomId !== undefined;
  const navigate = useNavigate();

  const uom = useUom(uomId);
  const createUom = useCreateUom();
  const updateUom = useUpdateUom(uomId ?? "");

  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (uom.data) {
      setValues({ code: uom.data.code, name: uom.data.name });
    }
  }, [uom.data]);

  const submit = async () => {
    setError(null);
    try {
      if (isEdit) {
        const payload: UomUpdate = { name: String(values.name ?? "") };
        await updateUom.mutateAsync(payload);
        void navigate({ to: "/inventory/uoms/$uomId", params: { uomId: uomId! } });
      } else {
        const payload: UomCreate = { code: String(values.code ?? ""), name: String(values.name ?? "") };
        const created = await createUom.mutateAsync(payload);
        void navigate({ to: "/inventory/uoms/$uomId", params: { uomId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the unit of measure."));
    }
  };

  const busy = createUom.isPending || updateUom.isPending;

  return (
    <div className="mx-auto max-w-md">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{isEdit ? "Edit unit of measure" : "New unit of measure"}</h1>
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
          submitLabel={isEdit ? "Save changes" : "Create UoM"}
          busy={busy}
          columns={1}
        />
      </div>
    </div>
  );
}
