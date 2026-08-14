/**
 * Field-definition-driven form (DESIGN.md): native controls only, uniform vocabulary,
 * 1–2 column layout, inline errors wired via aria-invalid/aria-describedby, busy submit.
 * Controlled — values/errors live with the caller; this renders and reports.
 */

import type { FormEvent, ReactNode } from "react";

export interface SelectOption {
  value: string;
  label: string;
}

export interface FieldDef {
  name: string;
  label: string;
  type: "text" | "password" | "number" | "date" | "select" | "checkbox" | "textarea";
  required?: boolean;
  placeholder?: string;
  /** For selects. An empty-value placeholder option is always added automatically — even
   * when required — so an unset value never silently displays as the first real option. */
  options?: SelectOption[];
  help?: string;
  disabled?: boolean;
  /** Grid columns to span in a 2-column layout. */
  span?: 1 | 2;
  /** number inputs: step granularity (e.g. "0.01" for money). */
  step?: string;
}

export type FormValues = Record<string, string | boolean>;

export interface FormBuilderProps {
  fields: FieldDef[];
  values: FormValues;
  errors?: Record<string, string>;
  onChange: (name: string, value: string | boolean) => void;
  onSubmit: () => void;
  submitLabel?: string;
  /** Disables everything and swaps the submit label while a mutation runs. */
  busy?: boolean;
  columns?: 1 | 2;
  /** Extra actions rendered beside submit (e.g. a cancel link). */
  footer?: ReactNode;
}

const CONTROL =
  "w-full min-h-[38px] rounded-control border border-line bg-surface px-3 py-2 text-[13px] text-ink " +
  "placeholder:text-ink-muted transition-colors duration-150 " +
  "hover:border-ink-muted disabled:cursor-not-allowed disabled:opacity-45";
const CONTROL_ERROR = "border-danger";

function Control({
  field,
  value,
  error,
  busy,
  onChange,
}: {
  field: FieldDef;
  value: string | boolean;
  error: string | undefined;
  busy: boolean;
  onChange: FormBuilderProps["onChange"];
}) {
  const shared = {
    id: `field-${field.name}`,
    name: field.name,
    disabled: busy || field.disabled === true,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": error
      ? `field-${field.name}-error`
      : field.help
        ? `field-${field.name}-help`
        : undefined,
    className: `${CONTROL} ${error ? CONTROL_ERROR : ""}`,
  };
  if (field.type === "textarea") {
    return (
      <textarea
        {...shared}
        rows={3}
        value={String(value ?? "")}
        placeholder={field.placeholder}
        onChange={(event) => onChange(field.name, event.target.value)}
      />
    );
  }
  if (field.type === "select") {
    return (
      <select
        {...shared}
        required={field.required}
        value={String(value ?? "")}
        onChange={(event) => onChange(field.name, event.target.value)}
      >
        {/* Always rendered, even when required: a controlled <select> whose value doesn't
         * match any option falls back to silently displaying the first real option while
         * the underlying state stays empty — a user who never opens the dropdown submits an
         * empty value that visually looked chosen. This placeholder keeps "nothing selected
         * yet" visually true until the user actually picks something. */}
        <option value="">{field.required ? "Select…" : "—"}</option>
        {(field.options ?? []).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }
  if (field.type === "checkbox") {
    return (
      <input
        {...shared}
        type="checkbox"
        checked={Boolean(value)}
        onChange={(event) => onChange(field.name, event.target.checked)}
        className="size-4 accent-primary disabled:cursor-not-allowed disabled:opacity-45"
      />
    );
  }
  return (
    <input
      {...shared}
      type={field.type}
      value={String(value ?? "")}
      placeholder={field.placeholder}
      {...(field.type === "number" && field.step ? { step: field.step } : {})}
      onChange={(event) => onChange(field.name, event.target.value)}
      className={`${shared.className} ${field.type === "number" ? "tabular-nums" : ""}`}
    />
  );
}

export function FormBuilder({
  fields,
  values,
  errors = {},
  onChange,
  onSubmit,
  submitLabel = "Save",
  busy = false,
  columns = 2,
  footer,
}: FormBuilderProps) {
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!busy) onSubmit();
  };

  return (
    <form onSubmit={submit} noValidate>
      <div className={`grid gap-x-6 gap-y-4 ${columns === 2 ? "sm:grid-cols-2" : ""}`}>
        {fields.map((field) => {
          const error = errors[field.name];
          const isCheckbox = field.type === "checkbox";
          return (
            <div
              key={field.name}
              className={`${field.span === 2 ? "sm:col-span-2" : ""} ${
                isCheckbox ? "flex items-center gap-2" : ""
              }`}
            >
              {!isCheckbox && (
                <label
                  htmlFor={`field-${field.name}`}
                  className="mb-1 block text-xs font-medium text-ink-muted"
                >
                  {field.label}
                  {field.required && (
                    <span aria-hidden="true" className="ml-0.5 text-danger">
                      *
                    </span>
                  )}
                </label>
              )}
              <Control
                field={field}
                value={values[field.name] ?? (isCheckbox ? false : "")}
                error={error}
                busy={busy}
                onChange={onChange}
              />
              {isCheckbox && (
                <label htmlFor={`field-${field.name}`} className="text-sm text-ink">
                  {field.label}
                </label>
              )}
              {error ? (
                <p id={`field-${field.name}-error`} role="alert" className="mt-1 text-xs text-danger">
                  {error}
                </p>
              ) : (
                field.help && (
                  <p id={`field-${field.name}-help`} className="mt-1 text-xs text-ink-faint">
                    {field.help}
                  </p>
                )
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-6 flex items-center gap-3">
        {/* The porcelain primary: ink fill, not the accent. The accent stays reserved for
            links, active nav, focus and chips, so a screen has exactly one loud object.
            Standalone primaries render at the full 44px target (register §3). */}
        <button type="submit" disabled={busy} className="btn-ink btn-tall">
          {busy ? "Saving…" : submitLabel}
        </button>
        {footer}
      </div>
    </form>
  );
}
