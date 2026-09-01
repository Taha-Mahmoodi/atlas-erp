"""THE GATE ON THE GATE: every path that writes room supply locks the row that decides its delta.

Three review rounds of PLAN 20.2 found the same defect three times, one call site further over each
time — a function computing an allotment delta from state it had read WITHOUT a row lock, so two
concurrent requests both computed it and both applied it. A `-m pg` race pins each path that exists
today; this file is what catches the path that does not exist yet, because "the reviewer noticed"
is not a control and the next writer of this counter will not have read the other three.

It is a STATIC gate, in the shape of ``test_tenancy_grep_gate`` (the D-007 precedent) but over the
AST rather than a regex, and it asserts two things:

1. **The census is closed.** The set of functions that call ``allotment.adjust_allotment`` /
   ``adjust_sellable`` / ``apply_allotment_deltas`` is exactly :data:`SUPPLY_WRITERS`. A new writer
   fails here until somebody names it and its deciding row — which is also what keeps the paths ×
   locks table in ``docs/modules/hospitality.md`` and the PR body from outrunning the code.
2. **Each of them takes its lock first.** The declared getter is called with ``for_update=True`` on
   a line ABOVE the allotment call. Line order matters: a lock taken after the counter has been read
   serializes nothing.

What this canNOT see is a lock taken through some spelling it does not know, so the census in (1) is
the part that must stay honest — a writer added without an entry fails, and an entry cannot be added
without naming the row and the getter. The runtime proof that each lock is the RIGHT lock is the
`-m pg` race per path in ``test_room_booking_races.py``; this is the proof that no path is missing
one at all.
"""

import ast
from pathlib import Path

import pytest

_SERVICE = Path(__file__).resolve().parents[3] / "app" / "modules" / "hospitality" / "service"

# The three entry points that move `hsp_room_type_inventory`. `apply_allotment_deltas` is the
# private shape `adjust_allotment` delegates to and is listed so a caller cannot reach the counter
# by skipping the public helper.
_ALLOTMENT_WRITES = frozenset(
    {"adjust_allotment", "adjust_sellable", "apply_allotment_deltas"}
)

# EVERY path in the module that writes `rooms_sold` or `rooms_sellable`, and the row whose state
# decides its delta. `(file, function) -> (getter, what it locks)`.
#
# `rooms_sold` is decided by the RoomReservation being moved: the transition it is allowed to make
# is read off `ROOM_RESERVATION_FLOW` in Python, so two requests moving one booking both pass it
# unless the row is locked (a double-clicked Confirm).
#
# `rooms_sellable` is decided by the Room being changed: the type it is moving OUT of and the
# housekeeping status it is moving out of are both read off the row, so two requests moving one room
# both compute the same move unless the row is locked.
#
# The room TYPE row is locked by `allotment` itself, on both paths, and so is deliberately absent
# here — a caller cannot forget a lock the callee takes.
SUPPLY_WRITERS: dict[tuple[str, str], tuple[str, str]] = {
    ("room_reservations.py", "confirm_room_reservation"): ("get_room_reservation", "the booking"),
    ("room_reservations.py", "cancel_room_reservation"): ("get_room_reservation", "the booking"),
    ("room_reservations.py", "amend_room_reservation"): ("get_room_reservation", "the booking"),
    ("rooms.py", "create_room"): ("", "nothing — the deciding row is the one being inserted"),
    ("rooms.py", "update_room"): ("get_room", "the room"),
    ("rooms.py", "set_housekeeping_status"): ("get_room", "the room"),
}

# The fields `_sellable_rooms` COUNTs over, and therefore the ONLY state whose mutation can change
# what a type can sell. A function that touches one of these MUST also move the counter.
#
# This is the half the first version of this file was missing, and it is the half that matters.
# Censusing the callers of the counter can only ever find a writer that locks WRONGLY; it is
# structurally blind to a path that changes physical supply and never calls the counter at all —
# which is exactly what `create_room` did, found in the fourth review round, after a census that
# advertised itself as the control against a fourth round.
_SUPPLY_STATE = frozenset({"room_type_id", "housekeeping_status"})


