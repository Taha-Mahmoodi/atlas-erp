/**
 * Create or edit an account (STRUCTURE §4: modules/finance/pages/AccountFormPage.tsx). Edit
 * mode is entered via `/finance/accounts/$accountId`; create mode via `/finance/accounts/new`.
 * code and account_type are immutable after creation (backend contract) — disabled, not hidden,
 * so the value stays visible for context.
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import {
  useAccount,
  useAccountGroups,
  useCreateAccount,
  useUpdateAccount,
} from "@/modules/finance/hooks";
import { ACCOUNT_TYPES } from "@/modules/finance/types";
import type { Account, AccountCreate, AccountUpdate } from "@/modules/finance/types";

function fieldsFor(isEdit: boolean, groupOptions: { value: string; label: string }[]): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    {
      name: "account_type",
      label: "Type",
      type: "select",
      required: true,
      disabled: isEdit,
      options: ACCOUNT_TYPES.map((type) => ({ value: type, label: type })),
      span: 1,
    },
    {
      name: "normal_balance",
      label: "Normal balance",
      type: "select",
      options: [
        { value: "DEBIT", label: "Debit" },
        { value: "CREDIT", label: "Credit" },
      ],
      help: "Defaults from the account type when left unset.",
      span: 1,
    },
    {
      name: "account_group_id",
      label: "Account group",
      type: "select",
      options: groupOptions,
      span: 1,
    },
    {
      name: "cash_flow_category",
      label: "Cash-flow category",
      type: "select",
      options: [
        { value: "OPERATING", label: "Operating" },
        { value: "INVESTING", label: "Investing" },
        { value: "FINANCING", label: "Financing" },
      ],
      span: 1,
    },
    { name: "currency_code", label: "Currency (if monetary)", type: "text", placeholder: "EUR", span: 1 },
    { name: "is_postable", label: "Postable (journal lines may post to it)", type: "checkbox", span: 2 },
    { name: "is_active", label: "Active", type: "checkbox", span: 2 },
    { name: "is_monetary", label: "Monetary (revalued at period end if foreign)", type: "checkbox", span: 2 },
    { name: "is_cash_equivalent", label: "Cash equivalent", type: "checkbox", span: 2 },
  ];
}

export function AccountFormPage() {
  const { accountId } = useParams({ strict: false });
  const isEdit = accountId !== undefined;
  const navigate = useNavigate();

  const account = useAccount(accountId);
  const groups = useAccountGroups();
  const createAccount = useCreateAccount();
  const updateAccount = useUpdateAccount(accountId ?? "");

  const [values, setValues] = useState<FormValues>({ is_postable: true, is_active: true });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (account.data) {
      setValues({
        code: account.data.code,
        name: account.data.name,
        account_type: account.data.account_type,
        normal_balance: account.data.normal_balance,
        account_group_id: account.data.account_group_id ?? "",
        cash_flow_category: account.data.cash_flow_category ?? "",
        currency_code: account.data.currency_code ?? "",
        is_postable: account.data.is_postable,
        is_active: account.data.is_active,
        is_monetary: account.data.is_monetary,
        is_cash_equivalent: account.data.is_cash_equivalent,
      });
    }
  }, [account.data]);

  const groupOptions = (groups.data?.items ?? []).map((group) => ({
    value: group.id,
    label: `${group.code} — ${group.name}`,
  }));

  const submit = async () => {
    setError(null);
    try {
      const normalBalance = values.normal_balance
        ? { normal_balance: values.normal_balance as "DEBIT" | "CREDIT" }
        : {};
      if (isEdit) {
        const payload: AccountUpdate = {
          name: String(values.name ?? ""),
          ...normalBalance,
          account_group_id: values.account_group_id ? String(values.account_group_id) : null,
          cash_flow_category: values.cash_flow_category
            ? (values.cash_flow_category as Account["cash_flow_category"])
            : null,
          currency_code: values.currency_code ? String(values.currency_code) : null,
          is_postable: Boolean(values.is_postable),
          is_active: Boolean(values.is_active),
          is_monetary: Boolean(values.is_monetary),
          is_cash_equivalent: Boolean(values.is_cash_equivalent),
        };
        await updateAccount.mutateAsync(payload);
        void navigate({ to: "/finance/accounts/$accountId", params: { accountId: accountId! } });
      } else {
        const payload: AccountCreate = {
          code: String(values.code ?? ""),
          name: String(values.name ?? ""),
          account_type: values.account_type as AccountCreate["account_type"],
          ...normalBalance,
          account_group_id: values.account_group_id ? String(values.account_group_id) : null,
          cash_flow_category: values.cash_flow_category
            ? (values.cash_flow_category as Account["cash_flow_category"])
            : null,
          currency_code: values.currency_code ? String(values.currency_code) : null,
          is_postable: Boolean(values.is_postable),
          is_active: Boolean(values.is_active),
          is_monetary: Boolean(values.is_monetary),
          is_cash_equivalent: Boolean(values.is_cash_equivalent),
        };
        const created = await createAccount.mutateAsync(payload);
        void navigate({ to: "/finance/accounts/$accountId", params: { accountId: created.id } });
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to save the account.");
    }
  };

  const busy = createAccount.isPending || updateAccount.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance/accounts">Chart of Accounts</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit account" : "New account"}</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {isEdit ? "Edit account" : "New account"}
        </h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, [{ value: "", label: "None" }, ...groupOptions])}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create account"}
          busy={busy}
        />
      </div>
    </div>
  );
}
