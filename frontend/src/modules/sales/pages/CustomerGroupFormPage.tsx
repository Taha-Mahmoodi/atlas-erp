/**
 * Create or edit a customer group (STRUCTURE §4). Edit mode via
 * `/sales/customer-groups/$customerGroupId`; create via `/sales/customer-groups/new`. `code`
 * is immutable after creation. Mirrors inventory's UomFormPage.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateCustomerGroup, useCustomerGroup, useUpdateCustomerGroup } from "@/modules/sales/hooks";
import type { CustomerGroupCreate, CustomerGroupUpdate } from "@/modules/sales/types";

function fieldsFor(isEdit: boolean): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
  ];
}

export function CustomerGroupFormPage() {
  const { customerGroupId } = useParams({ strict: false });
  const isEdit = customerGroupId !== undefined;
  const navigate = useNavigate();

  const group = useCustomerGroup(customerGroupId);
  const createGroup = useCreateCustomerGroup();
  const updateGroup = useUpdateCustomerGroup(customerGroupId ?? "");

  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (group.data) {
      setValues({ code: group.data.code, name: group.data.name });
    }
  }, [group.data]);

  const submit = async () => {
    setError(null);
    try {
      if (isEdit) {
        const payload: CustomerGroupUpdate = { name: String(values.name ?? "") };
        await updateGroup.mutateAsync(payload);
        void navigate({ to: "/sales/customer-groups/$customerGroupId", params: { customerGroupId: customerGroupId! } });
      } else {
        const payload: CustomerGroupCreate = { code: String(values.code ?? ""), name: String(values.name ?? "") };
        const created = await createGroup.mutateAsync(payload);
        void navigate({ to: "/sales/customer-groups/$customerGroupId", params: { customerGroupId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the customer group."));
    }
  };

  const busy = createGroup.isPending || updateGroup.isPending;

  return (
    <div className="mx-auto max-w-md">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{isEdit ? "Edit customer group" : "New customer group"}</h1>
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
          submitLabel={isEdit ? "Save changes" : "Create group"}
          busy={busy}
          columns={1}
        />
      </div>
    </div>
  );
}
