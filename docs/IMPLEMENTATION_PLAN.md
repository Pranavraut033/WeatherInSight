# WeatherInsight Implementation Plan

Assumptions
- Single repo with Docker Compose running MinIO, Postgres, Airflow, Spark, FastAPI, Prometheus/Grafana.
- Quarterly batch runs; DWD hourly station data as source.
- MinIO raw zone (immutable), Postgres curated mart.

Phase 0 — Foundations (Week 1)
- Define DWD products, station set, date range, and hourly granularity.
- Establish bucket/prefix layout for raw data in MinIO.
- Define raw and curated schemas + versioning rules.
Deliverables
- docs/requirements.md
- docs/data-contracts/

Phase 1 — Infrastructure & Dev Env (Week 1–2)
- Compose stack for MinIO, Postgres, Airflow, Spark, FastAPI, monitoring.
- Env config and secrets handling.
Deliverables
- docker-compose.yml
- .env.example
- docs/runbook.md

Phase 2 — Ingestion Service (Week 2–3)
- Incremental sync against DWD catalog/manifest.
- Hash verification and immutable storage to MinIO raw zone.
- Emit dataset metadata (date range, station IDs, file list, hashes).
Deliverables
- services/ingestion/
- Metadata entries in registry

Phase 3 — Metadata & Governance (Week 3)
- Schema registry tables or file-backed registry.
- Track dataset versions and schema changes.
Deliverables
- services/metadata/ or db/migrations/
- Change log

Phase 4 — Spark Processing (Week 4–5)
- Parse raw files from MinIO; enforce schemas.
- Missing value handling, unit normalization, station joins.
- Write cleaned/staged datasets.
Deliverables
- services/processing/
- Unit tests for parsing

Phase 5 — Aggregation & Feature Build (Week 5–6)
- Define quarterly features (means, sums, missingness ratios).
- Aggregate and write curated tables to Postgres.
Deliverables
- services/aggregation/
- Curated tables in Postgres

Phase 6 — Orchestration (Week 6–7)
- Airflow DAG: ingestion → processing → aggregation → publish.
- Idempotent runs and backfill support.
Deliverables
- services/orchestrator/

Phase 7 — Delivery API (Week 7–8)
- FastAPI endpoints for feature tables.
- Pagination and filtering by station/time/variable.
Deliverables
- services/api/
- openapi.yaml

Phase 8 — QA, Observability, Hardening (Week 8–9)
- End-to-end test run with sample DWD data.
- Data quality checks and alerts.
Deliverables
- tests/e2e/
- Monitoring dashboards

Phase 9 — Docs & Handover (Week 9)
- Setup, backfill, schema-change runbooks.
Deliverables
- docs/
