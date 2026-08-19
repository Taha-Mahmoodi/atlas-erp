/**
 * The guest's order: a running list, a submit, and the ONE number that is real.
 *
 * The five rules the website contract sets are all visible here:
 *
 * 1. The subtotal shown while ordering is labelled an estimate, because it is computed from a menu
 *    that may be 60 s old. `total_amount` from the 201 is what the guest is told they owe.
 * 2. No price is sent — the body carries item, quantity, seat and note, and nothing else.
 * 3. A 409 `idempotency.in_progress` keeps the SAME key and asks the guest to try again; minting a
 *    new one is how the duplicate order this mechanism prevents gets created.
 * 4. The key is minted per SUBMIT ATTEMPT and cleared only once an order is accepted, so a
 *    re-render never mints a second one mid-flight.
 * 5. The confirmation says the kitchen has the check — never that stock has moved, which is a
 *    background job that has not run yet.
 */

import { useRef, useState } from "react";

import { GuestApiError, guestPost, newIdempotencyKey } from "@/modules/hospitality/website/guestApi";

export interface CartLine {
  item_id: string;
  name: string;
  price: string;
  quantity: number;
}

interface AcceptedOrder {
  ticket_number: string;
  total_amount: string;
  currency_code: string | null;
}

export function OrderPanel({
  lines,
  onChangeQuantity,
  onClear,
  onOrdered,
}: {
  lines: CartLine[];
  onChangeQuantity: (itemId: string, delta: number) => void;
  onClear: () => void;
  onOrdered: () => void;
}) {
  const [table, setTable] = useState("");
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<AcceptedOrder | null>(null);
  const idempotencyKey = useRef<string | null>(null);

  const estimate = lines.reduce((sum, line) => sum + Number(line.price) * line.quantity, 0);

  async function submit() {
    idempotencyKey.current ??= newIdempotencyKey(); // reused by every retry of THIS order
    setSending(true);
    setError(null);
    try {
      const order = await guestPost<AcceptedOrder>(
        "/orders",
        {
          table_code: table.trim() || null,
          guest_count: null,
          notes: note.trim() || null,
          lines: lines.map((line) => ({ item_id: line.item_id, quantity: String(line.quantity) })),
        },
        idempotencyKey.current,
      );
      idempotencyKey.current = null;
      setAccepted(order);
      setTable("");
      setNote("");
      onOrdered();
    } catch (caught) {
      setError(messageFor(caught));
    } finally {
      setSending(false);
    }
  }

  if (accepted) {
    return (
      <section className="panel" aria-live="polite">
        <h2>Order {accepted.ticket_number}</h2>
        <p className="hint">The kitchen has your check.</p>
        <div className="total">
          <span>Total</span>
          <span>
            {Number(accepted.total_amount).toFixed(2)} {accepted.currency_code ?? ""}
          </span>
        </div>
        <button type="button" className="btn" onClick={() => setAccepted(null)}>
          Order something else
        </button>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Your order</h2>
      <p className="hint">Everything is prepared to order; the kitchen sees it the moment you send it.</p>
      {lines.length === 0 ? (
        <p className="muted">Nothing yet — add a dish from the menu.</p>
      ) : (
        <>
          {lines.map((line) => (
            <div className="line" key={line.item_id}>
              <span>
                <button type="button" className="btn-quiet" onClick={() => onChangeQuantity(line.item_id, -1)}>
                  <span aria-hidden="true">−</span>
                  <span className="visually-hidden">One fewer {line.name}</span>
                </button>{" "}
                {line.quantity} × {line.name}{" "}
                <button type="button" className="btn-quiet" onClick={() => onChangeQuantity(line.item_id, 1)}>
                  <span aria-hidden="true">+</span>
                  <span className="visually-hidden">One more {line.name}</span>
                </button>
              </span>
              <span>{(Number(line.price) * line.quantity).toFixed(2)}</span>
            </div>
          ))}
          <div className="total">
            <span>Estimated</span>
            <span>{estimate.toFixed(2)}</span>
          </div>
          <p className="muted">The kitchen prices your order when it arrives; that total is the one you pay.</p>

          <label htmlFor="order-table">Table</label>
          <input
            id="order-table"
            value={table}
            maxLength={20}
            onChange={(event) => setTable(event.target.value)}
            placeholder="e.g. 12"
          />
          <label htmlFor="order-note">Anything we should know</label>
          <textarea
            id="order-note"
            rows={2}
            maxLength={1000}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Allergies, celebrations, a seat by the window"
          />
          <button type="button" className="btn" disabled={sending} onClick={submit}>
            {sending ? "Sending to the kitchen…" : "Send to the kitchen"}
          </button>
          <button type="button" className="btn-quiet" style={{ marginTop: "0.6rem" }} onClick={onClear}>
            Clear
          </button>
        </>
      )}
      {error ? (
        <p className="notice" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

/** Each refusal has a different remedy at the guest's end, so each gets its own sentence. */
function messageFor(caught: unknown): string {
  if (!(caught instanceof GuestApiError)) return "We could not reach the kitchen. Please try again.";
  switch (caught.code) {
    case "hospitality.item_unavailable":
      return "The kitchen has just run out of something on your order. Refresh the menu and try again.";
    case "hospitality.item_not_priced":
      return "One of those is not on tonight's menu. Please ask your server.";
    case "idempotency.in_progress":
      return "We are still sending that order. Give it a moment and press again — it will not be sent twice.";
    default:
      return caught.message;
  }
}
