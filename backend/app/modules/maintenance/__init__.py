"""Maintenance module (PLAN 9.2) — the SEVENTH business module (s4hana-parity QM/PM).

PLAN 9.2 OPENS the Plant-Maintenance side of the parity QM/PM area with the DELIBERATELY SMALL PM
core the parity doc scopes (docs/research/s4hana-parity.md §QM/PM): an EQUIPMENT register,
CORRECTIVE maintenance orders (created ad-hoc against a piece of equipment), and PREVENTIVE
maintenance via interval-based PLANS that GENERATE due orders on a periodic run. Everything else PM
(functional location hierarchies, maintenance notifications, measurement points/counters, task
lists, and counter/strategy-based scheduling) is explicitly OUT of v1 — recorded in the parity doc
(D-051).

Maintenance sits ABOVE finance in the dependency order (STRUCTURE §5 / D-051). It:

- READS via ``finance/queries.cost_center_exists`` DOWNWARD (D-029) — an equipment's optional cost
  centre for cost attribution — never finance models, never a cross-module FK.
- Does NOT subscribe to or publish any cross-module event in v1: a completed maintenance order
  RECORDS its ``actual_cost`` on the order row (record-only — no GL posting, D-051). The parity
  scope is "equipment register + corrective/preventive orders", not full work-order costing; a GL
  posting through the cost centre is a documented later. So there is NO events.py / handlers.py here
  (an empty event file would be a dead file — STRUCTURE §8.3).

No cycle (D-051): finance is an OLDER module and imports nothing from maintenance, so
maintenance→finance/queries is one-directional (STRUCTURE §5 bans only bidirectional query imports).
``maintenance/queries.py`` is the only file a later module would import.

The PREVENTIVE generation run scans the tenant's ACTIVE plans whose ``next_due_date`` has arrived
and creates one PREVENTIVE order per due plan, advancing the plan past the run date. It runs INLINE
at v1 scale — the 6.4 reorder-scan precedent (D-032: a job is the later if plan counts grow). It is
set-based (PERFORMANCE §2) and idempotent (a second run the same day generates nothing).
"""