def _called_name(node: ast.Call) -> str:
    """The bare function name of a call, whether written ``f()`` or ``module.f()``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _functions(path: Path) -> list[ast.AsyncFunctionDef | ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
    ]


def _writers() -> dict[tuple[str, str], ast.AsyncFunctionDef | ast.FunctionDef]:
    """Every function under ``service/`` that calls into the allotment counter, keyed by
    ``(file, function)``. ``allotment.py`` itself is skipped: it IS the counter."""
    found: dict[tuple[str, str], ast.AsyncFunctionDef | ast.FunctionDef] = {}
    for path in sorted(_SERVICE.glob("*.py")):
        if path.name == "allotment.py":
            continue
        for function in _functions(path):
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
            if any(_called_name(call) in _ALLOTMENT_WRITES for call in calls):
                found[(path.name, function.name)] = function
    return found


def _supply_mutators() -> set[tuple[str, str]]:
    """Every function under ``service/`` that changes what :func:`_sellable_rooms` would COUNT —
    by constructing a ``Room``, by assigning one of :data:`_SUPPLY_STATE`, or by deleting one.

    The inverse census. :func:`_writers` asks "who calls the counter"; this asks "who changes the
    number the counter is supposed to track", and the two sets must be equal. A path in this set but
    not in :data:`SUPPLY_WRITERS` is a silent oversell or under-sell.
    """
    found: set[tuple[str, str]] = set()
    for path in sorted(_SERVICE.glob("*.py")):
        if path.name == "allotment.py":
            continue
        for function in _functions(path):
            for node in ast.walk(function):
                touches = (
                    # `Room(...)` — a new physical room, countable from birth.
                    (isinstance(node, ast.Call) and _called_name(node) == "Room")
                    # `room.room_type_id = ...` / `room.housekeeping_status = ...`
                    or (
                        isinstance(node, ast.Assign)
                        and any(
                            isinstance(target, ast.Attribute) and target.attr in _SUPPLY_STATE
                            for target in node.targets
                        )
                    )
                    # `setattr(room, field, value)` where field is a supply column: the loop shape
                    # `update_room` uses. Conservative — any setattr in a function that also names a
                    # supply column counts, because the field is a variable at parse time.
                    or (
                        isinstance(node, ast.Call)
                        and _called_name(node) == "setattr"
                        and any(
                            isinstance(inner, ast.Constant) and inner.value in _SUPPLY_STATE
                            for inner in ast.walk(function)
                        )
                    )
                    # `delete(Room)` — no such path exists today; this is the guard for the day one
                    # is added. Narrowed to Room on purpose: a bare `delete(...)` also matches the
                    # restaurant's menu and 86-board paths, which touch no room supply.
                    or (
                        isinstance(node, ast.Call)
                        and _called_name(node) == "delete"
                        and any(
                            isinstance(arg, ast.Name) and arg.id == "Room" for arg in node.args
                        )
                    )
                )
                if touches:
                    found.add((path.name, function.name))
                    break
    return found


def test_every_path_that_changes_physical_supply_moves_the_counter() -> None:
    """The inverse census: nothing may change what a type can sell without telling the counter.

    ``_sellable_rooms`` COUNTs ``hsp_rooms`` on ``(tenant_id, room_type_id, housekeeping_status)``,
    so exactly four operations can move that number — INSERT a room, change its type, change its
    condition, DELETE one — and the fourth has no path in this module. Three were hooked; INSERT was
    not, for four review rounds, because the only control was a whitelist of functions that already
    called the counter.
    """
    mutators = _supply_mutators()
    undeclared = sorted(mutators - set(SUPPLY_WRITERS))
    assert not undeclared, (
        "these change what a room type can sell but never move the allotment counter, so nights "
        "materialised before the change keep the old supply forever: "
        + ", ".join(f"{name}:{function}" for name, function in undeclared)
    )


def test_the_census_of_allotment_writers_is_closed() -> None:
    """A new path into the counter fails until it is named here with the row it locks.

    This is the half that catches the defect the review found three times: each round fixed the
    call sites it was given, and the next round found another one. A census that fails on an
    UNKNOWN writer cannot be one call site behind.
    """
    found = set(_writers())
    declared = set(SUPPLY_WRITERS)
    assert found == declared, (
        "the set of functions writing rooms_sold/rooms_sellable has changed.\n"
        f"  undeclared (name it in SUPPLY_WRITERS with the row it locks): "
        f"{sorted(found - declared)}\n"
        f"  declared but gone (delete the entry): {sorted(declared - found)}"
    )


@pytest.mark.parametrize(("where", "getter"), sorted(SUPPLY_WRITERS.items()))
def test_every_allotment_writer_locks_the_row_that_decides_its_delta(
    where: tuple[str, str], getter: tuple[str, str]
) -> None:
    """The declared getter is called with ``for_update=True``, ABOVE the counter call.

    Mutation: drop the ``for_update=True`` from either ``rooms.update_room`` or
    ``rooms.set_housekeeping_status`` (the two this repair adds) and the matching case goes red;
    move the lock below the ``adjust_*`` call and it goes red on the ordering clause.

    A writer with an EMPTY getter has no earlier row to lock — ``create_room``'s deciding state
    is the row it is inserting, and two concurrent builds are two different rooms that both
    legitimately count. It is still censused by the two tests above; only this does not apply.
    """
    function = _writers()[where]
    getter_name, subject = getter
    if not getter_name:
        pytest.skip(f"{where[0]}:{where[1]} has no deciding row to lock — {subject}")
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]

    locked_at = [
        call.lineno
        for call in calls
        if _called_name(call) == getter_name
        and any(
            keyword.arg == "for_update" and keyword.value.value is True
            for keyword in call.keywords
            if isinstance(keyword.value, ast.Constant)
        )
    ]
    assert locked_at, (
        f"{where[0]}:{function.name} moves the allotment counter but never calls "
        f"{getter_name}(..., for_update=True) — {subject} is what decides its delta, and two "
        "concurrent requests reading it unlocked both compute the same delta and both apply it"
    )

    wrote_at = [call.lineno for call in calls if _called_name(call) in _ALLOTMENT_WRITES]
    assert min(locked_at) < min(wrote_at), (
        f"{where[0]}:{function.name} locks {subject} at line {min(locked_at)} but touches the "
        f"counter at line {min(wrote_at)} — a lock taken after the delta was computed serializes "
        "nothing"
    )
