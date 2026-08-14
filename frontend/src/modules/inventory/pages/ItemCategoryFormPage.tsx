/**
 * Create or edit an item category (STRUCTURE §4). Edit mode via
 * `/inventory/item-categories/$categoryId`; create via `/inventory/item-categories/new`.
 * `code` is immutable after creation (backend contract) — disabled, not hidden, in edit mode.
 * The three GL account links are opaque finance-owned ids (D-029); a STOCKED item's category
 * needs all three wired before its moves can post, but nothing here enforces that client-side
 * — the backend validates at move-creation time, not category-save time.
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useAccountOptions } from "@/modules/finance/hooks";
import {
  useCreateItemCategory,
  useItemCategory,
  useUpdateItemCategory,
} from "@/modules/inventory/hooks";
import type { CostingMethod, ItemCategoryCreate, ItemCategoryUpdate } from "@/modules/inventory/types";

function fieldsFor(isEdit: boolean, accountOptions: { value: string; label: string }[]): FieldDef[] {
  return [
    { name: "code", label: "Code", type: "text", required: true, disabled: isEdit, span: 1 },
    { name: "name", label: "Name", type: "text", required: true, span: 1 },
    {
      name: "default_costing_method",
      label: "Default costing method",
      type: "select",
      required: true,
      options: [
        { value: "MOVING_AVERAGE", label: "Moving average" },
        { value: "FIFO", label: "FIFO" },
      ],
      span: 2,
    },
    {
      name: "inventory_account_id",
      label: "Inventory account",
      type: "select",
      options: accountOptions,
      help: "Required before a stocked item in this category can post moves.",
      span: 2,
    },
    {
      name: "cogs_account_id",
      label: "COGS account",
      type: "select",
      options: accountOptions,
      span: 2,
    },
    {
      name: "price_difference_account_id",
      label: "Price difference account",
      type: "select",
      options: accountOptions,
      span: 2,
    },
  ];
}

export function ItemCategoryFormPage() {
  const { categoryId } = useParams({ strict: false });
  const isEdit = categoryId !== undefined;
  const navigate = useNavigate();

  const category = useItemCategory(categoryId);
  const accounts = useAccountOptions();
  const createCategory = useCreateItemCategory();
  const updateCategory = useUpdateItemCategory(categoryId ?? "");

  const [values, setValues] = useState<FormValues>({ default_costing_method: "MOVING_AVERAGE" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (category.data) {
      setValues({
        code: category.data.code,
        name: category.data.name,
        default_costing_method: category.data.default_costing_method,
        inventory_account_id: category.data.inventory_account_id ?? "",
        cogs_account_id: category.data.cogs_account_id ?? "",
        price_difference_account_id: category.data.price_difference_account_id ?? "",
      });
    }
  }, [category.data]);

  const accountOptions = (accounts.data?.items ?? []).map((account) => ({
    value: account.id,
    label: `${account.code} — ${account.name}`,
  }));

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        name: String(values.name ?? ""),
        default_costing_method: values.default_costing_method as CostingMethod,
        inventory_account_id: values.inventory_account_id ? String(values.inventory_account_id) : null,
        cogs_account_id: values.cogs_account_id ? String(values.cogs_account_id) : null,
        price_difference_account_id: values.price_difference_account_id
          ? String(values.price_difference_account_id)
          : null,
      };
      if (isEdit) {
        const payload: ItemCategoryUpdate = shared;
        await updateCategory.mutateAsync(payload);
        void navigate({ to: "/inventory/item-categories/$categoryId", params: { categoryId: categoryId! } });
      } else {
        const payload: ItemCategoryCreate = { ...shared, code: String(values.code ?? "") };
        const created = await createCategory.mutateAsync(payload);
        void navigate({ to: "/inventory/item-categories/$categoryId", params: { categoryId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the item category."));
    }
  };

  const busy = createCategory.isPending || updateCategory.isPending;

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/inventory/item-categories">Item Categories</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit item category" : "New item category"}</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {isEdit ? "Edit item category" : "New item category"}
        </h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit, accountOptions)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create category"}
          busy={busy}
        />
      </div>
    </div>
  );
}
