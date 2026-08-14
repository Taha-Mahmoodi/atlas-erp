/**
 * Create or edit a customer (STRUCTURE §4). Edit mode via `/sales/customers/$customerId`;
 * create via `/sales/customers/new`. `customer_code` is immutable after creation. Mirrors
 * procurement's VendorFormPage; no approved-items equivalent exists for customers (any
 * customer can be priced/ordered any item, gated only by whether a price list matches).
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import {
  useCreateCustomer,
  useCustomer,
  useCustomerGroupOptions,
  useUpdateCustomer,
} from "@/modules/sales/hooks";
import type { CustomerCreate, CustomerStatus, CustomerUpdate } from "@/modules/sales/types";

function fieldsFor(isEdit: boolean, groupOptions: { value: string; label: string }[]): FieldDef[] {
  return [
    { name: "customer_code", label: "Customer code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    { name: "default_currency_code", label: "Default currency", type: "text", required: true, span: 1 },
    { name: "payment_terms_days", label: "Payment terms (days)", type: "number", span: 1 },
    { name: "credit_limit", label: "Credit limit", type: "number", step: "0.01", span: 1 },
    { name: "customer_group_id", label: "Customer group", type: "select", options: groupOptions, span: 1 },
    {
      name: "status",
      label: "Status",
      type: "select",
      options: [
        { value: "ACTIVE", label: "Active" },
        { value: "BLOCKED", label: "Blocked" },
        { value: "INACTIVE", label: "Inactive" },
      ],
      span: 1,
    },
    { name: "tax_reference", label: "Tax reference", type: "text", span: 1 },
    { name: "email", label: "Email", type: "text", span: 1 },
    { name: "phone", label: "Phone", type: "text", span: 1 },
    { name: "address", label: "Address", type: "textarea", span: 2 },
    { name: "notes", label: "Notes", type: "textarea", span: 2 },
  ];
}

export function CustomerFormPage() {
  const { customerId } = useParams({ strict: false });
  const isEdit = customerId !== undefined;
  const navigate = useNavigate();

  const customer = useCustomer(customerId);
  const groups = useCustomerGroupOptions();
  const createCustomer = useCreateCustomer();
  const updateCustomer = useUpdateCustomer(customerId ?? "");

  const [values, setValues] = useState<FormValues>({ status: "ACTIVE", payment_terms_days: "30", credit_limit: "0" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (customer.data) {
      setValues({
        customer_code: customer.data.customer_code,
        name: customer.data.name,
        default_currency_code: customer.data.default_currency_code,
        payment_terms_days: String(customer.data.payment_terms_days),
        credit_limit: customer.data.credit_limit,
        customer_group_id: customer.data.customer_group_id ?? "",
        status: customer.data.status,
        tax_reference: customer.data.tax_reference ?? "",
        email: customer.data.email ?? "",
        phone: customer.data.phone ?? "",
        address: customer.data.address ?? "",
        notes: customer.data.notes ?? "",
      });
    }
  }, [customer.data]);

  const groupOptions = (groups.data?.items ?? []).map((group) => ({
    value: group.id,
    label: `${group.code} — ${group.name}`,
  }));

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        default_currency_code: String(values.default_currency_code ?? "").toUpperCase(),
        payment_terms_days: Number(values.payment_terms_days ?? 30),
        credit_limit: String(values.credit_limit ?? "0"),
        customer_group_id: values.customer_group_id ? String(values.customer_group_id) : null,
        status: values.status as CustomerStatus,
        tax_reference: values.tax_reference ? String(values.tax_reference) : null,
        email: values.email ? String(values.email) : null,
        phone: values.phone ? String(values.phone) : null,
        address: values.address ? String(values.address) : null,
        notes: values.notes ? String(values.notes) : null,
      };
      if (isEdit) {
        const payload: CustomerUpdate = shared;
        await updateCustomer.mutateAsync(payload);
      } else {
        const payload: CustomerCreate = { ...shared, customer_code: String(values.customer_code ?? "") };
        const created = await createCustomer.mutateAsync(payload);
        void navigate({ to: "/sales/customers/$customerId", params: { customerId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the customer."));
    }
  };

  const busy = createCustomer.isPending || updateCustomer.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/sales/customers">Customers</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit customer" : "New customer"}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">
            {isEdit ? "Edit customer" : "New customer"}
          </h1>
        </div>
      </header>
      {error && (
        <p role="alert" className="mb-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, groupOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create customer"}
          busy={busy}
        />
      </div>
    </div>
  );
}
