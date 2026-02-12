# WeatherInsight Schema Change Procedures

## Overview
This document provides comprehensive procedures for managing schema changes in WeatherInsight, including planning, testing, execution, and rollback strategies.

## Table of Contents
1. [Schema Change Types](#schema-change-types)
2. [Change Management Process](#change-management-process)
3. [Execution Procedures](#execution-procedures)
4. [Testing & Validation](#testing--validation)
5. [Rollback Procedures](#rollback-procedures)
6. [Common Scenarios](#common-scenarios)
7. [Best Practices](#best-practices)

---

## Schema Change Types

### 1. Backward-Compatible Changes
**Risk Level**: Low
**Downtime Required**: None

Examples:
- Adding new nullable columns
- Adding new tables
- Creating new indexes
- Adding new constraints (non-blocking)
- Increasing column sizes

### 2. Backward-Incompatible Changes
**Risk Level**: Medium-High
**Downtime Required**: Possible

Examples:
- Removing columns
- Renaming columns or tables
- Changing column types
- Adding NOT NULL constraints
- Modifying primary keys

### 3. Data Migration Changes
**Risk Level**: High
**Downtime Required**: Often

Examples:
- Splitting tables
- Merging tables
- Data transformations
- Denormalization
- Historical data reprocessing

---

## Change Management Process

### Phase 1: Planning (1-2 days)

#### Step 1: Document the Change
Create a schema change proposal document:

```markdown
# Schema Change Proposal: [Title]

## Motivation
Why is this change needed?

## Current Schema
```sql
-- Current table definition
```

## Proposed Schema
```sql
-- New table definition
```

## Impact Analysis
- Services affected: [list]
- Queries affected: [list]
- Downtime required: [estimate]
- Data migration required: [yes/no]
- Backward compatibility: [yes/no]

## Rollback Plan
How to revert if issues arise

## Testing Plan
How to validate the change

## Timeline
- Planning: [date]
- Testing: [date]
- Staging deployment: [date]
- Production deployment: [date]
```

#### Step 2: Review & Approval
```bash
# Create review issue
gh issue create --title "Schema Change: [Title]" \
  --body-file schema_change_proposal.md \
  --label schema-change

# Assign reviewers
# - Database admin
# - Service owners
# - DevOps engineer
```

### Phase 2: Development (2-3 days)

#### Step 1: Create Migration Script
```bash
# Create migration file
TIMESTAMP=$(date +%Y%m%d%H%M%S)
touch migrations/${TIMESTAMP}_description.sql

# Edit migration file
nano migrations/${TIMESTAMP}_description.sql
```

**Migration Template:**
```sql
-- Migration: ${TIMESTAMP}_description.sql
-- Author: [Your Name]
-- Date: [Date]
-- Description: [Brief description]

-- ============================================
-- PRE-MIGRATION CHECKS
-- ============================================

-- Verify current schema version
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM schema_registry 
    WHERE version = 'v1.0.0'
  ) THEN
    RAISE EXCEPTION 'Current schema version mismatch. Expected v1.0.0';
  END IF;
END $$;

-- Check for blocking locks
SELECT 
  pid, 
  usename, 
  pg_blocking_pids(pid) as blocked_by,
  query 
FROM pg_stat_activity 
WHERE cardinality(pg_blocking_pids(pid)) > 0;

-- ============================================
-- MIGRATION START
-- ============================================

BEGIN;

-- Set lock timeout (fail fast if table is locked)
SET LOCAL lock_timeout = '5s';

-- Your migration code here
ALTER TABLE quarterly_temperature_features 
ADD COLUMN IF NOT EXISTS new_column NUMERIC;

-- Update schema registry
UPDATE schema_registry 
SET version = 'v1.1.0', 
    updated_at = NOW()
WHERE table_name = 'quarterly_temperature_features';

-- Verify migration
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'quarterly_temperature_features'
    AND column_name = 'new_column'
  ) THEN
    RAISE EXCEPTION 'Migration verification failed';
  END IF;
END $$;

COMMIT;

-- ============================================
-- POST-MIGRATION TASKS
-- ============================================

-- Analyze table for query planner
ANALYZE quarterly_temperature_features;

-- Update statistics
VACUUM ANALYZE quarterly_temperature_features;
```

#### Step 2: Create Rollback Script
```sql
-- Rollback: ${TIMESTAMP}_description.sql
-- Date: [Date]

BEGIN;

-- Reverse the change
ALTER TABLE quarterly_temperature_features 
DROP COLUMN IF EXISTS new_column;

-- Revert schema version
UPDATE schema_registry 
SET version = 'v1.0.0', 
    updated_at = NOW()
WHERE table_name = 'quarterly_temperature_features';

COMMIT;
```

### Phase 3: Testing (3-5 days)

#### Step 1: Test in Development
```bash
# Start dev environment
docker-compose -f docker-compose.dev.yml up -d

# Apply migration
docker exec postgres psql -U weatherinsight -d weatherinsight \
  -f /migrations/${TIMESTAMP}_description.sql

# Run tests
cd services/api && pytest tests/ -v
cd services/processing && pytest tests/ -v
cd services/aggregation && pytest tests/ -v

# Verify data integrity
docker exec postgres psql -U weatherinsight -d weatherinsight \
  -f /migrations/verify_${TIMESTAMP}.sql
```

#### Step 2: Test in Staging
```bash
# Deploy to staging
./deploy_staging.sh

# Apply migration
ssh staging "docker exec postgres psql -U weatherinsight -d weatherinsight \
  -f /migrations/${TIMESTAMP}_description.sql"

# Run integration tests
pytest tests/integration/ --env=staging -v

# Performance testing
ab -n 1000 -c 10 https://staging-api.weatherinsight.com/api/v1/features/temperature
```

### Phase 4: Production Deployment (Scheduled)

See [Execution Procedures](#execution-procedures) below.

---

## Execution Procedures

### Procedure 1: Backward-Compatible Column Addition

**Use case**: Adding optional features, metadata columns

**Downtime**: None

#### Step 1: Pre-Migration Checks
```bash
# Verify no active long-running transactions
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT 
  pid,
  usename,
  state,
  query_start,
  NOW() - query_start AS duration,
  query
FROM pg_stat_activity
WHERE state != 'idle'
  AND NOW() - query_start > INTERVAL '5 minutes'
ORDER BY duration DESC;
EOF

# Expected: No long-running transactions
# If found, coordinate with users or wait for completion
```

#### Step 2: Apply Migration
```bash
# Backup first
docker exec postgres pg_dump -U weatherinsight weatherinsight | \
  gzip > /backups/pre_migration_$(date +%Y%m%d_%H%M%S).sql.gz

# Apply migration
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
BEGIN;

-- Add new column (nullable, no default)
ALTER TABLE quarterly_temperature_features 
ADD COLUMN IF NOT EXISTS extreme_cold_hours INTEGER;

-- Add column comment
COMMENT ON COLUMN quarterly_temperature_features.extreme_cold_hours 
IS 'Number of hours with temperature < -10°C';

-- Update schema version
UPDATE schema_registry 
SET version = 'v1.1.0',
    updated_at = NOW(),
    change_description = 'Added extreme_cold_hours column'
WHERE table_name = 'quarterly_temperature_features';

COMMIT;
EOF
```

#### Step 3: Verify & Backfill Data (Optional)
```bash
# Verify column exists
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT column_name, data_type, is_nullable FROM information_schema.columns 
   WHERE table_name = 'quarterly_temperature_features' 
   AND column_name = 'extreme_cold_hours';"

# Backfill historical data (if needed)
docker exec airflow-scheduler airflow dags trigger compute_extreme_cold_hours

# Or backfill with SQL
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
UPDATE quarterly_temperature_features
SET extreme_cold_hours = (
  -- Compute from raw data or set to NULL
  NULL
)
WHERE extreme_cold_hours IS NULL;
EOF
```

#### Step 4: Deploy Updated Code
```bash
# Update services to populate new column
git pull origin main
docker-compose build aggregation
docker-compose up -d aggregation

# Verify new data includes column
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT station_id, year, quarter, extreme_cold_hours 
   FROM quarterly_temperature_features 
   ORDER BY year DESC, quarter DESC LIMIT 5;"
```

---

### Procedure 2: Column Type Change

**Use case**: Changing data types (e.g., INTEGER → NUMERIC)

**Downtime**: Short (1-5 minutes depending on table size)

#### Step 1: Plan Migration Strategy

**Strategy A: Add-Replace-Drop (Recommended for large tables)**
- Minimal downtime
- Safer rollback
- Takes longer

**Strategy B: Direct ALTER (For small tables)**
- Brief table lock
- Faster
- Harder to rollback

#### Step 2: Execute Strategy A (Add-Replace-Drop)
```bash
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
-- Step 1: Add new column
BEGIN;
ALTER TABLE quarterly_temperature_features 
ADD COLUMN temp_mean_c_new NUMERIC(5,2);
COMMIT;

-- Step 2: Backfill new column
BEGIN;
UPDATE quarterly_temperature_features 
SET temp_mean_c_new = temp_mean_c::NUMERIC(5,2);
COMMIT;

-- Step 3: Verify data integrity
SELECT 
  COUNT(*) as total,
  COUNT(temp_mean_c) as old_count,
  COUNT(temp_mean_c_new) as new_count,
  COUNT(*) FILTER (WHERE temp_mean_c::text != temp_mean_c_new::text) as mismatches
FROM quarterly_temperature_features;

-- Expected: mismatches = 0

-- Step 4: Update application to use new column
-- (Deploy code that reads/writes temp_mean_c_new)

-- Step 5: Drop old column (after verification period)
BEGIN;
ALTER TABLE quarterly_temperature_features 
DROP COLUMN temp_mean_c;
COMMIT;

-- Step 6: Rename new column
BEGIN;
ALTER TABLE quarterly_temperature_features 
RENAME COLUMN temp_mean_c_new TO temp_mean_c;
COMMIT;

-- Step 7: Update schema registry
UPDATE schema_registry 
SET version = 'v1.2.0',
    change_description = 'Changed temp_mean_c to NUMERIC(5,2)'
WHERE table_name = 'quarterly_temperature_features';
EOF
```

#### Step 3: Execute Strategy B (Direct ALTER)
```bash
# Only for small tables or during maintenance window
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
BEGIN;

-- Stop API temporarily
-- docker-compose stop api

-- Direct type change
ALTER TABLE quarterly_temperature_features 
ALTER COLUMN temp_mean_c TYPE NUMERIC(5,2) USING temp_mean_c::NUMERIC(5,2);

-- Update schema registry
UPDATE schema_registry 
SET version = 'v1.2.0',
    change_description = 'Changed temp_mean_c to NUMERIC(5,2)'
WHERE table_name = 'quarterly_temperature_features';

COMMIT;

-- Restart API
-- docker-compose start api
EOF
```

---

### Procedure 3: Adding NOT NULL Constraint

**Use case**: Enforcing data integrity on existing columns

**Downtime**: Minimal

#### Step 1: Check for NULL Values
```bash
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
SELECT COUNT(*) as null_count
FROM quarterly_temperature_features
WHERE temp_mean_c IS NULL;
EOF

# If null_count > 0, must handle nulls first
```

#### Step 2: Handle NULL Values
```bash
# Option A: Fill with default value
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
UPDATE quarterly_temperature_features
SET temp_mean_c = 0.0
WHERE temp_mean_c IS NULL;
EOF

# Option B: Delete rows with NULLs (if appropriate)
# docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
# DELETE FROM quarterly_temperature_features
# WHERE temp_mean_c IS NULL;
# EOF
```

#### Step 3: Add Constraint
```bash
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
BEGIN;

-- Add NOT NULL constraint
ALTER TABLE quarterly_temperature_features 
ALTER COLUMN temp_mean_c SET NOT NULL;

-- Verify constraint
SELECT 
  conname, 
  contype, 
  pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'quarterly_temperature_features'::regclass;

COMMIT;
EOF
```

---

### Procedure 4: Table Splitting/Refactoring

**Use case**: Normalizing schema, improving performance

**Downtime**: Moderate (10-30 minutes)

#### Example: Split station metadata from features

#### Step 1: Create New Table
```sql
BEGIN;

-- Create new station_metadata table
CREATE TABLE IF NOT EXISTS station_metadata (
  station_id VARCHAR(10) PRIMARY KEY,
  name VARCHAR(255),
  state VARCHAR(100),
  latitude NUMERIC(8,5),
  longitude NUMERIC(8,5),
  elevation_m INTEGER,
  start_date DATE,
  end_date DATE,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Populate from existing data
INSERT INTO station_metadata (
  station_id, name, state, latitude, longitude, 
  elevation_m, start_date, end_date, is_active
)
SELECT DISTINCT
  station_id,
  station_name,
  station_state,
  station_lat,
  station_lon,
  station_elevation,
  MIN(year || '-' || (quarter * 3 - 2) || '-01')::DATE,
  MAX(year || '-' || (quarter * 3) || '-' || 
    CASE quarter WHEN 1 THEN '31' WHEN 2 THEN '30' 
                 WHEN 3 THEN '30' ELSE '31' END)::DATE,
  true
FROM quarterly_temperature_features
GROUP BY station_id, station_name, station_state, 
         station_lat, station_lon, station_elevation;

-- Add foreign key to features table
ALTER TABLE quarterly_temperature_features
ADD CONSTRAINT fk_station
FOREIGN KEY (station_id) REFERENCES station_metadata(station_id);

-- Create index
CREATE INDEX idx_station_metadata_state ON station_metadata(state);

COMMIT;
```

#### Step 2: Update Application Code
```bash
# Update services to query new station_metadata table
# Deploy updated code

git pull origin feature/station-metadata-split
docker-compose build api processing aggregation
docker-compose up -d api processing aggregation
```

#### Step 3: Remove Redundant Columns (After Verification)
```sql
BEGIN;

-- Drop denormalized columns
ALTER TABLE quarterly_temperature_features
DROP COLUMN IF EXISTS station_name,
DROP COLUMN IF EXISTS station_state,
DROP COLUMN IF EXISTS station_lat,
DROP COLUMN IF EXISTS station_lon,
DROP COLUMN IF EXISTS station_elevation;

-- Update schema version
UPDATE schema_registry 
SET version = 'v2.0.0',
    change_description = 'Normalized station metadata into separate table'
WHERE table_name = 'quarterly_temperature_features';

COMMIT;

-- Vacuum to reclaim space
VACUUM FULL quarterly_temperature_features;
```

---

### Procedure 5: Adding Index

**Use case**: Improving query performance

**Downtime**: None (with CONCURRENTLY)

#### Step 1: Analyze Query Performance
```sql
-- Identify slow queries
SELECT 
  query,
  mean_exec_time,
  calls
FROM pg_stat_statements
WHERE query LIKE '%quarterly_temperature_features%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

#### Step 2: Create Index Concurrently
```bash
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
-- Create index without blocking writes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_temp_features_station_year 
ON quarterly_temperature_features(station_id, year, quarter);

-- Verify index created
SELECT 
  tablename, 
  indexname, 
  indexdef
FROM pg_indexes
WHERE tablename = 'quarterly_temperature_features';
EOF

# Note: CONCURRENTLY cannot run inside transaction block
```

#### Step 3: Monitor Index Usage
```sql
-- Check index usage after 24 hours
SELECT 
  schemaname,
  tablename,
  indexname,
  idx_scan as index_scans,
  idx_tup_read as tuples_read,
  idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE tablename = 'quarterly_temperature_features'
ORDER BY idx_scan DESC;
```

---

## Testing & Validation

### Pre-Migration Testing

#### 1. Schema Validation
```bash
# Create test database
docker exec postgres psql -U postgres << 'EOF'
CREATE DATABASE weatherinsight_test;
\c weatherinsight_test
-- Apply current schema
\i /docker-entrypoint-initdb.d/01_init_schema.sql
EOF

# Apply migration to test database
docker exec postgres psql -U weatherinsight -d weatherinsight_test \
  -f /migrations/${TIMESTAMP}_description.sql

# Run schema validation
docker exec postgres psql -U weatherinsight -d weatherinsight_test \
  -c "\d+ quarterly_temperature_features"
```

#### 2. Data Integrity Tests
```sql
-- Test script: verify_migration.sql

-- Check row counts (should not change unless migration modifies data)
SELECT 
  'quarterly_temperature_features' as table_name,
  COUNT(*) as row_count 
FROM quarterly_temperature_features;

-- Check for NULL values in NOT NULL columns
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'quarterly_temperature_features'
  AND is_nullable = 'NO'
  AND NOT EXISTS (
    SELECT 1 FROM quarterly_temperature_features
    WHERE column_name IS NOT NULL
  );

-- Check foreign key integrity
SELECT COUNT(*)
FROM quarterly_temperature_features f
LEFT JOIN station_metadata s ON f.station_id = s.station_id
WHERE s.station_id IS NULL;

-- Expected: 0 orphaned records

-- Check uniqueness constraints
SELECT station_id, year, quarter, COUNT(*)
FROM quarterly_temperature_features
GROUP BY station_id, year, quarter
HAVING COUNT(*) > 1;

-- Expected: Empty result
```

#### 3. Performance Testing
```bash
# Test query performance before and after
docker exec postgres psql -U weatherinsight -d weatherinsight << 'EOF'
EXPLAIN ANALYZE
SELECT * FROM quarterly_temperature_features
WHERE station_id = '00433' AND year = 2023
ORDER BY quarter;
EOF

# Compare execution time and plan
```

### Post-Migration Validation

#### 1. Service Health Checks
```bash
# Check all services
curl http://localhost:8000/health
curl http://localhost:8080/health
curl http://localhost:9090/-/healthy

# Run integration tests
pytest tests/e2e/ -v --env=production
```

#### 2. Data Quality Checks
```bash
# Trigger data quality DAG
docker exec airflow-scheduler airflow dags trigger weatherinsight_data_quality

# Review results
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT * FROM data_quality_results ORDER BY check_timestamp DESC LIMIT 10;"
```

#### 3. API Validation
```bash
# Test API endpoints
curl "http://localhost:8000/api/v1/features/temperature?year=2023&quarter=1&limit=10" | jq .

# Verify schema in response matches new structure
```

---

## Rollback Procedures

### Automated Rollback

#### Step 1: Detect Issue
```bash
# Monitor error rates
curl -s http://localhost:9090/api/v1/query?query='rate(api_errors_total[5m])' | jq .

# If error rate spikes after migration, initiate rollback
```

#### Step 2: Stop Services
```bash
# Stop services that depend on schema
docker-compose stop api aggregation processing
```

#### Step 3: Rollback Database
```bash
# Apply rollback script
docker exec postgres psql -U weatherinsight -d weatherinsight \
  -f /migrations/rollback_${TIMESTAMP}_description.sql

# Verify rollback
docker exec postgres psql -U weatherinsight -d weatherinsight \
  -c "SELECT version FROM schema_registry WHERE table_name = 'quarterly_temperature_features';"

# Expected: Previous version (e.g., v1.0.0)
```

#### Step 4: Rollback Code
```bash
# Revert to previous code version
git checkout <PREVIOUS_TAG>
docker-compose build api aggregation processing
docker-compose up -d api aggregation processing
```

#### Step 5: Validate Rollback
```bash
# Run health checks
./scripts/health_check.sh

# Test API
curl http://localhost:8000/api/v1/features/temperature?year=2023

# Verify error rate returns to normal
```

### Point-in-Time Recovery

If rollback script is not sufficient:

```bash
# Stop all services
docker-compose stop

# Restore database from pre-migration backup
docker exec postgres psql -U postgres -c "DROP DATABASE weatherinsight;"
docker exec postgres psql -U postgres -c "CREATE DATABASE weatherinsight;"

gunzip -c /backups/pre_migration_20240208_100000.sql.gz | \
  docker exec -i postgres psql -U weatherinsight -d weatherinsight

# Verify restoration
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT COUNT(*) FROM quarterly_temperature_features;"

# Restart services
docker-compose up -d
```

---

## Common Scenarios

### Scenario 1: Adding New Product Type

**Requirements**:
- New feature tables
- New metadata entries
- Updated API endpoints

**Steps**:
```sql
-- Create new table for cloud cover features
CREATE TABLE quarterly_cloudcover_features (
  id SERIAL PRIMARY KEY,
  station_id VARCHAR(10) NOT NULL,
  year INTEGER NOT NULL,
  quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
  
  -- Cloud cover features
  cloud_cover_mean_oktas NUMERIC(4,2),
  clear_sky_hours INTEGER,
  overcast_hours INTEGER,
  partly_cloudy_hours INTEGER,
  
  -- Quality metrics
  valid_observations INTEGER,
  missing_observations INTEGER,
  quality_score NUMERIC(3,2),
  
  -- Metadata
  dataset_version VARCHAR(20),
  created_at TIMESTAMP DEFAULT NOW(),
  
  UNIQUE(station_id, year, quarter),
  FOREIGN KEY (station_id) REFERENCES station_metadata(station_id)
);

-- Create indexes
CREATE INDEX idx_cloudcover_station_year ON quarterly_cloudcover_features(station_id, year, quarter);
CREATE INDEX idx_cloudcover_year_quarter ON quarterly_cloudcover_features(year, quarter);

-- Register in schema registry
INSERT INTO schema_registry (
  table_name, 
  version, 
  schema_definition, 
  created_at
) VALUES (
  'quarterly_cloudcover_features',
  'v1.0.0',
  '{"type": "quarterly_features", "product": "cloud_cover", "columns": [...]}',
  NOW()
);
```

### Scenario 2: Adding Computed Column

**Requirements**:
- Add column to store precomputed value
- Backfill historical data
- Update aggregation code

**Steps**:
```sql
-- Add column
ALTER TABLE quarterly_temperature_features 
ADD COLUMN temp_range_c NUMERIC(5,2);

-- Backfill with computed values
UPDATE quarterly_temperature_features
SET temp_range_c = temp_max_c - temp_min_c
WHERE temp_range_c IS NULL;

-- Add NOT NULL constraint after backfill
ALTER TABLE quarterly_temperature_features
ALTER COLUMN temp_range_c SET NOT NULL;

-- Create index for queries
CREATE INDEX idx_temp_features_range ON quarterly_temperature_features(temp_range_c);
```

### Scenario 3: Schema Version Migration

**Requirements**:
- Migrate from v1.x to v2.x
- Major restructuring
- Multi-step process

**Steps**:
```bash
# Phase 1: Create v2 tables (run alongside v1)
docker exec postgres psql -U weatherinsight -d weatherinsight \
  -f /migrations/v2_create_tables.sql

# Phase 2: Dual-write (write to both v1 and v2)
# Deploy code that writes to both schemas

# Phase 3: Backfill v2 tables
docker exec airflow-scheduler airflow dags trigger backfill_v2_schema

# Phase 4: Validate v2 data
pytest tests/schema_v2_validation.py -v

# Phase 5: Switch reads to v2
# Deploy code that reads from v2 tables

# Phase 6: Monitor for 48 hours

# Phase 7: Drop v1 tables (after verification period)
docker exec postgres psql -U weatherinsight -d weatherinsight \
  -f /migrations/v1_drop_tables.sql
```

---

## Best Practices

### Planning
1. **Document everything**: Create detailed migration plans
2. **Review changes**: Peer review by database admin and service owners
3. **Test thoroughly**: Test in dev → staging → production
4. **Communicate early**: Notify stakeholders of upcoming changes
5. **Schedule wisely**: Perform during low-traffic periods

### Execution
1. **Backup first**: Always create backups before schema changes
2. **Use transactions**: Wrap DDL in BEGIN/COMMIT for atomicity
3. **Set timeouts**: Use lock_timeout to fail fast
4. **Monitor closely**: Watch error rates, latency, resource usage
5. **Have rollback ready**: Test rollback procedures before migration

### Post-Migration
1. **Validate data**: Run comprehensive data quality checks
2. **Monitor metrics**: Watch for anomalies for 24-48 hours
3. **Update documentation**: Keep schema docs current
4. **Document learnings**: Record issues and solutions for future
5. **Clean up**: Remove old code, unused columns after verification period

### Security
1. **Audit changes**: Log all schema modifications
2. **Restrict access**: Only authorized users can modify schemas
3. **Version control**: Store migrations in git
4. **Approval process**: Require sign-off for production changes
5. **Compliance**: Ensure changes meet regulatory requirements

---

## Troubleshooting

### Issue: Migration Stuck (Waiting for Lock)

**Symptoms**: Migration command hangs

**Diagnosis**:
```sql
-- Check blocking queries
SELECT 
  blocked.pid AS blocked_pid,
  blocked.query AS blocked_query,
  blocking.pid AS blocking_pid,
  blocking.query AS blocking_query
FROM pg_stat_activity AS blocked
JOIN pg_stat_activity AS blocking 
  ON blocking.pid = ANY(pg_blocking_pids(blocked.pid))
WHERE blocked.wait_event_type = 'Lock';
```

**Solution**:
```sql
-- Terminate blocking query (carefully!)
SELECT pg_terminate_backend(<blocking_pid>);

-- Or wait for query to complete
```

### Issue: Migration Failed Mid-Transaction

**Symptoms**: Error during ALTER TABLE, database in inconsistent state

**Solution**:
```bash
# Check if transaction rolled back automatically
docker exec postgres psql -U weatherinsight -d weatherinsight -c \
  "SELECT version FROM schema_registry WHERE table_name = 'quarterly_temperature_features';"

# If version unchanged, migration rolled back successfully
# Review error, fix migration script, retry

# If version changed but schema incomplete, manual rollback needed
docker exec postgres psql -U weatherinsight -d weatherinsight \
  -f /migrations/rollback_${TIMESTAMP}_description.sql
```

### Issue: Performance Degradation After Migration

**Symptoms**: Slow queries, high CPU usage

**Diagnosis**:
```sql
-- Check for missing indexes
SELECT 
  schemaname, 
  tablename, 
  indexname,
  idx_scan as index_scans
FROM pg_stat_user_indexes
WHERE tablename = 'quarterly_temperature_features'
  AND idx_scan < 100
ORDER BY idx_scan;

-- Check query plans
EXPLAIN ANALYZE
SELECT * FROM quarterly_temperature_features 
WHERE year = 2023;
```

**Solution**:
```sql
-- Recreate statistics
ANALYZE quarterly_temperature_features;

-- Add missing indexes
CREATE INDEX CONCURRENTLY idx_name ON table_name(column);

-- Consider VACUUM FULL if fragmentation suspected
VACUUM FULL ANALYZE quarterly_temperature_features;
```

---

## Appendix

### Schema Registry Structure
```sql
CREATE TABLE schema_registry (
  id SERIAL PRIMARY KEY,
  table_name VARCHAR(100) NOT NULL,
  version VARCHAR(20) NOT NULL,
  schema_definition JSONB,
  change_description TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(table_name, version)
);
```

### Migration File Naming Convention
```
YYYYMMDDHHMMSS_description.sql
20240208143002_add_extreme_cold_hours_column.sql
20240208150000_split_station_metadata.sql
```

### Emergency Contacts
- **Database Admin**: dba@example.com
- **DevOps Lead**: devops@example.com
- **On-Call Engineer**: oncall@example.com

---

## Version History
- v1.0.0 (2026-02-08): Initial schema change procedures documentation
