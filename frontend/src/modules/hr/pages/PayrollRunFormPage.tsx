/**
 * Compute a DRAFT payroll run (STRUCTURE §4; PLAN 10.4, D-055): period + pay date + the flat
 * withholding rate (omit for the per-tenant default). The run covers every active employee
 * with a base salary (gross = base_salary, tax = gross × rate, net = gross − tax) — no
 * per-employee selection here (ponytail: the backend's `employee_ids` subset filter is
 * unexposed; add a picker when a real partial-run need appears).
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreatePayrollRun } from "@/modules/hr/hooks";
import { PayrollDisclaimer } from "@/modules/hr/pages/PayrollRunListPage";
import type { PayrollRunCreate } from "@/modules/hr/types";

const FIELDS: FieldDef[] = [
  { name: "period_start", label: "Period start", type: "date", required: true, span: 1 },
  { name: "period_end", label: "Period end", type: "date", required: true, span: 1 },
  { name: "pay_date", label: "Pay date", type: "date", required: true, help: "The journal posting date.", span: 1 },
  {
    name: "tax_rate_percent",
    label: "Withholding rate (%)",
    type: "number",
    step: "0.01",
    help: "The single flat rate (D-055). Leave unset for the tenant default.",
    span: 1,
  },
  {
    name: "currency_code",
    label: "Currency",
    type: "text",
    help: "Leave unset for the tenant's functional currency.",
    span: 1,
  },
  { name: "notes", label: "Notes", type: "textarea", span: 2 },
];

export function PayrollRunFormPage() {
  const navigate = useNavigate();
  const createRun = useCreatePayrollRun();

  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    try {
      const payload: PayrollRunCreate = {
        period_start: String(values.period_start ?? ""),
        period_end: String(values.period_end ?? ""),
        pay_date: String(values.pay_date ?? ""),
        tax_rate_percent: values.tax_rate_percent ? String(values.tax_rate_percent) : null,
        currency_code: values.currency_code ? String(values.currency_code).toUpperCase() : null,
        notes: values.notes ? String(values.notes) : null,
      };
      const created = await createRun.mutateAsync(payload);
      void navigate({ to: "/hr/payroll-runs/$runId", params: { runId: created.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the payroll run."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">New payroll run</h1>
      <PayrollDisclaimer />
      <p className="mt-2 text-sm text-ink-muted">
        Computes one gross → tax → net line per active employee with a base salary, in draft.
      </p>
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
          submitLabel="Compute run"
          busy={createRun.isPending}
        />
      </div>
    </div>
  );
}
