/**
 * Create or edit a leave type (STRUCTURE §4). Edit via `/hr/leave-types/$leaveTypeId`; create
 * via `/hr/leave-types/new`. `code` is immutable after creation. `accrual_amount` is the
 * per-period grant in days (0.5 = a half day); `max_balance` caps the accrued balance.
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateLeaveType, useLeaveType, useUpdateLeaveType } from "@/modules/hr/hooks";
import type { AccrualFrequency, LeaveTypeCreate, LeaveTypeUpdate } from "@/modules/hr/types";

function fieldsFor(isEdit: boolean): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    {
      name: "accrual_frequency",
      label: "Accrual frequency",
      type: "select",
      options: [
        { value: "MONTHLY", label: "Monthly" },
        { value: "ANNUAL", label: "Annual" },
      ],
      span: 1,
    },
    {
      name: "accrual_amount",
      label: "Accrual amount (days)",
      type: "number",
      step: "0.5",
      required: true,
      help: "Days granted per accrual period.",
      span: 1,
    },
    {
      name: "max_balance",
      label: "Max balance (days)",
      type: "number",
      step: "0.5",
      help: "Leave unset for an uncapped balance.",
      span: 1,
    },
    { name: "is_paid", label: "Paid leave", type: "checkbox", span: 1 },
    { name: "is_active", label: "Active", type: "checkbox", span: 1 },
  ];
}

export function LeaveTypeFormPage() {
  const { leaveTypeId } = useParams({ strict: false });
  const isEdit = leaveTypeId !== undefined;
  const navigate = useNavigate();

  const leaveType = useLeaveType(leaveTypeId);
  const createLeaveType = useCreateLeaveType();
  const updateLeaveType = useUpdateLeaveType(leaveTypeId ?? "");

  const [values, setValues] = useState<FormValues>({ accrual_frequency: "MONTHLY", is_paid: true, is_active: true });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (leaveType.data) {
      setValues({
        code: leaveType.data.code,
        name: leaveType.data.name,
        accrual_frequency: leaveType.data.accrual_frequency,
        accrual_amount: leaveType.data.accrual_amount,
        max_balance: leaveType.data.max_balance ?? "",
        is_paid: leaveType.data.is_paid,
        is_active: leaveType.data.is_active,
      });
    }
  }, [leaveType.data]);

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        accrual_frequency: values.accrual_frequency as AccrualFrequency,
        accrual_amount: String(values.accrual_amount ?? "0"),
        max_balance: values.max_balance ? String(values.max_balance) : null,
        is_paid: values.is_paid === true,
        is_active: values.is_active === true,
      };
      if (isEdit) {
        const payload: LeaveTypeUpdate = shared;
        await updateLeaveType.mutateAsync(payload);
      } else {
        const payload: LeaveTypeCreate = { ...shared, code: String(values.code ?? "") };
        const created = await createLeaveType.mutateAsync(payload);
        void navigate({ to: "/hr/leave-types/$leaveTypeId", params: { leaveTypeId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the leave type."));
    }
  };

  const busy = createLeaveType.isPending || updateLeaveType.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hr/leave-types">Leave types</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit leave type" : "New leave type"}</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {isEdit ? "Edit leave type" : "New leave type"}
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
          submitLabel={isEdit ? "Save changes" : "Create leave type"}
          busy={busy}
        />
      </div>
    </div>
  );
}
