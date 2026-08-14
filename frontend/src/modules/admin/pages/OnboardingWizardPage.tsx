/**
 * Tenant onboarding wizard (PLAN 14.2 backend, 15.12 UI): company info → industry
 * template pick → review + instantiation. One POST /onboarding/tenants provisions the
 * tenant, first admin and the template's COA/tax/currencies/UoMs/numbering atomically;
 * the result step renders the instantiated-count summary the backend returns.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useMe } from "@/lib/session";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useIndustryTemplates, useOnboardTenant } from "@/modules/admin/hooks";
import type { OnboardTenantResponse } from "@/modules/admin/types";

const COMPANY_FIELDS: FieldDef[] = [
  { name: "company_name", label: "Company name", type: "text", required: true, span: 2 },
  { name: "slug", label: "Slug", type: "text", span: 2, help: "Optional URL-safe identifier; derived from the company name when left blank." },
  { name: "admin_email", label: "Admin email", type: "text", required: true, span: 1 },
  { name: "admin_password", label: "Admin password", type: "password", required: true, span: 1, help: "At least 12 characters." },
];

function CompanyStep({ values, onChange, onNext }: {
  values: FormValues;
  onChange: (name: string, value: string | boolean) => void;
  onNext: () => void;
}) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const next = () => {
    const problems: Record<string, string> = {};
    if (!String(values.company_name ?? "").trim()) problems.company_name = "Company name is required.";
    const email = String(values.admin_email ?? "");
    if (!email.includes("@") || email.startsWith("@") || email.endsWith("@")) {
      problems.admin_email = "Enter a valid email address.";
    }
    if (String(values.admin_password ?? "").length < 12) {
      problems.admin_password = "Password must be at least 12 characters.";
    }
    setErrors(problems);
    if (Object.keys(problems).length === 0) onNext();
  };
  return (
    <FormBuilder
      fields={COMPANY_FIELDS}
      values={values}
      errors={errors}
      onChange={onChange}
      onSubmit={next}
      submitLabel="Next: pick a template"
    />
  );
}

export function OnboardingWizardPage() {
  const me = useMe();
  const templates = useIndustryTemplates();
  const onboard = useOnboardTenant();

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [values, setValues] = useState<FormValues>({});
  const [templateName, setTemplateName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OnboardTenantResponse | null>(null);

  const canOnboard = (me.data?.permissions ?? []).includes("onboarding.tenant.create");
  const chosen = templates.data?.find((template) => template.name === templateName);

  const submit = async () => {
    setError(null);
    try {
      const slug = String(values.slug ?? "").trim();
      setResult(
        await onboard.mutateAsync({
          company_name: String(values.company_name ?? "").trim(),
          ...(slug ? { slug } : {}),
          template_name: templateName!,
          admin_email: String(values.admin_email ?? "").trim(),
          admin_password: String(values.admin_password ?? ""),
        }),
      );
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to provision the tenant."));
    }
  };

  if (me.data && !canOnboard) {
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Tenant Onboarding</h1>
        <p className="mt-4 text-sm text-ink-muted">
          Provisioning tenants requires the <code>onboarding.tenant.create</code> permission.
        </p>
      </div>
    );
  }

  if (result) {
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Tenant provisioned</h1>
        <div className="mt-6 rounded-card border border-line bg-surface p-4 shadow-card">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <dt className="text-ink-muted">Slug</dt>
            <dd className="text-ink">{result.slug}</dd>
            <dt className="text-ink-muted">Template applied</dt>
            <dd className="text-ink">{result.template_applied}</dd>
            <dt className="text-ink-muted">Tenant ID</dt>
            <dd className="text-ink tabular-nums">{result.tenant_id}</dd>
            <dt className="text-ink-muted">Admin user ID</dt>
            <dd className="text-ink tabular-nums">{result.admin_user_id}</dd>
          </dl>
          <h2 className="mt-4 text-sm font-medium text-ink">Instantiated</h2>
          <ul className="mt-1 text-sm text-ink-muted">
            {Object.entries(result.instantiated).map(([kind, count]) => (
              <li key={kind}>
                {kind}: <span className="tabular-nums text-ink">{count}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="mt-4 text-sm text-ink-muted">
          The new tenant's admin can now sign in with the email and password from step 1.
        </p>
        <Link to="/admin" className="mt-4 inline-block text-sm font-medium text-primary hover:underline">
          Back to Admin
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Tenant Onboarding</h1>
      <p className="mt-1 text-sm text-ink-muted">Step {step} of 3 — {step === 1 ? "Company info" : step === 2 ? "Industry template" : "Review & create"}</p>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      {step === 1 && (
        <div className="mt-6">
          <CompanyStep values={values} onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))} onNext={() => setStep(2)} />
        </div>
      )}

      {step === 2 && (
        <div className="mt-6">
          {templates.isPending && <p className="text-sm text-ink-muted">Loading templates…</p>}
          {templates.isError && (
            <p role="alert" className="rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
              {getErrorMessage(templates.error, "Unable to load the template catalog.")}
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            {(templates.data ?? []).map((template) => (
              <button
                key={template.name}
                type="button"
                onClick={() => setTemplateName(template.name)}
                aria-pressed={templateName === template.name}
                className={`rounded-card border bg-surface p-4 text-left shadow-card transition-colors duration-150 hover:border-primary ${
                  templateName === template.name ? "border-primary bg-primary-tint/30" : "border-line"
                }`}
              >
                <span className="block text-sm font-medium text-ink">{template.display_name}</span>
                <span className="mt-0.5 block text-xs text-ink-muted">{template.description}</span>
                <span className="mt-2 block text-xs text-ink-faint">
                  Modules: {Object.entries(template.modules).filter(([, on]) => on).map(([key]) => key).join(", ")}
                </span>
              </button>
            ))}
          </div>
          <div className="mt-6 flex items-center gap-3">
            <button
              type="button"
              disabled={templateName === null}
              onClick={() => setStep(3)}
              className="btn-ink"
            >
              Next: review
            </button>
            <button type="button" onClick={() => setStep(1)} className="text-sm font-medium text-ink-muted hover:text-ink">
              Back
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="mt-6">
          <div className="rounded-card border border-line bg-surface p-4 shadow-card">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <dt className="text-ink-muted">Company</dt>
              <dd className="text-ink">{String(values.company_name ?? "")}</dd>
              <dt className="text-ink-muted">Slug</dt>
              <dd className="text-ink">{String(values.slug ?? "").trim() || "(derived from company name)"}</dd>
              <dt className="text-ink-muted">Admin email</dt>
              <dd className="text-ink">{String(values.admin_email ?? "")}</dd>
              <dt className="text-ink-muted">Template</dt>
              <dd className="text-ink">{chosen?.display_name ?? templateName}</dd>
            </dl>
          </div>
          <p className="mt-3 text-xs text-ink-muted">
            Creating the tenant instantiates the template's chart of accounts, tax codes, currencies,
            units of measure and number sequences in one transaction.
          </p>
          <div className="mt-6 flex items-center gap-3">
            <button
              type="button"
              disabled={onboard.isPending}
              onClick={() => void submit()}
              className="btn-ink"
            >
              {onboard.isPending ? "Provisioning…" : "Create tenant"}
            </button>
            <button type="button" onClick={() => setStep(2)} className="text-sm font-medium text-ink-muted hover:text-ink">
              Back
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
