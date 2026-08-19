/**
 * The menu as a guest reads it: courses in the property's own running order, each dish with its
 * price, its labels, and — when the kitchen has said something — what it has said.
 *
 * An 86'd dish stays ON the menu, struck through and marked. Hiding it would leave a guest who
 * heard about the sea bass wondering whether they misremembered; a restaurant's own answer is to
 * say "not tonight", which is also what the availability contract's fail-open policy assumes.
 */

import type { MenuCourse, MenuDish } from "@/modules/hospitality/website/menu";
import { remainingPortions } from "@/modules/hospitality/website/menu";

function money(dish: MenuDish): string {
  if (dish.price === null) return "—";
  // Money is a decimal STRING on the wire (D-015); Number() here is presentation only and never
  // feeds a total the guest is charged — the order response's total_amount is authoritative.
  return `${Number(dish.price).toFixed(2)}`;
}

function Dish({ dish, onAdd }: { dish: MenuDish; onAdd: (dish: MenuDish) => void }) {
  const gone = dish.availability?.state === "EIGHTY_SIXED";
  const remaining = remainingPortions(dish);
  return (
    <li className={gone ? "dish is-gone" : "dish"}>
      <div className="dish-main">
        <div className="dish-name">{dish.name}</div>
        {dish.description ? <div className="dish-note">{dish.description}</div> : null}
        <div>
          {dish.tags.map((tag) => (
            <span className="tag" key={tag}>
              {tag}
            </span>
          ))}
          {gone ? (
            <span className="mark-gone">
              {dish.availability?.reason ?? "Not available tonight"}
            </span>
          ) : null}
          {remaining !== null ? (
            <span className="mark-limited">
              {remaining === 1 ? "Last portion" : `${remaining} portions left`}
            </span>
          ) : null}
          {!gone && dish.price === null ? (
            <span className="mark-gone">Ask your server</span>
          ) : null}
        </div>
      </div>
      <div className="dish-price">{money(dish)}</div>
      <button
        type="button"
        className="btn-quiet"
        disabled={!dish.orderable}
        onClick={() => onAdd(dish)}
      >
        Add
        <span className="visually-hidden"> {dish.name} to your order</span>
      </button>
    </li>
  );
}

function Course({ course, onAdd }: { course: MenuCourse; onAdd: (dish: MenuDish) => void }) {
  return (
    <section className="course">
      <h2>{course.section.name}</h2>
      {course.dishes.length > 0 ? (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {course.dishes.map((dish) => (
            <Dish dish={dish} key={dish.item_id} onAdd={onAdd} />
          ))}
        </ul>
      ) : null}
      {course.children.map((child) => (
        <Course course={child} key={child.section.id} onAdd={onAdd} />
      ))}
    </section>
  );
}

export function MenuBoard({
  courses,
  onAdd,
}: {
  courses: MenuCourse[];
  onAdd: (dish: MenuDish) => void;
}) {
  if (courses.length === 0) {
    return <p className="muted">Tonight&rsquo;s menu is being written. Please call the house.</p>;
  }
  return (
    <div>
      {courses.map((course) => (
        <Course course={course} key={course.section.id} onAdd={onAdd} />
      ))}
    </div>
  );
}
