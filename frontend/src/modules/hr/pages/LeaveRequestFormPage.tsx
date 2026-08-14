/**
 * File or edit a DRAFT leave request (STRUCTURE §4; PLAN 10.2). Create via
 * `/hr/leave-requests/new`; edit via `/hr/leave-requests/$requestId/edit` (only a DRAFT is
 * editable; employee and leave type are immutable after creation). `days` is caller-supplied
 * (0.5 = a half day) — business-day computation from the dates is documented later (D-053).
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import {
  useCreateLeaveRequest,
  useEmployeeOptions,
  useLeaveRequest,
  useLeaveTypeOptions,
  useUpdateLeaveRequest,
} from "@/modules/hr/hooks";
import type { LeaveRequestCreate, LeaveRequestUpdate } from "@/modules/hr/types";

type Option = { value: string; label: string };

function fieldsFor(isEdit: boolean, employeeOptions: Option[], leaveTypeOptions: Option[]): FieldDef[] {
  return [
    {
      name: "employee_id",
      label: "Employee",
      type: "select",
      options: employeeOptions,
      required: !isEdit,
      disabled: isEdit,
      span: 1,
    },
    {
      name: "leave_type_id",
      label: "Leave type",
      type: "select",
      options: leaveTypeOptions,
      required: !isEdit,
      disabled: isEdit,
      span: 1,
    },
    { name: "start_date", label: "Start date", type: "date", required: true, span: 1 },
    { name: "end_date", label: "End date", type: "date", required: true, span: 1 },
    {
      name: "days",
      label: "Days",
      type: "number",
      step: "0.5",
      required: true,
      help: "0.5 is a half day.",
      span: 1,
    },
    { name: "reason", label: "Reason", type: "text", span: 1 },
    { name: "notes", label: "Notes", type: "textarea", span: 2 },
  ];
}

export function LeaveRequestFormPage() {
  const { requestId } = useParams({ strict: false });
  const isEdit = requestId !== undefined;
  const navigate = useNavigate();

  const request = useLeaveRequest(requestId);
  const employees = useEmployeeOptions();
  const leaveTypes = useLeaveTypeOptions();
  const createRequest = useCreateLeaveRequest();
  const updateRequest = useUpdateLeaveRequest(requestId ?? "");

  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (request.data) {
      setValues({
        employee_id: request.data.employee_id,
        leave_type_id: request.data.leave_type_id,
        start_date: request.data.start_date,
        end_date: request.data.end_date,
        days: request.data.days,
        reason: request.data.reason ?? "",
        notes: request.data.notes ?? "",
      });
    }
  }, [request.data]);

  const employeeOptions = (employees.data?.items ?? []).map((e) => ({
    value: e.id,
    label: `${e.employee_code} — ${e.first_name} ${e.last_name}`,
  }));
  const leaveTypeOptions = (leaveTypes.data?.items ?? [])
    .filter((t) => t.is_active || t.id === request.data?.leave_type_id)
    .map((t) => ({ value: t.id, label: `${t.code} — ${t.name}` }));

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        start_date: String(values.start_date ?? ""),
        end_date: String(values.end_date ?? ""),
        days: String(values.days ?? "0"),
        reason: values.reason ? String(values.reason) : null,
        notes: values.notes ? String(values.notes) : null,
      };
      if (isEdit) {
        const payload: LeaveRequestUpdate = shared;
        await updateRequest.mutateAsync(payload);
        void navigate({ to: "/hr/leave-requests/$requestId", params: { requestId: requestId as string } });
      } else {
        const payload: LeaveRequestCreate = {
          ...shared,
          employee_id: String(values.employee_id ?? ""),
          leave_type_id: String(values.leave_type_id ?? ""),
        };
        const created = await createRequest.mutateAsync(payload);
        void navigate({ to: "/hr/leave-requests/$requestId", params: { requestId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the leave request."));
    }
  };

  const busy = createRequest.isPending || updateRequest.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hr/leave-requests">Leave requests</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit leave request" : "New leave request"}</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {isEdit ? "Edit leave request" : "New leave request"}
        </h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, employeeOptions, leaveTypeOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create request"}
          busy={busy}
        />
      </div>
    </div>
  );
}
