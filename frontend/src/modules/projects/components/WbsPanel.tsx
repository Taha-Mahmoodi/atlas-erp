/**
 * The WBS elements panel on the project workbench (module-specific composite, STRUCTURE §4):
 * indented tree table + an inline add/edit form (the price-list lines precedent — WBS elements
 * are managed on their project's page, not on standalone routes). `code` is immutable after
 * creation; `parent_id` picks from the same project's elements.
 */

import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney } from "@/lib/format";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import { treeOrder } from "@/modules/projects/components/wbsTree";
import { useCreateWbsElement, useUpdateWbsElement, useWbsElements } from "@/modules/projects/hooks";
import type { WbsElement, WbsElementCreate, WbsElementUpdate, WbsStatus } from "@/modules/projects/types";
import { StatusPill } from "@/components/StatusPill";

const EMPTY: FormValues = { status: "OPEN", is_billable: false };

function fieldsFor(isEdit: boolean, parentOptions: { value: string; label: string }[]): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    { name: "parent_id", label: "Parent element", type: "select", options: parentOptions, span: 1 },
    {
      name: "status",
      label: "Status",
      type: "select",
      options: [
        { value: "OPEN", label: "Open" },
        { value: "CLOSED", label: "Closed" },
      ],
      span: 1,
    },
    { name: "budget_amount", label: "Budget", type: "number", step: "0.01", span: 1 },
    { name: "is_billable", label: "Billable", type: "checkbox", span: 1 },
  ];
}

export function WbsPanel({ projectId, canManage }: { projectId: string; canManage: boolean }) {
  const currency = useFunctionalCurrency();
  const elements = useWbsElements(projectId);
  const createElement = useCreateWbsElement(projectId);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const updateElement = useUpdateWbsElement(editingId ?? "");

  const rows = treeOrder(elements.data?.items ?? []);
  const parentOptions = rows
    .filter((entry) => entry.node.id !== editingId)
    .map((entry) => ({ value: entry.node.id, label: `${entry.node.code} — ${entry.node.name}` }));

  const startEdit = (element: WbsElement) => {
    setEditingId(element.id);
    setError(null);
    setValues({
      code: element.code,
      name: element.name,
      parent_id: element.parent_id ?? "",
      status: element.status,
      budget_amount: element.budget_amount ?? "",
      is_billable: element.is_billable,
    });
  };

  const reset = () => {
    setEditingId(null);
    setValues(EMPTY);
    setError(null);
  };

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        parent_id: values.parent_id ? String(values.parent_id) : null,
        status: values.status as WbsStatus,
        is_billable: Boolean(values.is_billable),
        budget_amount: values.budget_amount ? String(values.budget_amount) : null,
      };
      if (editingId) {
        const payload: WbsElementUpdate = shared;
        await updateElement.mutateAsync(payload);
      } else {
        const payload: WbsElementCreate = { ...shared, code: String(values.code ?? "") };
        await createElement.mutateAsync(payload);
      }
      reset();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the WBS element."));
    }
  };

  return (
    <section aria-label="WBS elements">
      <h2 className="text-sm font-semibold text-ink">WBS elements</h2>
      <p className="mt-0.5 text-xs text-ink-muted">
        The costing objects — finance journal lines and HR time entries post to a WBS element.
      </p>

      <div className="mt-3 overflow-x-auto rounded-card border border-line bg-surface shadow-card">
        <table className="w-full border-collapse text-[13px]" aria-label="WBS tree">
          <thead>
            <tr className="border-b border-line bg-panel text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
              <th className="px-3 py-2">Code</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Billable</th>
              <th className="px-3 py-2 text-right">Budget</th>
              {canManage && <th className="w-16 px-3 py-2" />}
            </tr>
          </thead>
          <tbody>
            {!elements.isPending && rows.length === 0 && (
              <tr>
                <td colSpan={canManage ? 6 : 5} className="px-4 py-8 text-center text-sm text-ink-muted">
                  No WBS elements yet — add the first one below.
                </td>
              </tr>
            )}
            {rows.map(({ node, depth }) => (
              <tr key={node.id} className="border-b border-line last:border-b-0">
                <td className="px-3 py-1.5 text-ink" style={{ paddingLeft: `${12 + depth * 20}px` }}>
                  {node.code}
                </td>
                <td className="px-3 py-1.5 text-ink">{node.name}</td>
                <td className="px-3 py-1.5">
                  <StatusPill status={node.status} />
                </td>
                <td className="px-3 py-1.5 text-ink-muted">{node.is_billable ? "Yes" : "—"}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">
                  {node.budget_amount === null ? "—" : formatMoney(node.budget_amount, currency.data ?? "—")}
                </td>
                {canManage && (
                  <td className="px-3 py-1.5 text-right">
                    <button
                      type="button"
                      onClick={() => startEdit(node)}
                      className="rounded-control px-2 py-0.5 text-xs font-medium text-primary transition-colors duration-150 hover:bg-primary-tint"
                    >
                      Edit
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {canManage && (
        <div className="mt-4 rounded-card border border-line bg-surface p-4 shadow-card">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-ink">
              {editingId ? "Edit WBS element" : "New WBS element"}
            </h3>
            {editingId && (
              <button
                type="button"
                onClick={reset}
                className="text-xs font-medium text-ink-muted transition-colors duration-150 hover:text-ink"
              >
                Cancel edit
              </button>
            )}
          </div>
          {error && (
            <p role="alert" className="mt-3 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
              {error}
            </p>
          )}
          <div className="mt-4">
            <FormBuilder
              fields={fieldsFor(editingId !== null, parentOptions)}
              values={values}
              onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
              onSubmit={() => void submit()}
              submitLabel={editingId ? "Save element" : "Add element"}
              busy={createElement.isPending || updateElement.isPending}
            />
          </div>
        </div>
      )}
    </section>
  );
}
