/**
 * Create or edit a routing (STRUCTURE §4) — the BOM form's twin. Identity is (item_id,
 * version), both immutable after creation. Only DRAFT is header-editable and only DRAFT can
 * gain/lose operations (setup/run times per work center). Activating demotes any prior
 * ACTIVE+default version of the same item; deactivating clears status AND the default flag.
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useItemOptions } from "@/modules/inventory/hooks";
import {
  useActivateRouting,
  useCreateRouting,
  useCreateRoutingOperation,
  useDeactivateRouting,
  useDeleteRoutingOperation,
  useRouting,
  useRoutingOperations,
  useUpdateRouting,
  useWorkCenterOptions,
} from "@/modules/manufacturing/hooks";
import type { RoutingCreate, RoutingUpdate } from "@/modules/manufacturing/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function fieldsFor(isEdit: boolean, itemOptions: { value: string; label: string }[]): FieldDef[] {
  return [
    { name: "item_id", label: "Item", type: "select", options: itemOptions, required: true, disabled: isEdit, span: 1 },
    { name: "version", label: "Version", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 2 },
    { name: "notes", label: "Notes", type: "textarea", span: 2 },
  ];
}

function RoutingOperationsSection({ routingId, isDraft }: { routingId: string; isDraft: boolean }) {
  const operations = useRoutingOperations(routingId);
  const workCenters = useWorkCenterOptions();
  const createOperation = useCreateRoutingOperation(routingId);
  const deleteOperation = useDeleteRoutingOperation(routingId);
  const [workCenterId, setWorkCenterId] = useState("");
  const [description, setDescription] = useState("");
  const [setupMinutes, setSetupMinutes] = useState("0");
  const [runMinutes, setRunMinutes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    setError(null);
    try {
      await createOperation.mutateAsync({
        work_center_id: workCenterId,
        description: description || null,
        setup_time_minutes: setupMinutes,
        run_time_minutes_per_unit: runMinutes,
      });
      setWorkCenterId("");
      setDescription("");
      setSetupMinutes("0");
      setRunMinutes("");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to add the operation."));
    }
  };

  const remove = async (operationId: string) => {
    setError(null);
    try {
      await deleteOperation.mutateAsync(operationId);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to remove the operation."));
    }
  };

  const workCenterLabel = (id: string) => {
    const workCenter = workCenters.data?.items.find((w) => w.id === id);
    return workCenter ? `${workCenter.code} — ${workCenter.name}` : id;
  };

  return (
    <div className="mt-8 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
      <h2 className="mono-caps mb-3.5 text-ink-muted">Operations</h2>
      <p className="text-[12px] text-ink-muted">
        Ordered steps with setup and per-unit run times at a work center — a production order snapshots
        these at create time.
      </p>
      {error && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <table className="mt-3 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-1.5 pr-2">Op</th>
            <th className="py-1.5 pr-2">Work center</th>
            <th className="py-1.5 pr-2">Description</th>
            <th className="py-1.5 pr-2 text-right">Setup (min)</th>
            <th className="py-1.5 pr-2 text-right">Run (min/unit)</th>
            {isDraft && <th className="py-1.5 pr-2" />}
          </tr>
        </thead>
        <tbody>
          {(operations.data ?? []).map((operation) => (
            <tr key={operation.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{operation.operation_number}</td>
              <td className="py-1.5 pr-2 text-ink">{workCenterLabel(operation.work_center_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{operation.description ?? "—"}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(operation.setup_time_minutes)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">
                {formatQuantity(operation.run_time_minutes_per_unit)}
              </td>
              {isDraft && (
                <td className="py-1.5 pr-2">
                  <button
                    type="button"
                    onClick={() => void remove(operation.id)}
                    className="text-[12.5px] font-medium text-danger hover:underline"
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {isDraft && (
        <div className="mt-3 flex items-end gap-2">
          <div className="flex-1">
            <label htmlFor="op-work-center" className="mb-1 block text-xs font-medium text-ink-muted">
              Work center
            </label>
            <select
              id="op-work-center"
              value={workCenterId}
              onChange={(event) => setWorkCenterId(event.target.value)}
              className={CONTROL}
            >
              <option value="">Select work center</option>
              {(workCenters.data?.items ?? []).map((workCenter) => (
                <option key={workCenter.id} value={workCenter.id}>
                  {workCenter.code} — {workCenter.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label htmlFor="op-description" className="mb-1 block text-xs font-medium text-ink-muted">
              Description
            </label>
            <input
              id="op-description"
              type="text"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className={CONTROL}
            />
          </div>
          <div className="w-28">
            <label htmlFor="op-setup" className="mb-1 block text-xs font-medium text-ink-muted">
              Setup (min)
            </label>
            <input
              id="op-setup"
              type="number"
              step="0.01"
              value={setupMinutes}
              onChange={(event) => setSetupMinutes(event.target.value)}
              className={CONTROL}
            />
          </div>
          <div className="w-32">
            <label htmlFor="op-run" className="mb-1 block text-xs font-medium text-ink-muted">
              Run (min/unit)
            </label>
            <input
              id="op-run"
              type="number"
              step="0.01"
              value={runMinutes}
              onChange={(event) => setRunMinutes(event.target.value)}
              className={CONTROL}
            />
          </div>
          <button
            type="button"
            onClick={() => void add()}
            disabled={!workCenterId || !runMinutes || createOperation.isPending}
            className="btn-ink"
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}

export function RoutingFormPage() {
  const { routingId } = useParams({ strict: false });
  const isEdit = routingId !== undefined;
  const navigate = useNavigate();

  const routing = useRouting(routingId);
  const items = useItemOptions();
  const createRouting = useCreateRouting();
  const updateRouting = useUpdateRouting(routingId ?? "");
  const activateRouting = useActivateRouting(routingId ?? "");
  const deactivateRouting = useDeactivateRouting(routingId ?? "");

  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  const itemOptions = (items.data?.items ?? []).map((item) => ({
    value: item.id,
    label: `${item.item_code} — ${item.name}`,
  }));

  useEffect(() => {
    if (routing.data) {
      setValues({
        item_id: routing.data.item_id,
        version: routing.data.version,
        name: routing.data.name,
        notes: routing.data.notes ?? "",
      });
    }
  }, [routing.data]);

  const isDraft = !isEdit || routing.data?.status === "DRAFT";
  const isActive = routing.data?.status === "ACTIVE";

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        notes: values.notes ? String(values.notes) : null,
      };
      if (isEdit) {
        const payload: RoutingUpdate = shared;
        await updateRouting.mutateAsync(payload);
      } else {
        const payload: RoutingCreate = {
          ...shared,
          item_id: String(values.item_id ?? ""),
          version: String(values.version ?? ""),
        };
        const created = await createRouting.mutateAsync(payload);
        void navigate({ to: "/manufacturing/routings/$routingId", params: { routingId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the routing."));
    }
  };

  const activate = async () => {
    setError(null);
    try {
      await activateRouting.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to activate the routing."));
    }
  };

  const deactivate = async () => {
    setError(null);
    try {
      await deactivateRouting.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to deactivate the routing."));
    }
  };

  const busy = createRouting.isPending || updateRouting.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/manufacturing/routings">Routings</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit routing" : "New routing"}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{isEdit ? "Edit routing" : "New routing"}</h1>
          {isEdit && routing.data && (
            <div className="flex items-center gap-2.5">
              {isDraft && (
                <button
                  type="button"
                  onClick={() => void activate()}
                  disabled={activateRouting.isPending}
                  className="btn-ink"
                >
                  {activateRouting.isPending ? "Activating…" : "Activate"}
                </button>
              )}
              {isActive && (
                <button
                  type="button"
                  onClick={() => void deactivate()}
                  disabled={deactivateRouting.isPending}
                  className="btn-chip hover:border-danger hover:text-danger"
                >
                  Deactivate
                </button>
              )}
            </div>
          )}
        </div>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, itemOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create routing"}
          busy={busy}
        />
      </div>

      {isEdit && routingId && <RoutingOperationsSection routingId={routingId} isDraft={Boolean(isDraft)} />}
    </div>
  );
}
