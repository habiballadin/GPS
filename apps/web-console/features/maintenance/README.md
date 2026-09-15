# Maintenance feature

Own service plans, work orders, inspections, parts, vendors, downtime, and maintenance cost views.

`GET /api/v1/maintenance/predictions` provides an explainable 30-day risk
watchlist using due service plans, open defects, active work orders, diagnostic
telemetry, and data-quality coverage. It is intentionally a deterministic
baseline so an ML scoring worker can replace the implementation without changing
the UI contract.
