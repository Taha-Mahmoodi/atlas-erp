"""The D-007 tenancy grep gate (#82) — the CI control the architecture docs promise.

The ORM tenant filter intentionally skips non-ORM statements (``tenancy.py``), so raw
``text(...)`` or a Core ``Table.insert()`` against a tenant table would bypass tenant isolation
silently. Core-level statements are sanctioned only inside ``app/core`` (audit writer, numbering,
idempotency — tenant_id always explicit) and in ``tests/`` (the DB-guard tests bypass the service
layer on purpose). This test IS the gate: it fails the build the moment either pattern appears
under ``app/modules/``. Runs in the CI backend job's pytest step, so it is a required check on
``dev`` and ``main``.
"""

import re
from pathlib import Path

_APP_MODULES = Path(__file__).resolve().parents[2] / "app" / "modules"

# Bare ``text(`` (however imported), qualified ``sa.text(`` / ``sqlalchemy.text(``, and Core
# ``<table>.insert(`` — but not ``read_text(`` / ``insert(Model)`` (the ORM-enabled function
# form, which the tenant filter DOES see).
_BANNED = re.compile(r"(?:^|[^\w.])text\(|\bsa\.text\(|\bsqlalchemy\.text\(|\.insert\(")


def test_no_raw_text_or_core_insert_under_app_modules() -> None:
    offenders: list[str] = []
    for path in sorted(_APP_MODULES.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]  # a comment may NAME the pattern; code may not use it
            if _BANNED.search(code):
                offenders.append(f"{path.relative_to(_APP_MODULES.parent.parent)}:{lineno}")
    assert not offenders, (
        "Raw text() / Core .insert( under app/modules/ bypasses the D-007 tenant filter. "
        "Use ORM statements (or move a genuinely-core statement into app/core with an "
        f"explicit tenant_id). Offenders: {offenders}"
    )
