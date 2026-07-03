/**
 * Create or edit a fixed asset (STRUCTURE §4). Create via `/finance/assets/new`; edit via
 * `/finance/assets/$assetId/edit` — edits only take effect while status is DRAFT (backend
 * 409s otherwise), so the whole form disables once activated, mirroring how
 * AccountFormPage disables its own immutable-after-create fields.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useAccountOptions, useAsset, useCreateAsset, useUpdateAsset } from "@/modules/finance/hooks";
import type { AssetCreate, AssetUpdate, DepreciationMethod } from "@/modules/finance/types";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function fieldsFor(
  disabled: boolean,
  isDeclining: boolean,
  assetAccountOptions: { value: string; label: string }[],
  expenseAccountOptions: { value: string; label: string }[],
): FieldDef[] {
  return [
    { name: "name", label: "Name", type: "text", required: true, disabled, span: 1 },
    {
      name: "acquisition_date",
      label: "Acquisition date",
      type: "date",
      required: true,
      disabled,
      span: 1,
    },
    { name: "description", label: "Description", type: "textarea", disabled, span: 2 },
    {
      name: "acquisition_cost",
      label: "Acquisition cost",
      type: "number",
      step: "0.01",
      required: true,
      disabled,
      span: 1,
    },
    {
      name: "salvage_value",
      label: "Salvage value",
      type: "number",
      step: "0.01",
      disabled,
      span: 1,
    },
    {
      name: "useful_life_months",
      label: "Useful life (months)",
      type: "number",
      required: true,
      disabled,
      span: 1,
    },
    {
      name: "depreciation_method",
      label: "Depreciation method",
      type: "select",
      required: true,
      disabled,
      options: [
        { value: "STRAIGHT_LINE", label: "Straight line" },
        { value: "DECLINING_BALANCE", label: "Declining balance" },
      ],
      span: 1,
    },
    ...(isDeclining
      ? ([
          {
            name: "declining_rate_percent",
            label: "Declining rate (% per year)",
            type: "number",
            step: "0.01",
            required: true,
            disabled,
            span: 1,
          },
        ] as FieldDef[])
      : []),
    {
      name: "asset_account_id",
      label: "Asset account",
      type: "select",
      required: true,
      disabled,
      options: assetAccountOptions,
      span: 1,
    },
    {
      name: "accumulated_depreciation_account_id",
      label: "Accumulated depreciation account",
      type: "select",
      required: true,
      disabled,
      options: assetAccountOptions,
      span: 1,
    },
    {
      name: "depreciation_expense_account_id",
      label: "Depreciation expense account",
      type: "select",
      required: true,
      disabled,
      options: expenseAccountOptions,
      span: 1,
    },
  ];
}

export function AssetFormPage() {
  const { assetId } = useParams({ strict: false });
  const isEdit = assetId !== undefined;
  const navigate = useNavigate();

  const asset = useAsset(assetId);
  const accounts = useAccountOptions();
  const createAsset = useCreateAsset();
  const updateAsset = useUpdateAsset(assetId ?? "");

  const [values, setValues] = useState<FormValues>({
    acquisition_date: today(),
    depreciation_method: "STRAIGHT_LINE",
    salvage_value: "0",
    currency_code: "USD",
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (asset.data) {
      setValues({
        name: asset.data.name,
        description: asset.data.description ?? "",
        acquisition_date: asset.data.acquisition_date,
        acquisition_cost: asset.data.acquisition_cost,
        salvage_value: asset.data.salvage_value,
        useful_life_months: String(asset.data.useful_life_months),
        depreciation_method: asset.data.depreciation_method,
        declining_rate_percent: asset.data.declining_rate_percent ?? "",
        asset_account_id: asset.data.asset_account_id,
        accumulated_depreciation_account_id: asset.data.accumulated_depreciation_account_id,
        depreciation_expense_account_id: asset.data.depreciation_expense_account_id,
      });
    }
  }, [asset.data]);

  const isDraft = !isEdit || asset.data?.status === "DRAFT";
  const isDeclining = values.depreciation_method === "DECLINING_BALANCE";
  const assetAccountOptions = (accounts.data?.items ?? [])
    .filter((account) => account.account_type === "ASSET")
    .map((account) => ({ value: account.id, label: `${account.code} — ${account.name}` }));
  const expenseAccountOptions = (accounts.data?.items ?? [])
    .filter((account) => account.account_type === "EXPENSE")
    .map((account) => ({ value: account.id, label: `${account.code} — ${account.name}` }));

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        description: values.description ? String(values.description) : null,
        acquisition_date: String(values.acquisition_date ?? ""),
        acquisition_cost: String(values.acquisition_cost ?? ""),
        salvage_value: String(values.salvage_value ?? "0"),
        useful_life_months: Number(values.useful_life_months ?? 0),
        depreciation_method: values.depreciation_method as DepreciationMethod,
        ...(isDeclining
          ? { declining_rate_percent: String(values.declining_rate_percent ?? "") }
          : { declining_rate_percent: null }),
        asset_account_id: String(values.asset_account_id ?? ""),
        accumulated_depreciation_account_id: String(values.accumulated_depreciation_account_id ?? ""),
        depreciation_expense_account_id: String(values.depreciation_expense_account_id ?? ""),
      };
      if (isEdit) {
        const payload: AssetUpdate = shared;
        await updateAsset.mutateAsync(payload);
        void navigate({ to: "/finance/assets/$assetId", params: { assetId: assetId! } });
      } else {
        const payload: AssetCreate = { ...shared, currency_code: String(values.currency_code ?? "USD") };
        const created = await createAsset.mutateAsync(payload);
        void navigate({ to: "/finance/assets/$assetId", params: { assetId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the asset."));
    }
  };

  const busy = createAsset.isPending || updateAsset.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold text-ink">{isEdit ? "Edit asset" : "New asset"}</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {isEdit && !isDraft && (
        <p className="mt-4 rounded-control bg-warn-tint px-3 py-2 text-xs text-warn">
          This asset is active — only draft assets can be edited.
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(!isDraft, isDeclining, assetAccountOptions, expenseAccountOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create asset"}
          busy={busy || !isDraft}
        />
      </div>
    </div>
  );
}
