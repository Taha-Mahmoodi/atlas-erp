/**
 * Create or edit an employee (STRUCTURE §4), split along the D-009 write-side convention:
 * the main form writes only NON-compensation fields (the general PATCH can never touch pay),
 * while compensation/PII goes through the dedicated `/compensation` endpoint in its own card —
 * rendered only for `hr.employee.read_compensation` holders, with a masked notice for everyone
 * else (the fields arrive as null for them, so there is nothing to edit). Create accepts
 * initial compensation in one call (the backend gates create on BOTH keys).
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useMe } from "@/lib/session";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import {
  useCreateEmployee,
  useDepartmentOptions,
  useEmployee,
  useEmployeeOptions,
  usePositionOptions,
  useSetEmployeeCompensation,
  useUpdateEmployee,
} from "@/modules/hr/hooks";
import type {
  Employee,
  EmployeeCreate,
  EmployeeUpdate,
  EmploymentStatus,
  EmploymentType,
} from "@/modules/hr/types";

type Option = { value: string; label: string };

const STATUS_OPTIONS: Option[] = [
  { value: "ACTIVE", label: "Active" },
  { value: "ON_LEAVE", label: "On leave" },
  { value: "TERMINATED", label: "Terminated" },
];
const TYPE_OPTIONS: Option[] = [
  { value: "FULL_TIME", label: "Full time" },
  { value: "PART_TIME", label: "Part time" },
  { value: "CONTRACT", label: "Contract" },
];

const COMPENSATION_FIELDS: FieldDef[] = [
  { name: "base_salary", label: "Base salary", type: "number", step: "0.01", span: 1 },
  { name: "currency_code", label: "Currency", type: "text", span: 1 },
  { name: "national_id", label: "National ID", type: "text", span: 1 },
  { name: "tax_id", label: "Tax ID", type: "text", span: 1 },
  { name: "date_of_birth", label: "Date of birth", type: "date", span: 1 },
  { name: "bank_account", label: "Bank account", type: "text", span: 1 },
];

function coreFieldsFor(
  isEdit: boolean,
  departmentOptions: Option[],
  positionOptions: Option[],
  managerOptions: Option[],
): FieldDef[] {
  return [
    { name: "employee_code", label: "Employee code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "hire_date", label: "Hire date", type: "date", required: true, span: 1 },
    { name: "first_name", label: "First name", type: "text", required: true, span: 1 },
    { name: "last_name", label: "Last name", type: "text", required: true, span: 1 },
    { name: "email", label: "Email", type: "text", span: 1 },
    { name: "department_id", label: "Department", type: "select", options: departmentOptions, span: 1 },
    { name: "position_id", label: "Position", type: "select", options: positionOptions, span: 1 },
    { name: "manager_id", label: "Manager", type: "select", options: managerOptions, span: 1 },
    { name: "status", label: "Status", type: "select", options: STATUS_OPTIONS, span: 1 },
    { name: "employment_type", label: "Employment type", type: "select", options: TYPE_OPTIONS, span: 1 },
    { name: "termination_date", label: "Termination date", type: "date", span: 1 },
  ];
}

function compensationPayload(values: FormValues) {
  return {
    base_salary: values.base_salary ? String(values.base_salary) : null,
    currency_code: values.currency_code ? String(values.currency_code).toUpperCase() : null,
    national_id: values.national_id ? String(values.national_id) : null,
    tax_id: values.tax_id ? String(values.tax_id) : null,
    date_of_birth: values.date_of_birth ? String(values.date_of_birth) : null,
    bank_account: values.bank_account ? String(values.bank_account) : null,
  };
}

/** The dedicated compensation/PII card (edit mode, read_compensation holders only). */
function CompensationSection({ employee }: { employee: Employee }) {
  const setCompensation = useSetEmployeeCompensation(employee.id);
  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setValues({
      base_salary: employee.base_salary ?? "",
      currency_code: employee.currency_code ?? "",
      national_id: employee.national_id ?? "",
      tax_id: employee.tax_id ?? "",
      date_of_birth: employee.date_of_birth ?? "",
      bank_account: employee.bank_account ?? "",
    });
  }, [employee]);

  const submit = async () => {
    setError(null);
    try {
      await setCompensation.mutateAsync(compensationPayload(values));
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the compensation."));
    }
  };

  return (
    <div className="mt-8 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
      <h2 className="mb-3.5 mono-caps text-ink-muted">Compensation & PII</h2>
      <p className="text-[12px] text-ink-muted">
        Written only through the dedicated compensation endpoint (D-009) — the general employee
        update can never touch these fields.
      </p>
      {error && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-3">
        <FormBuilder
          fields={COMPENSATION_FIELDS}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel="Save compensation"
          busy={setCompensation.isPending}
        />
      </div>
    </div>
  );
}

