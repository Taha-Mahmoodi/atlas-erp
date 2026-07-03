/**
 * The one unauthenticated screen (PLAN 15.3). Centered card on canvas — the single
 * restrained moment of brand before the dense product UI takes over.
 */

import { useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { login } from "@/lib/auth";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";

const FIELDS: FieldDef[] = [
  { name: "tenant_slug", label: "Company", type: "text", required: true, placeholder: "acme" },
  { name: "email", label: "Email", type: "text", required: true, placeholder: "you@company.com" },
  { name: "password", label: "Password", type: "password", required: true },
];

export function LoginPage() {
  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      await login({
        tenant_slug: String(values.tenant_slug ?? ""),
        email: String(values.email ?? ""),
        password: String(values.password ?? ""),
      });
      // AuthGate re-renders into the app shell once the session store flips — no navigation
      // call needed here.
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to sign in. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-4">
      <div className="w-full max-w-sm rounded-card border border-line bg-surface p-8 shadow-card">
        <h1 className="text-xl font-semibold text-ink">Atlas ERP</h1>
        <p className="mt-1 text-sm text-ink-muted">Sign in to continue.</p>
        {error && (
          <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}
        <div className="mt-6">
          <FormBuilder
            fields={FIELDS}
            values={values}
            onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
            onSubmit={submit}
            submitLabel="Sign in"
            busy={busy}
            columns={1}
          />
        </div>
      </div>
    </main>
  );
}
