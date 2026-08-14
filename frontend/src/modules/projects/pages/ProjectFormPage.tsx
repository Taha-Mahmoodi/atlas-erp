/**
 * Create or edit a project (STRUCTURE §4). Edit via `/projects/$projectId/edit`; create via
 * `/projects/new`. `code` is immutable after creation. Customer link via sales' option hook
 * (the finance-AR precedent for cross-module option pickers).
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateProject, useProject, useUpdateProject } from "@/modules/projects/hooks";
import type { ProjectCreate, ProjectStatus, ProjectUpdate } from "@/modules/projects/types";
import { useCustomerOptions } from "@/modules/sales/hooks";

// ponytail: cost_center_id is omitted — finance has no frontend cost-center surface yet;
// add the picker when finance ships one (the field stays null-able server-side).
function fieldsFor(isEdit: boolean, customerOptions: { value: string; label: string }[]): FieldDef[] {
  return [
    { name: "code", label: "Project code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    {
      name: "status",
      label: "Status",
      type: "select",
      options: [
        { value: "PLANNING", label: "Planning" },
        { value: "ACTIVE", label: "Active" },
        { value: "CLOSED", label: "Closed" },
        { value: "CANCELLED", label: "Cancelled" },
      ],
      span: 1,
    },
    { name: "customer_id", label: "Customer", type: "select", options: customerOptions, span: 1 },
    { name: "start_date", label: "Start date", type: "date", span: 1 },
    { name: "end_date", label: "End date", type: "date", span: 1 },
    {
      name: "budget_amount",
      label: "Budget",
      type: "number",
      step: "0.01",
      span: 1,
      help: "Overall project budget; WBS elements carry their own.",
    },
    { name: "is_active", label: "Active", type: "checkbox", span: 1 },
    { name: "description", label: "Description", type: "textarea", span: 2 },
  ];
}

export function ProjectFormPage() {
  const { projectId } = useParams({ strict: false });
  const isEdit = projectId !== undefined;
  const navigate = useNavigate();

  const project = useProject(projectId);
  const customers = useCustomerOptions();
  const createProject = useCreateProject();
  const updateProject = useUpdateProject(projectId ?? "");

  const [values, setValues] = useState<FormValues>({ status: "PLANNING", is_active: true });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (project.data) {
      setValues({
        code: project.data.code,
        name: project.data.name,
        status: project.data.status,
        customer_id: project.data.customer_id ?? "",
        start_date: project.data.start_date ?? "",
        end_date: project.data.end_date ?? "",
        budget_amount: project.data.budget_amount ?? "",
        is_active: project.data.is_active,
        description: project.data.description ?? "",
      });
    }
  }, [project.data]);

  const customerOptions = (customers.data?.items ?? []).map((customer) => ({
    value: customer.id,
    label: `${customer.customer_code} — ${customer.name}`,
  }));

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        description: values.description ? String(values.description) : null,
        status: values.status as ProjectStatus,
        customer_id: values.customer_id ? String(values.customer_id) : null,
        start_date: values.start_date ? String(values.start_date) : null,
        end_date: values.end_date ? String(values.end_date) : null,
        budget_amount: values.budget_amount ? String(values.budget_amount) : null,
        is_active: Boolean(values.is_active),
      };
      if (isEdit) {
        const payload: ProjectUpdate = shared;
        await updateProject.mutateAsync(payload);
        void navigate({ to: "/projects/$projectId", params: { projectId } });
      } else {
        const payload: ProjectCreate = { ...shared, code: String(values.code ?? "") };
        const created = await createProject.mutateAsync(payload);
        void navigate({ to: "/projects/$projectId", params: { projectId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the project."));
    }
  };

  const busy = createProject.isPending || updateProject.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{isEdit ? "Edit project" : "New project"}</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, customerOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create project"}
          busy={busy}
        />
      </div>
    </div>
  );
}
