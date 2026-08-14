/**
 * Create or edit a piece of equipment (STRUCTURE §4). Edit via
 * `/maintenance/equipment/$equipmentId`; create via `/maintenance/equipment/new`. `code` is
 * immutable after creation (the vendor-code precedent). `cost_center_id` is accepted by the
 * backend but has no picker UI yet — no cost-center lookup exists frontend-side.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateEquipment, useEquipment, useUpdateEquipment } from "@/modules/maintenance/hooks";
import type { EquipmentCreate, EquipmentStatus, EquipmentUpdate } from "@/modules/maintenance/types";

function fieldsFor(isEdit: boolean): FieldDef[] {
  return [
    { name: "code", label: "Equipment code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    {
      name: "status",
      label: "Status",
      type: "select",
      // Equipment always has a status — required stops the "—" empty option from
      // reaching the API as "" (422).
      required: true,
      options: [
        { value: "ACTIVE", label: "Active" },
        { value: "INACTIVE", label: "Inactive" },
        { value: "RETIRED", label: "Retired" },
      ],
      help: "Only ACTIVE equipment can receive new maintenance orders.",
      span: 1,
    },
    { name: "location", label: "Location", type: "text", span: 1 },
    { name: "manufacturer", label: "Manufacturer", type: "text", span: 1 },
    { name: "model", label: "Model", type: "text", span: 1 },
    { name: "serial_number", label: "Serial number", type: "text", span: 1 },
    { name: "commissioned_date", label: "Commissioned", type: "date", span: 1 },
    { name: "description", label: "Description", type: "textarea", span: 2 },
    { name: "notes", label: "Notes", type: "textarea", span: 2 },
  ];
}

export function EquipmentFormPage() {
  const { equipmentId } = useParams({ strict: false });
  const isEdit = equipmentId !== undefined;
  const navigate = useNavigate();

  const equipment = useEquipment(equipmentId);
  const createEquipment = useCreateEquipment();
  const updateEquipment = useUpdateEquipment(equipmentId ?? "");

  const [values, setValues] = useState<FormValues>({ status: "ACTIVE" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (equipment.data) {
      setValues({
        code: equipment.data.code,
        name: equipment.data.name,
        status: equipment.data.status,
        location: equipment.data.location ?? "",
        manufacturer: equipment.data.manufacturer ?? "",
        model: equipment.data.model ?? "",
        serial_number: equipment.data.serial_number ?? "",
        commissioned_date: equipment.data.commissioned_date ?? "",
        description: equipment.data.description ?? "",
        notes: equipment.data.notes ?? "",
      });
    }
  }, [equipment.data]);

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        status: values.status as EquipmentStatus,
        location: values.location ? String(values.location) : null,
        manufacturer: values.manufacturer ? String(values.manufacturer) : null,
        model: values.model ? String(values.model) : null,
        serial_number: values.serial_number ? String(values.serial_number) : null,
        commissioned_date: values.commissioned_date ? String(values.commissioned_date) : null,
        description: values.description ? String(values.description) : null,
        notes: values.notes ? String(values.notes) : null,
      };
      if (isEdit) {
        const payload: EquipmentUpdate = shared;
        await updateEquipment.mutateAsync(payload);
      } else {
        const payload: EquipmentCreate = { ...shared, code: String(values.code ?? "") };
        const created = await createEquipment.mutateAsync(payload);
        void navigate({ to: "/maintenance/equipment/$equipmentId", params: { equipmentId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the equipment."));
    }
  };

  const busy = createEquipment.isPending || updateEquipment.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{isEdit ? "Edit equipment" : "New equipment"}</h1>
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
          submitLabel={isEdit ? "Save changes" : "Create equipment"}
          busy={busy}
        />
      </div>
    </div>
  );
}
