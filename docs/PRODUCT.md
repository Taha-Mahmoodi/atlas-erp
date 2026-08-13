# PRODUCT.md — Atlas ERP frontend

## Register

**Product.** Design serves the work: authenticated app UI for running a business — data tables,
posting forms, workbenches, dashboards. No marketing surfaces live in this repo.

## Users & purpose

Operators doing repetitive, correctness-critical work all day: accountants posting journals and
clearing invoices, warehouse staff counting and moving stock, buyers matching invoices, planners
reading MRP output, admins wiring roles. Their context is a desk (occasionally a warehouse
laptop), dozens of screens per day, muscle memory over novelty. The job on any screen: find the
document, verify the numbers, act (post / clear / release), move on.

## Personality

Calm, precise, institutional. Three words: **legible, dense, dependable.** The benchmark is
SAP S/4HANA's Fiori language (CLAUDE.md pins "Fiori-inspired role-based home pages"): light
surfaces, one signal blue, generous data density, nothing decorative. The interface should
disappear into the task; a user fluent in Fiori, Linear, or Stripe Dashboard should trust every
control on first sight.

## Anti-references

- Consumer-SaaS landing flash: gradients, glassmorphism, hero metrics, orchestrated page-load motion.
- Cream/parchment "warm neutral" body backgrounds.
- Cards for everything; nested cards; side-stripe accent borders.
- Custom scrollbars, invented form controls, modals as the first answer.

## Strategic principles

1. **Density is a feature.** ERP users compare rows; compact tables and tight rhythm beat airy layouts.
2. **State vocabulary over decoration.** Color signals status (posted/draft/exception), selection, and destructive intent — never mood.
3. **Every interactive component ships all states**: default, hover, focus, active, disabled, loading, error, empty.
4. **Terminology lock** (STRUCTURE §7): item, vendor, customer, warehouse, journal entry — UI labels may be overridden per industry template, internal names never.
5. **Accessibility floor**: WCAG AA contrast (≥4.5:1 body), full keyboard operability, visible focus.
