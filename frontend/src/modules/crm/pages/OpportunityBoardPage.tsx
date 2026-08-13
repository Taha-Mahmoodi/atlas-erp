/**
 * The opportunity pipeline board (STRUCTURE §4, D-057): the design-system Kanban (PLAN 15.2)
 * over the bounded kanban endpoint. The stage IS the column; dragging a card (or its keyboard
 * move menu) calls move-stage — the server owns the transition rules, so an illegal move (e.g.
 * out of WON/LOST) just surfaces its 422 here and the board stays authoritative.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatPercent } from "@/lib/format";
import { useMe } from "@/lib/session";
import { Kanban, type KanbanColumn } from "@/components/Kanban";
import { useKanbanBoard, useMoveOpportunityStage } from "@/modules/crm/hooks";
import type { Opportunity, OpportunityStage } from "@/modules/crm/types";

const STAGE_LABEL: Record<OpportunityStage, string> = {
  PROSPECTING: "Prospecting",
  QUALIFICATION: "Qualification",
  PROPOSAL: "Proposal",
  NEGOTIATION: "Negotiation",
  WON: "Won",
  LOST: "Lost",
};

function Card({ opportunity }: { opportunity: Opportunity }) {
  return (
    <Link
      to="/crm/opportunities/$opportunityId"
      params={{ opportunityId: opportunity.id }}
      className="block pr-4"
    >
      <span className="block text-[11px] text-ink-muted">{opportunity.opportunity_number}</span>
      <span className="block font-medium text-ink">{opportunity.name}</span>
      <span className="block text-xs text-ink-muted">{opportunity.company_name}</span>
      <span className="mt-1 block text-xs tabular-nums text-ink">
        {formatMoney(opportunity.estimated_value, opportunity.currency_code)}
        {opportunity.probability_percent !== null && (
          <span className="text-ink-muted"> · {formatPercent(opportunity.probability_percent)}</span>
        )}
      </span>
    </Link>
  );
}

export function OpportunityBoardPage() {
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canManage = permissions.includes("crm.opportunity.manage");

  const board = useKanbanBoard();
  const moveStage = useMoveOpportunityStage();
  const [error, setError] = useState<string | null>(null);

  // Each card carries its own currency; a column total over mixed currencies is displayed in
  // the first card's currency (single-currency tenants — the common case — are always exact).
  const columns: KanbanColumn<Opportunity>[] = (board.data?.columns ?? []).map((column) => ({
    key: column.stage,
    title:
      column.count > 0
        ? `${STAGE_LABEL[column.stage]} · ${formatMoney(
            column.total_estimated_value,
            column.opportunities[0]?.currency_code ?? "—",
          )}`
        : STAGE_LABEL[column.stage],
    items: column.opportunities,
  }));

  const onItemMove = (itemKey: string, _fromColumn: string, toColumn: string) => {
    setError(null);
    moveStage.mutate(
      { opportunityId: itemKey, stage: toColumn as OpportunityStage },
      { onError: (caught) => setError(getErrorMessage(caught, "Unable to move the opportunity.")) },
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Pipeline</h1>
        {canManage && (
          <Link
            to="/crm/opportunities/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New opportunity
          </Link>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6">
        {board.isPending ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : (
          <Kanban
            columns={columns}
            itemKey={(opportunity) => opportunity.id}
            renderItem={(opportunity) => <Card opportunity={opportunity} />}
            {...(canManage ? { onItemMove } : {})}
            emptyHint="No deals"
          />
        )}
      </div>
    </div>
  );
}
