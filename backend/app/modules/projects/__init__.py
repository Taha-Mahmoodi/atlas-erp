"""Projects module (PLAN 11.1) — the PS-lite cost-collector module (s4hana-parity §PS).

PLAN 11.1 delivers the DELIBERATELY SMALL Project-System core the parity doc scopes
(docs/research/s4hana-parity.md §PS): PROJECTS with a WBS-element HIERARCHY as COSTING OBJECTS, time
and purchases POSTABLE to a WBS, and a PROJECT COST REPORT. Everything else PS (networks/activities,
scheduling, cost planning, budgeting with availability control, settlement, results analysis /
revenue recognition, customer-project billing) is explicitly OUT of v1 — recorded in the parity doc
(D-056).

THE OPAQUE-WBS-DIMENSION MODEL (D-056, D-017/D-029). A WBS element's ``id`` is the COSTING OBJECT —
it is the OPAQUE project dimension a finance journal line (``fin_journal_lines.project_id``, already
on the universal journal since D-017) and a HR time entry (``hr_time_entries.project_id``) tag when
work / purchases are "posted to a WBS". Finance and HR do NOT validate that id against this
module — it stays an opaque tag so FINANCE STAYS AT THE BOTTOM of the dependency order (D-029).
Projects posts NOTHING itself; it OWNS the WBS masters + the report.

Projects sits ABOVE finance, hr and sales in the dependency order (STRUCTURE §5 / D-056). It:

- READS DOWNWARD via ``finance/queries`` (``cost_center_exists`` for a project's optional cost
  centre; ``costs_by_project_dimension`` for the journal-projection actuals by WBS id — a sanctioned
  finance/queries addition), ``hr/queries.approved_hours_for_project`` (approved timesheet hours by
  WBS id), and ``sales/queries.customer_exists`` (a project's optional customer) — never their
  models, never a cross-module FK.
- Does NOT subscribe to or publish any cross-module event in v1: projects is masters + a READ
  report, it triggers no cross-module write. So there is NO events.py / handlers.py here (an empty
  event file would be a dead file — STRUCTURE §8.3).

No cycle (D-056): finance / hr / sales are OLDER modules and import nothing from projects, so
projects→{finance,hr,sales}/queries is one-directional (STRUCTURE §5 bans only bidirectional query
imports). ``projects/queries.py`` is the only file a later module would import; it exposes
``wbs_element_exists`` so a future projects-owned posting gate (or finance/hr validation, when the
dependency direction allows) COULD validate a WBS dimension — today they treat it as opaque.

THE PROJECT COST REPORT is a BOUNDED PROJECTION (PERFORMANCE §6, D-056): for a project it loads its
WBS ids ONCE, then runs ONE finance journal projection over all those ids
(``costs_by_project_dimension``) and ONE hr aggregate per WBS for the hours — no per-WBS N+1 on the
actuals — then rolls each WBS up to the project total and computes budget − actual variance.
"""
