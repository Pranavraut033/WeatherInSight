# WeatherInsight Documentation Index

Comprehensive guide to the WeatherInsight weather data platform. Navigate by use case or explore technical specifications.

---

## Quick Start
- **New to the project?** Start with [README.md](../README.md) for project overview
- **Setting up locally?** See [runbook.md](runbook.md)
- **Running in production?** Go to [OPERATIONS_HANDOVER.md](OPERATIONS_HANDOVER.md)

---

## Core Documentation

### System Design & Requirements
- [requirements.md](requirements.md): Project scope, data source, architecture overview
- [DATA_CONTRACTS.md](DATA_CONTRACTS.md): Raw and curated data schemas

### Planning & Roadmap
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md): 9-milestone development roadmap
- [MILESTONES.md](MILESTONES.md): Project milestone status

---

## Development & Operations

### Local Development
- [runbook.md](runbook.md): Docker setup, local service operations, testing
- [TESTING_STRATEGY.md](TESTING_STRATEGY.md): Testing approach and tools

### Production Operations
- [OPERATIONS_HANDOVER.md](OPERATIONS_HANDOVER.md): Daily operations manual
- [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md): Deployment strategies
- [MONITORING_GUIDE.md](MONITORING_GUIDE.md): Observability setup

### Incident & Change Management
- [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md): Incident resolution process
- [BACKFILL_PROCEDURES.md](BACKFILL_PROCEDURES.md): Historical data reprocessing
- [SCHEMA_CHANGE_PROCEDURES.md](SCHEMA_CHANGE_PROCEDURES.md): Schema modification guidelines

---

## Historical & Archived Documents
- See the [ARCHIVED/](ARCHIVED/) directory for milestone completion records

## Notes
- Always refer to the most recent document version
- Consult project maintainers for clarifications

---

## Archived Project Records
Files in [ARCHIVED/](ARCHIVED/) document historical milestone completions (M2-M9). These are reference materials for understanding what was implemented, not operational procedures.

---

## Navigation Tips

| Use Case | Documents |
|----------|-----------|
| **I need to set up the system locally** | [runbook.md](runbook.md) |
| **I need to understand data schemas** | [DATA_CONTRACTS.md](DATA_CONTRACTS.md) |
| **I'm on-call and something broke** | [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) → [OPERATIONS_HANDOVER.md](OPERATIONS_HANDOVER.md) |
| **I need to backfill missing data** | [BACKFILL_PROCEDURES.md](BACKFILL_PROCEDURES.md) |
| **I'm deploying to production** | [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) → [OPERATIONS_HANDOVER.md](OPERATIONS_HANDOVER.md) |
| **I need to change a schema** | [SCHEMA_CHANGE_PROCEDURES.md](SCHEMA_CHANGE_PROCEDURES.md) |
| **I need to monitor the system** | [MONITORING_GUIDE.md](MONITORING_GUIDE.md) |
| **I want the full project history** | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) → [ARCHIVED/](ARCHIVED/) |

---

## Key Contacts & Escalation

Refer to [OPERATIONS_HANDOVER.md](OPERATIONS_HANDOVER.md#emergency-procedures) for on-call schedules, escalation contacts, and emergency procedures.
