/**
 * Open a DRAFT timesheet (STRUCTURE §4; PLAN 10.3): employee + period + notes. One timesheet
 * per (employee, period_start); a gapless TS- number is claimed at creation. Time entries are
 * added on the workbench once the header exists.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateTimesheet, useEmployeeOptions } from "@/modules/hr/hooks";
import type { TimesheetCreate } from "@/modules/hr/types";

export function TimesheetFormPage() {
  const navigate = useNavigate();
  const employees = useEmployeeOptions();
  const createTimesheet = useCreateTimesheet();

  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  const fields: FieldDef[] = [
    {
      name: "employee_id",
      label: "Employee",
      type: "select",
      required: true,
      options: (employees.data?.items ?? []).map((e) => ({
        value: e.id,
        label: `${e.employee_code} — ${e.first_name} ${e.last_name}`,
      })),
      span: 1,
    },
    { name: "period_start", label: "Period start", type: "date", required: true, span: 1 },
    { name: "period_end", label: "Period end", type: "date", required: true, span: 1 },
    { name: "notes", label: "Notes", type: "textarea", span: 2 },
  ];

  const submit = async () => {
    setError(null);
    try {
      const payload: TimesheetCreate = {
        employee_id: String(values.employee_id ?? ""),
        period_start: String(values.period_start ?? ""),
        period_end: String(values.period_end ?? ""),
        notes: values.notes ? String(values.notes) : null,
      };
      const created = await createTimesheet.mutateAsync(payload);
      void navigate({ to: "/hr/timesheets/$timesheetId", params: { timesheetId: created.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the timesheet."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hr/timesheets">Timesheets</Link> / <span className="text-ink">New timesheet</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">New timesheet</h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fields}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel="Create timesheet"
          busy={createTimesheet.isPending}
        />
      </div>
    </div>
  );
}
