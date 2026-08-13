/**
 * Create or edit a lead (STRUCTURE §4). Edit via `/crm/leads/$leadId/edit`; create via
 * `/crm/leads/new`. Status is server-owned (qualify/disqualify on the workbench), so it never
 * appears here.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateLead, useLead, useUpdateLead } from "@/modules/crm/hooks";
import type { LeadUpdate } from "@/modules/crm/types";

// ponytail: owner_employee_id is omitted — hr has no frontend employee-picker surface yet;
// add it when the HR UI slice ships one (the field stays null-able server-side).
const FIELDS: FieldDef[] = [
  { name: "company_name", label: "Company", type: "text", required: true, span: 2 },
  { name: "contact_name", label: "Contact", type: "text", span: 1 },
  { name: "email", label: "Email", type: "text", span: 1 },
  { name: "phone", label: "Phone", type: "text", span: 1 },
  { name: "source", label: "Source", type: "text", span: 1, placeholder: "Referral, website, trade fair…" },
  { name: "estimated_value", label: "Estimated value", type: "number", step: "0.01", span: 1 },
  { name: "currency_code", label: "Currency", type: "text", span: 1, help: "Required when a value is set." },
  { name: "notes", label: "Notes", type: "textarea", span: 2 },
];

export function LeadFormPage() {
  const { leadId } = useParams({ strict: false });
  const isEdit = leadId !== undefined;
  const navigate = useNavigate();

  const lead = useLead(leadId);
  const createLead = useCreateLead();
  const updateLead = useUpdateLead(leadId ?? "");

  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (lead.data) {
      setValues({
        company_name: lead.data.company_name,
        contact_name: lead.data.contact_name ?? "",
        email: lead.data.email ?? "",
        phone: lead.data.phone ?? "",
        source: lead.data.source ?? "",
        estimated_value: lead.data.estimated_value ?? "",
        currency_code: lead.data.currency_code ?? "",
        notes: lead.data.notes ?? "",
      });
    }
  }, [lead.data]);

  const submit = async () => {
    setError(null);
    try {
      const payload: LeadUpdate = {
        company_name: String(values.company_name ?? ""),
        contact_name: values.contact_name ? String(values.contact_name) : null,
        email: values.email ? String(values.email) : null,
        phone: values.phone ? String(values.phone) : null,
        source: values.source ? String(values.source) : null,
        estimated_value: values.estimated_value ? String(values.estimated_value) : null,
        currency_code: values.currency_code ? String(values.currency_code).toUpperCase() : null,
        notes: values.notes ? String(values.notes) : null,
      };
      if (isEdit) {
        await updateLead.mutateAsync(payload);
        void navigate({ to: "/crm/leads/$leadId", params: { leadId } });
      } else {
        const created = await createLead.mutateAsync(payload);
        void navigate({ to: "/crm/leads/$leadId", params: { leadId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the lead."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold text-ink">{isEdit ? "Edit lead" : "New lead"}</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={FIELDS}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create lead"}
          busy={createLead.isPending || updateLead.isPending}
        />
      </div>
    </div>
  );
}
