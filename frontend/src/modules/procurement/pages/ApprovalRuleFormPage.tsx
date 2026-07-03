/**
 * Create or edit an approval rule (STRUCTURE §4). Edit mode via
 * `/procurement/approval-rules/$ruleId`; create via `/procurement/approval-rules/new`.
 * `document_type` is immutable after creation (it's the rule's identity key alongside
 * currency_code).
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useApprovalRule, useCreateApprovalRule, useUpdateApprovalRule } from "@/modules/procurement/hooks";
import type { ApprovalDocumentType, ApprovalRuleCreate, ApprovalRuleUpdate } from "@/modules/procurement/types";

function fieldsFor(isEdit: boolean): FieldDef[] {
  return [
    {
      name: "document_type",
      label: "Document type",
      type: "select",
      required: true,
      disabled: isEdit,
      options: [
        { value: "REQUISITION", label: "Requisition" },
        { value: "PURCHASE_ORDER", label: "Purchase order" },
      ],
      span: 1,
    },
    { name: "currency_code", label: "Currency", type: "text", required: true, span: 1 },
    { name: "threshold_amount", label: "Threshold amount", type: "number", step: "0.01", required: true, span: 1 },
    { name: "is_active", label: "Active", type: "checkbox", span: 1 },
    { name: "description", label: "Description", type: "textarea", span: 2 },
  ];
}

export function ApprovalRuleFormPage() {
  const { ruleId } = useParams({ strict: false });
  const isEdit = ruleId !== undefined;
  const navigate = useNavigate();

  const rule = useApprovalRule(ruleId);
  const createRule = useCreateApprovalRule();
  const updateRule = useUpdateApprovalRule(ruleId ?? "");

  const [values, setValues] = useState<FormValues>({ is_active: true, currency_code: "USD" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (rule.data) {
      setValues({
        document_type: rule.data.document_type,
        currency_code: rule.data.currency_code,
        threshold_amount: rule.data.threshold_amount,
        is_active: rule.data.is_active,
        description: rule.data.description ?? "",
      });
    }
  }, [rule.data]);

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        currency_code: String(values.currency_code ?? "").toUpperCase(),
        threshold_amount: String(values.threshold_amount ?? "0"),
        is_active: Boolean(values.is_active),
        description: values.description ? String(values.description) : null,
      };
      if (isEdit) {
        const payload: ApprovalRuleUpdate = shared;
        await updateRule.mutateAsync(payload);
        void navigate({ to: "/procurement/approval-rules/$ruleId", params: { ruleId: ruleId! } });
      } else {
        const payload: ApprovalRuleCreate = {
          ...shared,
          document_type: values.document_type as ApprovalDocumentType,
        };
        const created = await createRule.mutateAsync(payload);
        void navigate({ to: "/procurement/approval-rules/$ruleId", params: { ruleId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the approval rule."));
    }
  };

  const busy = createRule.isPending || updateRule.isPending;

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-xl font-semibold text-ink">{isEdit ? "Edit approval rule" : "New approval rule"}</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <FormBuilder
          fields={fieldsFor(isEdit)}
          values={values}
          onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
          onSubmit={() => void submit()}
          submitLabel={isEdit ? "Save changes" : "Create rule"}
          busy={busy}
        />
      </div>
    </div>
  );
}