export function EmployeeFormPage() {
  const { employeeId } = useParams({ strict: false });
  const isEdit = employeeId !== undefined;
  const navigate = useNavigate();
  const me = useMe();
  const canReadCompensation = (me.data?.permissions ?? []).includes("hr.employee.read_compensation");

  const employee = useEmployee(employeeId);
  const departments = useDepartmentOptions();
  const positions = usePositionOptions();
  const employees = useEmployeeOptions();
  const createEmployee = useCreateEmployee();
  const updateEmployee = useUpdateEmployee(employeeId ?? "");

  const [values, setValues] = useState<FormValues>({ status: "ACTIVE", employment_type: "FULL_TIME" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (employee.data) {
      setValues({
        employee_code: employee.data.employee_code,
        first_name: employee.data.first_name,
        last_name: employee.data.last_name,
        email: employee.data.email ?? "",
        department_id: employee.data.department_id ?? "",
        position_id: employee.data.position_id ?? "",
        manager_id: employee.data.manager_id ?? "",
        status: employee.data.status,
        employment_type: employee.data.employment_type,
        hire_date: employee.data.hire_date,
        termination_date: employee.data.termination_date ?? "",
      });
    }
  }, [employee.data]);

  const departmentOptions = (departments.data?.items ?? []).map((d) => ({
    value: d.id,
    label: `${d.code} — ${d.name}`,
  }));
  const positionOptions = (positions.data?.items ?? []).map((p) => ({
    value: p.id,
    label: `${p.code} — ${p.title}`,
  }));
  const managerOptions = (employees.data?.items ?? [])
    .filter((e) => e.id !== employeeId)
    .map((e) => ({ value: e.id, label: `${e.employee_code} — ${e.first_name} ${e.last_name}` }));

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        first_name: String(values.first_name ?? ""),
        last_name: String(values.last_name ?? ""),
        email: values.email ? String(values.email) : null,
        department_id: values.department_id ? String(values.department_id) : null,
        position_id: values.position_id ? String(values.position_id) : null,
        manager_id: values.manager_id ? String(values.manager_id) : null,
        status: values.status as EmploymentStatus,
        employment_type: values.employment_type as EmploymentType,
        hire_date: String(values.hire_date ?? ""),
        termination_date: values.termination_date ? String(values.termination_date) : null,
      };
      if (isEdit) {
        const payload: EmployeeUpdate = shared;
        await updateEmployee.mutateAsync(payload);
      } else {
        const payload: EmployeeCreate = {
          ...shared,
          employee_code: String(values.employee_code ?? ""),
          ...compensationPayload(values),
        };
        const created = await createEmployee.mutateAsync(payload);
        void navigate({ to: "/hr/employees/$employeeId", params: { employeeId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the employee."));
    }
  };

  const busy = createEmployee.isPending || updateEmployee.isPending;
  const coreFields = coreFieldsFor(isEdit, departmentOptions, positionOptions, managerOptions);
  // Create seeds initial pay in the same call (the create endpoint requires read_compensation).
  const fields = isEdit ? coreFields : [...coreFields, ...COMPENSATION_FIELDS];

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hr/employees">Employees</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit employee" : "New employee"}</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {isEdit ? "Edit employee" : "New employee"}
        </h1>
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
          submitLabel={isEdit ? "Save changes" : "Create employee"}
          busy={busy}
        />
      </div>

      {isEdit &&
        employee.data &&
        (canReadCompensation ? (
          <CompensationSection employee={employee.data} />
        ) : (
          <p className="mt-8 rounded-card border border-line bg-panel px-4 py-3 text-xs text-ink-muted">
            Compensation and PII are masked — viewing or editing them requires the
            hr.employee.read_compensation permission.
          </p>
        ))}
    </div>
  );
}
