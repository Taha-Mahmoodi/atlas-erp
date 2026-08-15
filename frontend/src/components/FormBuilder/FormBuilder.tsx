/**
 * Field-definition-driven form (DESIGN.md): native controls only, uniform vocabulary,
 * 1–2 column layout, inline errors wired via aria-invalid/aria-describedby, busy submit.
 * Controlled — values and server errors live with the caller; this renders and reports.
 * The one rule it owns itself: `required` fields are checked before `onSubmit` fires, so an
 * empty required field costs a field-level message instead of a round-trip and a 422 banner.
 */

import { useState, type FormEvent, type ReactNode } from "react";

export interface SelectOption {
  value: string;
  label: string;
}

export interface FieldDef {
  name: string;
  label: string;
  type: "text" | "password" | "number" | "date" | "select" | "checkbox" | "textarea";
  /** Blocks submit while empty, and marks the control required for assistive tech. Ignored
   * on checkboxes (would mean must-be-checked) and on disabled fields (unfixable). */
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
    /* Announced to assistive tech, not enforced by the browser (the form is noValidate).
     * Checkboxes are excluded because there `required` means must-be-checked — a rule the
     * submit gate deliberately does not enforce, and announcing it would be a lie. */
    required: field.type === "checkbox" ? undefined : field.required,
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
  /* Required is enforced here rather than by the browser: the form stays `noValidate`
   * because native bubbles would fight this component's own inline error slot and its
   * controlled state. Client errors merge under the caller's `errors`, which win on
   * collision — those carry server truth (a 422 field error) that outranks "this looks
   * empty". */
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});
  /* A client error is only *shown* while its field is still empty, rather than being cleared
   * on change: the caller may replace `values` wholesale without going through `onChange`
   * (an edit record landing, WbsPanel switching from add to edit), and a "X is required."
   * with aria-invalid sitting over a filled control is a lie to a screen reader. */
  const shownErrors = {
    ...Object.fromEntries(
      Object.entries(clientErrors).filter(([name]) => String(values[name] ?? "").trim() === ""),
    ),
    ...errors,
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const missing: Record<string, string> = {};
    for (const field of fields) {
      /* Disabled fields are exempt for the same reason the HTML spec bars them from
       * constraint validation: the user cannot fix what they cannot type in, and an edit
       * form's immutable key (`required: true, disabled: isEdit`) is empty for the moment
       * before the record loads. Unchecked checkboxes are not "missing" either — a
       * must-be-checked rule is a different flag no caller has asked for yet. */
      if (!field.required || field.disabled === true || field.type === "checkbox") continue;
      if (String(values[field.name] ?? "").trim() === "") {
        missing[field.name] = `${field.label} is required.`;
      }
    }
    setClientErrors(missing);
    const first = Object.keys(missing)[0];
    if (first !== undefined) {
      // Move the caret to the first offender so a keyboard user is not left hunting.
      document.getElementById(`field-${first}`)?.focus();
      return;
    }
    onSubmit();
  };

  return (
    <form onSubmit={submit} noValidate>
      <div className={`grid gap-x-6 gap-y-4 ${columns === 2 ? "sm:grid-cols-2" : ""}`}>
        {fields.map((field) => {
          const error = shownErrors[field.name];
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
