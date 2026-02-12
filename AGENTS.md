# AGENTS.md — WeatherInsight Session Guide

Purpose
- Provide consistent, repeatable guidance for each session.
- Ensure uniform outputs and step-by-step execution for WeatherInsight.

Session Defaults
- Work in this repo root only.
- Keep files ASCII unless the existing file uses Unicode.
- Prefer small, incremental edits with clear deliverables.
- Update docs when behavior or scope changes.

Architecture Summary
- Source: DWD Open Data hourly station observations (Germany).
- Raw zone: MinIO (immutable objects).
- Metadata & governance: schema + dataset version registry.
- Batch: Airflow orchestrates Spark jobs quarterly.
- Curated mart: PostgreSQL.
- Serving: FastAPI.

Folder Conventions
- docs/ : requirements, runbooks, data contracts, plans.
- services/ingestion/ : DWD sync and raw storage.
- services/metadata/ : schema registry + version tracking.
- services/processing/ : Spark parsing/cleaning.
- services/aggregation/ : Spark feature builds.
- services/orchestrator/ : Airflow DAGs.
- services/api/ : FastAPI.
- tests/ : unit and end-to-end tests.
- infra/ : local/dev infrastructure assets.

Definition of Done (DoD)
- Code compiles or runs locally in Docker Compose.
- Data contracts updated for any schema change.
- Tests updated or added when behavior changes.
- Runbook updated for operational changes.

Standard Outputs (per session)
- What changed (files + rationale).
- Any assumptions made.
- Next steps (1–3 options).

Next Steps Roadmap
1) Infrastructure
   - docker-compose.yml
   - .env.example
   - docs/runbook.md updates
2) Data Contracts
   - Raw schema(s)
   - Curated feature schema(s)
3) Ingestion Service
   - DWD sync + checksum verification
   - Raw zone object layout
4) Metadata & Governance
   - Schema registry tables and migration
   - Dataset versioning logic
5) Processing & Aggregation
   - Spark jobs for parsing + quarterly features
   - Data quality checks
6) Orchestration
   - Airflow DAGs with quarterly schedule
7) Delivery API
   - FastAPI endpoints for feature access
8) QA/Observability
   - E2E tests
   - Prometheus/Grafana dashboards

Session Checklist
- Confirm which roadmap step is active.
- Implement smallest viable slice.
- Update docs/tests if needed.
