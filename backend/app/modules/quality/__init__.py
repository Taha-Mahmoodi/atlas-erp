"""Quality module (PLAN 9) — the sixth business module (s4hana-parity QM/PM).

PLAN 9.1 opens it with the DELIBERATELY SMALL QM core the parity doc scopes (s4hana-parity §QM): the
goods-receipt inspection FLAG → inspection LOT → accept/reject usage DECISION with a stock
DISPOSITION. Everything else QM (inspection plans, master inspection characteristics, results
recording, usage-decision code catalogs, quality notifications/CAPA, certificates) is explicitly OUT
of v1 — recorded in docs/research/s4hana-parity.md.

Quality sits ABOVE inventory and procurement in the dependency order (STRUCTURE §5 / D-050). It:

- SUBSCRIBES to procurement's ``GoodsReceiptPosted`` (importing procurement/events — the sanctioned
  declarative-event import) to CREATE one OPEN inspection lot per ``requires_inspection`` GR line,
  in
  the SAME transaction as the GR post (D-011). It NEVER imports procurement's service.
- READS via ``inventory/queries`` DOWNWARD (D-029) — bin existence, on-hand — never inventory
models.
- PUBLISHES its OWN ``InspectionDispositioned`` event on a REJECT so inventory's ``handlers.py``
moves
  the rejected stock (SCRAP = an ADJUSTMENT-out write-off; BLOCK = a TRANSFER to a blocked bin). It
  NEVER imports inventory's service.

No cycle (D-050): procurement and inventory are OLDER modules and import nothing from quality, so
quality→procurement/events and quality→inventory/queries are one-directional (STRUCTURE §5 bans only
bidirectional query imports). ``quality/queries.py`` is the only file a later module would import.
"""
