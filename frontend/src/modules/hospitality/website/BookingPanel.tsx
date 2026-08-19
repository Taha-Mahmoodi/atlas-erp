/**
 * Booking a table: a date, a party size, the night's grid, and one instant.
 *
 * The grid comes from Atlas already answered — one boolean per quarter-hour for THIS party size —
 * so nothing here decides whether a slot is bookable. Two things are the site's own job, exactly
 * as the reservation contract draws the line: rendering the UTC instants in the guest's own
 * timezone, and knowing who the guest is. Atlas is handed a name and a way to reach them.
 *
 * A full slot is a normal answer, not an error: the 422 carries the nearest bookable alternatives
 * for the same night, and they are offered rather than swallowed.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { GuestApiError, guestGet, guestPost, newIdempotencyKey } from "@/modules/hospitality/website/guestApi";

interface SlotOffer {
  slot_start: string;
  bookable: boolean;
}
interface AvailabilityRead {
  service_date: string;
  party_size: number;
  slots: SlotOffer[];
}
interface ReservationRead {
  reservation_number: string;
  slot_start: string;
  party_size: number;
}

/** The instants are UTC; a guest reads their own clock. */
const clock = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function BookingPanel() {
  const [serviceDate, setServiceDate] = useState(today);
  const [party, setParty] = useState(2);
  const [slot, setSlot] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [booked, setBooked] = useState<ReservationRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [alternatives, setAlternatives] = useState<string[]>([]);
  const [sending, setSending] = useState(false);

  const grid = useQuery({
    queryKey: ["reservation-availability", serviceDate, party],
    queryFn: () =>
      guestGet<AvailabilityRead>("/reservation-availability", {
        service_date: serviceDate,
        party_size: String(party),
      }),
    // The grid moves as other guests book; nothing is cached across a change of mind.
    staleTime: 0,
    retry: false,
  });

  async function book() {
    if (!slot) return;
    setSending(true);
    setError(null);
    setAlternatives([]);
    try {
      const reservation = await guestPost<ReservationRead>(
        "/table-reservations",
        {
          service_date: serviceDate,
          slot_start: slot,
          party_size: party,
          guest_name: name.trim(),
          guest_contact: contact.trim() || null,
        },
        // A booking is a document with a number; a fresh key per attempt, and a retry of a
        // timed-out submit is the caller pressing again with a new one only because the previous
        // attempt is known to have failed outright (a 409 in-progress is reported, not retried).
        newIdempotencyKey(),
      );
      setBooked(reservation);
      setSlot(null);
      setName("");
      setContact("");
      await grid.refetch();
    } catch (caught) {
      if (caught instanceof GuestApiError && caught.code === "hospitality.slot_full") {
        const offered = caught.details?.alternatives;
        setAlternatives(Array.isArray(offered) ? (offered as string[]) : []);
        setError("That time has just gone.");
      } else if (caught instanceof GuestApiError) {
        setError(caught.message);
      } else {
        setError("We could not reach the house. Please try again.");
      }
      await grid.refetch();
    } finally {
      setSending(false);
    }
  }

  if (booked) {
    return (
      <section className="panel" aria-live="polite">
        <h2>Table booked</h2>
        <p className="hint">
          {booked.reservation_number} — {booked.party_size} at {clock.format(new Date(booked.slot_start))}
        </p>
        <p className="notice notice-good">We have your table. Call the house if your plans change.</p>
        <button type="button" className="btn" onClick={() => setBooked(null)}>
          Book another
        </button>
      </section>
    );
  }

  const slots = grid.data?.slots ?? [];
  return (
    <section className="panel">
      <h2>Book a table</h2>
      <p className="hint">Sittings every fifteen minutes. Times are your own clock.</p>

      <label htmlFor="booking-date">Date</label>
      <input
        id="booking-date"
        type="date"
        value={serviceDate}
        min={today()}
        onChange={(event) => {
          setServiceDate(event.target.value);
          setSlot(null);
        }}
      />
      <label htmlFor="booking-party">Party</label>
      <select
        id="booking-party"
        value={party}
        onChange={(event) => {
          setParty(Number(event.target.value));
          setSlot(null);
        }}
      >
        {Array.from({ length: 12 }, (_, index) => index + 1).map((size) => (
          <option key={size} value={size}>
            {size === 1 ? "1 guest" : `${size} guests`}
          </option>
        ))}
      </select>

      <label id="slot-label">Time</label>
      {grid.isPending ? <p className="muted">Looking at the book…</p> : null}
      {grid.isError ? (
        <p className="notice" role="alert">
          {grid.error instanceof GuestApiError
            ? grid.error.message
            : "We could not read the book just now."}
        </p>
      ) : null}
      {!grid.isPending && !grid.isError && slots.every((offer) => !offer.bookable) ? (
        <p className="muted">Nothing free that night. Try another date.</p>
      ) : null}
      <div className="slots" role="group" aria-labelledby="slot-label">
        {slots.map((offer) => (
          <button
            type="button"
            className="slot"
            key={offer.slot_start}
            disabled={!offer.bookable}
            aria-pressed={slot === offer.slot_start}
            onClick={() => setSlot(offer.slot_start)}
          >
            {clock.format(new Date(offer.slot_start))}
          </button>
        ))}
      </div>

      <label htmlFor="booking-name">Name</label>
      <input
        id="booking-name"
        value={name}
        maxLength={200}
        onChange={(event) => setName(event.target.value)}
      />
      <label htmlFor="booking-contact">Phone or email</label>
      <input
        id="booking-contact"
        value={contact}
        maxLength={200}
        onChange={(event) => setContact(event.target.value)}
      />
      <button type="button" className="btn" disabled={!slot || !name.trim() || sending} onClick={book}>
        {sending ? "Holding the table…" : "Book the table"}
      </button>

      {error ? (
        <p className="notice" role="alert">
          {error}
          {alternatives.length > 0 ? (
            <>
              {" "}
              The nearest we have:{" "}
              {alternatives.slice(0, 6).map((instant) => (
                <button
                  type="button"
                  className="btn-quiet"
                  key={instant}
                  style={{ marginRight: "0.3rem" }}
                  onClick={() => {
                    setSlot(instant);
                    setError(null);
                    setAlternatives([]);
                  }}
                >
                  {clock.format(new Date(instant))}
                </button>
              ))}
            </>
          ) : null}
        </p>
      ) : null}
    </section>
  );
}
