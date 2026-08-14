/**
 * Create or edit a department (STRUCTURE §4). Edit via `/hr/departments/$departmentId`; create
 * via `/hr/departments/new`. `code` is immutable after creation. Parent must not form a cycle
 * (validated server-side); cost center is finance-owned reference data (D-029).
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import {
  useCostCenterOptions,
  useCreateDepartment,
  useDepartment,
  useDepartmentOptions,
  useEmployeeOptions,
  useUpdateDepartment,
} from "@/modules/hr/hooks";
import type { DepartmentCreate, DepartmentUpdate } from "@/modules/hr/types";

type Option = { value: string; label: string };

function fieldsFor(
  isEdit: boolean,
  parentOptions: Option[],
  costCenterOptions: Option[],
  employeeOptions: Option[],
): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    { name: "parent_id", label: "Parent department", type: "select", options: parentOptions, span: 1 },
    { name: "cost_center_id", label: "Cost center", type: "select", options: costCenterOptions, span: 1 },
    { name: "manager_employee_id", label: "Manager", type: "select", options: employeeOptions, span: 1 },
    { name: "is_active", label: "Active", type: "checkbox", span: 1 },
    { name: "description", label: "Description", type: "textarea", span: 2 },
  ];
}

export function DepartmentFormPage() {
  const { departmentId } = useParams({ strict: false });
  const isEdit = departmentId !== undefined;
  const navigate = useNavigate();

  const department = useDepartment(departmentId);
  const departments = useDepartmentOptions();
  const costCenters = useCostCenterOptions();
  const employees = useEmployeeOptions();
  const createDepartment = useCreateDepartment();
  const updateDepartment = useUpdateDepartment(departmentId ?? "");

  const [values, setValues] = useState<FormValues>({ is_active: true });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (department.data) {
      setValues({
        code: department.data.code,
        name: department.data.name,
        parent_id: department.data.parent_id ?? "",
        cost_center_id: department.data.cost_center_id ?? "",
        manager_employee_id: department.data.manager_employee_id ?? "",
        is_active: department.data.is_active,
        description: department.data.description ?? "",
      });
    }
  }, [department.data]);

  const parentOptions = (departments.data?.items ?? [])
    .filter((d) => d.id !== departmentId)
    .map((d) => ({ value: d.id, label: `${d.code} — ${d.name}` }));
  const costCenterOptions = (costCenters.data?.items ?? []).map((c) => ({
    value: c.id,
    label: `${c.code} — ${c.name}`,
  }));
  const employeeOptions = (employees.data?.items ?? []).map((e) => ({
    value: e.id,
    label: `${e.employee_code} — ${e.first_name} ${e.last_name}`,
  }));

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        description: values.description ? String(values.description) : null,
        parent_id: values.parent_id ? String(values.parent_id) : null,
        cost_center_id: values.cost_center_id ? String(values.cost_center_id) : null,
        manager_employee_id: values.manager_employee_id ? String(values.manager_employee_id) : null,
        is_active: values.is_active === true,
      };
      if (isEdit) {
        const payload: DepartmentUpdate = shared;
        await updateDepartment.mutateAsync(payload);
      } else {
        const payload: DepartmentCreate = { ...shared, code: String(values.code ?? "") };
        const created = await createDepartment.mutateAsync(payload);
        void navigate({ to: "/hr/departments/$departmentId", params: { departmentId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the department."));
    }
  };

  const busy = createDepartment.isPending || updateDepartment.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hr/departments">Departments</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit department" : "New department"}</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {isEdit ? "Edit department" : "New department"}
        </h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, parentOptions, costCenterOptions, employeeOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create department"}
          busy={busy}
        />
      </div>
    </div>
  );
}
