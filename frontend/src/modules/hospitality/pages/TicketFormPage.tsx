/**
 * Open a check (STRUCTURE §4). Deliberately minimal: a server opens a ticket when the table is
 * seated and takes the order afterwards, so an empty OPEN check is the normal first state rather
 * than an error — dishes are added on the detail page (the StockCount two-step shape).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { FormBuilder, type FieldDef, type FormValues } from "@/components/FormBuilder";
import { useCreateTicket } from "@/modules/hospitality/hooks";

// NO service-date field (#207). A restaurant sells today: a check dated yesterday or next week is
// always a mistake, and it was the trigger for #209, where one backdated check destroyed the whole
// ticket number sequence. The API does not accept a service date either — hiding the field here
// alone would leave the bypass open. Backdating is a correction, not service-floor work; if it is
// ever needed it belongs behind its own permission, not on the form every server uses.
const FIELDS: FieldDef[] = [
  { name: "table_code", label: "Table", type: "text", placeholder: "12" },
  { name: "guest_count", label: "Guests", type: "number" },
  { name: "notes", label: "Notes", type: "textarea", span: 2 },
];

export function TicketFormPage() {
  const navigate = useNavigate();
  const createTicket = useCreateTicket();
  const [values, setValues] = useState<FormValues>({});
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    const tableCode = String(values.table_code ?? "").trim();
    const guests = String(values.guest_count ?? "").trim();
    const notes = String(values.notes ?? "").trim();
    try {
      const created = await createTicket.mutateAsync({
        table_code: tableCode || null,
        guest_count: guests ? Number(guests) : null,
        notes: notes || null,
      });
      void navigate({
        to: "/hospitality/tickets/$ticketId",
        params: { ticketId: created.id },
      });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to open the check."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hospitality/tickets" className="hover:underline">
            Tickets
          </Link>{" "}
          / <span className="text-ink">New ticket</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">New ticket</h1>
      </header>

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
          submitLabel="Open check"
          busy={createTicket.isPending}
          footer={
            <Link to="/hospitality/tickets" className="btn-chip">
              Cancel
            </Link>
          }
        />
      </div>
    </div>
  );
}
