/**
 * Create or edit an opportunity (STRUCTURE §4). Edit via `/crm/opportunities/$opportunityId/edit`
 * (open stages only — enforced server-side); create via `/crm/opportunities/new`. PATCH replaces
 * the line set wholesale, so this page always submits the full current line array (the sales
 * QuoteFormPage precedent). Customer is optional — a prospect deal creates its customer on
 * convert.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { OpportunityLinesEditor } from "@/modules/crm/components/OpportunityLinesEditor";
import { useCreateOpportunity, useOpportunity, useUpdateOpportunity } from "@/modules/crm/hooks";
import type { OpportunityLineCreate } from "@/modules/crm/types";
import { useItemOptions } from "@/modules/inventory/hooks";
import { useCustomerOptions } from "@/modules/sales/hooks";

/** API decimal strings ("40.000000") → clean number-input seeds ("40"). Pure string trim — no float precision risk. */
function trimDecimal(value: string | null | undefined): string {
  return value ? value.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "") : "";
}

function fieldsFor(customerOptions: { value: string; label: string }[]): FieldDef[] {
  return [
    { name: "name", label: "Deal name", type: "text", required: true, span: 1 },
    { name: "company_name", label: "Company", type: "text", required: true, span: 1 },
    { name: "contact_name", label: "Contact", type: "text", span: 1 },
    { name: "email", label: "Email", type: "text", span: 1 },
    {
      name: "customer_id",
      label: "Existing customer",
      type: "select",
      options: customerOptions,
      span: 1,
      help: "Leave empty for a prospect — convert creates the customer.",
    },
    { name: "currency_code", label: "Currency", type: "text", required: true, span: 1 },
    { name: "estimated_value", label: "Estimated value", type: "number", step: "0.01", span: 1 },
    { name: "probability_percent", label: "Probability %", type: "number", step: "1", span: 1 },
    { name: "expected_close_date", label: "Expected close", type: "date", span: 1 },
    { name: "notes", label: "Notes", type: "textarea", span: 2 },
  ];
}

export function OpportunityFormPage() {
  const { opportunityId } = useParams({ strict: false });
  const isEdit = opportunityId !== undefined;
  const navigate = useNavigate();

  const opportunity = useOpportunity(opportunityId);
  const customers = useCustomerOptions();
  const items = useItemOptions();
  const createOpportunity = useCreateOpportunity();
  const updateOpportunity = useUpdateOpportunity(opportunityId ?? "");

  const [values, setValues] = useState<FormValues>({ currency_code: "USD" });
  const [lines, setLines] = useState<OpportunityLineCreate[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (opportunity.data) {
      setValues({
        name: opportunity.data.name,
        company_name: opportunity.data.company_name,
        contact_name: opportunity.data.contact_name ?? "",
        email: opportunity.data.email ?? "",
        customer_id: opportunity.data.customer_id ?? "",
        currency_code: opportunity.data.currency_code,
        estimated_value: trimDecimal(opportunity.data.estimated_value),
        probability_percent: trimDecimal(opportunity.data.probability_percent),
        expected_close_date: opportunity.data.expected_close_date ?? "",
        notes: opportunity.data.notes ?? "",
      });
      setLines(
        opportunity.data.lines.map((line) => ({
          item_id: line.item_id,
          description: line.description,
          quantity: trimDecimal(line.quantity),
          estimated_unit_price: trimDecimal(line.estimated_unit_price),
        })),
      );
    }
  }, [opportunity.data]);

  const customerOptions = (customers.data?.items ?? []).map((customer) => ({
    value: customer.id,
    label: `${customer.customer_code} — ${customer.name}`,
  }));
  const validLines = lines.filter(
    (line) => line.item_id && (Number(line.quantity) || 0) > 0 && line.estimated_unit_price !== "",
  );

  const submit = async () => {
    setError(null);
    try {
      const payload = {
        name: String(values.name ?? ""),
        company_name: String(values.company_name ?? ""),
        contact_name: values.contact_name ? String(values.contact_name) : null,
        email: values.email ? String(values.email) : null,
        customer_id: values.customer_id ? String(values.customer_id) : null,
        currency_code: String(values.currency_code ?? "").toUpperCase(),
        estimated_value: values.estimated_value ? String(values.estimated_value) : "0",
        probability_percent: values.probability_percent ? String(values.probability_percent) : null,
        expected_close_date: values.expected_close_date ? String(values.expected_close_date) : null,
        notes: values.notes ? String(values.notes) : null,
        lines: validLines,
      };
      if (isEdit) {
        await updateOpportunity.mutateAsync(payload);
        void navigate({ to: "/crm/opportunities/$opportunityId", params: { opportunityId } });
      } else {
        const created = await createOpportunity.mutateAsync(payload);
        void navigate({
          to: "/crm/opportunities/$opportunityId",
          params: { opportunityId: created.id },
        });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the opportunity."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">
        {isEdit ? "Edit opportunity" : "New opportunity"}
      </h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(customerOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create opportunity"}
          busy={createOpportunity.isPending || updateOpportunity.isPending}
          footer={
            <span className="text-xs text-ink-muted">Lines below are saved with the deal.</span>
          }
        />
      </div>
      <div className="mt-6">
        <OpportunityLinesEditor lines={lines} items={items.data?.items ?? []} onChange={setLines} />
      </div>
    </div>
  );
}
