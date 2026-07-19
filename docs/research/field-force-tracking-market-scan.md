# Field Force Tracking — Market Scan

This document scopes a candidate capability — real-time tracking of field marketers/sales reps (location, activity, tasks, goals, and territory/zone assignment) delivered as a tablet app — that is **not** part of Atlas v1 and has no analogue in the [S/4HANA parity map](s4hana-parity.md). SAP's closest adjacent capability, Field Service Management, is a separate cloud product outside core S/4HANA and is not benchmarked here. This scan instead surveys the dedicated "field force management / field sales tracking / retail execution" software category directly, so that if this capability is built, its scope is grounded in what practitioners in that category consider baseline. Research conducted July 2026 via public product and feature pages.

**Relationship to Atlas CRM.** Atlas's CRM module (Phase 12, D-057) is deliberately scoped as a lead → opportunity pipeline; campaigns, marketing automation, and field-rep tracking are explicitly out of v1 (see `docs/modules/crm.md`). A field-tracking capability would be a materially different problem — live location/geofencing, an offline-capable tablet client, background GPS — rather than an extension of the existing CRM data model. Whether and how it fits into Atlas is an open design question, tracked separately from this scan.

## Products surveyed

Badger Maps, SPOTIO, Repsly, Zenput, LeadSquared (Field Force Automation), BeatRoute, SalesRabbit, TrackoField, Lystloc, Unolo, and (referenced but not deep-dived) AllGeo, FieldServicely, B2Field, TrackObit, Fieldproxy.

## Consolidated feature list

### 1. Real-time location tracking
- Live map of all reps' current position
- GPS breadcrumbs/trails — full path traveled through the day, replayable
- Location history, distance-traveled reports, device battery/network status

### 2. Geofencing & zone/territory management
- Manager-drawn virtual boundaries (polygons, multi-coordinate) around sites or whole territories
- Geo-verified check-in/check-out — a visit or attendance mark only registers inside the geofence
- Geofence-violation tracking and real-time deviation alerts
- Per-rep territory/zone assignment with territory-level performance reporting
- AI/route-optimized daily visit sequences ("beat plans") within a zone

### 3. Task & goal assignment
- One-off and recurring task assignment, with priority and due dates
- Proximity/skill/availability-based auto-allocation of tasks
- Individual and team goal/target setting, with a target-vs-achievement report
- Checklists/structured forms attached to a task or visit
- Automated corrective/follow-up tasks on failure conditions

### 4. Visit & activity tracking
- One-tap, time- and location-stamped check-in/check-out per visit
- Activity logging beyond location: calls, meetings, notes, visit outcomes, competitor mentions
- Remote check-in for off-site work not tied to a geofence
- Photo capture with annotation as proof of visit; AI photo recognition for shelf/planogram audits (retail-specific)
- Voice notes / speech-to-text for field data entry

### 5. Route planning & optimization
- Auto-optimized daily route across assigned visits
- Manual territory/route drawing, then optimize
- Coverage-gap analysis for under-served parts of a territory

### 6. Attendance
- Automated or manual check-in/out against a workday template
- Geo-verified attendance; face-recognition attendance (anti-spoofing) in some products
- Leave management

### 7. Order, expense & proof capture
- In-app order booking against a product catalog with custom pricing/discounts
- Expense/mileage capture with receipt photo and hierarchy-based approval workflows
- Digital signature capture for agreements

### 8. Reporting & manager dashboards
- Real-time dashboard: task completion rates, visit compliance, cross-team performance
- Rep/team leaderboards
- Three-layer KPI framework common across the category: **Activity** (visits/calls made), **Execution** (quality of the visit), **Outcome** (revenue/growth per territory)
- Drill-down reports per site/district/rep

### 9. Offline mode
- Full form/checklist completion without connectivity, with sync on reconnect — depth varies by vendor, from simple data caching to full submission queuing

### 10. Gamification (seen in a subset of products)
- Leaderboards, badges, redeemable rewards for hitting KPIs

### 11. Integrations
- CRM sync (Salesforce, HubSpot, Zoho, Dynamics 365) and ERP/payroll integration

## Baseline for a v1, if built

A competitive v1 needs at minimum: live map + breadcrumbs, geofenced zones with violation alerts, task assignment with due dates and completion tracking, per-rep goals with a target-vs-achievement report, geofence-gated visit check-in/out with notes and photos, a manager dashboard with drill-down reporting, and offline capture with sync-on-reconnect. AI photo/shelf recognition, gamification, and AI copilots are category differentiators, not baseline, and belong in a later phase.
