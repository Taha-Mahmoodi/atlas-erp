/**
 * The lead workbench (STRUCTURE §4): facts, lifecycle actions gated on status (qualify from
 * NEW/CONTACTED, disqualify from any open status, convert only when QUALIFIED — the service
 * rules), and the activity timeline. Convert navigates to the created opportunity.
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { ActivityTimeline } from "@/modules/crm/components/ActivityTimeline";
import { useConvertLead, useDisqualifyLead, useLead, useQualifyLead } from "@/modules/crm/hooks";
import { LeadStatusChip } from "@/modules/crm/pages/LeadListPage";

export function LeadDetailPage() {
  const { leadId } = useParams({ strict: false });
  const navigate = useNavigate();
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canManage = permissions.includes("crm.lead.manage");
  const canManageActivities = permissions.includes("crm.activity.manage");

  const lead = useLead(leadId);
  const qualify = useQualifyLead(leadId ?? "");
  const disqualify = useDisqualifyLead(leadId ?? "");
  const convert = useConvertLead(leadId ?? "");

  const [error, setError] = useState<string | null>(null);

  if (lead.isPending || !lead.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = lead.data;
  const canQualify = data.status === "NEW" || data.status === "CONTACTED";
  const canDisqualify = canQualify || data.status === "QUALIFIED";
  const canConvert = data.status === "QUALIFIED";

  const run = async (action: () => Promise<unknown>, failure: string) => {
    setError(null);
    try {
      await action();
    } catch (caught) {
      setError(getErrorMessage(caught, failure));
    }
  };

  const doConvert = () =>
    run(async () => {
      // name/value/currency default from the lead server-side (ConvertLead is all-optional).
      const opportunity = await convert.mutateAsync({});
      void navigate({
        to: "/crm/opportunities/$opportunityId",
        params: { opportunityId: opportunity.id },
      });
    }, "Unable to convert the lead.");

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-3 text-xl font-semibold text-ink">
          {data.lead_number} — {data.company_name}
          <LeadStatusChip status={data.status} />
        </h1>
        {canManage && (
          <div className="flex gap-2">
            {(canQualify || canDisqualify) && (
              <Link
                to="/crm/leads/$leadId/edit"
                params={{ leadId: data.id }}
                className="rounded-control border border-line px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-150 hover:border-primary"
              >
                Edit
              </Link>
            )}
            {canDisqualify && (
              <button
                type="button"
                onClick={() => void run(() => disqualify.mutateAsync(), "Unable to disqualify the lead.")}
                disabled={disqualify.isPending}
                className="rounded-control border border-line px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-150 hover:border-danger hover:text-danger disabled:cursor-not-allowed disabled:opacity-45"
              >
                Disqualify
              </button>
            )}
            {canQualify && (
              <button
                type="button"
                onClick={() => void run(() => qualify.mutateAsync(), "Unable to qualify the lead.")}
                disabled={qualify.isPending}
                className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
              >
                {qualify.isPending ? "Qualifying…" : "Qualify"}
              </button>
            )}
            {canConvert && (
              <button
                type="button"
                onClick={() => void doConvert()}
                disabled={convert.isPending}
                className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
              >
                {convert.isPending ? "Converting…" : "Convert to opportunity"}
              </button>
            )}
          </div>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {data.converted_opportunity_id && (
        <p className="mt-4 rounded-control bg-success-tint px-3 py-2 text-xs text-success">
          Converted —{" "}
          <Link
            to="/crm/opportunities/$opportunityId"
            params={{ opportunityId: data.converted_opportunity_id }}
            className="underline"
          >
            view the opportunity
          </Link>
          .
        </p>
      )}

      <dl className="mt-6 grid grid-cols-4 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Contact</dt>
          <dd className="text-ink">{data.contact_name ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Email</dt>
          <dd className="text-ink">{data.email ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Phone</dt>
          <dd className="text-ink">{data.phone ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Source</dt>
          <dd className="text-ink">{data.source ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Estimated value</dt>
          <dd className="text-ink tabular-nums">
            {data.estimated_value !== null && data.currency_code
              ? formatMoney(data.estimated_value, data.currency_code)
              : "—"}
          </dd>
        </div>
        {data.notes && (
          <div className="col-span-3">
            <dt className="text-xs text-ink-muted">Notes</dt>
            <dd className="text-ink">{data.notes}</dd>
          </div>
        )}
      </dl>

      <div className="mt-8">
        <ActivityTimeline parent={{ lead_id: data.id }} canManage={canManageActivities} />
      </div>
    </div>
  );
}
