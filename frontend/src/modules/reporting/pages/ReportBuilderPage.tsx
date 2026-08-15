/**
 * The ad-hoc report builder (PLAN 15.12, D-059): pick a whitelisted entity from the
 * role-filtered catalog, then columns + filters + optional group-by/aggregations; run to a
 * results grid (10k cap, truncation flagged) or download the full set as streaming CSV.
 * Define-and-run only — nothing is persisted, matching the backend's ad-hoc-only v1.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { exportReportCsv } from "@/modules/reporting/api";
import { useReportEntities, useRunReport } from "@/modules/reporting/hooks";
import type {
  ReportAggregation,
  ReportAggregationFunc,
  ReportEntityDescriptor,
  ReportFilter,
  ReportFilterOperator,
  ReportResult,
  ReportSpec,
} from "@/modules/reporting/types";

const OPERATORS: { value: ReportFilterOperator; label: string }[] = [
  { value: "eq", label: "=" },
  { value: "ne", label: "≠" },
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
  { value: "in", label: "in (comma-separated)" },
  { value: "like", label: "contains" },
  { value: "between", label: "between (low, high)" },
  { value: "is_null", label: "is empty" },
];

const AGG_FUNCS: ReportAggregationFunc[] = ["count", "sum", "avg", "min", "max"];

/** A filter row as edited — the value stays a string until the spec is built. */
interface FilterDraft {
  column: string;
  operator: ReportFilterOperator;
  value: string;
}

interface AggregationDraft {
  func: ReportAggregationFunc;
  column: string;
}

/** Turn a draft's text value into the wire shape the operator expects (D-059): a list for IN,
 * a [low, high] pair for BETWEEN, a bool for IS_NULL, the raw string otherwise (the backend
 * coerces bound values to the column's type). Exported for its unit test only. */
export function filterValue(draft: FilterDraft): unknown {
  if (draft.operator === "is_null") return draft.value !== "false";
  if (draft.operator === "in")
    return draft.value.split(",").map((part) => part.trim()).filter(Boolean);
  if (draft.operator === "between") {
    const [low, high] = draft.value.split(",").map((part) => part.trim());
    return [low ?? "", high ?? ""];
  }
  return draft.value;
}

/** The grid's header for each result column (#166): the backend's display label, falling back to
 * the wire name when a label is missing (a pre-#166 server, or a stale cached response). The CSV
 * export writes the very same labels server-side, so the two surfaces cannot drift apart.
 * Exported for its unit test only. */
export function resultHeaders(
  result?: Pick<ReportResult, "columns"> & Partial<Pick<ReportResult, "column_labels">>,
): string[] {
  const labels = result?.column_labels ?? [];
  return (result?.columns ?? []).map((name, index) => labels[index] ?? name);
}

const controlClass = "rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink";
const primaryButtonClass =
  "btn-ink";
const secondaryButtonClass =
  "rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-primary disabled:opacity-50";

