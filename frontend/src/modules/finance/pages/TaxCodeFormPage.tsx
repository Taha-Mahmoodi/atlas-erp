/**
 * Create or edit a tax code (STRUCTURE §4, PLAN 15.12). Edit via
 * `/finance/tax-codes/$taxCodeId`; create via `/finance/tax-codes/new`. `code` is immutable
 * after creation (posted lines reference it). rate_percent is a percentage string (20 ==
 * 20%, D-015); the payable account collects output (sales) tax, the receivable account
 * input (purchase) tax — each optional so a code wires only its side.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useAccountOptions, useCreateTaxCode, useTaxCode, useUpdateTaxCode } from "@/modules/finance/hooks";
import type { TaxCodeCreate, TaxCodeUpdate } from "@/modules/finance/types";

export function TaxCodeFormPage() {
  const { taxCodeId } = useParams({ strict: false });
  const isEdit = taxCodeId !== undefined;
  const navigate = useNavigate();

  const taxCode = useTaxCode(taxCodeId);
  const accounts = useAccountOptions();
  const createTaxCode = useCreateTaxCode();
  const updateTaxCode = useUpdateTaxCode(taxCodeId ?? "");

  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (taxCode.data) {
      setValues({
        code: taxCode.data.code,
        name: taxCode.data.name,
        rate_percent: taxCode.data.rate_percent,
        jurisdiction: taxCode.data.jurisdiction ?? "",
        is_inclusive: taxCode.data.is_inclusive,
        is_active: taxCode.data.is_active,
        tax_payable_account_id: taxCode.data.tax_payable_account_id ?? "",
        tax_receivable_account_id: taxCode.data.tax_receivable_account_id ?? "",
      });
    }
  }, [taxCode.data]);

  const accountOptions = (accounts.data?.items ?? []).map((account) => ({
    value: account.id,
    label: `${account.code} — ${account.name}`,
  }));

  const fields: FieldDef[] = [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    { name: "rate_percent", label: "Rate (%)", type: "number", required: true, step: "0.01", span: 1 },
    { name: "jurisdiction", label: "Jurisdiction", type: "text", span: 1 },
    { name: "tax_payable_account_id", label: "Tax payable account (output tax)", type: "select", options: accountOptions, span: 1 },
    { name: "tax_receivable_account_id", label: "Tax receivable account (input tax)", type: "select", options: accountOptions, span: 1 },
    { name: "is_inclusive", label: "Prices include this tax", type: "checkbox", span: 1 },
    ...(isEdit ? [{ name: "is_active", label: "Active", type: "checkbox", span: 1 } as FieldDef] : []),
  ];

  const submit = async () => {
    setError(null);
    const jurisdiction = String(values.jurisdiction ?? "").trim();
    const payable = String(values.tax_payable_account_id ?? "");
    const receivable = String(values.tax_receivable_account_id ?? "");
    try {
      if (isEdit) {
        const payload: TaxCodeUpdate = {
          name: String(values.name ?? ""),
          rate_percent: String(values.rate_percent ?? ""),
          jurisdiction: jurisdiction || null,
          is_inclusive: Boolean(values.is_inclusive),
          is_active: Boolean(values.is_active),
          tax_payable_account_id: payable || null,
          tax_receivable_account_id: receivable || null,
        };
        await updateTaxCode.mutateAsync(payload);
      } else {
        const payload: TaxCodeCreate = {
          code: String(values.code ?? "").trim(),
          name: String(values.name ?? ""),
          rate_percent: String(values.rate_percent ?? ""),
          ...(jurisdiction ? { jurisdiction } : {}),
          is_inclusive: Boolean(values.is_inclusive),
          ...(payable ? { tax_payable_account_id: payable } : {}),
          ...(receivable ? { tax_receivable_account_id: receivable } : {}),
        };
        await createTaxCode.mutateAsync(payload);
      }
      void navigate({ to: "/finance/tax-codes" });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the tax code."));
    }
  };

  const busy = createTaxCode.isPending || updateTaxCode.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{isEdit ? "Edit tax code" : "New tax code"}</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fields}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create tax code"}
          busy={busy}
        />
      </div>
    </div>
  );
}
