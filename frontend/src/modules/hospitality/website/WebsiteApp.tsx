/**
 * The property's own website — the guest-facing surface of the hospitality module.
 *
 * It is a SEPARATE ORIGIN from the Atlas console on purpose. The credential it talks to Atlas with
 * is a machine API key (D-069), attached by its nginx and never present in this bundle; a page
 * served from the console's origin would either have to hold that key in the browser or make a
 * guest log in, and both are wrong. See `website-nginx.conf.template` for the allowlist.
 *
 * Four reads assemble the menu, and their cache policies are the API's, not this file's: menu
 * structure and price are 60 s fresh, the 86 board is revalidated on every request. React Query's
 * stale times below mirror that contract rather than inventing a second one.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { Page } from "@/lib/apiClient";
import type {
  MenuAvailabilityBoard,
  MenuItem,
  MenuPlacement,
  MenuSection,
} from "@/modules/hospitality/types";
import { BookingPanel } from "@/modules/hospitality/website/BookingPanel";
import { guestGet } from "@/modules/hospitality/website/guestApi";
import { MenuBoard } from "@/modules/hospitality/website/MenuBoard";
import type { MenuDish } from "@/modules/hospitality/website/menu";
import { buildMenu } from "@/modules/hospitality/website/menu";
import type { CartLine } from "@/modules/hospitality/website/OrderPanel";
import { OrderPanel } from "@/modules/hospitality/website/OrderPanel";

const MINUTE = 60_000;

export function WebsiteApp() {
  const [cart, setCart] = useState<CartLine[]>([]);

  const menu = useQuery({
    queryKey: ["menu"],
    queryFn: () => guestGet<Page<MenuItem>>("/menu", { limit: "200" }),
    staleTime: MINUTE,
  });
  const sections = useQuery({
    queryKey: ["menu-sections"],
    queryFn: () => guestGet<MenuSection[]>("/menu/sections"),
    staleTime: 10 * MINUTE, // a manager rewrites the menu; it does not change during service
  });
  const placements = useQuery({
    queryKey: ["menu-placements"],
    queryFn: () => guestGet<{ items: MenuPlacement[] }>("/menu/placements"),
    staleTime: 10 * MINUTE,
  });
  const availability = useQuery({
    queryKey: ["menu-availability"],
    queryFn: () => guestGet<MenuAvailabilityBoard>("/menu/availability"),
    // The one read that must never be served stale — a stale "available" sells a dish that is
    // gone. The endpoint revalidates on every request; this keeps the page honest between them.
    staleTime: 0,
    refetchInterval: MINUTE,
  });

  const loading = menu.isPending || sections.isPending || placements.isPending;
  const failed = menu.isError || sections.isError || placements.isError;
  const courses =
    menu.data && sections.data && placements.data
      ? buildMenu(
          menu.data.items,
          sections.data,
          placements.data.items,
          // Fail OPEN: if the board itself cannot be read the menu is still served, which is the
          // policy its own `stale-if-error` window encodes — showing an unavailable dish is a
          // normal restaurant apology, showing nothing is not.
          availability.data?.items ?? [],
        )
      : [];

  function add(dish: MenuDish) {
    setCart((lines) => {
      const existing = lines.find((line) => line.item_id === dish.item_id);
      if (existing) {
        return lines.map((line) =>
          line.item_id === dish.item_id ? { ...line, quantity: line.quantity + 1 } : line,
        );
      }
      // `orderable` gates the button, so a null price cannot reach here.
      return [...lines, { item_id: dish.item_id, name: dish.name, price: dish.price ?? "0", quantity: 1 }];
    });
  }

  function changeQuantity(itemId: string, delta: number) {
    setCart((lines) =>
      lines
        .map((line) => (line.item_id === itemId ? { ...line, quantity: line.quantity + delta } : line))
        .filter((line) => line.quantity > 0),
    );
  }

  return (
    <div className="site">
      <header className="masthead">
        <h1>Lantern &amp; Larder</h1>
        <p>Whatever the market gave us that morning, cooked to order.</p>
      </header>

      <div className="columns">
        <main>
          <h2 className="visually-hidden">Menu</h2>
          {loading ? <p className="muted">Setting the table…</p> : null}
          {failed ? (
            <p className="notice" role="alert">
              We cannot show tonight&rsquo;s menu just now. Please call the house.
            </p>
          ) : null}
          {!loading && !failed ? <MenuBoard courses={courses} onAdd={add} /> : null}
        </main>

        <aside className="aside">
          <OrderPanel
            lines={cart}
            onChangeQuantity={changeQuantity}
            onClear={() => setCart([])}
            onOrdered={() => {
              setCart([]);
              // An order burns countdowns and can 86 a dish outright — re-read the board rather
              // than leaving the next guest looking at the state before this order.
              void availability.refetch();
            }}
          />
          <BookingPanel />
        </aside>
      </div>
    </div>
  );
}