export function ReportBuilderPage() {
  const entities = useReportEntities();
  const run = useRunReport();

  const [entityKey, setEntityKey] = useState("");
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [filters, setFilters] = useState<FilterDraft[]>([]);
  const [groupBy, setGroupBy] = useState<string[]>([]);
  const [aggregations, setAggregations] = useState<AggregationDraft[]>([]);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const entity: ReportEntityDescriptor | undefined = entities.data?.entities.find(
    (candidate) => candidate.key === entityKey,
  );
  const grouped = groupBy.length > 0;

  const selectEntity = (key: string) => {
    setEntityKey(key);
    // Reset the whole definition — columns/filters are entity-specific.
    setSelectedColumns([]);
    setFilters([]);
    setGroupBy([]);
    setAggregations([]);
    run.reset();
    setExportError(null);
  };

  const toggle = (list: string[], name: string): string[] =>
    list.includes(name) ? list.filter((entry) => entry !== name) : [...list, name];

  const buildSpec = (): ReportSpec | null => {
    if (!entity) return null;
    const spec: ReportSpec = {
      entity: entity.key,
      filters: filters
        .filter((draft) => draft.column)
        .map(
          (draft): ReportFilter => ({
            column: draft.column,
            operator: draft.operator,
            value: filterValue(draft),
          }),
        ),
    };
    if (grouped) {
      spec.group_by = groupBy;
      // A grouped report requires at least one aggregation (backend rule) — default to count.
      spec.aggregations = (
        aggregations.length > 0 ? aggregations : [{ func: "count" as const, column: "" }]
      ).map(
        (draft): ReportAggregation =>
          draft.func === "count" && !draft.column
            ? { func: "count" }
            : { func: draft.func, column: draft.column },
      );
    } else if (selectedColumns.length > 0) {
      // Preserve the entity's column order rather than click order.
      spec.columns = entity.columns
        .map((column) => column.name)
        .filter((name) => selectedColumns.includes(name));
    }
    return spec;
  };

  const runReport = () => {
    const spec = buildSpec();
    if (spec) run.mutate(spec);
  };

  const downloadCsv = async () => {
    const spec = buildSpec();
    if (!spec || exporting) return;
    setExporting(true);
    setExportError(null);
    try {
      const blob = await exportReportCsv(spec);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${spec.entity}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  const result = run.data;
  const headers = resultHeaders(result);
  const gridColumns: DataGridColumn<Record<string, unknown>>[] = (result?.columns ?? []).map(
    (name, index) => ({
      key: name,
      header: headers[index],
      render: (row) => String(row[name] ?? ""),
    }),
  );
  // Result rows have no natural id — key by position (identical duplicate rows are possible).
  const gridRows = (result?.rows ?? []).map((row, index) => ({ ...row, __key: String(index) }));

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/reporting">Reporting</Link> /{" "}
          <span className="text-ink">Report Builder</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          Report Builder
        </h1>
        <p className="mt-1 text-[13px] text-ink-muted">
          Ad-hoc reports over the entities your role can see. Define, run, export — nothing is
          saved.
        </p>
      </header>

      <div className="flex items-center gap-3">
        <label htmlFor="report-entity" className="text-sm text-ink-muted">
          Entity
        </label>
        <select
          id="report-entity"
          value={entityKey}
          onChange={(event) => selectEntity(event.target.value)}
          className={controlClass}
        >
          <option value="">
            {entities.isPending ? "Loading…" : "Select an entity"}
          </option>
          {(entities.data?.entities ?? []).map((candidate) => (
            <option key={candidate.key} value={candidate.key}>
              {candidate.label}
            </option>
          ))}
        </select>
      </div>

      {entities.data && entities.data.entities.length === 0 && (
        <p className="mt-6 text-sm text-ink-muted">
          Your role has no reportable entities — ask an administrator for module read access.
        </p>
      )}

      {entity && (
        <div className="mt-4 space-y-4">
          {/* Columns — used for a flat (ungrouped) report */}
          <section className="rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
            <h2 className="mb-3.5 mono-caps text-ink-muted">
              Columns {grouped && <span className="font-normal normal-case">(ignored while grouping — the result is group-by + aggregates)</span>}
            </h2>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {entity.columns.map((column) => (
                <label key={column.name} className="flex items-center gap-1.5 text-sm text-ink">
                  <input
                    type="checkbox"
                    disabled={grouped}
                    checked={selectedColumns.includes(column.name)}
                    onChange={() => setSelectedColumns(toggle(selectedColumns, column.name))}
                  />
                  {column.label}
                </label>
              ))}
            </div>
            {!grouped && selectedColumns.length === 0 && (
              <p className="mt-2 text-xs text-ink-faint">None selected — all columns are included.</p>
            )}
          </section>

          {/* Filters */}
          <section className="rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
            <h2 className="mb-3.5 mono-caps text-ink-muted">
              Filters
            </h2>
            {filters.map((draft, index) => (
              <div key={index} className="mt-2 flex flex-wrap items-center gap-2">
                <select
                  aria-label="Filter column"
                  value={draft.column}
                  onChange={(event) =>
                    setFilters(
                      filters.map((entry, at) =>
                        at === index ? { ...entry, column: event.target.value } : entry,
                      ),
                    )
                  }
                  className={controlClass}
                >
                  <option value="">Column…</option>
                  {entity.columns
                    .filter((column) => column.filterable)
                    .map((column) => (
                      <option key={column.name} value={column.name}>
                        {column.label}
                      </option>
                    ))}
                </select>
                <select
                  aria-label="Filter operator"
                  value={draft.operator}
                  onChange={(event) =>
                    setFilters(
                      filters.map((entry, at) =>
                        at === index
                          ? { ...entry, operator: event.target.value as ReportFilterOperator }
                          : entry,
                      ),
                    )
                  }
                  className={controlClass}
                >
                  {OPERATORS.map((operator) => (
                    <option key={operator.value} value={operator.value}>
                      {operator.label}
                    </option>
                  ))}
                </select>
                {draft.operator === "is_null" ? (
                  <select
                    aria-label="Filter value"
                    value={draft.value === "false" ? "false" : "true"}
                    onChange={(event) =>
                      setFilters(
                        filters.map((entry, at) =>
                          at === index ? { ...entry, value: event.target.value } : entry,
                        ),
                      )
                    }
                    className={controlClass}
                  >
                    <option value="true">empty</option>
                    <option value="false">not empty</option>
                  </select>
                ) : (
                  <input
                    aria-label="Filter value"
                    type="text"
                    value={draft.value}
                    placeholder={
                      draft.operator === "in"
                        ? "a, b, c"
                        : draft.operator === "between"
                          ? "low, high"
                          : "value"
                    }
                    onChange={(event) =>
                      setFilters(
                        filters.map((entry, at) =>
                          at === index ? { ...entry, value: event.target.value } : entry,
                        ),
                      )
                    }
                    className={controlClass}
                  />
                )}
                <button
                  type="button"
                  onClick={() => setFilters(filters.filter((_, at) => at !== index))}
                  className="text-[12.5px] font-medium text-ink-muted hover:text-danger"
                  aria-label="Remove filter"
                >
                  Remove
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => setFilters([...filters, { column: "", operator: "eq", value: "" }])}
              className={`mt-2 ${secondaryButtonClass}`}
            >
              Add filter
            </button>
          </section>

          {/* Group by + aggregations */}
          <section className="rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
            <h2 className="mb-3.5 mono-caps text-ink-muted">
              Group by
            </h2>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {entity.columns
                .filter((column) => column.groupable)
                .map((column) => (
                  <label key={column.name} className="flex items-center gap-1.5 text-sm text-ink">
                    <input
                      type="checkbox"
                      checked={groupBy.includes(column.name)}
                      onChange={() => setGroupBy(toggle(groupBy, column.name))}
                    />
                    {column.label}
                  </label>
                ))}
            </div>
            {grouped && (
              <div className="mt-3">
                <h3 className="mb-3.5 mono-caps text-ink-muted">
                  Aggregations
                </h3>
                {aggregations.map((draft, index) => (
                  <div key={index} className="mt-2 flex flex-wrap items-center gap-2">
                    <select
                      aria-label="Aggregation function"
                      value={draft.func}
                      onChange={(event) =>
                        setAggregations(
                          aggregations.map((entry, at) =>
                            at === index
                              ? { ...entry, func: event.target.value as ReportAggregationFunc }
                              : entry,
                          ),
                        )
                      }
                      className={controlClass}
                    >
                      {AGG_FUNCS.map((func) => (
                        <option key={func} value={func}>
                          {func}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Aggregation column"
                      value={draft.column}
                      onChange={(event) =>
                        setAggregations(
                          aggregations.map((entry, at) =>
                            at === index ? { ...entry, column: event.target.value } : entry,
                          ),
                        )
                      }
                      className={controlClass}
                    >
                      <option value="">{draft.func === "count" ? "rows (*)" : "Column…"}</option>
                      {entity.columns
                        .filter((column) => draft.func === "count" || column.is_aggregatable)
                        .map((column) => (
                          <option key={column.name} value={column.name}>
                            {column.label}
                          </option>
                        ))}
                    </select>
                    <button
                      type="button"
                      onClick={() =>
                        setAggregations(aggregations.filter((_, at) => at !== index))
                      }
                      className="text-[12.5px] font-medium text-ink-muted hover:text-danger"
                      aria-label="Remove aggregation"
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() =>
                    setAggregations([...aggregations, { func: "count", column: "" }])
                  }
                  className={`mt-2 ${secondaryButtonClass}`}
                >
                  Add aggregation
                </button>
                {aggregations.length === 0 && (
                  <p className="mt-2 text-xs text-ink-faint">
                    None added — a row count per group is used.
                  </p>
                )}
              </div>
            )}
          </section>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={runReport}
              disabled={run.isPending}
              className={primaryButtonClass}
            >
              {run.isPending ? "Running…" : "Run report"}
            </button>
            <button
              type="button"
              onClick={() => void downloadCsv()}
              disabled={exporting}
              className={secondaryButtonClass}
            >
              {exporting ? "Exporting…" : "Export CSV"}
            </button>
          </div>

          {run.isError && (
            <p role="alert" className="text-sm text-danger">
              {run.error instanceof Error ? run.error.message : "Report failed"}
            </p>
          )}
          {exportError && (
            <p role="alert" className="text-sm text-danger">
              {exportError}
            </p>
          )}

          {result && (
            <section>
              <p className="mb-2 text-sm text-ink-muted">
                {result.row_count} row{result.row_count === 1 ? "" : "s"}
                {result.truncated &&
                  " — truncated at the grid cap; use Export CSV for the full result."}
              </p>
              <DataGrid
                label="Report result"
                columns={gridColumns}
                rows={gridRows}
                rowKey={(row) => String(row.__key)}
                emptyMessage="No rows matched — adjust the filters and run again."
              />
            </section>
          )}
        </div>
      )}
    </div>
  );
}
