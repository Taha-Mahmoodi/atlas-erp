/**
 * Create a user in the caller's tenant (STRUCTURE §4). The backend hashes the password
 * with argon2id (D-008); roles are assigned afterwards on the user's detail page.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateUser } from "@/modules/admin/hooks";

const FIELDS: FieldDef[] = [
  { name: "email", label: "Email", type: "text", required: true, span: 2 },
  { name: "full_name", label: "Full name", type: "text", span: 2 },
  { name: "password", label: "Password", type: "password", required: true, span: 2, help: "At least 8 characters." },
];

export function UserFormPage() {
  const navigate = useNavigate();
  const createUser = useCreateUser();
  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    try {
      const fullName = String(values.full_name ?? "").trim();
      const created = await createUser.mutateAsync({
        email: String(values.email ?? "").trim(),
        password: String(values.password ?? ""),
        ...(fullName ? { full_name: fullName } : {}),
      });
      void navigate({ to: "/admin/users/$userId", params: { userId: created.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the user."));
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <h1 className="text-xl font-semibold text-ink">New user</h1>
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
          onSubmit={() => void submit()}
          submitLabel="Create user"
          busy={createUser.isPending}
          columns={1}
        />
      </div>
    </div>
  );
}
